"""Armado automático sin Claude: plantilla + crudos nuevos + textos nuevos → spec listo.

La plantilla ya trae el estilo aprobado (ritmo de cortes, cámara, animación, música). Acá sólo:
  - se eligen los mejores tramos de los crudos para cada plano (movimiento + nitidez), sin repetir;
  - se reemplazan los textos por los nuevos (una línea vacía se saca);
  - se aplica la marca del cliente (colores, fuentes, pie, oscurecido).
Cero tokens: Claude queda para los cambios que necesitan criterio.
"""
from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

from .analyze import interest_curve
from .probe import probe
from .spec import Spec

RATE = 4.0  # muestras por segundo de la curva de interés


def _safe_center(z: float, cx: float, cy: float, W: int, H: int) -> tuple[float, float]:
    mx, my = W / 2 * (1 - 1 / z), H / 2 * (1 - 1 / z)
    return float(np.clip(cx, W / 2 - mx, W / 2 + mx)), float(np.clip(cy, H / 2 - my, H / 2 + my))


def pick_windows(needs: list[float], curves: dict[str, tuple[np.ndarray, np.ndarray]], durations: dict[str, float]
                 ) -> list[tuple[str, float]]:
    """Para cada largo pedido (segundos del crudo), el mejor tramo (clip, inicio) sin repetir tramos.

    Se elige primero el plano más largo (es el más difícil de ubicar). Se alternan los clips cuando hay
    varios, y lo ya usado se penaliza fuerte para no mostrar dos veces lo mismo.
    """
    used: dict[str, np.ndarray] = {c: np.zeros(len(curves[c][1])) for c in curves}
    count = {c: 0 for c in curves}
    out: list[tuple[str, float] | None] = [None] * len(needs)
    for k in sorted(range(len(needs)), key=lambda i: -needs[i]):
        need = needs[k]
        best = (-1e9, None, 0.0)
        for c, (ts, sc) in curves.items():
            L = max(1, int(round(need * RATE)))
            dur = durations[c]
            last_start = dur - need - 0.05
            if last_start < 0:  # clip más corto que el plano: usarlo entero (se valida después)
                cand = [(float(sc.mean()) - 0.5, 0.0)]
            else:
                cand = []
                for i in range(0, max(1, int(last_start * RATE)) + 1):
                    seg = sc[i:i + L]
                    if len(seg) == 0:
                        continue
                    overlap = used[c][i:i + L].mean()
                    cand.append((float(seg.mean()) - 2.0 * overlap - 0.08 * count[c], i / RATE))
            for score, start in cand:
                if score > best[0]:
                    best = (score, c, start)
        _, c, start = best
        out[k] = (c, round(start, 2))
        i0, L = int(start * RATE), max(1, int(round(need * RATE)))
        used[c][i0:i0 + L] = 1
        count[c] += 1
    return out  # type: ignore[return-value]


def fill(template: dict, clips: list[Path], texts: dict[str, str] | None = None, client: dict | None = None) -> dict:
    """template: spec (dict) de una plantilla. texts: {"<escena>.<línea>": "texto nuevo"}. Devuelve un spec (dict)."""
    spec = copy.deepcopy(template)
    W, H = spec["format"].get("w", 1080), spec["format"].get("h", 1920)
    infos = {c.name: probe(c) for c in clips}
    curves = {c.name: interest_curve(c, RATE) for c in clips}
    durations = {n: i.duration for n, i in infos.items()}

    shots = spec["shots"]
    for s in shots:  # cámara lenta limpia sólo con crudos de 50–60 fps
        s.setdefault("speed", 1.0)
    needs = [(s["t1"] - s["t0"]) * s["speed"] for s in shots]
    picks = pick_windows(needs, curves, durations)
    for s, (clip, start) in zip(shots, picks):
        if s["speed"] < 0.7 and infos[clip].fps < 48:
            s["speed"] = 0.85
        s["clip"] = clip
        need = (s["t1"] - s["t0"]) * s["speed"]
        s["src_in"] = max(0.0, min(start, durations[clip] - need - 0.02))
        if s["src_in"] + need > durations[clip]:  # clip corto: bajar la velocidad para que alcance
            s["speed"] = max(0.3, round((durations[clip] - 0.05) / (s["t1"] - s["t0"]), 3))
            s["src_in"] = 0.0
        zoom = s.get("zoom", [1.0, 1.0])
        # los encuadres de la plantilla eran para otro crudo: se centran (con el mismo recorrido relativo)
        cen = s.get("center", [[W / 2, H / 2], [W / 2, H / 2]])
        dx, dy = cen[1][0] - cen[0][0], cen[1][1] - cen[0][1]
        c0 = _safe_center(zoom[0], W / 2 - dx / 2, H / 2 - dy / 2, W, H)
        c1 = _safe_center(zoom[1], W / 2 + dx / 2, H / 2 + dy / 2, W, H)
        s["center"] = [list(c0), list(c1)]

    for si, sc in enumerate(spec.get("scenes", [])):
        lines = []
        for li, ln in enumerate(sc["lines"]):
            key = f"{si}.{li}"
            if texts is not None and key in texts:
                t = texts[key].strip()
                if not t:
                    continue  # campo vacío: se saca la línea
                old = ln.get("text", "")
                if "*" not in t and len(old) > 2 and old.startswith("*") and old.endswith("*") and old.count("*") == 2:
                    t = f"*{t}*"  # la línea entera iba en acento: se mantiene
                ln["text"] = t
            lines.append(ln)
        sc["lines"] = lines

    if client:
        st = spec.setdefault("style", {})
        for k in ("accent", "text", "display_font", "serif_font", "darken"):
            if client.get(k) not in (None, ""):
                st[k] = client[k]
        if client.get("footer"):
            spec["footer"] = {**(spec["footer"] if isinstance(spec.get("footer"), dict) else {}), "lines": client["footer"]}
        spec["client"] = client.get("slug", spec.get("client", ""))
    Spec.model_validate(spec)
    return spec


def fields(template: dict) -> list[dict]:
    """Campos editables de una plantilla: una por línea de texto, con una etiqueta legible."""
    out = []
    for si, sc in enumerate(template.get("scenes", [])):
        lines = sc.get("lines", [])
        biggest = max((ln.get("size", 0) for ln in lines if ln.get("kind") == "display"), default=0)
        for li, ln in enumerate(lines):
            kind = ln.get("kind")
            if kind == "emoji":
                label = "Emojis"
            elif kind == "serif":
                label = "Frase"
            elif ln.get("size", 0) >= biggest * 0.9:
                label = "Título"
            else:
                label = "Antetítulo" if li == 0 else "Subtítulo"
            out.append({"key": f"{si}.{li}", "escena": si + 1, "label": label, "kind": kind,
                        "ejemplo": ln.get("text", "").replace("*", ""), "texto": ln.get("text", ""),
                        "t0": sc.get("t0"), "t1": sc.get("t1")})
    return out
