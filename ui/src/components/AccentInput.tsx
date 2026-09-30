// Campo de texto con acento por palabra: se escribe normal y se toca cada palabra para resaltarla
// (por dentro se guarda con *asteriscos*, que es lo que entiende el motor).
import { parseWords, buildText } from "../pages/Guion";
import { cx } from "./ui";

export default function AccentInput({ value, onChange, placeholder, upper, noAccent }: {
  value: string; onChange: (v: string) => void; placeholder?: string; upper?: boolean; noAccent?: boolean;
}) {
  const words = parseWords(value);
  const plain = words.map(w => w.w).join(" ") + (value.endsWith(" ") ? " " : "");
  const setPlain = (t: string) => {
    const prev = new Map(parseWords(value).map(w => [w.w, w.acc]));
    const ws = t.split(" ").filter(Boolean).map(w => ({ w, acc: prev.get(w) ?? false }));
    onChange(buildText(ws) + (t.endsWith(" ") && ws.length ? " " : ""));
  };
  return (
    <div>
      <input className={cx("input", upper && "uppercase font-semibold tracking-wide")} value={plain} placeholder={placeholder}
        onChange={e => setPlain(e.target.value)} onBlur={() => onChange(value.trim())} />
      {!noAccent && words.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2 items-center">
          <span className="text-[12px] text-ink-muted mr-1">Tocá para resaltar:</span>
          {words.map((w, i) => (
            <button key={i} type="button" onClick={() => { const ws = parseWords(value); ws[i].acc = !ws[i].acc; onChange(buildText(ws)); }}
              className={cx("h-7 px-2.5 rounded-full text-[13px] font-medium transition-colors", w.acc ? "bg-lime text-lime-ink" : "bg-surface-muted hover:bg-line")}>
              {upper ? w.w.toUpperCase() : w.w}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
