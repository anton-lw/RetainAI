import { expect, test } from "@playwright/test";

import { mockRetainAiApi } from "./fixtures/mockApi";


test.beforeEach(async ({ page }) => {
  await mockRetainAiApi(page);
});


test("allows an operator to sign in and see the live dashboard shell", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Sign in to RetainAI" })).toBeVisible();
  await page.getByLabel("Email").fill("admin@retainai.local");
  await page.getByLabel("Password").fill("retainai-demo");
  await page.getByRole("button", { name: "Sign in" }).click();

  const queueSection = page.getByTestId("risk-queue-section");
  await expect(page.getByRole("heading", { name: "High-priority follow-up list" })).toBeVisible();
  await expect(queueSection.getByText("Amina Noor")).toBeVisible();
  await expect(page.getByText("Runtime ok").first()).toBeVisible();
});


test("filters the queue by region and beneficiary search", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Email").fill("admin@retainai.local");
  await page.getByLabel("Password").fill("retainai-demo");
  await page.getByRole("button", { name: "Sign in" }).click();

  const queueSection = page.getByTestId("risk-queue-section");
  await expect(queueSection).toBeVisible();
  await page.getByLabel("Region filter").selectOption("Northern Region");
  await expect(queueSection.getByText("Amina Noor")).toBeVisible();
  await expect(queueSection.getByText("David Ochieng")).toBeHidden();

  await page.getByLabel("Region filter").selectOption("All");
  await page.getByLabel("Risk queue search").fill("David");
  await expect(queueSection.getByText("David Ochieng")).toBeVisible();
  await expect(queueSection.getByText("Amina Noor")).toBeHidden();
});

test("shows validation readiness history for the selected program", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Email").fill("admin@retainai.local");
  await page.getByLabel("Password").fill("retainai-demo");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("heading", { name: "Shadow-mode readiness" })).toBeVisible();
  await expect(page.getByText("Last evaluation status: ready_for_shadow_mode.")).toBeVisible();
  await expect(page.getByText("Rolling validation meets the current shadow-mode threshold.")).toBeVisible();
  await expect(page.getByText("partial followup | 24 cases | precision 40%")).toBeVisible();
});


test("renders the dedicated mobile-lite workflow and explanation sheet", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  await page.getByLabel("Email").fill("admin@retainai.local");
  await page.getByLabel("Password").fill("retainai-demo");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByTestId("mobile-lite-view")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Mobile-lite follow-up queue" })).toBeVisible();
  await page.getByRole("button", { name: "Explain case" }).first().click();
  await expect(page.getByText("Amina Noor:")).toBeVisible();
  await expect(page.getByText("Amina has missed recent check-ins and may benefit from a supportive outreach call.")).toBeVisible();
});
