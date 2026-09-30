"""Regresión: el spec del ejemplo tiene que reproducir el video aprobado (archivos locales, no van al repo).

No van a ser idénticos (cambian las curvas y la fuente de emojis), así que se compara SSIM ≥ 0.85
en cuadros clave.
"""
import re
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from engine import cli
from engine.probe import ffmpeg_exe

EJ = Path(__file__).parent.parent / "ejemplo"
SPEC = EJ / "aprobado.spec.json"
REF = EJ / "aprobado_final.mp4"
TIMES = [0.2, 1.5, 3.5, 6.5, 8.8, 10.2]

pytestmark = pytest.mark.skipif(not (REF.exists() and SPEC.exists() and (EJ / "crudo_IMG_9001.MOV").exists()),
                                reason="faltan los videos de ejemplo")


def grab(video: Path, t: float) -> np.ndarray:
    r = subprocess.run([ffmpeg_exe(), "-v", "error", "-ss", f"{t:.4f}", "-i", str(video), "-frames:v", "1",
                        "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, check=True)
    return cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR)


def ssim(a: np.ndarray, b: np.ndarray) -> float:
    prep = lambda x: cv2.cvtColor(cv2.resize(x, (540, 960), interpolation=cv2.INTER_AREA),
                                  cv2.COLOR_BGR2GRAY).astype(np.float64)
    a, b = prep(a), prep(b)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    g = lambda x: cv2.GaussianBlur(x, (11, 11), 1.5)
    ma, mb = g(a), g(b)
    va, vb, cov = g(a * a) - ma ** 2, g(b * b) - mb ** 2, g(a * b) - ma * mb
    return float((((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma ** 2 + mb ** 2 + c1) * (va + vb + c2))).mean())


@pytest.fixture(scope="module")
def stills_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("stills")
    assert cli.main(["stills", str(SPEC), "--times", ",".join(map(str, TIMES)), "-o", str(out)]) == 0
    return out


@pytest.mark.parametrize("t", TIMES)
def test_stills_match_approved(stills_dir, t):
    tq = round(t * 30) / 30
    s = ssim(grab(REF, tq), cv2.imread(str(stills_dir / f"t{tq:06.2f}.jpg")))
    assert s >= 0.85, f"{t}s: SSIM {s:.3f}"


@pytest.mark.slow
def test_full_render_matches_approved(tmp_path):
    out = tmp_path / "video.mp4"
    assert cli.main(["render", str(SPEC), "-o", str(out)]) == 0
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(out)], capture_output=True, text=True)
    assert "1080x1920" in r.stderr and "Duration: 00:00:11.0" in r.stderr and "Audio: aac" in r.stderr
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(out), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    summary = r.stderr[r.stderr.rindex("Summary:"):]
    lufs = float(re.search(r"I:\s+(-?[\d.]+) LUFS", summary)[1])
    peak = float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", summary)[1])
    assert abs(lufs + 12) <= 1 and peak <= -2.0, f"audio: {lufs} LUFS, true peak {peak} dBFS"
    for t in TIMES:
        tq = round(t * 30) / 30
        s = ssim(grab(REF, tq), grab(out, tq))
        assert s >= 0.85, f"{t}s: SSIM {s:.3f}"
