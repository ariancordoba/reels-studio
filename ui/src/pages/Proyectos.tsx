import { useState } from "react";
import { FolderOpen } from "lucide-react";
import { ETAPAS, activeJob, hace, thumbUrl, useStore, type Etapa, type Proyecto } from "../api";
import { Badge, Empty, Progress, Segmented } from "../components/ui";
import { go } from "../App";
import { jobFraction, statusOf } from "./Inicio";

export default function Proyectos({ proyectos }: { proyectos: Proyecto[] }) {
  const { trabajos, clientes, proyectos: all } = useStore();
  const [f, setF] = useState<"todos" | Etapa>("todos");
  const list = proyectos.filter(p => f === "todos" || p.etapa === f);
  return (
    <div className="card p-7">
      <div className="flex items-center justify-between mb-6 gap-4 flex-wrap">
        <div><div className="h-card">Proyectos</div><div className="label">{proyectos.length} en total</div></div>
        <Segmented size="sm" value={f} onChange={setF}
          options={[{ id: "todos" as const, label: "Todos" }, ...ETAPAS.map(e => ({ id: e.id, label: e.label }))]} />
      </div>
      {all === null ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-5">{Array.from({ length: 6 }, (_, i) => <div key={i} className="skeleton aspect-[9/14]" />)}</div>
      ) : list.length === 0 ? (
        <Empty icon={<FolderOpen size={28} strokeWidth={1.5} />} title="No hay proyectos acá" text="Cuando armes un video nuevo va a aparecer en esta lista."
          action={<button className="btn-primary" onClick={() => go("nuevo")}>Nuevo video</button>} />
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-5">
          {list.map(p => {
            const j = activeJob(p, trabajos);
            const st = statusOf(p, j);
            const frac = jobFraction(j);
            return (
              <button key={p.id} onClick={() => go(`proyecto/${p.id}`)} className="text-left group">
                <div className="relative aspect-[9/14] rounded-[22px] overflow-hidden bg-surface-muted">
                  <img src={thumbUrl(p.id, p.actualizado)} alt="" className="size-full object-cover group-hover:scale-[1.02] transition-transform duration-200"
                    onError={e => { (e.target as HTMLImageElement).style.visibility = "hidden"; }} />
                  <div className="absolute top-3 left-3"><Badge tone={st.tone} dot>{st.label}</Badge></div>
                  <div className="absolute top-3 right-3 chip bg-surface font-mono">{p.version_actual ?? "—"}</div>
                  {frac != null && <div className="absolute left-3 right-3 bottom-3 rounded-full bg-surface p-1.5"><Progress value={frac} /></div>}
                </div>
                <div className="px-1 pt-3">
                  <div className="font-semibold truncate">{p.titulo}</div>
                  <div className="label truncate">{clientes?.find(c => c.slug === p.cliente)?.nombre ?? p.cliente} · {hace(p.actualizado)}</div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
