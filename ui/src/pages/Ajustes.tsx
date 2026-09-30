import { useEffect, useState } from "react";
import { CheckCircle2, Download, FolderSync, Loader2, RefreshCw, Sparkles, Wrench, XCircle } from "lucide-react";
import { api, useStore } from "../api";
import { Field, Modal, Segmented, Toggle } from "../components/ui";
import { openClaude } from "../App";

interface Sistema { [k: string]: { ok: boolean; detail: string; version?: string } }

export default function Ajustes() {
  const { estado, refresh, toast } = useStore();
  const [name, setName] = useState("");
  const [dir, setDir] = useState("");
  const [quality, setQuality] = useState("final");
  const [modo, setModo] = useState("equilibrado");
  const [src, setSrc] = useState("");
  const [sys, setSys] = useState<Sistema | null>(null);
  useEffect(() => {
    if (!estado) return;
    setName(estado.config.user_name); setDir(estado.config.data_dir || estado.data_dir); setQuality(estado.config.quality || "final");
    setModo(estado.config.claude_modo || "equilibrado"); setSrc(estado.config.update_source || "");
  }, [estado]);
  const check = () => { setSys(null); api<Sistema>("/sistema").then(setSys).then(() => refresh(["estado"])).catch(e => toast(e.message, "error")); };
  useEffect(check, []); // eslint-disable-line react-hooks/exhaustive-deps
  const save = () => api("/ajustes", { method: "PUT", json: { user_name: name, data_dir: dir, quality, claude_modo: modo, ...(src ? { update_source: src } : {}) } })
    .then(() => refresh()).then(() => toast("Ajustes guardados")).catch(e => toast(e.message, "error"));
  const fix = (q: string) => api(`/sistema/reparar/${q}`, { method: "POST" }).then(() => toast("Se abrió una ventana para reparar. Cuando termine, tocá “Revisar”."));
  const rows: { id: string; label: string; fix?: string; help: string }[] = [
    { id: "ffmpeg", label: "Motor de video (ffmpeg)", fix: "todo", help: "Viene con la instalación." },
    { id: "chromium", label: "Textos (Chromium)", fix: "chromium", help: "Dibuja y anima los textos." },
    { id: "claude", label: "Claude Code", fix: "claude", help: "Arma los guiones. Tiene que tener la sesión iniciada." },
  ];
  return (
    <div className="grid grid-cols-12 gap-6">
      <div className="col-span-12 xl:col-span-7 card p-7 space-y-5">
        <div className="h-card">Ajustes</div>
        <Field label="Tu nombre"><input className="input" value={name} onChange={e => setName(e.target.value)} /></Field>
        <Field label="Carpeta de datos" hint="Usá la misma carpeta de OneDrive o Google Drive en la compu y en la laptop: así ves los mismos proyectos en las dos.">
          <input className="input font-mono text-sm" value={dir} onChange={e => setDir(e.target.value)} />
        </Field>
        <Field label="Calidad por defecto">
          <div><Segmented value={quality} onChange={setQuality} options={[{ id: "borrador", label: "Borrador 540p" }, { id: "final", label: "Final 1080p" }]} /></div>
        </Field>
        <Field label="Uso de Claude" hint={MODOS.find(m => m.id === modo)?.hint}>
          <div><Segmented value={modo} onChange={setModo} options={MODOS.map(m => ({ id: m.id, label: m.label }))} /></div>
        </Field>
        <details className="text-sm">
          <summary className="cursor-pointer text-ink-muted">Avanzado</summary>
          <div className="mt-3"><Field label="Origen de actualizaciones" hint="github:usuario/repositorio o la URL de un update.json. Vacío = el que vino con el programa.">
            <input className="input font-mono text-sm" value={src} onChange={e => setSrc(e.target.value)} placeholder="github:usuario/reels-studio" /></Field></div>
        </details>
        <button className="btn-primary" onClick={save}>Guardar</button>
      </div>
      <div className="col-span-12 xl:col-span-5 card p-7">
        <div className="flex items-center justify-between mb-5">
          <div className="h-card">Estado del sistema</div>
          <button className="btn-secondary btn-sm" onClick={check}>Revisar</button>
        </div>
        <div className="space-y-3">
          {rows.map(r => {
            const s = sys?.[r.id];
            return (
              <div key={r.id} className="flex items-center gap-4 p-4 rounded-[20px] bg-surface-muted/70">
                {!s ? <Loader2 size={22} className="animate-spin text-ink-muted" /> : s.ok ? <CheckCircle2 size={22} className="text-ok" /> : <XCircle size={22} className="text-danger" />}
                <div className="flex-1 min-w-0"><div className="font-medium">{r.label}</div><div className="label truncate">{s?.detail ?? r.help}</div></div>
                {s && !s.ok && r.id === "claude" && <button className="btn-primary btn-sm" onClick={openClaude}><Sparkles size={15} /> Conectar</button>}
                {s && !s.ok && r.fix && r.id !== "claude" && <button className="btn-primary btn-sm" onClick={() => fix(r.fix!)}><Wrench size={15} /> Reparar</button>}
                {s?.ok && r.id === "claude" && <button className="btn-secondary btn-sm" onClick={openClaude}>Cuenta</button>}
              </div>
            );
          })}
        </div>
        <div className="label mt-5">Compu: <span className="font-mono">{estado?.machine}</span></div>
      </div>
      <div className="col-span-12 xl:col-span-5 xl:col-start-8 -mt-0"><Updates /></div>
    </div>
  );
}

