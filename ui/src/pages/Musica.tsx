import { useEffect, useState } from "react";
import { Music, Upload, Waves } from "lucide-react";
import { api, useStore } from "../api";
import { Empty, Field, Modal } from "../components/ui";

interface Pista { archivo: string; titulo: string; licencia: string; subida: string; tamano_mb: number }

export default function MusicaPage() {
  const { toast } = useStore();
  const [list, setList] = useState<Pista[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [titulo, setTitulo] = useState("");
  const [lic, setLic] = useState("");
  const load = () => api<Pista[]>("/musica").then(setList).catch(e => toast(e.message, "error"));
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const upload = () => {
    if (!file) return;
    const fd = new FormData(); fd.append("archivo", file); fd.append("titulo", titulo || file.name); fd.append("licencia", lic);
    api("/musica", { method: "POST", body: fd }).then(() => { setFile(null); setTitulo(""); setLic(""); load(); toast("Pista guardada"); })
      .catch(e => toast(e.message, "error"));
  };
  return (
    <div className="grid grid-cols-12 gap-6">
      <div className="col-span-12 xl:col-span-8 card p-7">
        <div className="flex items-center justify-between mb-5">
          <div><div className="h-card">Música</div><div className="label">Pistas con licencia que Claude puede usar en vez de la música sintetizada.</div></div>
          <label className="btn-primary cursor-pointer"><Upload size={18} strokeWidth={1.75} /> Subir pista
            <input type="file" accept="audio/*" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) { setFile(f); setTitulo(f.name.replace(/\.[^.]+$/, "")); } e.target.value = ""; }} /></label>
        </div>
        {list?.length === 0 && <Empty icon={<Music size={26} strokeWidth={1.5} />} title="Sin pistas propias" text="Por defecto cada video lleva música sintetizada (sin problemas de licencia). Si tenés pistas con licencia para uso comercial, subilas acá." />}
        <div className="space-y-2">
          {list?.map(p => (
            <div key={p.archivo} className="flex items-center gap-4 p-4 rounded-[20px] bg-surface-muted/70">
              <div className="size-11 rounded-full bg-surface grid place-items-center"><Music size={18} strokeWidth={1.75} /></div>
              <div className="flex-1 min-w-0"><div className="font-medium truncate">{p.titulo}</div><div className="label truncate">Licencia: {p.licencia}</div></div>
              <audio src={`/api/musica/${encodeURIComponent(p.archivo)}`} controls className="h-9" />
            </div>
          ))}
        </div>
      </div>
      <div className="col-span-12 xl:col-span-4 rounded-[28px] bg-lime p-7 text-lime-ink">
        <Waves size={28} strokeWidth={1.5} />
        <div className="text-[22px] font-semibold mt-4 leading-tight">Música sintetizada por defecto</div>
        <p className="mt-3 text-lime-ink/80 leading-relaxed">Cada video trae una pista propia hecha por el motor: tempo, tonalidad, redoble y drop se ajustan a los cortes. No hay licencias de terceros.</p>
        <p className="mt-3 text-lime-ink/80 leading-relaxed">Para usar una pista tuya, subila acá con su licencia y pedile a Claude: “usá la pista X”.</p>
      </div>
      <Modal open={!!file} onClose={() => setFile(null)} title="Nueva pista">
        <div className="space-y-4">
          <Field label="Nombre"><input className="input" value={titulo} onChange={e => setTitulo(e.target.value)} /></Field>
          <Field label="Licencia / origen" hint="Obligatorio: de dónde sale y si se puede usar para trabajo comercial."><input className="input" value={lic} onChange={e => setLic(e.target.value)} placeholder="Ej: Artlist, licencia comercial, cuenta de la agencia" /></Field>
          <button className="btn-primary w-full" disabled={lic.trim().length < 3} onClick={upload}>Guardar</button>
        </div>
      </Modal>
    </div>
  );
}
