import { describe, expect, it } from "vitest";
import { formatDay } from "./dates";
import { tidyStem } from "./FilenameEditor";
import { pageWindow } from "./Pagination";

describe("page numbers", () => {
  it("shows every page when there are few", () => {
    expect(pageWindow(1, 1)).toEqual([1]);
    expect(pageWindow(3, 7)).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it("keeps the ends and the pages around the current one", () => {
    expect(pageWindow(1, 14)).toEqual([1, 2, 3, 4, "…", 14]);
    expect(pageWindow(7, 14)).toEqual([1, "…", 6, 7, 8, "…", 14]);
    expect(pageWindow(14, 14)).toEqual([1, "…", 11, 12, 13, 14]);
  });

  it("shows a single missing page instead of a gap", () => {
    expect(pageWindow(4, 14)).toEqual([1, 2, 3, 4, 5, "…", 14]);
    expect(pageWindow(11, 14)).toEqual([1, "…", 10, 11, 12, 13, 14]);
  });

  it("always includes the current page, once and in order", () => {
    for (let total = 1; total <= 30; total++) {
      for (let current = 1; current <= total; current++) {
        const numbers = pageWindow(current, total).filter((p): p is number => p !== "…");
        expect(numbers).toContain(current);
        expect(numbers).toEqual([...new Set(numbers)].sort((a, b) => a - b));
        expect(numbers[0]).toBe(1);
        expect(numbers.at(-1)).toBe(total);
      }
    }
  });
});

describe("filename cleaning (same rules as the server)", () => {
  it("turns spaces and forbidden characters into single hyphens", () => {
    expect(tidyStem("My Report: Q3/2026?")).toBe("My-Report-Q3-2026");
    expect(tidyStem('a<b>c"d|e*f\\g')).toBe("a-b-c-d-e-f-g");
  });

  it("drops a typed .pdf, edge punctuation and repeated hyphens", () => {
    expect(tidyStem("Annual report.pdf")).toBe("Annual-report");
    expect(tidyStem("  --name--  ")).toBe("name");
    expect(tidyStem("a  -  b")).toBe("a-b");
  });

  it("keeps Chinese characters and gives an empty name for nothing usable", () => {
    expect(tidyStem("TC_2026-10-15-00700-委任董事")).toBe("TC_2026-10-15-00700-委任董事");
    expect(tidyStem(' / : * ? ')).toBe("");
  });

  it("is limited in length", () => {
    expect(tidyStem("x".repeat(500)).length).toBe(110);
  });
});

describe("day format", () => {
  it("writes the day without a leading zero", () => {
    expect(formatDay("2026-10-03")).toBe("3 Oct 2026");
    expect(formatDay("2026-01-31")).toBe("31 Jan 2026");
  });
});
