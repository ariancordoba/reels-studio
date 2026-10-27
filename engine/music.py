"""Música: generador sintetizado por géneros (sin licencias de terceros) o pista subida con licencia.

Cada género define tempo, progresión típica, patrones de batería de 16 pasos por compás, bajo, instrumento
de acordes y extras (vinilo, braam…). Sobre eso, igual para todos: build con redoble + riser, hueco de
silencio y drop con impacto. Los efectos de sonido (engine/sfx.py) se mezclan antes del master.
Master: normalizado a target_lufs con true peak ≤ −3.5 dBFS (el AAC sube los picos).
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
QUALITIES = [  # sufijo → intervalos (se prueba en este orden)
    ("maj7", [0, 4, 7, 11]), ("m7", [0, 3, 7, 10]), ("add9", [0, 4, 7, 14]), ("sus2", [0, 2, 7]),
    ("sus4", [0, 5, 7]), ("dim", [0, 3, 6]), ("m", [0, 3, 7]), ("7", [0, 4, 7, 10]), ("", [0, 4, 7]),
]

# ── géneros. Patrones: 16 pasos por compás; "x" golpe fuerte, "o" golpe suave, "." nada.
GENRES: dict[str, dict] = {
    "house": {
        "bpm": 120, "prog": ["Am", "F", "C", "G"], "kick": "house",
        "kick_p": "x...x...x...x...", "clap_p": "....x.......x...", "hat_p": "..x...x...x...x.", "ohat": True,
        "bass": "saw_offbeat", "chords": "stab", "desc": "energético de club, 4x4",
    },
    "pop": {
        "bpm": 116, "prog": ["C", "G", "Am", "F"], "kick": "soft",
        "kick_p": "x.......x.x.....", "snare_p": "....x.......x...", "hat_p": "x.o.x.o.x.o.x.o.",
        "bass": "pluck", "chords": "pluck_arp", "pad": True, "desc": "alegre y luminoso, para casi todo",
    },
    "trap": {
        "bpm": 140, "prog": ["Am", "Am", "F", "E"], "kick": "808",
        "kick_p": "x.....x...x.....", "snare_p": "........x.......", "hat_p": "x.x.x.xxx.x.x.xx",
        "bass": "808", "chords": "bells", "desc": "urbano, oscuro, hi-hats rápidos y 808",
    },
    "reggaeton": {
        "bpm": 95, "prog": ["Am", "F", "C", "G"], "kick": "808",
        "kick_p": "x...x...x...x...", "snare_p": "...x..x....x..x.", "hat_p": "x.x.x.x.x.x.x.x.",
        "bass": "808", "chords": "pluck_arp", "desc": "dembow, perreo, fiesta",
    },
    "lofi": {
        "bpm": 80, "prog": ["Fmaj7", "Em7", "Dm7", "Cmaj7"], "kick": "soft", "swing": 0.22,
        "kick_p": "x......x..x.....", "snare_p": "....x.......x...", "hat_p": "x.o.x.o.x.o.x.o.",
        "bass": "sine", "chords": "keys", "vinyl": True, "lowpass": 5500, "desc": "relajado, cálido, café y estudio",
    },
    "cinematico": {
        "bpm": 90, "prog": ["Dm", "Bb", "F", "C"], "kick": "boom",
        "kick_p": "x.......x.......", "tom_p": "......x.......xx", "hat_p": "................",
        "bass": "sine", "chords": "pad", "braam": True, "desc": "épico, tráiler, lanzamientos importantes",
    },
    "corporativo": {
        "bpm": 110, "prog": ["C", "Am", "F", "G"], "kick": "soft",
        "kick_p": "x...x...x...x...", "clap_p": "....x.......x...", "shaker_p": "xoxoxoxoxoxoxoxo",
        "bass": "sine", "chords": "piano_arp", "pad": True, "desc": "inspirador y prolijo, empresas y servicios",
    },
    "funk": {
        "bpm": 108, "prog": ["Em7", "A7"], "kick": "house",
        "kick_p": "x..x..x...x.....", "snare_p": "....x.......x...", "hat_p": "xoxoxoxoxoxoxoxo",
        "bass": "funk", "chords": "keys_stab", "desc": "groove con onda, moda, gastronomía, retro",
    },
    "ambient": {
        "bpm": 70, "prog": ["Cmaj7", "Fmaj7", "Am7", "G"], "kick": None,
        "kick_p": "................", "hat_p": "................",
        "bass": None, "chords": "pad", "sparkle": True, "desc": "suave y etéreo, bienestar, spa, inmobiliaria",
    },
}


def parse_chord(name: str) -> tuple[int, bool]:
    """'Am' → (9, True); 'F#' → (6, False)."""
    pc, iv = parse_chord_full(name)
    return pc, iv[1] == 3


def parse_chord_full(name: str) -> tuple[int, list[int]]:
    n = name.strip()
    root = n[:2].upper() if len(n) > 1 and n[1] in "#b" else n[:1].upper()
    if root not in NOTES:
        raise ValueError(f"acorde no reconocido: {name}")
    rest = n[len(root):]
    for suf, iv in QUALITIES:
        if rest.startswith(suf):
            return NOTES[root], iv
    return NOTES[root], [0, 4, 7]


def chord_notes(name: str) -> tuple[list[int], int]:
    pc, iv = parse_chord_full(name)
    r = 48 + pc
    bass = 36 + pc if 36 + pc >= 41 else 48 + pc
    return [r + i for i in iv], bass


def note(m):
    return 440 * 2 ** ((m - 69) / 12)


class Synth:
    def __init__(self, m: MusicSynth, duration: float):
        self.m, self.D = m, duration
        self.g = GENRES[m.genre]
        self.N = int(SR * duration)
        self.L = np.zeros(self.N)
        self.R = np.zeros(self.N)
        self.rng = np.random.default_rng(m.seed)
        self.bpm = m.bpm or self.g["bpm"]
        self.beat = 60.0 / self.bpm
        self.chords = [chord_notes(c) for c in (m.progression or self.g["prog"])]

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

    def sine(self, f, n, phase_rand=True):
        return np.sin(2 * np.pi * f * np.arange(n) / SR + (self.rng.random() * 6.28 if phase_rand else 0))

    # ── batería
    def kick(self, big=False, kind="house"):
        if kind == "808":
            return self.k808(note(self.chord_at(0)[1]), 0.9 if big else 0.6)
        if kind == "boom":
            n = int(1.4 * SR)
            t = np.arange(n) / SR
            f = 40 + 70 * np.exp(-t * 12)
            body = np.sin(2 * np.pi * np.cumsum(f) / SR) * self.env(n, 0.002, 0.6)
            return np.tanh(body * 1.8) + self.filt(self.noise(n), "lowpass", 900) * self.env(n, 0.001, 0.08) * 0.4
        soft = kind == "soft"
        n = int(0.45 * SR)
        t = np.arange(n) / SR
        f = 48 + (150 if big else (90 if soft else 115)) * np.exp(-t * (26 if soft else 32))
        body = np.sin(2 * np.pi * np.cumsum(f) / SR) * self.env(n, 0.001, 0.32 if big else (0.16 if soft else 0.2))
        click = self.filt(self.noise(n), "highpass", 2500) * self.env(n, 0.0005, 0.006) * (0.15 if soft else 0.35)
        return np.tanh((body + click) * (1.2 if soft else 1.6))

    def k808(self, f, dur=0.6, glide_from=None):
        n = int(dur * SR)
        t = np.arange(n) / SR
        f0 = glide_from or f * 2.2
        fr = f + (f0 - f) * np.exp(-t * 30)
        body = np.sin(2 * np.pi * np.cumsum(fr) / SR) * self.env(n, 0.002, dur * 0.7)
        click = self.filt(self.noise(n), "highpass", 3000) * self.env(n, 0.0005, 0.004) * 0.3
        return np.tanh((body + click) * 1.4)

    def clap(self):
        n = int(0.3 * SR)
        x = self.filt(self.noise(n), "bandpass", [900, 3500])
        e = np.zeros(n)
        for k, o in enumerate([0, 0.008, 0.017, 0.026]):
            i = int(o * SR)
            e[i:] += self.env(n - i, 0.0005, 0.012 if k < 3 else 0.11)
        tone = np.sin(2 * np.pi * 190 * np.arange(n) / SR) * self.env(n, 0.001, 0.05) * 0.4
        return x * e * 0.9 + tone

    def snare(self):
        n = int(0.3 * SR)
        nz = self.filt(self.noise(n), "bandpass", [1500, 8000]) * self.env(n, 0.0005, 0.09)
        tone = np.sin(2 * np.pi * np.cumsum(220 * np.exp(-np.arange(n) / SR * 8) + 160) / SR) * self.env(n, 0.001, 0.06)
        return nz * 0.8 + tone * 0.6

    def hat(self, open_=False):
        n = int((0.22 if open_ else 0.06) * SR)
        return self.filt(self.noise(n), "highpass", 7500) * self.env(n, 0.0005, 0.07 if open_ else 0.018)

    def shaker(self):
        n = int(0.07 * SR)
        e = np.minimum(1, np.arange(n) / (0.012 * SR)) * np.exp(-np.arange(n) / SR / 0.02)
        return self.filt(self.noise(n), "bandpass", [5000, 11000]) * e

    def tom(self, f=110):
        n = int(0.5 * SR)
        t = np.arange(n) / SR
        return np.sin(2 * np.pi * np.cumsum(f * (1 + 0.6 * np.exp(-t * 20))) / SR) * self.env(n, 0.001, 0.22)

    # ── instrumentos con altura
    def keys(self, f, n):
        """Tipo Rhodes: fundamental + armónicos suaves, trémolo."""
        t = np.arange(n) / SR
        x = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 6)
             + 0.12 * np.sin(2 * np.pi * 3.01 * f * t) * np.exp(-t * 9))
        return x * (1 + 0.15 * np.sin(2 * np.pi * 5 * t))

    def piano(self, f, n):
        t = np.arange(n) / SR
        x = sum(a * np.sin(2 * np.pi * f * k * (1 + 0.0004 * k * k) * t) * np.exp(-t * (1.6 + 1.2 * k))
                for k, a in enumerate([1, 0.5, 0.3, 0.18, 0.1], start=1))
        return x * self.env(n, 0.002, 2.0)

    def pluck(self, f, n, bright=3500):
        x = self.saw(f, n, (-6, 6))
        return self.filt(x, "lowpass", bright) * self.env(n, 0.002, 0.12)

    def bell(self, f, n):
        t = np.arange(n) / SR
        return (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 4)) * self.env(n, 0.001, 0.5)

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

    def steps(self, pattern: str | None):
        """(t, fuerte) de cada golpe del patrón a lo largo del tema (con swing en las semicorcheas impares)."""
        if not pattern:
            return
        sw = self.g.get("swing", 0.0) * self.beat / 4
        n_bars = int(self.D / (4 * self.beat)) + 1
        for bar in range(n_bars):
            for s, ch in enumerate(pattern):
                if ch == ".":
                    continue
                t = (bar * 16 + s) * self.beat / 4 + (sw if s % 2 else 0)
                if t < self.D and not self.in_gap(t):
                    yield t, ch == "x"

    def render(self) -> np.ndarray:
        g, B, m = self.g, self.beat, self.m
        drop = m.drop
        # batería
        if g.get("kick"):
            for t, strong in self.steps(g["kick_p"]):
                big = drop is not None and abs(t - drop) < 1e-6
                if g["kick"] == "808":
                    if g["bass"] == "808":
                        continue  # el 808 hace de bombo y bajo a la vez (más abajo, con la nota del acorde)
                self.put(self.kick(big, g["kick"]), t, (1.05 if self.after_drop(t) else 0.95) * (1 if strong else 0.6))
        for t, strong in self.steps(g.get("clap_p")):
            if not self.in_build(t):
                self.put(self.clap(), t, 0.55 if strong else 0.3, 0.05)
        for t, strong in self.steps(g.get("snare_p")):
            if not self.in_build(t):
                self.put(self.snare(), t, 0.5 if strong else 0.25, 0.03)
        for k, (t, strong) in enumerate(self.steps(g.get("hat_p"))):
            open_ = g.get("ohat") and k % 2 == 1
            self.put(self.hat(open_), t, (0.2 if open_ else 0.13) * (1 if strong else 0.6), 0.3 if k % 2 else -0.25)
        if g.get("hat_p") and g["kick"] == "808":  # trap/reggaetón: redobles de hats (rolls) al final de cada compás
            for bar in range(int(self.D / (4 * B)) + 1):
                t0 = (bar + 1) * 4 * B - B / 2
                for r in range(6):
                    t = t0 + r * B / 12
                    if t < self.D and not self.in_gap(t):
                        self.put(self.hat(), t, 0.08 + 0.01 * r, 0.3)
        for t, strong in self.steps(g.get("shaker_p")):
            self.put(self.shaker(), t, 0.16 if strong else 0.09, -0.3)
        for t, strong in self.steps(g.get("tom_p")):
            self.put(self.tom(100 if strong else 130), t, 0.4, 0.2)
        # redoble que acelera (build)
        if m.build:
            b0, b1 = m.build
            t, step = b0, B / 4
            hit = self.clap if g.get("clap_p") else self.snare
            while t < b1:
                self.put(hit(), t, 0.25 + 0.45 * (t - b0) / (b1 - b0))
                t += step
                if t >= b0 + (b1 - b0) * 0.5:
                    step = B / 8
                if t >= b0 + (b1 - b0) * 5 / 6:
                    step = B / 16
        self._bass()
        self._chords()
        if g.get("pad"):
            self._pad(0.035)
        if g.get("sparkle"):
            for k in range(int(self.D / (B / 2))):
                t = k * B / 2
                if self.rng.random() < 0.45 and not self.in_gap(t):
                    notes = self.chord_at(t)[0]
                    self.put(self.bell(note(notes[k % len(notes)] + 24), int(0.6 * SR)), t, 0.05, self.rng.uniform(-0.6, 0.6))
        if g.get("vinyl"):
            self._vinyl()
        if drop is not None:
            self._drop(drop)
        # crash de arranque
        n = int(2.2 * SR)
        self.put(self.filt(self.noise(n), "highpass", 4000) * self.env(n, 0.001, 0.6) * 0.08, 0.0)
        # compatibilidad: pops y whooshes que vienen en music (ahora también están en spec.sfx)
        from .sfx import synth as sfx_synth

        for i, t in enumerate(m.pops):
            self.put(sfx_synth("pop", self.rng, variant=i), t, 0.9, -0.2 if i % 2 == 0 else 0.2)
        for c in m.whooshes:
            w = sfx_synth("whoosh", self.rng)
            self.put(w, c - 0.2, 1, -0.4)
            self.put(w[::-1] * 0.55, c - 0.2, 1, 0.4)
        st = self._room()
        if g.get("lowpass"):
            st = np.stack([self.filt(st[:, 0], "lowpass", g["lowpass"]), self.filt(st[:, 1], "lowpass", g["lowpass"])], 1)
        return st

    def _bass(self):
        g, B = self.g, self.beat
        kind = g.get("bass")
        if not kind:
            return
        if kind == "saw_offbeat":  # house: contratiempo en corcheas
            for k in range(int(self.D / (B / 2)) + 1):
                t = k * B / 2
                if k % 2 == 0 or self.in_gap(t):
                    continue
                f = note(self.chord_at(t)[1])
                n = int(0.2 * SR)
                x = self.saw(f, n, (-8, 8)) * self.env(n, 0.003, 0.12)
                x = self.filt(x, "lowpass", 950 if self.after_drop(t) else 700)
                x += 0.6 * np.sin(2 * np.pi * f * np.arange(n) / SR) * self.env(n, 0.003, 0.14)
                self.put(np.tanh(x * 1.4), t, 0.42)
        elif kind == "808":  # bombo-bajo afinado a la nota del acorde, con glide
            prev = None
            for t, strong in self.steps(g["kick_p"]):
                f = note(self.chord_at(t)[1] - 12)
                big = self.m.drop is not None and abs(t - self.m.drop) < 1e-6
                self.put(self.k808(f, 0.9 if big else 0.55, glide_from=prev * 1.0 if prev and prev != f else None),
                         t, 0.75 if strong else 0.5)
                prev = f
        elif kind == "pluck":
            for k in range(int(self.D / (B / 2)) + 1):
                t = k * B / 2
                if not self.in_gap(t) and k % 4 in (0, 3):
                    f = note(self.chord_at(t)[1])
                    self.put(self.pluck(f, int(0.25 * SR), 900), t, 0.4)
        elif kind == "funk":  # bajo sincopado con saltos de octava
            pat = "x..x.xx...x.x..x"
            octs = [0, 0, 12, 0, 7, 12, 0, 0]
            for k, (t, _) in enumerate(self.steps(pat)):
                f = note(self.chord_at(t)[1] + octs[k % len(octs)])
                n = int(0.16 * SR)
                x = self.saw(f, n) * self.env(n, 0.002, 0.08)
                self.put(np.tanh(self.filt(x, "lowpass", 1400) * 2), t, 0.45)
        elif kind == "sine":  # bajo redondo, nota por medio compás
            for k in range(int(self.D / (2 * B)) + 1):
                t = k * 2 * B
                if self.in_gap(t):
                    continue
                f = note(self.chord_at(t)[1])
                n = int(2 * B * SR)
                x = np.sin(2 * np.pi * f * np.arange(n) / SR) * np.minimum(1, np.arange(n) / (0.02 * SR)) * np.exp(-np.arange(n) / SR / 1.2)
                self.put(x, t, 0.4)

    def _chords(self):
        g, B, m = self.g, self.beat, self.m
        kind = g.get("chords")
        D = self.D

        def cutoff(t):
            if self.after_drop(t):
                return 7000
            if self.in_build(t):
                return 2200 + 5000 * (t - m.build[0]) / (m.drop - m.build[0])
            return 2200

        if kind == "stab":  # house: supersaw corta sincopada
            for bar in range(int(D / (4 * B)) + 1):
                for rep in (0, 1):
                    for o in (0.0, 0.75, 1.5):
                        t = bar * 4 * B + rep * 2 * B + o * B
                        if t >= D or self.in_gap(t):
                            continue
                        n = int(0.24 * SR)
                        x = sum(self.saw(note(p + 12), n, (-14, -5, 5, 14)) for p in self.chord_at(t)[0][:3])
                        x = self.filt(x, "lowpass", min(cutoff(t), 9000)) * self.env(n, 0.004, 0.09)
                        self.put(x, t, 0.14 if self.after_drop(t) else 0.10, 0.35 if rep else -0.35)
        elif kind in ("pluck_arp", "piano_arp", "bells"):
            step = B / 2 if kind != "bells" else B
            for k in range(int(D / step) + 1):
                t = k * step
                if t >= D or self.in_gap(t):
                    continue
                notes = self.chord_at(t)[0]
                p = notes[[0, 1, 2, 1, 3 % len(notes), 2, 1, 2][k % 8] % len(notes)] + 12
                if kind == "pluck_arp":
                    self.put(self.pluck(note(p), int(0.3 * SR), min(cutoff(t) + 1000, 8000)), t, 0.12, 0.3 * math.sin(k))
                elif kind == "piano_arp":
                    self.put(self.piano(note(p), int(1.2 * SR)), t, 0.09, 0.25 * math.sin(k))
                else:
                    self.put(self.bell(note(p + 12), int(0.8 * SR)), t, 0.07, 0.4 * math.sin(k))
        elif kind in ("keys", "keys_stab"):
            hold = 2 * B if kind == "keys" else B / 2
            pat = (0.0, 2.0) if kind == "keys" else (0.5, 1.25, 2.5, 3.25)
            for bar in range(int(D / (4 * B)) + 1):
                for o in pat:
                    t = bar * 4 * B + o * B
                    if t >= D or self.in_gap(t):
                        continue
                    n = int(hold * SR)
                    x = sum(self.keys(note(p + 12), n) for p in self.chord_at(t)[0]) * self.env(n, 0.005, hold * 0.8)
                    self.put(x, t, 0.06 if kind == "keys" else 0.07, -0.15)
        elif kind == "pad":
            self._pad(0.06)

    def _pad(self, gain):
        B, D = self.beat, self.D
        for bar in range(int(D / (4 * B)) + 1):
            t = bar * 4 * B
            if t >= D or self.in_gap(t):
                continue
            n = int(min(4 * B + 0.5, D - t + 0.5) * SR)
            x = sum(self.saw(note(p + 12), n, (-10, 0, 10)) for p in self.chord_at(t)[0])
            a = np.minimum(1, np.arange(n) / (0.6 * SR)) * np.minimum(1, (n - np.arange(n)) / (0.4 * SR))
            self.put(self.filt(x, "lowpass", 1800) * a, t, gain, 0.0)

    def _vinyl(self):
        n = self.N
        crackle = np.zeros(n)
        idx = self.rng.integers(0, n, size=int(self.D * 18))
        crackle[idx] = self.rng.uniform(-1, 1, size=len(idx))
        crackle = self.filt(crackle, "bandpass", [1000, 8000])
        hiss = self.filt(self.noise(n), "bandpass", [2000, 9000]) * 0.04
        self.put(crackle * 0.25 + hiss, 0.0, 0.5)

    def _drop(self, drop):
        B = self.beat
        tonic, _ = chord_notes(self.m.key)
        n = int(8 * B * SR)
        pad = sum(self.saw(note(p + 12), n, (-12, 0, 12)) for p in [*tonic[:3], tonic[0] + 12])
        pad = self.filt(pad, "lowpass", 3000) * np.minimum(1, np.arange(n) / (0.05 * SR)) * np.exp(-np.arange(n) / SR / 1.6)
        self.put(pad, drop, 0.07)
        if self.g.get("braam"):  # cinematográfico: "braam" de metales graves
            n = int(2.5 * SR)
            t = np.arange(n) / SR
            x = sum(self.saw(note(p - 12), n, (-15, 0, 15)) for p in (tonic[0], tonic[0] + 7, tonic[0] + 12))
            sweep = np.zeros(n)
            for a in range(0, n, 4800):  # filtro que se abre y se vuelve a cerrar
                f = 300 + 2200 * np.sin(np.pi * min(1, a / n)) ** 0.5
                blk = x[a:a + 4800]
                sweep[a:a + len(blk)] = self.filt(blk, "lowpass", f)
            self.put(np.tanh(sweep * 1.5) * np.minimum(1, t / 0.03) * np.exp(-t / 1.8), drop, 0.22)
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
        n = int(2.2 * SR)
        t = np.arange(n) / SR
        boom = np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-t * 10)) / SR) * self.env(n, 0.001, 0.7)
        crash = self.filt(self.noise(n), "highpass", 4000) * self.env(n, 0.001, 0.6)
        self.put(np.tanh(boom * 1.5) * 0.7 + crash * 0.18, drop)

    def _room(self):
        ir_n = int(1.1 * SR)
        ir = self.noise(ir_n) * np.exp(-np.arange(ir_n) / SR / (0.45 if self.m.genre in ("ambient", "cinematico") else 0.28))
        ir = self.filt(ir, "lowpass", 6000)
        ir /= np.sqrt((ir ** 2).sum())
        wet = 0.3 if self.m.genre in ("ambient", "cinematico") else 0.16
        wl = fftconvolve(self.L, ir)[: self.N]
        wr = fftconvolve(self.R, ir[::-1] * 0.9 + np.roll(ir, 211) * 0.1)[: self.N]
        st = np.stack([self.L + wet * wl, self.R + wet * wr], 1)
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
    """Música + efectos de sonido → wav. None si el video no lleva audio."""
    from . import sfx

    m, D = spec.music, spec.format.duration
    events = sfx.events(spec)
    if isinstance(m, MusicNone) and not events:
        return None
    rng = np.random.default_rng(getattr(m, "seed", 7))
    if isinstance(m, MusicSynth):
        st = Synth(m, D).render()
    elif isinstance(m, MusicFile):
        st = load_file(m, D, base or Path.cwd())
    else:
        st = np.zeros((int(SR * D), 2))
    music_level = float(np.sqrt((st ** 2).mean())) if st.any() else 0.0
    fx = sfx.render(events, D, rng)
    if isinstance(m, MusicNone):  # sólo efectos: nivel fijo, sin "subir" el silencio
        st = fx * 0.5
        tp = true_peak(st)
        if tp > 10 ** (TRUE_PEAK_DB / 20):
            st *= 10 ** (TRUE_PEAK_DB / 20) / tp
    else:
        # los efectos van a un nivel relativo a la música (antes del master, que normaliza todo junto)
        st = st + fx * max(music_level, 0.05) * 2.2
        st = master(st, m.target_lufs, m.fade)
    wavfile.write(str(out), SR, st.astype(np.float32))
    return out


def loudness(path: Path) -> tuple[float, float]:
    """(LUFS integrado, pico dBFS) de un wav."""
    sr, x = wavfile.read(str(path))
    x = x.astype(np.float64) / (32768 if x.dtype.kind == "i" else 1)
    return pyloudnorm.Meter(sr).integrated_loudness(x), 20 * math.log10(np.abs(x).max() + 1e-12)
