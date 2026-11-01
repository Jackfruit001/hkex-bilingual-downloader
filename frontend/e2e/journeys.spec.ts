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
  await expect(page.locator("#summary")).toContainText("17 announcements: 17 matched");
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
