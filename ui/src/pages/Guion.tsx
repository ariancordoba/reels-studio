// Editor del guion sin Claude: textos, acento por palabra (en vez de *asteriscos*), tiempos y colores.
// Guardar crea una versión nueva y genera la vista previa.
import { useEffect, useState } from "react";
import { Eye, Loader2, Plus, Trash2, Undo2 } from "lucide-react";
import { api, useStore } from "../api";
import { ICON, cx } from "../components/ui";

type Kind = "display" | "serif" | "emoji";
interface Line { kind: Kind; text: string; size: number; y: number; delay: number; spacing?: string | null; color?: string | null }
interface Scene { t0: number; t1: number; lines: Line[] }
interface Spec {
  format: { duration: number; [k: string]: unknown };
  style: { accent: string; text: string; darken: number; [k: string]: unknown };
  scenes: Scene[];
  footer: { lines: string[]; [k: string]: unknown } | string[];
  [k: string]: unknown;
}

// ── acento por palabra
interface Word { w: string; acc: boolean }
export function parseWords(text: string): Word[] {
  const out: Word[] = [];
  let acc = false, cur = "", curAcc = 0, n = 0;
  const flush = () => { if (cur) out.push({ w: cur, acc: curAcc > n / 2 }); cur = ""; curAcc = 0; n = 0; };
  for (const c of Array.from(text)) {
    if (c === "*") { acc = !acc; continue; }
    if (c === " ") { flush(); continue; }
    cur += c; n++; if (acc) curAcc++;
  }
  flush();
  return out;
}
export function buildText(words: Word[]): string {
  let s = "", open = false;
  words.forEach((x, i) => {
    if (x.acc && !open) { s += (i ? " " : "") + "*"; open = true; } else if (!x.acc && open) { s += "* "; open = false; } else if (i) s += " ";
    s += x.w;
  });
  if (open) s += "*";
  return s.replace(/\* \*/g, " ");
}

const KINDS: { id: Kind; label: string }[] = [{ id: "display", label: "Título" }, { id: "serif", label: "Frase" }, { id: "emoji", label: "Emoji" }];

