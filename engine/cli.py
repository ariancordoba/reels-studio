"""reels check|stills|render|music <proyecto | versión | spec.json>

Con --json cada línea de salida es un evento JSON (la app lo usa para la barra de progreso).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import compose, music, overlay, stills
from .project import Target, resolve
from .spec import SpecError


class Out:
    def __init__(self, as_json: bool):
        self.json = as_json
        self._last = 0.0

    def event(self, kind: str, **kw):
        if self.json:
            print(json.dumps({"event": kind, **kw}, ensure_ascii=False), flush=True)
        elif kind == "progress":
            now = time.monotonic()
            if now - self._last > 0.3 or kw["done"] == kw["total"]:
                self._last = now
                end = "\n" if kw["done"] == kw["total"] else ""
                print(f"\r  {kw['stage']}: {kw['done']}/{kw['total']}", end=end, flush=True)
        elif kind == "stage":
            print(f"· {kw['msg']}", flush=True)
        elif kind == "warning":
            print(f"  aviso: {kw['msg']}", flush=True)
        elif kind == "error":
            print(f"ERROR: {kw['msg']}", file=sys.stderr, flush=True)
        elif kind == "done":
            print("listo: " + ", ".join(str(v) for v in kw.values()), flush=True)

    def progress(self, stage):
        return lambda done, total: self.event("progress", stage=stage, done=done, total=total)


def _target(a, out: Out) -> Target | None:
    try:
        t = resolve(a.target, [Path(c) for c in a.clips])
    except SpecError as e:
        for m in e.errors:
            out.event("error", msg=m)
        return None
    except FileNotFoundError as e:
        out.event("error", msg=str(e))
        return None
    errors, warns = t.check()
    for w in warns:
        out.event("warning", msg=w)
    for e in errors:
        out.event("error", msg=e)
    return None if errors else t


def cmd_check(a, out):
    t = _target(a, out)
    if t:
        out.event("done", ok="spec válido")
    return 0 if t else 1


def cmd_stills(a, out):
    t = _target(a, out)
    if not t:
        return 1
    times = [float(x) for x in a.times.split(",")] if a.times else None
    dest = Path(a.out) if a.out else t.out_dir / "stills"
    out.event("stage", msg="generando cuadros de vista previa")
    paths = stills.render(t.spec, t.clips(), dest, times, t.font_dirs, dense=a.completo)
    out.event("done", stills=[str(p) for p in paths] if a.json else dest)
    return 0


def cmd_render(a, out):
    t = _target(a, out)
    if not t:
        return 1
    scale = 0.5 if a.draft else 1.0
    dest = Path(a.out) if a.out else t.out_dir / ("borrador.mp4" if a.draft else "video.mp4")
    fps = t.spec.format.fps
    n = int(round(t.spec.format.duration * fps))
    out.event("stage", msg="música")
    wav = dest.with_suffix(".wav")
    audio = music.render(t.spec, wav, t.project or t.out_dir)
    out.event("stage", msg="textos")
    ov = overlay.render(t.spec, list(range(n)), scale, t.font_dirs, out.progress("textos"))
    out.event("stage", msg="video")
    compose.render_video(t.spec, t.clips(), dest, audio, scale, ov, crf=23 if a.draft else 18,
                         progress=out.progress("video"))
    if audio:
        wav.unlink(missing_ok=True)
    out.event("done", video=str(dest))
    return 0


def cmd_music(a, out):
    t = _target(a, out)
    if not t:
        return 1
    dest = Path(a.out) if a.out else t.out_dir / "musica.wav"
    if music.render(t.spec, dest, t.project or t.out_dir) is None:
        out.event("warning", msg="el spec no tiene música")
        return 0
    lufs, peak = music.loudness(dest)
    out.event("done", musica=str(dest), lufs=round(lufs, 1), pico_dbfs=round(peak, 1))
    return 0


# ── flujo con Claude (usa app/, se importa sólo si hace falta)
def _emit_to(out: Out):
    def emit(e):
        if e["type"] == "status":
            out.event("stage", msg=e["text"])
        elif e["type"] == "progress":
            out.event("progress", stage=e["stage"], done=e["done"], total=e["total"])
        elif e["type"] == "thinking" and out.json:
            out.event("thinking", text=e["text"])
        elif e["type"] == "session" and out.json:
            out.event("session", session_id=e["session_id"])
    return emit


def _report(res: dict, out: Out) -> int:
    for w in res.get("warnings") or []:
        out.event("warning", msg=w)
    if not res["ok"]:
        out.event("error", msg=res["message"])
        return 1
    if out.json:
        out.event("done", **{k: v for k, v in res.items() if k != "ok"})
    else:
        print(f"\n{res.get('version', '')}: {res['message']}\n")
    return 0


def cmd_analyze(a, out):
    from app import workflow

    workflow.run_analysis(Path(a.project).resolve(), _emit_to(out))
    out.event("done", analisis=str(Path(a.project) / "analisis" / "resumen.md"))
    return 0


def cmd_nuevo(a, out):
    from app import projects, workflow

    instr = Path(a.instrucciones).read_text(encoding="utf-8") if Path(a.instrucciones).is_file() else a.instrucciones
    p = projects.create_project(a.titulo, a.cliente, [Path(x) for x in a.crudos],
                                [Path(x) for x in a.referencias], instr, a.duracion)
    out.event("stage", msg=f"proyecto creado: {p}")
    return _report(workflow.first_version(p, _emit_to(out)), out)


def cmd_pedir(a, out):
    from app import workflow

    return _report(workflow.request_change(Path(a.project).resolve(), a.pedido, _emit_to(out)), out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="reels", description="Motor de Reels Studio")
    ap.add_argument("--json", action="store_true", help="eventos JSON por línea (para la app)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        p = sub.add_parser(name, help=help_)
        p.add_argument("target", help="carpeta de proyecto, carpeta de versión o spec.json")
        p.add_argument("--clips", action="append", default=[], help="carpeta extra donde buscar crudos")
        p.set_defaults(fn=fn)
        return p

    add("check", cmd_check, "valida el spec contra los archivos")
    p = add("stills", cmd_stills, "cuadros sueltos + hoja de contacto")
    p.add_argument("--times", help="segundos separados por coma (default: uno por escena)")
    p.add_argument("--completo", action="store_true", help="un cuadro cada medio segundo (vista previa para revisar)")
    p.add_argument("-o", "--out", help="carpeta de salida (default: <versión>/stills)")
    p = add("render", cmd_render, "renderiza el video")
    p.add_argument("--draft", action="store_true", help="borrador rápido a 540×960")
    p.add_argument("-o", "--out", help="archivo de salida (default: <versión>/video.mp4)")
    p = add("music", cmd_music, "genera sólo la música (wav)")
    p.add_argument("-o", "--out")

    p = sub.add_parser("analyze", help="analiza referencias y crudos de un proyecto")
    p.add_argument("project")
    p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("nuevo", help="crea un proyecto y le pide a Claude la primera versión")
    p.add_argument("--titulo", required=True)
    p.add_argument("--cliente", required=True, help="slug del cliente")
    p.add_argument("--crudos", nargs="+", required=True)
    p.add_argument("--referencias", nargs="*", default=[])
    p.add_argument("--instrucciones", required=True, help="texto o ruta a un .md/.txt")
    p.add_argument("--duracion", type=float)
    p.set_defaults(fn=cmd_nuevo)
    p = sub.add_parser("pedir", help="pedido de cambio a Claude (crea una versión nueva)")
    p.add_argument("project")
    p.add_argument("pedido")
    p.set_defaults(fn=cmd_pedir)

    for stream in (sys.stdout, sys.stderr):  # la consola de Windows no es UTF-8 por defecto
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    a = ap.parse_args(argv)
    out = Out(a.json)
    try:
        return a.fn(a, out)
    except KeyboardInterrupt:
        out.event("error", msg="cancelado")
        return 130
    except Exception as e:  # noqa: BLE001 — que la app siempre reciba un mensaje legible
        out.event("error", msg=f"{type(e).__name__}: {e}")
        if not a.json:
            raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
