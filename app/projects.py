"""Clientes, proyectos y versiones sobre la carpeta de datos (sincronizada).

<datos>/clientes/<slug>/cliente.json, fonts/, logo.png
<datos>/proyectos/<fecha>-<slug>/{entrada/, analisis/, versiones/vN/, CLAUDE.md, cliente.json, proyecto.json}
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path

from engine.project import version_num, versions

from . import settings

TEMPLATE = settings.REPO / "workspace_template" / "CLAUDE.md"
STAGES = ["crudos", "guion", "vista_previa", "render", "entregado"]


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:48] or "video"


def read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def retry(fn, tries: int = 8):
    """Escrituras en la carpeta sincronizada: OneDrive/Drive pueden bloquearla un instante."""
    for i in range(tries):
        try:
            return fn()
        except OSError:
            if i == tries - 1:
                raise
            time.sleep(min(0.5 * (i + 1), 3))


def write_json(p: Path, data):
    def _w():
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)
    retry(_w)


# ── clientes
CLIENT_DEFAULTS = {
    "nombre": "", "accent": "#caffbf", "text": "#ffffff", "display_font": "", "serif_font": "",  # vacío = que Claude elija según el rubro
    "footer": [], "darken": 0.32, "logo": None, "notas": "",
}


def clients_dir() -> Path:
    return settings.data_dir() / "clientes"


def list_clients() -> list[dict]:
    out = []
    for d in sorted(clients_dir().iterdir()):
        c = read_json(d / "cliente.json")
        if c:
            out.append({**CLIENT_DEFAULTS, **c, "slug": d.name, "fonts": font_files(d)})
    return out


def font_files(cdir: Path) -> list[str]:
    fd = cdir / "fonts"
    return sorted(f.name for f in fd.iterdir() if f.suffix.lower() in (".ttf", ".otf", ".woff", ".woff2")) if fd.is_dir() else []


def get_client(slug: str) -> dict | None:
    d = clients_dir() / slug
    c = read_json(d / "cliente.json")
    return {**CLIENT_DEFAULTS, **c, "slug": slug, "fonts": font_files(d)} if c else None


def save_client(data: dict, slug: str | None = None) -> dict:
    slug = slug or data.get("slug") or slugify(data.get("nombre", "cliente"))
    d = clients_dir() / slug
    (d / "fonts").mkdir(parents=True, exist_ok=True)
    cur = read_json(d / "cliente.json", {})
    keep = {k: v for k, v in data.items() if k in CLIENT_DEFAULTS}
    write_json(d / "cliente.json", {**CLIENT_DEFAULTS, **cur, **keep})
    return get_client(slug)


# ── proyectos
def projects_dir() -> Path:
    return settings.data_dir() / "proyectos"


def meta(project: Path) -> dict:
    return read_json(project / "proyecto.json", {})


def save_meta(project: Path, **changes) -> dict:
    m = {**meta(project), **changes, "actualizado": datetime.now().isoformat(timespec="seconds")}
    write_json(project / "proyecto.json", m)
    return m


def safe_transfer(src: Path, dst: Path, move: bool, tries: int = 8):
    """Copiar/mover a la carpeta de datos aunque OneDrive/Drive la esté sincronizando.

    Al poner archivos nuevos, OneDrive bloquea la carpeta un instante: os.rename falla y la copia nativa de
    Windows (CopyFile2, la que usa shutil.copy2) a veces devuelve "no se encuentra el archivo". Se reintenta y,
    si sigue, se copia leyendo y escribiendo a mano.
    """
    src, dst = Path(src), Path(dst)
    last = None
    for i in range(tries):
        try:
            if move:
                try:
                    os.replace(src, dst)  # mismo disco: instantáneo
                    return
                except OSError:
                    pass
            tmp = dst.with_name(dst.name + ".parcial")
            with open(src, "rb") as fi, open(tmp, "wb") as fo:
                shutil.copyfileobj(fi, fo, 8 << 20)
            os.replace(tmp, dst)
            if move:
                src.unlink(missing_ok=True)
            return
        except OSError as e:
            last = e
            time.sleep(min(0.5 * (i + 1), 3))
    raise OSError(f"no pude guardar «{src.name}» en la carpeta de datos (¿OneDrive/Drive sincronizando o sin espacio?): {last}")


def create_project(titulo: str, cliente: str, crudos: list[Path], referencias: list[Path], instrucciones: str,
                   duracion: float | None = None, move: bool = False) -> Path:
    base = projects_dir() / f"{date.today():%Y-%m-%d}-{slugify(titulo)}"
    p, n = base, 2
    while p.exists():
        p, n = base.with_name(f"{base.name}-{n}"), n + 1
    try:
        for sub in ("entrada/crudos", "entrada/referencias", "analisis", "versiones"):
            (p / sub).mkdir(parents=True)
        for f in crudos:
            safe_transfer(Path(f), p / "entrada" / "crudos" / Path(f).name, move)
        for f in referencias:
            safe_transfer(Path(f), p / "entrada" / "referencias" / Path(f).name, move)
        txt = instrucciones.strip()
        if duracion:
            txt += f"\n\nDuración deseada: {duracion:g} s."
        retry(lambda: (p / "entrada" / "instrucciones.md").write_text(txt + "\n", encoding="utf-8"))
        safe_transfer(TEMPLATE, p / "CLAUDE.md", move=False)
        snapshot_client(p, cliente)
        save_meta(p, titulo=titulo, cliente=cliente, creado=datetime.now().isoformat(timespec="seconds"),
                  version_actual=None, session_id=None, etapa="crudos", duracion=duracion, pendiente=None,
                  prioridad="media", entrega=None)
    except Exception:
        # todo o nada: que no quede un proyecto a medio crear (invisible en la app)
        shutil.rmtree(p, ignore_errors=True)
        raise
    return p


def snapshot_client(project: Path, slug: str):
    """Copia cliente.json al proyecto: Claude sólo lee dentro del proyecto."""
    c = get_client(slug) or {**CLIENT_DEFAULTS, "nombre": slug, "slug": slug}
    write_json(project / "cliente.json", c)


def list_projects() -> list[dict]:
    out = []
    for d in projects_dir().iterdir():
        if (d / "proyecto.json").exists():
            out.append(project_info(d))
    return sorted(out, key=lambda x: x.get("actualizado") or "", reverse=True)


def project_info(p: Path) -> dict:
    m = meta(p)
    vs = []
    for v in versions(p):
        spec = read_json(v / "spec.json")
        vs.append({
            "id": v.name,
            "fecha": datetime.fromtimestamp(v.stat().st_mtime).isoformat(timespec="minutes"),
            "resumen": (v / "resumen.txt").read_text(encoding="utf-8").strip() if (v / "resumen.txt").exists() else "",
            "pedido": (v / "pedido.txt").read_text(encoding="utf-8").strip() if (v / "pedido.txt").exists() else "",
            "tiene_spec": spec is not None,
            "duracion": (spec or {}).get("format", {}).get("duration"),
            "video": (v / "video.mp4").exists(),
            "borrador": (v / "borrador.mp4").exists(),
            "stills": sorted(f.name for f in (v / "stills").glob("t*.jpg")) if (v / "stills").is_dir() else [],
            "tamano_mb": round((v / "video.mp4").stat().st_size / 1e6, 1) if (v / "video.mp4").exists() else None,
        })
    return {**m, "id": p.name, "path": str(p), "versiones": vs, "lock": read_lock(p)}


def next_version(project: Path) -> Path:
    vs = versions(project)
    n = version_num(vs[-1]) + 1 if vs else 1
    d = project / "versiones" / f"v{n}"
    d.mkdir(parents=True)
    return d


def current_version(project: Path) -> Path | None:
    cur = meta(project).get("version_actual")
    if cur and (project / "versiones" / cur / "spec.json").exists():
        return project / "versiones" / cur
    good = [v for v in versions(project) if (v / "spec.json").exists()]
    return good[-1] if good else None


# ── lock: que dos máquinas no rendericen el mismo proyecto a la vez
LOCK_STALE_S = 3 * 3600


def read_lock(project: Path) -> dict | None:
    lk = read_json(project / "proyecto.lock")
    if lk and time.time() - lk.get("ts", 0) > LOCK_STALE_S:
        return None
    return lk


class Locked(Exception):
    pass


class project_lock:
    def __init__(self, project: Path, what: str):
        self.p, self.what = project, what

    def __enter__(self):
        lk = read_lock(self.p)
        if lk and lk.get("machine") != settings.machine():
            raise Locked(f"'{lk.get('machine')}' está trabajando en este proyecto ({lk.get('what')}). Esperá a que termine.")
        write_json(self.p / "proyecto.lock", {"machine": settings.machine(), "what": self.what, "ts": time.time()})
        return self

    def __exit__(self, *exc):
        lk = read_lock(self.p)
        if lk and lk.get("machine") == settings.machine():
            (self.p / "proyecto.lock").unlink(missing_ok=True)


# ── música y plantillas (compartidas entre proyectos)
def list_music() -> list[dict]:
    d = settings.data_dir() / "musica"
    idx = read_json(d / "musica.json", {}) if d.is_dir() else {}
    return [{"archivo": k, **v, "path": str(d / k), "tamano_mb": round((d / k).stat().st_size / 1e6, 1)}
            for k, v in idx.items() if (d / k).exists()]


def templates_dir() -> Path:
    d = settings.data_dir() / "plantillas"
    d.mkdir(exist_ok=True)
    return d


def list_templates() -> list[dict]:
    from engine.autofill import fields

    out = []
    for f in sorted(templates_dir().glob("*.json")):
        t = read_json(f)
        if t:
            spec = t.get("spec", {})
            out.append({"id": f.stem, **{k: v for k, v in t.items() if k != "spec"},
                        "duracion": spec.get("format", {}).get("duration"), "escenas": len(spec.get("scenes", [])),
                        "planos": len(spec.get("shots", [])), "campos": fields(spec),
                        "preview": (templates_dir() / f"{f.stem}.jpg").exists()})
    return out


def get_template(tid: str) -> dict | None:
    return read_json(templates_dir() / f"{Path(tid).name}.json")


def save_template(spec_path: Path, nombre: str, descripcion: str, origen: str, reglas: str = "",
                  preview: Path | None = None, cliente: str = "") -> dict:
    tid = slugify(nombre)
    write_json(templates_dir() / f"{tid}.json", {
        "nombre": nombre, "descripcion": descripcion, "origen": origen, "cliente": cliente, "reglas": reglas,
        "creada": datetime.now().isoformat(timespec="seconds"), "spec": read_json(spec_path)})
    if preview and preview.exists():
        shutil.copy2(preview, templates_dir() / f"{tid}.jpg")
    return {"id": tid, "nombre": nombre}


# ── aprendizajes: preferencias que Claude detecta en los pedidos y quedan para el cliente
def client_learnings_path(slug: str) -> Path:
    return clients_dir() / slug / "aprendizajes.md"


def merge_learnings(project: Path):
    """Pasa al cliente las líneas nuevas que Claude anotó en el proyecto (sin duplicar)."""
    slug = meta(project).get("cliente")
    src = project / "aprendizajes.md"
    if not slug or not src.exists() or not (clients_dir() / slug).is_dir():
        return
    dst = client_learnings_path(slug)
    have = dst.read_text(encoding="utf-8").splitlines() if dst.exists() else []
    norm = {l.strip().lower() for l in have}
    new = [l for l in src.read_text(encoding="utf-8").splitlines()
           if l.strip().startswith("-") and l.strip().lower() not in norm]
    if new:
        dst.write_text("\n".join([*have, *new]).strip() + "\n", encoding="utf-8")


def sync_shared(project: Path):
    """Deja en el proyecto lo que Claude necesita de afuera (sólo lee dentro del proyecto):
    la marca del cliente y la lista de pistas con licencia."""
    slug = meta(project).get("cliente", "")
    shutil.copy2(TEMPLATE, project / "CLAUDE.md")  # las instrucciones mejoran con las actualizaciones
    snapshot_client(project, slug)
    learned = client_learnings_path(slug) if slug else None
    if learned and learned.exists() and not (project / "aprendizajes.md").exists():
        shutil.copy2(learned, project / "aprendizajes.md")
    tracks = [{"titulo": t["titulo"], "licencia": t["licencia"], "path": t["path"]} for t in list_music()]
    write_json(project / "musica_disponible.json", tracks)
