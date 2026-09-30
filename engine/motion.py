"""Curvas y resortes propios. Misma matemática que text_comp/motion.js (hay un test que los compara).

spring(): respuesta al escalón (0 → 1) de un oscilador amortiguado que parte del reposo.
"""
import math


def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def lerp(a, b, u):
    return a + (b - a) * u


def ease_in_out(u):
    """smoothstep."""
    u = clamp(u)
    return u * u * (3 - 2 * u)


def spring(tau, zeta=0.5, omega=18.0):
    if tau <= 0:
        return 0.0
    if abs(zeta - 1) < 1e-6:
        return 1 - math.exp(-omega * tau) * (1 + omega * tau)
    if zeta < 1:
        wd = omega * math.sqrt(1 - zeta * zeta)
        return 1 - math.exp(-zeta * omega * tau) * (math.cos(wd * tau) + zeta * omega / wd * math.sin(wd * tau))
    s = math.sqrt(zeta * zeta - 1)
    r1, r2 = -omega * (zeta - s), -omega * (zeta + s)
    return 1 + (r2 * math.exp(r1 * tau) - r1 * math.exp(r2 * tau)) / (r1 - r2)


def spring_vel(tau, zeta=0.5, omega=18.0):
    """d spring / d tau (analítica)."""
    if tau <= 0:
        return 0.0
    if abs(zeta - 1) < 1e-6:
        return omega * omega * tau * math.exp(-omega * tau)
    if zeta < 1:
        wd = omega * math.sqrt(1 - zeta * zeta)
        return omega * omega / wd * math.exp(-zeta * omega * tau) * math.sin(wd * tau)
    s = math.sqrt(zeta * zeta - 1)
    r1, r2 = -omega * (zeta - s), -omega * (zeta + s)
    return r1 * r2 * (math.exp(r1 * tau) - math.exp(r2 * tau)) / (r1 - r2)


def letter_drop(t, t0, i, stagger=0.032, zeta=0.45, omega=24.0, dist=80.0, squash=0.0022, max_sq=0.25):
    """Letra que cae y rebota. y = desplazamiento hacia arriba (px); squash por velocidad en px/s."""
    tau = t - t0 - i * stagger
    k = spring(tau, zeta, omega)
    v = spring_vel(tau, zeta, omega) * dist
    sq = clamp(abs(v) * squash, 0, max_sq)
    return {"k": k, "y": (1 - k) * dist, "op": clamp(1.6 * k), "sx": 1 + 0.6 * sq, "sy": 1 - sq}


def pop_in(t, t0, rise=24.0, zeta=0.8, omega=14.0):
    k = spring(t - t0, zeta, omega)
    return {"k": k, "op": clamp(1.5 * k), "dy": (1 - k) * rise}
