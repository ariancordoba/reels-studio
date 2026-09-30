import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bell, ChevronDown, ChevronRight, Clapperboard, FolderOpen, Home, LayoutTemplate, Music, PanelLeft, Plus, Search,
  Settings, Sparkles, Users, AlertTriangle, Check, CircleHelp, Download, Loader2,
} from "lucide-react";
import { StoreCtx, useStore, useStoreState, needsReview, hace, type Proyecto } from "./api";
import { Badge, ICON, Modal, Toasts, Toggle, cx, type ToastItem } from "./components/ui";
import Inicio from "./pages/Inicio";
import Proyectos from "./pages/Proyectos";
import ProyectoPage from "./pages/Proyecto";
import NuevoVideo from "./pages/NuevoVideo";
import Clientes from "./pages/Clientes";
import Ajustes, { Onboarding } from "./pages/Ajustes";
import MusicaPage from "./pages/Musica";
import Plantillas from "./pages/Plantillas";
import Ayuda from "./pages/Ayuda";
import ClaudeConnect from "./components/ClaudeConnect";

/** Abre la ventana "Conectar Claude" desde cualquier pantalla. */
export const openClaude = () => window.dispatchEvent(new Event("rs:claude"));

// ── router por hash (#/proyecto/<id>)
export function useRoute(): [string[], (to: string) => void] {
  const parse = () => (location.hash.replace(/^#\/?/, "") || "inicio").split("/").map(decodeURIComponent);
  const [r, setR] = useState(parse);
  useEffect(() => {
    const on = () => setR(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return [r, (to: string) => { location.hash = to.startsWith("#") ? to : `#/${to}`; }];
}
export const go = (to: string) => { location.hash = `#/${to}`; };

const CLIENT_KEY = "rs.cliente";
function useClienteSel(): [string, (s: string) => void] {
  const [v, setV] = useState(() => { try { return localStorage.getItem(CLIENT_KEY) || ""; } catch { return ""; } });
  return [v, (s: string) => { setV(s); try { localStorage.setItem(CLIENT_KEY, s); } catch { /* sin storage */ } }];
}

export default function App() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const toast = useCallback((msg: string, kind: "ok" | "error" = "ok") => {
    const id = Date.now() + Math.random();
    setToasts(t => [...t.slice(-3), { id, msg, kind }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), kind === "error" ? 8000 : 4000);
  }, []);
  const store = useStoreState(toast);
  return (
    <StoreCtx.Provider value={store}>
      <Shell />
      <Toasts items={toasts} dismiss={id => setToasts(t => t.filter(x => x.id !== id))} />
    </StoreCtx.Provider>
  );
}

function Shell() {
  const { estado, proyectos } = useStore();
  const [route] = useRoute();
  const [cliente, setCliente] = useClienteSel();
  const [collapsed, setCollapsed] = useState(() => window.innerWidth < 1280);
  const [search, setSearch] = useState(false);
  const [claudeOpen, setClaudeOpen] = useState(false);
  const [restarting, setRestarting] = useState(false);
  useEffect(() => { const on = () => setRestarting(true); window.addEventListener("rs:reiniciando", on); return () => window.removeEventListener("rs:reiniciando", on); }, []);
  useEffect(() => { const on = () => setClaudeOpen(true); window.addEventListener("rs:claude", on); return () => window.removeEventListener("rs:claude", on); }, []);
  useEffect(() => {
    const onResize = () => setCollapsed(window.innerWidth < 1280);
    const onKey = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearch(true); } };
    window.addEventListener("resize", onResize);
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("resize", onResize); window.removeEventListener("keydown", onKey); };
  }, []);
  const filtered = useMemo(() => (proyectos ?? []).filter(p => !cliente || p.cliente === cliente), [proyectos, cliente]);

  const page = route[0];
  let body;
  if (page === "proyecto" && route[1]) body = <ProyectoPage id={route[1]} />;
  else if (page === "proyectos") body = <Proyectos proyectos={filtered} />;
  else if (page === "nuevo") body = <NuevoVideo clienteSel={cliente} />;
  else if (page === "clientes") body = <Clientes sel={route[1]} />;
  else if (page === "musica") body = <MusicaPage />;
  else if (page === "plantillas") body = <Plantillas />;
  else if (page === "ajustes") body = <Ajustes />;
  else if (page === "ayuda") body = <Ayuda />;
  else body = <Inicio proyectos={filtered} />;

  return (
    <div className="h-full flex gap-6 p-6 min-w-[1100px]">
      <Sidebar collapsed={collapsed} setCollapsed={setCollapsed} page={page} cliente={cliente} setCliente={setCliente} />
      <main className="flex-1 min-w-0 flex flex-col gap-6 overflow-y-auto overflow-x-hidden -mr-3 pr-3 pb-4">
        {page !== "proyecto" && <Header onSearch={() => setSearch(true)} proyectos={filtered} />}
        {body}
      </main>
      <SearchPalette open={search} onClose={() => setSearch(false)} proyectos={proyectos ?? []} />
      {estado && !estado.configurado && <Onboarding />}
      <ClaudeConnect open={claudeOpen} onClose={() => setClaudeOpen(false)} />
      {restarting && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-bg/95">
          <div className="text-center"><Loader2 size={36} className="animate-spin mx-auto mb-4" />
            <div className="h-card">Actualizando Reels Studio…</div>
            <div className="label mt-1">La app se va a cerrar y abrir sola en 1–2 minutos. No hace falta que hagas nada.</div></div>
        </div>
      )}
    </div>
  );
}

