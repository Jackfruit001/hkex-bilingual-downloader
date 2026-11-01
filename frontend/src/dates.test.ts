import { describe, expect, it } from "vitest";
import { addDays, formatHkt, presetRange, todayHkt } from "./dates";

describe("Hong Kong dates", () => {
  it("uses the Hong Kong date, not the browser's", () => {
    // 17:30 UTC on 31 Oct is already 1 Nov in Hong Kong
    expect(todayHkt(new Date("2026-10-31T17:30:00Z"))).toBe("2026-11-01");
    expect(todayHkt(new Date("2026-10-31T15:59:00Z"))).toBe("2026-10-31");
  });

  it("adds days across month and year ends", () => {
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  });

  it("computes the presets including today", () => {
    expect(presetRange("today", "2026-11-01")).toEqual(["2026-11-01", "2026-11-01"]);
    expect(presetRange("7d", "2026-11-01")).toEqual(["2026-10-26", "2026-11-01"]);
    expect(presetRange("30d", "2026-11-01")).toEqual(["2026-10-03", "2026-11-01"]);
    expect(presetRange("year", "2026-11-01")).toEqual(["2026-01-01", "2026-11-01"]);
  });

  it("shows the time as published, with no conversion", () => {
    expect(formatHkt("2026-10-22T12:03+08:00")).toBe("22 Oct 2026, 12:03");
    expect(formatHkt("2026-01-05T00:05+08:00")).toBe("5 Jan 2026, 00:05");
  });
});
