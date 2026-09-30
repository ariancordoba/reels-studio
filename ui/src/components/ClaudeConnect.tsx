// Conectar Claude sin terminal: instalar Claude Code (si falta) e iniciar sesión con la cuenta de Claude.
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Download, ExternalLink, Loader2, LogIn, Sparkles } from "lucide-react";
import { api, useStore, type ClaudeStatus } from "../api";
import { ICON, Modal, cx } from "./ui";

interface Flow { state: "idle" | "running" | "waiting" | "done" | "error" | "cancelled"; message: string; url: string | null; log: string[] }
interface ClaudeInfo { status: ClaudeStatus; login: Flow; install: Flow }

export default function ClaudeConnect({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { refresh, toast } = useStore();
  const [info, setInfo] = useState<ClaudeInfo | null>(null);
  const [code, setCode] = useState("");
  const [email, setEmail] = useState("");
  const timer = useRef<number | null>(null);
  const load = () => api<ClaudeInfo>("/claude").then(setInfo).catch(() => {});
  useEffect(() => {
    if (!open) return;
    load();
    timer.current = window.setInterval(load, 2000);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const connected = !!info?.status.logged_in;
  useEffect(() => { if (connected) refresh(["estado"]); }, [connected, refresh]);

  const st = info?.status;
  const login = info?.login;
  const inst = info?.install;
  const busyLogin = login?.state === "running" || login?.state === "waiting";
  const busyInst = inst?.state === "running";
  const step = !info ? "cargando" : connected ? "listo" : !st?.installed ? "instalar" : "login";

  const post = (path: string, json?: unknown) => api(path, { method: "POST", json }).then(load).catch(e => toast(e.message, "error"));

  return (
    <Modal open={open} onClose={onClose} title={<span className="flex items-center gap-2"><Sparkles size={22} strokeWidth={1.75} /> Conectar Claude</span>} width={560}>
      {/* pasos */}
      <div className="flex items-center gap-2 mb-6">
        {[["instalar", "Instalar"], ["login", "Iniciar sesión"], ["listo", "Listo"]].map(([id, label], i) => {
          const order = ["instalar", "login", "listo"];
          const done = order.indexOf(step) > i;
          const active = step === id;
          return (
            <div key={id} className="flex items-center gap-2 flex-1">
              <span className={cx("size-7 rounded-full grid place-items-center text-[13px] font-semibold shrink-0",
                done ? "bg-ink text-lime" : active ? "bg-lime text-lime-ink" : "bg-surface-muted text-ink-muted")}>
                {done ? "✓" : i + 1}
              </span>
              <span className={cx("text-sm", active ? "font-medium" : "text-ink-muted")}>{label}</span>
              {i < 2 && <span className="flex-1 h-px bg-line" />}
            </div>
          );
        })}
      </div>

      {step === "cargando" && <div className="py-10 grid place-items-center"><Loader2 className="animate-spin" /></div>}

      {step === "instalar" && (
        <div className="space-y-4">
          <p className="leading-relaxed">Reels Studio usa <b>Claude Code</b> para armar los guiones. No está instalado en esta compu: lo instalo yo, sin que abras nada.</p>
          {inst?.state === "error" && <div className="rounded-[16px] bg-warn-soft text-warn-ink p-4 text-sm">{inst.message}</div>}
          {busyInst ? (
            <div className="rounded-[18px] bg-surface-muted p-4">
              <div className="flex items-center gap-3 font-medium"><Loader2 size={18} className="animate-spin" /> {inst?.message}</div>
              {inst?.log.length ? <div className="mt-2 font-mono text-[12px] text-ink-muted truncate">{inst.log.at(-1)}</div> : null}
            </div>
          ) : (
            <button className="btn-primary w-full h-12" onClick={() => post("/claude/instalar")}><Download {...ICON} /> Instalar Claude Code</button>
          )}
        </div>
      )}

      {step === "login" && (
        <div className="space-y-4">
          <p className="leading-relaxed">Iniciá sesión con tu cuenta de <b>Claude</b> (plan Pro o Max). Se abre tu navegador, entrás y aceptás. No hace falta API key.</p>
          {login?.state === "error" && <div className="rounded-[16px] bg-warn-soft text-warn-ink p-4 text-sm">{login.message}</div>}
          {!busyLogin ? (
            <>
              <input className="input" type="email" placeholder="Tu email de Claude (opcional)" value={email} onChange={e => setEmail(e.target.value)} />
              <button className="btn-primary w-full h-12" onClick={() => post("/claude/login", { email: email.trim() || null })}><LogIn {...ICON} /> Iniciar sesión con Claude</button>
            </>
          ) : (
            <div className="space-y-3">
              <div className="rounded-[18px] bg-surface-muted p-4 flex items-center gap-3">
                <Loader2 size={18} className="animate-spin shrink-0" />
                <div className="flex-1 text-sm">{login?.message || "Esperando que inicies sesión en el navegador…"}</div>
              </div>
              {login?.url && (
                <button className="btn-secondary w-full" onClick={() => post("/claude/login/abrir")}><ExternalLink size={16} /> No se abrió el navegador: abrir de nuevo</button>
              )}
              <div className="rounded-[18px] border border-line p-4">
                <div className="label mb-2">¿El navegador te muestra un código? Copialo y pegalo acá:</div>
                <div className="flex gap-2">
                  <input className="input font-mono" value={code} onChange={e => setCode(e.target.value)} placeholder="Código" />
                  <button className="btn-primary" disabled={!code.trim()} onClick={() => { post("/claude/login/codigo", { codigo: code }); setCode(""); }}>Enviar</button>
                </div>
              </div>
              <button className="btn-ghost w-full text-ink-muted" onClick={() => post("/claude/login/cancelar")}>Cancelar</button>
            </div>
          )}
        </div>
      )}

      {step === "listo" && (
        <div className="text-center space-y-4 py-2">
          <CheckCircle2 size={44} strokeWidth={1.5} className="mx-auto text-ok" />
          <div className="text-lg font-semibold">Claude está conectado</div>
          <div className="label">{st?.version ? `Claude Code ${st.version}` : ""}{st?.plan ? ` · plan ${st.plan}` : ""}</div>
          <div className="flex gap-2 justify-center">
            <button className="btn-primary" onClick={onClose}>Listo</button>
            <button className="btn-secondary" onClick={() => post("/claude/logout").then(() => refresh(["estado"]))}>Cambiar de cuenta</button>
          </div>
        </div>
      )}
    </Modal>
  );
}
