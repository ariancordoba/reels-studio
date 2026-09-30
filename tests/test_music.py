import pytest

from engine import music
from engine.spec import MusicSynth, Spec


def short_spec(**m):
    return Spec.model_validate({
        "format": {"duration": 6.0},
        "shots": [{"clip": "x.mov", "t0": 0, "t1": 6}],
        "music": {"mode": "synth", **m},
    })


def test_parse_chord():
    assert music.parse_chord("Am") == (9, True)
    assert music.parse_chord("F#") == (6, False)
    assert music.parse_chord("Bbm7") == (10, True)
    assert music.parse_chord("Cmaj7") == (0, False)
    with pytest.raises(ValueError):
        music.parse_chord("H")


def test_voicings_match_prototype():
    # los mismos acordes que el v0 (Am–F–C–G)
    assert music.chord_notes("Am") == ([57, 60, 64], 45)
    assert music.chord_notes("F") == ([53, 57, 60], 41)
    assert music.chord_notes("G") == ([55, 59, 62], 43)


@pytest.mark.parametrize("bpm,drop", [(120, 4.0), (97, None), (140, 3.5)])
def test_synth_loudness(tmp_path, bpm, drop):
    s = short_spec(bpm=bpm, drop=drop, build=[2.5, 3.25] if drop else None, gap=[drop - 0.25, drop] if drop else None,
                   whooshes=[2.0], pops=[4.5])
    out = music.render(s, tmp_path / "m.wav")
    lufs, peak = music.loudness(out)
    assert abs(lufs - s.music.target_lufs) < 1.0
    assert peak <= -2.4


def test_groove_stops_in_gap_before_drop():
    """En el hueco se cortan kick y bajo (el riser sigue subiendo hasta el drop, como en el v0)."""
    s = short_spec(drop=4.0, build=[2.5, 3.5], gap=[3.5, 4.0])
    x = music.Synth(s.music, 6.0).render().mean(axis=1)
    low = music.Synth.filt(x, "lowpass", 150, order=4)
    gap = low[int(3.65 * music.SR): int(3.95 * music.SR)]
    groove = low[int(1.0 * music.SR): int(2.0 * music.SR)]
    assert (gap ** 2).mean() < 0.1 * (groove ** 2).mean()
