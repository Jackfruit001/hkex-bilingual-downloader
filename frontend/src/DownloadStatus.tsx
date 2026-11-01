import type { DownloadState } from "./useDownload";

interface Props {
  state: DownloadState;
  onRetry: (jobId: string) => void;
}

/** What is happening to a download, in words; failures say why and offer a retry. */
export function DownloadStatus({ state, onRetry }: Props) {
  return (
    <span role="status" aria-live="polite" className="text-sm">
      {state.phase === "working" && "Downloading and checking the files…"}
      {state.phase === "sent" && "Sent to your downloads."}
      {state.phase === "failed" && (
        <>
          <span className="text-danger">{state.message} </span>
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
