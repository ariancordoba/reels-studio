"""Arma el paquete para compartir: dist/reels-studio-<versión>.zip + dist/update.json

    uv run python scripts/empaquetar.py [--url https://…/reels-studio-X.zip] [--notas "qué cambió"]

El zip lleva sólo lo necesario para usar la app (sin tests, sin videos de ejemplo, sin fuentes de la UI).
Publicarlo: subir el zip como asset de un release de GitHub (tag vX.Y.Z), o subir zip + update.json
a cualquier lado y poner la URL del update.json en update_source.txt.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INCLUDE = ["app", "engine", "assets", "workspace_template", "ui/dist", "pyproject.toml", "uv.lock",
           ".python-version", "INSTALAR.bat", "ABRIR.bat", "DESINSTALAR.bat", "LEEME.txt", "VERSION",
           "update_source.txt", "README.md"]
SKIP_DIRS = {"__pycache__", ".pytest_cache"}


def files() -> list[Path]:
    out = []
    for item in INCLUDE:
        p = REPO / item
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out += [f for f in sorted(p.rglob("*")) if f.is_file() and not SKIP_DIRS & set(f.relative_to(REPO).parts)]
        else:
            sys.exit(f"falta {item}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="URL pública donde va a quedar el zip (para update.json)")
    ap.add_argument("--notas", default="", help="qué cambió en esta versión")
    ap.add_argument("--sin-build", action="store_true", help="no recompilar la UI")
    a = ap.parse_args()
    if not a.sin_build and (REPO / "ui" / "node_modules").is_dir():
        subprocess.run("npm run build", cwd=REPO / "ui", shell=True, check=True)
    ver = (REPO / "VERSION").read_text(encoding="utf-8").strip()
    dist = REPO / "dist"
    dist.mkdir(exist_ok=True)
    zpath = dist / f"reels-studio-{ver}.zip"
    fl = files()
    manifest = "\n".join(f.relative_to(REPO).as_posix() for f in fl) + "\nMANIFEST.txt\n"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in fl:
            z.write(f, f"reels-studio/{f.relative_to(REPO).as_posix()}")
        z.writestr("reels-studio/MANIFEST.txt", manifest)
    sha = hashlib.sha256(zpath.read_bytes()).hexdigest()
    upd = {"version": ver, "url": a.url or f"<subí {zpath.name} y poné acá su URL>", "sha256": sha, "notas": a.notas}
    (dist / "update.json").write_text(json.dumps(upd, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{zpath}  ({zpath.stat().st_size / 1e6:.1f} MB, {len(fl)} archivos)\nsha256 {sha}\n{dist / 'update.json'}")


if __name__ == "__main__":
    main()
