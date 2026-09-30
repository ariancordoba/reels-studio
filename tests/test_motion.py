import json

import pytest

from engine import motion
from engine.overlay import MOTION_JS

CASES = [(z, w) for z in (0.38, 0.45, 0.7, 1.0, 1.6) for w in (14, 20, 24)]
TAUS = [-0.1, 0.0, 0.01, 0.05, 0.1, 0.2, 0.35, 0.6, 1.0, 2.0]


@pytest.mark.parametrize("zeta,omega", CASES)
def test_spring_limits(zeta, omega):
    assert motion.spring(0, zeta, omega) == 0
    assert abs(motion.spring(5, zeta, omega) - 1) < 1e-3
    assert motion.spring_vel(0, zeta, omega) == 0


@pytest.mark.parametrize("zeta,omega", CASES)
def test_spring_vel_is_derivative(zeta, omega):
    h = 1e-6
    for tau in TAUS[2:]:
        num = (motion.spring(tau + h, zeta, omega) - motion.spring(tau - h, zeta, omega)) / (2 * h)
        assert abs(num - motion.spring_vel(tau, zeta, omega)) < 1e-4 * max(1, abs(num))


def test_underdamped_overshoots_overdamped_does_not():
    assert max(motion.spring(t / 100, 0.45, 24) for t in range(100)) > 1.1
    assert max(motion.spring(t / 100, 1.6, 24) for t in range(300)) <= 1.0


def test_letter_drop_settles():
    m = motion.letter_drop(3.0, 0, 0, dist=84)
    assert abs(m["y"]) < 0.05 and m["op"] == 1 and abs(m["sx"] - 1) < 1e-3


def test_python_and_js_match():
    """motion.py y motion.js tienen que dar lo mismo (el overlay usa JS, el compositor Python)."""
    from playwright.sync_api import sync_playwright

    pts = [(z, w, t) for z, w in CASES for t in TAUS]
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.add_script_tag(content=MOTION_JS.read_text(encoding="utf-8"))
        js = pg.evaluate(
            f"""{json.dumps(pts)}.map(([z, w, t]) => [M.spring(t, z, w), M.springVel(t, z, w),
                  M.letterDrop(t, 0.1, 2, {{zeta: z, omega: w, dist: 90}}).y, M.popIn(t, 0.05).dy])""")
        b.close()
    for (z, w, t), (s, v, y, dy) in zip(pts, js):
        assert s == pytest.approx(motion.spring(t, z, w), abs=1e-9)
        assert v == pytest.approx(motion.spring_vel(t, z, w), abs=1e-7)
        assert y == pytest.approx(motion.letter_drop(t, 0.1, 2, zeta=z, omega=w, dist=90)["y"], abs=1e-7)
        assert dy == pytest.approx(motion.pop_in(t, 0.05)["dy"], abs=1e-7)
