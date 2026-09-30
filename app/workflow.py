"""Flujo de un proyecto: analizar → Claude escribe v1 → stills → pedidos de cambio (v2, v3…) → render.

Lo usan tanto el CLI (`reels nuevo`, `reels pedir`) como la API de la app.
Cada pedido = versión nueva; nunca se sobrescribe la anterior. El historial vive en archivos
(spec, notas, pedido, resumen), así que si la sesión de Claude se pierde se retoma desde ahí.
"""
from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Callable

from engine import analyze, stills
from engine.project import resolve, version_num, versions
from engine.spec import SpecError

from . import projects
from .claude_runner import ClaudeRunner, Result

Emit = Callable[[dict], None]


def _noop(e):
    pass


# Uso de Claude (Ajustes): cuánto "cerebro" usar en cada tarea. Con suscripción no se paga por token,
# pero cada tarea consume del límite de uso: Sonnet rinde mucho más que Opus para cambios chicos.
MODES = {  # "calidad" (Opus en todo) es el default
    "calidad": {"primera": "opus", "cambio": "opus", "estilo": "opus"},
    "equilibrado": {"primera": "opus", "cambio": "sonnet", "estilo": "opus"},
    "ahorro": {"primera": "sonnet", "cambio": "sonnet", "estilo": "sonnet"},
}
MAX_TURNS = {"primera": 70, "cambio": 35, "estilo": 50}


def runner_for(task: str) -> ClaudeRunner:
    from . import settings

    cfg = settings.load()
    mode = MODES.get(cfg.get("claude_modo") or "calidad", MODES["calidad"])
    return ClaudeRunner(model=cfg.get("claude_model") or mode[task], max_turns=MAX_TURNS[task])


def run_analysis(project: Path, emit: Emit = _noop) -> list[dict]:
    emit({"type": "status", "text": "Analizando la referencia y los crudos…"})
    return analyze.analyze_project(
        project, lambda i, n, name: emit({"type": "progress", "stage": "análisis", "done": i, "total": n, "item": name}))


def history_context(project: Path, upto: Path) -> str:
    """Resumen de versiones anteriores para arrancar una sesión nueva de Claude."""
    parts = []
    for v in versions(project):
        if version_num(v) >= version_num(upto):
            break
        pedido = (v / "pedido.txt").read_text(encoding="utf-8").strip() if (v / "pedido.txt").exists() else "(primera versión)"
        notas = (v / "notas.md").read_text(encoding="utf-8").strip() if (v / "notas.md").exists() else ""
        parts.append(f"### {v.name}\nPedido: {pedido}\n{notas}")
    return "\n\n".join(parts)


def _validate_and_preview(vdir: Path, emit: Emit) -> tuple[list[str], list[str]]:
    try:
        t = resolve(vdir)
    except (SpecError, FileNotFoundError) as e:
        return (e.errors if isinstance(e, SpecError) else [str(e)]), []
    errors, warns = t.check()
    if errors:
        return errors, warns
    shots = list((vdir / "stills").glob("t*.jpg"))
    stale = not shots or max(p.stat().st_mtime for p in shots) < (vdir / "spec.json").stat().st_mtime
    if stale or not (vdir / "stills" / ".completa").exists():  # la de Claude es corta: para ella, la completa
        emit({"type": "status", "text": "Generando la vista previa completa…"})
        stills.render(t.spec, t.clips(), vdir / "stills", font_dirs=t.font_dirs, dense=True)
    return [], warns


def _run_claude(project: Path, vdir: Path, prompt: str, emit: Emit, cancel: threading.Event | None,
                runner: ClaudeRunner) -> Result:
    m = projects.meta(project)
    sid = m.get("session_id")

    res = runner.run(project, prompt, sid, emit, cancel)
    if res.error == "session_lost" or (not res.ok and sid and res.error == "failed" and not res.session_id):
        # otra compu o sesión vencida: arrancar de cero con el historial que está en archivos
        emit({"type": "status", "text": "Retomando el proyecto desde las notas…"})
        projects.save_meta(project, session_id=None)
        ctx = history_context(project, vdir)
        res = runner.run(project, f"{prompt}\n\nHistorial del proyecto (la conversación anterior se perdió):\n{ctx}",
                         None, emit, cancel)
    if res.ok and res.session_id:  # sólo sesiones que llegaron a trabajar
        projects.save_meta(project, session_id=res.session_id)
    return res


