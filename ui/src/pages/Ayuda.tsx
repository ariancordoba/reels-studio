import { useState, type ReactNode } from "react";
import { ChevronDown, FileArchive, LifeBuoy, Sparkles, Zap } from "lucide-react";
import { api, useStore } from "../api";
import { cx } from "../components/ui";
import { go, openClaude } from "../App";
import { GettingStarted } from "./Inicio";

export default function Ayuda() {
  const { toast } = useStore();
  const [diag, setDiag] = useState(false);
  const makeDiag = () => {
    setDiag(true);
    api<{ path: string }>("/diagnostico", { method: "POST" })
      .then(r => toast(`Diagnóstico listo en el escritorio: ${r.path.split(/[\\/]/).pop()}`)).catch(e => toast(e.message, "error"))
      .finally(() => setDiag(false));
  };
  return (
    <div className="grid grid-cols-12 gap-6">
      <div className="col-span-12 xl:col-span-8 flex flex-col gap-6">
        <GettingStarted force />
        <div className="card p-7">
          <div className="h-card mb-1">Cómo funciona</div>
          <div className="label mb-5">El recorrido completo de un video, de los crudos al archivo final.</div>
          <ol className="space-y-4">
            {[
              ["Nuevo video", "Elegís el cliente, subís los crudos y decidís cómo armarlo: con una plantilla (al instante, sin Claude) o con Claude a partir de una referencia."],
              ["Vista previa", "En unos minutos ves cuadros de cada escena. No es el video todavía: es para revisar textos, colores y tomas rápido."],
              ["Cambios", "Pedís cambios con tus palabras (“el título más grande”, “otra toma al principio”). Cada cambio es una versión nueva: nunca se pierde la anterior."],
              ["Borrador", "Un video rápido en baja calidad para ver el ritmo y la música (menos de un minuto)."],
              ["Render final", "El video en 1080p. Después “Exportar” lo copia a Descargas con un nombre prolijo, listo para subir."],
            ].map(([t, d], i) => (
              <li key={i} className="flex gap-4">
                <span className="size-8 shrink-0 rounded-full bg-lime text-lime-ink font-semibold grid place-items-center">{i + 1}</span>
                <div><div className="font-semibold">{t}</div><div className="text-ink-muted leading-relaxed">{d}</div></div>
              </li>
            ))}
          </ol>
        </div>

        <div className="card p-7">
          <div className="h-card mb-4">Preguntas frecuentes</div>
          <Faq q="¿Qué es mejor: plantilla o Claude?">
            Si ya tenés un video que te gustó para ese cliente, usá <b>plantilla</b>: sale en segundos y no gasta tu plan de Claude.
            Para un estilo nuevo, subí una referencia y dejá que <b>Claude</b> lo arme. Cuando lo apruebes, guardalo como plantilla
            (botón en la tarjeta de versiones) y la próxima vez va directo.
          </Faq>
          <Faq q="¿Cómo gasto menos de mi plan de Claude?">
            <ul className="list-disc pl-5 space-y-1.5">
              <li>Usá los botones <b>“Al instante, sin Claude”</b> (acento más claro, se lee mejor, textos más grandes…) y la pestaña <b>Guion</b> para cambiar textos y tiempos a mano.</li>
              <li>Juntá varios cambios en un solo pedido: “el título más grande, la fecha en verde y sin emojis”.</li>
              <li>Con <b>plantillas</b> la primera versión no usa Claude.</li>
              <li>Claude anota lo que aprende de cada cliente (en Clientes → Lo que Claude aprendió), así los videos siguientes necesitan menos correcciones.</li>
              <li>En Ajustes → Uso de Claude, el modo <b>Ahorro</b> usa un modelo más liviano.</li>
            </ul>
          </Faq>
          <Faq q="Claude dice que no inició sesión">
            Tocá la tarjeta verde de Claude (abajo a la izquierda) → “Iniciar sesión con Claude”. Se abre el navegador, entrás con tu
            cuenta y aceptás. <button className="underline" onClick={openClaude}>Conectar ahora</button>
          </Faq>
          <Faq q="Se ve un borde raro o espejado en una toma">
            Es un encuadre que se sale del crudo. Pedile a Claude “en la toma del segundo X hay un borde, acercala un poco”.
          </Faq>
          <Faq q="El texto no se lee sobre el fondo">
            Tocá “Se lee mejor” (oscurece un poco el video) o pedí “bajá el texto a la zona más oscura”.
          </Faq>
          <Faq q="¿Puedo usar la compu y la laptop?">
            Sí: instalá en las dos y elegí la misma carpeta de OneDrive en Ajustes. Si una está renderizando un proyecto, la otra espera
            a que termine ese proyecto.
          </Faq>
          <Faq q="¿Puedo usar música propia?">
            Sí, si tenés licencia para uso comercial: subila en <button className="underline" onClick={() => go("musica")}>Música</button> con su
            licencia y pedile a Claude “usá la pista X”. Si no, cada video lleva música hecha por el programa, sin problemas de derechos.
          </Faq>
        </div>
      </div>

      <div className="col-span-12 xl:col-span-4 flex flex-col gap-6">
        <div className="rounded-[28px] bg-ink text-white p-6">
          <div className="flex items-center gap-2 mb-4"><Sparkles size={18} className="text-lime" /><span className="font-medium">Cómo pedir cambios</span></div>
          <div className="space-y-2.5 text-[15px]">
            <Ex bad="no me gusta" good="el título más grande y que entre más rápido" />
            <Ex bad="cambiá la toma" good="al principio usá la toma donde patean al arco" />
            <Ex bad="más lindo" good="el verde más clarito y sin los emojis" />
          </div>
          <div className="text-white/60 text-sm mt-4">Concreto = menos idas y vueltas = menos uso de tu plan.</div>
        </div>
        <div className="card p-6">
          <div className="flex items-center gap-2 mb-2"><Zap size={18} /><span className="font-semibold">Atajos</span></div>
          <ul className="text-sm space-y-2">
            <li className="flex justify-between"><span>Buscar proyectos</span><span className="chip font-mono">Ctrl K</span></li>
            <li className="flex justify-between"><span>Enviar pedido</span><span className="chip font-mono">Enter</span></li>
            <li className="flex justify-between"><span>Salto de línea en el pedido</span><span className="chip font-mono">Shift Enter</span></li>
          </ul>
        </div>
        <div className="card p-6">
          <div className="flex items-center gap-2 mb-2"><LifeBuoy size={18} /><span className="font-semibold">¿Algo no anda?</span></div>
          <div className="label mb-4">Generá un diagnóstico y mandáselo a quien te pasó el programa. No incluye tus videos ni datos de clientes.</div>
          <button className="btn-primary w-full" disabled={diag} onClick={makeDiag}><FileArchive size={18} /> Generar diagnóstico</button>
        </div>
      </div>
    </div>
  );
}

function Faq({ q, children }: { q: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-line last:border-0">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between py-4 text-left font-medium">
        {q}<ChevronDown size={18} className={cx("text-ink-muted transition-transform", open && "rotate-180")} />
      </button>
      {open && <div className="pb-4 text-ink-muted leading-relaxed">{children}</div>}
    </div>
  );
}

function Ex({ bad, good }: { bad: string; good: string }) {
  return (
    <div className="rounded-[14px] bg-white/10 p-3">
      <div className="text-white/50 line-through text-sm">“{bad}”</div>
      <div>“{good}”</div>
    </div>
  );
}
