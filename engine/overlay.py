"""Textos: Playwright abre text_comp/comp.html con el spec y saca un PNG transparente por cuadro.

Los PNG se cachean por hash de (textos + estilo + fuentes + escala): si sólo cambian los planos o la
música, el overlay no se vuelve a renderizar.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .probe import ASSETS, cache_root
from .spec import Spec

COMP = Path(__file__).parent / "text_comp" / "comp.html"
MOTION_JS = COMP.with_name("motion.js")
FONT_EXT = (".ttf", ".otf", ".woff2", ".woff")
EMOJI_FILES = ("NotoColorEmoji.ttf", "Noto-COLRv1.ttf")


def workers(n_items: int) -> int:
    return max(1, min(6, (os.cpu_count() or 4) - 2, n_items))


def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def find_font(name: str, dirs: list[Path]) -> Path | None:
    """Busca un archivo de fuente cuyo nombre coincida con `name` (ignora mayúsculas/espacios/guiones)."""
    want = _norm(name)
    cands = [f for d in dirs if d.is_dir() for f in d.iterdir() if f.suffix.lower() in FONT_EXT]
    for f in cands:
        if _norm(f.stem) == want:
            return f
    for f in cands:  # "Penting" → "Penting-Heavy.otf"
        if _norm(f.stem).startswith(want):
            return f
    return None


def font_dirs(extra: list[Path] | None = None) -> list[Path]:
    return [*(extra or []), ASSETS / "fonts"]


def resolve_fonts(spec: Spec, extra_dirs: list[Path] | None = None) -> dict[str, Path | None]:
    dirs = font_dirs(extra_dirs)
    emoji = next((ASSETS / "fonts" / f for f in EMOJI_FILES if (ASSETS / "fonts" / f).exists()), None)
    return {"display": find_font(spec.style.display_font, dirs),
            "serif": find_font(spec.style.serif_font, dirs),
            "emoji": emoji}


def page_payload(spec: Spec, fonts: dict[str, Path | None]) -> dict:
    d = spec.model_dump(include={"format", "style", "scenes", "footer"})
    d["fonts"] = {k: (v.resolve().as_uri() if v else None) for k, v in fonts.items()}
    return d


def overlay_key(payload: dict, fonts: dict[str, Path | None], scale: float) -> str:
    h = hashlib.sha1(json.dumps(payload, sort_keys=True).encode())
    for src in (COMP, MOTION_JS, *[f for f in fonts.values() if f]):
        h.update(src.read_bytes() if src.stat().st_size < (40 << 20) else str(src.stat().st_mtime).encode())
    h.update(str(scale).encode())
    return h.hexdigest()[:16]


def _work(args):
    payload, frames, fps, scale, out = args
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=scale)
        pg.add_init_script(f"window.__SPEC = {json.dumps(payload)};")
        pg.goto(COMP.as_uri())
        pg.evaluate("window.__ready")
        for f in frames:
            pg.evaluate(f"window.__seek({f / fps})")
            pg.screenshot(path=str(Path(out) / f"{f:05d}.png"), omit_background=True)
        b.close()
    return len(frames)


def render(spec: Spec, frames: list[int], scale: float = 1.0, font_extra: list[Path] | None = None,
           progress=None) -> Path:
    """Renderiza los cuadros pedidos (índices a spec.format.fps) y devuelve la carpeta con los PNG."""
    fonts = resolve_fonts(spec, font_extra)
    payload = page_payload(spec, fonts)
    out = cache_root() / "overlay" / overlay_key(payload, fonts, scale)
    out.mkdir(parents=True, exist_ok=True)
    todo = [f for f in frames if not (out / f"{f:05d}.png").exists()]
    if todo:
        n = workers(len(todo))
        chunks = [todo[i::n] for i in range(n)]
        # tandas para poder informar progreso (cada tanda abre su Chromium: no tan chicas)
        size = max(30, len(todo) // (n * 4))
        jobs = [(payload, c[i:i + size], spec.format.fps, scale, str(out)) for c in chunks for i in range(0, len(c), size)]
        if n == 1:
            done = 0
            for j in jobs:
                done += _work(j)
                progress and progress(done, len(todo))
        else:
            with ProcessPoolExecutor(n) as ex:
                done = 0
                for k in ex.map(_work, jobs):
                    done += k
                    progress and progress(done, len(todo))
    return out


def clear_cache():
    shutil.rmtree(cache_root() / "overlay", ignore_errors=True)
