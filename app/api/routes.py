"""API local de la app. Todo bajo /api; los estáticos de la UI los sirve main.py."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from engine.project import versions

from .. import projects, settings, workflow
from ..claude_runner import ClaudeRunner
from ..jobs import Job, bus, jobs, run_cli

router = APIRouter(prefix="/api")

# ── helpers


def project_path(pid: str) -> Path:
    p = (projects.projects_dir() / pid).resolve()
    if p.parent != projects.projects_dir().resolve() or not (p / "proyecto.json").exists():
        raise HTTPException(404, "No encuentro ese proyecto")
    return p


def version_path(pid: str, vid: str) -> Path:
    v = project_path(pid) / "versiones" / vid
    if not (v / "spec.json").exists():
        raise HTTPException(404, "No encuentro esa versión")
    return v


def chat_path(p: Path) -> Path:
    return p / "chat.json"


def chat_add(p: Path, rol: str, texto: str, **kw):
    msgs = projects.read_json(chat_path(p), [])
    msgs.append({"rol": rol, "texto": texto, "fecha": datetime.now().isoformat(timespec="seconds"), **kw})
    projects.write_json(chat_path(p), msgs)
    bus.publish({"type": "chat", "project": p.name})


def with_jobs(info: dict) -> dict:
    info["trabajos"] = [j.public() for j in jobs.active(info["id"])]
    return info


_claude_status = {"t": 0.0, "v": None}


def claude_status(force=False) -> dict:
    if force or not _claude_status["v"] or time.time() - _claude_status["t"] > 300:
        _claude_status.update(t=time.time(), v=ClaudeRunner().status())
    return _claude_status["v"]


# ── estado / ajustes


@router.get("/estado")
def estado():
    cfg = settings.load()
    return {"config": cfg, "data_dir": str(settings.data_dir()), "machine": settings.machine(),
            "claude": claude_status(), "configurado": bool(cfg.get("data_dir")),
            "sugerido": str(settings.suggested_data_dir())}


@router.get("/sistema")
def sistema():
    st = settings.system_status()
    _claude_status.update(t=time.time(), v=st["claude"])
    return st


class Ajustes(BaseModel):
    data_dir: str | None = None
    user_name: str | None = None
    quality: str | None = None
    claude_model: str | None = None
    claude_modo: str | None = None  # calidad | equilibrado | ahorro
    auto_update: bool | None = None
    update_source: str | None = None


@router.put("/ajustes")
def put_ajustes(a: Ajustes):
    cfg = {k: v for k, v in a.model_dump().items() if v is not None}
    if "data_dir" in cfg:
        Path(cfg["data_dir"]).mkdir(parents=True, exist_ok=True)
    return settings.save(cfg)


@router.post("/sistema/reparar/{que}")
def reparar(que: str):
    """Abre una consola visible con la reparación: es lo único que ella ve de una terminal, a propósito."""
    if que == "chromium":
        cmd = f'"{settings.venv_scripts() / "playwright"}" install chromium & pause'
    elif que == "claude":
        cmd = "npm install -g @anthropic-ai/claude-code@latest & echo. & echo Inicia sesion y despues escribi /exit & claude"
    elif que == "todo":
        cmd = f'"{settings.REPO / "INSTALAR.bat"}"'
    else:
        raise HTTPException(400, "No sé reparar eso")
    subprocess.Popen(["cmd", "/c", "start", "Reels Studio - reparar", "cmd", "/k", cmd], cwd=str(settings.REPO))
    _claude_status["t"] = 0
    return {"ok": True}


# ── clientes


@router.get("/clientes")
def get_clientes():
    return projects.list_clients()


class Cliente(BaseModel):
    nombre: str
    accent: str = "#caffbf"
    text: str = "#ffffff"
    display_font: str = "Archivo"
    serif_font: str = "Playfair"
    footer: list[str] = []
    darken: float = 0.32
    notas: str = ""


@router.post("/clientes")
def post_cliente(c: Cliente):
    return projects.save_client(c.model_dump())


@router.put("/clientes/{slug}")
def put_cliente(slug: str, c: Cliente):
    if not projects.get_client(slug):
        raise HTTPException(404, "No encuentro ese cliente")
    return projects.save_client(c.model_dump(), slug)


@router.post("/clientes/{slug}/fuentes")
async def post_fuente(slug: str, archivo: UploadFile = File(...)):
    if Path(archivo.filename).suffix.lower() not in (".ttf", ".otf", ".woff", ".woff2"):
        raise HTTPException(400, "La fuente tiene que ser .ttf, .otf, .woff o .woff2")
    d = projects.clients_dir() / slug / "fonts"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / Path(archivo.filename).name, "wb") as f:
        shutil.copyfileobj(archivo.file, f)
    return projects.get_client(slug)


@router.post("/clientes/{slug}/logo")
async def post_logo(slug: str, archivo: UploadFile = File(...)):
    d = projects.clients_dir() / slug
    ext = Path(archivo.filename).suffix.lower() or ".png"
    with open(d / f"logo{ext}", "wb") as f:
        shutil.copyfileobj(archivo.file, f)
    projects.save_client({"logo": f"logo{ext}"}, slug)
    return projects.get_client(slug)


@router.get("/clientes/{slug}/logo")
def get_logo(slug: str):
    c = projects.get_client(slug)
    if not c or not c.get("logo"):
        raise HTTPException(404)
    return FileResponse(projects.clients_dir() / slug / c["logo"])


# ── proyectos


@router.get("/proyectos")
def get_proyectos():
    return [with_jobs(p) for p in projects.list_projects()]


@router.get("/proyectos/{pid}")
def get_proyecto(pid: str):
    p = project_path(pid)
    info = with_jobs(projects.project_info(p))
    info["chat"] = projects.read_json(chat_path(p), [])
    info["instrucciones"] = (p / "entrada" / "instrucciones.md").read_text(encoding="utf-8") \
        if (p / "entrada" / "instrucciones.md").exists() else ""
    return info


class Meta(BaseModel):
    titulo: str | None = None
    prioridad: str | None = None
    entrega: str | None = None
    etapa: str | None = None
    version_actual: str | None = None


@router.put("/proyectos/{pid}")
def put_proyecto(pid: str, m: Meta):
    p = project_path(pid)
    projects.save_meta(p, **{k: v for k, v in m.model_dump().items() if v is not None})
    bus.publish({"type": "projects_changed", "project": pid})
    return projects.project_info(p)


def _claude_job(p: Path, kind: str, title: str, fn) -> Job:
    job = Job(kind, p.name, title, "claude")

    def run(j: Job):
        def emit(e):
            if e["type"] == "status":
                jobs.say(j, e["text"])
            elif e["type"] == "progress":
                jobs.update(j, done=e["done"], total=e["total"])
        res = fn(emit, j.cancel)
        chat_add(p, "claude", res.get("message") or "", version=res.get("version"), ok=res["ok"],
                 error=res.get("error"))
        return res

    return jobs.submit(job, run)


@router.post("/proyectos")
async def post_proyecto(titulo: str = Form(...), cliente: str = Form(...), instrucciones: str = Form(""),
                        duracion: float | None = Form(None), plantilla: str = Form(""),
                        modo: str = Form("claude"), textos: str = Form(""),
                        crudos: list[UploadFile] = File(...),
                        referencias: list[UploadFile] = File(default=[])):
    tmp = settings.local_dir() / "subidas" / str(time.time_ns())
    tmp.mkdir(parents=True)
    saved: dict[str, list[Path]] = {"crudos": [], "referencias": []}
    for kind, files in (("crudos", crudos), ("referencias", referencias)):
        for up in files:
            dst = tmp / kind / Path(up.filename).name
            dst.parent.mkdir(exist_ok=True)
            with open(dst, "wb") as f:
                shutil.copyfileobj(up.file, f, 8 << 20)
            saved[kind].append(dst)
    p = projects.create_project(titulo, cliente, saved["crudos"], saved["referencias"], instrucciones, duracion,
                                move=True)
    shutil.rmtree(tmp, ignore_errors=True)
    if plantilla:
        t = projects.read_json(projects.templates_dir() / f"{Path(plantilla).name}.json")
        if t:
            projects.write_json(p / "entrada" / "plantilla.json", t)
    chat_add(p, "yo", instrucciones.strip() or "(sin instrucciones)", tipo="inicio")
    if plantilla and modo == "rapido":  # sin Claude: cero tokens
        try:
            texts = json.loads(textos) if textos else None
        except json.JSONDecodeError:
            texts = None
        job = _render_lane_job(p, "rapido", "Armado automático",
                               lambda emit: workflow.quick_version(p, plantilla, texts, emit))
    else:
        job = _claude_job(p, "primera", "Primera versión", lambda emit, cancel: workflow.first_version(p, emit, cancel))
    bus.publish({"type": "projects_changed", "project": p.name})
    return {"id": p.name, "job": job.public()}


class Pedido(BaseModel):
    texto: str
    adjuntos: list[str] = []  # rutas relativas al proyecto (subidas antes con /adjuntos)


@router.post("/proyectos/{pid}/adjuntos")
async def adjuntar(pid: str, archivos: list[UploadFile] = File(...)):
    """Imágenes para un pedido ("así quiero el título"): quedan en entrada/adjuntos, achicadas."""
    from engine.analyze import IMAGE_EXT, shrink_image

    p = project_path(pid)
    d = p / "entrada" / "adjuntos"
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for up in archivos:
        name = Path(up.filename).name
        if Path(name).suffix.lower() not in IMAGE_EXT:
            raise HTTPException(400, f"{name}: sólo imágenes (jpg, png, webp)")
        dst = d / f"{time.strftime('%Y%m%d-%H%M%S')}_{name}"
        with open(dst, "wb") as f:
            shutil.copyfileobj(up.file, f)
        out.append(shrink_image(dst).relative_to(p).as_posix())
    return {"adjuntos": out}


@router.post("/proyectos/{pid}/pedir")
def pedir(pid: str, body: Pedido):
    p = project_path(pid)
    if not body.texto.strip():
        raise HTTPException(400, "Escribí qué querés cambiar")
    adj = [a for a in body.adjuntos if (p / a).resolve().is_relative_to(p.resolve()) and (p / a).exists()]
    chat_add(p, "yo", body.texto.strip(), adjuntos=adj)
    if projects.current_version(p) is None:
        fn = lambda emit, cancel: workflow.first_version(p, emit, cancel)  # noqa: E731
        return _claude_job(p, "primera", "Primera versión", fn).public()
    fn = lambda emit, cancel: workflow.request_change(p, body.texto, emit, cancel, adjuntos=adj)  # noqa: E731
    return _claude_job(p, "cambio", body.texto[:60], fn).public()


@router.get("/proyectos/{pid}/versiones/{vid}/spec")
def get_spec(pid: str, vid: str):
    return json.loads((version_path(pid, vid) / "spec.json").read_text(encoding="utf-8"))


@router.put("/proyectos/{pid}/versiones/{vid}/spec")
def put_spec(pid: str, vid: str, spec: dict):
    version_path(pid, vid)
    p = project_path(pid)
    job = Job("stills", pid, "Vista previa del guion editado", "render")
    job = jobs.submit(job, lambda j: (jobs.say(j, "Generando la vista previa…"),
                                      workflow.edit_version(p, spec, f"Edición manual del guion (sobre {vid})"))[1])
    return job.public()


class RenderReq(BaseModel):
    version: str | None = None
    calidad: str = "final"  # stills | borrador | final


@router.post("/proyectos/{pid}/render")
def render(pid: str, body: RenderReq):
    p = project_path(pid)
    v = version_path(pid, body.version) if body.version else projects.current_version(p)
    if v is None:
        raise HTTPException(400, "Todavía no hay una versión para renderizar")
    if any(j.kind in ("borrador", "final", "stills") for j in jobs.active(pid)):
        raise HTTPException(409, "Ya hay un render de este proyecto en marcha")
    titles = {"stills": "Vista previa rápida", "borrador": "Borrador 540p", "final": "Render final 1080p"}
    job = Job(body.calidad, pid, f"{titles[body.calidad]} · {v.name}", "render")

    def run(j: Job):
        try:
            with projects.project_lock(p, titles[body.calidad]):
                if body.calidad != "stills":
                    projects.save_meta(p, etapa="render")
                args = ["stills", str(v), "--completo"] if body.calidad == "stills" else \
                    ["render", str(v), *(["--draft"] if body.calidad == "borrador" else [])]
                res = run_cli(j, args)
                res["version"] = v.name
                return res
        except projects.Locked as e:
            return {"ok": False, "message": str(e)}

    return jobs.submit(job, run).public()


@router.post("/proyectos/{pid}/abrir")
def abrir(pid: str, version: str | None = None):
    p = project_path(pid)
    target = p / "versiones" / version if version else p
    if os.name == "nt":
        os.startfile(target)  # noqa: S606
    return {"ok": True}


@router.post("/proyectos/{pid}/exportar")
def exportar(pid: str, version: str | None = None):
    p = project_path(pid)
    v = p / "versiones" / version if version else projects.current_version(p)
    src = v / "video.mp4" if v else None
    if not src or not src.exists():
        raise HTTPException(400, "Primero hacé el render final")
    m = projects.meta(p)
    dl = Path.home() / "Downloads"
    dl.mkdir(exist_ok=True)
    name = f"{projects.slugify(m.get('cliente') or '')}_{projects.slugify(m.get('titulo') or pid)}_{v.name}.mp4".strip("_")
    dst = dl / name
    shutil.copy2(src, dst)
    projects.save_meta(p, etapa="entregado", entregado=datetime.now().isoformat(timespec="seconds"))
    bus.publish({"type": "projects_changed", "project": pid})
    if os.name == "nt":
        subprocess.Popen(["explorer", "/select,", str(dst)])
    return {"ok": True, "path": str(dst)}


# ── trabajos y eventos


@router.get("/trabajos")
def get_trabajos():
    return [j.public() for j in sorted(jobs.jobs.values(), key=lambda j: -j.created)][:50]


@router.post("/trabajos/{jid}/cancelar")
def cancelar(jid: str):
    return {"ok": jobs.cancel(jid)}


@router.get("/eventos")
async def eventos(request: Request):
    q = bus.subscribe()

    async def stream():
        try:
            yield "retry: 2000\n\n"
            while not await request.is_disconnected():
                try:
                    ev = await asyncio.to_thread(q.get, True, 15)
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                except Exception:  # noqa: BLE001 — timeout: latido para mantener viva la conexión
                    yield ": ping\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── archivos (videos, stills, hojas) — sólo dentro de la carpeta de datos


@router.get("/archivo/{pid}/{rel:path}")
def archivo(pid: str, rel: str):
    p = project_path(pid)
    f = (p / rel).resolve()
    if p not in f.parents or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f, headers={"Cache-Control": "no-cache"})


@router.get("/miniatura/{pid}")
def miniatura(pid: str):
    p = project_path(pid)
    v = projects.current_version(p)
    cands = []
    if v:
        cands += sorted((v / "stills").glob("t*.jpg"))
    for vv in reversed(versions(p)):
        cands += sorted((vv / "stills").glob("t*.jpg"))
    cands += sorted((p / "analisis").glob("*/hoja_01.jpg"))
    if not cands:
        raise HTTPException(404)
    return FileResponse(cands[0], headers={"Cache-Control": "no-cache"})


# ── música (pistas subidas con licencia) — <datos>/musica/


def music_dir() -> Path:
    d = settings.data_dir() / "musica"
    d.mkdir(exist_ok=True)
    return d


@router.get("/musica")
def get_musica():
    return projects.list_music()


@router.post("/musica")
async def post_musica(archivo: UploadFile = File(...), titulo: str = Form(...), licencia: str = Form(...)):
    if len(licencia.strip()) < 3:
        raise HTTPException(400, "Anotá la licencia o el origen de la pista")
    name = Path(archivo.filename).name
    with open(music_dir() / name, "wb") as f:
        shutil.copyfileobj(archivo.file, f)
    idx = projects.read_json(music_dir() / "musica.json", {})
    idx[name] = {"titulo": titulo.strip() or name, "licencia": licencia.strip(),
                 "subida": datetime.now().isoformat(timespec="seconds")}
    projects.write_json(music_dir() / "musica.json", idx)
    return projects.list_music()


@router.get("/musica/{archivo}")
def get_pista(archivo: str):
    f = (music_dir() / archivo).resolve()
    if f.parent != music_dir().resolve() or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


# ── plantillas: specs aprobados que sirven de estructura — <datos>/plantillas/


class NuevaPlantilla(BaseModel):
    proyecto: str
    nombre: str
    descripcion: str = ""


@router.get("/plantillas")
def get_plantillas():
    return projects.list_templates()


@router.post("/plantillas")
def post_plantilla(body: NuevaPlantilla):
    p = project_path(body.proyecto)
    v = projects.current_version(p)
    if not v:
        raise HTTPException(400, "Ese proyecto no tiene versiones")
    m = projects.meta(p)
    still = next(iter(sorted((v / "stills").glob("t*.jpg"))), None)
    return projects.save_template(v / "spec.json", body.nombre, body.descripcion, m.get("titulo", p.name),
                                  preview=still, cliente=m.get("cliente", ""))


@router.delete("/plantillas/{tid}")
def del_plantilla(tid: str):
    f = (projects.templates_dir() / f"{tid}.json").resolve()
    if f.parent != projects.templates_dir().resolve():
        raise HTTPException(404)
    f.unlink(missing_ok=True)
    return {"ok": True}


# ── conectar Claude sin terminal (instalar + iniciar sesión)
from .. import claude_auth  # noqa: E402


class LoginReq(BaseModel):
    email: str | None = None


class Codigo(BaseModel):
    codigo: str


@router.get("/claude")
def claude_estado():
    return {"status": claude_status(force=True), "login": claude_auth.login.public(),
            "install": claude_auth.install.public()}


@router.post("/claude/instalar")
def claude_instalar():
    return claude_auth.install.start()


@router.post("/claude/login")
def claude_login(body: LoginReq | None = None):
    return claude_auth.login.start(body.email if body else None)


@router.post("/claude/login/codigo")
def claude_codigo(body: Codigo):
    return claude_auth.login.send_code(body.codigo)


@router.post("/claude/login/abrir")
def claude_abrir():
    return {"ok": claude_auth.login.open_browser()}


@router.post("/claude/login/cancelar")
def claude_cancelar():
    claude_auth.login.cancel()
    return claude_auth.login.public()


@router.post("/claude/logout")
def claude_logout():
    st = claude_auth.logout()
    _claude_status.update(t=time.time(), v=st)
    return st


# ── actualizaciones
from .. import updater  # noqa: E402

_upd_cache = {"t": 0.0, "v": None}


@router.get("/actualizacion")
def actualizacion(forzar: bool = False):
    if forzar or not _upd_cache["v"] or time.time() - _upd_cache["t"] > 3600:
        _upd_cache.update(t=time.time(), v=updater.check())
    pending = updater.state["pending"]
    return {**_upd_cache["v"], "desarrollo": updater.is_dev_checkout(), "auto": updater.auto_enabled(),
            "lista": pending["version"] if pending else None}


@router.post("/actualizacion/instalar")
def actualizar():
    if updater.is_dev_checkout():
        raise HTTPException(400, "Esta es la carpeta de desarrollo: actualizá con git, no desde la app")
    if any(j.status == "corriendo" for j in jobs.jobs.values()):
        raise HTTPException(409, "Esperá a que terminen los renders y pedidos en curso")
    pending = updater.state["pending"]
    info = None if pending else updater.check()
    if not pending and not info.get("disponible"):
        raise HTTPException(400, info.get("error") or "Ya tenés la última versión")
    version = pending["version"] if pending else info["version"]
    job = Job("actualizacion", "", f"Actualizando a {version}", "render")

    def run(j: Job):
        if pending:  # ya estaba descargada en segundo plano: directo a instalar
            stage = Path(pending["stage"])
        else:
            jobs.say(j, "Descargando la actualización…")
            stage = updater.download(info, lambda d, t: jobs.update(j, done=d // (1 << 20), total=t // (1 << 20),
                                                                     result={"fraccion": d / t if t else 0}), j.cancel)
        jobs.say(j, "Instalando… la app se va a cerrar y abrir sola")
        updater.apply(stage)
        bus.publish({"type": "reiniciando"})
        updater.request_exit()
        return {"ok": True, "message": f"Actualizando a {version}"}

    return jobs.submit(job, run).public()


@router.get("/version")
def version():
    return {"version": updater.current_version(), "machine": settings.machine()}


# ── diagnóstico para soporte: un zip en el escritorio (sin videos ni datos de clientes)
@router.post("/diagnostico")
def diagnostico():
    import platform
    import zipfile

    desk = Path.home() / "Desktop"
    desk.mkdir(exist_ok=True)
    out = desk / f"ReelsStudio-diagnostico-{datetime.now():%Y%m%d-%H%M}.zip"
    info = {"version": updater.current_version(), "machine": settings.machine(), "python": sys.version,
            "windows": platform.platform(), "config": settings.load(), "sistema": settings.system_status(),
            "trabajos": [j.public() for j in jobs.jobs.values()],
            "proyectos": [{k: p.get(k) for k in ("id", "etapa", "version_actual", "pendiente", "lock")}
                          for p in projects.list_projects()]}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("info.json", json.dumps(info, ensure_ascii=False, indent=2, default=str))
        for d in (settings.local_dir() / "logs", updater.updates_dir()):
            for f in d.glob("*.log"):
                z.write(f, f"logs/{f.name}")
    if os.name == "nt":
        subprocess.Popen(["explorer", "/select,", str(out)])
    return {"ok": True, "path": str(out)}


# ── ahorro de tokens: armado rápido, ajustes rápidos, estilos aprendidos, aprendizajes del cliente


def _render_lane_job(p: Path, kind: str, title: str, fn) -> Job:
    """Trabajo sin Claude (carril de render): deja el resultado en el chat como mensaje de la app."""
    job = Job(kind, p.name, title, "render")

    def run(j: Job):
        res = fn(lambda e: e["type"] == "status" and jobs.say(j, e["text"]))
        chat_add(p, "claude", res.get("message") or "", version=res.get("version"), ok=res["ok"], sin_claude=True)
        return res

    return jobs.submit(job, run)


@router.get("/ajustes-rapidos")
def ajustes_rapidos():
    return [{"id": k, "label": v[0]} for k, v in workflow.QUICK.items()]


class Ajuste(BaseModel):
    tipo: str


@router.post("/proyectos/{pid}/ajuste")
def ajuste(pid: str, body: Ajuste):
    p = project_path(pid)
    if body.tipo not in workflow.QUICK:
        raise HTTPException(400, "Ajuste desconocido")
    label = workflow.QUICK[body.tipo][0]
    chat_add(p, "yo", f"⚡ {label}", tipo="ajuste")
    return _render_lane_job(p, "ajuste", label, lambda emit: workflow.quick_adjust(p, body.tipo)).public()


@router.get("/plantillas/{tid}/preview")
def plantilla_preview(tid: str):
    f = (projects.templates_dir() / f"{Path(tid).name}.jpg")
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f)


class EditPlantilla(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    reglas: str | None = None


@router.put("/plantillas/{tid}")
def put_plantilla(tid: str, body: EditPlantilla):
    f = projects.templates_dir() / f"{Path(tid).name}.json"
    t = projects.read_json(f)
    if not t:
        raise HTTPException(404)
    t.update({k: v for k, v in body.model_dump().items() if v is not None})
    projects.write_json(f, t)
    return {"ok": True}


@router.post("/plantillas/aprender")
async def aprender_estilo(archivo: UploadFile = File(...), nombre: str = Form(...), descripcion: str = Form(""),
                          cliente: str = Form("")):
    tmp = settings.local_dir() / "subidas" / f"estilo-{time.time_ns()}"
    tmp.mkdir(parents=True)
    ref = tmp / Path(archivo.filename).name
    with open(ref, "wb") as f:
        shutil.copyfileobj(archivo.file, f, 8 << 20)
    job = Job("estilo", "", f"Aprendiendo el estilo «{nombre}»", "claude")

    def run(j: Job):
        try:
            return workflow.learn_style(ref, nombre, descripcion, cliente,
                                        lambda e: e["type"] == "status" and jobs.say(j, e["text"]), j.cancel)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    return jobs.submit(job, run).public()


class Aprendizajes(BaseModel):
    texto: str


@router.get("/clientes/{slug}/aprendizajes")
def get_aprendizajes(slug: str):
    f = projects.client_learnings_path(slug)
    return {"texto": f.read_text(encoding="utf-8") if f.exists() else ""}


@router.put("/clientes/{slug}/aprendizajes")
def put_aprendizajes(slug: str, body: Aprendizajes):
    if not projects.get_client(slug):
        raise HTTPException(404)
    projects.client_learnings_path(slug).write_text(body.texto.strip() + "\n", encoding="utf-8")
    return {"ok": True}
