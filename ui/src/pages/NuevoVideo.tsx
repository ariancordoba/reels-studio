import { useEffect, useMemo, useState } from "react";
import { Clapperboard, Film, LayoutTemplate, Sparkles, Zap } from "lucide-react";
import { useStore, type Proyecto } from "../api";
import { Dropzone, Field, ICON, Progress, cx } from "../components/ui";
import AccentInput from "../components/AccentInput";
import { ClientAvatar, go, openClaude } from "../App";

export interface Campo { key: string; escena: number; label: string; kind: string; ejemplo: string; texto: string; t0: number; t1: number }
export interface Plantilla {
  id: string; nombre: string; descripcion: string; origen: string; cliente?: string; creada: string;
  duracion: number; escenas: number; planos: number; campos: Campo[]; preview: boolean; reglas?: string;
}

type Modo = "rapido" | "claude_plantilla" | "claude";

export default function NuevoVideo({ clienteSel }: { clienteSel: string }) {
  const { clientes, estado, toast, refresh } = useStore();
  const [cliente, setCliente] = useState(clienteSel);
  const [titulo, setTitulo] = useState("");
  const [crudos, setCrudos] = useState<File[]>([]);
  const [refs, setRefs] = useState<File[]>([]);
  const [instr, setInstr] = useState("");
  const [duracion, setDuracion] = useState("");
  const [plantillas, setPlantillas] = useState<Plantilla[] | null>(null);
  const [pid, setPid] = useState("");
  const [modo, setModo] = useState<Modo>("claude");
  const [textos, setTextos] = useState<Record<string, string>>({});
  const [sending, setSending] = useState<number | null>(null);
  useEffect(() => { if (!cliente && clientes?.length === 1) setCliente(clientes[0].slug); }, [clientes, cliente]);
  useEffect(() => { fetch("/api/plantillas").then(r => r.json()).then(setPlantillas).catch(() => setPlantillas([])); }, []);
  // plantillas del cliente primero
  const lista = useMemo(() => [...(plantillas ?? [])].sort((a, b) => Number(b.cliente === cliente) - Number(a.cliente === cliente)), [plantillas, cliente]);
  const pl = lista.find(p => p.id === pid);
  const pick = (id: string) => {
    setPid(id);
    const t = lista.find(p => p.id === id);
    setModo(t ? "rapido" : "claude");
    setTextos(t ? Object.fromEntries(t.campos.map(c => [c.key, c.texto])) : {});
  };
  const claudeOff = !!estado && !estado.claude.ok;
  const needsClaude = modo !== "rapido";

  const ok = cliente && titulo.trim() && crudos.length > 0 && sending == null && (!needsClaude || !claudeOff);
  const submit = () => {
    const fd = new FormData();
    fd.append("titulo", titulo.trim());
    fd.append("cliente", cliente);
    fd.append("instrucciones", instr);
    if (duracion && !pl) fd.append("duracion", duracion);
    if (pl) {
      fd.append("plantilla", pl.id);
      fd.append("modo", modo === "rapido" ? "rapido" : "claude");
      fd.append("textos", JSON.stringify(textos));
    }
    crudos.forEach(f => fd.append("crudos", f));
    refs.forEach(f => fd.append("referencias", f));
    // XHR y no fetch: para mostrar el progreso de la subida (los crudos pesan cientos de MB)
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/proyectos");
    xhr.upload.onprogress = e => e.lengthComputable && setSending(e.loaded / e.total);
    xhr.onload = () => {
      setSending(null);
      if (xhr.status >= 200 && xhr.status < 300) {
        const r = JSON.parse(xhr.responseText) as { id: string };
        refresh(["proyectos"]);
        toast(modo === "rapido" ? "Armando la primera versión con la plantilla…" : "Claude está armando la primera versión.");
        go(`proyecto/${r.id}`);
      } else {
        let m = "No se pudo crear el proyecto";
        try { m = JSON.parse(xhr.responseText).detail || m; } catch { /* */ }
        toast(m, "error");
      }
    };
    xhr.onerror = () => { setSending(null); toast("Se cortó la subida", "error"); };
    setSending(0);
    xhr.send(fd);
  };

  const escenas = pl ? [...new Set(pl.campos.map(c => c.escena))] : [];
  const hint = !cliente ? "Elegí un cliente" : crudos.length === 0 ? "Subí al menos un crudo" : !titulo.trim() ? "Ponele un nombre"
    : needsClaude && claudeOff ? "Conectá Claude o usá el armado rápido" : "";

  return (
    <div className="grid grid-cols-12 gap-6">
      <div className="col-span-12 xl:col-span-8 card p-7 space-y-7">
        <div>
          <div className="h-card">Nuevo video</div>
          <div className="label">Subí tus crudos, elegí cómo armarlo y en unos minutos tenés la vista previa.</div>
        </div>

        <Step n={1} title="Cliente">
          {clientes?.length === 0 ? (
            <button className="btn-secondary" onClick={() => go("clientes/nuevo")}>Crear el primer cliente</button>
          ) : (
            <div className="flex flex-wrap gap-2">
              {clientes?.map(c => (
                <button key={c.slug} onClick={() => setCliente(c.slug)}
                  className={cx("flex items-center gap-2.5 h-12 pl-1.5 pr-4 rounded-full border transition-colors",
                    cliente === c.slug ? "bg-ink text-white border-ink" : "bg-surface border-line hover:bg-surface-muted")}>
                  <ClientAvatar slug={c.slug} name={c.nombre} color={c.accent} logo={!!c.logo} small />
                  <span className="font-medium">{c.nombre}</span>
                </button>
              ))}
            </div>
          )}
        </Step>

        <Step n={2} title="Nombre y crudos">
          <div className="grid grid-cols-3 gap-4 mb-4">
            <div className="col-span-2"><Field label="Nombre del video"><input className="input" placeholder="Ej: Copa Primavera" value={titulo} onChange={e => setTitulo(e.target.value)} /></Field></div>
            {!pl && <Field label="Duración (opcional)"><input className="input font-mono" placeholder="11 s" inputMode="decimal" value={duracion} onChange={e => setDuracion(e.target.value.replace(/[^0-9.]/g, ""))} /></Field>}
          </div>
          <Dropzone label="Subí tus crudos" hint="Arrastrá los videos o hacé clic · .mov, .mp4 · mejor verticales, con buena luz" files={crudos} onFiles={setCrudos} icon={<Film {...ICON} />} />
        </Step>

        <Step n={3} title="¿Cómo lo armamos?">
          <div className="grid grid-cols-2 gap-3">
            <Option active={!pl} onClick={() => pick("")} icon={<Sparkles size={20} strokeWidth={1.75} />} title="Claude desde una referencia"
              text="Subís un reel que te guste y Claude copia el estilo. Más flexible; usa Claude." />
            <Option active={!!pl} onClick={() => pick(pid || lista[0]?.id || "")} disabled={!lista.length} icon={<LayoutTemplate size={20} strokeWidth={1.75} />}
              title="Con una plantilla" text={lista.length ? "Un estilo que ya funcionó. Completás los textos y listo. Rápido." : "Todavía no tenés plantillas (se crean en Plantillas)."} />
          </div>

          {!pl && (
            <div className="mt-4 space-y-4">
              <Dropzone label="Referencias" hint="El reel cuyo estilo querés copiar (opcional)" files={refs} onFiles={setRefs} icon={<Sparkles {...ICON} />} />
              <Field label="Instrucciones / guion" hint="Qué es, cuándo, dónde, qué tiene que decir, el tono. Cuanto más concreto, menos correcciones.">
                <textarea className="input h-40 py-3 resize-none leading-relaxed" value={instr} onChange={e => setInstr(e.target.value)}
                  placeholder={"Qué: Copa Primavera del Club Norte\nCuándo: 10 de octubre\nDónde: cancha principal del club\nPara quién: categorías infantiles\nTono: enérgico"} />
              </Field>
            </div>
          )}

          {pl && (
            <div className="mt-4 space-y-4">
              <div className="flex gap-2 overflow-x-auto pb-1">
                {lista.map(t => (
                  <button key={t.id} onClick={() => pick(t.id)}
                    className={cx("shrink-0 w-44 text-left rounded-[18px] border-2 p-2 transition-colors", t.id === pid ? "border-ink" : "border-transparent bg-surface-muted/70 hover:bg-surface-muted")}>
                    <div className="aspect-[4/3] rounded-[12px] overflow-hidden bg-line mb-2">
                      {t.preview && <img src={`/api/plantillas/${t.id}/preview`} className="size-full object-cover" alt="" />}
                    </div>
                    <div className="text-sm font-semibold truncate px-1">{t.nombre}</div>
                    <div className="text-[12px] text-ink-muted px-1">{t.duracion} s · {t.escenas} escenas</div>
                  </button>
                ))}
              </div>
              <div className="rounded-[20px] bg-surface-muted/60 p-5 space-y-5">
                <div className="flex items-center justify-between">
                  <div className="font-medium">Textos del video</div>
                  <span className="label">Dejá un campo vacío para sacar esa línea</span>
                </div>
                {escenas.map(e => {
                  const cs = pl.campos.filter(c => c.escena === e);
                  return (
                    <div key={e}>
                      <div className="text-[12px] font-semibold tracking-wide text-ink-muted mb-2">ESCENA {e} · {cs[0].t0.toFixed(1)}–{cs[0].t1.toFixed(1)} s</div>
                      <div className="space-y-3">
                        {cs.map(c => (
                          <Field key={c.key} label={c.label}>
                            <AccentInput value={textos[c.key] ?? ""} onChange={v => setTextos({ ...textos, [c.key]: v })} placeholder={c.ejemplo}
                              upper={c.kind === "display"} noAccent={c.kind === "emoji"} />
                          </Field>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Option active={modo === "rapido"} onClick={() => setModo("rapido")} icon={<Zap size={20} strokeWidth={1.75} />} title="Armado automático"
                  text="El programa elige las mejores tomas. Sin gastar Claude, en segundos." />
                <Option active={modo === "claude_plantilla"} onClick={() => setModo("claude_plantilla")} icon={<Sparkles size={20} strokeWidth={1.75} />} title="Que Claude lo afine"
                  text="Claude mira tus crudos y ajusta encuadres y textos respetando la plantilla." />
              </div>
              {modo === "claude_plantilla" && (
                <Field label="Algo más para Claude (opcional)"><textarea className="input h-24 py-3 resize-none" value={instr} onChange={e => setInstr(e.target.value)} /></Field>
              )}
            </div>
          )}
        </Step>

        <div className="flex items-center gap-4 pt-1">
          <button className="btn-primary h-12 px-7" disabled={!ok} onClick={submit}>
            {modo === "rapido" ? <Zap {...ICON} /> : <Sparkles {...ICON} />} {modo === "rapido" ? "Armar ahora" : "Generar"}
          </button>
          {sending != null && <div className="flex-1 flex items-center gap-3"><Progress value={sending} className="flex-1" /><span className="font-mono text-sm">Subiendo {Math.round(sending * 100)}%</span></div>}
          {sending == null && hint && <span className="label">{hint}</span>}
          {sending == null && needsClaude && claudeOff && <button className="btn-secondary btn-sm" onClick={openClaude}>Conectar Claude</button>}
        </div>
      </div>

      <div className="col-span-12 xl:col-span-4 flex flex-col gap-6">
        <div className="rounded-[28px] bg-ink text-white p-6">
          <div className="flex items-center gap-3 mb-4"><Sparkles size={20} strokeWidth={1.75} className="text-lime" /><span className="font-medium">Consejos para que salga bien de una</span></div>
          <ul className="space-y-3 text-white/85 text-[15px]">
            <li className="flex gap-3"><span className="text-lime">•</span>Crudos verticales, con buena luz y algo de acción. Si son a 60 fps, la cámara lenta queda perfecta.</li>
            <li className="flex gap-3"><span className="text-lime">•</span>Mejor 3 o 4 crudos cortos que uno largo y quieto.</li>
            <li className="flex gap-3"><span className="text-lime">•</span>En las instrucciones poné qué, cuándo, dónde y el tono. Los datos exactos (fecha, dirección) escribilos tal cual.</li>
            <li className="flex gap-3"><span className="text-lime">•</span>¿Te gustó un video? Guardalo como plantilla: el próximo sale en segundos y sin gastar Claude.</li>
          </ul>
        </div>
        <RecentHint />
      </div>
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section>
      <div className="flex items-center gap-2.5 mb-3"><span className="size-7 rounded-full bg-ink text-white text-[13px] font-semibold grid place-items-center">{n}</span><span className="font-medium">{title}</span></div>
      {children}
    </section>
  );
}

function Option({ active, onClick, icon, title, text, disabled }: { active: boolean; onClick: () => void; icon: React.ReactNode; title: string; text: string; disabled?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className={cx("text-left rounded-[20px] border-2 p-4 transition-colors disabled:opacity-50", active ? "border-ink bg-surface" : "border-line bg-surface-muted/50 hover:bg-surface-muted")}>
      <div className={cx("size-10 rounded-full grid place-items-center mb-3", active ? "bg-lime" : "bg-surface")}>{icon}</div>
      <div className="font-semibold">{title}</div>
      <div className="label mt-1 leading-snug">{text}</div>
    </button>
  );
}

function RecentHint() {
  const { proyectos } = useStore();
  const last: Proyecto | undefined = proyectos?.[0];
  if (!last) return null;
  return (
    <div className="card p-6">
      <div className="flex items-center gap-2 mb-2"><Clapperboard size={18} strokeWidth={1.75} /><span className="font-medium">Último proyecto</span></div>
      <div className="font-semibold">{last.titulo}</div>
      <div className="label mb-4">{last.cliente} · {last.version_actual ?? "sin versión"}</div>
      <button className="btn-secondary btn-sm" onClick={() => go(`proyecto/${last.id}`)}>Abrir</button>
    </div>
  );
}
