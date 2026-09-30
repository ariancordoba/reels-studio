"""Crudos → cuadros normalizados al lienzo (cubriendo, crop centrado), cacheados por hash del archivo.

ffmpeg aplica la rotación de los metadatos (iPhone); OpenCV no siempre, por eso se decodifica con ffmpeg.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from .probe import NO_WINDOW, cache_root, ffmpeg_exe, probe


def file_key(path: str | Path) -> str:
    """Hash rápido: tamaño + primeros y últimos 2 MB (los crudos pesan cientos de MB)."""
    p = Path(path)
    size = p.stat().st_size
    h = hashlib.sha1(str(size).encode())
    with open(p, "rb") as f:
        h.update(f.read(2 << 20))
        if size > 4 << 20:
            f.seek(-(2 << 20), os.SEEK_END)
            h.update(f.read())
    return h.hexdigest()[:16]


class Proxy:
    def __init__(self, clip: str | Path, w: int, h: int):
        self.clip = Path(clip)
        self.info = probe(clip)
        self.w, self.h = w, h
        self.dir = cache_root() / "proxies" / f"{file_key(clip)}_{w}x{h}"
        self._frames: dict[int, np.ndarray] = {}

    @property
    def ready(self) -> bool:
        return (self.dir / "done").exists()

    def build(self):
        if self.ready:
            return
        tmp = self.dir.with_name(self.dir.name + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        vf = (f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase:flags=lanczos,"
              f"crop={self.w}:{self.h},setsar=1")
        cmd = [ffmpeg_exe(), "-v", "error", "-y", "-i", str(self.clip), "-vf", vf, "-fps_mode", "passthrough",
               "-q:v", "2", str(tmp / "%05d.jpg")]
        r = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW)
        if r.returncode != 0:
            shutil.rmtree(tmp, ignore_errors=True)
            raise RuntimeError(f"ffmpeg no pudo decodificar {self.clip.name}: {r.stderr[-500:]}")
        shutil.rmtree(self.dir, ignore_errors=True)
        tmp.rename(self.dir)
        (self.dir / "done").write_text(str(len(list(self.dir.glob("*.jpg")))))

    @property
    def n_frames(self) -> int:
        return int((self.dir / "done").read_text())

    def frame(self, ts: float) -> np.ndarray:
        """Cuadro más cercano al segundo `ts` del clip, float32 BGR 0..1."""
        i = min(max(int(round(ts * self.info.fps)), 0), self.n_frames - 1) + 1
        f = self._frames.get(i)
        if f is None:
            if len(self._frames) > 48:
                self._frames.clear()
            img = cv2.imread(str(self.dir / f"{i:05d}.jpg"), cv2.IMREAD_COLOR)
            f = self._frames[i] = img.astype(np.float32) / 255.0
        return f


@lru_cache(maxsize=16)
def get(clip: str, w: int, h: int) -> Proxy:
    p = Proxy(clip, w, h)
    p.build()
    return p
