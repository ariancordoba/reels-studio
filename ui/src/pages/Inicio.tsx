import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, Check, ChevronRight, Film, SlidersHorizontal, Sparkles, X } from "lucide-react";
import {
  ETAPAS, activeJob, dur, etapaLabel, fecha, hace, needsReview, shortId, thumbUrl, useStore, type Proyecto, type Trabajo,
} from "../api";
import { Badge, Progress, Segmented, TickGauge, cx } from "../components/ui";
import { go, openClaude } from "../App";

const STAGE_PROGRESS = { crudos: 0.1, guion: 0.35, vista_previa: 0.6, render: 0.8, entregado: 1 } as const;

export function jobFraction(j?: Trabajo | null): number | null {
  if (!j || (j.status !== "corriendo" && j.status !== "en_cola")) return null;
  if (typeof j.result?.fraccion === "number") return j.result.fraccion;
  return j.total ? j.done / j.total : 0.05;
}

export function statusOf(p: Proyecto, j?: Trabajo): { label: string; tone: "lime" | "warn" | "muted" | "danger" | "ink" | "ok" } {
  if (j && (j.status === "corriendo" || j.status === "en_cola")) {
    if (j.lane === "claude") return { label: j.status === "en_cola" ? "En cola" : "Claude trabajando", tone: "lime" };
    return { label: j.status === "en_cola" ? "En cola" : j.kind === "stills" ? "Vista previa" : "Renderizando", tone: "warn" };
  }
  if (p.pendiente) return { label: "Cambio pedido", tone: "warn" };
  if (p.etapa === "entregado") return { label: "Entregado", tone: "ink" };
  if (needsReview(p)) return { label: "Esperando revisión", tone: "lime" };
  if (p.etapa === "crudos") return { label: "Sin guion", tone: "muted" };
  return { label: etapaLabel(p.etapa), tone: "muted" };
}

export default function Inicio({ proyectos }: { proyectos: Proyecto[] }) {
  const { proyectos: all, trabajos, clientes } = useStore();
  if (all === null) return <Skeleton />;
  if (all.length === 0) return <GettingStarted force />;
  const hero = [...proyectos].sort((a, b) => {
    const ja = activeJob(a, trabajos), jb = activeJob(b, trabajos);
    const la = ja && ja.status === "corriendo" ? 1 : 0, lb = jb && jb.status === "corriendo" ? 1 : 0;
    return lb - la || (b.actualizado ?? "").localeCompare(a.actualizado ?? "");
  })[0];
  return (
    <div className="grid grid-cols-12 gap-6">
      <div className="col-span-12 empty:hidden"><GettingStarted /></div>
      <div className="col-span-12 2xl:col-span-5 xl:col-span-5">{hero ? <Hero p={hero} /> : <div className="card h-full" />}</div>
      <div className="col-span-12 xl:col-span-7"><Resumen proyectos={proyectos} nClientes={clientes?.length ?? 0} /></div>
      <div className="col-span-12 xl:col-span-8"><Atencion proyectos={proyectos} /></div>
      <div className="col-span-12 xl:col-span-4 flex flex-col gap-6">
        <ClaudeCard proyectos={proyectos} />
        <RenderCard proyectos={proyectos} />
      </div>
    </div>
  );
}

function Skeleton() {
  return <div className="grid grid-cols-12 gap-6">
    <div className="col-span-5 skeleton h-[380px] rounded-[28px]" /><div className="col-span-7 skeleton h-[380px] rounded-[28px]" />
    <div className="col-span-8 skeleton h-[520px] rounded-[28px]" /><div className="col-span-4 skeleton h-[520px] rounded-[28px]" />
  </div>;
}

