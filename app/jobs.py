"""Cola de trabajos con dos carriles de un solo worker cada uno:
  - "claude": primera versión / pedidos de cambio (pueden tardar minutos);
  - "render": vista previa, borrador y render final (un render a la vez).
Así un pedido a Claude no bloquea el render de otro proyecto, pero nunca hay dos renders juntos.

Los renders corren el CLI en un subproceso (`reels --json render …`): se puede cancelar matando el
proceso y el servidor no carga con los procesos del compositor.
Cada cambio de estado se publica en el bus → la UI lo recibe por SSE.
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Callable

from . import settings
from .claude_runner import clean_env, kill_tree


class Bus:
    def __init__(self):
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1000)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def publish(self, event: dict):
        with self._lock:
            for q in list(self._subs):
                try:
                    q.put_nowait(event)
                except queue.Full:
                    pass


bus = Bus()


@dataclass
class Job:
    kind: str                 # primera | cambio | stills | borrador | final | analisis
    project: str              # id (nombre de carpeta)
    title: str
    lane: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    status: str = "en_cola"   # en_cola | corriendo | listo | error | cancelado
    stage: str = ""
    done: int = 0
    total: int = 0
    log: list[str] = field(default_factory=list)
    result: dict | None = None
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    def public(self) -> dict:
        # sin asdict: haría deepcopy del Event de cancelación (no se puede copiar)
        d = {f.name: getattr(self, f.name) for f in fields(self) if f.name != "cancel"}
        d["log"] = self.log[-30:]
        frac = (self.result or {}).get("fraccion") if self.status == "corriendo" else None
        if self.started and frac and frac > 0.05:
            el = time.time() - self.started
            d["eta_s"] = round(el / frac * (1 - frac))
        return d


class Queue:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self._q = {"claude": queue.Queue(), "render": queue.Queue()}
        self._fns: dict[str, Callable[[Job], dict]] = {}
        for lane in self._q:
            threading.Thread(target=self._worker, args=(lane,), daemon=True, name=f"jobs-{lane}").start()

    def submit(self, job: Job, fn: Callable[[Job], dict]) -> Job:
        self.jobs[job.id] = job
        self._fns[job.id] = fn
        self._q[job.lane].put(job.id)
        self.emit(job)
        return job

    def emit(self, job: Job, **extra):
        bus.publish({"type": "job", "job": job.public(), **extra})

    def update(self, job: Job, **kw):
        for k, v in kw.items():
            setattr(job, k, v)
        self.emit(job)

    def say(self, job: Job, text: str):
        if not job.log or job.log[-1] != text:
            job.log.append(text)
            job.stage = text
            self.emit(job)

    def cancel(self, job_id: str) -> bool:
        j = self.jobs.get(job_id)
        if not j or j.status in ("listo", "error", "cancelado"):
            return False
        j.cancel.set()
        if j.status == "en_cola":
            self.update(j, status="cancelado", finished=time.time())
        return True

    def active(self, project: str | None = None) -> list[Job]:
        return [j for j in self.jobs.values() if j.status in ("en_cola", "corriendo")
                and (project is None or j.project == project)]

    def _worker(self, lane: str):
        while True:
            jid = self._q[lane].get()
            job = self.jobs[jid]
            if job.status == "cancelado":
                continue
            self.update(job, status="corriendo", started=time.time())
            try:
                res = self._fns.pop(jid)(job)
                if job.cancel.is_set():
                    self.update(job, status="cancelado", finished=time.time(), result=res)
                else:
                    ok = res.get("ok", True) if isinstance(res, dict) else True
                    self.update(job, status="listo" if ok else "error", finished=time.time(), result=res)
            except Exception as e:  # noqa: BLE001
                self.update(job, status="error", finished=time.time(),
                            result={"ok": False, "message": f"{type(e).__name__}: {e}"})
            bus.publish({"type": "projects_changed", "project": job.project})
            # limpiar trabajos viejos
            old = [k for k, j in self.jobs.items() if j.finished and time.time() - j.finished > 6 * 3600]
            for k in old:
                self.jobs.pop(k, None)


jobs = Queue()


STAGE_NAMES = {"música": "Armando la música…", "textos": "Animando los textos…", "video": "Componiendo el video…",
               "generando cuadros de vista previa": "Generando la vista previa…"}


def run_cli(job: Job, args: list[str]) -> dict:
    """Corre `reels --json …` y traduce sus eventos al job."""
    cmd = [sys.executable, "-m", "engine.cli", "--json", *args]
    p = subprocess.Popen(cmd, cwd=str(settings.REPO), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace", env=clean_env(),
                         creationflags=settings.NO_WINDOW)
    stop = threading.Event()

    def watch():
        while not stop.is_set():
            if job.cancel.is_set():
                kill_tree(p)
                return
            time.sleep(0.3)

    threading.Thread(target=watch, daemon=True).start()
    # tramo de la barra total que ocupa cada etapa (los textos tardan ~1/3 del render, el video ~2/3)
    span = {"textos": (0.03, 0.38), "video": (0.38, 1.0)}
    result, errors = {"ok": True}, []
    for line in p.stdout:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        k = ev.get("event")
        if k == "stage":
            jobs.say(job, STAGE_NAMES.get(ev["msg"], ev["msg"].capitalize()))
        elif k == "progress":
            a, b = span.get(ev["stage"], (0, 1))
            frac = a + (b - a) * ev["done"] / max(1, ev["total"])
            kw = {"result": {"fraccion": round(frac, 3), "etapa": ev["stage"]}}
            if ev["stage"] == "video":  # "283 / 330 cuadros"
                kw.update(done=ev["done"], total=ev["total"])
            jobs.update(job, **kw)
        elif k == "warning":
            job.log.append("Aviso: " + ev["msg"])
        elif k == "error":
            errors.append(ev["msg"])
        elif k == "done":
            result = {"ok": True, **{kk: vv for kk, vv in ev.items() if kk != "event"}}
    p.wait()
    stop.set()
    if job.cancel.is_set():
        return {"ok": False, "message": "Cancelado"}
    if p.returncode != 0 or errors:
        return {"ok": False, "message": errors[0] if errors else (p.stderr.read()[-400:] or "falló el render")}
    return result
