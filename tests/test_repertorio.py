"""Repertorio: tipografías, animaciones y estilos de texto, géneros musicales y efectos de sonido."""
import copy
import importlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from engine import music, sfx
from engine.fonts import CATALOG
from engine.overlay import find_font
from engine.probe import ASSETS
from engine.spec import Spec

EX = json.loads((Path(__file__).parent / "fixtures" / "ejemplo.spec.json").read_text(encoding="utf-8"))
ANIMS = ["caida", "subida", "pop", "maquina", "fade", "deslizar", "zoom", "palabras", "rebote", "ola", "glitch",
         "desenfoque", "rotar"]
LOOKS = ["normal", "caja", "contorno", "resaltado", "neon", "sombra"]


def base(duration=6.0, **extra):
    return {"format": {"duration": duration}, "shots": [{"clip": "fondo.png", "t0": 0, "t1": duration}], **extra}


def test_every_catalog_font_is_installed():
    for f in CATALOG:
        assert find_font(f["name"], [ASSETS / "fonts"]), f"falta el archivo de {f['name']}"


def test_spec_accepts_new_options_and_rejects_typos():
    d = copy.deepcopy(EX)
    ln = d["scenes"][0]["lines"][0]
    ln.update(anim="maquina", out="fade", look="caja", align="izquierda", font="Anton")
    d["scenes"][0]["lines"].append({"kind": "script", "text": "a mano", "size": 60, "y": 700})
    d["style"].update(display_anim="zoom", look="neon", script_font="Pacifico", display_uppercase=False)
    d["music"]["genre"] = "reggaeton"
    d["sfx"] = [{"t": 1.0, "type": "ding"}]
    s = Spec.model_validate(d)
    assert s.bpm == 120  # el ejemplo fija bpm 120 explícito
    d["scenes"][0]["lines"][0]["anim"] = "explosion"
    with pytest.raises(ValidationError):
        Spec.model_validate(d)


def test_genre_default_bpm():
    s = Spec.model_validate(base(music={"mode": "synth", "genre": "reggaeton"}))
    assert s.bpm == 95


def test_seventh_chords():
    assert music.chord_notes("Am") == ([57, 60, 64], 45)
    assert music.chord_notes("Fmaj7")[0] == [53, 57, 60, 64]
    assert music.chord_notes("Em7")[0] == [52, 55, 59, 62]
    assert music.chord_notes("A7")[0] == [57, 61, 64, 67]


@pytest.mark.parametrize("genre", list(music.GENRES))
def test_every_genre_renders_at_target_loudness(tmp_path, genre):
    s = Spec.model_validate(base(8.0, music={"mode": "synth", "genre": genre, "drop": 4.0, "build": [3.0, 3.75]},
                                 auto_sfx=False))
    lufs, peak = music.loudness(music.render(s, tmp_path / "m.wav"))
    assert abs(lufs + 12) < 1.2 and peak < -2.4


def test_genres_sound_different():
    """Huella rítmica: la energía por semicorchea de dos géneros no puede ser casi igual."""
    def fingerprint(g):
        m = Spec.model_validate(base(8.0, music={"mode": "synth", "genre": g})).music
        x = music.Synth(m, 8.0).render().mean(1)
        step = int(music.SR * 60 / (m.bpm or music.GENRES[g]["bpm"]) / 4)
        e = np.array([np.abs(x[i:i + step]).mean() for i in range(0, len(x) - step, step)][:64])
        return e / (e.max() + 1e-9)
    prints = {g: fingerprint(g) for g in ("house", "reggaeton", "lofi", "trap", "ambient")}
    names = list(prints)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = prints[names[i]], prints[names[j]]
            n = min(len(a), len(b))
            assert np.corrcoef(a[:n], b[:n])[0, 1] < 0.97, f"{names[i]} y {names[j]} suenan igual"


def test_auto_sfx_follow_animations_and_cuts():
    d = base(6.0, scenes=[{"t0": 0, "t1": 3, "lines": [
        {"kind": "serif", "text": "Hola mundo", "size": 60, "y": 400, "delay": 0.5, "anim": "maquina"},
        {"kind": "display", "text": "WOW", "size": 100, "y": 500, "delay": 1.0, "anim": "glitch"}]}],
        sfx=[{"t": 4.0, "type": "caja_registradora"}])
    d["shots"] = [{"clip": "a.png", "t0": 0, "t1": 3}, {"clip": "a.png", "t0": 3, "t1": 6, "transition_in": "whip"}]
    ev = sfx.events(Spec.model_validate(d))
    kinds = [e[1] for e in ev]
    assert kinds.count("tick") == 9, "una tecla por letra (sin espacios)"
    first_tick = min(e[0] for e in ev if e[1] == "tick")
    assert first_tick == pytest.approx(0.5)
    assert "glitch" in kinds and "whoosh" in kinds and "caja_registradora" in kinds
    d["auto_sfx"] = False
    assert [e[1] for e in sfx.events(Spec.model_validate(d))] == ["caja_registradora"]


