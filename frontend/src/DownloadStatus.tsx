import { AlertIcon, CheckIcon, Spinner } from "./icons";
import type { DownloadState } from "./useDownload";

interface Props {
  state: DownloadState;
  onRetry: (jobId: string) => void;
}

/** What is happening to a download, in words and a progress bar; failures say why and offer a retry. */
export function DownloadStatus({ state, onRetry }: Props) {
  return (
    <span role="status" aria-live="polite" className="dl-status">
      {state.phase === "working" && (
        <>
          <Spinner />
          <span>
            Downloading and checking {state.done} of {state.total} {state.total === 1 ? "file" : "files"}…
          </span>
          <span className={`bar ${state.done === 0 ? "indeterminate" : ""}`} aria-hidden="true">
            <span style={{ width: `${Math.max(8, Math.round((state.done / state.total) * 100))}%` }} />
          </span>
        </>
      )}
      {state.phase === "sent" && (
        <span className="sent">
          <CheckIcon /> Sent to your downloads.
        </span>
      )}
      {state.phase === "failed" && (
        <>
          <span className="text-danger inline-flex items-center gap-1">
            <AlertIcon /> {state.message}
          </span>
          {state.jobId !== null && (
            <button type="button" className="link" onClick={() => onRetry(state.jobId ?? "")}>
              Retry failed files
            </button>
          )}
        </>
      )}
    </span>
  );
}
