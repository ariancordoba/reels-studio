"""Ubica spec, clips y fuentes a partir de lo que se le pase al CLI.

Acepta: un spec.json suelto, una carpeta de versión (versiones/v3) o una carpeta de proyecto
(usa la versión actual de proyecto.json, o la última).
Estructura de proyecto:  proyectos/<fecha>-<slug>/{entrada/crudos, versiones/vN/spec.json, proyecto.json}
Clientes:                <datos>/clientes/<slug>/{cliente.json, fonts/}
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import spec as specmod
from .probe import probe


def version_num(p: Path) -> int:
    m = re.fullmatch(r"v(\d+)", p.name)
    return int(m[1]) if m else -1


def versions(project: Path) -> list[Path]:
    vd = project / "versiones"
    return sorted((d for d in vd.iterdir() if d.is_dir() and version_num(d) > 0), key=version_num) if vd.is_dir() else []


def find_project(start: Path) -> Path | None:
    for d in [start, *start.parents]:
        if (d / "proyecto.json").exists():
            return d
    return None


@dataclass
class Target:
    spec_path: Path
    spec: specmod.Spec
    project: Path | None
    clip_dirs: list[Path] = field(default_factory=list)
    font_dirs: list[Path] = field(default_factory=list)

    @property
    def out_dir(self) -> Path:
        return self.spec_path.parent

    def clips(self) -> dict[str, Path]:
        found = {}
        for s in self.spec.shots:
            for d in self.clip_dirs:
                if (d / s.clip).exists():
                    found[s.clip] = d / s.clip
                    break
        return found

    def check(self) -> tuple[list[str], list[str]]:
        durs = {}
        for name, p in self.clips().items():
            try:
                durs[name] = probe(p).duration
            except ValueError as e:
                return [str(e)], []
        return specmod.check(self.spec, durs)


def resolve(arg: str | Path, clips: list[Path] | None = None) -> Target:
    p = Path(arg).resolve()
    if p.is_dir():
        if (p / "spec.json").exists():
            spec_path = p / "spec.json"
        elif (p / "proyecto.json").exists():
            meta = json.loads((p / "proyecto.json").read_text(encoding="utf-8"))
            cur = meta.get("version_actual")
            vs = versions(p)
            vdir = p / "versiones" / cur if cur and (p / "versiones" / cur / "spec.json").exists() else (vs[-1] if vs else None)
            if vdir is None:
                raise FileNotFoundError(f"el proyecto {p.name} todavía no tiene versiones")
            spec_path = vdir / "spec.json"
        else:
            raise FileNotFoundError(f"{p} no tiene spec.json ni proyecto.json")
    elif p.exists():
        spec_path = p
    else:
        raise FileNotFoundError(f"no existe {p}")
    spec = specmod.load(spec_path)
    project = find_project(spec_path.parent)
    clip_dirs = [*(clips or []), spec_path.parent]
    font_dirs = []
    if project:
        clip_dirs += [project / "entrada" / "crudos", project / "entrada"]
        font_dirs.append(project / "fonts")
        meta = json.loads((project / "proyecto.json").read_text(encoding="utf-8"))
        slug = meta.get("cliente") or spec.client
        if slug:
            font_dirs.append(project.parent.parent / "clientes" / slug / "fonts")
    return Target(spec_path, spec, project, clip_dirs, font_dirs)
