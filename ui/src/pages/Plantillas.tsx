import { useEffect, useState } from "react";
import { ChevronDown, LayoutTemplate, Loader2, Sparkles, Trash2, Zap } from "lucide-react";
import { api, fecha, useStore } from "../api";
import { Badge, Dropzone, Empty, Field, cx } from "../components/ui";
import { openClaude } from "../App";
import type { Plantilla } from "./NuevoVideo";

export default function Plantillas() {
  const { proyectos, clientes, toast, trabajos, estado } = useStore();
  const [list, setList] = useState<Plantilla[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const load = () => api<Plantilla[]>("/plantillas").then(setList).catch(e => toast(e.message, "error"));
  const learning = Object.values(trabajos).filter(t => t.kind === "estilo" && (t.status === "corriendo" || t.status === "en_cola"));
  const doneLearning = Object.values(trabajos).filter(t => t.kind === "estilo" && t.status === "listo").length;
  useEffect(() => { load(); }, [doneLearning]); // eslint-disable-line react-hooks/exhaustive-deps

  // desde un video aprobado
  const withVersion = (proyectos ?? []).filter(p => p.version_actual);
  const [pid, setPid] = useState("");
  const [nombre, setNombre] = useState("");
  const [desc, setDesc] = useState("");
  const create = () => api("/plantillas", { method: "POST", json: { proyecto: pid, nombre, descripcion: desc } })
    .then(() => { setNombre(""); setDesc(""); setPid(""); load(); toast("Plantilla guardada"); }).catch(e => toast(e.message, "error"));

  // desde una referencia
  const [ref, setRef] = useState<File[]>([]);
  const [rNombre, setRNombre] = useState("");
  const [rCliente, setRCliente] = useState("");
  const learn = () => {
    const fd = new FormData(); fd.append("archivo", ref[0]); fd.append("nombre", rNombre); fd.append("cliente", rCliente);
    api("/plantillas/aprender", { method: "POST", body: fd })
      .then(() => { setRef([]); setRNombre(""); toast("Claude está estudiando el estilo. Tarda unos minutos."); })
      .catch(e => toast(e.message, "error"));
  };
  const del = (id: string) => { if (confirm("¿Borrar esta plantilla?")) api(`/plantillas/${encodeURIComponent(id)}`, { method: "DELETE" }).then(load); };
  const saveRules = (id: string, reglas: string) => api(`/plantillas/${encodeURIComponent(id)}`, { method: "PUT", json: { reglas } }).then(() => toast("Reglas guardadas"));

  return (
    <div className="grid grid-cols-12 gap-6">
      <div className="col-span-12 xl:col-span-8 card p-7">
        <div className="h-card">Plantillas</div>
        <div className="label mb-5 max-w-2xl">Un estilo que ya funcionó (ritmo de cortes, textos, animación, música). Con una plantilla, un video nuevo se arma
          en segundos y <b>sin gastar Claude</b>: sólo completás los textos.</div>
        {learning.map(j => (
          <div key={j.id} className="mb-4 flex items-center gap-3 rounded-[18px] bg-lime/40 p-4 text-sm"><Loader2 size={18} className="animate-spin" /><span className="font-medium">{j.title}</span><span className="text-ink-muted">{j.stage}</span></div>
        ))}
        {list?.length === 0 && !learning.length && <Empty icon={<LayoutTemplate size={26} strokeWidth={1.5} />} title="Sin plantillas todavía"
          text="Guardá un video aprobado como plantilla, o dejá que Claude aprenda el estilo de un reel que te guste." />}
        <div className="space-y-3">
          {list?.map(t => (
            <div key={t.id} className="sub bg-surface-muted/60 p-4">
              <div className="flex items-start gap-4">
                <div className="w-28 aspect-[4/3] rounded-[14px] overflow-hidden bg-line shrink-0">
                  {t.preview && <img src={`/api/plantillas/${t.id}/preview`} className="size-full object-cover" alt="" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2"><div className="font-semibold truncate">{t.nombre}</div>
                    {t.cliente && <Badge tone="lime">{clientes?.find(c => c.slug === t.cliente)?.nombre ?? t.cliente}</Badge>}</div>
                  <div className="label line-clamp-2 mt-0.5">{t.descripcion || `de ${t.origen}`}</div>
                  <div className="flex gap-2 mt-3 flex-wrap">
                    <Badge>{t.duracion} s</Badge><Badge>{t.planos} planos</Badge><Badge>{t.campos.length} textos</Badge><Badge tone="muted">{fecha(t.creada)}</Badge>
                  </div>
                </div>
                <div className="flex gap-1">
                  <button className="icon-btn size-9 bg-surface" title="Ver detalles" onClick={() => setOpen(open === t.id ? null : t.id)}><ChevronDown size={16} className={cx("transition-transform", open === t.id && "rotate-180")} /></button>
                  <button className="icon-btn size-9 bg-surface hover:text-danger" title="Borrar" onClick={() => del(t.id)}><Trash2 size={15} /></button>
                </div>
              </div>
              {open === t.id && <Detail t={t} onSave={saveRules} />}
            </div>
          ))}
        </div>
      </div>

      <div className="col-span-12 xl:col-span-4 flex flex-col gap-6">
        <div className="card p-6 space-y-4">
          <div className="flex items-center gap-2"><Zap size={18} strokeWidth={1.75} /><div className="font-semibold">Desde un video que ya aprobaste</div></div>
          <div className="label -mt-2">Gratis: no usa Claude.</div>
          <Field label="Proyecto">
            <select className="input" value={pid} onChange={e => { setPid(e.target.value); const p = withVersion.find(x => x.id === e.target.value); if (p && !nombre) setNombre(p.titulo); }}>
              <option value="">Elegí un proyecto…</option>
              {withVersion.map(p => <option key={p.id} value={p.id}>{p.titulo} · {p.version_actual}</option>)}
            </select>
          </Field>
          <Field label="Nombre"><input className="input" value={nombre} onChange={e => setNombre(e.target.value)} placeholder="Ej: Lanzamiento de producto 11 s" /></Field>
          <Field label="Para qué sirve"><input className="input" value={desc} onChange={e => setDesc(e.target.value)} placeholder="Ej: promo con cuenta regresiva" /></Field>
          <button className="btn-primary w-full" disabled={!pid || !nombre.trim()} onClick={create}>Guardar plantilla</button>
        </div>

        <div className="rounded-[28px] bg-lime p-6 space-y-4 text-lime-ink">
          <div className="flex items-center gap-2"><Sparkles size={18} strokeWidth={1.75} /><div className="font-semibold">Aprender de una referencia</div></div>
          <div className="text-sm text-lime-ink/80 -mt-2">Claude estudia un reel <b>una sola vez</b> y lo guarda como plantilla. Después la usás todas las veces que quieras sin volver a gastar.</div>
          <Dropzone label="El reel de referencia" hint="Un video cuyo estilo quieras repetir" files={ref} onFiles={setRef} multiple={false} />
          <input className="input bg-surface" value={rNombre} onChange={e => setRNombre(e.target.value)} placeholder="Nombre del estilo" />
          <select className="input bg-surface" value={rCliente} onChange={e => setRCliente(e.target.value)}>
            <option value="">Para cualquier cliente</option>
            {clientes?.map(c => <option key={c.slug} value={c.slug}>{c.nombre}</option>)}
          </select>
          {estado && !estado.claude.ok
            ? <button className="btn-primary w-full" onClick={openClaude}>Conectar Claude</button>
            : <button className="btn-primary w-full" disabled={!ref.length || !rNombre.trim()} onClick={learn}>Aprender estilo</button>}
        </div>
      </div>
    </div>
  );
}

function Detail({ t, onSave }: { t: Plantilla; onSave: (id: string, reglas: string) => void }) {
  const [reglas, setReglas] = useState(t.reglas ?? "");
  return (
    <div className="mt-4 grid grid-cols-2 gap-4">
      <div>
        <div className="label mb-2">Textos que se completan</div>
        <ul className="space-y-1 text-sm max-h-56 overflow-auto">
          {t.campos.map(c => <li key={c.key} className="flex gap-2"><span className="font-mono text-[12px] text-ink-muted w-8">E{c.escena}</span><span className="text-ink-muted w-24 shrink-0">{c.label}</span><span className="truncate">{c.ejemplo}</span></li>)}
        </ul>
      </div>
      <div>
        <div className="label mb-2">Reglas del estilo (Claude las respeta en los cambios)</div>
        <textarea className="input h-40 py-2 text-sm resize-none bg-surface" value={reglas} onChange={e => setReglas(e.target.value)} placeholder="- Títulos cortos, máximo 3 palabras&#10;- Cortes cada 2 segundos" />
        <button className="btn-secondary btn-sm mt-2" onClick={() => onSave(t.id, reglas)}>Guardar reglas</button>
      </div>
    </div>
  );
}
