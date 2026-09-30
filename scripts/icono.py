"""Genera assets/icono.ico: cuadrado negro redondeado con una claqueta lima (sin dependencias extra)."""
import struct
from pathlib import Path

import cv2
import numpy as np

S = 256
LIME = (72, 238, 212)  # BGR de #D4EE48


def draw(s: int) -> np.ndarray:
    k = 4  # supermuestreo para bordes suaves
    n = s * k
    img = np.zeros((n, n, 4), np.uint8)
    r = int(n * 0.22)
    m = np.zeros((n, n), np.uint8)
    cv2.rectangle(m, (r, 0), (n - r, n), 255, -1)
    cv2.rectangle(m, (0, r), (n, n - r), 255, -1)
    for cx, cy in ((r, r), (n - r, r), (r, n - r), (n - r, n - r)):
        cv2.circle(m, (cx, cy), r, 255, -1)
    img[m > 0] = (17, 17, 17, 255)
    # claqueta: cuerpo + barra superior inclinada con franjas
    x0, x1, y0, y1 = int(n * .24), int(n * .76), int(n * .44), int(n * .76)
    cv2.rectangle(img, (x0, y0), (x1, y1), (*LIME, 255), -1)
    bar = np.array([[x0, int(n * .40)], [x1, int(n * .30)], [x1, int(n * .38)], [x0, int(n * .48)]])
    bar[:, 1] -= int(n * .02)
    cv2.fillPoly(img, [bar], (*LIME, 255))
    for i in range(1, 4):
        t = i / 4
        xa = int(x0 + (x1 - x0) * t)
        ya = int(n * .38 - (n * .10) * t)
        cv2.line(img, (xa, ya - int(n * .02)), (xa - int(n * .05), ya + int(n * .09)), (17, 17, 17, 255), int(n * .03))
    return cv2.resize(img, (s, s), interpolation=cv2.INTER_AREA)


def ico(path: Path, sizes=(256, 64, 48, 32, 16)):
    pngs = [cv2.imencode(".png", draw(s))[1].tobytes() for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(sizes))
    off = 6 + 16 * len(sizes)
    entries = b""
    for s, png in zip(sizes, pngs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), off)
        off += len(png)
    path.write_bytes(head + entries + b"".join(pngs))


if __name__ == "__main__":
    ico(Path("assets/icono.ico"))
    cv2.imwrite("assets/icono.png", draw(256))
