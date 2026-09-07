const test = require("node:test");
const assert = require("node:assert/strict");
const core = require("../plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/learning/core.js");
const pack = require("../plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/learning/requirements-writing.json");
const epoch = "2026-09-07T12:00:00.000Z";
const digest = "a".repeat(64);

test("wrong diagnosis selects a worked example; correct diagnosis selects transfer", () => {
  let session = core.createSession(pack, digest, epoch);
  const concept = pack.concepts[0];
  const q = concept.questions.diagnostic;
  const wrong = q.choices.find((c) => c.id !== q.correct).id;
  const bad = core.dispatch(
    pack,
    session,
    { type: "answer", concept: concept.id, choice: wrong },
    epoch,
  );
  assert.equal(core.status(pack, bad, concept.id, epoch).stage, "lesson");
  const good = core.dispatch(
    pack,
    session,
    { type: "answer", concept: concept.id, choice: q.correct },
    epoch,
  );
  assert.equal(core.status(pack, good, concept.id, epoch).stage, "transfer");
  assert.equal(session.events.length, 0);
});

function action(s, type, extra = {}, at = epoch) {
  return core.dispatch(pack, s, { type, concept: "obligation", ...extra }, at);
}
function completeFirst() {
  let s = core.createSession(pack, digest, epoch);
  s = action(s, "answer", { choice: "a" });
  s = action(s, "answer", { choice: "c" });
  s = action(s, "write", {
    text: "The meeting room service shall issue one booking confirmation.",
  });
  return action(s, "self-review", { criteria: ["subject", "single"] });
}
test("prerequisites, writing review, and seven-day retrieval form one executable journey", () => {
  let s = core.createSession(pack, digest, epoch);
  assert.equal(core.status(pack, s, "measure", epoch).stage, "locked");
  assert.throws(
    () =>
      core.dispatch(
        pack,
        s,
        { type: "answer", concept: "measure", choice: "b" },
        epoch,
      ),
    /prerequisite/,
  );
  s = completeFirst();
  assert.equal(core.status(pack, s, "measure", epoch).stage, "diagnostic");
  assert.equal(
    core.status(pack, s, "obligation", "2026-09-14T11:59:59.000Z").stage,
    "complete",
  );
  assert.throws(
    () => action(s, "answer", { choice: "a" }, "2026-09-14T11:59:59.000Z"),
    /No question/,
  );
  assert.equal(
    core.status(pack, s, "obligation", "2026-09-14T12:00:00.000Z").stage,
    "review",
  );
  s = action(s, "answer", { choice: "a" }, "2026-09-14T12:00:00.000Z");
  assert.equal(
    core.status(pack, s, "obligation", "2026-09-14T12:00:00.000Z").due,
    "2026-10-05T12:00:00.000Z",
  );
});
test("wrong retrieval gets a one-day retry; self-review does not fabricate a writing grade", () => {
  let s = completeFirst();
  const summary = core.summary(pack, s, epoch)[0];
  assert.equal(summary.self_checks, 2);
  assert.equal(summary.criteria_count, 3);
  assert.equal("mastered" in summary, false);
  s = action(s, "answer", { choice: "b" }, "2026-09-14T12:00:00.000Z");
  assert.equal(
    core.status(pack, s, "obligation", "2026-09-14T12:00:00.000Z").due,
    "2026-09-15T12:00:00.000Z",
  );
});
test("first wrong attempt remains visible after remediation and a correct retry", () => {
  let s = core.createSession(pack, digest, epoch);
  s = action(s, "answer", { choice: "b" });
  s = action(s, "study");
  s = action(s, "answer", { choice: "a" });
  s = action(s, "answer", { choice: "b" });
  assert.equal(core.status(pack, s, "obligation", epoch).stage, "transfer");
  const sum = core.summary(pack, s, epoch)[0];
  assert.equal(sum.first_correct, 0);
  assert.equal(sum.first_total, 2);
  assert.equal(sum.attempts, 3);
});
test("hints and repeated practice are recorded without mutating the first answer", () => {
  let s = core.createSession(pack, digest, epoch);
  s = action(s, "hint");
  s = action(s, "answer", { choice: "a" });
  assert.equal(s.events.at(-1).helped, true);
  assert.throws(
    () => action(s, "answer", { choice: "not-a-choice" }),
    /listed/,
  );
});
test("export/import replays exact transitions and rejects corruption atomically", () => {
  const s = completeFirst();
  assert.deepEqual(
    core.importSession(pack, digest, JSON.stringify(s), epoch),
    s,
  );
  for (const change of [
    (x) => {
      x.pack_digest = "b".repeat(64);
    },
    (x) => {
      x.events[0].helped = true;
    },
    (x) => {
      x.events[0].stage = "review";
    },
    (x) => {
      x.events.push({ ...x.events[0], at: "2099-01-01T00:00:00.000Z" });
    },
    (x) => {
      x.extra = "hidden";
    },
    (x) => {
      x.events[0].at = "2026-02-30T12:00:00.000Z";
    },
    (x) => {
      x.events[3].criteria = ["not-a-criterion"];
    },
  ]) {
    const bad = structuredClone(s);
    change(bad);
    assert.throws(() =>
      core.importSession(pack, digest, JSON.stringify(bad), epoch),
    );
  }
  assert.equal(s.events.length, 4);
});
test("revised writing requires a new self-review without resetting the first review clock", () => {
  let s = completeFirst();
  s = action(s, "write", {
    text: "The booking service shall issue a receipt for each accepted request.",
  });
  assert.equal(core.status(pack, s, "obligation", epoch).stage, "writing");
  s = action(s, "self-review", { criteria: [] }, "2026-09-08T12:00:00.000Z");
  assert.equal(
    core.status(pack, s, "obligation", "2026-09-08T12:00:00.000Z").due,
    "2026-09-14T12:00:00.000Z",
  );
});
test("invalid, oversized, backwards-clock, and unsupported actions fail closed", () => {
  const s = core.createSession(pack, digest, epoch);
  assert.throws(
    () =>
      core.importSession(pack, digest, "x".repeat(core.MAX_IMPORT + 1), epoch),
    /large/,
  );
  assert.throws(() => core.importSession(pack, digest, "null", epoch));
  assert.throws(
    () => action(s, "answer", { choice: "a" }, "2026-09-06T12:00:00.000Z"),
    /backwards/,
  );
  assert.throws(() => action(s, "promote"), /Unsupported/);
  assert.throws(() => action(s, "self-review", { criteria: [] }), /draft/);
});
test("Unicode progress stays exportable within the import byte limit", () => {
  let s = completeFirst();
  let full = false;
  for (let i = 0; i < 150; i++) {
    try {
      s = action(s, "write", { text: "学".repeat(3900) });
    } catch (e) {
      assert.match(e.message, /size limit/);
      full = true;
      break;
    }
  }
  assert.equal(full, true);
  assert.ok(
    new TextEncoder().encode(JSON.stringify(s)).length <= core.MAX_IMPORT,
  );
  assert.deepEqual(
    core.importSession(pack, digest, JSON.stringify(s), epoch),
    s,
  );
});
test("a delayed first review does not inherit assistance from the original lesson", () => {
  let s = core.createSession(pack, digest, epoch);
  s = action(s, "answer", { choice: "b" });
  s = action(s, "study");
  s = action(s, "answer", { choice: "b" });
  s = action(s, "answer", { choice: "c" });
  s = action(s, "write", {
    text: "The service shall send a booking confirmation.",
  });
  s = action(s, "self-review", { criteria: [] });
  s = action(s, "answer", { choice: "a" }, "2026-09-14T12:00:00.000Z");
  assert.equal(s.events.at(-1).helped, false);
});
