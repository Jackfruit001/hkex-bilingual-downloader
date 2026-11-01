import { useCallback, useRef, useState } from "react";
import { api, ApiError, type Job } from "./api";

export type DownloadState =
  | { phase: "idle" }
  | { phase: "working"; done: number; total: number }
  | { phase: "sent" }
  | { phase: "failed"; message: string; jobId: string | null };

const POLL_MS = 500;
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Starts a download job, polls it, and hands the finished file to the browser. */
export function useDownload() {
  const [state, setState] = useState<DownloadState>({ phase: "idle" });
  const alive = useRef(true);

  const follow = useCallback(async (first: Job) => {
    let job = first;
    while (alive.current && job.state === "running") {
      setState({
        phase: "working",
        done: job.items.filter((i) => i.state === "done").length,
        total: job.items.length,
      });
      await sleep(POLL_MS);
      job = await api.job(job.job_id);
    }
    if (job.state === "done") {
      const link = document.createElement("a");
      link.href = api.fileUrl(job.job_id);
      link.click(); // the server sends it as an attachment, so the page stays where it is
      setState({ phase: "sent" });
    } else {
      const failed = job.items.find((i) => i.error)?.error?.message;
      setState({ phase: "failed", message: failed ?? job.error?.message ?? "The download failed.", jobId: job.job_id });
    }
  }, []);

  const run = useCallback(
    async (start: () => Promise<Job>) => {
      setState({ phase: "working", done: 0, total: 1 });
      try {
        await follow(await start());
      } catch (e) {
        const message = e instanceof ApiError ? e.message : "The download failed. Try again.";
        setState({ phase: "failed", message, jobId: null });
      }
    },
    [follow],
  );

  const retry = useCallback(
    (jobId: string) => run(() => api.retry(jobId)),
    [run],
  );

  return { state, run, retry };
}
