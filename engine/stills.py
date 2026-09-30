"""Cuadros sueltos y hoja de contacto para la vista previa (sin renderizar el video entero)."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from . import overlay
from .compose import Composer
from .spec import Spec


def default_times(spec: Spec) -> list[float]:
    """Para cada escena: el momento en que terminó de entrar el texto (lo que hay que revisar)."""
    ts = []
    for sc in spec.scenes:
        last = max((ln.delay for ln in sc.lines), default=0)
        t = min(sc.t0 + last + 0.9, sc.t1 - 0.05, spec.format.duration - 0.05)
        ts.append(round(max(sc.t0, t), 2))
    if not ts:
        ts = [round(spec.format.duration * k / 4, 2) for k in (0.5, 1.5, 2.5, 3.5)]
    return ts


def contact_sheet(images: list[np.ndarray], labels: list[str], cols: int = 4, thumb_w: int = 360) -> np.ndarray:
    th = [cv2.resize(im, (thumb_w, int(im.shape[0] * thumb_w / im.shape[1])), interpolation=cv2.INTER_AREA) for im in images]
    h = th[0].shape[0]
    rows = (len(th) + cols - 1) // cols
    pad, lab = 12, 40
    sheet = np.full((rows * (h + lab + pad) + pad, cols * (thumb_w + pad) + pad, 3), 24, np.uint8)
    for i, (im, text) in enumerate(zip(th, labels)):
        r, c = divmod(i, cols)
        y, x = pad + r * (h + lab + pad), pad + c * (thumb_w + pad)
        sheet[y:y + h, x:x + thumb_w] = im
        cv2.putText(sheet, text, (x, y + h + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (235, 235, 235), 2, cv2.LINE_AA)
    return sheet


def render(spec: Spec, clips: dict[str, Path], out_dir: Path, times: list[float] | None = None,
           font_dirs: list[Path] | None = None, scale: float = 1.0) -> list[Path]:
    times = times or default_times(spec)
    fps = spec.format.fps
    ov = overlay.render(spec, sorted({round(t * fps) for t in times}), scale, font_dirs)
    comp = Composer(spec, clips, scale, ov)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("t*.jpg"):
        old.unlink()
    paths, imgs = [], []
    for t in times:
        t = round(t * fps) / fps  # el overlay está por cuadro
        img = comp.frame(t)
        p = out_dir / f"t{t:06.2f}.jpg"
        cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        paths.append(p)
        imgs.append(img)
    sheet = out_dir / "hoja.jpg"
    cv2.imwrite(str(sheet), contact_sheet(imgs, [f"{t:.2f}s" for t in times]), [cv2.IMWRITE_JPEG_QUALITY, 88])
    return [*paths, sheet]
