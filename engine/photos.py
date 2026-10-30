"""Fotos como crudos: una foto es un clip "quieto" y el movimiento lo pone la cámara del plano (zoom y
desplazamiento lento, tipo Ken Burns).

Las fotos de celular guardan la orientación en el EXIF (si no se aplica, salen acostadas) y las de
iPhone suelen ser HEIC: se leen con Pillow + pillow-heif.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # sin HEIC: el resto de los formatos sigue andando
    pass

PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".heif", ".tif", ".tiff"}
# una foto "dura" lo que pida el plano: se declara larga para que cualquier src_in/velocidad sea válido
PHOTO_DURATION = 600.0
PHOTO_FPS = 30.0


def is_photo(path: str | Path) -> bool:
    return Path(path).suffix.lower() in PHOTO_EXT


def load(path: str | Path) -> np.ndarray:
    """BGR uint8, ya derecha (orientación EXIF aplicada)."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        rgb = np.asarray(im.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def size(path: str | Path) -> tuple[int, int]:
    """(ancho, alto) como se ve (con la orientación EXIF aplicada), sin decodificar toda la imagen."""
    with Image.open(path) as im:
        w, h = im.size
        orient = im.getexif().get(0x0112, 1)
    return (h, w) if orient in (5, 6, 7, 8) else (w, h)


def logo_png(src: str | Path, dst: str | Path, tol: int = 28) -> Path:
    """Logo sobre fondo liso (blanco o del color de las esquinas) → PNG transparente, recortado al contenido.

    Sólo se borra el fondo que toca los bordes (relleno desde afuera): el blanco de adentro del logo queda.
    Si ya trae transparencia, sólo se recorta.
    """
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGBA")
        rgba = np.asarray(im).copy()
    if rgba[..., 3].min() < 250:  # ya es transparente
        alpha = rgba[..., 3]
    else:
        bgr = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2BGR)
        h, w = bgr.shape[:2]
        mask = np.zeros((h + 2, w + 2), np.uint8)
        flags = 4 | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE | (255 << 8)
        for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
            if mask[y + 1, x + 1] == 0:
                cv2.floodFill(bgr, mask, (x, y), 0, (tol,) * 3, (tol,) * 3, flags)
        bg = mask[1:-1, 1:-1] > 0
        alpha = np.where(bg, 0, 255).astype(np.uint8)
        alpha = cv2.GaussianBlur(alpha, (3, 3), 0)  # borde suave, sin serrucho
    rgba[..., 3] = alpha
    ys, xs = np.nonzero(alpha > 10)
    if len(xs):
        pad = 4
        rgba = rgba[max(0, ys.min() - pad): ys.max() + pad + 1, max(0, xs.min() - pad): xs.max() + pad + 1]
    out = Path(dst)
    Image.fromarray(rgba, "RGBA").save(out)
    return out


def cover(img: np.ndarray, w: int, h: int) -> np.ndarray:
    """Escala para cubrir w×h y recorta al centro (igual que los videos)."""
    ih, iw = img.shape[:2]
    k = max(w / iw, h / ih)
    nw, nh = max(w, round(iw * k)), max(h, round(ih * k))
    img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)
    x, y = (nw - w) // 2, (nh - h) // 2
    return img[y:y + h, x:x + w]
