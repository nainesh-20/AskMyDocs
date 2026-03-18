import type { QueryResponse } from "@/lib/api";
import SourceList from "./SourceList";

const modeConfig = {
  answer: {
    border: "border-l-emerald-500",
    badge: "bg-emerald-500/10 text-emerald-400",
    icon: "●",
    label: "High Confidence",
  },
  low_confidence: {
    border: "border-l-yellow-500",
    badge: "bg-yellow-500/10 text-yellow-400",
    icon: "⚠",
    label: "Low Confidence",
  },
  no_match: {
    border: "border-l-red-500",
    badge: "bg-red-500/10 text-red-400",
    icon: "✗",
    label: "No Match Found",
  },
};

export default function AnswerCard({ response }: { response: QueryResponse }) {
  const cfg = modeConfig[response.mode];

  return (
    <div
      className={`rounded-xl border border-zinc-800 border-l-4 bg-zinc-950 p-5 sm:p-6 ${cfg.border}`}
    >
      <div className="mb-4 flex items-center gap-2">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${cfg.badge}`}
        >
          <span>{cfg.icon}</span>
          {cfg.label}
        </span>
      </div>

      {response.warning && (
        <div className="mb-4 rounded-lg border border-yellow-500/20 bg-yellow-500/5 px-3 py-2 text-xs text-yellow-400 sm:text-sm">
          {response.warning}
        </div>
      )}

      <div className="min-h-[120px] whitespace-pre-wrap text-sm leading-relaxed text-zinc-300 sm:text-base sm:leading-7">
        {response.answer}
      </div>

      <SourceList sources={response.sources} />
    </div>
  );
}
