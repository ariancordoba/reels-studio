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


def used_font_names(spec: Spec) -> list[str]:
    st = spec.style
    names = [st.display_font, st.serif_font, st.script_font]
    names += [ln.font for sc in spec.scenes for ln in sc.lines if ln.font]
    return list(dict.fromkeys(names))


def resolve_fonts(spec: Spec, extra_dirs: list[Path] | None = None) -> dict[str, Path | None]:
    """{nombre de fuente del spec: archivo} para todas las que usa el video, + "__emoji__"."""
    dirs = font_dirs(extra_dirs)
    out: dict[str, Path | None] = {n: find_font(n, dirs) for n in used_font_names(spec)}
    out["__emoji__"] = next((ASSETS / "fonts" / f for f in EMOJI_FILES if (ASSETS / "fonts" / f).exists()), None)
    return out


def resolve_logo(spec: Spec, dirs: list[Path]) -> Path | None:
    """Archivo del logo listo para usar (PNG transparente). Uno con fondo liso se limpia solo (y se cachea)."""
    if not spec.logo:
        return None
    name = Path(spec.logo.file)
    src = name if name.is_absolute() and name.exists() else next((d / name for d in dirs if (d / name).is_file()), None)
    if src is None:
        raise FileNotFoundError(f"no encuentro el logo «{spec.logo.file}»")
    from . import photos
    from .proxies import file_key

    out = cache_root() / "logos" / f"{file_key(src)}.png"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        photos.logo_png(src, out)
    return out


def page_payload(spec: Spec, fonts: dict[str, Path | None], logo: Path | None = None) -> dict:
    d = spec.model_dump(include={"format", "style", "scenes", "footer"})
    d["fonts"] = {k: (v.resolve().as_uri() if v else None) for k, v in fonts.items()}
    if logo and spec.logo:
        d["logo"] = {**spec.logo.model_dump(), "url": logo.resolve().as_uri()}
    return d


def overlay_key(payload: dict, fonts: dict[str, Path | None], scale: float, logo: Path | None = None) -> str:
    h = hashlib.sha1(json.dumps(payload, sort_keys=True).encode())
    for src in (COMP, MOTION_JS, *[f for f in fonts.values() if f], *([logo] if logo else [])):
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
           progress=None, asset_dirs: list[Path] | None = None) -> Path:
    """Renderiza los cuadros pedidos (índices a spec.format.fps) y devuelve la carpeta con los PNG."""
    fonts = resolve_fonts(spec, font_extra)
    # el logo puede estar con los crudos, en el proyecto o en la carpeta del cliente (padre de fonts/)
    dirs = [*(asset_dirs or []), *[d.parent for d in (font_extra or [])]]
    logo = resolve_logo(spec, dirs)
    payload = page_payload(spec, fonts, logo)
    out = cache_root() / "overlay" / overlay_key(payload, fonts, scale, logo)
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