function Hero({ p }: { p: Proyecto }) {
  const { trabajos, clientes } = useStore();
  const j = activeJob(p, trabajos);
  const frac = jobFraction(j) ?? STAGE_PROGRESS[p.etapa] ?? 0.1;
  const st = statusOf(p, j);
  const cli = clientes?.find(c => c.slug === p.cliente);
  const v = p.versiones.at(-1);
  return (
    <div className="card p-2.5 h-full min-h-[380px]">
      <div className="relative h-full rounded-[22px] overflow-hidden bg-ink">
        <img src={thumbUrl(p.id, p.actualizado)} className="absolute inset-0 size-full object-cover opacity-90" alt=""
          onError={e => { (e.target as HTMLImageElement).style.display = "none"; }} />
        <div className="absolute inset-0 bg-gradient-to-b from-black/5 via-transparent to-black/25" />
        <div className="absolute top-4 left-4 right-4 flex justify-between">
          <span className="chip bg-surface h-9 px-3.5"><Film size={16} strokeWidth={1.75} /> <span className="font-mono">{shortId(p)}</span></span>
          <Badge tone={st.tone === "muted" ? "muted" : st.tone} dot>{st.label}</Badge>
        </div>
        <div className="absolute left-4 right-4 bottom-4 sub bg-surface p-5">
          <div className="flex items-start gap-3">
            <div className="flex-1 min-w-0">
              <div className="text-[20px] font-semibold tracking-[-0.01em] truncate">{p.titulo}</div>
              <div className="label truncate">{cli?.nombre ?? p.cliente} · {j?.status === "corriendo" ? j.stage : `actualizado ${hace(p.actualizado)}`}</div>
            </div>
            <button className="icon-btn bg-surface-muted size-10" onClick={() => go(`proyecto/${p.id}`)}><ArrowUpRight size={18} strokeWidth={1.75} /></button>
          </div>
          <div className="flex items-center gap-4 my-4">
            <Progress value={frac} className="flex-1" />
            <span className="font-medium text-sm w-10 text-right">{Math.round(frac * 100)}%</span>
          </div>
          <div className="grid grid-cols-3 rounded-[16px] border border-line divide-x divide-line">
            <Cell k="Duración" v={dur(v?.duracion ?? p.duracion)} mono />
            <Cell k="Etapa" v={etapaLabel(p.etapa)} />
            <Cell k="Entrega" v={fecha(p.entrega)} mono />
          </div>
        </div>
      </div>
    </div>
  );
}

