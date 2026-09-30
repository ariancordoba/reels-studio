"""Spec de un video: el contrato entre Claude, la UI y el motor. Todo el video sale de acá.

Validación en dos pasos:
  - estructural (pydantic, al cargar): tipos, rangos, planos sin huecos;
  - contra los archivos (`check`): largo de los clips, cortes fuera de la grilla de beats.
Los errores salen en español para que Claude (o la UI) los pueda mostrar tal cual.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

EPS = 1e-6
# textos de relleno que nunca pueden llegar a un video ("acá va la frase clave", "[TÍTULO]", "lorem ipsum"…)
PLACEHOLDER = re.compile(
    r"\bac[aá] va\b|\baqu[ií] va\b|\bva ac[aá]\b|\btexto (de )?(ejemplo|aqu[ií]|ac[aá])\b|\blorem\b|\bipsum\b|"
    r"\bplaceholder\b|\bfrase clave\b|\bTBD\b|\bxxx+\b|\[[^\]]*\]|\{[^}]*\}|<[^>]*>", re.I)


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Format(_M):
    w: int = 1080
    h: int = 1920
    fps: int = Field(30, ge=12, le=60)
    duration: float = Field(gt=0, le=180)


class Style(_M):
    accent: str = "#caffbf"
    text: str = "#ffffff"
    text_shadow: str = "0 4px 18px rgba(0,20,50,.35)"
    display_font: str = "Archivo"
    display_stretch: float = 125
    display_weight: int = 900
    serif_font: str = "Playfair"
    serif_weight: int = 400
    darken: float = Field(0.32, ge=0, le=0.9)
    top_gradient: float = Field(0.20, ge=0, le=1)
    bottom_gradient: float = Field(0.35, ge=0, le=1)
    contrast: float = Field(1.10, ge=0.5, le=2)
    saturation: float = Field(1.18, ge=0, le=2.5)
    vignette: float = Field(0.28, ge=0, le=1)


Transition = Literal["cut", "whip", "flash", "zoom_punch"]


class Shot(_M):
    clip: str
    t0: float = Field(ge=0)
    t1: float
    src_in: float = Field(0.0, ge=0)
    speed: float = Field(1.0, gt=0.05, le=4)
    zoom: tuple[float, float] = (1.0, 1.0)
    center: tuple[tuple[float, float], tuple[float, float]] = ((540, 960), (540, 960))
    transition_in: Transition = "cut"
    handheld: float | None = None  # sobreescribe camera.handheld en este plano

    @model_validator(mode="after")
    def _t(self):
        if self.t1 <= self.t0:
            raise ValueError(f"plano {self.clip}: t1 ({self.t1}) tiene que ser mayor que t0 ({self.t0})")
        if min(self.zoom) < 1.0:
            raise ValueError(f"plano {self.clip} en {self.t0}s: zoom menor a 1 deja bordes vacíos (mínimo 1.0)")
        return self

    @property
    def src_out(self) -> float:
        return self.src_in + (self.t1 - self.t0) * self.speed


class Shake(_M):
    t: float
    amp: float = 20


class Camera(_M):
    beat_punch: float = 0.018
    entry_punch: float = 0.10
    handheld: float = 5
    shakes: list[Shake] = []


class Effect(_M):
    type: Literal["flash", "fade_out", "fade_in"]
    t: float
    dur: float | None = None
    strength: float = 0.85


class Line(_M):
    kind: Literal["display", "serif", "emoji"]
    text: str = Field(min_length=1)
    size: float = Field(gt=4, le=400)
    y: float
    delay: float = 0.0
    spacing: str | None = None
    color: str | None = None


class Scene(_M):
    t0: float
    t1: float
    lines: list[Line]

    @model_validator(mode="after")
    def _t(self):
        if self.t1 <= self.t0:
            raise ValueError(f"escena {self.t0}–{self.t1}: t1 tiene que ser mayor que t0")
        return self


class Footer(_M):
    lines: list[str] = []
    y: float = 1700
    size: float = 31
    delay: float = 0.25


class MusicSynth(_M):
    mode: Literal["synth"]
    bpm: float = Field(120, ge=60, le=200)
    key: str = "Am"
    progression: list[str] = ["Am", "F", "C", "G"]
    build: tuple[float, float] | None = None
    gap: tuple[float, float] | None = None
    drop: float | None = None
    whooshes: list[float] = []
    pops: list[float] = []
    fade: float = 0.45
    target_lufs: float = -12
    seed: int = 7


class MusicFile(_M):
    mode: Literal["file"]
    path: str
    offset: float = 0.0
    license: str = Field(min_length=2, description="origen/licencia de la pista")
    fade: float = 0.45
    target_lufs: float = -12


class MusicNone(_M):
    mode: Literal["none"]


Music = Annotated[Union[MusicSynth, MusicFile, MusicNone], Field(discriminator="mode")]


class Spec(_M):
    format: Format
    client: str = ""
    style: Style = Style()
    shots: list[Shot] = Field(min_length=1)
    camera: Camera = Camera()
    effects: list[Effect] = []
    scenes: list[Scene] = []
    footer: Footer = Footer()
    music: Music = MusicNone(mode="none")

    @field_validator("footer", mode="before")
    @classmethod
    def _footer_list(cls, v):
        return {"lines": v} if isinstance(v, list) else v

    @model_validator(mode="after")
    def _cover(self):
        d = self.format.duration
        shots = self.shots
        if any(b.t0 < a.t0 for a, b in zip(shots, shots[1:])):
            raise ValueError("los planos tienen que estar ordenados por t0")
        if abs(shots[0].t0) > EPS:
            raise ValueError(f"el primer plano tiene que empezar en 0 (empieza en {shots[0].t0})")
        for a, b in zip(shots, shots[1:]):
            if abs(a.t1 - b.t0) > EPS:
                kind = "hueco" if b.t0 > a.t1 else "superposición"
                raise ValueError(f"{kind} entre planos: uno termina en {a.t1} y el siguiente empieza en {b.t0}")
        if shots[-1].t1 < d - EPS:
            raise ValueError(f"el último plano termina en {shots[-1].t1} pero el video dura {d}")
        return self

    # ── utilidades
    @property
    def bpm(self) -> float:
        return self.music.bpm if isinstance(self.music, MusicSynth) else 120.0

    def shot_at(self, t: float) -> Shot:
        for s in self.shots:
            if s.t0 <= t < s.t1:
                return s
        return self.shots[-1]

    @property
    def cuts(self) -> list[float]:
        return [s.t0 for s in self.shots[1:]]


def beat_grid(bpm: float, duration: float) -> list[float]:
    beat = 60.0 / bpm
    return [i * beat for i in range(int(duration / beat) + 1)]


class SpecError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


def _fmt_errors(e: ValidationError) -> list[str]:
    out = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err["loc"])
        msg = err["msg"].removeprefix("Value error, ")
        out.append(f"{loc}: {msg}" if loc else msg)
    return out


def load(path: str | Path) -> Spec:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SpecError([f"JSON inválido en {path}: línea {e.lineno}, columna {e.colno}: {e.msg}"])
    try:
        return Spec.model_validate(data)
    except ValidationError as e:
        raise SpecError(_fmt_errors(e))


def check(spec: Spec, clip_durations: dict[str, float]) -> tuple[list[str], list[str]]:
    """Validación contra los archivos. Devuelve (errores, avisos)."""
    errors, warns = [], []
    for s in spec.shots:
        dur = clip_durations.get(s.clip)
        if dur is None:
            errors.append(f"plano en {s.t0}s: no encuentro el clip '{s.clip}'")
        elif s.src_out > dur + 1 / 60:
            errors.append(
                f"plano en {s.t0}s: pide hasta {s.src_out:.2f}s del clip '{s.clip}' pero dura {dur:.2f}s "
                f"(bajá src_in, speed o el largo del plano)")
    W, H = spec.format.w, spec.format.h
    for s in spec.shots:
        for z, (cx, cy), when in ((s.zoom[0], s.center[0], "al empezar"), (s.zoom[1], s.center[1], "al terminar")):
            mx, my = W / 2 * (1 - 1 / z), H / 2 * (1 - 1 / z)
            if abs(cx - W / 2) > mx + 25 or abs(cy - H / 2) > my + 25:
                warns.append(f"plano en {s.t0}s ({when}): con zoom {z:g} el centro ({cx:g}, {cy:g}) deja ver bordes "
                             f"espejados; x tiene que estar entre {W / 2 - mx:.0f} y {W / 2 + mx:.0f}, "
                             f"y entre {H / 2 - my:.0f} y {H / 2 + my:.0f} (o subí el zoom)")
    frame = 1 / spec.format.fps
    beat = 60 / spec.bpm
    for c in spec.cuts:
        off = abs(c - round(c / beat) * beat)
        if off > frame + EPS:
            warns.append(f"el corte en {c:.2f}s cae a {off * 1000:.0f} ms del beat más cercano ({spec.bpm:g} BPM)")
    if not spec.scenes or not any(sc.lines for sc in spec.scenes):
        errors.append("el video no tiene ningún texto: agregá escenas con líneas (título, frase, etc.)")
    for sc in spec.scenes:
        if not sc.lines:
            errors.append(f"la escena {sc.t0}–{sc.t1}s no tiene líneas de texto: completala o sacala")
        for ln in sc.lines:
            if PLACEHOLDER.search(ln.text.replace("*", "")):
                errors.append(f"escena {sc.t0}s: '{ln.text}' es un texto de relleno. Escribí el texto real "
                              "(si falta un dato, escribí un texto completo que funcione igual y avisalo en el resumen)")
            if ln.text.count("*") % 2:
                warns.append(f"escena {sc.t0}s, '{ln.text}': asteriscos sin cerrar")
            if not 0 <= ln.y <= spec.format.h:
                errors.append(f"escena {sc.t0}s, '{ln.text}': y={ln.y} fuera del lienzo")
    if isinstance(spec.music, MusicSynth) and spec.music.drop is not None and spec.music.drop >= spec.format.duration:
        errors.append("music.drop cae después del final del video")
    return errors, warns
