import { createClient } from "./supabase";

const API_URL = process.env.NEXT_PUBLIC_API_URL!;

// --- Types matching backend schemas exactly ---

export type DocStatus = "pending" | "processing" | "indexed" | "failed";

export type Document = {
  id: string;
  filename: string;
  status: DocStatus;
  chunk_count: number;
  created_at: string;
  updated_at: string;
};

export type DocumentStatus = {
  id: string;
  filename: string;
  status: DocStatus;
  chunk_count: number;
  error_message: string | null;
};

export type SourceChunk = {
  filename: string;
  page: number;
  score: number;
  text: string;
};

export type QueryResponse = {
  mode: "answer" | "low_confidence" | "no_match";
  answer: string;
  sources: SourceChunk[];
  warning: string | null;
};

export type DocumentListResponse = {
  documents: Document[];
  max_documents: number;
  remaining: number;
};

// --- Auth header helper ---

async function getAuthHeaders(): Promise<HeadersInit> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) throw new Error("Not authenticated");

  return {
    Authorization: `Bearer ${session.access_token}`,
  };
}

// --- API functions ---

export async function uploadDocument(file: File): Promise<Document> {
  const headers = await getAuthHeaders();
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_URL}/documents/upload`, {
    method: "POST",
    headers: { Authorization: (headers as Record<string, string>).Authorization },
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail || "Upload failed");
  }
  return res.json();
}

export async function getDocuments(): Promise<DocumentListResponse> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/documents`, { headers });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to fetch documents" }));
    throw new Error(err.detail || "Failed to fetch documents");
  }
  return res.json();
}

export async function getDocumentStatus(id: string): Promise<DocumentStatus> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/documents/${id}/status`, { headers });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to fetch status" }));
    throw new Error(err.detail || "Failed to fetch status");
  }
  return res.json();
}

export async function queryDocuments(question: string): Promise<QueryResponse> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/query`, {
    method: "POST",
    headers: {
      ...headers,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ question }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Query failed" }));
    throw new Error(err.detail || "Query failed");
  }
  return res.json();
}
