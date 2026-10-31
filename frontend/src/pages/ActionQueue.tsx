import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Check, FileCheck2, Link2, Pencil, ShieldAlert, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import { Modal } from "../components/Shell";
import { Badge, EmptyState, IdChip, Panel, Q, Segmented, TierChip } from "../components/ui";
import { post, useActions, useAudit, useDistricts, useSystem } from "../lib/api";
import { titleCase } from "../lib/format";
import type { PendingAction } from "../lib/types";
import { color, motion as mo } from "../theme";

type Filter = "pending" | "executed" | "rejected" | "all";
const ACTOR = "duty_officer";

export default function ActionQueue() {
  const actions = useActions();
  const [filter, setFilter] = useState<Filter>("pending");
  const sys = useSystem();
  const killed = sys.data?.kill_switch ?? false;
  const counts = (s: Filter) => (actions.data ?? []).filter((a) => s === "all" || a.status === s).length;

  return (
    <div className="grid grid-cols-1 gap-3 2xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
      <Panel
        title="Action queue"
        subtitle="Agent proposals wait here. Nothing executes until an officer approves it."
        right={<Segmented value={filter} onChange={setFilter} options={(["pending", "executed", "rejected", "all"] as Filter[]).map((f) => ({ value: f, label: <span>{titleCase(f)} <span className="num opacity-70">{counts(f)}</span></span> }))} />}
        bodyClass="p-3"
      >
        {killed && (
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-e3/40 bg-e3/10 p-2.5 text-xs text-e3">
            <ShieldAlert size={14} /> Kill switch engaged: approvals are blocked until it is released.
          </div>
        )}
        <Q q={actions} rows={6}>
          {(list) => {
            const rows = list.filter((a) => filter === "all" || a.status === filter).sort((a, b) => b.created_at.localeCompare(a.created_at));
            if (!rows.length)
              return <EmptyState icon={<FileCheck2 size={18} />} title={filter === "pending" ? "Queue is clear" : `No ${filter} actions`} body={filter === "pending" ? "Run an investigation: recommended actions land here for approval." : undefined} />;
            return (
              <ul className="flex flex-col gap-2">
                <AnimatePresence initial={false}>
                  {rows.map((a, i) => (
                    <ActionCard key={a.ref} a={a} i={i} killed={killed} />
                  ))}
                </AnimatePresence>
              </ul>
            );
          }}
        </Q>
      </Panel>
      <AuditPanel />
    </div>
  );
}

function ActionCard({ a, i, killed }: { a: PendingAction; i: number; killed: boolean }) {
  const qc = useQueryClient();
  const districts = useDistricts();
  const name = districts.data?.find((d) => d.code === a.district)?.name ?? a.district;
  const [mode, setMode] = useState<"reject" | "edit" | null>(null);
  const done = () => {
    qc.invalidateQueries({ queryKey: ["actions"] });
    qc.invalidateQueries({ queryKey: ["audit"] });
  };
  const approve = useMutation({ mutationFn: () => post<PendingAction>(`/api/actions/${a.ref}/approve`, { actor: ACTOR }), onSuccess: done });
  const statusColor = a.status === "executed" ? color.good : a.status === "rejected" ? color.critical : color.warning;

  return (
    <motion.li layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: 30 }} transition={{ delay: Math.min(i, 6) * mo.stagger * 0.5 }} className="rounded-xl border border-line/30 bg-white/50 p-3.5">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="num text-[11px] text-ink-3">{a.ref}</span>
            <h3 className="text-[14px] font-semibold text-ink">{a.title}</h3>
            <Badge color={statusColor}>{a.status.toUpperCase()}</Badge>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11.5px] text-ink-3">
            <span className="text-ink-2">{name}</span>· signal <TierChip tier={a.signal_tier} size="sm" /> · requires <span className="num">{a.min_tier}</span> · proposed by {a.proposed_by}
          </div>
          <p className="mt-2 text-[12.5px] leading-relaxed text-ink-2">{a.rationale}</p>
          {Object.keys(a.params).length > 0 && (
            <div className="num mt-1.5 flex flex-wrap gap-1.5 text-[11px]">
              {Object.entries(a.params).map(([k, v]) => (
                <span key={k} className="rounded border border-line/30 px-1.5 py-0.5 text-ink-2">
                  {k}: <span className="text-ink">{String(v)}</span>
                </span>
              ))}
            </div>
          )}
          <div className="mt-2 flex flex-wrap gap-1">
            {a.evidence_ids.map((id) => (
              <IdChip key={id} id={id} />
            ))}
          </div>
        </div>
        {a.status === "pending" && (
          <div className="flex shrink-0 flex-col gap-1.5">
            <button disabled={killed || approve.isPending} onClick={() => approve.mutate()} className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-good px-3 py-1.5 text-xs font-semibold text-ink hover:brightness-110 disabled:opacity-40">
              <Check size={13} /> Approve
            </button>
            <button onClick={() => setMode("edit")} className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-line/50 px-3 py-1.5 text-xs text-ink-2 hover:border-accent/50 hover:text-accent-ink">
              <Pencil size={12} /> Edit
            </button>
            <button onClick={() => setMode("reject")} className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-e3/40 px-3 py-1.5 text-xs text-e3 hover:bg-e3/10">
              <X size={13} /> Reject
            </button>
          </div>
        )}
      </div>
      {approve.error && <div className="mt-2 text-xs text-e3">{(approve.error as Error).message}</div>}
      {a.receipt && <Receipt a={a} />}
      {a.status === "rejected" && a.decision_reason && (
        <div className="mt-2.5 rounded-lg border border-e3/25 bg-e3/[0.05] p-2.5 text-[12px] text-ink-2">
          <span className="label-caps text-e3">Rejected by {a.decided_by}</span>
          <div className="mt-0.5">“{a.decision_reason}”</div>
        </div>
      )}
      <RejectDialog a={a} open={mode === "reject"} onClose={() => setMode(null)} onDone={done} />
      <EditDialog a={a} open={mode === "edit"} onClose={() => setMode(null)} onDone={done} />
    </motion.li>
  );
}

