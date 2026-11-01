import { useMemo, useState } from "react";
import { AnnouncementCard, STATUS } from "./AnnouncementCard";
import { api, ApiError, type ApiErrorBody, type SearchParams, type SearchResult, type Status } from "./api";
import { DownloadStatus } from "./DownloadStatus";
import { SearchForm, stockLabel } from "./SearchForm";
import { useDownload } from "./useDownload";

const MAX_BULK_ANNOUNCEMENTS = 50;

export function summaryLine(result: SearchResult): string {
  const counts = result.summary;
  const parts = (["matched", "check", "en_only", "tc_only"] as Status[])
    .filter((s) => counts[s])
    .map((s) => `${counts[s]} ${STATUS[s].label.toLowerCase()}`);
  const total = counts.total ?? 0;
  return `${total} announcement${total === 1 ? "" : "s"}${parts.length ? `: ${parts.join(", ")}` : ""}`;
}

export function App() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState<ApiErrorBody | null>(null);
  const [last, setLast] = useState<SearchParams | null>(null);
  const [filter, setFilter] = useState<Status | null>(null);
  const [newestFirst, setNewestFirst] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const bulk = useDownload();

  const search = async (params: SearchParams) => {
    setBusy(true);
    setError(null);
    setLast(params);
    try {
      setResult(await api.search(params));
      setFilter(null);
      setSelected(new Set());
    } catch (e) {
      setResult(null);
      setError(e instanceof ApiError ? e.body : { code: "UNKNOWN", message: "Something went wrong. Try again." });
    } finally {
      setBusy(false);
    }
  };

  const shown = useMemo(() => {
    const list = (result?.announcements ?? []).filter((a) => !filter || a.status === filter);
    return newestFirst ? list : [...list].reverse();
  }, [result, filter, newestFirst]);

  const toggle = (id: string) =>
    setSelected((old) => {
      const next = new Set(old);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const downloadSelected = () => {
    if (!result) return;
    const items = result.announcements
      .filter((a) => selected.has(a.id))
      .flatMap((a) => [a.en, a.tc])
      .filter((d): d is NonNullable<typeof d> => !!d && d.downloadable && !!d.filename)
      .map((d) => ({ path: d.path, filename: d.filename! }));
    const code = result.company.code;
    void bulk.run(() => api.startDownload("bulk_zip", items, `HKEX_${code}_${result.start}_to_${result.end}.zip`));
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <header>
        <h1 className="text-2xl font-semibold">HKEX bilingual downloader</h1>
        <p className="text-muted mt-1">
          Find a company's announcements on HKEXnews and download the English and Chinese PDFs together.
        </p>
      </header>

      <main className="mt-6">
        <SearchForm busy={busy} onSearch={(p) => void search(p)} />

        <div role="status" aria-live="polite" className="mt-4">
          {busy && <p>Searching the English and Chinese sections, then pairing the versions…</p>}
        </div>

        {error && (
          <div role="alert" className="notice mt-4">
            <p>{error.message}</p>
            {error.code === "AMBIGUOUS_STOCK_CODE" && last && (
              <ul className="mt-2 grid gap-1">
                {(error.details?.choices ?? []).map((s) => (
                  <li key={s.stock_id}>
                    <button type="button" className="link" onClick={() => void search({ ...last, stock_id: s.stock_id })}>
                      {stockLabel(s)}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {result && !busy && (
          <section className="mt-8" aria-labelledby="results-heading">
            <h2 id="results-heading" className="text-xl font-semibold">
              {result.company.code} {result.company.name_en}{" "}
              <span lang="zh-Hant">{result.company.name_tc}</span>
              {!result.company.active && <span className="badge-muted">Delisted</span>}
            </h2>
            {result.alternatives.length > 0 && last && (
              <p className="text-muted mt-1 text-sm">
                {result.company.code} was also used by{" "}
                {result.alternatives.map((s, i) => (
                  <span key={s.stock_id}>
                    {i > 0 && ", "}
                    {s.name_en}
                    {!s.active && " (delisted)"}{" "}
                    <button type="button" className="link" onClick={() => void search({ ...last, stock_id: s.stock_id })}>
                      Switch
                    </button>
                  </span>
                ))}
                .
              </p>
            )}
            <p className="mt-2" id="summary">
              {summaryLine(result)}
            </p>
            {result.warnings.map((w) => (
              <p key={w} className="notice mt-2">
                {w}
              </p>
            ))}

            <div className="mt-3 flex flex-wrap items-center gap-2">
              {(["matched", "check", "en_only", "tc_only"] as Status[])
                .filter((s) => result.summary[s])
                .map((s) => (
                  <button
                    key={s}
                    type="button"
                    className="chip"
                    aria-pressed={filter === s}
                    onClick={() => setFilter(filter === s ? null : s)}
                  >
                    {STATUS[s].label} ({result.summary[s]})
                  </button>
                ))}
              <button type="button" className="link ml-auto" onClick={() => setNewestFirst(!newestFirst)}>
                {newestFirst ? "Showing newest first" : "Showing oldest first"}
              </button>
            </div>

            <div className="bulkbar mt-3">
              <span>{selected.size} selected</span>
              <button
                type="button"
                className="primary"
                disabled={selected.size === 0 || selected.size > MAX_BULK_ANNOUNCEMENTS || bulk.state.phase === "working"}
                onClick={downloadSelected}
              >
                Download selected as ZIP
              </button>
              {selected.size > MAX_BULK_ANNOUNCEMENTS && (
                <span className="text-danger text-sm">Choose up to {MAX_BULK_ANNOUNCEMENTS} announcements.</span>
              )}
              <DownloadStatus state={bulk.state} onRetry={(id) => void bulk.retry(id)} />
            </div>

            <ul className="mt-4 grid gap-4">
              {shown.map((a) => (
                <AnnouncementCard key={a.id} item={a} selected={selected.has(a.id)} onToggle={() => toggle(a.id)} />
              ))}
            </ul>

            <details className="mt-8 text-sm">
              <summary>Search details for technical reviewers</summary>
              <pre className="mt-2 overflow-x-auto">{JSON.stringify(result.diagnostics, null, 2)}</pre>
            </details>
          </section>
        )}

        <details className="mt-8">
          <summary>How pairing works</summary>
          <div className="mt-2 grid gap-2 text-sm">
            <p>
              HKEXnews lists English and Chinese documents separately. This app compares publication time,
              HKEX file numbers, headline categories and numbers in the titles to decide which documents belong
              together.
            </p>
            <ul className="list-disc pl-5">
              {(Object.keys(STATUS) as Status[]).map((s) => (
                <li key={s}>
                  <strong>{STATUS[s].label}:</strong> {STATUS[s].hint}
                </li>
              ))}
            </ul>
            <p>
              A version is never substituted for a missing one. When the evidence is not enough, the pair is
              marked "Check pairing" and the reasons are shown.
            </p>
          </div>
        </details>
      </main>

      <footer className="text-muted mt-10 text-sm">
        Documents are the original files from HKEXnews. All times are Hong Kong time.
      </footer>
    </div>
  );
}
