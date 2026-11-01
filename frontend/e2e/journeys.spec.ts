import { expect, test } from "@playwright/test";

async function search(page: import("@playwright/test").Page, code: string, from: string, to: string) {
  await page.goto("/");
  await page.getByLabel("Stock code or company name").fill(code);
  await page.getByRole("button", { name: "Custom" }).click();
  await page.getByLabel("From").fill(from);
  await page.getByLabel("to", { exact: true }).fill(to);
  await page.getByRole("button", { name: "Search announcements" }).click();
}

test("search, read the pairs, download a pair as a ZIP", async ({ page }) => {
  await search(page, "700", "2026-09-30", "2026-10-30");
  await expect(page.locator("#summary")).toContainText("17 announcements found");
  await expect(page.getByRole("button", { name: /Matched/ })).toContainText("17");
  await expect(page.getByText("Matched").first()).toBeVisible();

  const card = page.locator("li.card").first();
  await expect(card.getByText("English version")).toBeVisible();
  await expect(card.getByText("Chinese version")).toBeVisible();
  await expect(card.locator(".filename").first()).toContainText(/^EN_2026-/);

  await card.getByText("Why this pairing").click();
  await expect(card.getByText(/consecutive HKEX file numbers/)).toBeVisible();

  const download = page.waitForEvent("download");
  await card.getByRole("button", { name: "Download both (ZIP)" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^EN-TC_2026-\d\d-\d\d-00700-.*\.zip$/);
  await expect(card.getByText("Sent to your downloads.")).toBeVisible();
});

test("download a single PDF with the generated filename", async ({ page }) => {
  await search(page, "700", "2026-09-30", "2026-10-30");
  const download = page.waitForEvent("download");
  await page.locator("li.card").first().getByRole("button", { name: "Download English PDF" }).click();
  expect((await download).suggestedFilename()).toMatch(/^EN_2026-\d\d-\d\d-00700-.*\.pdf$/);
});

test("select several announcements and download them as one ZIP", async ({ page }) => {
  await search(page, "700", "2026-09-30", "2026-10-30");
  const boxes = page.locator("li.card input[type=checkbox]");
  await boxes.nth(0).check();
  await boxes.nth(1).check();
  await expect(page.getByText("2 selected")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download selected as ZIP" }).click();
  expect((await download).suggestedFilename()).toBe("HKEX_00700_2026-09-30_to_2026-10-30.zip");
});

test("an unknown code and an empty range explain what to do", async ({ page }) => {
  await search(page, "99999", "2026-09-30", "2026-10-30");
  await expect(page.getByRole("alert")).toContainText("No HKEX security uses code 99999");
  await search(page, "700", "2020-01-01", "2020-01-02");
  await expect(page.getByRole("alert")).toContainText("Try a wider range");
});

test("a bad date range is explained", async ({ page }) => {
  await search(page, "700", "2026-10-30", "2026-09-30");
  await expect(page.getByRole("alert")).toContainText("The start date is after the end date");
});

test("long results are split into pages that can be turned", async ({ page }) => {
  await search(page, "700", "2026-03-01", "2026-10-30");
  await expect(page.locator("#summary")).toContainText("50 announcements found");
  await expect(page.getByText("Showing 1 to 10 of 50")).toBeVisible();
  await expect(page.locator("li.card")).toHaveCount(10);

  const first = await page.locator("li.card time").first().textContent();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Showing 11 to 20 of 50")).toBeVisible();
  await expect(page.getByRole("button", { name: "Page 2" })).toHaveAttribute("aria-current", "page");
  expect(await page.locator("li.card time").first().textContent()).not.toBe(first);

  await page.getByRole("button", { name: "Page 5" }).click();
  await expect(page.getByText("Showing 41 to 50 of 50")).toBeVisible();
  await expect(page.getByRole("button", { name: "Next" })).toBeDisabled();

  await page.getByLabel("Per page").selectOption("20");
  await expect(page.getByText("Showing 1 to 20 of 50")).toBeVisible();
  await expect(page.locator("li.card")).toHaveCount(20);
});

test("sort order can be changed from a dropdown", async ({ page }) => {
  await search(page, "700", "2026-09-30", "2026-10-30");
  const newest = await page.locator("li.card time").first().getAttribute("datetime");
  await page.getByLabel("Sort by").selectOption("old");
  const oldest = await page.locator("li.card time").first().getAttribute("datetime");
  expect((oldest ?? "") < (newest ?? "")).toBe(true);
});

test("ticks stay when the page changes and can be set for a whole page", async ({ page }) => {
  await search(page, "700", "2026-03-01", "2026-10-30");
  await page.getByRole("button", { name: "Tick everything on this page" }).click();
  await expect(page.getByText("10 selected")).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("10 selected")).toBeVisible();
  await page.locator("li.card input[type=checkbox]").first().check();
  await expect(page.getByText("11 selected")).toBeVisible();
});

test("a filename can be edited and the download uses the new name", async ({ page }) => {
  await search(page, "700", "2026-09-30", "2026-10-30");
  const card = page.locator("li.card").first();
  await expect(card.getByText("Will be saved as").first()).toBeVisible();
  await card.getByRole("button", { name: "Edit filename" }).first().click();
  await page.getByRole("textbox", { name: "Edit filename" }).fill("My report: Q3/2026");
  await page.getByRole("button", { name: "Save name" }).click();
  await expect(card.locator(".filename").first()).toHaveText("My-report-Q3-2026.pdf");
  await expect(card.getByText("Edited.")).toBeVisible();

  const download = page.waitForEvent("download");
  await card.getByRole("button", { name: "Download English PDF" }).click();
  expect((await download).suggestedFilename()).toBe("My-report-Q3-2026.pdf");

  await card.getByRole("button", { name: "Use the suggested name" }).click();
  await expect(card.locator(".filename").first()).toContainText(/^EN_2026-/);
});

test("search details are shown as a readable table, not code", async ({ page }) => {
  await search(page, "700", "2026-09-30", "2026-10-30");
  await page.getByText("How this search worked").click();
  await expect(page.getByRole("table")).toContainText("Documents received");
  await expect(page.getByText("Every document is in the section you would expect")).toBeVisible();
  await expect(page.locator("pre")).toHaveCount(0);
});
