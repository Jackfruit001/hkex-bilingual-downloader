// Types and calls for the backend API (docs/SPEC.md §7). Every error has a code and a message.

export interface Stock {
  stock_id: number;
  code: string;
  name_en: string;
  name_tc: string | null;
  active: boolean;
}

export interface DocumentInfo {
  path: string;
  title: string;
  file_type: string;
  size_label: string;
  source_url: string;
  filename: string | null;
  downloadable: boolean;
}

export interface Rival {
  lang: "en" | "tc";
  title: string;
  path: string;
  score: number;
}

export type Status = "matched" | "check" | "en_only" | "tc_only";

export interface Announcement {
  id: string;
  status: Status;
  release_at: string;
  category: string;
  en: DocumentInfo | null;
  tc: DocumentInfo | null;
  evidence: string[];
  notice_url: string | null;
  rivals: Rival[];
  format: string;
  bilingual: boolean;
  separate: boolean;
  pair_zip_name: string | null;
  pair_zip_downloadable: boolean;
}

export interface SearchResult {
  company: Stock;
  alternatives: Stock[];
  start: string;
  end: string;
  announcements: Announcement[];
  summary: Record<string, number>;
  warnings: string[];
  diagnostics: Diagnostics;
}

export interface LangStats {
  calls: number;
  rows_fetched: number;
  rows_skipped: number;
  splits: number;
  rows_with_c_suffix: number;
  rows_without_c_suffix: number;
}

export interface Diagnostics {
  english: LangStats;
  chinese: LangStats;
  outside_range: number;
  seconds: number;
  pairing: Record<string, number>;
  reference: "live" | "snapshot";
}

export interface SearchParams {
  stock_code: string;
  stock_id?: number;
  start: string;
  end: string;
  categories: string[];
  keyword?: string;
}

export interface Category {
  code: string;
  name_en: string;
  name_tc: string;
}

export interface ContentCheck {
  available: boolean;
  conclusive?: boolean;
  best_path?: string;
  message: string;
}

export interface JobItem {
  path: string;
  filename: string;
  state: "queued" | "fetching" | "done" | "failed";
  bytes: number;
  error: ApiErrorBody | null;
}

export interface Job {
  job_id: string;
  state: "running" | "done" | "failed";
  items: JobItem[];
  error: ApiErrorBody | null;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: { choices?: Stock[] } & Record<string, unknown>;
}

export class ApiError extends Error {
  constructor(public body: ApiErrorBody) {
    super(body.message);
  }
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new ApiError({
      code: "NETWORK",
      message: "The app couldn't be reached. Check your connection and try again.",
    });
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body as Partial<ApiErrorBody> | null;
    throw new ApiError({
      code: error?.code ?? "UNKNOWN",
      message: error?.message ?? "Something went wrong. Try again in a minute.",
      details: error?.details,
    });
  }
  return body as T;
}

const post = (data: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

export const api = {
  stocks: (q: string) => call<Stock[]>(`/api/stocks?q=${encodeURIComponent(q)}`),
  categories: () => call<Category[]>("/api/categories"),
  search: (params: SearchParams) => call<SearchResult>("/api/search", post(params)),
  contentCheck: (enPath: string, tcPaths: string[]) =>
    call<ContentCheck>("/api/content-check", post({ en_path: enPath, tc_paths: tcPaths })),
  startDownload: (mode: "single" | "pair_zip" | "bulk_zip", items: { path: string; filename: string }[], zipName = "") =>
    call<Job>("/api/downloads", post({ mode, items, zip_name: zipName })),
  job: (id: string) => call<Job>(`/api/downloads/${id}`),
  retry: (id: string) => call<Job>(`/api/downloads/${id}/retry`, { method: "POST" }),
  fileUrl: (id: string) => `/api/downloads/${id}/file`,
};