def _finish_version(project: Path, vdir: Path, res: Result, pedido: str | None, emit: Emit,
                    runner: ClaudeRunner, cancel, base_spec: str | None) -> dict:
    if not res.ok:
        _drop_if_empty(vdir, base_spec)
        return {"ok": False, "message": res.text, "error": res.error}
    errors, warns = _validate_and_preview(vdir, emit)
    if errors:  # una vuelta más con los errores concretos
        emit({"type": "status", "text": "Corrigiendo un detalle del guion…"})
        fix = ("`reels check` da estos errores en " + f"versiones/{vdir.name}:\n- " + "\n- ".join(errors) +
               "\nCorregilos, generá stills, revisalos y respondé con el resumen para ella.")
        res2 = runner.run(project, fix, projects.meta(project).get("session_id"), emit, cancel)
        if res2.ok:
            res = res2
        errors, warns = _validate_and_preview(vdir, emit)
    if errors:
        _drop_if_empty(vdir, base_spec, force=True)
        return {"ok": False, "message": "No pude armar una versión válida: " + errors[0], "errors": errors}
    if base_spec is not None and (vdir / "spec.json").read_text(encoding="utf-8") == base_spec:
        shutil.rmtree(vdir)
        return {"ok": True, "unchanged": True, "message": res.text or "No hizo falta cambiar nada."}
    if pedido:
        (vdir / "pedido.txt").write_text(pedido.strip() + "\n", encoding="utf-8")
    (vdir / "resumen.txt").write_text(res.text.strip() + "\n", encoding="utf-8")
    projects.save_meta(project, version_actual=vdir.name, etapa="vista_previa", pendiente=None)
    projects.merge_learnings(project)
    return {"ok": True, "version": vdir.name, "message": res.text, "warnings": warns,
            "cost_usd": res.cost_usd, "turns": res.turns}


def _drop_if_empty(vdir: Path, base_spec: str | None, force: bool = False):
    spec = vdir / "spec.json"
    if force or not spec.exists() or (base_spec is not None and spec.read_text(encoding="utf-8") == base_spec):
        shutil.rmtree(vdir, ignore_errors=True)
    project = vdir.parent.parent
    projects.save_meta(project, etapa="vista_previa" if projects.current_version(project) else "crudos")


def first_version(project: Path, emit: Emit = _noop, cancel: threading.Event | None = None,
                  runner: ClaudeRunner | None = None) -> dict:
    runner = runner or runner_for("primera")
    with projects.project_lock(project, "primera versión"):
        projects.sync_shared(project)
        if not (project / "analisis" / "resumen.md").exists():
            run_analysis(project, emit)
        vdir = projects.next_version(project)
        projects.save_meta(project, etapa="guion")
        prompt = (f"Armá la primera versión del video en `versiones/{vdir.name}/spec.json` siguiendo CLAUDE.md "
                  "(instrucciones, análisis, hojas de contacto, cliente). Verificá con `reels check` y "
                  f"`reels stills versiones/{vdir.name}`, mirá los cuadros y corregí. Escribí notas.md. "
                  "Terminá con el resumen corto para ella.")
        res = _run_claude(project, vdir, prompt, emit, cancel, runner)
        return _finish_version(project, vdir, res, None, emit, runner, cancel, None)


def request_change(project: Path, pedido: str, emit: Emit = _noop, cancel: threading.Event | None = None,
                   runner: ClaudeRunner | None = None, adjuntos: list[str] | None = None) -> dict:
    runner = runner or runner_for("cambio")
    with projects.project_lock(project, "cambios"):
        projects.sync_shared(project)
        cur = projects.current_version(project)
        if cur is None:
            return {"ok": False, "message": "Este proyecto todavía no tiene una primera versión."}
        vdir = projects.next_version(project)
        shutil.copy2(cur / "spec.json", vdir / "spec.json")
        base = (vdir / "spec.json").read_text(encoding="utf-8")
        projects.save_meta(project, pendiente=pedido[:140])
        prompt = (f"Pedido de cambio: «{pedido.strip()}»\n\n"
                  f"La versión actual es `versiones/{cur.name}`; ya copié su spec a `versiones/{vdir.name}/spec.json`. "
                  f"Modificá lo mínimo ahí, verificá con `reels check versiones/{vdir.name}` y "
                  f"`reels stills versiones/{vdir.name}`, mirá los cuadros afectados y escribí notas.md. "
                  "Terminá con el resumen corto para ella.")
        if adjuntos:
            prompt += ("\n\nAdjuntó imágenes de referencia para este pedido (miralas con Read; muestran lo que quiere: "
                       "estilo de letra, colores, disposición): " + ", ".join(f"`{a}`" for a in adjuntos))
        res = _run_claude(project, vdir, prompt, emit, cancel, runner)
        out = _finish_version(project, vdir, res, pedido, emit, runner, cancel, base)
        if not out["ok"]:
            projects.save_meta(project, pendiente=None)
        return out


