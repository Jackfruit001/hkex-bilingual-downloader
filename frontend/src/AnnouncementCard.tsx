import { useState } from "react";
import { api, ApiError, type Announcement, type ContentCheck, type DocumentInfo, type Status } from "./api";
import { formatHkt } from "./dates";
import { DownloadStatus } from "./DownloadStatus";
import { useDownload } from "./useDownload";

export const STATUS: Record<Status, { label: string; icon: string; hint: string }> = {
  matched: { label: "Matched", icon: "✓", hint: "Confirmed by the pairing rules." },
  check: { label: "Check pairing", icon: "!", hint: "A likely counterpart exists, but the evidence isn't conclusive." },
  en_only: { label: "English only", icon: "–", hint: "No Chinese version was found." },
  tc_only: { label: "Chinese only", icon: "–", hint: "No English version was found." },
};

interface Props {
  item: Announcement;
  selected: boolean;
  onToggle: () => void;
}

function VersionRow({
  lang,
  doc,
  missing,
  onDownload,
  busy,
}: {
  lang: "en" | "tc";
  doc: DocumentInfo | null;
  missing: string;
  onDownload: (doc: DocumentInfo) => void;
  busy: boolean;
}) {
  const name = lang === "en" ? "English" : "Chinese";
  if (!doc) {
    return (
      <div className="version missing">
        <p className="version-lang">{name} version</p>
        <p className="text-muted">{missing}</p>
      </div>
    );
  }
  return (
    <div className="version">
      <p className="version-lang">{name} version</p>
      <p lang={lang === "tc" ? "zh-Hant" : "en"} className="font-medium break-words">
        {doc.title}
      </p>
      <p className="text-muted text-sm">
        {doc.file_type} {doc.size_label && `· ${doc.size_label}`} ·{" "}
        <a href={doc.source_url} target="_blank" rel="noreferrer">
          View on HKEXnews
        </a>
      </p>
      {doc.downloadable ? (
        <>
          <p className="filename" title="The file will be saved with this name">
            {doc.filename}
          </p>
          <button type="button" className="secondary" disabled={busy} onClick={() => onDownload(doc)}>
            Download {name} PDF
          </button>
        </>
      ) : (
        <p className="text-sm">This entry is a web page on HKEXnews, not a PDF. Open it on HKEXnews.</p>
      )}
    </div>
  );
}

export function AnnouncementCard({ item, selected, onToggle }: Props) {
  const download = useDownload();
  const [check, setCheck] = useState<ContentCheck | string | null>(null);
  const status = STATUS[item.status];
  const busy = download.state.phase === "working";

  const single = (doc: DocumentInfo) =>
    download.run(() => api.startDownload("single", [{ path: doc.path, filename: doc.filename ?? "document.pdf" }]));

  const pair = () => {
    if (!item.en?.filename || !item.tc?.filename) return;
    void download.run(() =>
      api.startDownload(
        "pair_zip",
        [
          { path: item.en!.path, filename: item.en!.filename! },
          { path: item.tc!.path, filename: item.tc!.filename! },
        ],
        item.pair_zip_name ?? "",
      ),
    );
  };

  const runCheck = async () => {
    if (!item.en) return;
    const tcPaths = [item.tc?.path, ...item.rivals.filter((r) => r.lang === "tc").map((r) => r.path)].filter(
      (p): p is string => !!p,
    );
    setCheck("Comparing the figures in the files…");
    try {
      setCheck(await api.contentCheck(item.en.path, tcPaths));
    } catch (e) {
      setCheck(e instanceof ApiError ? e.message : "The content check failed. Try again.");
    }
  };

  const zipReason = !item.en
    ? "A pair ZIP needs both versions; the English version is missing."
    : !item.tc
      ? "A pair ZIP needs both versions; the Chinese version is missing."
      : !item.pair_zip_downloadable
        ? "A pair ZIP needs both versions to be PDFs."
        : "";

  return (
    <li className={`card status-${item.status}`}>
      <header className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            aria-label={`Select ${(item.en ?? item.tc)?.title ?? "announcement"} for the bulk ZIP`}
          />
        </label>
        <span className="badge" title={status.hint}>
          <span aria-hidden="true">{status.icon}</span> {status.label}
        </span>
        <time dateTime={item.release_at} className="text-sm">
          {formatHkt(item.release_at)} HKT
        </time>
        {item.category && <span className="text-muted text-sm">{item.category}</span>}
        {item.bilingual && <span className="badge-muted">Bilingual document</span>}
        {item.separate && <span className="badge-muted">Published on different days</span>}
      </header>

      <div className="versions">
        <VersionRow
          lang="en"
          doc={item.en}
          missing="No English version found for these dates."
          onDownload={single}
          busy={busy}
        />
        <VersionRow
          lang="tc"
          doc={item.tc}
          missing="No Chinese version found for these dates."
          onDownload={single}
          busy={busy}
        />
      </div>

      {item.status === "check" && (
        <p className="notice">
          Both versions are shown, but they may not belong together. Compare the titles before relying on them.
        </p>
      )}
      {item.notice_url && (
        <p className="text-sm">
          HKEXnews shows a notice in the other section:{" "}
          <a href={item.notice_url} target="_blank" rel="noreferrer">
            open the notice
          </a>
          .
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button type="button" className="primary" disabled={!!zipReason || busy} onClick={pair} aria-describedby={zipReason ? `${item.id}-why` : undefined}>
          Download both (ZIP)
        </button>
        {zipReason && (
          <span id={`${item.id}-why`} className="text-muted text-sm">
            {zipReason}
          </span>
        )}
        {item.status === "check" && item.en && (
          <button type="button" className="secondary" onClick={runCheck}>
            Check contents
          </button>
        )}
        <DownloadStatus state={download.state} onRetry={(id) => void download.retry(id)} />
      </div>

      {check && (
        <p className="notice" role="status">
          {typeof check === "string" ? check : check.message}
          {typeof check !== "string" && check.available && (
            <>
              {" "}
              {check.conclusive
                ? "The figures agree clearly. This does not change the status."
                : "That is not conclusive either way."}
            </>
          )}
        </p>
      )}

      <details className="mt-3">
        <summary>Why this pairing</summary>
        <ul className="mt-2 list-disc pl-5 text-sm">
          {item.evidence.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        {item.rivals.length > 0 && (
          <>
            <p className="mt-2 text-sm font-medium">Other possible versions</p>
            <ul className="list-disc pl-5 text-sm">
              {item.rivals.map((r) => (
                <li key={r.path} lang={r.lang === "tc" ? "zh-Hant" : "en"}>
                  {r.title} (score {r.score})
                </li>
              ))}
            </ul>
          </>
        )}
      </details>
    </li>
  );
}
