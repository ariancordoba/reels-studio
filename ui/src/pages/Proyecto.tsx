import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft, Check, Download, Eye, Film, FolderOpen, Grid3x3, ImagePlus, Images, LayoutTemplate, Loader2, Play, RotateCcw, Send, Sparkles, X, Zap,
} from "lucide-react";
import {
  api, activeJob, fecha, fileUrl, hace, useStore, type ChatMsg, type Proyecto, type Trabajo, type Version,
} from "../api";
import { Badge, ICON, Progress, Segmented, cx } from "../components/ui";
import { go, openClaude } from "../App";
import { jobFraction, statusOf } from "./Inicio";
import GuionEditor from "./Guion";

export default function ProyectoPage({ id }: { id: string }) {
  const { tick, trabajos, toast, clientes } = useStore();
  const [p, setP] = useState<Proyecto | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [tab, setTab] = useState<"cambios" | "guion">("cambios");
  const load = () => api<Proyecto>(`/proyectos/${encodeURIComponent(id)}`).then(d => { setP(d); setErr(null); }).catch(e => setErr(e.message));
  useEffect(() => { load(); }, [id, tick]); // eslint-disable-line react-hooks/exhaustive-deps
  // al aparecer una versión nueva, mostrarla
  const lastCurrent = useRef<string | null>(null);
  useEffect(() => {
    if (!p) return;
    if (p.version_actual !== lastCurrent.current) { lastCurrent.current = p.version_actual; setSel(p.version_actual ?? p.versiones.at(-1)?.id ?? null); }
  }, [p]);

  if (err) return <div className="card p-10 text-center"><div className="h-card">No encontré el proyecto</div><div className="label mt-1">{err}</div>
    <button className="btn-primary mt-5" onClick={() => go("proyectos")}>Volver</button></div>;
  if (!p) return <div className="grid grid-cols-12 gap-6"><div className="col-span-5 skeleton h-[80vh] rounded-[28px]" /><div className="col-span-7 skeleton h-[80vh] rounded-[28px]" /></div>;

  const v = p.versiones.find(x => x.id === sel) ?? p.versiones.at(-1);
  const jobs = Object.values(trabajos).filter(t => t.project === p.id && (t.status === "corriendo" || t.status === "en_cola"));
  const claudeJob = jobs.find(t => t.lane === "claude");
  const renderJob = jobs.find(t => t.lane === "render");
  const st = statusOf(p, activeJob(p, trabajos));
  const cli = clientes?.find(c => c.slug === p.cliente);

  const render = (calidad: "stills" | "borrador" | "final") =>
    api(`/proyectos/${encodeURIComponent(p.id)}/render`, { method: "POST", json: { version: v?.id, calidad } })
      .then(() => toast(calidad === "final" ? "Render final en marcha" : calidad === "borrador" ? "Borrador en marcha" : "Generando vista previa"))
      .catch(e => toast(e.message, "error"));
  const exportar = () => api<{ path: string }>(`/proyectos/${encodeURIComponent(p.id)}/exportar?version=${v?.id ?? ""}`, { method: "POST" })
    .then(r => toast(`Copiado a Descargas: ${r.path.split(/[\\/]/).pop()}`)).catch(e => toast(e.message, "error"));
  const abrir = () => api(`/proyectos/${encodeURIComponent(p.id)}/abrir${v ? `?version=${v.id}` : ""}`, { method: "POST" });
  const usar = (vid: string) => api(`/proyectos/${encodeURIComponent(p.id)}`, { method: "PUT", json: { version_actual: vid } }).then(load);

  return (
    <div className="flex flex-col gap-6 min-h-0">
      {/* barra superior */}
      <div className="flex items-center gap-4 min-h-14">
        <button className="icon-btn size-12" onClick={() => go("proyectos")}><ArrowLeft {...ICON} /></button>
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <h1 className="h-title truncate">{p.titulo}</h1>
            <Badge tone={st.tone} dot>{st.label}</Badge>
          </div>
          <div className="label">{cli?.nombre ?? p.cliente} · creado {fecha(p.creado)} · {p.versiones.length} {p.versiones.length === 1 ? "versión" : "versiones"}</div>
        </div>
        <div className="flex-1" />
        <button className="icon-btn size-12" title="Abrir carpeta" onClick={abrir}><FolderOpen {...ICON} /></button>
        <button className="btn-secondary h-12" disabled={!v || !!renderJob} onClick={() => render("stills")}><Eye {...ICON} /> Vista previa<span className="hidden 2xl:inline"> rápida</span></button>
        <button className="btn-primary h-12" disabled={!v || !!renderJob} onClick={() => render("borrador")}><Zap {...ICON} /> Borrador</button>
        <button className="btn-lime h-12" disabled={!v || !!renderJob} onClick={() => render("final")}><Film {...ICON} /> Render final</button>
        <button className="btn-secondary h-12" disabled={!v?.video} onClick={exportar} title={v?.video ? "" : "Primero hacé el render final"}><Download {...ICON} /> Exportar</button>
      </div>

      {p.lock && <div className="rounded-[18px] bg-warn-soft text-warn-ink px-5 py-3 text-sm">“{p.lock.machine}” está trabajando en este proyecto ({p.lock.what}). Esperá a que termine para renderizar desde esta compu.</div>}

      <div className="grid grid-cols-12 gap-6 items-start">
        {/* izquierda: reproductor + versiones */}
        <div className="col-span-12 xl:col-span-5 flex flex-col gap-4">
          <Player p={p} v={v} job={renderJob ?? claudeJob} />
          <Versions p={p} sel={v?.id} onSel={setSel} onUse={usar} />
        </div>
        {/* derecha: guion / cambios */}
        <div className="col-span-12 xl:col-span-7 card p-6 flex flex-col min-h-[70vh]">
          <div className="flex items-center justify-between mb-5">
            <Segmented value={tab} onChange={setTab} options={[{ id: "cambios", label: "Pedir cambios" }, { id: "guion", label: "Guion" }]} />
            {v && <span className="font-mono text-sm text-ink-muted">{v.id} · {fecha(v.fecha, true)}</span>}
          </div>
          {tab === "cambios"
            ? <Chat p={p} job={claudeJob} onSent={load} />
            : v ? <GuionEditor key={`${p.id}/${v.id}`} pid={p.id} vid={v.id} busy={!!renderJob} onSaved={() => { toast("Guardado como versión nueva; generando vista previa"); load(); }} />
              : <div className="label py-10 text-center">Todavía no hay guion. Pedile la primera versión a Claude.</div>}
        </div>
      </div>
    </div>
  );
}

