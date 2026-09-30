// Cliente de la API local + store global que se refresca con los eventos SSE del servidor.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

export type Etapa = "crudos" | "guion" | "vista_previa" | "render" | "entregado";

export interface Trabajo {
  id: string; kind: string; project: string; title: string; lane: string;
  status: "en_cola" | "corriendo" | "listo" | "error" | "cancelado";
  stage: string; done: number; total: number; log: string[];
  result: { ok?: boolean; message?: string; fraccion?: number; version?: string; [k: string]: unknown } | null;
  created: number; started: number | null; finished: number | null; eta_s?: number;
}

export interface Version {
  id: string; fecha: string; resumen: string; pedido: string; tiene_spec: boolean; duracion: number | null;
  video: boolean; borrador: boolean; stills: string[]; tamano_mb: number | null;
}

export interface Proyecto {
  id: string; titulo: string; cliente: string; creado: string; actualizado: string;
  version_actual: string | null; etapa: Etapa; duracion: number | null; pendiente: string | null;
  prioridad: "alta" | "media" | "baja"; entrega: string | null; entregado?: string;
  versiones: Version[]; trabajos: Trabajo[]; lock: { machine: string; what: string } | null;
  chat?: ChatMsg[]; instrucciones?: string;
}

export interface ChatMsg { rol: "yo" | "claude"; texto: string; fecha: string; version?: string; ok?: boolean; tipo?: string; sin_claude?: boolean }

export interface Cliente {
  slug: string; nombre: string; accent: string; text: string; display_font: string; serif_font: string;
  footer: string[]; darken: number; logo: string | null; notas: string; fonts: string[];
}

export interface ClaudeStatus { ok: boolean; installed: boolean; logged_in: boolean; version?: string; plan?: string; detail: string }

export interface Estado {
  config: { data_dir: string | null; user_name: string; quality: string; claude_model: string | null; claude_modo?: string; update_source?: string; guia_oculta?: boolean; auto_update?: boolean };
  data_dir: string; machine: string; claude: ClaudeStatus; configurado: boolean; sugerido: string;
}

export class ApiError extends Error {}

