"""Efectos de sonido sintetizados (sin licencias) y efectos automáticos según cortes y animaciones de texto.

`spec.sfx` = efectos puntuales que pide Claude ({t, type, gain}). Con `spec.auto_sfx` además se agregan
solos: whoosh en los cortes con látigo, swipe en los flashes, golpe en los zoom punch, teclas en los textos
"maquina", glitch en los "glitch", pops en "pop"/"palabras" y en los emojis.
Los tiempos de las animaciones tienen que coincidir con text_comp/comp.html (STAGGER).
"""
from __future__ import annotations

import math

import numpy as np
from scipy.signal import butter, sosfilt

from .spec import MusicSynth, Spec

SR = 48000
# segundos entre letras/palabras de cada animación (igual que en comp.html)
STAGGER = {"maquina": 0.045, "palabras": 0.16, "pop": 0.05}

SFX_DESC = {
    "whoosh": "barrido de aire (cortes, cambios de escena)",
    "whoosh_corto": "barrido corto y agudo",
    "swipe": "deslizar rápido (transiciones de UI, flash)",
    "pop": "burbuja/pop (aparece algo chico, emojis, palabras)",
    "click": "clic seco (botón, selección)",
    "tick": "tecla de máquina de escribir",
    "glitch": "ruido digital entrecortado",
    "camara": "obturador de cámara de fotos",
    "ding": "campanita (dato importante, precio, novedad)",
    "notificacion": "notificación de celular de dos tonos",
    "impacto": "golpe grave con platillo (drop, revelación)",
    "boom": "golpe grave solo, más corto",
    "riser": "subida de tensión (antes de algo importante)",
    "reversa": "platillo al revés que crece hasta el golpe",
    "caja_registradora": "caja registradora (ofertas, precios, ventas)",
    "burbuja": "burbujas (bebidas, limpieza, algo fresco)",
}


def _filt(x, kind, f, order=2):
    return sosfilt(butter(order, f, kind, fs=SR, output="sos"), x)


def _env(n, a=0.002, d=0.2):
    t = np.arange(n) / SR
    return np.minimum(1, t / a) * np.exp(-t / d)


def _sweep(nz, f0, f1, n):
    """Ruido con un pasabanda que se mueve de f0 a f1 (por bloques)."""
    out = np.zeros(n)
    blk = 1200
    for a in range(0, n, blk):
        f = f0 + (f1 - f0) * (a / n)
        seg = nz[max(0, a - blk): a + blk]
        out[a:a + blk] = _filt(seg, "bandpass", [max(60, f * 0.6), min(f * 1.6, 22000)])[-min(blk, n - a):]
    return out


def synth(kind: str, rng: np.random.Generator, variant: int = 0) -> np.ndarray:
    """Un efecto, mono, pico ~0.5–1."""
    if kind in ("whoosh", "whoosh_corto", "swipe"):
        dur = {"whoosh": 0.35, "whoosh_corto": 0.2, "swipe": 0.14}[kind]
        n = int(dur * SR)
        t = np.arange(n) / SR
        lo, hi = {"whoosh": (500, 5000), "whoosh_corto": (1200, 7000), "swipe": (2500, 10000)}[kind]
        x = _sweep(rng.standard_normal(n), lo, hi, n) * np.sin(np.pi * t / dur) ** 2
        return x / (np.abs(x).max() + 1e-9) * 0.8
    if kind == "pop":
        n = int(0.12 * SR)
        tt = np.arange(n) / SR
        f0 = 500 + 100 * (variant % 2)
        return np.sin(2 * np.pi * np.cumsum(f0 + (900 + 200 * (variant % 2)) * tt / 0.12) / SR) * _env(n, 0.002, 0.04) * 0.3
    if kind == "burbuja":
        n = int(0.6 * SR)
        x = np.zeros(n)
        for k in range(5):
            i = int(rng.uniform(0, 0.45) * SR)
            m = int(0.07 * SR)
            tt = np.arange(m) / SR
            f = rng.uniform(600, 1400)
            x[i:i + m] += np.sin(2 * np.pi * np.cumsum(f + 1500 * tt / 0.07) / SR) * _env(m, 0.002, 0.02)
        return x * 0.4
    if kind in ("click", "tick"):
        n = int((0.03 if kind == "click" else 0.05) * SR)
        x = _filt(rng.standard_normal(n), "bandpass", [1800, 7000] if kind == "click" else [900, 5000]) * _env(n, 0.0003, 0.006)
        if kind == "tick":  # cuerpo de la tecla
            x += np.sin(2 * np.pi * (180 + 40 * (variant % 3)) * np.arange(n) / SR) * _env(n, 0.0005, 0.012) * 0.6
        return x / (np.abs(x).max() + 1e-9) * (0.5 if kind == "click" else 0.35)
    if kind == "glitch":
        n = int(0.4 * SR)
        x = np.zeros(n)
        pos = 0
        while pos < n:
            seg = int(rng.uniform(0.01, 0.05) * SR)
            if rng.random() < 0.65:
                f = rng.choice([220, 440, 880, 1320, 3520])
                tone = np.sign(np.sin(2 * np.pi * f * np.arange(seg) / SR))  # onda cuadrada
                nz = rng.standard_normal(seg)
                x[pos:pos + seg] = (tone * 0.5 + nz * 0.5)[: n - pos]
            pos += seg
        x = np.round(x * 6) / 6  # "bitcrush"
        return x * np.linspace(1, 0.4, n) * 0.35
    if kind == "camara":
        n = int(0.25 * SR)
        x = np.zeros(n)
        for o, g in ((0.0, 1.0), (0.09, 0.7)):
            i = int(o * SR)
            m = int(0.05 * SR)
            x[i:i + m] += _filt(rng.standard_normal(m), "bandpass", [1500, 9000]) * _env(m, 0.0005, 0.01) * g
        return x / (np.abs(x).max() + 1e-9) * 0.6
    if kind in ("ding", "notificacion"):
        tones = [(1568, 0.0)] if kind == "ding" else [(1047, 0.0), (1568, 0.11)]
        n = int(1.2 * SR)
        x = np.zeros(n)
        for f, o in tones:
            i = int(o * SR)
            m = n - i
            tt = np.arange(m) / SR
            x[i:] += (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * f * 2.76 * tt) * np.exp(-tt * 6)) * _env(m, 0.001, 0.35)
        return x / (np.abs(x).max() + 1e-9) * 0.45
    if kind in ("impacto", "boom"):
        n = int((2.2 if kind == "impacto" else 0.9) * SR)
        t = np.arange(n) / SR
        boom = np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-t * 10)) / SR) * _env(n, 0.001, 0.7 if kind == "impacto" else 0.3)
        x = np.tanh(boom * 1.5) * 0.8
        if kind == "impacto":
            x += _filt(rng.standard_normal(n), "highpass", 4000) * _env(n, 0.001, 0.6) * 0.2
        return x / (np.abs(x).max() + 1e-9) * 0.9
    if kind in ("riser", "reversa"):
        dur = 1.5
        n = int(dur * SR)
        t = np.arange(n) / SR
        if kind == "riser":
            x = _sweep(rng.standard_normal(n), 300, 9000, n) * (t / dur) ** 2
        else:  # platillo al revés
            x = (_filt(rng.standard_normal(n), "highpass", 3500) * np.exp(-(dur - t) / 0.45))
        return x / (np.abs(x).max() + 1e-9) * 0.6
    if kind == "caja_registradora":
        n = int(1.0 * SR)
        x = np.zeros(n)
        m = int(0.08 * SR)  # mecanismo
        x[:m] += _filt(rng.standard_normal(m), "bandpass", [800, 4000]) * _env(m, 0.0005, 0.015)
        i = int(0.1 * SR)
        tt = np.arange(n - i) / SR
        for f in (2637, 3136, 3951):  # campanita
            x[i:] += np.sin(2 * np.pi * f * tt) * _env(n - i, 0.001, 0.3) * 0.35
        return x / (np.abs(x).max() + 1e-9) * 0.5
    raise ValueError(f"efecto de sonido desconocido: {kind}")