@pytest.mark.parametrize("kind", list(sfx.SFX_DESC))
def test_every_sfx_synthesizes(kind):
    x = sfx.synth(kind, np.random.default_rng(1))
    assert len(x) > 100 and np.isfinite(x).all() and 0.05 < np.abs(x).max() <= 1.2


def test_sfx_without_music(tmp_path):
    s = Spec.model_validate(base(4.0, sfx=[{"t": 1.0, "type": "ding"}]))
    p = music.render(s, tmp_path / "fx.wav")
    assert p is not None
    _, peak = music.loudness(p)
    assert -30 < peak < -2


def test_quick_variety_cycles(tmp_path, monkeypatch):
    monkeypatch.setenv("REELS_DATA", str(tmp_path / "datos"))
    monkeypatch.setenv("REELS_LOCAL", str(tmp_path / "local"))
    from app import workflow
    importlib.reload(workflow)
    s = copy.deepcopy(EX)
    seen = set()
    for _ in range(4):
        workflow._other_music(s)
        seen.add(s["music"]["genre"])
        Spec.model_validate(s)
    assert len(seen) == 4, "cada clic, otro género"
    workflow._other_anim(s)
    workflow._other_font(s)
    workflow._other_look(s)
    sp = Spec.model_validate(s)
    assert (sp.style.display_anim, sp.style.display_font, sp.style.look) != ("caida", "Archivo", "normal")


def test_logo_white_background_removed_and_drawn(tmp_path, monkeypatch):
    monkeypatch.setenv("REELS_CACHE", str(tmp_path / "cache"))
    from engine import photos, stills

    # logo: escudo rojo con un círculo blanco ADENTRO, sobre fondo blanco
    img = np.full((800, 600, 3), 255, np.uint8)
    cv2.rectangle(img, (150, 200), (450, 600), (40, 40, 200), -1)
    cv2.circle(img, (300, 400), 80, (255, 255, 255), -1)
    src = tmp_path / "logo.jpg"
    cv2.imwrite(str(src), img)
    out = photos.logo_png(src, tmp_path / "logo.png")
    rgba = cv2.imread(str(out), cv2.IMREAD_UNCHANGED)
    assert rgba.shape[2] == 4 and rgba.shape[0] < 450, "recortado al escudo"
    h, w = rgba.shape[:2]
    assert rgba[h // 2, w // 2, 3] == 255, "el blanco de adentro queda"
    # dibujado en el video, arriba al centro
    bg = tmp_path / "fondo.png"
    cv2.imwrite(str(bg), np.full((1920, 1080, 3), (30, 120, 30), np.uint8))
    spec = Spec.model_validate({**base(2.0), "shots": [{"clip": "fondo.png", "t0": 0, "t1": 2.0}],
                                "logo": {"file": "logo.jpg", "width": 160}, "music": {"mode": "none"}, "auto_sfx": False})
    shot = stills.render(spec, {"fondo.png": bg, "logo.jpg": src}, tmp_path / "s", times=[1.5])[0]
    frame = cv2.imread(str(shot))
    top = frame[70:250, 460:620].astype(int)
    assert (top[..., 2] - top[..., 1]).max() > 80, "se ve el rojo del logo arriba"


def test_every_animation_and_look_renders(tmp_path, monkeypatch):
    """Todas las animaciones y estilos se dibujan (sin errores de JS) y dejan texto visible al asentarse."""
    monkeypatch.setenv("REELS_CACHE", str(tmp_path / "cache"))
    from engine import stills

    bg = tmp_path / "fondo.png"
    cv2.imwrite(str(bg), np.full((1920, 1080, 3), (90, 60, 30), np.uint8))
    scenes, t, times = [], 0.0, []
    for i, a in enumerate(ANIMS):
        look = LOOKS[i % len(LOOKS)]
        font = CATALOG[i % len(CATALOG)]["name"]
        scenes.append({"t0": t, "t1": t + 1.0, "out": "fade", "lines": [
            {"kind": "display", "text": f"PRUEBA *{a.upper()}*", "size": 90, "y": 500, "anim": a, "look": look, "font": font},
            {"kind": "script", "text": "a mano", "size": 70, "y": 650, "anim": a}]})
        times.append(round(t + 0.6, 2))
        t += 1.0
    spec = Spec.model_validate({"format": {"duration": t}, "shots": [{"clip": "fondo.png", "t0": 0, "t1": t}],
                                "scenes": scenes, "music": {"mode": "none"}, "auto_sfx": False})
    out = stills.render(spec, {"fondo.png": bg}, tmp_path / "s", times=times)
    for p, a in zip(out[:-1], ANIMS):
        img = cv2.imread(str(p))
        band = img[480:620].astype(int)
        assert np.abs(band - [90, 60, 30]).sum(axis=2).max() > 150, f"no se ve el texto con «{a}»"
