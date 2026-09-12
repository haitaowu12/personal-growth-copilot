#!/usr/bin/env node

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

import { chromium } from "playwright-core";

const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  const name = process.argv[index];
  const value = process.argv[index + 1];
  if (!name?.startsWith("--") || !value) {
    throw new Error("Usage: run_learning_browser_acceptance.mjs --html FILE --evidence FILE");
  }
  args.set(name.slice(2), value);
}

const htmlPath = resolve(args.get("html") || "build/learning-package/requirements-writing.html");
const evidencePath = resolve(
  args.get("evidence") || "build/evidence/learning-browser-acceptance.json",
);
if (!existsSync(htmlPath)) throw new Error(`Learning HTML is absent: ${htmlPath}`);

function browserExecutable() {
  const configured = process.env.PGC_BROWSER_EXECUTABLE;
  const candidates = [
    configured,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ].filter(Boolean);
  const found = candidates.find((candidate) => existsSync(candidate));
  if (!found) {
    throw new Error(
      "No supported Chromium browser was found. Set PGC_BROWSER_EXECUTABLE to an installed Chrome, Edge, or Chromium executable.",
    );
  }
  return found;
}

function check(condition, message) {
  if (!condition) throw new Error(message);
}

async function expectText(locator, text, message = `Expected text: ${text}`) {
  await locator.waitFor({ state: "visible" });
  const observed = await locator.textContent();
  check(observed?.includes(text), `${message}; observed ${JSON.stringify(observed)}`);
}

async function waitForNotice(page, text) {
  await page.locator("#notice").waitFor({ state: "visible" });
  await page.waitForFunction(
    (expected) => document.querySelector("#notice")?.textContent?.includes(expected),
    text,
  );
}

async function loadPage(browser, options = {}) {
  const context = await browser.newContext({
    viewport: options.viewport || { width: 1440, height: 1000 },
    reducedMotion: "reduce",
    acceptDownloads: true,
  });
  if (options.storageFailure) {
    await context.addInitScript(() => {
      Storage.prototype.setItem = () => {
        throw new DOMException("simulated storage denial", "SecurityError");
      };
      Storage.prototype.removeItem = () => {
        throw new DOMException("simulated storage denial", "SecurityError");
      };
    });
  }
  const signals = { consoleErrors: [], pageErrors: [], networkRequests: [] };
  await context.route(/^https?:\/\//, async (route) => {
    signals.networkRequests.push(route.request().url());
    await route.abort("blockedbyclient");
  });
  const page = await context.newPage();
  page.on("console", (message) => {
    if (message.type() === "error") signals.consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => signals.pageErrors.push(String(error)));
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "domcontentloaded" });
  await page.locator("#workspace").waitFor({ state: "visible" });
  return { context, page, signals };
}

async function assertHealthy(signals, label) {
  check(signals.consoleErrors.length === 0, `${label}: console errors: ${signals.consoleErrors.join(" | ")}`);
  check(signals.pageErrors.length === 0, `${label}: page errors: ${signals.pageErrors.join(" | ")}`);
  check(
    signals.networkRequests.length === 0,
    `${label}: unexpected network requests: ${signals.networkRequests.join(" | ")}`,
  );
}

async function currentPack(page) {
  return page.locator("#topic-data").evaluate((node) => JSON.parse(node.textContent).pack);
}

async function keyboardActivate(page, label) {
  for (let attempts = 0; attempts < 30; attempts += 1) {
    const active = await page.evaluate(() => ({
      tag: document.activeElement?.tagName || "",
      text: document.activeElement?.textContent?.trim() || "",
    }));
    if (["A", "BUTTON"].includes(active.tag) && active.text.includes(label)) {
      await page.keyboard.press("Enter");
      return;
    }
    await page.keyboard.press("Tab");
  }
  throw new Error(`Keyboard focus did not reach ${label}`);
}

async function answer(page, question, useCorrectAnswer) {
  const choice = useCorrectAnswer
    ? question.correct
    : question.choices.find((item) => item.id !== question.correct)?.id;
  check(Boolean(choice), "Question lacks a usable answer choice");
  await page.locator(`input[name="answer"][value="${choice}"]`).check();
  await page.getByRole("button", { name: "Check answer" }).click();
  await page.locator("section.feedback").waitFor({ state: "visible" });
}

async function answerWithKeyboard(page, question, useCorrectAnswer) {
  const choice = useCorrectAnswer
    ? question.correct
    : question.choices.find((item) => item.id !== question.correct)?.id;
  check(Boolean(choice), "Question lacks a usable answer choice");
  await page.locator(`input[name="answer"][value="${choice}"]`).focus();
  await page.keyboard.press("Space");
  await page.getByRole("button", { name: "Check answer" }).focus();
  await page.keyboard.press("Enter");
  const feedback = page.locator("section.feedback");
  await feedback.waitFor({ state: "visible" });
  check(
    await feedback.evaluate((node) => node === document.activeElement),
    "Keyboard answer feedback did not receive focus",
  );
}