export async function api<T = unknown>(path: string, opts: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = opts;
  const r = await fetch(`/api${path}`, {
    ...rest,
    headers: json !== undefined ? { "Content-Type": "application/json", ...(rest.headers || {}) } : rest.headers,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (!r.ok) {
    let msg = `Error ${r.status}`;
    try { const d = await r.json(); msg = typeof d.detail === "string" ? d.detail : d.message || msg; } catch { /* sin cuerpo */ }
    throw new ApiError(msg);
  }
  return r.json() as Promise<T>;
}

export const fileUrl = (pid: string, rel: string, bust?: string | number) =>
  `/api/archivo/${encodeURIComponent(pid)}/${rel.split("/").map(encodeURIComponent).join("/")}${bust ? `?v=${bust}` : ""}`;
export const thumbUrl = (pid: string, bust?: string | number) => `/api/miniatura/${encodeURIComponent(pid)}?v=${bust ?? ""}`;

// ── store
export interface Store {
  estado: Estado | null;
  proyectos: Proyecto[] | null;
  clientes: Cliente[] | null;
  trabajos: Record<string, Trabajo>;
  refresh: (what?: ("estado" | "proyectos" | "clientes")[]) => Promise<void>;
  toast: (msg: string, kind?: "ok" | "error") => void;
  tick: number; // sube con cada evento de chat/proyecto: las pantallas de detalle recargan
}

export const StoreCtx = createContext<Store>(null as unknown as Store);
export const useStore = () => useContext(StoreCtx);

export function useStoreState(toast: Store["toast"]): Store {
  const [estado, setEstado] = useState<Estado | null>(null);
  const [proyectos, setProyectos] = useState<Proyecto[] | null>(null);
  const [clientes, setClientes] = useState<Cliente[] | null>(null);
  const [trabajos, setTrabajos] = useState<Record<string, Trabajo>>({});
  const [tick, setTick] = useState(0);
  const pending = useRef<number | null>(null);

  const refresh = useCallback(async (what: ("estado" | "proyectos" | "clientes")[] = ["estado", "proyectos", "clientes"]) => {
    await Promise.all([
      what.includes("estado") && api<Estado>("/estado").then(setEstado),
      what.includes("proyectos") && api<Proyecto[]>("/proyectos").then(setProyectos),
      what.includes("clientes") && api<Cliente[]>("/clientes").then(setClientes),
    ].filter(Boolean));
  }, []);

  useEffect(() => {
    refresh().catch(() => toast("No me pude conectar con el motor", "error"));
    api<Trabajo[]>("/trabajos").then(ts => setTrabajos(Object.fromEntries(ts.map(t => [t.id, t])))).catch(() => {});
    const es = new EventSource("/api/eventos");
    const soon = () => { // agrupa ráfagas de eventos en un solo refresco
      if (pending.current) return;
      pending.current = window.setTimeout(() => { pending.current = null; refresh(["proyectos"]); setTick(t => t + 1); }, 250);
    };
    es.onmessage = (m) => {
      const ev = JSON.parse(m.data);
      if (ev.type === "job") {
        const j: Trabajo = ev.job;
        setTrabajos(prev => {
          const was = prev[j.id];
          if (was && was.status !== j.status) {
            if (j.status === "listo") toast(`${j.title}: listo`, "ok");
            if (j.status === "error") toast(j.result?.message || `${j.title}: falló`, "error");
            soon();
          }
          if (!was) soon();
          return { ...prev, [j.id]: j };
        });
      } else if (ev.type === "actualizacion_lista") {
        window.dispatchEvent(new CustomEvent("rs:actualizacion", { detail: ev.version }));
      } else if (ev.type === "reiniciando") {
        window.dispatchEvent(new Event("rs:reiniciando"));
      } else if (ev.type === "projects_changed" || ev.type === "chat") {
        soon();
      }
    };
    return () => es.close();
  }, [refresh, toast]);

  return { estado, proyectos, clientes, trabajos, refresh, toast, tick };
}

// ── utilidades de presentación
export const ETAPAS: { id: Etapa; label: string }[] = [
  { id: "crudos", label: "Crudos" }, { id: "guion", label: "Guion" }, { id: "vista_previa", label: "Vista previa" },
  { id: "render", label: "Render" }, { id: "entregado", label: "Entregado" },
];
export const etapaLabel = (e: Etapa) => ETAPAS.find(x => x.id === e)?.label ?? e;

export function shortId(p: Proyecto): string {
  const initials = (p.titulo || p.id).split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join("").toUpperCase();
  return `${initials || "RS"}-${p.version_actual ?? "v0"}`;
}

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
export function fecha(iso?: string | null, withTime = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(+d)) return iso;
  const base = `${d.getDate()} ${MESES[d.getMonth()]}`;
  return withTime ? `${base} · ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}` : base;
}

export function hace(ts?: number | string | null): string {
  if (!ts) return "";
  const t = typeof ts === "number" ? ts * 1000 : +new Date(ts);
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return "recién";
  if (s < 3600) return `hace ${Math.round(s / 60)} min`;
  if (s < 86400) return `hace ${Math.round(s / 3600)} h`;
  return `hace ${Math.round(s / 86400)} d`;
}

export const dur = (s?: number | null) =>
  s == null ? "—" : `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.round(s % 60)).padStart(2, "0")}`;

export function needsReview(p: Proyecto) { return p.etapa === "vista_previa" && !p.pendiente; }
export function activeJob(p: Proyecto, trabajos: Record<string, Trabajo>): Trabajo | undefined {
  const live = Object.values(trabajos).filter(t => t.project === p.id && (t.status === "corriendo" || t.status === "en_cola"));
  return live.sort((a, b) => b.created - a.created)[0] ?? p.trabajos?.[0];
}
