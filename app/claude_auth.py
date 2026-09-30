"""Conectar Claude desde la app, sin terminal: instalar Claude Code e iniciar sesión.

Login: `claude auth login` abre el navegador (cuenta de Claude, suscripción Pro/Max). Si el navegador no
vuelve solo, la página muestra un código: la UI lo pide y se lo pasamos por stdin al proceso.
Se da por hecho cuando `claude auth status` dice loggedIn. Las credenciales las guarda Claude Code
(en la carpeta del usuario); la app nunca las ve.

Instalación: instalador oficial de Claude Code (nativo, no necesita Node).
"""
from __future__ import annotations

import re
import subprocess
import threading
import time
import webbrowser

from . import settings
from .claude_runner import ClaudeRunner, clean_env, kill_tree
from .jobs import bus

URL_RE = re.compile(r"https://\S+")
INSTALL_PS = "irm https://claude.ai/install.ps1 | iex"


class _Flow:
    """Estado compartido de un proceso de fondo (login o instalación) que la UI consulta."""

    name = ""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self.state = "idle"  # idle | running | waiting | done | error | cancelled
        self.message = ""
        self.url: str | None = None
        self.lines: list[str] = []

    def public(self) -> dict:
        return {"state": self.state, "message": self.message, "url": self.url, "log": self.lines[-12:]}

    def publish(self):
        bus.publish({"type": f"claude_{self.name}", **self.public()})

    def set(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self.publish()

    def cancel(self):
        if self.proc:
            kill_tree(self.proc)
        self.set(state="cancelled", message="Cancelado")


class Login(_Flow):
    name = "login"

    def start(self, email: str | None = None) -> dict:
        with self.lock:
            if self.state in ("running", "waiting"):
                return self.public()
            exe = settings.claude_exe()
            if not exe:
                self.set(state="error", message="Primero hay que instalar Claude Code.")
                return self.public()
            cmd = [exe, "auth", "login", "--claudeai"] + (["--email", email] if email else [])
            self.lines, self.url = [], None
            self.proc = subprocess.Popen(cmd, env=clean_env(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
                                         creationflags=settings.NO_WINDOW)
            self.set(state="running", message="Abriendo el navegador…")
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._poll, daemon=True).start()
        return self.public()

    def _read(self):
        p = self.proc
        buf = ""
        while p and p.poll() is None:
            ch = p.stdout.read(1)  # carácter a carácter: "Paste code here >" no termina en salto de línea
            if not ch:
                break
            buf += ch
            if ch == "\n" or buf.rstrip().endswith(">"):
                line = buf.strip()
                buf = ""
                if not line:
                    continue
                self.lines.append(line)
                m = URL_RE.search(line)
                if m and not self.url:
                    self.url = m.group(0)
                if "paste code" in line.lower():
                    self.set(state="waiting", message="Iniciá sesión en el navegador. Si te muestra un código, pegalo acá.")
                else:
                    self.publish()

    def _poll(self):
        t0 = time.monotonic()
        while self.state in ("running", "waiting"):
            time.sleep(2.5)
            st = ClaudeRunner().status()
            if st.get("logged_in"):
                if self.proc:
                    kill_tree(self.proc)
                self.set(state="done", message=f"¡Listo! Claude quedó conectado{' (' + st['plan'] + ')' if st.get('plan') else ''}.")
                bus.publish({"type": "claude_status", **st})
                return
            if self.proc and self.proc.poll() is not None and self.state != "done":
                # terminó sin sesión (código mal pegado, ventana cerrada…)
                self.set(state="error", message="No se completó el inicio de sesión. Probá de nuevo.")
                return
            if time.monotonic() - t0 > 15 * 60:
                self.cancel()
                self.set(state="error", message="Pasó mucho tiempo sin completar el inicio de sesión. Probá de nuevo.")
                return

    def send_code(self, code: str) -> dict:
        code = code.strip()
        if not code or not self.proc or self.proc.poll() is not None:
            return {**self.public(), "error": "No hay un inicio de sesión esperando un código."}
        self.proc.stdin.write(code + "\n")
        self.proc.stdin.flush()
        self.set(state="running", message="Verificando el código…")
        return self.public()

    def open_browser(self) -> bool:
        return bool(self.url) and webbrowser.open(self.url)


class Install(_Flow):
    name = "install"

    def start(self) -> dict:
        with self.lock:
            if self.state == "running":
                return self.public()
            self.lines = []
            self.proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", INSTALL_PS],
                env=clean_env(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                encoding="utf-8", errors="replace", creationflags=settings.NO_WINDOW)
            self.set(state="running", message="Instalando Claude Code… (1–2 minutos)")
        threading.Thread(target=self._run, daemon=True).start()
        return self.public()

    def _run(self):
        for line in self.proc.stdout:
            if line.strip():
                self.lines.append(line.strip())
                self.publish()
        self.proc.wait()
        settings.forget_claude()
        st = ClaudeRunner().status()
        if st.get("installed"):
            self.set(state="done", message="Claude Code instalado. Ahora iniciá sesión.")
        else:
            self.set(state="error", message="No se pudo instalar Claude Code. " + (self.lines[-1] if self.lines else ""))


def logout() -> dict:
    exe = settings.claude_exe()
    if exe:
        subprocess.run([exe, "auth", "logout"], env=clean_env(), capture_output=True, timeout=60,
                       stdin=subprocess.DEVNULL, creationflags=settings.NO_WINDOW)
    return ClaudeRunner().status()


login = Login()
install = Install()