def edit_version(project: Path, spec_data: dict, nota: str = "Edición manual del guion") -> dict:
    """Ediciones desde la pestaña Guion (sin Claude): crea una versión nueva con el spec editado."""
    from engine.spec import Spec
    from pydantic import ValidationError

    try:
        Spec.model_validate(spec_data)
    except ValidationError as e:
        return {"ok": False, "message": "El guion tiene un error: " + e.errors()[0]["msg"]}
    with projects.project_lock(project, "edición"):
        vdir = projects.next_version(project)
        projects.write_json(vdir / "spec.json", spec_data)
        (vdir / "pedido.txt").write_text(nota + "\n", encoding="utf-8")
        errors, warns = _validate_and_preview(vdir, _noop)
        if errors:
            shutil.rmtree(vdir, ignore_errors=True)
            return {"ok": False, "message": errors[0], "errors": errors}
        (vdir / "resumen.txt").write_text("Editaste el guion a mano.\n", encoding="utf-8")
        (vdir / "notas.md").write_text(f"# {vdir.name}\n\n{nota}\n", encoding="utf-8")
        projects.save_meta(project, version_actual=vdir.name, etapa="vista_previa")
        return {"ok": True, "version": vdir.name, "warnings": warns}


# ── sin Claude: armado automático con plantilla y ajustes rápidos (cero tokens)


def quick_version(project: Path, template_id: str, texts: dict[str, str] | None = None,
                  emit: Emit = _noop) -> dict:
    """Primera versión con una plantilla: el motor elige los tramos de los crudos y pone los textos."""
    from engine import autofill

    t = projects.get_template(template_id)
    if not t:
        return {"ok": False, "message": "No encuentro esa plantilla."}
    with projects.project_lock(project, "armado automático"):
        clips = sorted(p for p in (project / "entrada" / "crudos").iterdir() if p.suffix.lower() in analyze.VIDEO_EXT)
        if not clips:
            return {"ok": False, "message": "El proyecto no tiene crudos."}
        emit({"type": "status", "text": "Buscando los mejores momentos de los crudos…"})
        client = projects.get_client(projects.meta(project).get("cliente", "")) or {}
        try:
            spec = autofill.fill(t["spec"], clips, texts, client)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": f"No pude armarlo con la plantilla: {e}"}
        vdir = projects.next_version(project)
        projects.write_json(vdir / "spec.json", spec)
        emit({"type": "status", "text": "Generando la vista previa…"})
        errors, warns = _validate_and_preview(vdir, emit)
        if errors:
            shutil.rmtree(vdir, ignore_errors=True)
            return {"ok": False, "message": errors[0], "errors": errors}
        msg = (f"Armé esta versión con la plantilla «{t['nombre']}», sin usar a Claude: elegí los momentos con más "
               "acción de tus crudos y puse tus textos. Mirá los cuadros; si algo no te convence, pedí el cambio.")
        (vdir / "pedido.txt").write_text(f"Armado automático con la plantilla {t['nombre']}\n", encoding="utf-8")
        (vdir / "resumen.txt").write_text(msg + "\n", encoding="utf-8")
        (vdir / "notas.md").write_text(f"# {vdir.name}\n\nArmado automático (sin Claude) con la plantilla "
                                       f"«{t['nombre']}».\n", encoding="utf-8")
        projects.save_meta(project, version_actual=vdir.name, etapa="vista_previa", plantilla=template_id)
    return {"ok": True, "version": vdir.name, "message": msg, "warnings": warns}


def _hex_shift(hexcol: str, amount: float) -> str:
    """Aclara (+) u oscurece (−) un color manteniendo el tono."""
    import colorsys

    h = hexcol.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hh, light, sat = colorsys.rgb_to_hls(r, g, b)
    light = max(0.05, min(0.97, light + amount))
    r, g, b = colorsys.hls_to_rgb(hh, light, sat)
    return "#{:02x}{:02x}{:02x}".format(*(round(v * 255) for v in (r, g, b)))


def _scale_text(spec: dict, k: float):
    for sc in spec.get("scenes", []):
        if not sc["lines"]:
            continue
        top = min(ln["y"] for ln in sc["lines"])
        for ln in sc["lines"]:
            ln["size"] = round(ln["size"] * k, 1)
            ln["y"] = round(top + (ln["y"] - top) * k, 1)


def _style(spec: dict) -> dict:
    return spec.setdefault("style", {})


QUICK = {
    "acento_claro": ("Color de acento más claro",
                     lambda s: _style(s).update(accent=_hex_shift(_style(s).get("accent", "#caffbf"), 0.08))),
    "acento_oscuro": ("Color de acento más oscuro",
                      lambda s: _style(s).update(accent=_hex_shift(_style(s).get("accent", "#caffbf"), -0.08))),
    "fondo_oscuro": ("Fondo más oscuro (se lee mejor)",
                     lambda s: _style(s).update(darken=round(min(0.7, _style(s).get("darken", 0.32) + 0.08), 2))),
    "fondo_claro": ("Fondo más claro",
                    lambda s: _style(s).update(darken=round(max(0.0, _style(s).get("darken", 0.32) - 0.08), 2))),
    "texto_grande": ("Textos más grandes", lambda s: _scale_text(s, 1.1)),
    "texto_chico": ("Textos más chicos", lambda s: _scale_text(s, 1 / 1.1)),
    "sin_musica": ("Sin música", lambda s: s.update(music={"mode": "none"})),
    "con_musica": ("Con música", lambda s: s.update(music={"mode": "synth", "bpm": 120})),
}