async function continueFromFeedback(page) {
  await page.getByRole("button", { name: /Continue|See your review status/ }).click();
}

async function completeWriting(page, concept, suffix) {
  const draft = `${concept.title}: observable example ${suffix}. The response states one condition, one measurable result, and one review point.`;
  await page.locator("#draft").fill(draft);
  await page.getByRole("button", { name: "Save draft & self-review" }).click();
  const checks = page.locator("section input[type=checkbox]");
  for (let index = 0; index < (await checks.count()); index += 1) {
    await checks.nth(index).check();
  }
  await page.getByRole("button", { name: "Record self-review" }).click();
  await expectText(page.locator("#workspace"), "Practice recorded");
}

async function completeCorrectPath(page, concept, useHint, suffix) {
  if (useHint) await page.getByRole("button", { name: "Give me a hint" }).click();
  await answer(page, concept.questions.diagnostic, true);
  await continueFromFeedback(page);
  await answer(page, concept.questions.transfer, true);
  await continueFromFeedback(page);
  await completeWriting(page, concept, suffix);
}

const browserPath = browserExecutable();
const browser = await chromium.launch({
  executablePath: browserPath,
  headless: true,
  args: ["--disable-dev-shm-usage"],
});
const scenarios = [];

async function scenario(name, operation) {
  const started = Date.now();
  try {
    const details = (await operation()) || {};
    scenarios.push({ name, status: "pass", duration_ms: Date.now() - started, ...details });
  } catch (error) {
    scenarios.push({ name, status: "fail", duration_ms: Date.now() - started, error: String(error) });
    throw error;
  }
}

