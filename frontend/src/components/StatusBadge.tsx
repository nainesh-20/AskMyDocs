import type { DocStatus } from "@/lib/api";

const config: Record<DocStatus, { label: string; color: string; icon: string }> = {
  pending: {
    label: "Queued",
    color: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
    icon: "⏳",
  },
  processing: {
    label: "Processing...",
    color: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
    icon: "⏳",
  },
  indexed: {
    label: "Ready",
    color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    icon: "✓",
  },
  failed: {
    label: "Failed",
    color: "bg-red-500/10 text-red-400 border-red-500/20",
    icon: "✗",
  },
};

export default function StatusBadge({ status }: { status: DocStatus }) {
  const { label, color, icon } = config[status] || config.pending;
  const showSpinner = status === "pending" || status === "processing";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${color}`}
    >
      {showSpinner ? (
        <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
      ) : (
        <span>{icon}</span>
      )}
      {label}
    </span>
  );
}
