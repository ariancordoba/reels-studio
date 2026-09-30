"""Metadatos de crudos (duración, fps, rotación, resolución) con el ffmpeg que viene en imageio-ffmpeg.

imageio-ffmpeg no trae ffprobe, así que se lee la salida de `ffmpeg -i`.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import imageio_ffmpeg

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "assets"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # sin consola que parpadee en Windows


def ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def cache_root() -> Path:
    root = os.environ.get("REELS_CACHE") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ReelsStudio" / "cache"
    p = Path(root)
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass(frozen=True)
class ClipInfo:
    path: str
    duration: float
    fps: float
    width: int  # ya rotado (como se ve)
    height: int
    rotation: float
    has_audio: bool


@lru_cache(maxsize=64)
def _probe(path: str, _mtime: float) -> ClipInfo:
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    txt = r.stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", txt)
    if not m:
        raise ValueError(f"no pude leer '{Path(path).name}' como video")
    dur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    vline = next((l for l in txt.splitlines() if "Video:" in l), None)
    if vline is None:
        raise ValueError(f"'{Path(path).name}' no tiene pista de video")
    wh = re.search(r", (\d{2,5})x(\d{2,5})", vline)
    w, h = int(wh[1]), int(wh[2])
    fr = re.search(r"([\d.]+) tbr", vline) or re.search(r"([\d.]+) fps", vline)
    fps = float(fr[1]) if fr else 30.0
    rot = re.search(r"rotation of (-?[\d.]+) degrees", txt)
    rotation = float(rot[1]) if rot else 0.0
    if round(abs(rotation)) % 180 == 90:
        w, h = h, w
    return ClipInfo(path, dur, fps, w, h, rotation, "Audio:" in txt)


def probe(path: str | Path) -> ClipInfo:
    p = str(Path(path).resolve())
    return _probe(p, os.path.getmtime(p))
