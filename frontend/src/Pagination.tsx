import { ChevronLeft, ChevronRight } from "./icons";

/** Page numbers to show: the ends and the pages around the current one, with "…" for gaps. */
export function pageWindow(current: number, total: number): (number | "…")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const wanted = new Set([1, total, current - 1, current, current + 1]);
  if (current <= 3) [2, 3, 4].forEach((p) => wanted.add(p));
  if (current >= total - 2) [total - 3, total - 2, total - 1].forEach((p) => wanted.add(p));
  const pages = [...wanted].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b);
  const out: (number | "…")[] = [];
  let previous = 0;
  for (const page of pages) {
    if (page - previous === 2) out.push(previous + 1); // one missing page: show it, not a gap
    else if (page - previous > 2) out.push("…");
    out.push(page);
    previous = page;
  }
  return out;
}

interface Props {
  page: number;
  pages: number;
  onPage: (page: number) => void;
}

export function Pagination({ page, pages, onPage }: Props) {
  if (pages <= 1) return null;
  return (
    <nav className="pager" aria-label="Pages of results">
      <button type="button" className="pager-btn" disabled={page === 1} onClick={() => onPage(page - 1)}>
        <ChevronLeft /> Previous
      </button>
      {pageWindow(page, pages).map((p, i) =>
        p === "…" ? (
          <span key={`gap-${i}`} className="pager-gap" aria-hidden="true">
            …
          </span>
        ) : (
          <button
            key={p}
            type="button"
            className="pager-btn pager-num"
            aria-label={`Page ${p}`}
            aria-current={p === page ? "page" : undefined}
            onClick={() => onPage(p)}
          >
            {p}
          </button>
        ),
      )}
      <button type="button" className="pager-btn" disabled={page === pages} onClick={() => onPage(page + 1)}>
        Next <ChevronRight />
      </button>
    </nav>
  );
}
