"""Que nunca salga un video con relleno o sin textos; vista previa completa; imágenes; plan B de modelo."""
import copy
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

from engine.spec import Spec, check

EX = json.loads((Path(__file__).parent / "fixtures" / "ejemplo.spec.json").read_text(encoding="utf-8"))
CLIP = "crudo_IMG_9001.MOV"


def with_text(t: str) -> Spec:
    d = copy.deepcopy(EX)
    d["scenes"][1]["lines"][1]["text"] = t
    return Spec.model_validate(d)


@pytest.mark.parametrize("t", ["Acá va la frase clave", "[TÍTULO]", "Texto de ejemplo", "Lorem ipsum", "aquí va tu slogan"])
def test_placeholder_text_is_an_error(t):
    errors, _ = check(with_text(t), {CLIP: 9.14})
    assert any("relleno" in e for e in errors)


@pytest.mark.parametrize("t", ["JUGAR. APRENDER. *CRECER.*", "Se viene algo grande...", "Acá te esperamos"])
def test_real_text_passes(t):
    errors, _ = check(with_text(t), {CLIP: 9.14})
    assert errors == []


def test_video_without_text_is_an_error():
    d = copy.deepcopy(EX)
    d["scenes"] = []
    errors, _ = check(Spec.model_validate(d), {CLIP: 9.14})
    assert any("ningún texto" in e for e in errors)
    d["scenes"] = [{"t0": 0, "t1": 3, "lines": []}]
    errors, _ = check(Spec.model_validate(d), {CLIP: 9.14})
    assert any("no tiene líneas" in e for e in errors)


def test_dense_preview_times():
    from engine.stills import default_times, dense_times

    sp = Spec.model_validate(EX)
    ts = dense_times(sp)
    assert len(ts) >= 20 and ts == sorted(ts) and max(ts) < sp.format.duration
    assert set(default_times(sp)) <= set(ts), "incluye el momento en que se asienta cada escena"


def test_shrink_image(tmp_path):
    from engine.analyze import shrink_image

    p = tmp_path / "ref.png"
    cv2.imwrite(str(p), np.full((3000, 2000, 3), 200, np.uint8))
    out = shrink_image(p)
    img = cv2.imread(str(out))
    assert out.suffix == ".jpg" and max(img.shape[:2]) == 1600 and not p.exists()


def test_falls_back_when_model_not_in_plan(tmp_path):
    """Si la cuenta no tiene Opus, reintenta con el modelo por defecto en vez de fallar."""
    from app.claude_runner import ClaudeRunner

    script = tmp_path / "fake.py"
    script.write_text(
        "import json, sys\n"
        "if '--model' in sys.argv:\n"
        "    print(json.dumps({'type':'result','is_error':True,'result':'Error: model opus is not available on your plan','session_id':'x'}))\n"
        "else:\n"
        "    print(json.dumps({'type':'result','is_error':False,'result':'Listo.','session_id':'y'}))\n", encoding="utf-8")
    exe = tmp_path / "claude.cmd"
    exe.write_text(f'@"{sys.executable}" "{script}" %*\n', encoding="utf-8")
    seen = []
    r = ClaudeRunner(exe=str(exe), model="opus")
    res = r.run(tmp_path, "hola", on_event=seen.append)
    assert res.ok and res.text == "Listo."
    assert any("no incluye opus" in e.get("text", "") for e in seen)
    assert r.model == "opus", "no cambia la preferencia guardada"
