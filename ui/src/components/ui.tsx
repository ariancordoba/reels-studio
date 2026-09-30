import { useEffect, useRef, useState, type ReactNode } from "react";
import { FileVideo, UploadCloud, X } from "lucide-react";

export const ICON = { size: 20, strokeWidth: 1.75 } as const;

export function cx(...c: (string | false | null | undefined)[]) { return c.filter(Boolean).join(" "); }

export function Badge({ tone = "muted", children, dot }: { tone?: "muted" | "lime" | "danger" | "warn" | "ink" | "ok"; children: ReactNode; dot?: boolean }) {
  const tones = {
    muted: "bg-surface-muted text-ink", lime: "bg-lime text-lime-ink", danger: "bg-danger text-white",
    warn: "bg-warn-soft text-warn-ink", ink: "bg-ink text-white", ok: "bg-[#e3f4e9] text-ok",
  };
  return (
    <span className={cx("inline-flex items-center gap-1.5 h-7 px-3 rounded-full text-[13px] font-medium whitespace-nowrap", tones[tone])}>
      {dot && <span className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function Segmented<T extends string>({ value, options, onChange, size = "md" }: {
  value: T; options: { id: T; label: ReactNode }[]; onChange: (v: T) => void; size?: "sm" | "md";
}) {
  return (
    <div className="inline-flex p-1 rounded-full bg-surface-muted">
      {options.map(o => (
        <button key={o.id} onClick={() => onChange(o.id)}
          className={cx("rounded-full font-medium transition-colors duration-150",
            size === "sm" ? "h-8 px-3.5 text-[13px]" : "h-9 px-4 text-sm",
            value === o.id ? "bg-ink text-white" : "text-ink-muted hover:text-ink")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Progress({ value, className, tone = "ink" }: { value: number; className?: string; tone?: "ink" | "lime" }) {
  return (
    <div className={cx("h-2 rounded-full bg-surface-muted overflow-hidden", className)}>
      <div className={cx("h-full rounded-full transition-[width] duration-500 ease-out", tone === "ink" ? "bg-ink" : "bg-lime")}
        style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }} />
    </div>
  );
}

/** Gauge radial de ticks (como "Package compliance"). */
export function TickGauge({ value, label, big }: { value: number | null; label: string; big: string }) {
  const n = 44, a0 = -200, a1 = 20;
  const filled = value == null ? 0 : Math.round(n * Math.max(0, Math.min(1, value)));
  return (
    <div className="relative w-[220px] h-[128px] mx-auto">
      <svg viewBox="0 0 220 128" className="absolute inset-0">
        {Array.from({ length: n }, (_, i) => {
          const a = ((a0 + (a1 - a0) * (i / (n - 1))) * Math.PI) / 180;
          const r0 = 78, r1 = i % 4 === 0 ? 102 : 96;
          return <line key={i} x1={110 + r0 * Math.cos(a)} y1={112 + r0 * Math.sin(a)} x2={110 + r1 * Math.cos(a)} y2={112 + r1 * Math.sin(a)}
            stroke={i < filled ? "#111" : "rgba(17,17,17,.18)"} strokeWidth={2.4} strokeLinecap="round" />;
        })}
      </svg>
      <div className="absolute inset-x-0 bottom-1 text-center">
        <div className="text-[40px] font-semibold tracking-[-0.03em] leading-none">{big}</div>
        <div className="text-[13px] text-lime-ink/70 mt-1">{label}</div>
      </div>
    </div>
  );
}

export function Dropzone({ label, hint, files, onFiles, accept = "video/*", multiple = true, icon }: {
  label: string; hint: string; files: File[]; onFiles: (f: File[]) => void; accept?: string; multiple?: boolean; icon?: ReactNode;
}) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const add = (list: FileList | null) => {
    if (!list) return;
    const okVideo = accept.includes("video"), okImage = accept.includes("image");
    const arr = Array.from(list).filter(f => accept === "*"
      || (okVideo && (f.type.startsWith("video") || /\.(mov|mp4|m4v|mkv|webm|avi)$/i.test(f.name)))
      || (okImage && (f.type.startsWith("image") || /\.(jpe?g|png|webp)$/i.test(f.name))));
    onFiles(multiple ? [...files, ...arr] : arr.slice(0, 1));
  };
  return (
    <div>
      <div onClick={() => input.current?.click()}
        onDragOver={e => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={e => { e.preventDefault(); setOver(false); add(e.dataTransfer.files); }}
        className={cx("cursor-pointer rounded-[20px] border-2 border-dashed px-6 py-7 text-center transition-colors duration-150",
          over ? "border-ink bg-lime/30" : "border-line bg-surface-muted/60 hover:bg-surface-muted")}>
        <div className="mx-auto mb-2 size-11 rounded-full bg-surface grid place-items-center">{icon ?? <UploadCloud {...ICON} />}</div>
        <div className="font-medium">{label}</div>
        <div className="label mt-0.5">{hint}</div>
        <input ref={input} type="file" accept={accept} multiple={multiple} className="hidden" onChange={e => { add(e.target.files); e.target.value = ""; }} />
      </div>
      {files.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {files.map((f, i) => (
            <li key={i} className="flex items-center gap-2 h-10 px-3 rounded-[14px] bg-surface-muted text-sm">
              <FileVideo size={16} strokeWidth={1.75} className="text-ink-muted" />
              <span className="truncate flex-1">{f.name}</span>
              <span className="font-mono text-[12px] text-ink-muted">{(f.size / 1e6).toFixed(0)} MB</span>
              <button className="text-ink-muted hover:text-ink" onClick={() => onFiles(files.filter((_, j) => j !== i))}><X size={16} /></button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Modal({ open, onClose, title, children, width = 560 }: { open: boolean; onClose?: () => void; title: ReactNode; children: ReactNode; width?: number }) {
  useEffect(() => {
    if (!open || !onClose) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-ink/30 p-6" onMouseDown={e => e.target === e.currentTarget && onClose?.()}>
      <div className="card p-7 w-full max-h-[90vh] overflow-auto" style={{ maxWidth: width }}>
        <div className="flex items-center justify-between mb-5">
          <div className="h-card">{title}</div>
          {onClose && <button className="icon-btn bg-surface-muted size-9" onClick={onClose}><X size={18} /></button>}
        </div>
        {children}
      </div>
    </div>
  );
}

export function Empty({ icon, title, text, action }: { icon: ReactNode; title: string; text: string; action?: ReactNode }) {
  return (
    <div className="text-center py-14 px-6">
      <div className="mx-auto size-16 rounded-[22px] bg-surface-muted grid place-items-center mb-4">{icon}</div>
      <div className="text-lg font-semibold">{title}</div>
      <div className="label mt-1 max-w-sm mx-auto">{text}</div>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export interface ToastItem { id: number; msg: string; kind: "ok" | "error" }
export function Toasts({ items, dismiss }: { items: ToastItem[]; dismiss: (id: number) => void }) {
  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 items-end">
      {items.map(t => (
        <div key={t.id} onClick={() => dismiss(t.id)}
          className="cursor-pointer flex items-center gap-3 max-w-[420px] rounded-[18px] bg-ink text-white px-5 py-3.5 text-sm shadow-lg">
          <span className={cx("size-2 rounded-full shrink-0", t.kind === "ok" ? "bg-lime" : "bg-danger")} />
          <span>{t.msg}</span>
        </div>
      ))}
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <div className="label mb-1.5">{label}</div>
      {children}
      {hint && <div className="text-[12px] text-ink-muted mt-1">{hint}</div>}
    </label>
  );
}

export function Toggle({ on, onChange, dark }: { on: boolean; onChange?: (v: boolean) => void; dark?: boolean }) {
  return (
    <button onClick={() => onChange?.(!on)}
      className={cx("relative w-12 h-7 rounded-full transition-colors duration-150", on ? (dark ? "bg-ink" : "bg-lime") : "bg-black/15")}>
      <span className={cx("absolute top-1 size-5 rounded-full bg-white transition-all duration-150", on ? "left-6" : "left-1")} />
    </button>
  );
}
