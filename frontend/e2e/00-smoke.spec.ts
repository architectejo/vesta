import { test, expect } from "@playwright/test";
import { loginAs } from "./support/auth";

test("président se connecte et voit l'accueil de Fc Malaïka", async ({ page }) => {
  page.on("console", (msg) => console.log(`[console:${msg.type()}]`, msg.text()));
  page.on("pageerror", (err) => console.log("[pageerror]", err.message));

  console.log("t0", Date.now());
  const session = await loginAs(page, "president@example.org");
  console.log("t1 after loginAs", Date.now());
  expect(session.club?.slug).toBe("fc-malaika");
  console.log("t2 before toHaveURL", Date.now());
  await expect(page).toHaveURL("/", { timeout: 5_000 });
  console.log("t3 after toHaveURL", Date.now());
  await expect(page.getByText(/Malaïka/i).first()).toBeVisible({ timeout: 5_000 });
  console.log("t4 done", Date.now());
});
