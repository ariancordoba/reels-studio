"""Claude Code en modo headless con el proyecto como cwd.

    claude -p <pedido> --output-format stream-json --verbose [--resume <session>]
           --permission-mode acceptEdits --allowedTools ... --append-system-prompt ...

Usa la sesión/suscripción de Claude Code ya iniciada en la compu (no hace falta API key).
Todo pasa por la interfaz `Runner`: si hiciera falta, se cambia por una implementación con
Claude Agent SDK + API key sin tocar el resto de la app.
"""
from __future__ import annotations

import json
import re
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from . import settings

ALLOWED = ["Read", "Glob", "Grep", "Write", "Edit", "MultiEdit",
           "Bash(reels:*)", "Bash(reels *)", "PowerShell(reels:*)", "PowerShell(reels *)"]
DISALLOWED = ["WebFetch", "WebSearch", "Task", "Agent", "NotebookEdit"]
SYSTEM = (
    "Trabajás dentro de Reels Studio para una community manager no técnica. Seguí CLAUDE.md al pie de la letra. "
    "Sólo escribís dentro de la carpeta del proyecto y sólo corrés comandos `reels`. "
    "Tu último mensaje se le muestra a ella tal cual: 2 a 4 líneas en español rioplatense, sin tecnicismos."
)
# "el modelo X no está disponible para tu plan / no existe": se reintenta con el modelo por defecto
MODEL_ERROR = re.compile(
    r"(model|modelo).{0,80}(not (available|found|supported|allowed|enabled)|no (est[aá] )?disponible|access|"
    r"permission|upgrade|invalid|unknown)|(invalid|unknown|unsupported|no access to).{0,40}(model|modelo)", re.I)
AUTH_ERRORS = ("failed to authenticate", "oauth", "not logged in", "invalid api key", "please run /login",
               "authentication", "401")


@dataclass
class Result:
    ok: bool
    text: str
    session_id: str | None = None
    cost_usd: float | None = None
    turns: int | None = None
    error: str | None = None  # auth | timeout | cancelled | not_installed | session_lost | failed


class Runner(Protocol):
    def status(self) -> dict: ...
    def run(self, cwd: Path, prompt: str, session_id: str | None = None,
            on_event: Callable[[dict], None] | None = None, cancel: threading.Event | None = None) -> Result: ...


def friendly(tool: str, inp: dict) -> str | None:
    """Evento de herramienta → frase para la UI."""
    path = str(inp.get("file_path") or inp.get("path") or inp.get("pattern") or "").replace("\\", "/")
    cmd = str(inp.get("command") or "")
    if tool == "Read":
        if "/analisis/" in path or path.startswith("analisis"):
            return "Mirando la referencia y los crudos…" if path.endswith(".jpg") else "Leyendo el análisis…"
        if "/stills/" in path:
            return "Revisando la vista previa…"
        if "instrucciones" in path:
            return "Leyendo tus instrucciones…"
        if "cliente.json" in path:
            return "Revisando la marca del cliente…"
        return "Leyendo…"
    if tool in ("Write", "Edit", "MultiEdit"):
        if path.endswith("spec.json"):
            return "Escribiendo el guion…" if tool == "Write" else "Ajustando el guion…"
        if path.endswith("notas.md"):
            return "Anotando los cambios…"
        return "Escribiendo…"
    if tool in ("Bash", "PowerShell"):
        if "stills" in cmd:
            return "Generando la vista previa…"
        if "check" in cmd:
            return "Verificando el guion…"
        return "Trabajando…"
    if tool in ("Glob", "Grep"):
        return "Buscando archivos…"
    return None


