"""Actualizaciones: buscar, descargar y aplicar una versión nueva sin que ella toque nada.

Fuente (update_source.txt o Ajustes): `github:usuario/repo` (último release público; el zip es un asset)
o la URL de un manifiesto JSON {"version", "url", "sha256", "notas"}.

Aplicar: la app no puede pisar sus propios archivos mientras corre, así que deja un script de PowerShell
que espera a que la app se cierre, hace backup, copia la versión nueva, borra lo que ya no existe,
corre `uv sync` y vuelve a abrir la app. Los datos (proyectos, clientes) viven afuera: no se tocan.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import urllib.request
import zipfile
from pathlib import Path

from . import settings

UA = {"User-Agent": "ReelsStudio-updater"}
KEEP = {".venv", "ejemplo", "out", "node_modules", ".git"}  # nunca se borran al actualizar


def current_version() -> str:
    try:
        return (settings.REPO / "VERSION").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "0.0.0"


def vtuple(v: str) -> tuple[int, ...]:
    out = []
    for part in v.strip().lstrip("vV").split("."):
        num = "".join(c for c in part if c.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out)


def source() -> str:
    cfg = settings.load().get("update_source")
    if cfg:
        return cfg.strip()
    f = settings.REPO / "update_source.txt"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                return line.strip()
    return ""


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={**UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def check() -> dict:
    """{configurado, actual, disponible, version, notas, url, sha256, error}"""
    cur = current_version()
    src = source()
    base = {"configurado": bool(src), "actual": cur, "disponible": False}
    if not src:
        return base
    try:
        if src.startswith("github:"):
            repo = src.removeprefix("github:").strip("/")
            rel = _get_json(f"https://api.github.com/repos/{repo}/releases/latest")
            asset = next((a for a in rel.get("assets", []) if a["name"].endswith(".zip")), None)
            if not asset:
                return {**base, "error": "El último release no tiene un .zip adjunto."}
            digest = (asset.get("digest") or "").removeprefix("sha256:") or None
            info = {"version": rel.get("tag_name", "").lstrip("vV"), "url": asset["browser_download_url"],
                    "sha256": digest, "notas": rel.get("body") or ""}
        else:
            m = _get_json(src)
            info = {"version": str(m["version"]), "url": m["url"], "sha256": m.get("sha256"), "notas": m.get("notas", "")}
    except Exception as e:  # noqa: BLE001 — sin internet, repo privado, etc.
        return {**base, "error": f"No pude buscar actualizaciones: {e}"}
    return {**base, **info, "disponible": vtuple(info["version"]) > vtuple(cur)}


def updates_dir() -> Path:
    d = settings.local_dir() / "actualizaciones"
    d.mkdir(parents=True, exist_ok=True)
    return d


def download(info: dict, progress=None, cancel: threading.Event | None = None) -> Path:
    """Baja el zip, verifica el hash y lo descomprime en una carpeta de preparación."""
    ver = info["version"]
    zpath = updates_dir() / f"reels-studio-{ver}.zip"
    req = urllib.request.Request(info["url"], headers=UA)
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as r, open(zpath, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 20):
            if cancel and cancel.is_set():
                raise KeyboardInterrupt("cancelado")
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            progress and progress(done, total)
    if info.get("sha256") and h.hexdigest().lower() != info["sha256"].lower():
        zpath.unlink(missing_ok=True)
        raise ValueError("El archivo descargado está dañado (no coincide el hash). Probá de nuevo.")
    stage = updates_dir() / f"stage-{ver}"
    shutil.rmtree(stage, ignore_errors=True)
    with zipfile.ZipFile(zpath) as z:
        for n in z.namelist():  # nada de rutas absolutas ni ".."
            if n.startswith(("/", "\\")) or ".." in Path(n).parts:
                raise ValueError(f"Zip inválido: {n}")
        z.extractall(stage)
    # el zip puede traer una carpeta raíz
    roots = [p for p in stage.iterdir()]
    if len(roots) == 1 and roots[0].is_dir() and not (stage / "VERSION").exists():
        stage = roots[0]
    if not (stage / "VERSION").exists() or not (stage / "app").is_dir():
        raise ValueError("El zip no parece una versión de Reels Studio.")
    return stage


PS_TEMPLATE = r"""
$ErrorActionPreference = 'Continue'
$log = '{log}'
function Log($m) {{ Add-Content -Path $log -Value ("$(Get-Date -Format s) " + $m) -Encoding utf8 }}
Log 'esperando que se cierre la app (pid {pid})'
try {{ Wait-Process -Id {pid} -Timeout 60 -ErrorAction SilentlyContinue }} catch {{}}
Start-Sleep -Seconds 1
$src = '{stage}'; $dst = '{install}'; $bak = '{backup}'
Log "backup en $bak"
if (Test-Path $bak) {{ Remove-Item -Recurse -Force $bak }}
robocopy $dst $bak /E /XD .venv ejemplo out node_modules .git __pycache__ /NFL /NDL /NJH /NJS | Out-Null
Log 'copiando versión nueva'
robocopy $src $dst /E /NFL /NDL /NJH /NJS | Out-Null
# borrar archivos de la versión anterior que ya no existen en la nueva
$old = Join-Path $bak 'MANIFEST.txt'; $new = Join-Path $src 'MANIFEST.txt'
if ((Test-Path $old) -and (Test-Path $new)) {{
  $keep = Get-Content $new -Encoding utf8
  foreach ($f in (Get-Content $old -Encoding utf8)) {{
    if ($f -and -not ($keep -contains $f)) {{ $p = Join-Path $dst $f; if (Test-Path $p) {{ Remove-Item -Force $p; Log "borrado $f" }} }}
  }}
}}
Set-Location $dst
$uv = '{uv}'
Log 'uv sync'
& $uv sync --no-dev *>> $log
if ($LASTEXITCODE -ne 0) {{
  Log 'uv sync falló: vuelvo a la versión anterior'
  robocopy $bak $dst /E /NFL /NDL /NJH /NJS | Out-Null
  & $uv sync --no-dev *>> $log
}}
& $uv run --no-dev playwright install chromium *>> $log
Log 'reabriendo la app'
Start-Process -FilePath (Join-Path $dst '.venv\Scripts\pythonw.exe') -ArgumentList '-m','app.main' -WorkingDirectory $dst
"""


def uv_exe() -> str:
    for c in (shutil.which("uv"), str(Path.home() / ".local" / "bin" / "uv.exe")):
        if c and Path(c).exists():
            return c
    return "uv"


def apply(stage: Path, relaunch: bool = True) -> Path:
    """Lanza el script que aplica la actualización cuando la app se cierra. Devuelve la ruta del log."""
    d = updates_dir()
    log = d / "actualizacion.log"
    script = d / "aplicar.ps1"
    body = PS_TEMPLATE.format(
        log=log, pid=os.getpid(), stage=stage, install=settings.REPO, backup=d / "backup-anterior", uv=uv_exe(),
    )
    if not relaunch:  # se aplicó al cerrar la app: no volver a abrirla
        body = body.replace("Log 'reabriendo la app'", "Log 'listo (se abre la próxima vez)'")
        body = "\n".join(l for l in body.splitlines() if not l.startswith("Start-Process"))
    script.write_text(body, encoding="utf-8-sig")
    state["applying"] = True
    # consola oculta (no DETACHED_PROCESS: PowerShell sin consola se cierra sin hacer nada)
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | settings.NO_WINDOW
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script)]
    try:
        # que el script sobreviva al cierre de la app aunque ésta corra dentro de un "job" de Windows (p. ej. `uv run`)
        subprocess.Popen(cmd, creationflags=flags | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000),
                         close_fds=True, cwd=str(d))
    except OSError:  # el job no permite salir: lanzarlo igual
        subprocess.Popen(cmd, creationflags=flags, close_fds=True, cwd=str(d))
    return log


# ── automático: al abrir, buscar y descargar en segundo plano; al cerrar, instalar
state: dict = {"pending": None, "applying": False, "checking": False}


def auto_enabled() -> bool:
    return settings.load().get("auto_update", True) and bool(source()) and not is_dev_checkout()


def auto_prepare(on_ready=None):
    """Si hay versión nueva, la deja descargada y lista ("pending"). No interrumpe nada."""
    if not auto_enabled() or state["checking"] or state["pending"]:
        return
    state["checking"] = True
    try:
        info = check()
        if info.get("disponible"):
            stage = download(info)
            state["pending"] = {"version": info["version"], "notas": info.get("notas", ""), "stage": str(stage)}
            on_ready and on_ready(state["pending"])
    except Exception:  # noqa: BLE001 — sin internet, etc.: se intenta la próxima vez
        pass
    finally:
        state["checking"] = False


def apply_pending_on_exit():
    """Llamado al cerrar la ventana: si hay una actualización descargada, se instala sola."""
    p = state["pending"]
    if p and not state["applying"] and Path(p["stage"]).exists():
        apply(Path(p["stage"]), relaunch=False)


# ── cierre de la app (lo registra main.py: cerrar la ventana o el servidor)
_exit_hook = {"fn": None}


def on_exit(fn):
    _exit_hook["fn"] = fn


def request_exit():
    fn = _exit_hook["fn"]
    threading.Timer(0.8, fn if fn else (lambda: os._exit(0))).start()


def is_dev_checkout() -> bool:
    """Carpeta de desarrollo (el paquete para compartir no lleva tests/): ahí no se pisan archivos."""
    return (settings.REPO / ".git").exists() or (settings.REPO / "tests").is_dir()
