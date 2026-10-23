"""Fotos como crudos: orientación de celular (EXIF), HEIC, mezcla con videos, armado automático y análisis."""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from engine import photos
from engine.probe import probe
from engine.spec import Spec, check

EJ = Path(__file__).parent.parent / "ejemplo"
CLIP = EJ / "crudo_IMG_9001.MOV"
EX = json.loads((Path(__file__).parent / "fixtures" / "ejemplo.spec.json").read_text(encoding="utf-8"))


def phone_photo(path: Path, fmt="JPEG") -> Path:
    """4000×3000 guardada "acostada" con orientación EXIF 6 (así guardan muchos celulares una foto vertical).
    Arriba de la foto real hay una franja roja: después de rotar tiene que quedar arriba."""
    real = np.zeros((4000, 3000, 3), np.uint8)
    real[:600] = (255, 0, 0)  # arriba, en RGB
    stored = np.rot90(real, k=1)  # lo que guarda el sensor (rotado 90° antihorario)
    im = Image.fromarray(np.ascontiguousarray(stored))
    exif = Image.Exif()
    exif[0x0112] = 6
    im.save(path, fmt, exif=exif.tobytes(), quality=90)
    return path


def test_exif_orientation(tmp_path):
    p = phone_photo(tmp_path / "foto.jpg")
    assert photos.size(p) == (3000, 4000), "se ve vertical"
    img = photos.load(p)
    assert img.shape[:2] == (4000, 3000)
    assert img[100, 1500, 2] > 200 and img[3900, 1500, 2] < 50, "la franja roja quedó arriba"
    info = probe(p)
    assert info.is_photo and info.width == 3000 and info.height == 4000 and info.duration > 100


def test_heic(tmp_path):
    pytest.importorskip("pillow_heif")
    try:
        p = phone_photo(tmp_path / "foto.heic", "HEIF")
    except (KeyError, OSError, ValueError) as e:
        pytest.skip(f"este pillow-heif no trae codificador HEIC: {e}")
    assert photos.size(p) == (3000, 4000)
    assert photos.load(p).shape[:2] == (4000, 3000)


def test_photo_proxy_covers_canvas(tmp_path, monkeypatch):
    monkeypatch.setenv("REELS_CACHE", str(tmp_path / "cache"))
    from engine import proxies

    p = tmp_path / "horizontal.png"
    cv2.imwrite(str(p), np.full((1000, 3000, 3), 128, np.uint8))  # muy horizontal
    px = proxies.Proxy(p, 1080, 1920)
    px.build()
    assert px.n_frames == 1
    f = px.frame(0)
    assert f.shape == (1920, 1080, 3) and px.frame(37.5).shape == f.shape, "cualquier segundo = la misma foto"


@pytest.mark.skipif(not CLIP.exists(), reason="falta el crudo de ejemplo")
def test_mixed_video_and_photo_render(tmp_path, monkeypatch):
    monkeypatch.setenv("REELS_CACHE", str(tmp_path / "cache"))
    from engine import stills

    foto = phone_photo(tmp_path / "IMG_2001.jpg")
    d = json.loads(json.dumps(EX))
    d["shots"][1].update(clip=foto.name, src_in=0, speed=1, zoom=[1.0, 1.12], center=[[540, 960], [540, 960]])
    sp = Spec.model_validate(d)
    errors, _ = check(sp, {CLIP.name: 9.14, foto.name: probe(foto).duration})
    assert errors == []
    out = stills.render(sp, {CLIP.name: CLIP, foto.name: foto}, tmp_path / "stills", times=[1.0, 3.0])
    img = cv2.imread(str(out[1]))  # t=3.0 es el plano de la foto
    assert img.shape[:2] == (1920, 1080)
    assert img[60, 540, 2] > img[60, 540, 1] + 40, "se ve la franja roja de arriba de la foto (derecha, no acostada)"


@pytest.mark.skipif(not CLIP.exists(), reason="falta el crudo de ejemplo")
def test_autofill_with_photos(tmp_path):
    from engine import autofill

    f1, f2 = phone_photo(tmp_path / "a.jpg"), phone_photo(tmp_path / "b.jpg")
    out = autofill.fill(EX, [CLIP, f1, f2])
    used = [s["clip"] for s in out["shots"]]
    assert {"a.jpg", "b.jpg"} & set(used), "usa las fotos"
    for s in out["shots"]:
        if s["clip"].endswith(".jpg"):
            assert s["src_in"] == 0 and abs(s["zoom"][0] - s["zoom"][1]) >= 0.04, "foto siempre con movimiento"


def test_analyze_project_with_photo(tmp_path):
    from engine import analyze

    (tmp_path / "entrada" / "crudos").mkdir(parents=True)
    (tmp_path / "entrada" / "referencias").mkdir()
    phone_photo(tmp_path / "entrada" / "crudos" / "IMG_1.jpg")
    res = analyze.analyze_project(tmp_path)
    assert res[0]["tipo"] == "foto" and res[0]["vertical"]
    assert (tmp_path / "analisis" / "IMG_1_foto" / "hoja_01.jpg").exists()
    md = (tmp_path / "analisis" / "resumen.md").read_text(encoding="utf-8")
    assert "Fotos crudas" in md and "IMG_1.jpg" in md
