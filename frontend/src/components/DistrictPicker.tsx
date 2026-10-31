import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { useAnalysis, useDistricts } from "../lib/api";
import { confLabel } from "../lib/format";
import { TierChip } from "./ui";

/** Accessible custom listbox for choosing the case-file district (replaces the native <select>). */
export function DistrictPicker({ value, onChange }: { value: string; onChange: (code: string) => void }) {
  const districts = useDistricts();
  const analysis = useAnalysis();
  const [open, setOpen] = useState(false);
  const list = districts.data ?? [];
  const [active, setActive] = useState(0);
  const btn = useRef<HTMLButtonElement>(null);
  const box = useRef<HTMLUListElement>(null);
  const id = useId();
  const cur = list.find((d) => d.code === value);
  const info = (code: string) => analysis.data?.assessments.find((a) => a.district === code);

  useEffect(() => {
    if (open) {
      setActive(Math.max(0, list.findIndex((d) => d.code === value)));
      box.current?.focus();
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const choose = (i: number) => {
    const d = list[i];
    if (d) onChange(d.code);
    setOpen(false);
    btn.current?.focus();
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") setActive((i) => Math.min(i + 1, list.length - 1));
    else if (e.key === "ArrowUp") setActive((i) => Math.max(i - 1, 0));
    else if (e.key === "Home") setActive(0);
    else if (e.key === "End") setActive(list.length - 1);
    else if (e.key === "Enter" || e.key === " ") choose(active);
    else if (e.key === "Escape" || e.key === "Tab") {
      setOpen(false);
      if (e.key === "Escape") btn.current?.focus();
      return;
    } else if (/^[a-z]$/i.test(e.key)) {
      // type-ahead: jump to the next city starting with that letter
      const k = e.key.toLowerCase();
      const n = list.length;
      for (let s = 1; s <= n; s++) {
        const j = (active + s) % n;
        if (list[j].name.toLowerCase().startsWith(k)) {
          setActive(j);
          break;
        }
      }
    } else return;
    e.preventDefault();
  };

  const a = cur ? info(cur.code) : undefined;
  return (
    <div className="relative">
      <button
        ref={btn}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            setOpen(true);
          }
        }}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={id}
        aria-label={`Case file district: ${cur?.name ?? value}`}
        className="flex min-w-[240px] items-center gap-3 rounded-2xl border border-line/40 bg-white/80 py-1.5 pl-3.5 pr-2.5 text-left outline-none transition-colors duration-150 hover:bg-white focus-visible:ring-2 focus-visible:ring-accent-strong"
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[19px] font-semibold leading-tight text-ink">{cur?.name ?? "…"}</span>
          <span className="num block text-[10.5px] text-ink-3">
            {value}
            {a ? ` · ${confLabel(a.confidence)}` : ""}
          </span>
        </span>
        {a && <TierChip tier={a.gate.tier} size="sm" />}
        <ChevronDown size={16} className={`shrink-0 text-ink-3 transition-transform duration-150 ${open ? "rotate-180" : ""}`} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.ul
            ref={box}
            id={id}
            role="listbox"
            tabIndex={-1}
            aria-activedescendant={list[active] ? `${id}-${list[active].code}` : undefined}
            onKeyDown={onKey}
            onBlur={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget as Node) && e.relatedTarget !== btn.current) setOpen(false);
            }}
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.16 }}
            className="glass absolute left-0 top-[calc(100%+6px)] z-40 w-[320px] p-1.5 outline-none"
            style={{ background: "rgba(255,253,251,0.96)" }}
          >
            {list.map((d, i) => {
              const x = info(d.code);
              const sel = d.code === value;
              return (
                <li
                  key={d.code}
                  id={`${id}-${d.code}`}
                  role="option"
                  aria-selected={sel}
                  onMouseEnter={() => setActive(i)}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    choose(i);
                  }}
                  className={`flex cursor-pointer items-center gap-2.5 rounded-xl px-3 py-2 transition-colors duration-100 ${i === active ? "bg-mint/60" : ""}`}
                >
                  <span className="grid w-4 place-items-center text-accent-ink">{sel && <Check size={14} />}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13.5px] font-medium text-ink">{d.name}</span>
                    <span className="num block text-[10.5px] text-ink-3">{x ? `confidence ${confLabel(x.confidence)}` : d.code}</span>
                  </span>
                  {x && <TierChip tier={x.gate.tier} size="sm" />}
                </li>
              );
            })}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}
