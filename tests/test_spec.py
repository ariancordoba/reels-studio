import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine.spec import Spec, beat_grid, check

EXAMPLE = json.loads((Path(__file__).parent / "fixtures" / "ejemplo.spec.json").read_text(encoding="utf-8"))
CLIP = "crudo_IMG_9001.MOV"


def spec(**patch):
    d = copy.deepcopy(EXAMPLE)
    d.update(patch)
    return d


def test_example_is_valid():
    s = Spec.model_validate(EXAMPLE)
    assert s.cuts == [2.0, 4.0, 7.0]
    assert s.footer.lines[0].startswith("CLUB")  # la lista se convierte a Footer
    assert check(s, {CLIP: 9.14}) == ([], [])


def test_gap_between_shots():
    d = spec()
    d["shots"][1]["t0"] = 2.5
    with pytest.raises(ValidationError, match="hueco entre planos"):
        Spec.model_validate(d)


def test_overlap_between_shots():
    d = spec()
    d["shots"][1]["t0"] = 1.5
    with pytest.raises(ValidationError, match="superposición"):
        Spec.model_validate(d)


def test_shots_must_cover_duration():
    d = spec()
    d["format"]["duration"] = 12
    with pytest.raises(ValidationError, match="dura 12"):
        Spec.model_validate(d)


def test_unknown_field_rejected():
    d = spec()
    d["shots"][0]["zooom"] = [1, 1]
    with pytest.raises(ValidationError):
        Spec.model_validate(d)


def test_clip_too_short():
    errors, _ = check(Spec.model_validate(EXAMPLE), {CLIP: 8.0})
    assert any("dura 8.00s" in e for e in errors)


def test_missing_clip():
    errors, _ = check(Spec.model_validate(EXAMPLE), {})
    assert any("no encuentro el clip" in e for e in errors)


def test_off_beat_cut_warns():
    d = spec()
    d["shots"][0]["t1"] = d["shots"][1]["t0"] = 2.2
    _, warns = check(Spec.model_validate(d), {CLIP: 9.14})
    assert any("2.20s" in w for w in warns)


def test_beat_grid():
    g = beat_grid(120, 3)
    assert g == [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    assert len(beat_grid(100, 6)) == 11
