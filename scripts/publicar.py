"""Publica una versión nueva: las apps de tus amigos la descargan e instalan solas.

    uv run python scripts/publicar.py --notas "qué cambió"            # 0.2.0 → 0.2.1
    uv run python scripts/publicar.py --menor --notas "…"              # 0.2.1 → 0.3.0
    uv run python scripts/publicar.py --version 1.0.0 --notas "…"

Pasos: tests → sube VERSION → compila la UI → arma el zip → revisa que no se publique nada privado →
commit + tag + push → release en GitHub con el zip adjunto.
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GITHUB_REPO = "ariancordoba/reels-studio"
# nada de esto puede aparecer en lo que se publica (datos personales, clientes, credenciales)
PRIVATE = re.compile(r"gasolero|@gmail\.com|Balmoral|Liga [ÁA]rea|Rel[áa]mpago|Permitly|Pichincha|Temperley|"
                     r"sk-ant-|ghp_|github_pat_|C:\\Users\\arian|D:\\Users\\arian", re.I)
PRIVATE_PATHS = ("ejemplo/", "referencia_motor_v0/", "PLAN.md", "ui_referencia.webp", ".claude/")


def run(cmd, **kw):
    print("›", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, cwd=REPO, check=True, **kw)


def out(cmd) -> str:
    return subprocess.run(cmd, cwd=REPO, check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def gh() -> str:
    for c in (shutil.which("gh"), r"C:\Program Files\GitHub CLI\gh.exe"):
        if c and Path(c).exists():
            return c
    sys.exit("No encuentro gh (GitHub CLI). Instalalo con: winget install GitHub.cli")


def bump(v: str, kind: str) -> str:
    major, minor, patch = (int(x) for x in v.split("."))
    return f"{major + 1}.0.0" if kind == "mayor" else f"{major}.{minor + 1}.0" if kind == "menor" else f"{major}.{minor}.{patch + 1}"


def privacy_check():
    """Frena la publicación si algo privado está por subirse."""
    files = out(["git", "ls-files", "--cached"]).splitlines()
    bad_paths = [f for f in files if f.startswith(PRIVATE_PATHS)]
    hits = []
    for f in files:
        if f.endswith((".lock", "package-lock.json")) or f.startswith("ui/dist/") or f == "scripts/publicar.py":
            continue
        p = REPO / f
        try:
            txt = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for i, line in enumerate(txt.splitlines(), 1):
            if PRIVATE.search(line):
                hits.append(f"{f}:{i}: {line.strip()[:100]}")
    email = out(["git", "config", "user.email"])
    if not email.endswith("@users.noreply.github.com"):
        hits.append(f"git user.email es {email!r}: usá el mail anónimo de GitHub")
    if bad_paths or hits:
        print("\nFRENADO: hay cosas privadas por publicarse:")
        for x in bad_paths + hits:
            print("  -", x)
        sys.exit(1)
    print("✓ revisión de privacidad: nada privado")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--version")
    g.add_argument("--menor", action="store_true")
    g.add_argument("--mayor", action="store_true")
    ap.add_argument("--notas", required=True, help="qué cambió (se muestra en la app de tus amigos)")
    ap.add_argument("--sin-tests", action="store_true")
    a = ap.parse_args()

    if out(["git", "rev-parse", "--abbrev-ref", "HEAD"]) != "main":
        sys.exit("Publicá desde la rama main")
    cur = (REPO / "VERSION").read_text(encoding="utf-8").strip()
    new = a.version or bump(cur, "mayor" if a.mayor else "menor" if a.menor else "parche")
    if out(["git", "tag", "-l", f"v{new}"]):
        sys.exit(f"La versión {new} ya existe")
    print(f"Publicando {cur} → {new}")

    if not a.sin_tests:
        run([sys.executable, "-m", "pytest", "-q", "-m", "not slow"])
    (REPO / "VERSION").write_text(new + "\n", encoding="utf-8")
    run([sys.executable, "scripts/empaquetar.py", "--notas", a.notas])  # compila la UI y arma el zip
    run(["git", "add", "-A"])
    privacy_check()
    run(["git", "commit", "-m", f"Versión {new}\n\n{a.notas}"])
    run(["git", "tag", f"v{new}"])
    run(["git", "push", "origin", "main", "--tags"])
    zpath = REPO / "dist" / f"reels-studio-{new}.zip"
    run([gh(), "release", "create", f"v{new}", str(zpath), "--repo", GITHUB_REPO, "--title", f"Reels Studio {new}",
         "--notes", a.notas + "\n\nSe instala sola: la app la descarga y la aplica al cerrarse."])
    print(f"\n✓ Publicada la {new}. Las apps la van a descargar solas (al abrir, o en menos de 6 horas).")


if __name__ == "__main__":
    main()