function JobBar({ job }: { job: Trabajo }) {
  const { toast } = useStore();
  const frac = jobFraction(job);
  return (
    <div className="rounded-[18px] bg-surface-muted p-4">
      <div className="flex items-center gap-3 text-sm">
        <Loader2 size={16} className="animate-spin" />
        <span className="flex-1 truncate font-medium">{job.status === "en_cola" ? "En cola…" : job.stage || job.title}</span>
        {job.total > 0 && <span className="font-mono text-ink-muted">{job.done} / {job.total}</span>}
        {job.eta_s != null && <span className="font-mono text-ink-muted">~{Math.max(1, job.eta_s)} s</span>}
        <button className="text-ink-muted hover:text-ink" title="Cancelar" onClick={() => api(`/trabajos/${job.id}/cancelar`, { method: "POST" }).then(() => toast("Cancelado"))}><X size={16} /></button>
      </div>
      {job.lane === "render" && <Progress value={frac ?? 0} className="mt-3" />}
    </div>
  );
}

function Player({ p, v, job }: { p: Proyecto; v?: Version; job?: Trabajo }) {
  const hasVideo = !!(v?.video || v?.borrador);
  const [mode, setMode] = useState<"video" | "cuadros" | "todos">(hasVideo ? "video" : "cuadros");
  const [i, setI] = useState(0);
  useEffect(() => { setMode(v?.video || v?.borrador ? "video" : "cuadros"); setI(0); }, [v?.id, v?.video, v?.borrador]);
  const src = v?.video ? "video.mp4" : v?.borrador ? "borrador.mp4" : null;
  const bust = v ? `${v.fecha}-${v.tamano_mb ?? ""}-${p.actualizado}` : "";
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3 px-1">
        <Segmented size="sm" value={mode} onChange={setMode}
          options={[{ id: "video", label: <span className="flex items-center gap-1.5"><Play size={14} /> Video</span> },
            { id: "cuadros", label: <span className="flex items-center gap-1.5"><Images size={14} /> Cuadros</span> },
            { id: "todos", label: <span className="flex items-center gap-1.5"><Grid3x3 size={14} /> Todos</span> }]} />
        <span className="label">{src === "video.mp4" ? "Render final 1080p" : src === "borrador.mp4" ? "Borrador 540p" : "Sin render todavía"}</span>
      </div>
      {mode === "todos" && v ? (
        <div className="grid grid-cols-4 gap-2 max-h-[64vh] overflow-y-auto pr-1">
          {v.stills.map((s, k) => (
            <button key={s} onClick={() => { setI(k); setMode("cuadros"); }} className="text-left">
              <img src={fileUrl(p.id, `versiones/${v.id}/stills/${s}`, bust)} className="w-full aspect-[9/16] object-cover rounded-[10px]" alt="" />
              <div className="font-mono text-[11px] text-ink-muted mt-0.5">{parseFloat(s.slice(1)).toFixed(1)} s</div>
            </button>
          ))}
          {!v.stills.length && <div className="col-span-4 label py-10 text-center">Sin cuadros: tocá “Vista previa”.</div>}
        </div>
      ) : (
      <div className="relative mx-auto aspect-[9/16] max-h-[64vh] rounded-[20px] overflow-hidden bg-ink">
        {!v ? (
          <div className="absolute inset-0 grid place-items-center text-white/60 text-center p-8">
            <div><Sparkles size={28} strokeWidth={1.5} className="mx-auto mb-3 text-lime" />{job ? "Claude está armando la primera versión…" : "Todavía no hay versiones"}</div>
          </div>
        ) : mode === "video" && src ? (
          <video key={`${v.id}-${src}-${bust}`} src={fileUrl(p.id, `versiones/${v.id}/${src}`, bust)} controls autoPlay loop playsInline className="size-full object-contain bg-black" />
        ) : v.stills.length ? (
          <img src={fileUrl(p.id, `versiones/${v.id}/stills/${v.stills[Math.min(i, v.stills.length - 1)]}`, bust)} className="size-full object-contain" alt="" />
        ) : (
          <div className="absolute inset-0 grid place-items-center text-white/60 text-sm">Sin cuadros: tocá “Vista previa rápida”.</div>
        )}
      </div>
      )}
      {mode === "cuadros" && v && v.stills.length > 1 && (
        <div className="flex gap-2 mt-3 overflow-x-auto pb-1">
          {v.stills.map((s, k) => (
            <button key={s} onClick={() => setI(k)} className={cx("shrink-0 w-14 aspect-[9/16] rounded-[10px] overflow-hidden border-2", k === i ? "border-ink" : "border-transparent opacity-70")}>
              <img src={fileUrl(p.id, `versiones/${v.id}/stills/${s}`, bust)} className="size-full object-cover" alt="" />
            </button>
          ))}
        </div>
      )}
      {job && <div className="mt-3"><JobBar job={job} /></div>}
    </div>
  );
}

