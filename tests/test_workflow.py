"""Flujo de proyecto con un Claude simulado (escribe specs como lo haría Claude)."""
import json
import sys
from pathlib import Path

import pytest

from app.claude_runner import Result

EJ = Path(__file__).parent.parent / "ejemplo"
SPEC = json.loads((Path(__file__).parent / "fixtures" / "ejemplo.spec.json").read_text(encoding="utf-8"))
CLIP = EJ / "crudo_IMG_9001.MOV"

pytestmark = pytest.mark.skipif(not CLIP.exists(), reason="falta el crudo de ejemplo")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("REELS_DATA", str(tmp_path / "datos"))
    monkeypatch.setenv("REELS_LOCAL", str(tmp_path / "local"))
    import importlib

    from app import projects, settings, workflow
    importlib.reload(settings)
    importlib.reload(projects)
    importlib.reload(workflow)
    projects.save_client({"nombre": "Club Norte", "accent": "#caffbf"})
    p = projects.create_project("Copa Primavera", "club-norte", [CLIP], [], "Reel del torneo", 11)
    # análisis ya hecho (rápido): el flujo no lo repite
    (p / "analisis" / "resumen.md").write_text("# Análisis\n", encoding="utf-8")
    return projects, workflow, p


class FakeClaude:
    """Hace lo que CLAUDE.md pide: escribe el spec de la versión que le indican."""

    def __init__(self, edit=None, fail=None, session="s-1"):
        self.edit, self.fail, self.session = edit, fail, session
        self.calls = []

    def run(self, cwd, prompt, session_id=None, on_event=None, cancel=None):
        self.calls.append((prompt, session_id))
        if self.fail:
            err = self.fail.pop(0) if isinstance(self.fail, list) else self.fail
            if err:
                return Result(False, "falló", None, error=err)
        vdir = sorted((Path(cwd) / "versiones").iterdir(), key=lambda d: int(d.name[1:]))[-1]
        spec = json.loads((vdir / "spec.json").read_text(encoding="utf-8")) if (vdir / "spec.json").exists() else json.loads(json.dumps(SPEC))
        if self.edit:
            self.edit(spec)
        (vdir / "spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        on_event and on_event({"type": "status", "text": "Escribiendo el guion…"})
        return Result(True, "Listo, armé el video.", self.session, 0.1, 5)


def test_first_version_and_change(env):
    projects, workflow, p = env
    res = workflow.first_version(p, runner=FakeClaude())
    assert res["ok"] and res["version"] == "v1"
    v1 = p / "versiones" / "v1"
    assert list((v1 / "stills").glob("t*.jpg")), "genera la vista previa"
    m = projects.meta(p)
    assert m["version_actual"] == "v1" and m["session_id"] == "s-1" and m["etapa"] == "vista_previa"
    assert not (p / "proyecto.lock").exists()

    def lighter(spec):
        spec["style"]["accent"] = "#e4ffdc"

    fake = FakeClaude(edit=lighter)
    res = workflow.request_change(p, "el verde más claro", runner=fake)
    assert res["ok"] and res["version"] == "v2"
    assert fake.calls[0][1] == "s-1", "retoma la misma sesión"
    v2 = json.loads((p / "versiones" / "v2" / "spec.json").read_text(encoding="utf-8"))
    assert v2["style"]["accent"] == "#e4ffdc"
    assert json.loads((v1 / "spec.json").read_text(encoding="utf-8"))["style"]["accent"] == "#caffbf", "v1 intacta"
    assert (p / "versiones" / "v2" / "pedido.txt").read_text(encoding="utf-8").strip() == "el verde más claro"


def test_unchanged_request_drops_version(env):
    projects, workflow, p = env
    workflow.first_version(p, runner=FakeClaude())
    res = workflow.request_change(p, "¿está todo bien?", runner=FakeClaude())
    assert res["ok"] and res.get("unchanged")
    assert [v.name for v in (p / "versiones").iterdir()] == ["v1"]


def test_invalid_spec_gets_one_retry(env):
    projects, workflow, p = env
    state = {"n": 0}

    def gap_first_time(spec):
        state["n"] += 1
        if state["n"] == 1:
            spec["shots"][1]["t0"] = 2.5  # hueco → error de validación
        else:
            spec["shots"][1]["t0"] = 2.0

    fake = FakeClaude(edit=gap_first_time)
    res = workflow.first_version(p, runner=fake)
    assert res["ok"], res
    assert len(fake.calls) == 2 and "hueco" in fake.calls[1][0]


def test_auth_error_leaves_no_version(env):
    projects, workflow, p = env
    res = workflow.first_version(p, runner=FakeClaude(fail="auth"))
    assert not res["ok"] and res["error"] == "auth"
    assert not any((p / "versiones").iterdir())
    m = projects.meta(p)
    assert m["etapa"] == "crudos" and m["session_id"] is None


def test_lost_session_restarts_with_history(env):
    projects, workflow, p = env
    workflow.first_version(p, runner=FakeClaude())
    fake = FakeClaude(fail=["session_lost", None], session="s-2", edit=lambda s: s["style"].update(darken=0.4))
    res = workflow.request_change(p, "que se lea mejor", runner=fake)
    assert res["ok"]
    assert fake.calls[1][1] is None and "Historial del proyecto" in fake.calls[1][0]
    assert projects.meta(p)["session_id"] == "s-2"


def test_lock_blocks_other_machine(env):
    projects, workflow, p = env
    projects.write_json(p / "proyecto.lock", {"machine": "LAPTOP", "what": "render", "ts": __import__("time").time()})
    with pytest.raises(projects.Locked, match="LAPTOP"):
        workflow.first_version(p, runner=FakeClaude())


def test_manual_edit_creates_version(env):
    projects, workflow, p = env
    workflow.first_version(p, runner=FakeClaude())
    spec = json.loads((p / "versiones" / "v1" / "spec.json").read_text(encoding="utf-8"))
    spec["scenes"][0]["lines"][2]["text"] = "*RAYO*"
    assert workflow.edit_version(p, spec)["version"] == "v2"
    spec["shots"][1]["t0"] = 3  # inválido
    assert not workflow.edit_version(p, spec)["ok"]
    assert sorted(v.name for v in (p / "versiones").iterdir()) == ["v1", "v2"]


def test_friendly_status():
    from app.claude_runner import friendly

    assert friendly("Read", {"file_path": "C:/p/analisis/ref/hoja_01.jpg"}) == "Mirando la referencia y los crudos…"
    assert friendly("Write", {"file_path": "versiones/v1/spec.json"}) == "Escribiendo el guion…"
    assert friendly("Bash", {"command": "reels stills versiones/v1"}) == "Generando la vista previa…"


def test_runner_parses_stream(tmp_path, monkeypatch):
    """ClaudeRunner con un 'claude' falso que emite stream-json."""
    from app.claude_runner import ClaudeRunner

    events = [
        {"type": "system", "subtype": "init", "session_id": "abc"},
        {"type": "assistant", "session_id": "abc", "message": {"content": [
            {"type": "tool_use", "name": "Write", "input": {"file_path": "versiones/v1/spec.json"}}]}},
        {"type": "result", "subtype": "success", "is_error": False, "result": "Listo.", "session_id": "abc",
         "total_cost_usd": 0.2, "num_turns": 7},
    ]
    script = tmp_path / "fake_claude.py"
    script.write_text("import json\n" + "".join(f"print(json.dumps({e!r}))\n" for e in events), encoding="utf-8")
    exe = tmp_path / "claude.cmd"
    exe.write_text(f'@"{sys.executable}" "{script}"\n', encoding="utf-8")
    seen = []
    res = ClaudeRunner(exe=str(exe)).run(tmp_path, "hola", on_event=seen.append)
    assert res.ok and res.text == "Listo." and res.session_id == "abc" and res.turns == 7
    assert {"type": "status", "text": "Escribiendo el guion…", "tool": "Write"} in seen
