"""Referencias y crudos → material para que Claude arme el guion.

Por cada video deja en analisis/<nombre>/:
  info.json      duración, fps, resolución, cortes detectados, tempo y beats (si tiene audio), movimiento por segundo
  hoja_NN.jpg    hojas de contacto con la hora de cada cuadro (Claude las lee como imágenes)
  cortes.jpg     (referencias) un cuadro por plano, justo después de cada corte
Y un analisis/resumen.md con todo junto, en texto.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import cv2
import numpy as np

from .probe import NO_WINDOW, ffmpeg_exe, probe

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def shrink_image(path: Path, max_side: int = 1600) -> Path:
    """Imágenes de referencia: a lo sumo 1600 px y en JPG (se ven igual y Claude gasta menos al mirarlas)."""
    img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return path
    h, w = img.shape[:2]
    k = min(1.0, max_side / max(h, w))
    if k < 1:
        img = cv2.resize(img, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
    out = path.with_suffix(".jpg")
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if ok:
        buf.tofile(str(out))
        if out != path:
            path.unlink(missing_ok=True)
    return out
THUMB_W = 270  # vertical 270×480 por cuadro: legible y liviano
COLS, ROWS = 6, 3


def frames_at(path: Path, times: list[float], width: int = THUMB_W) -> list[np.ndarray]:
    """Cuadros en los segundos pedidos (ffmpeg aplica la rotación)."""
    out = []
    for t in times:
        r = subprocess.run([ffmpeg_exe(), "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", str(path), "-frames:v", "1",
                            "-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                           capture_output=True, creationflags=NO_WINDOW)
        img = cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR) if r.stdout else None
        out.append(img)
    return out


def frames_every(path: Path, step: float, duration: float, width: int = THUMB_W) -> tuple[list[float], list[np.ndarray]]:
    """Un cuadro cada `step` segundos en una sola pasada de ffmpeg."""
    info = probe(path)
    h = int(round(width * info.height / info.width / 2)) * 2
    r = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", str(path), "-vf", f"fps=1/{step},scale={width}:{h}",
                        "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True, creationflags=NO_WINDOW)
    n = len(r.stdout) // (width * h * 3)
    imgs = list(np.frombuffer(r.stdout[: n * width * h * 3], np.uint8).reshape(n, h, width, 3))
    times = [round(i * step, 2) for i in range(n)]
    keep = [i for i, t in enumerate(times) if t < duration - 0.05]
    return [times[i] for i in keep], [imgs[i] for i in keep]


def sheet(images: list[np.ndarray | None], labels: list[str], cols: int = COLS) -> np.ndarray:
    ok = [im for im in images if im is not None]
    h, w = ok[0].shape[:2]
    rows = (len(images) + cols - 1) // cols
    pad, lab = 6, 26
    s = np.full((rows * (h + lab + pad) + pad, cols * (w + pad) + pad, 3), 20, np.uint8)
    for i, (im, text) in enumerate(zip(images, labels)):
        r, c = divmod(i, cols)
        y, x = pad + r * (h + lab + pad), pad + c * (w + pad)
        if im is not None:
            im = cv2.resize(im, (w, h)) if im.shape[:2] != (h, w) else im
            s[y:y + h, x:x + w] = im
        cv2.putText(s, text, (x + 4, y + h + 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 240, 240), 1, cv2.LINE_AA)
    return s


def detect_cuts(path: Path, threshold: float = 0.3) -> list[float]:
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path), "-vf",
                        f"scale=270:-2,select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    cuts = [round(float(m), 3) for m in re.findall(r"pts_time:([\d.]+)", r.stderr)]
    merged = []
    for c in cuts:  # dos "cortes" a menos de 0.25 s son el mismo (flash, látigo)
        if not merged or c - merged[-1] > 0.25:
            merged.append(c)
    return merged


def motion_per_second(path: Path, duration: float) -> list[float]:
    """Cuánto se mueve la imagen en cada segundo (0–100): sirve para encontrar los momentos de acción."""
    r = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", str(path), "-vf", "fps=6,scale=96:-2,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, creationflags=NO_WINDOW)
    buf = np.frombuffer(r.stdout, np.uint8)
    probe_r = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", str(path), "-vf", "scale=96:-2", "-frames:v", "1",
                              "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, creationflags=NO_WINDOW)
    px = len(probe_r.stdout)
    if not px or len(buf) < 2 * px:
        return []
    fr = buf[: len(buf) // px * px].reshape(-1, px).astype(np.float32)
    diff = np.abs(np.diff(fr, axis=0)).mean(axis=1)
    per_s = [float(diff[i * 6:(i + 1) * 6].mean()) for i in range(int(np.ceil(len(diff) / 6)))]
    top = max(per_s) or 1
    return [round(100 * v / top) for v in per_s][: int(np.ceil(duration))]


def interest_curve(path: Path, rate: float = 4.0) -> tuple[np.ndarray, np.ndarray]:
    """Qué tan "bueno" es cada momento del clip (0–1), `rate` muestras por segundo.

    Mezcla movimiento (algo pasa) y nitidez (no está movido ni fuera de foco). Penaliza cuadros muy
    oscuros o quemados. Sirve para elegir planos sin mirar las imágenes (armado automático, sin Claude).
    """
    w = 160
    info = probe(path)
    h = int(round(w * info.height / info.width / 2)) * 2
    r = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", str(path), "-vf", f"fps={rate},scale={w}:{h},format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, creationflags=NO_WINDOW)
    n = len(r.stdout) // (w * h)
    if n < 2:
        return np.zeros(1), np.zeros(1)
    fr = np.frombuffer(r.stdout[: n * w * h], np.uint8).reshape(n, h, w).astype(np.float32)
    motion = np.concatenate([[0], np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))])
    sharp = np.array([cv2.Laplacian(f, cv2.CV_32F).var() for f in fr])
    bright = fr.mean(axis=(1, 2))
    norm = lambda x: (x - np.percentile(x, 5)) / (np.percentile(x, 95) - np.percentile(x, 5) + 1e-6)
    m, s = np.clip(norm(motion), 0, 1), np.clip(norm(sharp), 0, 1)
    # mucho movimiento con poca nitidez = cámara sacudida: no suma
    score = 0.55 * m * (0.4 + 0.6 * s) + 0.45 * s
    score *= np.clip(1 - np.abs(bright - 128) / 160, 0.3, 1)
    score = np.convolve(score, np.ones(3) / 3, mode="same")
    return np.arange(n) / rate, score


def tempo(path: Path) -> dict | None:
    try:
        import librosa
    except ImportError:
        return None
    r = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "22050",
                        "-f", "f32le", "-"], capture_output=True, creationflags=NO_WINDOW)
    y = np.frombuffer(r.stdout, np.float32)
    if len(y) < 22050 * 2 or np.abs(y).max() < 1e-3:
        return None
    bpm, beats = librosa.beat.beat_track(y=y, sr=22050, units="time")
    bpm = float(np.atleast_1d(bpm)[0])
    onset = librosa.onset.onset_strength(y=y, sr=22050)
    # momento de mayor energía (el "drop"): máximo del RMS suavizado
    rms = librosa.feature.rms(y=y)[0]
    k = max(1, int(0.5 * 22050 / 512))
    smooth = np.convolve(rms, np.ones(k) / k, mode="same")
    jump = np.diff(smooth, prepend=smooth[0])
    drop = float(librosa.frames_to_time(int(np.argmax(jump)), sr=22050))
    return {"bpm": round(bpm, 1), "beats": [round(float(b), 3) for b in beats][:200],
            "drop_estimado": round(drop, 2), "onset_medio": round(float(onset.mean()), 3)}


def analyze_video(path: Path, out: Path, kind: str) -> dict:
    """kind: 'referencia' | 'crudo'."""
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.jpg"):
        old.unlink()
    info = probe(path)
    d = info.duration
    # referencia: cada 0.5 s (el ritmo de los textos importa); crudos: cada 0.5 s hasta 60 s, después más espaciado
    step = 0.5 if kind == "referencia" or d <= 60 else max(1.0, d / 90)
    times, imgs = frames_every(path, step, d)
    per_sheet = COLS * ROWS
    sheets = []
    for n, i in enumerate(range(0, len(times), per_sheet), start=1):
        ts = times[i:i + per_sheet]
        p = out / f"hoja_{n:02d}.jpg"
        cv2.imwrite(str(p), sheet(imgs[i:i + per_sheet], [f"{t:.1f}s" for t in ts]), [cv2.IMWRITE_JPEG_QUALITY, 82])
        sheets.append(p.name)
    res = {"archivo": path.name, "tipo": kind, "duracion": round(d, 3), "fps": info.fps,
           "resolucion": [info.width, info.height], "rotacion": info.rotation,
           "vertical": info.height > info.width, "hojas": sheets, "paso_hojas_s": step}
    if kind == "referencia":
        cuts = detect_cuts(path)
        res["cortes"] = cuts
        starts = [0.0, *cuts]
        ts = [min(s + 0.15, d - 0.05) for s in starts]
        cv2.imwrite(str(out / "cortes.jpg"), sheet(frames_at(path, ts), [f"plano {i + 1} · {s:.2f}s" for i, s in enumerate(starts)]),
                    [cv2.IMWRITE_JPEG_QUALITY, 82])
        res["duracion_planos"] = [round(b - a, 2) for a, b in zip(starts, [*cuts, d])]
    else:
        res["movimiento_por_segundo"] = motion_per_second(path, d)
    if info.has_audio and kind == "referencia":
        res["audio"] = tempo(path)
    (out / "info.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem)[:60]


def summary_md(results: list[dict], images: list[str] | None = None) -> str:
    L = ["# Análisis", "",
         "Hojas de contacto: cada cuadro tiene su segundo abajo. Miralas con Read (son imágenes).", ""]
    if images:
        L += ["## Imágenes de referencia (estilo que ella quiere)",
              "Miralas con Read: tipografías, colores, disposición de textos, tono. Imitá ese estilo.", ""]
        L += [f"- `{i}`" for i in images] + [""]
    for r in results:
        base = f"analisis/{slug(r['archivo'])}"
        L.append(f"## {r['tipo'].capitalize()}: `{r['archivo']}`")
        L.append(f"- {r['duracion']:.2f} s · {r['fps']:g} fps · {r['resolucion'][0]}×{r['resolucion'][1]}"
                 f"{' (vertical)' if r['vertical'] else ' (horizontal: se recorta al centro para 9:16)'}")
        L.append(f"- hojas: " + ", ".join(f"`{base}/{h}`" for h in r["hojas"]) + f" (un cuadro cada {r['paso_hojas_s']:g} s)")
        if r["tipo"] == "referencia":
            L.append(f"- cortes ({len(r['cortes'])}): " + ", ".join(f"{c:.2f}" for c in r["cortes"]))
            L.append(f"- duración de cada plano: " + ", ".join(f"{x:.2f}" for x in r["duracion_planos"]))
            L.append(f"- primer cuadro de cada plano: `{base}/cortes.jpg`")
            a = r.get("audio")
            if a:
                L.append(f"- música: ~{a['bpm']:g} BPM, subida de energía más fuerte cerca de {a['drop_estimado']:.2f} s")
        else:
            mv = r.get("movimiento_por_segundo") or []
            if mv:
                best = sorted(range(len(mv)), key=lambda i: -mv[i])[:5]
                L.append(f"- movimiento por segundo (0–100): {mv}")
                L.append(f"- segundos con más acción: {sorted(best)}")
        L.append("")
    return "\n".join(L)


def analyze_project(project: Path, progress=None) -> list[dict]:
    entrada = project / "entrada"
    items = [(p, "referencia") for p in sorted((entrada / "referencias").glob("*")) if p.suffix.lower() in VIDEO_EXT]
    items += [(p, "crudo") for p in sorted((entrada / "crudos").glob("*")) if p.suffix.lower() in VIDEO_EXT]
    out = project / "analisis"
    results = []
    for i, (p, kind) in enumerate(items):
        progress and progress(i, len(items), p.name)
        results.append(analyze_video(p, out / slug(p.name), kind))
    progress and progress(len(items), len(items), "")
    images = [shrink_image(p) for p in sorted((entrada / "referencias").glob("*")) if p.suffix.lower() in IMAGE_EXT]
    rel = [p.relative_to(project).as_posix() for p in images]
    (out / "resumen.md").write_text(summary_md(results, rel), encoding="utf-8")
    return results
