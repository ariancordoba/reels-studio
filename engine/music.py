"""Música: generador sintetizado paramétrico (sin licencias de terceros) o pista subida con licencia.

Síntesis: kick 4x4, clap, hats, bajo en contratiempo, stabs de acordes, redoble + riser antes del drop,
hueco de silencio, impacto; whooshes en los cortes y pops. Todo en función de bpm y duración.
Master: normalizado a target_lufs con pico ≤ −2.5 dBFS (el AAC sube los picos).
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np
import pyloudnorm
from scipy.io import wavfile
from scipy.signal import butter, fftconvolve, resample_poly, sosfilt

from .probe import NO_WINDOW, ffmpeg_exe
from .spec import MusicFile, MusicNone, MusicSynth, Spec

SR = 48000
CEILING_DB = -2.5    # techo del limitador (pico de muestra)
TRUE_PEAK_DB = -3.5  # margen: el AAC sube los picos; así queda ≤ −2 dBFS (true peak) en el mp4
NOTES = {"C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5, "F#": 6, "GB": 6, "G": 7,
         "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11}


def parse_chord(name: str) -> tuple[int, bool]:
    """'Am' → (9, True); 'F#' → (6, False). Ignora extensiones ('7', 'sus', …)."""
    n = name.strip()
    root = n[:2].upper() if len(n) > 1 and n[1] in "#b" else n[:1].upper()
    if root not in NOTES:
        raise ValueError(f"acorde no reconocido: {name}")
    rest = n[len(root):]
    minor = rest.startswith("m") and not rest.startswith("maj")
    return NOTES[root], minor


def chord_notes(name: str) -> tuple[list[int], int]:
    pc, minor = parse_chord(name)
    r = 48 + pc
    bass = 36 + pc if 36 + pc >= 41 else 48 + pc
    return [r, r + (3 if minor else 4), r + 7], bass


def note(m):
    return 440 * 2 ** ((m - 69) / 12)


class Synth:
    def __init__(self, m: MusicSynth, duration: float):
        self.m, self.D = m, duration
        self.N = int(SR * duration)
        self.L = np.zeros(self.N)
        self.R = np.zeros(self.N)
        self.rng = np.random.default_rng(m.seed)
        self.beat = 60.0 / m.bpm
        self.chords = [chord_notes(c) for c in (m.progression or ["Am"])]

    # ── utilidades
    def env(self, n, a=0.002, d=0.2):
        t = np.arange(n) / SR
        return np.minimum(1, t / a) * np.exp(-t / d)

    def put(self, sig, t, gain=1.0, pan=0.0):
        i = int(round(t * SR))
        if i < 0:
            sig, i = sig[-i:], 0
        j = min(self.N, i + len(sig))
        if i >= self.N or j <= i:
            return
        s = sig[: j - i] * gain
        self.L[i:j] += s * math.sqrt(0.5 * (1 - pan))
        self.R[i:j] += s * math.sqrt(0.5 * (1 + pan))

    @staticmethod
    def filt(x, kind, f, order=2):
        return sosfilt(butter(order, f, kind, fs=SR, output="sos"), x)

    def noise(self, n):
        return self.rng.standard_normal(n)

    def saw(self, f, n, detune=(0,)):
        t = np.arange(n) / SR
        out = np.zeros(n)
        for d in detune:
            out += 2 * ((t * f * 2 ** (d / 1200) + self.rng.random()) % 1) - 1
        return out / len(detune)

    # ── instrumentos
    def kick(self, big=False):
        n = int(0.45 * SR)
        t = np.arange(n) / SR
        f = 48 + (150 if big else 115) * np.exp(-t * 32)
        body = np.sin(2 * np.pi * np.cumsum(f) / SR) * self.env(n, 0.001, 0.32 if big else 0.2)
        click = self.filt(self.noise(n), "highpass", 2500) * self.env(n, 0.0005, 0.006) * 0.35
        return np.tanh((body + click) * 1.6)

    def clap(self):
        n = int(0.3 * SR)
        x = self.filt(self.noise(n), "bandpass", [900, 3500])
        e = np.zeros(n)
        for k, o in enumerate([0, 0.008, 0.017, 0.026]):
            i = int(o * SR)
            e[i:] += self.env(n - i, 0.0005, 0.012 if k < 3 else 0.11)
        tone = np.sin(2 * np.pi * 190 * np.arange(n) / SR) * self.env(n, 0.001, 0.05) * 0.4
        return x * e * 0.9 + tone

    def hat(self, open_=False):
        n = int((0.22 if open_ else 0.06) * SR)
        return self.filt(self.noise(n), "highpass", 7500) * self.env(n, 0.0005, 0.07 if open_ else 0.018)

    # ── arreglo
    def chord_at(self, t):
        return self.chords[int(t // (4 * self.beat)) % len(self.chords)]

    def in_gap(self, t):
        g = self.m.gap
        return g is not None and g[0] <= t < g[1]

    def in_build(self, t):
        return self.m.build is not None and self.m.drop is not None and self.m.build[0] <= t < self.m.drop

    def after_drop(self, t):
        return self.m.drop is not None and t >= self.m.drop

    def render(self) -> np.ndarray:
        m, B, D = self.m, self.beat, self.D
        drop = m.drop
        # batería
        for b in range(int(D / B) + 1):
            t = b * B
            if self.in_gap(t):
                continue
            big = drop is not None and abs(t - drop) < 1e-6
            self.put(self.kick(big), t, 1.05 if self.after_drop(t) else 0.95)
            if b % 2 == 1 and not self.in_build(t):
                self.put(self.clap(), t, 0.55, 0.05)
        for k in range(int(D / (B / 2)) + 1):
            t = k * B / 2
            if not self.in_gap(t):
                self.put(self.hat(k % 2 == 1), t, 0.22 if k % 2 else 0.13, 0.3 if k % 2 else -0.25)
        # redoble acelerando (build)
        if m.build:
            b0, b1 = m.build
            t, step = b0, B / 4
            while t < b1:
                self.put(self.clap(), t, 0.25 + 0.45 * (t - b0) / (b1 - b0))
                t += step
                if t >= b0 + (b1 - b0) * 0.5:
                    step = B / 8
                if t >= b0 + (b1 - b0) * 5 / 6:
                    step = B / 16
        # bajo en contratiempo
        for k in range(int(D / (B / 2)) + 1):
            t = k * B / 2
            if k % 2 == 0 or self.in_gap(t):
                continue
            f = note(self.chord_at(t)[1])
            n = int(0.2 * SR)
            x = self.saw(f, n, (-8, 8)) * self.env(n, 0.003, 0.12)
            x = self.filt(x, "lowpass", 950 if self.after_drop(t) else 700)
            x += 0.6 * np.sin(2 * np.pi * f * np.arange(n) / SR) * self.env(n, 0.003, 0.14)
            self.put(np.tanh(x * 1.4), t, 0.42)
        # stabs sincopados
        for bar in range(int(D / (4 * B)) + 1):
            for rep in (0, 1):
                for o in (0.0, 0.75, 1.5):
                    t = bar * 4 * B + rep * 2 * B + o * B
                    if t >= D or self.in_gap(t):
                        continue
                    n = int(0.24 * SR)
                    x = sum(self.saw(note(p + 12), n, (-14, -5, 5, 14)) for p in self.chord_at(t)[0])
                    if self.after_drop(t):
                        cut = 7000
                    elif self.in_build(t):
                        cut = 2200 + 5000 * (t - m.build[0]) / (drop - m.build[0])
                    else:
                        cut = 2200
                    x = self.filt(x, "lowpass", min(cut, 9000)) * self.env(n, 0.004, 0.09)
                    self.put(x, t, 0.14 if self.after_drop(t) else 0.10, 0.35 if rep else -0.35)
        if drop is not None:
            self._drop(drop)
        # crash de arranque
        n = int(2.2 * SR)
        self.put(self.filt(self.noise(n), "highpass", 4000) * self.env(n, 0.001, 0.6) * 0.08, 0.0)
        for i, t in enumerate(m.pops):
            n = int(0.12 * SR)
            tt = np.arange(n) / SR
            f0 = 500 + 100 * (i % 2)
            sig = np.sin(2 * np.pi * np.cumsum(f0 + (900 + 200 * (i % 2)) * tt / 0.12) / SR) * self.env(n, 0.002, 0.04)
            self.put(sig * (0.25 if i % 2 == 0 else 0.22), t, 1, -0.2 if i % 2 == 0 else 0.2)
        for c in m.whooshes:
            n = int(0.35 * SR)
            tt = np.arange(n) / SR
            w = self.filt(self.noise(n), "bandpass", [800, 6000]) * np.sin(np.pi * tt / 0.35) ** 3
            self.put(w * 0.35, c - 0.2, 1, -0.4)
            self.put(w[::-1] * 0.2, c - 0.2, 1, 0.4)
        return self._room()

    def _drop(self, drop):
        B = self.beat
        # pad largo (acorde de la tonalidad + octava)
        tonic, _ = chord_notes(self.m.key)
        n = int(8 * B * SR)
        pad = sum(self.saw(note(p + 12), n, (-12, 0, 12)) for p in [*tonic, tonic[0] + 12])
        pad = self.filt(pad, "lowpass", 3000) * np.minimum(1, np.arange(n) / (0.05 * SR)) * np.exp(-np.arange(n) / SR / 1.6)
        self.put(pad, drop, 0.07)
        # riser (ruido con pasa-banda abriéndose + tono ascendente) que termina en el drop
        rl = min(3 * B, drop)
        n = int(rl * SR)
        if n > 4800:
            t = np.arange(n) / SR
            nz = self.noise(n)
            ris = np.zeros(n)
            for a in range(0, n, 2400):
                f = 400 + 9000 * (a / n) ** 2
                blk = nz[max(0, a - 2400): a + 2400]
                ris[a:a + 2400] = self.filt(blk, "bandpass", [f * 0.7, min(f * 1.4, 23000)])[-min(2400, n - a):]
            start = drop - rl
            self.put(ris * (t / rl) ** 2 * 0.55, start)
            f = 220 * 2 ** (2.5 * t / rl)
            self.put(np.sin(2 * np.pi * np.cumsum(f) / SR) * (t / rl) ** 3 * 0.12, start)
        # impacto: sub boom + crash
        n = int(2.2 * SR)
        t = np.arange(n) / SR
        boom = np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-t * 10)) / SR) * self.env(n, 0.001, 0.7)
        crash = self.filt(self.noise(n), "highpass", 4000) * self.env(n, 0.001, 0.6)
        self.put(np.tanh(boom * 1.5) * 0.7 + crash * 0.18, drop)

    def _room(self):
        ir_n = int(1.1 * SR)
        ir = self.noise(ir_n) * np.exp(-np.arange(ir_n) / SR / 0.28)
        ir = self.filt(ir, "lowpass", 6000)
        ir /= np.sqrt((ir ** 2).sum())
        wl = fftconvolve(self.L, ir)[: self.N]
        wr = fftconvolve(self.R, ir[::-1] * 0.9 + np.roll(ir, 211) * 0.1)[: self.N]
        st = np.stack([self.L + 0.16 * wl, self.R + 0.16 * wr], 1)
        return np.tanh(st * 1.3) / np.tanh(1.3)  # glue


def load_file(m: MusicFile, duration: float, base: Path) -> np.ndarray:
    path = Path(m.path)
    if not path.is_absolute():
        path = base / path
    if not path.exists():
        raise FileNotFoundError(f"no encuentro la pista de música {path}")
    cmd = [ffmpeg_exe(), "-v", "error", "-ss", str(m.offset), "-t", str(duration), "-i", str(path),
           "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True, creationflags=NO_WINDOW).stdout
    x = np.frombuffer(raw, np.float32).reshape(-1, 2).astype(np.float64)
    n = int(SR * duration)
    if len(x) < n:
        x = np.pad(x, ((0, n - len(x)), (0, 0)))
    return x[:n]


def soft_limit(x, ceiling):
    knee = 0.7 * ceiling
    a = np.abs(x)
    over = a > knee
    y = x.copy()
    y[over] = np.sign(x[over]) * (knee + (ceiling - knee) * np.tanh((a[over] - knee) / (ceiling - knee)))
    return y


def master(st: np.ndarray, target_lufs: float, fade: float) -> np.ndarray:
    n = len(st)
    fi = max(0, n - int(fade * SR))
    env = np.ones(n)
    env[fi:] = np.linspace(1, 0, n - fi) ** 1.5
    st = st * env[:, None]
    target_tp = 10 ** (TRUE_PEAK_DB / 20)
    ceiling = 10 ** (CEILING_DB / 20)
    meter = pyloudnorm.Meter(SR)
    src = st
    for _ in range(6):
        st = src
        for _ in range(3):
            lufs = meter.integrated_loudness(st)
            if not math.isfinite(lufs):
                break
            st = soft_limit(st * 10 ** ((target_lufs - lufs) / 20), ceiling)
        tp = true_peak(st)
        if tp <= target_tp:
            break
        ceiling *= target_tp / tp  # los picos entre muestras superan al de muestra: bajar el techo
    tp = true_peak(st)
    if tp > target_tp:
        st *= target_tp / tp
    return st


def true_peak(x: np.ndarray) -> float:
    """Pico entre muestras (sobremuestreo x4), el que después se nota en el AAC."""
    return float(np.abs(resample_poly(x, 4, 1, axis=0)).max())


def render(spec: Spec, out: Path, base: Path | None = None) -> Path | None:
    m, D = spec.music, spec.format.duration
    if isinstance(m, MusicNone):
        return None
    if isinstance(m, MusicSynth):
        st = Synth(m, D).render()
    else:
        st = load_file(m, D, base or Path.cwd())
    st = master(st, m.target_lufs, m.fade)
    wavfile.write(str(out), SR, st.astype(np.float32))
    return out


def loudness(path: Path) -> tuple[float, float]:
    """(LUFS integrado, pico dBFS) de un wav."""
    sr, x = wavfile.read(str(path))
    x = x.astype(np.float64) / (32768 if x.dtype.kind == "i" else 1)
    return pyloudnorm.Meter(sr).integrated_loudness(x), 20 * math.log10(np.abs(x).max() + 1e-12)