// ── sidebar
function Sidebar({ collapsed, setCollapsed, page, cliente, setCliente }: {
  collapsed: boolean; setCollapsed: (b: boolean) => void; page: string; cliente: string; setCliente: (s: string) => void;
}) {
  const { proyectos, clientes, estado, trabajos } = useStore();
  const [menu, setMenu] = useState(false);
  const sel = clientes?.find(c => c.slug === cliente);
  const esperando = (proyectos ?? []).filter(p => p.pendiente || Object.values(trabajos).some(t => t.project === p.id && t.lane === "claude" && (t.status === "corriendo" || t.status === "en_cola"))).length;
  const item = (id: string, label: string, Icon: typeof Home, count?: number) => (
    <button key={id} onClick={() => go(id)} title={collapsed ? label : undefined}
      className={cx("w-full flex items-center gap-3 h-11 rounded-full transition-colors duration-150",
        collapsed ? "justify-center px-0" : "px-4",
        (page === id || (id === "proyectos" && page === "proyecto")) ? "bg-ink text-white" : "text-ink hover:bg-surface-muted")}>
      <Icon {...ICON} />
      {!collapsed && <span className="flex-1 text-left text-[15px]">{label}</span>}
      {!collapsed && count != null && <span className={cx("min-w-8 h-6 px-2 rounded-full text-[12px] font-mono grid place-items-center",
        page === id ? "bg-white/15" : "bg-surface-muted text-ink-muted")}>{count}</span>}
    </button>
  );
  const claude = estado?.claude;
  const name = estado?.config.user_name || "Vos";
  return (
    <aside className={cx("card shrink-0 flex flex-col p-4 transition-[width] duration-200 ease-out", collapsed ? "w-[84px]" : "w-[280px]")}>
      <div className={cx("flex items-center gap-3 h-12 mb-3", collapsed ? "justify-center" : "px-2")}>
        <div className="size-10 rounded-[14px] bg-ink grid place-items-center shrink-0"><Clapperboard size={20} strokeWidth={1.75} className="text-lime" /></div>
        {!collapsed && <div className="flex-1 text-[19px] font-semibold tracking-[-0.02em]">Reels Studio</div>}
        {!collapsed && <button className="icon-btn size-9 bg-surface-muted" onClick={() => setCollapsed(true)} title="Colapsar"><PanelLeft size={18} strokeWidth={1.75} /></button>}
      </div>
      {collapsed && <button className="icon-btn size-10 mx-auto mb-3 bg-surface-muted" onClick={() => setCollapsed(false)} title="Expandir"><PanelLeft size={18} strokeWidth={1.75} /></button>}

      {/* selector de cliente */}
      <div className="relative mb-4">
        <button onClick={() => setMenu(!menu)}
          className={cx("w-full flex items-center gap-3 rounded-[20px] bg-surface-muted hover:bg-line/70 transition-colors", collapsed ? "p-2 justify-center" : "p-3")}>
          <ClientAvatar slug={sel?.slug} name={sel?.nombre ?? "Todos"} color={sel?.accent} logo={!!sel?.logo} />
          {!collapsed && <div className="flex-1 text-left min-w-0">
            <div className="text-[15px] font-medium truncate">{sel?.nombre ?? "Todos los clientes"}</div>
            <div className="label truncate">{sel ? `${(proyectos ?? []).filter(p => p.cliente === sel.slug).length} proyectos` : `${clientes?.length ?? 0} clientes`}</div>
          </div>}
          {!collapsed && <ChevronDown size={18} className="text-ink-muted" />}
        </button>
        {menu && (
          <div className="absolute z-30 left-0 top-full mt-2 w-[260px] card p-2 border border-line" onMouseLeave={() => setMenu(false)}>
            {[{ slug: "", nombre: "Todos los clientes", accent: "#111", logo: null }, ...(clientes ?? [])].map(c => (
              <button key={c.slug} onClick={() => { setCliente(c.slug); setMenu(false); }}
                className="w-full flex items-center gap-3 p-2 rounded-[14px] hover:bg-surface-muted text-left">
                <ClientAvatar slug={c.slug || undefined} name={c.nombre} color={c.accent} logo={!!c.logo} small />
                <span className="flex-1 truncate text-sm">{c.nombre}</span>
                {cliente === c.slug && <Check size={16} />}
              </button>
            ))}
            <button onClick={() => { setMenu(false); go("clientes/nuevo"); }} className="w-full flex items-center gap-3 p-2 rounded-[14px] hover:bg-surface-muted text-sm text-ink-muted">
              <span className="size-8 rounded-full border border-dashed border-ink-muted grid place-items-center"><Plus size={14} /></span> Nuevo cliente
            </button>
          </div>
        )}
      </div>

      <nav className="flex flex-col gap-1">
        {item("inicio", "Inicio", Home)}
        {item("proyectos", "Proyectos", FolderOpen, proyectos?.length ?? 0)}
        {item("clientes", "Clientes", Users, clientes?.length ?? 0)}
        {item("musica", "Música", Music)}
        {item("plantillas", "Plantillas", LayoutTemplate)}
        {!collapsed && <div className="mt-5 mb-1 px-4 text-[11px] font-semibold tracking-[0.08em] text-ink-muted">ESPACIO</div>}
        {collapsed && <div className="h-4" />}
        {item("ajustes", "Ajustes", Settings)}
        {item("ayuda", "Ayuda", CircleHelp)}
      </nav>

      <div className="flex-1" />

      {/* tarjeta Claude */}
      {!collapsed ? (
        <div className="rounded-[22px] bg-lime p-3 mb-3">
          <div className="flex items-center gap-3 px-1 pb-3">
            <div className="size-10 rounded-full bg-ink grid place-items-center"><Sparkles size={18} strokeWidth={1.75} className="text-lime" /></div>
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-lime-ink">Claude</div>
              <div className="text-[12px] text-lime-ink/70 truncate">{claude ? (claude.ok ? "Conectado · sesión activa" : claude.detail) : "…"}</div>
            </div>
            <Toggle on={!!claude?.ok} dark onChange={openClaude} />
          </div>
          <button onClick={() => go("proyectos")} className="w-full h-10 px-4 rounded-full bg-surface flex items-center justify-between text-sm font-medium">
            {esperando === 1 ? "1 espera cambios" : `${esperando} esperan cambios`} <ChevronRight size={16} />
          </button>
        </div>
      ) : (
        <button onClick={openClaude} title={claude?.detail} className="mx-auto mb-3 size-11 rounded-full bg-lime grid place-items-center relative">
          <Sparkles size={18} strokeWidth={1.75} />
          <span className={cx("absolute top-0.5 right-0.5 size-2.5 rounded-full border-2 border-lime", claude?.ok ? "bg-ok" : "bg-danger")} />
        </button>
      )}
      <div className={cx("flex items-center gap-3 rounded-[20px] bg-surface-muted", collapsed ? "p-2 justify-center" : "p-3")}>
        <div className="size-10 rounded-full bg-ink text-white grid place-items-center font-semibold shrink-0">{name.slice(0, 1).toUpperCase()}</div>
        {!collapsed && <div className="min-w-0"><div className="font-medium truncate">{name}</div><div className="label">Community Manager</div></div>}
      </div>
    </aside>
  );
}