export default function GuionEditor({ pid, vid, busy, onSaved }: { pid: string; vid: string; busy: boolean; onSaved: () => void }) {
  const { toast } = useStore();
  const [orig, setOrig] = useState<Spec | null>(null);
  const [s, setS] = useState<Spec | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    api<Spec>(`/proyectos/${encodeURIComponent(pid)}/versiones/${vid}/spec`).then(d => { setOrig(d); setS(structuredClone(d)); })
      .catch(e => toast(e.message, "error"));
  }, [pid, vid, toast]);
  if (!s || !orig) return <div className="space-y-3">{[0, 1, 2].map(i => <div key={i} className="skeleton h-28" />)}</div>;

  const dirty = JSON.stringify(s) !== JSON.stringify(orig);
  const D = s.format.duration;
  const set = (f: (x: Spec) => void) => setS(prev => { const n = structuredClone(prev!); f(n); return n; });
  const footer = Array.isArray(s.footer) ? s.footer : s.footer.lines;
  const save = () => {
    setSaving(true);
    const clean = structuredClone(s);
    clean.scenes.forEach(sc => sc.lines.forEach(l => { l.text = l.text.trim(); }));
    api(`/proyectos/${encodeURIComponent(pid)}/versiones/${vid}/spec`, { method: "PUT", json: clean })
      .then(onSaved).catch(e => toast(e.message, "error")).finally(() => setSaving(false));
  };

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex-1 overflow-y-auto pr-1 space-y-4 max-h-[60vh]">
        {/* estilo */}
        <div className="sub bg-surface-muted/60 p-4 grid grid-cols-3 gap-4 items-end">
          <ColorField label="Acento" value={s.style.accent} onChange={v => set(x => { x.style.accent = v; })} />
          <ColorField label="Texto" value={s.style.text} onChange={v => set(x => { x.style.text = v; })} />
          <label className="block">
            <div className="label mb-1.5 flex justify-between"><span>Oscurecer fondo</span><span className="font-mono">{Math.round(s.style.darken * 100)}%</span></div>
            <input type="range" min={0} max={0.7} step={0.01} value={s.style.darken} onChange={e => set(x => { x.style.darken = +e.target.value; })} className="w-full accent-ink" />
          </label>
        </div>

        {s.scenes.map((sc, si) => (
          <div key={si} className="sub border border-line p-4">
            <div className="flex items-center gap-3 mb-3">
              <div className="font-semibold">Escena {si + 1}</div>
              <div className="font-mono text-sm text-ink-muted">{sc.t0.toFixed(1)}–{sc.t1.toFixed(1)} s</div>
              <div className="flex-1" />
              <button className="text-ink-muted hover:text-danger" title="Borrar escena" onClick={() => set(x => { x.scenes.splice(si, 1); })}><Trash2 size={16} /></button>
            </div>
            <div className="grid grid-cols-2 gap-4 mb-3">
              <Slider label="Empieza" v={sc.t0} min={0} max={D} onChange={v => set(x => { x.scenes[si].t0 = Math.min(v, x.scenes[si].t1 - 0.2); })} />
              <Slider label="Termina" v={sc.t1} min={0} max={D} onChange={v => set(x => { x.scenes[si].t1 = Math.max(v, x.scenes[si].t0 + 0.2); })} />
            </div>
            <div className="space-y-2.5">
              {sc.lines.map((ln, li) => (
                <LineRow key={li} ln={ln} onChange={f => set(x => f(x.scenes[si].lines[li]))} onDelete={() => set(x => { x.scenes[si].lines.splice(li, 1); })} />
              ))}
            </div>
            <button className="btn-ghost btn-sm mt-2 text-ink-muted" onClick={() => set(x => {
              const last = x.scenes[si].lines.at(-1);
              x.scenes[si].lines.push({ kind: "serif", text: "Texto nuevo", size: 56, y: last ? last.y + last.size + 20 : 400, delay: (last?.delay ?? 0) + 0.3 });
            })}><Plus size={15} /> Línea</button>
          </div>
        ))}
        <button className="btn-secondary btn-sm" onClick={() => set(x => {
          const last = x.scenes.at(-1);
          const t0 = last ? Math.min(last.t1, D - 0.5) : 0;
          x.scenes.push({ t0, t1: D, lines: [{ kind: "display", text: "NUEVO TÍTULO", size: 104, y: 380, delay: 0 }] });
        })}><Plus size={15} /> Escena</button>

        <div className="sub bg-surface-muted/60 p-4">
          <div className="label mb-2">Pie de página (fijo abajo)</div>
          {footer.map((f, i) => (
            <input key={i} className="input bg-surface mb-2" value={f} onChange={e => set(x => {
              const fl = Array.isArray(x.footer) ? x.footer : x.footer.lines; fl[i] = e.target.value;
            })} />
          ))}
        </div>
      </div>
      <div className="flex items-center gap-3 pt-4 border-t border-line mt-4">
        <span className="label flex-1">{dirty ? "Tenés cambios sin guardar. Se guardan como versión nueva." : "Editá textos, acentos y tiempos sin llamar a Claude."}</span>
        <button className="btn-secondary" disabled={!dirty || saving} onClick={() => setS(structuredClone(orig))}><Undo2 size={16} /> Descartar</button>
        <button className="btn-primary" disabled={!dirty || saving || busy} onClick={save}>
          {saving ? <Loader2 size={18} className="animate-spin" /> : <Eye {...ICON} />} Guardar y vista previa
        </button>
      </div>
    </div>
  );
}

