import { useEffect, useState } from "react";
import { ImagePlus, Plus, Sparkles, Type, Users } from "lucide-react";
import { api, useStore, type Cliente } from "../api";
import { Empty, Field, cx } from "../components/ui";
import { ClientAvatar, go } from "../App";

const BUILTIN = ["Archivo", "Playfair"];
const blank: Omit<Cliente, "slug" | "fonts" | "logo"> = {
  nombre: "", accent: "#caffbf", text: "#ffffff", display_font: "Archivo", serif_font: "Playfair", footer: [], darken: 0.32, notas: "",
};

export default function Clientes({ sel }: { sel?: string }) {
  const { clientes, proyectos } = useStore();
  const current = sel === "nuevo" ? null : clientes?.find(c => c.slug === sel) ?? clientes?.[0] ?? null;
  const creating = sel === "nuevo" || (clientes !== null && clientes.length === 0);
  return (
    <div className="grid grid-cols-12 gap-6">
      <div className="col-span-12 xl:col-span-4 card p-5">
        <div className="flex items-center justify-between px-2 pt-1 pb-4">
          <div className="h-card">Clientes</div>
          <button className="btn-primary btn-sm" onClick={() => go("clientes/nuevo")}><Plus size={16} /> Nuevo</button>
        </div>
        {clientes?.length === 0 && <Empty icon={<Users size={26} strokeWidth={1.5} />} title="Sin clientes" text="Cargá la marca de cada cliente: colores, fuentes y pie de página." />}
        <div className="space-y-1.5">
          {clientes?.map(c => (
            <button key={c.slug} onClick={() => go(`clientes/${c.slug}`)}
              className={cx("w-full flex items-center gap-3 p-3 rounded-[20px] text-left transition-colors",
                !creating && current?.slug === c.slug ? "bg-ink text-white" : "hover:bg-surface-muted")}>
              <ClientAvatar slug={c.slug} name={c.nombre} color={c.accent} logo={!!c.logo} />
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{c.nombre}</div>
                <div className={cx("text-[13px]", !creating && current?.slug === c.slug ? "text-white/60" : "text-ink-muted")}>
                  {(proyectos ?? []).filter(p => p.cliente === c.slug).length} proyectos
                </div>
              </div>
              <span className="size-5 rounded-full border border-black/10" style={{ background: c.accent }} />
            </button>
          ))}
        </div>
      </div>
      <div className="col-span-12 xl:col-span-8">
        {creating ? <Editor key="nuevo" c={null} /> : current ? <><Editor key={current.slug} c={current} /><Learned key={"l" + current.slug} slug={current.slug} /></> : <div className="card skeleton h-96" />}
      </div>
    </div>
  );
}