def clean_env() -> dict:
    """Sin variables de una sesión de Claude padre (si no, el hijo espera a la app que lo lanzó)."""
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith("CLAUDE") or k in ("ANTHROPIC_BASE_URL",))}
    env["PATH"] = str(settings.venv_scripts()) + os.pathsep + env.get("PATH", "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


class ClaudeRunner:
    def __init__(self, exe: str | None = None, model: str | None = None, timeout_s: float = 30 * 60,
                 max_turns: int = 80):
        cfg = settings.load()
        self.exe = exe or settings.claude_exe()
        self.model = model or cfg.get("claude_model")
        self.timeout_s, self.max_turns = timeout_s, max_turns

    # ── estado (Ajustes / tarjeta "Claude")
    def status(self) -> dict:
        if not self.exe:
            return {"ok": False, "installed": False, "logged_in": False,
                    "detail": "Claude Code no está instalado"}
        try:
            v = subprocess.run([self.exe, "--version"], capture_output=True, text=True, timeout=30,
                               env=clean_env(), stdin=subprocess.DEVNULL, creationflags=settings.NO_WINDOW)
            version = v.stdout.strip().split(" ")[0]
            a = subprocess.run([self.exe, "auth", "status"], capture_output=True, text=True, timeout=30,
                               env=clean_env(), stdin=subprocess.DEVNULL, creationflags=settings.NO_WINDOW,
                               encoding="utf-8", errors="replace")
            info = json.loads(a.stdout) if a.stdout.strip().startswith("{") else {}
            logged = bool(info.get("loggedIn"))
            return {"ok": logged, "installed": True, "logged_in": logged, "version": version,
                    "plan": info.get("subscriptionType"),
                    "detail": f"Conectado · {version}" if logged else "No inició sesión"}
        except (subprocess.TimeoutExpired, OSError) as e:
            return {"ok": False, "installed": True, "logged_in": False, "detail": f"No responde: {e}"}

    def command(self, prompt: str, session_id: str | None) -> list[str]:
        cmd = [self.exe, "-p", prompt, "--output-format", "stream-json", "--verbose",
               "--permission-mode", "acceptEdits",
               "--allowedTools", *ALLOWED, "--disallowedTools", *DISALLOWED,
               "--append-system-prompt", SYSTEM, "--max-turns", str(self.max_turns)]
        if self.model:
            cmd += ["--model", self.model]
        if session_id:
            cmd += ["--resume", session_id]
        return cmd

    def run(self, cwd: Path, prompt: str, session_id: str | None = None,
            on_event: Callable[[dict], None] | None = None, cancel: threading.Event | None = None) -> Result:
        res = self._run(cwd, prompt, session_id, on_event, cancel)
        if not res.ok and self.model and res.error == "failed" and MODEL_ERROR.search(res.text or ""):
            # el plan de esta cuenta no incluye ese modelo (p. ej. Opus): seguir con el modelo por defecto
            (on_event or (lambda e: None))({"type": "status", "text": f"Tu plan no incluye {self.model}: sigo con el modelo por defecto…"})
            wanted, self.model = self.model, None
            try:
                res = self._run(cwd, prompt, session_id, on_event, cancel)
            finally:
                self.model = wanted
        return res

    def _run(self, cwd: Path, prompt: str, session_id: str | None = None,
             on_event: Callable[[dict], None] | None = None, cancel: threading.Event | None = None) -> Result:
        emit = on_event or (lambda e: None)
        if not self.exe:
            return Result(False, "No encuentro Claude Code en esta compu. Instalalo desde Ajustes → Reparar.",
                          error="not_installed")
        emit({"type": "status", "text": "Despertando a Claude…"})
        proc = subprocess.Popen(self.command(prompt, session_id), cwd=str(cwd), env=clean_env(),
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                encoding="utf-8", errors="replace", creationflags=settings.NO_WINDOW)
        state = {"sid": session_id, "result": None, "last_text": "", "stderr": [], "last_event": time.monotonic()}

        def read_err():
            for line in proc.stderr:
                state["stderr"].append(line)

        threading.Thread(target=read_err, daemon=True).start()
        killer_reason = {}

        def watchdog():
            t0 = time.monotonic()
            while proc.poll() is None:
                if cancel and cancel.is_set():
                    killer_reason["r"] = "cancelled"
                elif time.monotonic() - t0 > self.timeout_s:
                    killer_reason["r"] = "timeout"
                elif time.monotonic() - state["last_event"] > 180 and state["sid"] is None:
                    killer_reason["r"] = "timeout"  # ni siquiera arrancó (típico: sesión vencida en versiones viejas)
                if killer_reason:
                    kill_tree(proc)
                    return
                time.sleep(0.5)

        threading.Thread(target=watchdog, daemon=True).start()
        for line in proc.stdout:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            state["last_event"] = time.monotonic()
            self._handle(ev, state, emit)
        proc.wait()
        return self._finish(proc, state, killer_reason.get("r"))

    @staticmethod
    def _handle(ev: dict, state: dict, emit):
        t = ev.get("type")
        if ev.get("session_id"):
            if state["sid"] != ev["session_id"]:
                state["sid"] = ev["session_id"]
                emit({"type": "session", "session_id": ev["session_id"]})
        if t == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    msg = friendly(block.get("name", ""), block.get("input") or {})
                    if msg:
                        emit({"type": "status", "text": msg, "tool": block.get("name")})
                elif block.get("type") == "text" and block.get("text", "").strip():
                    state["last_text"] = block["text"].strip()
                    emit({"type": "thinking", "text": state["last_text"]})
        elif t == "result":
            state["result"] = ev

    def _finish(self, proc, state, killed) -> Result:
        sid, r = state["sid"], state["result"]
        err_txt = "".join(state["stderr"])[-2000:]
        if killed == "cancelled":
            return Result(False, "Cancelaste el pedido.", sid, error="cancelled")
        if killed == "timeout":
            return Result(False, "Claude tardó demasiado en responder. Probá de nuevo; si sigue igual, revisá en "
                                 "Ajustes que Claude Code tenga la sesión iniciada.", sid, error="timeout")
        if r is None:
            low = err_txt.lower()
            if "no conversation found" in low:
                return Result(False, "Se perdió la conversación anterior.", None, error="session_lost")
            if any(a in low for a in AUTH_ERRORS):
                return Result(False, "Claude Code no tiene la sesión iniciada en esta compu. "
                                     "Abrí Ajustes → Claude → Reparar.", sid, error="auth")
            return Result(False, f"Claude se cortó sin responder. {err_txt[-300:]}".strip(), sid, error="failed")
        text = (r.get("result") or state["last_text"] or "").strip()
        if r.get("is_error"):
            low = text.lower()
            if any(a in low for a in AUTH_ERRORS):
                return Result(False, "Claude Code no tiene la sesión iniciada en esta compu. "
                                     "Abrí Ajustes → Claude → Reparar.", sid, error="auth")
            if "no conversation found" in low:
                return Result(False, "Se perdió la conversación anterior.", None, error="session_lost")
            if r.get("subtype") == "error_max_turns":
                return Result(False, "Claude no llegó a terminar (demasiados pasos). Pedí algo más acotado.",
                              sid, r.get("total_cost_usd"), r.get("num_turns"), error="failed")
            return Result(False, text or "Claude devolvió un error.", sid, error="failed")
        return Result(True, text, sid, r.get("total_cost_usd"), r.get("num_turns"))


def kill_tree(proc: subprocess.Popen):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                       creationflags=settings.NO_WINDOW)
    else:
        proc.kill()