try {
  await scenario("complete learning journey with keyboard entry, remediation, hint, transfer, writing, and self-review", async () => {
    const { context, page, signals } = await loadPage(browser);
    try {
      const pack = await currentPack(page);
      check(pack.concepts.length === 3, "Expected three governed learning concepts");
      await expectText(page.locator("h1"), pack.title);
      await keyboardActivate(page, "Start practice");
      await page.locator('input[name="answer"]').first().waitFor({ state: "visible" });

      const first = pack.concepts[0];
      await answerWithKeyboard(page, first.questions.diagnostic, false);
      await expectText(page.locator("section.feedback"), "Supported answer");
      await continueFromFeedback(page);
      await expectText(page.locator("#workspace"), "Worked example");
      await page.getByRole("button", { name: "Try a practice question" }).click();
      await answer(page, first.questions.practice, false);
      await continueFromFeedback(page);
      await answer(page, first.questions.practice, true);
      await continueFromFeedback(page);
      await answer(page, first.questions.transfer, true);
      await continueFromFeedback(page);
      await completeWriting(page, first, "one");

      await page.getByRole("button", { name: /Continue to the next task/ }).click();
      await completeCorrectPath(page, pack.concepts[1], true, "two");
      await page.getByRole("button", { name: /Continue to the next task/ }).click();
      await completeCorrectPath(page, pack.concepts[2], false, "three");
      await page.getByRole("button", { name: /Back to your learning path/ }).click();
      await expectText(page.locator("#context"), `3 / ${pack.concepts.length}`);
      await assertHealthy(signals, "complete journey");
      return { concepts_completed: pack.concepts.length };
    } finally {
      await context.close();
    }
  });

  await scenario("browser save, reload, opt-out, and scoped removal", async () => {
    const { context, page, signals } = await loadPage(browser);
    try {
      const pack = await currentPack(page);
      const save = page.getByLabel("Save progress on this device");
      await save.check();
      await waitForNotice(page, "Progress is saved in this browser");
      await page.getByRole("button", { name: "Start practice" }).click();
      await answer(page, pack.concepts[0].questions.diagnostic, true);
      await page.reload({ waitUntil: "domcontentloaded" });
      check(await page.getByLabel("Save progress on this device").isChecked(), "Saving did not survive reload");
      await expectText(page.locator("#workspace"), "Continue practice");
      await page.getByLabel("Save progress on this device").uncheck();
      await waitForNotice(page, "browser copy was removed");
      check((await page.evaluate(() => localStorage.length)) === 0, "Scoped browser record remains after opt-out");
      await page.reload({ waitUntil: "domcontentloaded" });
      await expectText(page.locator("#workspace"), "Start practice");
      await assertHealthy(signals, "save and reload");
    } finally {
      await context.close();
    }
  });

  await scenario("export, valid import, invalid import rejection, and clear", async () => {
    const source = await loadPage(browser);
    const temporaryDirectory = dirname(evidencePath);
    mkdirSync(temporaryDirectory, { recursive: true });
    const exportedPath = resolve(temporaryDirectory, "learning-progress-export.json");
    const malformedPath = resolve(temporaryDirectory, "learning-progress-malformed.json");
    const wrongVersionPath = resolve(temporaryDirectory, "learning-progress-wrong-version.json");
    const futurePath = resolve(temporaryDirectory, "learning-progress-future.json");
    try {
      const pack = await currentPack(source.page);
      await source.page.getByRole("button", { name: "Start practice" }).click();
      await answer(source.page, pack.concepts[0].questions.diagnostic, true);
      const [download] = await Promise.all([
        source.page.waitForEvent("download"),
        source.page.getByRole("button", { name: "Export progress" }).click(),
      ]);
      await download.saveAs(exportedPath);
      const exported = JSON.parse(readFileSync(exportedPath, "utf8"));
      check(exported.events.length === 1, "Export did not retain the recorded answer");
      writeFileSync(malformedPath, "{not-json", "utf8");
      writeFileSync(
        wrongVersionPath,
        JSON.stringify({ ...exported, pack_version: "different-version" }),
        "utf8",
      );
      writeFileSync(
        futurePath,
        JSON.stringify({ ...exported, started_at: "2099-01-01T00:00:00.000Z" }),
        "utf8",
      );
      await assertHealthy(source.signals, "export source");
    } finally {
      await source.context.close();
    }

    const imported = await loadPage(browser);
    try {
      const input = imported.page.locator("#import");
      await input.setInputFiles(exportedPath);
      await waitForNotice(imported.page, "Imported into this tab");
      await expectText(imported.page.locator("#workspace"), "Continue practice");

      for (const rejected of [malformedPath, wrongVersionPath, futurePath]) {
        await input.setInputFiles(rejected);
        await waitForNotice(imported.page, "Import rejected");
        await expectText(imported.page.locator("#workspace"), "Continue practice");
      }

      await imported.page.getByRole("button", { name: "Clear progress" }).click();
      await waitForNotice(imported.page, "progress cleared");
      await expectText(imported.page.locator("#workspace"), "Start practice");
      await assertHealthy(imported.signals, "import and clear");
      return { rejected_imports: 3 };
    } finally {
      await imported.context.close();
    }
  });

  await scenario("storage-denial recovery", async () => {
    const { context, page, signals } = await loadPage(browser, { storageFailure: true });
    try {
      await page.getByLabel("Save progress on this device").click();
      await waitForNotice(page, "Browser storage is unavailable");
      check(!(await page.getByLabel("Save progress on this device").isChecked()), "Saving stayed enabled after storage denial");
      await page.getByRole("button", { name: "Clear progress" }).click();
      await waitForNotice(page, "browser copy could not be removed");
      await assertHealthy(signals, "storage denial");
    } finally {
      await context.close();
    }
  });

  await scenario("390-pixel reduced-motion offline layout", async () => {
    const { context, page, signals } = await loadPage(browser, {
      viewport: { width: 390, height: 844 },
    });
    try {
      const geometry = await page.evaluate(() => ({
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
        reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      }));
      check(geometry.reducedMotion, "Reduced-motion preference was not applied");
      check(
        geometry.scrollWidth <= geometry.clientWidth,
        `Mobile layout overflows horizontally: ${geometry.scrollWidth} > ${geometry.clientWidth}`,
      );
      await expectText(page.locator("#workspace"), "Start practice");
      await assertHealthy(signals, "mobile layout");
      return geometry;
    } finally {
      await context.close();
    }
  });
} finally {
  const browserVersion = browser.version();
  await browser.close();
  const html = readFileSync(htmlPath);
  const status = scenarios.every((item) => item.status === "pass") ? "pass" : "fail";
  const evidence = {
    schema_version: "1.0",
    evidence_class: "local-browser-acceptance",
    status,
    generated_at: new Date().toISOString(),
    browser_executable: browserPath,
    browser_version: browserVersion,
    html_path: htmlPath,
    html_sha256: createHash("sha256").update(html).digest("hex"),
    constraints: {
      file_origin: true,
      network_blocked: true,
      reduced_motion_checked: true,
      mobile_width_px: 390,
      claim_limit: "Local browser behavior only; this is not learner-outcome or cross-browser compatibility evidence.",
    },
    scenarios,
  };
  mkdirSync(dirname(evidencePath), { recursive: true });
  writeFileSync(evidencePath, `${JSON.stringify(evidence, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify(evidence, null, 2)}\n`);
  if (status !== "pass") process.exitCode = 1;
}