function Editor({ c }: { c: Cliente | null }) {
  const { refresh, toast } = useStore();
  const [f, setF] = useState(() => c ? { ...blank, ...c } : { ...blank });
  const [footer, setFooter] = useState((c?.footer ?? []).join("\n"));
  const [saving, setSaving] = useState(false);
  useEffect(() => { setF(c ? { ...blank, ...c } : { ...blank }); setFooter((c?.footer ?? []).join("\n")); }, [c]);
  const fonts = [...BUILTIN, ...(c?.fonts ?? []).map(x => x.replace(/\.(ttf|otf|woff2?)$/i, ""))];
  const save = async () => {
    setSaving(true);
    const body = { ...f, footer: footer.split("\n").map(s => s.trim()).filter(Boolean) };
    try {
      const r = await api<Cliente>(c ? `/clientes/${c.slug}` : "/clientes", { method: c ? "PUT" : "POST", json: body });
      await refresh(["clientes"]);
      toast("Cliente guardado");
      if (!c) go(`clientes/${r.slug}`);
    } catch (e) { toast((e as Error).message, "error"); } finally { setSaving(false); }
  };
  const upload = async (kind: "fuentes" | "logo", file?: File) => {
    if (!file || !c) return;
    const fd = new FormData(); fd.append("archivo", file);
    try { await api(`/clientes/${c.slug}/${kind}`, { method: "POST", body: fd }); await refresh(["clientes"]); toast(kind === "logo" ? "Logo actualizado" : `Fuente ${file.name} cargada`); }
    catch (e) { toast((e as Error).message, "error"); }
  };
  return (
    <div className="card p-7">
      <div className="flex items-center gap-4 mb-6">
        <ClientAvatar slug={c?.slug} name={f.nombre || "?"} color={f.accent} logo={!!c?.logo} />
        <div className="flex-1"><div className="h-card">{c ? f.nombre : "Nuevo cliente"}</div><div className="label">Marca que Claude usa por defecto en sus videos</div></div>
        <button className="btn-primary" disabled={!f.nombre.trim() || saving} onClick={save}>Guardar</button>
      </div>
      <div className="grid grid-cols-2 gap-5">
        <Field label="Nombre"><input className="input" value={f.nombre} onChange={e => setF({ ...f, nombre: e.target.value })} placeholder="Ej: Café Aurora" /></Field>
        <Field label="Oscurecido por defecto" hint="Más alto = los textos se leen mejor sobre fondos claros">
          <div className="flex items-center gap-3 h-11"><input type="range" min={0} max={0.7} step={0.01} value={f.darken} onChange={e => setF({ ...f, darken: +e.target.value })} className="flex-1 accent-ink" /><span className="font-mono w-12 text-right">{Math.round(f.darken * 100)}%</span></div>
        </Field>
        <Field label="Color de acento"><Color v={f.accent} on={v => setF({ ...f, accent: v })} /></Field>
        <Field label="Color de texto"><Color v={f.text} on={v => setF({ ...f, text: v })} /></Field>
        <Field label="Fuente de títulos">
          <select className="input" value={f.display_font} onChange={e => setF({ ...f, display_font: e.target.value })}>{fonts.map(x => <option key={x}>{x}</option>)}</select>
        </Field>
        <Field label="Fuente de frases">
          <select className="input" value={f.serif_font} onChange={e => setF({ ...f, serif_font: e.target.value })}>{fonts.map(x => <option key={x}>{x}</option>)}</select>
        </Field>
        <div className="col-span-2">
          <Field label="Pie de página (una línea por renglón)"><textarea className="input h-24 py-3 resize-none" value={footer} onChange={e => setFooter(e.target.value)} placeholder={"CAFÉ AURORA · PALERMO\nPedidos por mensaje privado"} /></Field>
        </div>
        <div className="col-span-2">
          <Field label="Notas para Claude" hint="Tono, palabras que usa la marca, cosas a evitar"><textarea className="input h-20 py-3 resize-none" value={f.notas} onChange={e => setF({ ...f, notas: e.target.value })} /></Field>
        </div>
      </div>

      {/* muestra */}
      <div className="mt-6 rounded-[22px] bg-ink p-6 text-center" style={{ background: `linear-gradient(rgba(0,0,0,${f.darken}),rgba(0,0,0,${f.darken})), #4a8fd8` }}>
        <div className="text-[34px] font-black uppercase tracking-tight leading-none" style={{ color: f.text }}>Nueva <span style={{ color: f.accent }}>colección</span></div>
        <div className="mt-2 font-serif text-lg" style={{ color: f.text }}>Llegó el otoño.</div>
        <div className="mt-6 text-[11px] font-bold tracking-wide" style={{ color: f.text }}>{footer.split("\n")[0]}</div>
      </div>

      {c && (
        <div className="grid grid-cols-2 gap-4 mt-6">
          <label className="btn-secondary cursor-pointer"><Type size={18} strokeWidth={1.75} /> Subir fuente (.otf/.ttf)
            <input type="file" accept=".ttf,.otf,.woff,.woff2" className="hidden" onChange={e => upload("fuentes", e.target.files?.[0])} /></label>
          <label className="btn-secondary cursor-pointer"><ImagePlus size={18} strokeWidth={1.75} /> {c.logo ? "Cambiar logo" : "Subir logo"}
            <input type="file" accept="image/*" className="hidden" onChange={e => upload("logo", e.target.files?.[0])} /></label>
          {c.fonts.length > 0 && <div className="col-span-2 label">Fuentes propias: {c.fonts.join(", ")}</div>}
        </div>
      )}
      {!c && <div className="label mt-4">Guardá el cliente para poder subir fuentes y logo.</div>}
    </div>
  );
}

function Color({ v, on }: { v: string; on: (v: string) => void }) {
  return (
    <div className="flex items-center gap-2 h-11 px-2 rounded-[16px] bg-surface-muted">
      <input type="color" value={v} onChange={e => on(e.target.value)} className="size-8 cursor-pointer bg-transparent border-0" />
      <input value={v} onChange={e => on(e.target.value)} className="flex-1 bg-transparent outline-none font-mono text-sm" />
    </div>
  );
}

/** Preferencias que Claude fue anotando en los pedidos: se usan en todos los videos nuevos del cliente. */
function Learned({ slug }: { slug: string }) {
  const { toast } = useStore();
  const [txt, setTxt] = useState<string | null>(null);
  const [orig, setOrig] = useState("");
  useEffect(() => { api<{ texto: string }>(`/clientes/${slug}/aprendizajes`).then(r => { setTxt(r.texto); setOrig(r.texto); }).catch(() => setTxt("")); }, [slug]);
  const save = () => api(`/clientes/${slug}/aprendizajes`, { method: "PUT", json: { texto: txt } }).then(() => { setOrig(txt ?? ""); toast("Guardado"); });
  return (
    <div className="card p-7 mt-6">
      <div className="flex items-center gap-2 mb-1"><Sparkles size={18} strokeWidth={1.75} /><div className="font-semibold">Lo que Claude aprendió de este cliente</div></div>
      <div className="label mb-4">Cuando pedís algo que vale para siempre (“nunca amarillo”, “títulos más grandes”), Claude lo anota acá y lo respeta en los videos siguientes. Menos correcciones, menos uso de tu plan. Podés editarlo.</div>
      {txt === null ? <div className="skeleton h-28" /> : (
        <>
          <textarea className="input h-36 py-3 resize-none font-mono text-sm" value={txt} onChange={e => setTxt(e.target.value)}
            placeholder={"- Prefiere el título más grande\n- Nunca usar emojis\n- El pie siempre con el teléfono"} />
          <button className="btn-secondary btn-sm mt-3" disabled={txt === orig} onClick={save}>Guardar</button>
        </>
      )}
    </div>
  );
}