function Receipt({ a }: { a: PendingAction }) {
  const r = a.receipt!;
  return (
    <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} className="mt-3 rounded-lg border border-good/30 bg-good/[0.06] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-good">
          <FileCheck2 size={14} /> Execution receipt
        </span>
        <span className="num rounded-md border border-good/40 px-2 py-0.5 text-sm font-semibold text-good">{String(r.ticket)}</span>
      </div>
      <div className="num mt-2 grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] text-ink-3 md:grid-cols-4">
        <span>system: <span className="text-ink-2">{String(r.system)}</span></span>
        <span>as: <span className="text-ink-2">{String(r.executes_as)}</span></span>
        <span>by: <span className="text-ink-2">{a.decided_by}</span></span>
        <span>at: <span className="text-ink-2">{String(r.executed_at).replace("T", " ").slice(0, 19)}</span></span>
      </div>
      {typeof r.summary === "string" && <p className="mt-1.5 text-[12px] text-ink-2">{r.summary}</p>}
      {r.simulated === true && <p className="mt-1 text-[10.5px] text-ink-3">Simulated integration: no external system was contacted.</p>}
    </motion.div>
  );
}

function RejectDialog({ a, open, onClose, onDone }: { a: PendingAction; open: boolean; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const m = useMutation({
    mutationFn: () => post(`/api/actions/${a.ref}/reject`, { actor: ACTOR, reason }),
    onSuccess: () => {
      onDone();
      onClose();
    },
  });
  return (
    <Modal open={open} onClose={onClose} title={`Reject: ${a.title}`}>
      <p className="text-sm text-ink-2">A reason is required and is written to the audit log.</p>
      <textarea autoFocus value={reason} onChange={(e) => setReason(e.target.value)} rows={3} placeholder="e.g. Lab confirmation pending; revisit in 48h" className="mt-3 w-full rounded-lg border border-line/30 bg-white/85 px-3 py-2 text-sm text-ink outline-none focus:border-accent/60" />
      {m.error && <div className="mt-2 text-xs text-e3">{(m.error as Error).message}</div>}
      <div className="mt-4 flex justify-end gap-2">
        <button onClick={onClose} className="rounded-lg px-3 py-2 text-sm text-ink-3 hover:text-ink">
          Cancel
        </button>
        <button disabled={reason.trim().length < 3 || m.isPending} onClick={() => m.mutate()} className="rounded-lg bg-e3 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">
          Reject action
        </button>
      </div>
    </Modal>
  );
}

function EditDialog({ a, open, onClose, onDone }: { a: PendingAction; open: boolean; onClose: () => void; onDone: () => void }) {
  const [rationale, setRationale] = useState(a.rationale);
  const [params, setParams] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(a.params).map(([k, v]) => [k, String(v)])));
  const m = useMutation({
    mutationFn: () =>
      post(`/api/actions/${a.ref}/edit`, {
        actor: ACTOR,
        rationale,
        params: Object.fromEntries(Object.entries(params).map(([k, v]) => [k, v !== "" && !Number.isNaN(Number(v)) ? Number(v) : v])),
      }),
    onSuccess: () => {
      onDone();
      onClose();
    },
  });
  return (
    <Modal open={open} onClose={onClose} title={`Edit: ${a.title}`} width={520}>
      <label className="label-caps">Rationale</label>
      <textarea value={rationale} onChange={(e) => setRationale(e.target.value)} rows={3} className="mt-1.5 w-full rounded-lg border border-line/30 bg-white/85 px-3 py-2 text-sm text-ink outline-none focus:border-accent/60" />
      {Object.keys(params).length > 0 && (
        <>
          <label className="label-caps mt-3 block">Parameters</label>
          <div className="mt-1.5 grid grid-cols-2 gap-2">
            {Object.entries(params).map(([k, v]) => (
              <label key={k} className="text-[11px] text-ink-3">
                {k}
                <input value={v} onChange={(e) => setParams({ ...params, [k]: e.target.value })} className="num mt-1 w-full rounded-lg border border-line/30 bg-white/85 px-2.5 py-1.5 text-sm text-ink outline-none focus:border-accent/60" />
              </label>
            ))}
          </div>
        </>
      )}
      <p className="mt-3 text-[11px] text-ink-3">Edits keep the action pending. Approval is a separate, audited step.</p>
      {m.error && <div className="mt-2 text-xs text-e3">{(m.error as Error).message}</div>}
      <div className="mt-4 flex justify-end gap-2">
        <button onClick={onClose} className="rounded-lg px-3 py-2 text-sm text-ink-3 hover:text-ink">
          Cancel
        </button>
        <button disabled={m.isPending} onClick={() => m.mutate()} className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-ink disabled:opacity-40">
          Save edit
        </button>
      </div>
    </Modal>
  );
}

