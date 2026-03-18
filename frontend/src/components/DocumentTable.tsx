import type { Document } from "@/lib/api";
import StatusBadge from "./StatusBadge";

function timeAgo(dateStr: string): string {
  const seconds = Math.floor(
    (Date.now() - new Date(dateStr).getTime()) / 1000
  );
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function DocumentTable({ documents }: { documents: Document[] }) {
  if (documents.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-950 px-6 py-12 text-center">
        <p className="text-sm text-zinc-500">
          No documents yet. Upload a PDF to get started.
        </p>
      </div>
    );
  }

  return (
    <>
      {/* Desktop table */}
      <div className="hidden overflow-hidden rounded-xl border border-zinc-800 sm:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-zinc-800 bg-zinc-950">
            <tr>
              <th className="px-4 py-3 font-medium text-zinc-400">Filename</th>
              <th className="px-4 py-3 font-medium text-zinc-400">Chunks</th>
              <th className="px-4 py-3 font-medium text-zinc-400">Status</th>
              <th className="px-4 py-3 text-right font-medium text-zinc-400">
                Uploaded
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/50">
            {documents.map((doc) => (
              <tr key={doc.id} className="bg-zinc-950/50 hover:bg-zinc-900/50">
                <td className="px-4 py-3 font-medium text-zinc-200">
                  {doc.filename}
                </td>
                <td className="px-4 py-3 tabular-nums text-zinc-400">
                  {doc.status === "indexed" ? doc.chunk_count : "—"}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={doc.status} />
                </td>
                <td className="px-4 py-3 text-right text-zinc-500">
                  {timeAgo(doc.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile card list */}
      <div className="space-y-3 sm:hidden">
        {documents.map((doc) => (
          <div
            key={doc.id}
            className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-4"
          >
            <div className="mb-2 flex items-start justify-between gap-2">
              <p className="min-w-0 truncate text-sm font-medium text-zinc-200">
                {doc.filename}
              </p>
              <StatusBadge status={doc.status} />
            </div>
            <div className="flex items-center gap-3 text-xs text-zinc-500">
              <span>{timeAgo(doc.created_at)}</span>
              {doc.status === "indexed" && (
                <span className="tabular-nums">{doc.chunk_count} chunks</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
