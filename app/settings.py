"""Ajustes locales de la máquina (no se sincronizan) y detección de ffmpeg / Chromium / Claude Code."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def local_dir() -> Path:
    base = os.environ.get("REELS_LOCAL") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ReelsStudio"
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


CONFIG = local_dir() / "config.json"
DEFAULTS = {"data_dir": None, "user_name": "", "quality": "final", "claude_model": None, "claude_exe": None,
            "auto_update": True}


def load() -> dict:
    try:
        return {**DEFAULTS, **json.loads(CONFIG.read_text(encoding="utf-8"))}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULTS)


def save(cfg: dict) -> dict:
    cfg = {**load(), **cfg}
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def suggested_data_dir() -> Path:
    """OneDrive si está (se sincroniza entre la compu y la laptop); si no, Documentos."""
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if os.environ.get(var) and Path(os.environ[var]).is_dir():
            return Path(os.environ[var]) / "ReelsStudio"
    gd = Path.home() / "Google Drive" / "Mi unidad"
    if gd.is_dir():
        return gd / "ReelsStudio"
    return Path.home() / "Documents" / "ReelsStudio"


def data_dir() -> Path:
    d = os.environ.get("REELS_DATA") or load().get("data_dir") or suggested_data_dir()
    p = Path(d)
    (p / "clientes").mkdir(parents=True, exist_ok=True)
    (p / "proyectos").mkdir(parents=True, exist_ok=True)
    return p


def machine() -> str:
    return os.environ.get("COMPUTERNAME") or socket.gethostname()


def venv_scripts() -> Path:
    return REPO / ".venv" / ("Scripts" if os.name == "nt" else "bin")


_CLAUDE_CACHE: dict[str, str | None] = {}


def _claude_version(exe: str) -> tuple[int, ...]:
    try:
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20, env=env,
                             stdin=subprocess.DEVNULL, creationflags=NO_WINDOW).stdout
        return tuple(int(x) for x in out.split()[0].split("."))
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        return ()


def claude_candidates() -> list[str]:
    """Todas las instalaciones: instalador nativo (~/.local/bin) y los `claude` de npm que haya en el PATH."""
    found = []
    native = Path.home() / ".local" / "bin" / ("claude.exe" if os.name == "nt" else "claude")
    if native.exists():
        found.append(str(native))
    for d in os.environ.get("PATH", "").split(os.pathsep):
        for name in (("claude.cmd", "claude.exe") if os.name == "nt" else ("claude",)):
            p = Path(d) / name
            if p.suffix == ".cmd":
                # el atajo de npm pasa por cmd.exe, que rompe argumentos con saltos de línea: usar el exe real
                real = Path(d) / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
                p = real if real.is_file() else p
            if p.is_file() and str(p) not in found:
                found.append(str(p))
    return found


def forget_claude():
    """Después de instalar/actualizar: volver a buscar la instalación más nueva."""
    _CLAUDE_CACHE.clear()


def claude_exe() -> str | None:
    """La instalación más nueva (puede haber varias: npm viejo, npm de nvm, instalador nativo)."""
    forced = load().get("claude_exe")
    if forced:
        return forced
    if "exe" not in _CLAUDE_CACHE:
        cands = [(v, c) for c in claude_candidates() if (v := _claude_version(c))]
        _CLAUDE_CACHE["exe"] = max(cands)[1] if cands else shutil.which("claude")
    return _CLAUDE_CACHE["exe"]


def system_status() -> dict:
    """Para la pantalla de Ajustes: ✓/✗ de cada pieza."""
    from engine.probe import ffmpeg_exe

    st = {}
    try:
        st["ffmpeg"] = {"ok": Path(ffmpeg_exe()).exists(), "detail": Path(ffmpeg_exe()).name}
    except Exception as e:  # noqa: BLE001
        st["ffmpeg"] = {"ok": False, "detail": str(e)}
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            path = Path(p.chromium.executable_path)
        st["chromium"] = {"ok": path.exists(), "detail": "instalado" if path.exists() else "falta instalar"}
    except Exception as e:  # noqa: BLE001
        st["chromium"] = {"ok": False, "detail": str(e)[:200]}
    from .claude_runner import ClaudeRunner

    st["claude"] = ClaudeRunner().status()
    return st