function Cell({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return <div className="px-4 py-3 min-w-0"><div className="label">{k}</div><div className={cx("font-medium truncate", mono && "font-mono")}>{v}</div></div>;
}

type Period = "hoy" | "7" | "30";
function Resumen({ proyectos, nClientes }: { proyectos: Proyecto[]; nClientes: number }) {
  const { trabajos } = useStore();
  const [period, setPeriod] = useState<Period>("7");
  const inPeriod = useMemo(() => {
    const days = period === "hoy" ? 1 : Number(period);
    const since = Date.now() - days * 86400e3;
    return proyectos.filter(p => +new Date(p.actualizado || p.creado) >= since);
  }, [proyectos, period]);
  const activos = inPeriod.filter(p => p.etapa !== "entregado");
  const rendering = inPeriod.filter(p => { const j = activeJob(p, trabajos); return p.etapa === "render" || (j && j.lane === "render" && j.status === "corriendo"); });
  const review = inPeriod.filter(needsReview);
  const entregados = inPeriod.filter(p => p.etapa === "entregado");
  const counts = ETAPAS.map(e => ({ ...e, n: inPeriod.filter(p => p.etapa === e.id).length }));
  const max = Math.max(...counts.map(c => c.n));
  const clientesActivos = new Set(activos.map(p => p.cliente)).size;
  return (
    <div className="card p-7 h-full">
      <div className="flex items-center justify-between mb-5">
        <div className="h-card">Resumen</div>
        <Segmented value={period} onChange={setPeriod} options={[{ id: "hoy", label: "Hoy" }, { id: "7", label: "7 días" }, { id: "30", label: "30 días" }]} />
      </div>
      <div className="grid grid-cols-4 gap-3">
        <Stat dark k="Proyectos activos" n={activos.length} sub={`${clientesActivos || nClientes} clientes`} />
        <Stat k="En render" n={rendering.length} sub={rendering.length ? "renderizando ahora" : "nada en cola"} />
        <Stat k="Esperando revisión" n={review.length} sub="listos para mirar" />
        <Stat k="Entregados" n={entregados.length} sub={period === "hoy" ? "hoy" : `últimos ${period} días`} />
      </div>
      <div className="mt-3 sub bg-surface-muted/60 p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="font-medium">Pipeline</div>
          <button className="text-sm font-medium flex items-center gap-1" onClick={() => go("proyectos")}>Ver <ChevronRight size={16} /></button>
        </div>
        <div className="flex gap-2 h-9">
          {counts.map((c, i) => (
            <div key={c.id} className={cx("rounded-full transition-all duration-300",
              i === counts.length - 1 ? "bg-ink" : c.n === max && max > 0 ? "bg-lime" : "bg-line")}
              style={{ flex: `${Math.max(c.n, 0.6)} 1 0` }} title={`${c.label}: ${c.n}`} />
          ))}
        </div>
        <div className="flex gap-2 mt-3">
          {counts.map(c => (
            <div key={c.id} style={{ flex: `${Math.max(c.n, 0.6)} 1 0` }} className="min-w-[64px]">
              <div className="font-semibold">{c.n}</div><div className="label">{c.label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({ k, n, sub, dark }: { k: string; n: number; sub: string; dark?: boolean }) {
  return (
    <div className={cx("sub p-5", dark ? "bg-ink text-white" : "bg-surface-muted/60")}>
      <div className={cx("text-[13px]", dark ? "text-white/60" : "text-ink-muted")}>{k}</div>
      <div className="num mt-2">{n}</div>
      <div className={cx("text-[13px] mt-2", dark ? "text-white/60" : "text-ink-muted")}>{sub}</div>
    </div>
  );
}

function attention(p: Proyecto, j?: Trabajo): { text: string; prio: "alta" | "media" | "baja" } | null {
  if (j && j.status === "error") return { text: j.result?.message?.slice(0, 80) || "Falló el último trabajo", prio: "alta" };
  if (p.pendiente) return { text: `Cambio pedido: ${p.pendiente}`, prio: p.prioridad === "alta" ? "alta" : "media" };
  if (needsReview(p)) return { text: `Revisar ${p.version_actual}`, prio: p.prioridad ?? "media" };
  if (p.etapa === "crudos" && !(j && j.status === "corriendo")) return { text: "Todavía sin primera versión", prio: "media" };
  if (p.etapa === "render" && !(j && j.status === "corriendo")) return { text: "Render listo para exportar", prio: "baja" };
  return null;
}

function Atencion({ proyectos }: { proyectos: Proyecto[] }) {
  const { trabajos, clientes } = useStore();
  const lastJob = (p: Proyecto) => Object.values(trabajos).filter(t => t.project === p.id).sort((a, b) => b.created - a.created)[0];
  const rank = { alta: 0, media: 1, baja: 2 };
  const rows = proyectos.map(p => ({ p, a: attention(p, lastJob(p)) })).filter(r => r.a)
    .sort((x, y) => rank[x.a!.prio] - rank[y.a!.prio] || (x.p.entrega ?? "9").localeCompare(y.p.entrega ?? "9"));
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, 5);
  return (
    <div className="card p-3 h-full flex flex-col">
      <div className="flex items-start justify-between px-4 pt-4 pb-4">
        <div>
          <div className="h-card">Necesita atención</div>
          <div className="label mt-0.5">{rows.length} {rows.length === 1 ? "proyecto" : "proyectos"} · actualizado {hace(Date.now() / 1000)}</div>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone="lime"><Sparkles size={14} strokeWidth={1.75} /> Por prioridad</Badge>
          <button className="icon-btn bg-surface-muted size-10" onClick={() => go("proyectos")}><SlidersHorizontal size={17} strokeWidth={1.75} /></button>
        </div>
      </div>
      {rows.length === 0 ? (
        <div className="flex-1 grid place-items-center label py-12">Todo al día. Nada pendiente.</div>
      ) : (
        <table className="w-full text-left">
          <thead>
            <tr className="text-[13px] text-ink-muted">
              {["Proyecto", "Cliente", "Etapa", "Pendiente", "Prioridad", "Entrega"].map((h, i) => (
                <th key={h} className={cx("font-normal py-3 bg-surface-muted/70", i === 0 && "pl-4 rounded-l-[16px]", i === 5 && "pr-4 rounded-r-[16px]")}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map(({ p, a }) => {
              const cli = clientes?.find(c => c.slug === p.cliente);
              return (
                <tr key={p.id} onClick={() => go(`proyecto/${p.id}`)} className="cursor-pointer hover:bg-surface-muted/70 transition-colors duration-150 border-b border-line last:border-0">
                  <td className="pl-4 py-4 font-mono text-sm">{shortId(p)}</td>
                  <td className="py-4 pr-3"><div className="font-medium truncate max-w-[180px]">{cli?.nombre ?? p.cliente}</div><div className="label truncate max-w-[180px]">{p.titulo}</div></td>
                  <td className="py-4 pr-3"><span className="chip whitespace-nowrap">{etapaLabel(p.etapa)}</span></td>
                  <td className="py-4 pr-3 text-sm max-w-[260px]"><div className="truncate">{a!.text}</div></td>
                  <td className="py-4 pr-3"><Badge tone={a!.prio === "alta" ? "danger" : a!.prio === "media" ? "warn" : "muted"}>{a!.prio === "alta" ? "Alta" : a!.prio === "media" ? "Media" : "Baja"}</Badge></td>
                  <td className="py-4 pr-4 font-mono text-sm whitespace-nowrap">{fecha(p.entrega)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <div className="flex-1" />
      <div className="flex items-center justify-between px-4 py-4 text-sm">
        <span className="text-ink-muted">Mostrando {shown.length}{rows.length > shown.length ? ` de ${rows.length}` : ""}</span>
        {rows.length > 5 && <button className="font-medium flex items-center gap-1" onClick={() => setAll(!all)}>{all ? "Ver menos" : "Ver todos"} <ChevronRight size={16} /></button>}
      </div>
    </div>
  );
}

function ClaudeCard({ proyectos }: { proyectos: Proyecto[] }) {
  const { trabajos, estado } = useStore();
  const review = proyectos.filter(needsReview);
  const claudeJobs = Object.values(trabajos).filter(t => t.lane === "claude");
  const working = claudeJobs.filter(t => t.status === "corriendo" || t.status === "en_cola");
  const last = claudeJobs.filter(t => t.finished).sort((a, b) => (b.finished ?? 0) - (a.finished ?? 0))[0];
  const rendering = Object.values(trabajos).filter(t => t.lane === "render" && t.status === "corriendo").length;
  const sinGuion = proyectos.filter(p => p.etapa === "crudos").length;
  const off = estado && !estado.claude.ok;
  const headline = off ? "Claude no está conectado" : working.length ? `Trabajando en ${working.length === 1 ? "1 video" : `${working.length} videos`}`
    : review.length ? `${review.length === 1 ? "1 video listo" : `${review.length} videos listos`} para revisar` : "Todo en orden";
  return (
    <div className="rounded-[28px] bg-ink text-white p-6">
      <div className="flex items-center gap-3">
        <Sparkles size={20} strokeWidth={1.75} className="text-lime" />
        <div className="flex-1 font-medium">Claude</div>
        <span className="font-mono text-[13px] text-white/50">{last ? hace(last.finished) : ""}</span>
      </div>
      <div className="text-[24px] font-semibold tracking-[-0.02em] leading-tight mt-4">{headline}</div>
      <ul className="mt-4 space-y-2.5 text-[15px] text-white/85">
        {off && <li className="flex gap-3 items-center"><span className="size-2 rounded-full bg-danger" />{estado!.claude.detail}</li>}
        {working.slice(0, 2).map(t => <li key={t.id} className="flex gap-3 items-center"><span className="size-2 rounded-full bg-lime" /><span className="truncate">{t.stage || t.title}</span></li>)}
        <li className="flex gap-3 items-center"><span className="size-2 rounded-full bg-danger" />{proyectos.filter(p => p.pendiente).length} con cambios pedidos</li>
        <li className="flex gap-3 items-center"><span className="size-2 rounded-full bg-[#f5b544]" />{rendering} renderizando ahora</li>
        <li className="flex gap-3 items-center"><span className="size-2 rounded-full bg-lime" />{sinGuion} sin primera versión</li>
      </ul>
      <button className="btn-lime w-full mt-6 h-12" onClick={() => off ? openClaude() : go(review[0] ? `proyecto/${review[0].id}` : "proyectos")}>
        {off ? "Conectar" : "Revisar"}
      </button>
    </div>
  );
}

function RenderCard({ proyectos }: { proyectos: Proyecto[] }) {
  const { trabajos } = useStore();
  const running = Object.values(trabajos).filter(t => t.lane === "render" && (t.status === "corriendo" || t.status === "en_cola"))
    .sort((a, b) => (a.status === "corriendo" ? -1 : 1) - (b.status === "corriendo" ? -1 : 1))[0];
  const recent = (list: Proyecto[]) => [...list].sort((a, b) => (b.actualizado ?? "").localeCompare(a.actualizado ?? ""))[0];
  const p = running ? proyectos.find(x => x.id === running.project)
    : recent(proyectos.filter(x => x.versiones.some(v => v.video))) ?? recent(proyectos.filter(x => x.versiones.length));
  const v = p?.versiones.filter(x => x.video).at(-1) ?? p?.versiones.at(-1);
  const frac = running ? jobFraction(running) ?? 0 : v?.video ? 1 : null;
  return (
    <div className="card p-3">
      <div className="flex items-center justify-between px-3 pt-3 pb-4">
        <div className="h-card">Render</div>
        {p && <button className="icon-btn bg-surface-muted size-10" onClick={() => go(`proyecto/${p.id}`)}><ArrowUpRight size={18} strokeWidth={1.75} /></button>}
      </div>
      <div className="rounded-[22px] bg-lime p-4">
        <TickGauge value={frac} big={frac == null ? "—" : `${Math.round(frac * 100)}%`}
          label={running ? (running.status === "en_cola" ? "en cola" : running.stage || "renderizando") : frac === 1 ? "listo para exportar" : "nada renderizado"} />
        <div className="mt-4 h-11 px-4 rounded-full bg-surface flex items-center justify-between text-sm">
          <span className="font-medium truncate">{p?.titulo ?? "Sin renders todavía"}</span>
          <span className="font-mono text-ink-muted whitespace-nowrap">
            {running?.total ? `${running.done} / ${running.total} cuadros` : v ? `${v.id}` : ""}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-2 mt-2">
          <Mini k="Versiones" v={String(p?.versiones.length ?? 0)} />
          <Mini k="Duración" v={v?.duracion ? `${v.duracion} s` : "—"} />
          <Mini k="Tamaño" v={v?.tamano_mb ? `${v.tamano_mb} MB` : "—"} />
        </div>
        {running?.eta_s != null && running.status === "corriendo" &&
          <div className="text-center text-[13px] text-lime-ink/70 mt-3">Faltan ~{Math.max(1, Math.round(running.eta_s))} s</div>}
      </div>
    </div>
  );
}

function Mini({ k, v }: { k: string; v: string }) {
  return <div className="rounded-[16px] bg-surface px-3.5 py-3"><div className="text-[12px] text-ink-muted">{k}</div><div className="font-semibold font-mono">{v}</div></div>;
}


// ── guía de primeros pasos: se marca sola a medida que se completa
const GUIA_KEY = "rs.guia-oculta";

export function GettingStarted({ force }: { force?: boolean }) {
  const { estado, clientes, proyectos } = useStore();
  const [hidden, setHidden] = useState(() => { try { return localStorage.getItem(GUIA_KEY) === "1"; } catch { return false; } });
  const [nPlantillas, setN] = useState<number | null>(null);
  useEffect(() => { fetch("/api/plantillas").then(r => r.json()).then(l => setN(l.length)).catch(() => setN(0)); }, []);
  const steps = [
    { done: !!estado?.claude.ok, title: "Conectá Claude", text: "Iniciá sesión con tu cuenta de Claude (Pro o Max).", cta: "Conectar", act: () => window.dispatchEvent(new Event("rs:claude")) },
    { done: (clientes?.length ?? 0) > 0, title: "Cargá un cliente", text: "Colores, fuentes y pie de página de la marca.", cta: "Crear cliente", act: () => go("clientes/nuevo") },
    { done: (proyectos?.length ?? 0) > 0, title: "Hacé tu primer video", text: "Subí crudos y una referencia que te guste.", cta: "Nuevo video", act: () => go("nuevo") },
    { done: (proyectos ?? []).some(p => p.versiones.some(v => v.video)), title: "Render final y exportá", text: "En el proyecto: Render final → Exportar.", cta: "Ver proyectos", act: () => go("proyectos") },
    { done: (nPlantillas ?? 0) > 0, title: "Guardá una plantilla", text: "El próximo video sale en segundos y sin gastar Claude.", cta: "Plantillas", act: () => go("plantillas") },
  ];
  const doneCount = steps.filter(x => x.done).length;
  if (!estado || nPlantillas === null) return null;
  if (!force && (hidden || doneCount === steps.length)) return null;
  const next = steps.findIndex(x => !x.done);
  return (
    <div className="card p-7">
      <div className="flex items-start justify-between mb-5">
        <div>
          <div className="h-card">Primeros pasos</div>
          <div className="label">{doneCount} de {steps.length} listos{doneCount === steps.length ? " · ¡ya sabés usar Reels Studio!" : ""}</div>
        </div>
        {!force && <button className="icon-btn size-9 bg-surface-muted" title="Ocultar" onClick={() => { setHidden(true); try { localStorage.setItem(GUIA_KEY, "1"); } catch { /* */ } }}><X size={16} /></button>}
      </div>
      <Progress value={doneCount / steps.length} tone="lime" className="mb-5 h-2.5" />
      <div className="grid grid-cols-5 gap-3">
        {steps.map((x, i) => (
          <div key={i} className={cx("sub p-4 flex flex-col", i === next ? "bg-ink text-white" : x.done ? "bg-surface-muted/50" : "bg-surface-muted/70")}>
            <span className={cx("size-8 rounded-full grid place-items-center text-sm font-semibold mb-3",
              x.done ? "bg-lime text-lime-ink" : i === next ? "bg-white text-ink" : "bg-surface text-ink-muted")}>{x.done ? <Check size={16} /> : i + 1}</span>
            <div className={cx("font-semibold leading-tight", x.done && "line-through opacity-60")}>{x.title}</div>
            <div className={cx("text-[13px] mt-1 flex-1", i === next ? "text-white/70" : "text-ink-muted")}>{x.text}</div>
            {!x.done && <button className={cx("mt-3 btn-sm", i === next ? "btn-lime" : "btn-secondary")} onClick={x.act}>{x.cta}</button>}
          </div>
        ))}
      </div>
    </div>
  );
}
