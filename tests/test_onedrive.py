"""Carpeta de datos sincronizada (OneDrive/Drive): bloqueos momentáneos al crear proyectos."""
import importlib
import os

import pytest


@pytest.fixture()
def projects(tmp_path, monkeypatch):
    monkeypatch.setenv("REELS_DATA", str(tmp_path / "datos"))
    monkeypatch.setenv("REELS_LOCAL", str(tmp_path / "local"))
    from app import projects, settings
    importlib.reload(settings)
    importlib.reload(projects)
    monkeypatch.setattr(projects.time, "sleep", lambda s: None)
    return projects


def make_files(tmp_path, n=8):
    d = tmp_path / "subidas"
    d.mkdir()
    out = []
    for i in range(n):
        f = d / f"IMG_{i} (1).jpg"
        f.write_bytes(os.urandom(200_000))
        out.append(f)
    return out


def test_retries_when_sync_locks_folder(projects, tmp_path, monkeypatch):
    """Como en OneDrive: después de 4 archivos la carpeta se bloquea un rato (rename y copia nativa fallan)."""
    files = make_files(tmp_path)
    real_replace, calls = os.replace, {"n": 0}

    def flaky_replace(a, b):
        calls["n"] += 1
        if 5 <= calls["n"] <= 9:
            raise FileNotFoundError(2, "El sistema no puede encontrar el archivo especificado")
        return real_replace(a, b)

    monkeypatch.setattr(projects.os, "replace", flaky_replace)
    projects.save_client({"nombre": "Marca"})
    p = projects.create_project("Video", "marca", files, [], "instrucciones", None, move=False)
    got = sorted(f.name for f in (p / "entrada" / "crudos").iterdir())
    assert got == sorted(f.name for f in files), "están los 8 archivos"
    assert all((p / "entrada" / "crudos" / f.name).read_bytes() == f.read_bytes() for f in files)
    assert all(f.exists() for f in files), "copiar no borra los originales"
    assert projects.meta(p)["titulo"] == "Video"


def test_failure_leaves_no_half_project(projects, tmp_path, monkeypatch):
    files = make_files(tmp_path, 3)

    def always_fail(*a, **k):
        raise OSError("disco lleno")

    monkeypatch.setattr(projects, "safe_transfer", always_fail)
    projects.save_client({"nombre": "Marca"})
    with pytest.raises(OSError):
        projects.create_project("Video", "marca", files, [], "", None)
    assert not list(projects.projects_dir().iterdir()), "no queda un proyecto fantasma"
    assert all(f.exists() for f in files), "los archivos subidos siguen ahí"


def test_safe_transfer_falls_back_to_manual_copy(projects, tmp_path, monkeypatch):
    src = tmp_path / "a.mov"
    src.write_bytes(b"x" * 1000)
    dst = tmp_path / "dest" / "a.mov"
    dst.parent.mkdir()
    real_replace = os.replace
    # el rename directo (mover) falla siempre; el reemplazo del archivo .parcial funciona
    monkeypatch.setattr(projects.os, "replace",
                        lambda a, b: (_ for _ in ()).throw(PermissionError("bloqueado")) if str(a) == str(src)
                        else real_replace(a, b))
    projects.safe_transfer(src, dst, move=True)
    assert dst.read_bytes() == b"x" * 1000 and not src.exists()
    assert not list(dst.parent.glob("*.parcial"))
