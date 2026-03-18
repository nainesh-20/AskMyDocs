"use client";

import { useEffect, useState, useCallback } from "react";
import {
  getDocuments,
  getDocumentStatus,
  uploadDocument,
  type Document,
} from "@/lib/api";
import UploadZone from "@/components/UploadZone";
import DocumentTable from "@/components/DocumentTable";

const FREE_TIER_LIMIT = 3;

export default function DashboardPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [maxDocs, setMaxDocs] = useState(FREE_TIER_LIMIT);
  const [remaining, setRemaining] = useState(FREE_TIER_LIMIT);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDocuments = useCallback(async () => {
    try {
      const data = await getDocuments();
      setDocuments(data.documents);
      setMaxDocs(data.max_documents);
      setRemaining(data.remaining);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  useEffect(() => {
    const pendingDocs = documents.filter(
      (d) => d.status === "pending" || d.status === "processing"
    );
    if (pendingDocs.length === 0) return;

    const interval = setInterval(async () => {
      for (const doc of pendingDocs) {
        try {
          const updated = await getDocumentStatus(doc.id);
          if (updated.status !== doc.status) {
            setDocuments((prev) =>
              prev.map((d) =>
                d.id === doc.id
                  ? { ...d, status: updated.status, chunk_count: updated.chunk_count }
                  : d
              )
            );
          }
        } catch {
          // Silently ignore polling errors
        }
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [documents]);

  const handleUpload = async (file: File) => {
    const result = await uploadDocument(file);
    setDocuments((prev) => [
      {
        id: result.id,
        filename: result.filename,
        status: result.status as Document["status"],
        chunk_count: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      ...prev,
    ]);
    setRemaining((r) => Math.max(0, r - 1));
  };

  const limitReached = remaining <= 0;

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:py-8">
      {/* Usage bar */}
      <div className="mb-6 rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium text-zinc-300">
              {documents.length} / {maxDocs} documents used
            </p>
            <p className="mt-0.5 text-xs text-zinc-500">
              {limitReached
                ? "Free tier limit reached"
                : `${remaining} upload${remaining === 1 ? "" : "s"} remaining`}
            </p>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-800 sm:max-w-48">
            <div
              className={`h-full rounded-full transition-all ${
                limitReached ? "bg-red-500" : "bg-emerald-500"
              }`}
              style={{ width: `${Math.min(100, (documents.length / maxDocs) * 100)}%` }}
            />
          </div>
        </div>
      </div>

      {/* Upload or limit message */}
      <div className="mb-8">
        {limitReached ? (
          <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-zinc-700 bg-zinc-900/30 px-6 py-10 text-center">
            <div className="mb-3 text-4xl">🔒</div>
            <h3 className="text-base font-semibold text-zinc-200">
              Free tier limit reached
            </h3>
            <p className="mt-2 max-w-md text-sm text-zinc-500">
              You&apos;ve used all {maxDocs} document uploads on the free plan.
              Check back later when we scale up the infrastructure — more capacity is on the way!
            </p>
          </div>
        ) : (
          <UploadZone onUpload={handleUpload} />
        )}
      </div>

      <div>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-zinc-500">
          Your Documents
        </h2>
        {loading ? (
          <div className="flex items-center justify-center py-12 text-zinc-500">
            <span className="mr-2 inline-block h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent" />
            Loading documents...
          </div>
        ) : error ? (
          <div className="rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        ) : (
          <DocumentTable documents={documents} />
        )}
      </div>
    </div>
  );
}
