// Dates are Hong Kong time everywhere (docs/SPEC.md): never the browser's own time zone.

const HK = "Asia/Hong_Kong";

export function todayHkt(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: HK }).format(now); // YYYY-MM-DD
}

export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export type Preset = "today" | "7d" | "30d" | "year" | "custom";

export const PRESETS: { id: Preset; label: string }[] = [
  { id: "today", label: "Today" },
  { id: "7d", label: "Last 7 days" },
  { id: "30d", label: "Last 30 days" },
  { id: "year", label: "This year" },
  { id: "custom", label: "Custom" },
];

export function presetRange(preset: Exclude<Preset, "custom">, today: string): [string, string] {
  switch (preset) {
    case "today":
      return [today, today];
    case "7d":
      return [addDays(today, -6), today];
    case "30d":
      return [addDays(today, -29), today];
    case "year":
      return [`${today.slice(0, 4)}-01-01`, today];
  }
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "3 Oct 2026" from "2026-10-03". */
export function formatDay(iso: string): string {
  const [y = "", m = "", d = ""] = iso.slice(0, 10).split("-");
  return `${Number(d)} ${MONTHS[Number(m) - 1] ?? m} ${y}`;
}

/** "22 Oct 2026, 12:03" from an ISO time that already carries the +08:00 offset. */
export function formatHkt(iso: string): string {
  const [date = "", time = ""] = iso.split("T");
  return `${formatDay(date)}, ${time.slice(0, 5)}`;
}