function saveTemplate(p: Proyecto) {
  const nombre = prompt("Nombre de la plantilla (por ejemplo: Evento deportivo 11 s)", p.titulo);
  if (!nombre) return;
  api("/plantillas", { method: "POST", json: { proyecto: p.id, nombre, descripcion: "" } })
    .then(() => alert("Plantilla guardada. La vas a ver al crear un video nuevo."))
    .catch(e => alert(e.message));
}

function Versions({ p, sel, onSel, onUse }: { p: Proyecto; sel?: string; onSel: (v: string) => void; onUse: (v: string) => void }) {
  const v = p.versiones.find(x => x.id === sel);
  if (!p.versiones.length) return null;
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="font-medium">Versiones</div>
        <div className="flex gap-2">
          {v && v.id !== p.version_actual && <button className="btn-secondary btn-sm" onClick={() => onUse(v.id)}><RotateCcw size={14} /> Volver a esta</button>}
          {p.version_actual && <button className="btn-secondary btn-sm" title="Reusar este estilo en otros videos, sin gastar Claude" onClick={() => saveTemplate(p)}><LayoutTemplate size={14} /> Guardar como plantilla</button>}
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {p.versiones.map(x => (
          <button key={x.id} onClick={() => onSel(x.id)}
            className={cx("h-9 px-4 rounded-full font-mono text-sm flex items-center gap-1.5 transition-colors",
              x.id === sel ? "bg-ink text-white" : "bg-surface-muted hover:bg-line")}>
            {x.id}{x.id === p.version_actual && <Check size={13} />}{x.video && <Film size={13} className={x.id === sel ? "text-lime" : ""} />}
          </button>
        ))}
      </div>
      {v && (
        <div className="mt-4 text-sm space-y-1.5">
          <div className="text-ink-muted font-mono text-[13px]">{fecha(v.fecha, true)}{v.duracion ? ` · ${v.duracion} s` : ""}{v.tamano_mb ? ` · ${v.tamano_mb} MB` : ""}</div>
          {v.pedido && <div><span className="text-ink-muted">Pedido: </span>{v.pedido}</div>}
          {v.resumen && <div className="leading-relaxed">{v.resumen}</div>}
        </div>
      )}
    </div>
  );
}