export function ClientAvatar({ slug, name, color, logo, small }: { slug?: string; name: string; color?: string; logo?: boolean; small?: boolean }) {
  const s = small ? "size-8 text-[12px]" : "size-10 text-sm";
  if (slug && logo) return <img src={`/api/clientes/${slug}/logo`} className={cx(s, "rounded-full object-cover bg-surface shrink-0")} alt="" />;
  return <div className={cx(s, "rounded-full grid place-items-center font-semibold shrink-0 text-ink border border-black/5")} style={{ background: color || "#fff" }}>
    {name.split(/\s+/).slice(0, 2).map(w => w[0]).join("").toUpperCase()}
  </div>;
}

// ── header
function saludo() {
  const h = new Date().getHours();
  return h < 13 ? "Buenos días" : h < 20 ? "Buenas tardes" : "Buenas noches";
}

function Header({ onSearch, proyectos }: { onSearch: () => void; proyectos: Proyecto[] }) {
  const { estado, trabajos } = useStore();
  const [bell, setBell] = useState(false);
  const seenKey = "rs.visto";
  const [seen, setSeen] = useState(() => { try { return Number(localStorage.getItem(seenKey) || 0); } catch { return 0; } });
  const review = proyectos.filter(needsReview).length;
  const recent = Object.values(trabajos).filter(t => t.finished).sort((a, b) => (b.finished ?? 0) - (a.finished ?? 0)).slice(0, 8);
  const unread = recent.some(t => (t.finished ?? 0) * 1000 > seen);
  const ref = useRef<HTMLDivElement>(null);
  const name = estado?.config.user_name;
  const [upd, setUpd] = useState<{ version: string; lista: boolean } | null>(null);
  useEffect(() => {
    fetch("/api/actualizacion").then(r => r.json()).then(u => {
      if (u.desarrollo) return;
      if (u.lista) setUpd({ version: u.lista, lista: true }); else if (u.disponible) setUpd({ version: u.version, lista: false });
    }).catch(() => {});
    const on = (e: Event) => setUpd({ version: (e as CustomEvent).detail, lista: true });
    window.addEventListener("rs:actualizacion", on);
    return () => window.removeEventListener("rs:actualizacion", on);
  }, []);
  const { toast } = useStore();
  const restart = () => fetch("/api/actualizacion/instalar", { method: "POST" }).then(async r => { if (!r.ok) toast((await r.json()).detail || "No se pudo actualizar", "error"); });
  return (
    <header className="flex items-center gap-4 min-h-14">
      <h1 className="h-title whitespace-nowrap">{saludo()}{name ? `, ${name}` : ""}</h1>
      {review > 0 && (
        <button onClick={() => go("proyectos")} className="hidden xl:inline-flex items-center gap-2 h-10 px-4 rounded-full bg-lime text-lime-ink text-sm font-medium whitespace-nowrap">
          <AlertTriangle size={16} strokeWidth={1.75} /> {review === 1 ? "1 video espera revisión" : `${review} videos esperan revisión`}
        </button>
      )}
      {upd && (
        <button onClick={() => upd.lista ? restart() : go("ajustes")} title={upd.lista ? "Se instala sola cuando cierres la app, o ahora con un clic" : ""}
          className="inline-flex items-center gap-2 h-10 px-4 rounded-full bg-ink text-white text-sm font-medium whitespace-nowrap">
          <Download size={16} strokeWidth={1.75} className="text-lime" /> {upd.lista ? `Versión ${upd.version} lista · Reiniciar y actualizar` : `Nueva versión ${upd.version}`}
        </button>
      )}
      <div className="flex-1" />
      <button onClick={onSearch} className="flex items-center gap-3 h-14 pl-5 pr-2 rounded-full bg-surface w-[300px] max-2xl:w-[240px] shrink-0 text-ink-muted hover:text-ink transition-colors">
        <Search {...ICON} />
        <span className="flex-1 text-left whitespace-nowrap truncate">Buscar proyectos</span>
        <span className="h-9 px-3 rounded-full bg-lime text-lime-ink text-[12px] font-mono font-medium grid place-items-center">Ctrl K</span>
      </button>
      <div className="relative" ref={ref}>
        <button className="icon-btn size-14 relative" onClick={() => { setBell(!bell); const now = Date.now(); setSeen(now); try { localStorage.setItem(seenKey, String(now)); } catch { /* */ } }}>
          <Bell {...ICON} />
          {unread && <span className="absolute top-3.5 right-4 size-2.5 rounded-full bg-danger border-2 border-surface" />}
        </button>
        {bell && (
          <div className="absolute right-0 top-full mt-2 z-30 w-[360px] card p-3 border border-line" onMouseLeave={() => setBell(false)}>
            <div className="px-2 py-1.5 font-semibold">Actividad</div>
            {recent.length === 0 && <div className="label px-2 py-3">Todavía nada por acá.</div>}
            {recent.map(t => (
              <button key={t.id} onClick={() => { setBell(false); go(`proyecto/${t.project}`); }} className="w-full flex items-start gap-3 p-2 rounded-[14px] hover:bg-surface-muted text-left">
                <span className={cx("mt-1.5 size-2 rounded-full shrink-0", t.status === "listo" ? "bg-ok" : t.status === "error" ? "bg-danger" : "bg-ink-muted")} />
                <span className="flex-1 min-w-0">
                  <span className="block text-sm font-medium truncate">{t.title}</span>
                  <span className="block label truncate">{t.status === "error" ? t.result?.message : t.project}</span>
                </span>
                <span className="text-[12px] text-ink-muted font-mono whitespace-nowrap">{hace(t.finished)}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      <button className="btn-primary h-14 px-6 whitespace-nowrap shrink-0" onClick={() => go("nuevo")}><Plus {...ICON} /> Nuevo video</button>
    </header>
  );
}

function SearchPalette({ open, onClose, proyectos }: { open: boolean; onClose: () => void; proyectos: Proyecto[] }) {
  const [q, setQ] = useState("");
  const [i, setI] = useState(0);
  const res = proyectos.filter(p => `${p.titulo} ${p.cliente} ${p.id}`.toLowerCase().includes(q.toLowerCase())).slice(0, 8);
  useEffect(() => { if (open) { setQ(""); setI(0); } }, [open]);
  const pick = (p?: Proyecto) => { if (p) { go(`proyecto/${p.id}`); onClose(); } };
  return (
    <Modal open={open} onClose={onClose} title="Buscar proyectos" width={560}>
      <input autoFocus className="input h-12" placeholder="Nombre, cliente…" value={q}
        onChange={e => { setQ(e.target.value); setI(0); }}
        onKeyDown={e => {
          if (e.key === "ArrowDown") setI(Math.min(i + 1, res.length - 1));
          if (e.key === "ArrowUp") setI(Math.max(i - 1, 0));
          if (e.key === "Enter") pick(res[i]);
        }} />
      <div className="mt-3 space-y-1">
        {res.map((p, k) => (
          <button key={p.id} onMouseEnter={() => setI(k)} onClick={() => pick(p)}
            className={cx("w-full flex items-center gap-3 p-3 rounded-[16px] text-left", k === i ? "bg-surface-muted" : "")}>
            <span className="font-mono text-[13px] text-ink-muted w-16">{p.version_actual ?? "—"}</span>
            <span className="flex-1 truncate font-medium">{p.titulo}</span>
            <Badge>{p.cliente}</Badge>
          </button>
        ))}
        {res.length === 0 && <div className="label p-3">No encontré nada con “{q}”.</div>}
      </div>
    </Modal>
  );
}
