"""Reels Studio: servidor local (FastAPI) + ventana nativa (pywebview / Edge WebView2).

    uv run python -m app.main            → abre la ventana
    uv run python -m app.main --browser  → sólo el servidor, para abrir en el navegador (desarrollo)
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import settings, updater
from .api.routes import router

DIST = settings.REPO / "ui" / "dist"

app = FastAPI(title="Reels Studio", docs_url="/api/docs")
app.include_router(router)

if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    f = DIST / path
    if path and f.is_file():
        return FileResponse(f)
    idx = DIST / "index.html"
    if idx.exists():
        return FileResponse(idx, headers={"Cache-Control": "no-cache"})
    return {"error": "Falta compilar la interfaz: cd ui && npm run build"}


def free_port(preferred: int = 8765) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("no hay puertos libres")


def running_instance(port: int) -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/estado", timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


def serve(port: int):
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return server, t


def log_to_file():
    """Con pythonw (sin consola) stdout/stderr son None: todo va a un log para poder diagnosticar."""
    if sys.stdout is None or sys.stderr is None:
        logs = settings.local_dir() / "logs"
        logs.mkdir(exist_ok=True)
        f = open(logs / "app.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        f.write(f"\n── {time.strftime('%Y-%m-%d %H:%M:%S')} inicio en {settings.machine()}\n")
        sys.stdout = sys.stderr = f


def main(argv=None):
    log_to_file()
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    if running_instance(a.port):
        # ya está abierta: otra ventana contra el mismo servidor (una sola cola de renders)
        if not a.browser:
            import webview

            webview.create_window("Reels Studio", f"http://127.0.0.1:{a.port}/", width=1440, height=900,
                                  min_size=(1100, 720), background_color="#F3F3F1")
            webview.start()
        return
    port = free_port(a.port)
    server, t = serve(port)
    url = f"http://127.0.0.1:{port}/"
    if a.browser:
        print(f"Reels Studio en {url}", flush=True)
        updater.on_exit(lambda: os._exit(0))
        t.join()
        return
    import webview

    win = webview.create_window("Reels Studio", url, width=1440, height=900, min_size=(1100, 720),
                          background_color="#F3F3F1")
    updater.on_exit(win.destroy)
    threading.Thread(target=auto_update_loop, daemon=True).start()
    icon = settings.REPO / "assets" / "icono.ico"
    webview.start(private_mode=False, icon=str(icon) if icon.exists() else None)
    server.should_exit = True
    updater.apply_pending_on_exit()  # si se descargó una versión nueva, se instala ahora que se cerró


def auto_update_loop():
    """Busca actualizaciones al abrir y cada 6 horas; si hay, las deja descargadas y avisa a la UI."""
    from .jobs import bus

    time.sleep(8)  # que la app termine de abrir primero
    while True:
        updater.auto_prepare(lambda p: bus.publish({"type": "actualizacion_lista", "version": p["version"]}))
        time.sleep(6 * 3600)


if __name__ == "__main__":
    main(sys.argv[1:])