def quick_adjust(project: Path, kind: str) -> dict:
    import json

    if kind not in QUICK:
        return {"ok": False, "message": "Ajuste desconocido"}
    cur = projects.current_version(project)
    if cur is None:
        return {"ok": False, "message": "Todavía no hay una versión para ajustar."}
    label, fn = QUICK[kind]
    spec = json.loads((cur / "spec.json").read_text(encoding="utf-8"))
    fn(spec)
    res = edit_version(project, spec, f"Ajuste rápido: {label.lower()}")
    if res["ok"]:
        vdir = project / "versiones" / res["version"]
        (vdir / "resumen.txt").write_text(f"Ajuste rápido (sin Claude): {label.lower()}.\n", encoding="utf-8")
        res["message"] = f"Listo: {label.lower()}. Lo hice sin Claude, en la versión {res['version']}."
    return res


# ── aprender un estilo de una referencia (Claude una sola vez → plantilla reutilizable)

STYLE_PROMPT = """Estás en una carpeta de trabajo de Reels Studio para **aprender un estilo**, no para hacer un video.
En `entrada/referencias/` hay un reel de referencia y en `analisis/` sus hojas de contacto (resumen.md, hoja_NN.jpg,
cortes.jpg). `CLAUDE.md` explica el spec.

Escribí `plantilla.json`: un spec que **replique la estructura** de la referencia para reusarla con otros crudos:
- `format.duration` igual o parecida a la referencia (máx. 20 s). Planos con los mismos cortes (redondeados a la
  grilla de beats), `clip` = "@1" en todos, `src_in` 0, velocidades, zooms y transiciones parecidas.
- Escenas de texto con la misma cantidad de líneas, tamaños, posiciones (`y`), tipo (display/serif/emoji) y ritmo
  (`delay`) que la referencia. Usá los textos de la referencia: sirven de ejemplo de qué va en cada campo.
- `style` con colores y oscurecido parecidos; `music` synth con bpm/drop/gap según el análisis; `footer` si hay pie fijo.
Validá con `reels check plantilla.json` (los errores de clip "@1" son esperables: ignoralos, corregí el resto).
Escribí también `reglas.md` (5–10 bullets): qué hace reconocible a este estilo (ritmo, cantidad de texto, dónde va,
acentos, transiciones, cierre), para respetarlo en el futuro sin volver a mirar la referencia.
Terminá con un resumen de 2 líneas en español rioplatense de cómo es el estilo."""


def learn_style(ref: Path, nombre: str, descripcion: str = "", cliente: str = "", emit: Emit = _noop,
                cancel: threading.Event | None = None, runner: ClaudeRunner | None = None) -> dict:
    import json
    import time

    from pydantic import ValidationError

    from engine.spec import Spec

    from . import settings

    runner = runner or runner_for("estilo")
    ws = settings.local_dir() / "estilos" / f"{projects.slugify(nombre)}-{int(time.time())}"
    (ws / "entrada" / "referencias").mkdir(parents=True)
    (ws / "entrada" / "crudos").mkdir(parents=True)
    shutil.copy2(ref, ws / "entrada" / "referencias" / ref.name)
    shutil.copy2(projects.TEMPLATE, ws / "CLAUDE.md")
    emit({"type": "status", "text": "Analizando la referencia…"})
    analyze.analyze_project(ws)
    emit({"type": "status", "text": "Claude está estudiando el estilo…"})
    res = runner.run(ws, STYLE_PROMPT, None, emit, cancel)
    if not res.ok:
        return {"ok": False, "message": res.text, "error": res.error}
    pj = ws / "plantilla.json"
    try:
        Spec.model_validate(json.loads(pj.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, ValidationError) as e:
        return {"ok": False, "message": f"Claude no dejó una plantilla válida: {str(e)[:200]}"}
    reglas = (ws / "reglas.md").read_text(encoding="utf-8") if (ws / "reglas.md").exists() else ""
    cortes = next(iter((ws / "analisis").glob("*/cortes.jpg")), None)
    t = projects.save_template(pj, nombre, descripcion or res.text[:240], f"referencia {ref.name}", reglas, cortes,
                               cliente)
    shutil.rmtree(ws / "entrada", ignore_errors=True)  # el video ya no hace falta
    return {"ok": True, "message": res.text, "plantilla": t["id"]}
