// Curvas y resortes propios. Misma matemática que engine/motion.py (hay un test que los compara).
(function (root) {
  const clamp = (x, lo = 0, hi = 1) => (x < lo ? lo : x > hi ? hi : x);
  const lerp = (a, b, u) => a + (b - a) * u;
  const easeInOut = u => { u = clamp(u); return u * u * (3 - 2 * u); };

  function spring(tau, zeta = 0.5, omega = 18) {
    if (tau <= 0) return 0;
    if (Math.abs(zeta - 1) < 1e-6) return 1 - Math.exp(-omega * tau) * (1 + omega * tau);
    if (zeta < 1) {
      const wd = omega * Math.sqrt(1 - zeta * zeta);
      return 1 - Math.exp(-zeta * omega * tau) * (Math.cos(wd * tau) + zeta * omega / wd * Math.sin(wd * tau));
    }
    const s = Math.sqrt(zeta * zeta - 1), r1 = -omega * (zeta - s), r2 = -omega * (zeta + s);
    return 1 + (r2 * Math.exp(r1 * tau) - r1 * Math.exp(r2 * tau)) / (r1 - r2);
  }

  function springVel(tau, zeta = 0.5, omega = 18) {
    if (tau <= 0) return 0;
    if (Math.abs(zeta - 1) < 1e-6) return omega * omega * tau * Math.exp(-omega * tau);
    if (zeta < 1) {
      const wd = omega * Math.sqrt(1 - zeta * zeta);
      return omega * omega / wd * Math.exp(-zeta * omega * tau) * Math.sin(wd * tau);
    }
    const s = Math.sqrt(zeta * zeta - 1), r1 = -omega * (zeta - s), r2 = -omega * (zeta + s);
    return r1 * r2 * (Math.exp(r1 * tau) - Math.exp(r2 * tau)) / (r1 - r2);
  }

  function letterDrop(t, t0, i, o = {}) {
    const { stagger = 0.032, zeta = 0.45, omega = 24, dist = 80, squash = 0.0022, max = 0.25 } = o;
    const tau = t - t0 - i * stagger;
    const k = spring(tau, zeta, omega);
    const v = springVel(tau, zeta, omega) * dist;
    const sq = clamp(Math.abs(v) * squash, 0, max);
    return { k, y: (1 - k) * dist, op: clamp(1.6 * k), sx: 1 + 0.6 * sq, sy: 1 - sq };
  }

  function popIn(t, t0, o = {}) {
    const { rise = 24, zeta = 0.8, omega = 14 } = o;
    const k = spring(t - t0, zeta, omega);
    return { k, op: clamp(1.5 * k), dy: (1 - k) * rise };
  }

  root.M = { clamp, lerp, easeInOut, spring, springVel, letterDrop, popIn };
})(window);
