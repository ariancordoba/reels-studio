"""Planos + cámara + transiciones + grade + overlay → cuadros crudos → ffmpeg.

Todo sale del spec. Las coordenadas del spec (center, amplitudes, degradés) están en px del lienzo
1080×1920; con `scale` < 1 (borrador) se multiplica todo y se trabaja a menor resolución.
"""
from __future__ import annotations

import math
import os
import subprocess
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np

from . import proxies
from .motion import ease_in_out, spring
from .probe import NO_WINDOW, ffmpeg_exe
from .spec import Spec

WHIP_DUR, WHIP_AMP, WHIP_SUBSAMPLES = 0.12, 260.0, 7
FLASH_DUR = 0.12
ZOOM_PUNCH = 0.30


def canvas_size(spec: Spec, scale: float) -> tuple[int, int]:
    even = lambda x: max(2, int(round(x * scale / 2)) * 2)
    return even(spec.format.w), even(spec.format.h)


class Composer:
    def __init__(self, spec: Spec, clips: dict[str, Path], scale: float = 1.0, overlay_dir: Path | None = None):
        self.spec, self.scale = spec, scale
        self.W, self.H = canvas_size(spec, scale)
        self.cw, self.ch = spec.format.w, spec.format.h  # lienzo lógico
        self.proxies = {s.clip: proxies.get(str(clips[s.clip]), self.W, self.H) for s in spec.shots}
        self.overlay_dir = overlay_dir
        self.beat = 60.0 / spec.bpm
        self.whips = [s.t0 for s in spec.shots[1:] if s.transition_in == "whip"]
        self.flashes = [(e.t, e.dur or FLASH_DUR, e.strength) for e in spec.effects if e.type == "flash"]
        self.flashes += [(s.t0, FLASH_DUR, 0.85) for s in spec.shots[1:] if s.transition_in == "flash"]
        self._grade_maps()

    # ── grade
    def _grade_maps(self):
        st, s = self.spec.style, self.scale
        yy, xx = np.mgrid[0:self.H, 0:self.W].astype(np.float32) / s  # en px del lienzo lógico
        cw, ch = self.cw, self.ch
        vig = 1 - st.vignette * (((xx - cw / 2) / (cw * 0.75)) ** 2 + ((yy - ch / 2) / (ch * 0.7)) ** 2)
        vig = np.clip(vig, 0.6, 1)
        # degradé oscuro arriba (hasta 1250 px de 1920) y abajo (desde 1550 px), para que se lea el texto
        top = st.top_gradient * np.clip(1 - yy / (ch * 1250 / 1920), 0, 1) ** 1.5
        bot = st.bottom_gradient * np.clip((yy - ch * 1550 / 1920) / (ch * 370 / 1920), 0, 1) ** 1.3
        self.gain = (vig * (1 - top) * (1 - st.darken) * (1 - bot))[..., None].astype(np.float32)

    def grade(self, img):
        st = self.spec.style
        if st.contrast != 1:
            img = np.clip((img - 0.5) * st.contrast + 0.5, 0, 1)
        if st.saturation != 1:
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            hsv[..., 1] = np.clip(hsv[..., 1] * st.saturation, 0, 1)
            img = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        return img * self.gain

    # ── cámara: el operador
    def camera(self, t):
        shot, cam = self.spec.shot_at(t), self.spec.camera
        u = ease_in_out((t - shot.t0) / (shot.t1 - shot.t0))
        z = shot.zoom[0] + (shot.zoom[1] - shot.zoom[0]) * u
        (cx0, cy0), (cx1, cy1) = shot.center
        cx, cy = cx0 + (cx1 - cx0) * u, cy0 + (cy1 - cy0) * u
        z *= 1 + cam.beat_punch * math.exp(-(t % self.beat) * 9)  # golpe en cada negra
        if shot.t0 > 0:  # entrada al plano: arranca un poco más cerca y se asienta
            punch = ZOOM_PUNCH if shot.transition_in == "zoom_punch" else cam.entry_punch
            z *= 1 + punch * (1 - spring(t - shot.t0, 0.55, 16))
        amp = cam.handheld if shot.handheld is None else shot.handheld  # flote de mano
        dx = amp * math.sin(t * 1.3 + 0.4) + 0.6 * amp * math.sin(t * 2.9)
        dy = amp * math.sin(t * 1.1 + 1.7) + 0.6 * amp * math.sin(t * 2.3 + 0.2)
        rot = 0.0
        for sh in cam.shakes:
            tau = t - sh.t
            if tau > 0:
                e = sh.amp * math.exp(-8 * tau)
                w = 2 * math.pi * tau
                dx += e * math.sin(w * 19)
                dy += 0.7 * e * math.sin(w * 24.9)
                rot += 0.03 * e * math.sin(w * 14.6)
        return z, cx, cy, dx, dy, rot

    def plate(self, t):
        shot = self.spec.shot_at(t)
        img = self.proxies[shot.clip].frame(shot.src_in + (t - shot.t0) * shot.speed)
        z, cx, cy, dx, dy, rot = self.camera(t)
        s = self.scale
        M = cv2.getRotationMatrix2D((cx * s, cy * s), rot, z)
        M[0, 2] += self.W / 2 - cx * s + dx * s
        M[1, 2] += self.H / 2 - cy * s + dy * s
        return cv2.warpAffine(img, M, (self.W, self.H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

    def whip_offset(self, t):
        """Paneo látigo vertical alrededor del corte (en px del lienzo lógico)."""
        for c in self.whips:
            d = t - c
            if -WHIP_DUR <= d < 0:
                return -ease_in_out((d + WHIP_DUR) / WHIP_DUR) ** 2 * WHIP_AMP
            if 0 <= d < WHIP_DUR:
                return (1 - ease_in_out(d / WHIP_DUR)) ** 2 * WHIP_AMP
        return 0.0

    def fade(self, t) -> float:
        k = 1.0
        for e in self.spec.effects:
            dur = e.dur or 0.4
            if e.type == "fade_out" and t > e.t:
                k *= max(0.0, 1 - (t - e.t) / dur)
            elif e.type == "fade_in" and t < e.t + dur:
                k *= min(1.0, max(0.0, (t - e.t) / dur))
        return k

    def frame(self, t: float) -> np.ndarray:
        fps = self.spec.format.fps
        if abs(self.whip_offset(t)) > 2:  # obturador: promedio de sub-muestras a lo largo del movimiento
            acc = np.zeros((self.H, self.W, 3), np.float32)
            for k in range(WHIP_SUBSAMPLES):
                tt = t + (k / (WHIP_SUBSAMPLES - 1) - 0.5) / fps * 0.5
                M = np.float32([[1, 0, 0], [0, 1, self.whip_offset(tt) * self.scale]])
                acc += cv2.warpAffine(self.plate(tt), M, (self.W, self.H), borderMode=cv2.BORDER_REFLECT)
            img = acc / WHIP_SUBSAMPLES
        else:
            img = self.plate(t)
        img = self.grade(img)
        for ft, dur, strength in self.flashes:
            if ft <= t < ft + dur:
                fl = strength * (1 - (t - ft) / dur)
                img = img * (1 - fl) + fl
        k = self.fade(t)
        if k < 1:
            img = img * k
        if self.overlay_dir is not None:
            p = self.overlay_dir / f"{round(t * fps):05d}.png"
            ov = cv2.imread(str(p), cv2.IMREAD_UNCHANGED) if p.exists() else None
            if ov is not None:
                if ov.shape[:2] != (self.H, self.W):
                    ov = cv2.resize(ov, (self.W, self.H), interpolation=cv2.INTER_AREA)
                ov = ov.astype(np.float32) / 255.0
                a = ov[..., 3:4] * k
                img = img * (1 - a) + ov[..., :3] * a
        return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


# ── render en paralelo: cada proceso arma su Composer una vez
_C: Composer | None = None


def _init(spec_json, clips, scale, overlay_dir):
    global _C
    cv2.setNumThreads(1)
    _C = Composer(Spec.model_validate_json(spec_json), clips, scale, overlay_dir)


def _frame(i):
    return _C.frame(i / _C.spec.format.fps).tobytes()


def render_video(spec: Spec, clips: dict[str, Path], out: Path, audio: Path | None, scale: float = 1.0,
                 overlay_dir: Path | None = None, crf: int = 18, progress=None, cancel=None):
    # que los proxies existan antes de repartir el trabajo (si no, cada proceso los generaría)
    W, H = canvas_size(spec, scale)
    for s in spec.shots:
        proxies.get(str(clips[s.clip]), W, H)
    fps = spec.format.fps
    n = int(round(spec.format.duration * fps))
    tmp = out.with_name(out.stem + ".part" + out.suffix)
    cmd = [ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-"]
    if audio:
        cmd += ["-i", str(audio)]
    cmd += ["-c:v", "libx264", "-preset", "medium" if scale < 1 else "slow", "-crf", str(crf),
            "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "256k", "-shortest"]
    cmd += ["-movflags", "+faststart", str(tmp)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NO_WINDOW)
    nproc = max(1, min(6, (os.cpu_count() or 4) - 2))
    ok = False
    try:
        with Pool(nproc, _init, (spec.model_dump_json(), clips, scale, overlay_dir)) as pool:
            for i, buf in enumerate(pool.imap(_frame, range(n), chunksize=2)):
                p.stdin.write(buf)
                progress and progress(i + 1, n)
                if cancel and cancel():
                    pool.terminate()
                    raise KeyboardInterrupt("render cancelado")
        ok = True
    finally:
        p.stdin.close()
        err = p.stderr.read().decode(errors="replace")
        p.wait()
        if not ok:
            tmp.unlink(missing_ok=True)
    if p.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg falló: {err[-800:]}")
    tmp.replace(out)
    return out