/** Primera apertura: nombre + carpeta de datos (OneDrive si está). */
export function Onboarding() {
  const { estado, refresh, toast } = useStore();
  const [name, setName] = useState("");
  const [dir, setDir] = useState(estado?.sugerido ?? "");
  const go = () => api("/ajustes", { method: "PUT", json: { user_name: name.trim(), data_dir: dir.trim() } })
    .then(() => refresh()).then(() => { if (!estado?.claude.ok) openClaude(); }).catch(e => toast(e.message, "error"));
  return (
    <Modal open title="¡Hola! Configuremos Reels Studio" width={560}>
      <div className="space-y-5">
        <Field label="¿Cómo te llamás?"><input autoFocus className="input" value={name} onChange={e => setName(e.target.value)} placeholder="Tu nombre" /></Field>
        <Field label="¿Dónde guardamos los proyectos?" hint="Sugerimos una carpeta dentro de OneDrive para verlos también en la laptop. En la laptop elegí la misma.">
          <input className="input font-mono text-sm" value={dir} onChange={e => setDir(e.target.value)} />
        </Field>
        <div className="flex items-center gap-3 rounded-[18px] bg-surface-muted p-4 text-sm"><FolderSync size={20} strokeWidth={1.75} /> Los videos pesados (cache) quedan en esta compu; en la carpeta sólo van proyectos, versiones y clientes.</div>
        <button className="btn-primary w-full h-12" disabled={!name.trim() || !dir.trim()} onClick={go}>Empezar</button>
      </div>
    </Modal>
  );
}

const MODOS = [
  { id: "calidad", label: "Máxima calidad", hint: "El modelo más capaz en todo. Consume más de tu plan." },
  { id: "equilibrado", label: "Equilibrado", hint: "El más capaz para la primera versión y uno más liviano para los cambios. Recomendado." },
  { id: "ahorro", label: "Ahorro", hint: "Un modelo liviano para todo: rinde mucho más tu plan, con algo menos de criterio." },
];

interface Upd { configurado: boolean; actual: string; disponible: boolean; version?: string; notas?: string; error?: string; desarrollo?: boolean; auto?: boolean; lista?: string | null }

export function Updates() {
  const { toast, estado, refresh } = useStore();
  const auto = estado?.config.auto_update !== false;
  const setAuto = (v: boolean) => api("/ajustes", { method: "PUT", json: { auto_update: v } }).then(() => refresh(["estado"]));
  const [u, setU] = useState<Upd | null>(null);
  const [busy, setBusy] = useState(false);
  const check = (forzar = false) => { setBusy(true); api<Upd>(`/actualizacion${forzar ? "?forzar=true" : ""}`).then(setU).catch(e => toast(e.message, "error")).finally(() => setBusy(false)); };
  useEffect(() => check(), []); // eslint-disable-line react-hooks/exhaustive-deps
  const install = () => api("/actualizacion/instalar", { method: "POST" }).then(() => toast("Descargando la actualización…")).catch(e => toast(e.message, "error"));
  return (
    <div className="card p-7">
      <div className="flex items-center justify-between mb-4">
        <div><div className="h-card">Versión</div><div className="label">Reels Studio <span className="font-mono">{u?.actual ?? "…"}</span></div></div>
        <button className="btn-secondary btn-sm" disabled={busy} onClick={() => check(true)}>{busy ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />} Buscar actualizaciones</button>
      </div>
      {u && !u.configurado && <div className="label">Este programa no tiene configurado de dónde actualizarse. Pedíselo a quien te lo pasó.</div>}
      {u?.error && <div className="rounded-[16px] bg-warn-soft text-warn-ink p-4 text-sm">{u.error}</div>}
      {u?.configurado && !u.error && !u.disponible && <div className="flex items-center gap-2 text-sm"><CheckCircle2 size={18} className="text-ok" /> Tenés la última versión.</div>}
      <label className="flex items-center justify-between gap-4 rounded-[18px] bg-surface-muted/70 p-4 mb-4 cursor-pointer">
        <div><div className="font-medium">Actualizar automáticamente</div>
          <div className="label">Descarga las versiones nuevas en segundo plano y las instala cuando cerrás la app.</div></div>
        <Toggle on={auto} onChange={setAuto} dark />
      </label>
      {u?.disponible && (
        <div className="rounded-[20px] bg-lime p-5 text-lime-ink">
          <div className="font-semibold text-lg">Hay una versión nueva: {u.version}</div>
          {u.notas && <div className="text-sm mt-2 whitespace-pre-wrap text-lime-ink/80 max-h-40 overflow-auto">{u.notas}</div>}
          {u.desarrollo
            ? <div className="text-sm mt-3">Esta es la carpeta de desarrollo: actualizá con git.</div>
            : <button className="btn-primary mt-4 w-full" onClick={install}><Download size={18} /> {u.lista ? "Reiniciar y actualizar" : "Actualizar ahora"}</button>}
          {u.lista && <div className="text-[12px] mt-2 text-lime-ink/70">Ya está descargada: si no hacés nada, se instala sola la próxima vez que cierres la app.</div>}
          <div className="text-[12px] mt-2 text-lime-ink/70">La app se cierra, se actualiza y se vuelve a abrir sola (1–2 minutos). Tus proyectos no se tocan.</div>
        </div>
      )}
    </div>
  );
}
