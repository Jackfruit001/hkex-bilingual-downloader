import type { Diagnostics, SearchResult, Status } from "./api";
import { STATUS } from "./AnnouncementCard";
import { formatDay } from "./dates";

const ORDER: Status[] = ["matched", "check", "en_only", "tc_only"];

/** What the search did, in plain terms, for a reviewer who wants to see how the result was built. */
export function SearchDetails({ result }: { result: SearchResult }) {
  const d: Diagnostics = result.diagnostics;
  const sections = [
    ["English section", d.english],
    ["Chinese section", d.chinese],
  ] as const;
  const looksWrong = d.english.rows_with_c_suffix + d.chinese.rows_without_c_suffix;
  return (
    <details className="details-panel">
      <summary>How this search worked (for technical reviewers)</summary>
      <div className="mt-3 grid gap-4 text-sm">
        <p>
          The app asks HKEXnews for each language section separately, keeps the documents released between{" "}
          <strong>{formatDay(result.start)}</strong> and <strong>{formatDay(result.end)}</strong> (Hong Kong time), and
          then pairs the English and Chinese documents.
        </p>

        <table className="trace">
          <caption className="sr-only">Documents received from HKEXnews, by section</caption>
          <thead>
            <tr>
              <th scope="col">From HKEXnews</th>
              {sections.map(([name]) => (
                <th key={name} scope="col">
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Requests made</th>
              {sections.map(([name, s]) => (
                <td key={name}>{s.calls}</td>
              ))}
            </tr>
            <tr>
              <th scope="row">Documents received</th>
              {sections.map(([name, s]) => (
                <td key={name}>{s.rows_fetched}</td>
              ))}
            </tr>
            <tr>
              <th scope="row">Date range split into parts</th>
              {sections.map(([name, s]) => (
                <td key={name}>{s.splits === 0 ? "No" : `${s.splits} times`}</td>
              ))}
            </tr>
            <tr>
              <th scope="row">Entries that could not be read</th>
              {sections.map(([name, s]) => (
                <td key={name}>{s.rows_skipped}</td>
              ))}
            </tr>
          </tbody>
        </table>

        <dl className="facts">
          <dt>Outside your dates</dt>
          <dd>
            {d.outside_range} documents. The search asks for one extra day on each side so the edges never depend on
            how HKEXnews treats dates, then drops them.
          </dd>
          <dt>Section check</dt>
          <dd>
            {looksWrong === 0
              ? "Every document is in the section you would expect (Chinese files in the Chinese section)."
              : `${looksWrong} documents look like they are in the wrong section. Treat their pairings with care.`}
          </dd>
          <dt>Pairing result</dt>
          <dd>
            {result.summary.total} announcements:{" "}
            {ORDER.filter((s) => d.pairing[s]).map((s, i) => (
              <span key={s}>
                {i > 0 && ", "}
                {d.pairing[s]} {STATUS[s].label.toLowerCase()}
              </span>
            ))}
            .
          </dd>
          <dt>Time taken</dt>
          <dd>{d.seconds} seconds</dd>
          <dt>Stock and category lists</dt>
          <dd>{d.reference === "live" ? "Loaded from HKEXnews." : "Bundled copy, because HKEXnews could not be reached."}</dd>
        </dl>
      </div>
    </details>
  );
}