function LineRow({ ln, onChange, onDelete }: { ln: Line; onChange: (f: (l: Line) => void) => void; onDelete: () => void }) {
  const words = parseWords(ln.text);
  const plain = words.map(w => w.w).join(" ") + (ln.text.endsWith(" ") ? " " : "");
  const setPlain = (t: string) => onChange(l => {
    const prev = new Map(parseWords(l.text).map(w => [w.w, w.acc]));
    const ws = t.split(" ").map(w => ({ w, acc: prev.get(w) ?? false }));
    l.text = t.endsWith(" ") ? buildText(ws.filter(w => w.w)) + " " : buildText(ws.filter(w => w.w));
  });
  return (
    <div className="rounded-[16px] bg-surface-muted/60 p-3">
      <div className="flex items-center gap-2">
        <select className="h-9 rounded-full bg-surface px-3 text-sm outline-none border border-line" value={ln.kind} onChange={e => onChange(l => { l.kind = e.target.value as Kind; })}>
          {KINDS.map(k => <option key={k.id} value={k.id}>{k.label}</option>)}
        </select>
        <input className={cx("input h-9 bg-surface flex-1", ln.kind === "display" && "uppercase font-semibold tracking-wide")} value={plain} onChange={e => setPlain(e.target.value)} />
        <button className="text-ink-muted hover:text-danger px-1" onClick={onDelete}><Trash2 size={15} /></button>
      </div>
      {ln.kind !== "emoji" && words.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2.5 items-center">
          <span className="text-[12px] text-ink-muted mr-1">Acento:</span>
          {words.map((w, i) => (
            <button key={i} onClick={() => onChange(l => { const ws = parseWords(l.text); ws[i].acc = !ws[i].acc; l.text = buildText(ws); })}
              className={cx("h-7 px-2.5 rounded-full text-[13px] font-medium transition-colors", w.acc ? "bg-lime text-lime-ink" : "bg-surface hover:bg-line")}>
              {ln.kind === "display" ? w.w.toUpperCase() : w.w}
            </button>
          ))}
        </div>
      )}
      <div className="grid grid-cols-3 gap-3 mt-2.5">
        <Num label="Tamaño" v={ln.size} step={2} onChange={v => onChange(l => { l.size = v; })} />
        <Num label="Altura (y)" v={ln.y} step={5} onChange={v => onChange(l => { l.y = v; })} />
        <Slider label="Entra a los" v={ln.delay} min={0} max={3} step={0.02} unit="s" onChange={v => onChange(l => { l.delay = v; })} />
      </div>
    </div>
  );
}

function Slider({ label, v, min, max, step = 0.05, unit = "s", onChange }: { label: string; v: number; min: number; max: number; step?: number; unit?: string; onChange: (v: number) => void }) {
  return (
    <label className="block">
      <div className="text-[12px] text-ink-muted mb-1 flex justify-between"><span>{label}</span><span className="font-mono">{v.toFixed(2)} {unit}</span></div>
      <input type="range" min={min} max={max} step={step} value={v} onChange={e => onChange(Math.round(+e.target.value * 100) / 100)} className="w-full accent-ink" />
    </label>
  );
}

function Num({ label, v, step, onChange }: { label: string; v: number; step: number; onChange: (v: number) => void }) {
  return (
    <label className="block">
      <div className="text-[12px] text-ink-muted mb-1">{label}</div>
      <input type="number" step={step} value={v} onChange={e => onChange(+e.target.value)} className="input h-9 bg-surface font-mono" />
    </label>
  );
}

function ColorField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block">
      <div className="label mb-1.5">{label}</div>
      <div className="flex items-center gap-2 h-11 px-2 rounded-[16px] bg-surface border border-line">
        <input type="color" value={value} onChange={e => onChange(e.target.value)} className="size-8 rounded-full overflow-hidden cursor-pointer border-0 bg-transparent" />
        <input value={value} onChange={e => onChange(e.target.value)} className="flex-1 min-w-0 bg-transparent outline-none font-mono text-sm" />
      </div>
    </label>
  );
}