const SUGERENCIAS = ["Otra toma al principio", "Que el título entre más rápido", "Alargalo a 12 s", "Más dinámico"];
const RAPIDOS: { id: string; label: string }[] = [
  { id: "acento_claro", label: "Acento más claro" }, { id: "acento_oscuro", label: "Acento más oscuro" },
  { id: "fondo_oscuro", label: "Se lee mejor" }, { id: "texto_grande", label: "Textos más grandes" },
  { id: "texto_chico", label: "Textos más chicos" }, { id: "sin_musica", label: "Sin música" },
];

function Chat({ p, job, onSent }: { p: Proyecto; job?: Trabajo; onSent: () => void }) {
  const { toast, estado } = useStore();
  const [txt, setTxt] = useState("");
  const [sending, setSending] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const msgs: ChatMsg[] = p.chat ?? [];
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs.length, job?.stage]);
  const send = async (t = txt) => {
    if (!t.trim()) return;
    setSending(true);
    try {
      let adjuntos: string[] = [];
      if (files.length) {
        const fd = new FormData(); files.forEach(f => fd.append("archivos", f));
        adjuntos = (await api<{ adjuntos: string[] }>(`/proyectos/${encodeURIComponent(p.id)}/adjuntos`, { method: "POST", body: fd })).adjuntos;
      }
      await api(`/proyectos/${encodeURIComponent(p.id)}/pedir`, { method: "POST", json: { texto: t, adjuntos } });
      setTxt(""); setFiles([]); onSent();
    } catch (e) { toast((e as Error).message, "error"); } finally { setSending(false); }
  };
  const quick = (tipo: string) => api(`/proyectos/${encodeURIComponent(p.id)}/ajuste`, { method: "POST", json: { tipo } })
    .then(onSent).catch(e => toast(e.message, "error"));
  const busy = !!job || sending;
  const noVersion = p.versiones.length === 0;
  const off = estado && !estado.claude.ok;
  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex-1 overflow-y-auto space-y-3 pr-1 max-h-[58vh]">
        {msgs.length === 0 && <div className="label text-center py-10">Contale a Claude qué querés cambiar, con tus palabras.</div>}
        {msgs.map((m, i) => m.rol === "yo" ? (
          <div key={i} className="flex justify-end">
            <div className="max-w-[80%] rounded-[20px] rounded-br-[8px] bg-surface-muted px-4 py-3 whitespace-pre-wrap">
              {m.tipo === "inicio" && <div className="label mb-1">Instrucciones</div>}{m.texto}
              {!!m.adjuntos?.length && <div className="flex gap-2 mt-2 flex-wrap">{m.adjuntos.map(a =>
                <img key={a} src={fileUrl(p.id, a)} className="h-20 rounded-[10px] object-cover" alt="" />)}</div>}
            </div>
          </div>
        ) : (
          <div key={i} className="flex">
            <div className={cx("max-w-[85%] rounded-[20px] rounded-bl-[8px] px-5 py-4", m.ok === false ? "bg-warn-soft text-warn-ink" : "bg-ink text-white")}>
              <div className="flex items-center gap-2 mb-1.5 text-[13px] opacity-70">
                {m.sin_claude ? <><Zap size={14} className="text-lime" /> Reels Studio</> : <><Sparkles size={14} className={m.ok === false ? "" : "text-lime"} /> Claude</>}
                {m.version && <span className="font-mono">· {m.version}</span>}<span className="font-mono">· {hace(m.fecha)}</span>
              </div>
              <div className="whitespace-pre-wrap leading-relaxed">{m.texto}</div>
            </div>
          </div>
        ))}
        {job && (
          <div className="flex"><div className="rounded-[20px] rounded-bl-[8px] bg-ink text-white px-5 py-4 flex items-center gap-3">
            <Loader2 size={16} className="animate-spin text-lime" /><span>{job.status === "en_cola" ? "En cola…" : job.stage || "Pensando…"}</span>
            <button className="ml-2 text-white/50 hover:text-white" title="Cancelar" onClick={() => api(`/trabajos/${job.id}/cancelar`, { method: "POST" })}><X size={15} /></button>
          </div></div>
        )}
        <div ref={end} />
      </div>
      {off && <button onClick={openClaude} className="mb-3 w-full rounded-[18px] bg-warn-soft text-warn-ink px-4 py-3 text-sm text-left">Claude no está conectado. <u>Conectar ahora</u></button>}
      {noVersion && !job ? (
        <div className="pt-4">
          <button className="btn-primary w-full h-12" disabled={sending} onClick={() => send("Armá la primera versión.")}><Sparkles {...ICON} /> Generar la primera versión</button>
        </div>
      ) : (
        <div className="pt-4">
          <div className="flex flex-wrap gap-2 mb-2 items-center">
            <span className="text-[12px] text-ink-muted flex items-center gap-1 mr-1"><Zap size={13} /> Al instante, sin Claude:</span>
            {RAPIDOS.map(r => <button key={r.id} disabled={busy || noVersion} onClick={() => quick(r.id)} className="chip bg-lime/50 hover:bg-lime disabled:opacity-40">{r.label}</button>)}
          </div>
          <div className="flex flex-wrap gap-2 mb-3 items-center">
            <span className="text-[12px] text-ink-muted flex items-center gap-1 mr-1"><Sparkles size={13} /> Ideas para Claude:</span>
            {SUGERENCIAS.map(s => <button key={s} disabled={busy} onClick={() => setTxt(s)} className="chip hover:bg-line disabled:opacity-40">{s}</button>)}
          </div>
          {files.length > 0 && (
            <div className="flex gap-2 mb-2 flex-wrap">
              {files.map((f, i) => (
                <div key={i} className="relative">
                  <img src={URL.createObjectURL(f)} className="h-16 w-16 rounded-[12px] object-cover" alt="" />
                  <button className="absolute -top-1.5 -right-1.5 size-5 rounded-full bg-ink text-white grid place-items-center" onClick={() => setFiles(files.filter((_, j) => j !== i))}><X size={12} /></button>
                </div>
              ))}
            </div>
          )}
          <div className="flex items-end gap-2 rounded-[22px] bg-surface-muted p-2">
            <button className="icon-btn size-11 shrink-0 bg-transparent hover:bg-surface" title="Adjuntar imágenes de referencia (así lo quiero)" disabled={busy}
              onClick={() => fileInput.current?.click()}><ImagePlus size={19} strokeWidth={1.75} /></button>
            <input ref={fileInput} type="file" accept="image/*" multiple className="hidden"
              onChange={e => { setFiles([...files, ...Array.from(e.target.files ?? [])].slice(0, 6)); e.target.value = ""; }} />
            <textarea value={txt} onChange={e => setTxt(e.target.value)} rows={2} disabled={busy}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder={off ? "Claude no está conectado (mirá Ajustes)" : busy ? "Esperá a que Claude termine…" : "Ej: el verde más claro y que el título entre más rápido"}
              className="flex-1 bg-transparent resize-none outline-none px-3 py-2 leading-relaxed" />
            <button className="btn-primary size-11 px-0 shrink-0" disabled={busy || !txt.trim()} onClick={() => send()}><Send size={18} strokeWidth={1.75} /></button>
          </div>
        </div>
      )}
    </div>
  );
}

