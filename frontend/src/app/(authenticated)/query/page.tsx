"use client";

import { useState } from "react";
import { queryDocuments, type QueryResponse } from "@/lib/api";
import QueryInput from "@/components/QueryInput";
import AnswerCard from "@/components/AnswerCard";

export default function QueryPage() {
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleQuery = async (question: string) => {
    setError(null);
    setResponse(null);
    setLoading(true);

    try {
      const result = await queryDocuments(question);
      setResponse(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Query failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:py-8">
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-white sm:text-xl">
          Ask your documents anything
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          Your question will be matched against all your uploaded documents.
        </p>
      </div>

      <div className="mb-6">
        <QueryInput onSubmit={handleQuery} loading={loading} />
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 py-16 text-zinc-500">
          <span className="mr-2 inline-block h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent" />
          Searching documents and generating answer...
        </div>
      )}

      {response && !loading && <AnswerCard response={response} />}
    </div>
  );
}
