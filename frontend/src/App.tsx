import { useMemo, useRef, useState } from "react";
import { AnnouncementCard, STATUS, StatusIcon } from "./AnnouncementCard";
import {
  api,
  ApiError,
  type ApiErrorBody,
  type DocumentInfo,
  type SearchParams,
  type SearchResult,
  type Status,
} from "./api";
import { DownloadStatus } from "./DownloadStatus";
import { formatDay } from "./dates";
import { AlertIcon, BrandMark, CheckIcon, DownloadIcon, InfoIcon, SearchIcon, ZipIcon } from "./icons";
import { Pagination } from "./Pagination";
import { SearchDetails } from "./SearchDetails";
import { SearchForm, stockLabel } from "./SearchForm";
import { useDownload } from "./useDownload";

const MAX_BULK_ANNOUNCEMENTS = 50;
const PAGE_SIZES = [10, 20, 50];

export function App() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState<ApiErrorBody | null>(null);
  const [last, setLast] = useState<SearchParams | null>(null);
  const [filter, setFilter] = useState<Status | null>(null);
  const [newestFirst, setNewestFirst] = useState(true);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0] ?? 10);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [names, setNames] = useState<Record<string, string>>({});
  const bulk = useDownload();
  const top = useRef<HTMLDivElement>(null);

  const search = async (params: SearchParams) => {
    setBusy(true);
    setError(null);
    setLast(params);
    try {
      setResult(await api.search(params));
      setFilter(null);
      setPage(1);
      setSelected(new Set());
      setNames({});
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

  const pages = Math.max(1, Math.ceil(shown.length / pageSize));
  const current = Math.min(page, pages);
  const first = (current - 1) * pageSize;
  const visible = shown.slice(first, first + pageSize);
  const allVisibleSelected = visible.length > 0 && visible.every((a) => selected.has(a.id));

  const goToPage = (p: number) => {
    setPage(p);
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    top.current?.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" });
  };
  const change = (apply: () => void) => {
    apply();
    setPage(1);
  };

  const toggle = (id: string) =>
    setSelected((old) => {
      const next = new Set(old);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  const togglePage = () =>
    setSelected((old) => {
      const next = new Set(old);
      for (const a of visible) {
        if (allVisibleSelected) next.delete(a.id);
        else next.add(a.id);
      }
      return next;
    });

  const nameOf = (doc: DocumentInfo) => names[doc.path] ?? doc.filename ?? "";
  const rename = (path: string, name: string | null) =>
    setNames((old) => {
      const next = { ...old };
      if (name === null) delete next[path];
      else next[path] = name;
      return next;
    });

  const bulkItems = useMemo(
    () =>
      (result?.announcements ?? [])
        .filter((a) => selected.has(a.id))
        .flatMap((a) => [a.en, a.tc])
        .filter((d): d is DocumentInfo => !!d && d.downloadable)
        .map((d) => ({ path: d.path, filename: names[d.path] ?? d.filename ?? "" })),
    [result, selected, names],
  );
  const downloadSelected = () => {
    if (!result) return;
    const code = result.company.code;
    void bulk.run(() => api.startDownload("bulk_zip", bulkItems, `HKEX_${code}_${result.start}_to_${result.end}.zip`));
  };

  const STEPS = [
    { icon: <SearchIcon size={20} />, title: "Search", text: "Enter a stock code and the dates you need." },
    {
      icon: <CheckIcon />,
      title: "Check the pairs",
      text: "English and Chinese versions sit side by side, with the evidence for each pairing.",
    },
    { icon: <DownloadIcon />, title: "Download", text: "One PDF, a pair as a ZIP, or many announcements at once." },
  ];

  const total = result?.summary.total ?? 0;
  const tiles: { key: Status | null; label: string; count: number }[] = [
    { key: null, label: "All announcements", count: total },
    ...(["matched", "check", "en_only", "tc_only"] as Status[])
      .filter((s) => result?.summary[s])
      .map((s) => ({ key: s, label: STATUS[s].label, count: result?.summary[s] ?? 0 })),
  ];

  return (
    <>
      <header className="masthead">
        <div className="mx-auto max-w-4xl px-4">
          <div className="brand">
            <BrandMark />
            <div>
              <h1 className="text-2xl font-bold tracking-tight">HKEX bilingual downloader</h1>
              <p className="text-sm">English and Traditional Chinese announcements, paired and named for you.</p>
            </div>
          </div>
          <p className="mt-4">
            <span className="pill-hkt">All dates and times are Hong Kong time</span>
          </p>
        </div>
      </header>

      <div className={`mx-auto max-w-4xl px-4 ${selected.size > 0 ? "pb-32" : "pb-12"}`}>
        <main>
          <SearchForm busy={busy} onSearch={(p) => void search(p)} />

          {busy && (
            <div role="status" aria-live="polite" className="mt-6">
              <div className="loading-track" aria-hidden="true" />
              <p className="text-muted mt-3">Searching the English and Chinese sections, then pairing the versions…</p>
              <div className="mt-4 grid gap-4" aria-hidden="true">
                <div className="skeleton" />
                <div className="skeleton" style={{ opacity: 0.7 }} />
                <div className="skeleton" style={{ opacity: 0.4 }} />
              </div>
            </div>
          )}

          {error && !busy && (
            <div role="alert" className="notice mt-6">
              <AlertIcon />
              <div>
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
            </div>
          )}

          {!result && !busy && !error && (
            <ul className="steps" aria-label="How it works">
              {STEPS.map((step, i) => (
                <li key={step.title} className="step" style={{ "--i": i } as React.CSSProperties}>
                  <span className="step-icon">{step.icon}</span>
                  <p className="font-semibold">{step.title}</p>
                  <p className="text-muted text-sm">{step.text}</p>
                </li>
              ))}
            </ul>
          )}

          {result && !busy && (
            <section className="mt-10" aria-labelledby="results-heading" ref={top} style={{ scrollMarginTop: "1rem" }}>
              <div className="result-head">
                <span className="code-pill">{result.company.code}</span>
                <div>
                  <h2 id="results-heading" className="text-xl font-bold">
                    {result.company.name_en} <span lang="zh-Hant">{result.company.name_tc}</span>
                    {!result.company.active && <span className="badge-muted">Delisted</span>}
                  </h2>
                  <p className="text-muted text-sm">
                    Published {formatDay(result.start)} to {formatDay(result.end)} (Hong Kong time)
                  </p>
                </div>
              </div>

              {result.alternatives.length > 0 && last && (
                <div className="info">
                  <InfoIcon />
                  <div>
                    <p>
                      The code {result.company.code} was also used by{" "}
                      {result.alternatives.map((s) => s.name_en + (s.active ? "" : " (delisted)")).join(", ")}. You are
                      looking at the company that holds it today.
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {result.alternatives.map((s) => (
                        <button
                          key={s.stock_id}
                          type="button"
                          className="secondary btn-sm"
                          onClick={() => void search({ ...last, stock_id: s.stock_id })}
                        >
                          Search {s.name_en} instead
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {result.warnings.map((w) => (
                <p key={w} className="notice">
                  <AlertIcon />
                  <span>{w}</span>
                </p>
              ))}

              <p id="summary" className="summary">
                <strong>{total}</strong> {total === 1 ? "announcement" : "announcements"} found. Click a box to show
                only those.
              </p>
              <div className="tiles">
                {tiles.map((t) => (
                  <button
                    key={t.key ?? "all"}
                    type="button"
                    className={`tile ${t.key ?? "all"}`}
                    aria-pressed={filter === t.key}
                    onClick={() => change(() => setFilter(t.key === null || filter === t.key ? null : t.key))}
                  >
                    <span className="tile-count">{t.count}</span>
                    <span className="tile-label inline-flex items-center gap-1">
                      {t.key && <StatusIcon status={t.key} />} {t.label}
                    </span>
                  </button>
                ))}
              </div>

              <div className="hint">
                <span className="hint-icon">
                  <ZipIcon />
                </span>
                <div>
                  <p className="font-semibold">Want several announcements at once?</p>
                  <p className="text-sm">
                    Tick the box at the top left of each announcement, then press "Download selected as ZIP" at the
                    bottom of the screen. Your ticks stay when you change page.
                  </p>
                  <button type="button" className="link text-sm mt-1" onClick={togglePage}>
                    {allVisibleSelected ? "Untick everything on this page" : "Tick everything on this page"}
                  </button>
                </div>
              </div>

              <div className="toolbar">
                <p className="text-muted text-sm" aria-live="polite">
                  {shown.length === 0
                    ? "Nothing to show."
                    : `Showing ${first + 1} to ${first + visible.length} of ${shown.length}`}
                </p>
                <div className="toolbar-controls">
                  <label className="select-label">
                    Sort by
                    <select
                      className="select"
                      value={newestFirst ? "new" : "old"}
                      onChange={(e) => change(() => setNewestFirst(e.target.value === "new"))}
                    >
                      <option value="new">Newest first</option>
                      <option value="old">Oldest first</option>
                    </select>
                  </label>
                  <label className="select-label">
                    Per page
                    <select
                      className="select"
                      value={pageSize}
                      onChange={(e) => change(() => setPageSize(Number(e.target.value)))}
                    >
                      {PAGE_SIZES.map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>

              <ul className="mt-3 grid gap-4">
                {visible.map((a, i) => (
                  <AnnouncementCard
                    key={a.id}
                    item={a}
                    index={i}
                    selected={selected.has(a.id)}
                    onToggle={() => toggle(a.id)}
                    nameOf={nameOf}
                    onRename={rename}
                  />
                ))}
              </ul>

              <Pagination page={current} pages={pages} onPage={goToPage} />

              <SearchDetails result={result} />
            </section>
          )}

          <details className="panel mt-8" style={{ marginTop: "2rem", padding: "1rem 1.25rem" }}>
            <summary>How pairing works</summary>
            <div className="mt-2 grid gap-2 text-sm">
              <p>
                HKEXnews lists English and Chinese documents separately. This app compares publication time, HKEX
                file numbers, headline categories and numbers in the titles to decide which documents belong
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

      {result && selected.size > 0 && (
        <div className="bulkbar" role="region" aria-label="Bulk download">
          <span className="font-semibold">
            {selected.size} selected
          </span>
          <button type="button" className="link text-sm" onClick={() => setSelected(new Set())}>
            Clear
          </button>
          <button
            type="button"
            className="primary ml-auto"
            disabled={selected.size > MAX_BULK_ANNOUNCEMENTS || bulkItems.length === 0 || bulk.state.phase === "working"}
            onClick={downloadSelected}
          >
            <ZipIcon /> Download selected as ZIP
          </button>
          {selected.size > MAX_BULK_ANNOUNCEMENTS && (
            <span className="text-danger text-sm">Choose up to {MAX_BULK_ANNOUNCEMENTS} announcements.</span>
          )}
          {selected.size <= MAX_BULK_ANNOUNCEMENTS && bulkItems.length === 0 && (
            <span className="text-muted text-sm">None of the ticked entries has a PDF to download.</span>
          )}
          <DownloadStatus state={bulk.state} onRetry={(id) => void bulk.retry(id)} />
        </div>
      )}
    </>
  );
}
