"""Ahorro de tokens (armado automático, ajustes rápidos, aprendizajes) y actualizaciones."""
import hashlib
import importlib
import json
import zipfile
from pathlib import Path

import pytest

EJ = Path(__file__).parent.parent / "ejemplo"
SPEC = json.loads((Path(__file__).parent / "fixtures" / "ejemplo.spec.json").read_text(encoding="utf-8"))
CLIP = EJ / "crudo_IMG_9001.MOV"
needs_clip = pytest.mark.skipif(not CLIP.exists(), reason="falta el crudo de ejemplo")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("REELS_DATA", str(tmp_path / "datos"))
    monkeypatch.setenv("REELS_LOCAL", str(tmp_path / "local"))
    from app import projects, settings, updater, workflow
    for m in (settings, projects, updater, workflow):
        importlib.reload(m)
    return settings, projects, workflow, updater, tmp_path


# ── armado automático
@needs_clip
def test_autofill_fields_and_texts():
    from engine import autofill
    from engine.spec import Spec, check

    f = autofill.fields(SPEC)
    assert [x["label"] for x in f[:3]] == ["Antetítulo", "Título", "Título"]
    out = autofill.fill(SPEC, [CLIP], {"0.2": "CUMPLEAÑOS", "3.5": ""}, {"slug": "c", "accent": "#ffd166", "footer": ["PIE"]})
    assert out["scenes"][0]["lines"][2]["text"] == "*CUMPLEAÑOS*", "la línea toda en acento conserva el acento"
    assert len(out["scenes"][3]["lines"]) == len(SPEC["scenes"][3]["lines"]) - 1, "campo vacío = línea fuera"
    assert out["style"]["accent"] == "#ffd166" and out["footer"]["lines"] == ["PIE"]
    errors, warns = check(Spec.model_validate(out), {CLIP.name: 9.14})
    assert errors == [] and not any("bordes" in w for w in warns)
    starts = sorted(s["src_in"] for s in out["shots"])
    assert len(set(starts)) == len(starts), "no repite el mismo tramo"


def test_pick_windows_prefers_interesting_and_avoids_reuse():
    import numpy as np

    from engine.autofill import RATE, pick_windows

    ts = np.arange(40) / RATE  # 10 s
    sc = np.zeros(40)
    sc[20:28] = 1.0  # lo bueno está entre 5 y 7 s
    picks = pick_windows([2.0, 2.0], {"a.mov": (ts, sc)}, {"a.mov": 10.0})
    assert picks[0][1] == pytest.approx(5.0, abs=0.3)
    assert abs(picks[1][1] - picks[0][1]) >= 1.5, "el segundo plano no pisa al primero"


# ── ajustes rápidos
def test_hex_shift_and_scale(env):
    _, _, workflow, _, _ = env
    assert workflow._hex_shift("#caffbf", 0.08) != "#caffbf"
    lighter = workflow._hex_shift("#808080", 0.1)
    assert int(lighter[1:3], 16) > 0x80
    spec = json.loads(json.dumps(SPEC))
    workflow._scale_text(spec, 1.1)
    sc0 = spec["scenes"][0]["lines"]
    assert sc0[0]["y"] == SPEC["scenes"][0]["lines"][0]["y"], "la primera línea queda en su lugar"
    assert sc0[2]["size"] == pytest.approx(112 * 1.1, abs=0.1)


@needs_clip
def test_quick_adjust_and_quick_version(env):
    _, projects, workflow, _, _ = env
    projects.save_client({"nombre": "Liga", "accent": "#caffbf", "footer": ["PIE"]})
    tpl_spec = json.dumps(SPEC)
    p = projects.create_project("Prueba", "liga", [CLIP], [], "", None)
    src = p.parent / "tpl.json"
    src.write_text(tpl_spec, encoding="utf-8")
    t = projects.save_template(src, "Torneo", "", "prueba")
    res = workflow.quick_version(p, t["id"], {"0.2": "RAYO"})
    assert res["ok"] and res["version"] == "v1", res
    v1 = json.loads((p / "versiones/v1/spec.json").read_text(encoding="utf-8"))
    assert v1["scenes"][0]["lines"][2]["text"] == "*RAYO*"
    assert list((p / "versiones/v1/stills").glob("t*.jpg"))
    res = workflow.quick_adjust(p, "fondo_oscuro")
    assert res["ok"] and res["version"] == "v2"
    v2 = json.loads((p / "versiones/v2/spec.json").read_text(encoding="utf-8"))
    assert v2["style"]["darken"] == pytest.approx(v1["style"]["darken"] + 0.08)
    assert projects.meta(p)["version_actual"] == "v2"


# ── aprendizajes
def test_learnings_roundtrip(env):
    _, projects, _, _, tmp = env
    projects.save_client({"nombre": "Liga"})
    clip = tmp / "x.mov"
    clip.write_bytes(b"0")
    p = projects.create_project("A", "liga", [clip], [], "", None)
    (p / "aprendizajes.md").write_text("- Títulos grandes\n- Nunca amarillo\n", encoding="utf-8")
    projects.merge_learnings(p)
    projects.merge_learnings(p)  # no duplica
    got = projects.client_learnings_path("liga").read_text(encoding="utf-8")
    assert got.count("Nunca amarillo") == 1
    p2 = projects.create_project("B", "liga", [clip], [], "", None)
    projects.sync_shared(p2)
    assert "Títulos grandes" in (p2 / "aprendizajes.md").read_text(encoding="utf-8")


# ── actualizaciones
def test_version_compare(env):
    _, _, _, updater, _ = env
    assert updater.vtuple("v0.10.0") > updater.vtuple("0.9.9")
    assert updater.vtuple("1.2") == (1, 2)


def test_check_and_download_from_manifest(env):
    settings, _, _, updater, tmp = env
    z = tmp / "pub" / "reels-studio-9.9.9.zip"
    z.parent.mkdir()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("reels-studio/VERSION", "9.9.9\n")
        zf.writestr("reels-studio/app/__init__.py", "")
    sha = hashlib.sha256(z.read_bytes()).hexdigest()
    man = tmp / "pub" / "update.json"
    man.write_text(json.dumps({"version": "9.9.9", "url": z.as_uri(), "sha256": sha, "notas": "x"}), encoding="utf-8")
    settings.save({"update_source": man.as_uri()})
    info = updater.check()
    assert info["disponible"] and info["version"] == "9.9.9"
    stage = updater.download(info)
    assert (stage / "VERSION").read_text().strip() == "9.9.9"
    bad = {**info, "sha256": "0" * 64}
    with pytest.raises(ValueError, match="dañado"):
        updater.download(bad)

    # automático: la deja descargada y lista; con la opción apagada no hace nada
    monkey = pytest.MonkeyPatch()
    monkey.setattr(updater, "is_dev_checkout", lambda: False)
    try:
        settings.save({"auto_update": False})
        updater.auto_prepare()
        assert updater.state["pending"] is None
        settings.save({"auto_update": True})
        seen = []
        updater.auto_prepare(seen.append)
        assert updater.state["pending"]["version"] == "9.9.9" and seen
        assert (Path(updater.state["pending"]["stage"]) / "VERSION").exists()
    finally:
        monkey.undo()
        updater.state["pending"] = None

