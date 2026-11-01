import { useState } from "react";
import { api, ApiError, type Announcement, type ContentCheck, type DocumentInfo, type Status } from "./api";
import { formatHkt } from "./dates";
import { DownloadStatus } from "./DownloadStatus";
import { FilenameEditor } from "./FilenameEditor";
import { AlertIcon, CheckIcon, CompareIcon, DownloadIcon, ExternalIcon, SingleIcon, Spinner, ZipIcon } from "./icons";
import { useDownload } from "./useDownload";

export const STATUS: Record<Status, { label: string; hint: string }> = {
  matched: { label: "Matched", hint: "Confirmed by the pairing rules." },
  check: { label: "Check pairing", hint: "A likely counterpart exists, but the evidence isn't conclusive." },
  en_only: { label: "English only", hint: "No Chinese version was found." },
  tc_only: { label: "Chinese only", hint: "No English version was found." },
};

/** An icon for each status, so a status is never shown by colour alone. */
export function StatusIcon({ status }: { status: Status }) {
  if (status === "matched") return <CheckIcon />;
  if (status === "check") return <AlertIcon />;
  return <SingleIcon />;
}

interface Props {
  item: Announcement;
  index: number;
  selected: boolean;
  onToggle: () => void;
  nameOf: (doc: DocumentInfo) => string;
  onRename: (path: string, name: string | null) => void;
}

function VersionRow({
  lang,
  doc,
  missing,
  onDownload,
  busy,
  nameOf,
  onRename,
}: {
  lang: "en" | "tc";
  doc: DocumentInfo | null;
  missing: string;
  onDownload: (doc: DocumentInfo) => void;
  busy: boolean;
  nameOf: (doc: DocumentInfo) => string;
  onRename: (path: string, name: string | null) => void;
}) {
  const name = lang === "en" ? "English" : "Chinese";
  const tag = <span className={`lang-tag lang-${lang}`}>{lang === "en" ? "EN" : "中文"}</span>;
  if (!doc) {
    return (
      <div className="version missing">
        <p className="version-lang">
          {tag} {name} version
        </p>
        <p className="text-muted">{missing}</p>
      </div>
    );
  }
  return (
    <div className="version">
      <p className="version-lang">
        {tag} {name} version
      </p>
      <p lang={lang === "tc" ? "zh-Hant" : "en"} className="version-title">
        {doc.title}
      </p>
      <p className="text-muted text-sm">
        {doc.file_type} {doc.size_label && `· ${doc.size_label}`} ·{" "}
        <a href={doc.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1">
          View on HKEXnews <ExternalIcon />
        </a>
      </p>
      {doc.downloadable ? (
        <>
          <FilenameEditor
            suggested={doc.filename ?? ""}
            value={nameOf(doc)}
            onChange={(name) => onRename(doc.path, name)}
          />
          <button type="button" className="secondary btn-sm" disabled={busy} onClick={() => onDownload(doc)}>
            <DownloadIcon /> Download {name} PDF
          </button>
        </>
      ) : (
        <p className="text-sm">This entry is a web page on HKEXnews, not a PDF. Open it on HKEXnews.</p>
      )}
    </div>
  );
}

export function AnnouncementCard({ item, index, selected, onToggle, nameOf, onRename }: Props) {
  const download = useDownload();
  const [check, setCheck] = useState<ContentCheck | string | null>(null);
  const [checking, setChecking] = useState(false);
  const status = STATUS[item.status];
  const busy = download.state.phase === "working";

  const single = (doc: DocumentInfo) =>
    download.run(() => api.startDownload("single", [{ path: doc.path, filename: nameOf(doc) }]));

  const pair = () => {
    if (!item.en?.filename || !item.tc?.filename) return;
    void download.run(() =>
      api.startDownload(
        "pair_zip",
        [
          { path: item.en!.path, filename: nameOf(item.en!) },
          { path: item.tc!.path, filename: nameOf(item.tc!) },
        ],
        item.pair_zip_name ?? "",
      ),
    );
  };

  const runCheck = async () => {
    if (!item.en) return;
    const tcPaths = [item.tc?.path, ...item.rivals.filter((r) => r.lang === "tc" && /\.pdf$/i.test(r.path)).map((r) => r.path)].filter(
      (p): p is string => !!p,
    );
    setChecking(true);
    setCheck("Comparing the figures in the files…");
    try {
      setCheck(await api.contentCheck(item.en.path, tcPaths));
    } catch (e) {
      setCheck(e instanceof ApiError ? e.message : "The content check failed. Try again.");
    } finally {
      setChecking(false);
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
    <li
      className={`card status-${item.status}${selected ? " selected" : ""}`}
      style={{ "--i": Math.min(index, 12) } as React.CSSProperties}
    >
      <header className="card-head">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          aria-label={`Select ${(item.en ?? item.tc)?.title ?? "announcement"} for the bulk ZIP`}
        />
        <span className="badge" title={status.hint}>
          <StatusIcon status={item.status} /> {status.label}
        </span>
        <p className="published">
          <span className="published-label">Published:</span>
          <time dateTime={item.release_at}>{formatHkt(item.release_at)} HKT</time>
        </p>
        {(item.category || item.bilingual || item.separate) && (
          <div className="chips">
            {item.category && <span className="chip chip-category">{item.category}</span>}
            {item.bilingual && <span className="chip">Bilingual document</span>}
            {item.separate && <span className="chip">Published on different days</span>}
          </div>
        )}
      </header>

      <div className="versions">
        <VersionRow
          lang="en"
          doc={item.en}
          missing="No English version found for these dates."
          onDownload={single}
          busy={busy}
          nameOf={nameOf}
          onRename={onRename}
        />
        <VersionRow
          lang="tc"
          doc={item.tc}
          missing="No Chinese version found for these dates."
          onDownload={single}
          busy={busy}
          nameOf={nameOf}
          onRename={onRename}
        />
      </div>

      {item.status === "check" && (
        <p className="notice">
          <AlertIcon />
          <span>Both versions are shown, but they may not belong together. Compare the titles before relying on them.</span>
        </p>
      )}
      {item.notice_url && (
        <p className="text-sm mt-2">
          HKEXnews shows a notice in the other section:{" "}
          <a href={item.notice_url} target="_blank" rel="noreferrer">
            open the notice
          </a>
          .
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="primary"
          disabled={!!zipReason || busy}
          onClick={pair}
          aria-describedby={zipReason ? `${item.id}-why` : undefined}
        >
          <ZipIcon /> Download both (ZIP)
        </button>
        {zipReason && (
          <span id={`${item.id}-why`} className="text-muted text-sm">
            {zipReason}
          </span>
        )}
        {item.status === "check" && item.en?.downloadable && item.tc?.downloadable && (
          <button type="button" className="secondary" disabled={checking} onClick={runCheck}>
            {checking ? <Spinner /> : <CompareIcon />} Check contents
          </button>
        )}
        <DownloadStatus state={download.state} onRetry={(id) => void download.retry(id)} />
      </div>

      {check && (
        <p className="notice" role="status">
          <AlertIcon />
          <span>
            {typeof check === "string" ? check : check.message}
            {typeof check !== "string" && check.available && (
              <>
                {" "}
                {check.conclusive
                  ? "The figures agree clearly. This does not change the status."
                  : "That is not conclusive either way."}
              </>
            )}
          </span>
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