const EVENT_COLOR: Record<string, string> = { proposed: color.accentInk, approved: color.good, executed: color.good, rejected: color.critical, edited: color.warning, kill_switch: color.critical, demo_reset: color.textSecondary };

function AuditPanel() {
  const audit = useAudit();
  return (
    <Panel
      title="Audit log"
      subtitle="Append-only, hash-chained. Every proposal, decision and kill-switch change."
      right={
        audit.data &&
        (audit.data.verified ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-good/40 px-2 py-0.5 text-[11px] text-good">
            <ShieldCheck size={12} /> Chain verified
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full border border-e3/40 px-2 py-0.5 text-[11px] text-e3">
            <ShieldAlert size={12} /> Chain broken
          </span>
        ))
      }
      bodyClass="p-0"
    >
      <Q q={audit} rows={8}>
        {(d) =>
          d.entries.length === 0 ? (
            <EmptyState title="No audit entries yet" />
          ) : (
            <div className="max-h-[70vh] overflow-auto">
              <table className="w-full text-left text-[11.5px]">
                <thead className="sticky top-0 bg-[#FFF8F4]">
                  <tr className="label-caps">
                    <th className="px-3 py-2 font-semibold">#</th>
                    <th className="px-2 py-2 font-semibold">Time (UTC)</th>
                    <th className="px-2 py-2 font-semibold">Event</th>
                    <th className="px-2 py-2 font-semibold">Subject</th>
                    <th className="px-2 py-2 font-semibold">Actor</th>
                    <th className="px-3 py-2 font-semibold">Hash</th>
                  </tr>
                </thead>
                <tbody>
                  {[...d.entries].reverse().map((e) => (
                    <tr key={e.seq} className="border-t border-line/20 hover:bg-white/50">
                      <td className="num px-3 py-1.5 text-ink-3">{e.seq}</td>
                      <td className="num whitespace-nowrap px-2 py-1.5 text-ink-3">{e.ts.slice(11, 19)}</td>
                      <td className="px-2 py-1.5">
                        <span className="num text-[10.5px] font-semibold uppercase" style={{ color: EVENT_COLOR[e.event.toLowerCase().replace(/^action_/, "")] ?? color.textSecondary }}>
                          {e.event}
                        </span>
                      </td>
                      <td className="num px-2 py-1.5 text-ink-2">{e.subject}</td>
                      <td className="px-2 py-1.5 text-ink-2">{e.actor}</td>
                      <td className="num px-3 py-1.5 text-ink-3" title={`prev ${e.prev_hash}\nhash ${e.hash}`}>
                        <span className="inline-flex items-center gap-1">
                          <Link2 size={10} />
                          {e.hash.slice(0, 10)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </Q>
    </Panel>
  );
}