def events(spec: Spec) -> list[tuple[float, str, float, float]]:
    """(t, tipo, ganancia, paneo) de todos los efectos: los del spec + los automáticos."""
    ev = [(s.t, s.type, s.gain, 0.0) for s in spec.sfx]
    if not spec.auto_sfx:
        return sorted(ev)
    m = spec.music
    legacy_whoosh = list(m.whooshes) if isinstance(m, MusicSynth) else []
    legacy_pops = bool(m.pops) if isinstance(m, MusicSynth) else False
    near = lambda t, lst, tol=0.3: any(abs(t - x) < tol for x in lst)  # noqa: E731
    explicit = [s.t for s in spec.sfx]
    for s in spec.shots[1:]:
        if s.transition_in == "whip" and not near(s.t0, legacy_whoosh) and not near(s.t0 - 0.2, explicit):
            ev.append((s.t0 - 0.2, "whoosh", 0.9, -0.3))
        elif s.transition_in == "flash" and not near(s.t0, explicit):
            ev.append((s.t0 - 0.07, "swipe", 0.8, 0.2))
        elif s.transition_in == "zoom_punch" and not near(s.t0, explicit):
            ev.append((s.t0, "boom", 0.5, 0.0))
    st = spec.style
    default_anim = {"display": st.display_anim, "serif": st.serif_anim, "script": st.script_anim}
    for sc in spec.scenes:
        for ln in sc.lines:
            anim = ln.anim or default_anim.get(ln.kind)
            t0 = sc.t0 + ln.delay
            if t0 >= sc.t1:
                continue
            text = ln.text.replace("*", "")
            if ln.kind == "emoji":
                if not legacy_pops:
                    for i, _ in enumerate(text.replace(" ", "")[:4]):
                        ev.append((t0 + i * 0.14, "pop", 0.8, -0.2 if i % 2 == 0 else 0.2))
                continue
            if anim == "maquina":
                k = 0
                for ch in text:
                    if ch != " ":
                        t = t0 + k * STAGGER["maquina"]
                        if t < sc.t1:
                            ev.append((t, "tick", 0.55, ((k * 37) % 7 - 3) / 10))
                    k += 1
            elif anim == "glitch":
                ev.append((t0, "glitch", 0.7, 0.0))
            elif anim in ("palabras", "pop"):
                words = text.split()
                step = STAGGER["palabras"] if anim == "palabras" else STAGGER["pop"] * max(1, len(text) // max(1, len(words)))
                for i, _ in enumerate(words[:8]):
                    ev.append((t0 + i * step, "pop", 0.45, 0.25 * math.sin(i)))
    return sorted(e for e in ev if 0 <= e[0] < spec.format.duration)


def render(ev: list[tuple[float, str, float, float]], duration: float, rng: np.random.Generator) -> np.ndarray:
    n = int(SR * duration)
    out = np.zeros((n, 2))
    for k, (t, kind, gain, pan) in enumerate(ev):
        x = synth(kind, rng, variant=k) * gain
        i = int(round(t * SR))
        if i < 0:
            x, i = x[-i:], 0
        j = min(n, i + len(x))
        if j <= i:
            continue
        out[i:j, 0] += x[: j - i] * math.sqrt(0.5 * (1 - pan))
        out[i:j, 1] += x[: j - i] * math.sqrt(0.5 * (1 + pan))
    return out
