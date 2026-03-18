import type { SourceChunk } from "@/lib/api";

export default function SourceList({ sources }: { sources: SourceChunk[] }) {
  if (sources.length === 0) return null;

  return (
    <div className="mt-5 space-y-2 border-t border-zinc-800 pt-4">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
        Sources
      </h4>
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        {sources.map((s, i) => (
          <div
            key={i}
            className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs sm:text-sm"
          >
            <span className="text-zinc-500">📄</span>
            <span className="min-w-0 truncate font-medium text-zinc-300">{s.filename}</span>
            <span className="text-zinc-600">·</span>
            <span className="shrink-0 text-zinc-400">p.{s.page}</span>
            <span className="text-zinc-600">·</span>
            <span className="shrink-0 tabular-nums text-zinc-500">
              {(s.score * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
