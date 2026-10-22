// Run against a freshly generated offline lesson. Uses an existing Playwright
// installation; never downloads browsers or changes the user's browser profile.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const playwright = require(process.env.PLAYWRIGHT_MODULE || "playwright");

async function check(engine, html, output) {
  const browser = await playwright[engine].launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await page.route(/^https?:/, route => route.abort());
    await page.goto(pathToFileURL(html).href);
    await page.getByRole("button", { name: "Start practice", exact: true }).click();
    const choices = page.locator("label.choice");
    assert.ok(await choices.count() > 1);
    const appearance = choice => choice.evaluate(el => {
      const style = getComputedStyle(el);
      return { background: style.backgroundColor, border: style.borderColor };
    });
    const settle = () => page.evaluate(() => Promise.all(
      document.getAnimations().map(animation => animation.finished.catch(() => {}))));
    await page.mouse.move(0, 0);
    await settle();
    const idle = await appearance(choices.first());
    await choices.first().hover();
    await settle();
    assert.notDeepEqual(await appearance(choices.first()), idle,
      "enabled choices should give hover feedback");
    assert.match(await choices.first().evaluate(el => getComputedStyle(el).transitionProperty), /background/);

    const hint = page.getByRole("button", { name: "Give me a hint", exact: true });
    await hint.focus();
    await page.keyboard.press("Enter");
    const focusedHint = await page.locator(".hint").evaluate(el => {
      const style = getComputedStyle(el);
      return {
        focused: document.activeElement === el, tabIndex: el.tabIndex,
        text: el.textContent, live: el.getAttribute("aria-live"),
        outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth,
      };
    });
    assert.equal(focusedHint.focused, true);
    assert.equal(focusedHint.tabIndex, -1);
    assert.equal(focusedHint.live, "polite");
    assert.ok(focusedHint.text.trim());
    assert.equal(focusedHint.outlineStyle, "solid");
    assert.equal(focusedHint.outlineWidth, "3px");
    assert.equal(await hint.isDisabled(), true);
    assert.equal(await hint.evaluate(el => getComputedStyle(el).cursor), "not-allowed");
    await page.screenshot({ path: path.join(output, `${engine}-hint-focus.png`) });

    await choices.nth(1).getByRole("radio").check();
    await page.getByRole("button", { name: "Check answer", exact: true }).click();
    assert.equal(await choices.first().getByRole("radio").isDisabled(), true,
      "fieldset disabling must disable its radio descendants");
    await page.mouse.move(0, 0);
    await settle();
    const disabledIdle = await appearance(choices.first());
    await choices.first().hover();
    await settle();
    assert.deepEqual(await appearance(choices.first()), disabledIdle,
      "disabled choices must not acquire hover feedback");
    assert.equal(await choices.first().evaluate(el => getComputedStyle(el).cursor), "not-allowed");
    await page.screenshot({ path: path.join(output, `${engine}-disabled-choice.png`) });

    // Check the other useful PR #32 change in the actual self-review UI.
    await page.reload();
    await page.getByRole("button", { name: "Start practice", exact: true }).click();
    for (const stage of ["diagnostic", "transfer"]) {
      const answer = await page.locator("#topic-data").evaluate((el, stage) => {
        const question = JSON.parse(el.textContent).pack.concepts[0].questions[stage];
        return question.choices.find(choice => choice.id === question.correct).text;
      }, stage);
      await page.getByRole("radio", { name: answer, exact: true }).check();
      await page.getByRole("button", { name: "Check answer", exact: true }).click();
      await page.getByRole("button", { name: "Continue", exact: true }).click();
    }
    await page.locator("#draft").fill("The synthetic service shall retain one complete test record.");
    await page.getByRole("button", { name: "Save draft & self-review", exact: true }).click();
    const checkboxLabel = page.locator("label.check").first();
    assert.equal(await checkboxLabel.evaluate(el => getComputedStyle(el).cursor), "pointer");
    const checkbox = checkboxLabel.getByRole("checkbox");
    assert.equal(await checkbox.isChecked(), false);
    await checkboxLabel.click();
    assert.equal(await checkbox.isChecked(), true);
    return { engine, version: browser.version(), hint: focusedHint, disabledHoverUnchanged: true,
      enabledChoiceTransitions: true, checkboxLabelPointerAndActivation: true };
  } finally {
    await browser.close();
  }
}

(async () => {
  const html = path.resolve(process.argv[2] || "output/playwright/learning-ux.html");
  const output = path.resolve(process.argv[3] || "output/playwright");
  fs.mkdirSync(output, { recursive: true });
  const results = [];
  for (const engine of ["chromium", "firefox"]) results.push(await check(engine, html, output));
  fs.writeFileSync(path.join(output, "learning-interactions.json"), JSON.stringify(results, null, 2) + "\n");
  console.log(JSON.stringify(results, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
