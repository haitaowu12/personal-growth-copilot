/* Shared, deterministic learning transitions. No DOM, storage, network, or model. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.LearningCore = api;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";
  const MAX_EVENTS = 2000;
  const MAX_IMPORT = 1000000;
  const bytes = (text) => new TextEncoder().encode(text).length;
  function fail(message) {
    throw new Error(message);
  }
  function time(value) {
    if (
      typeof value !== "string" ||
      !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(value) ||
      !Number.isFinite(Date.parse(value)) ||
      new Date(value).toISOString() !== value
    )
      fail("Invalid timestamp.");
    return Date.parse(value);
  }
  function exact(value, keys) {
    if (
      !value ||
      typeof value !== "object" ||
      Array.isArray(value) ||
      Object.keys(value).sort().join("|") !== [...keys].sort().join("|")
    )
      fail("Unexpected progress fields.");
  }
  function createSession(pack, digest, now) {
    time(now);
    if (!/^[a-f0-9]{64}$/.test(digest)) fail("Invalid topic fingerprint.");
    return {
      schema_version: "1.0",
      pack_id: pack.id,
      pack_version: pack.version,
      pack_digest: digest,
      started_at: now,
      events: [],
    };
  }
  function conceptFor(pack, id) {
    return pack.concepts.find((c) => c.id === id) || fail("Unknown concept.");
  }
  function eventsFor(session, id) {
    return session.events.filter((e) => e.concept === id);
  }
  function hasReview(session, id) {
    return eventsFor(session, id).some((e) => e.type === "self-review");
  }
  function status(pack, session, id, now) {
    const c = conceptFor(pack, id),
      events = eventsFor(session, id);
    const missing = c.prerequisites.filter((p) => !hasReview(session, p));
    if (missing.length) return { stage: "locked", missing };
    const diagnosis = events.find(
      (e) => e.type === "answer" && e.stage === "diagnostic",
    );
    if (!diagnosis) return { stage: "diagnostic" };
    if (diagnosis.choice !== c.questions.diagnostic.correct) {
      if (!events.some((e) => e.type === "study")) return { stage: "lesson" };
      if (
        !events.some(
          (e) =>
            e.type === "answer" &&
            e.stage === "practice" &&
            e.choice === c.questions.practice.correct,
        )
      )
        return { stage: "practice" };
    }
    if (!events.some((e) => e.type === "answer" && e.stage === "transfer"))
      return { stage: "transfer" };
    const lastWrite = events.findLastIndex((e) => e.type === "write");
    const lastCheck = events.findLastIndex((e) => e.type === "self-review");
    if (lastWrite < 0 || lastCheck < lastWrite) return { stage: "writing" };
    const recalls = events.filter(
      (e) => e.type === "answer" && e.stage === "review",
    );
    const last = recalls.at(-1);
    const anchor = last || events.find((e) => e.type === "self-review");
    const days =
      last && last.choice !== c.questions.review.correct
        ? 1
        : pack.review_days[
            Math.min(recalls.length, pack.review_days.length - 1)
          ];
    const due = new Date(time(anchor.at) + days * 86400000).toISOString();
    return {
      stage: time(now) >= time(due) ? "review" : "complete",
      due,
      review_count: recalls.length,
      self_checks: events[lastCheck].criteria.length,
      criteria_count: c.writing.criteria.length,
    };
  }
  function dispatch(pack, session, action, now) {
    if (!Array.isArray(session.events) || session.events.length >= MAX_EVENTS)
      fail(
        "Progress limit reached. Export this record and start a new session.",
      );
    if (time(now) < time(session.events.at(-1)?.at || session.started_at))
      fail("Device time moved backwards. Correct the clock before continuing.");
    const c = conceptFor(pack, action.concept),
      s = status(pack, session, c.id, now);
    if (s.stage === "locked") fail("Complete prerequisite practice first.");
    const prior = eventsFor(session, c.id);
    let event;
    switch (action.type) {
      case "answer": {
        exact(action, ["type", "concept", "choice"]);
        if (!["diagnostic", "practice", "transfer", "review"].includes(s.stage))
          fail("No question is open.");
        const q = c.questions[s.stage];
        if (!q.choices.some((x) => x.id === action.choice))
          fail("Choose a listed answer.");
        const reviewAnchor =
          s.stage === "review"
            ? prior.findLastIndex(
                (e) =>
                  e.type === "self-review" ||
                  (e.type === "answer" && e.stage === "review"),
              )
            : -1;
        const current = prior.slice(reviewAnchor + 1);
        const helped =
          current.some((e) => e.type === "study") ||
          current.some((e) => e.type === "hint" && e.stage === s.stage) ||
          prior.some((e) => e.type === "answer" && e.stage === s.stage);
        event = { ...action, stage: s.stage, helped, at: now };
        break;
      }
      case "hint":
        exact(action, ["type", "concept"]);
        if (!["diagnostic", "practice", "transfer", "review"].includes(s.stage))
          fail("No question is open.");
        event = { ...action, stage: s.stage, at: now };
        break;
      case "study":
        exact(action, ["type", "concept"]);
        // Study is always an explicit learner action. It marks later responses assisted.
        event = { ...action, at: now };
        break;
      case "write":
        exact(action, ["type", "concept", "text"]);
        if (!prior.some((e) => e.type === "answer" && e.stage === "transfer"))
          fail("Try the application question first.");
        if (
          typeof action.text !== "string" ||
          action.text.trim().length < 10 ||
          action.text.length > 4000
        )
          fail("Write between 10 and 4,000 characters.");
        event = { ...action, at: now };
        break;
      case "self-review":
        exact(action, ["type", "concept", "criteria"]);
        if (s.stage !== "writing" || !prior.some((e) => e.type === "write"))
          fail("Save a draft before checking it.");
        if (
          !Array.isArray(action.criteria) ||
          new Set(action.criteria).size !== action.criteria.length ||
          action.criteria.some(
            (id) => !c.writing.criteria.some((x) => x.id === id),
          )
        )
          fail("Invalid self-review criteria.");
        event = { ...action, criteria: [...action.criteria], at: now };
        break;
      default:
        fail("Unsupported learner action.");
    }
    const next = { ...session, events: [...session.events, event] };
    if (bytes(JSON.stringify(next)) > MAX_IMPORT)
      fail(
        "Progress size limit reached. Export this record and start a new session.",
      );
    return next;
  }
  function importSession(pack, digest, input, now) {
    if (typeof input !== "string" || bytes(input) > MAX_IMPORT)
      fail("Progress file is too large.");
    let raw;
    try {
      raw = JSON.parse(input);
    } catch (_) {
      fail("Progress file is not valid JSON.");
    }
    exact(raw, [
      "schema_version",
      "pack_id",
      "pack_version",
      "pack_digest",
      "started_at",
      "events",
    ]);
    if (raw.schema_version !== "1.0") fail("Unsupported progress version.");
    if (
      raw.pack_id !== pack.id ||
      raw.pack_version !== pack.version ||
      raw.pack_digest !== digest
    )
      fail(
        "Progress belongs to different topic content. Open the matching lesson version.",
      );
    if (!Array.isArray(raw.events) || raw.events.length > MAX_EVENTS)
      fail("Invalid event history.");
    if (time(raw.started_at) > time(now))
      fail("Progress contains future timestamps.");
    let replay = createSession(pack, digest, raw.started_at);
    for (const e of raw.events) {
      if (!e || typeof e !== "object" || time(e.at) > time(now))
        fail("Progress contains invalid or future events.");
      const action = { type: e.type, concept: e.concept };
      if (e.type === "answer") action.choice = e.choice;
      if (e.type === "write") action.text = e.text;
      if (e.type === "self-review") action.criteria = e.criteria;
      replay = dispatch(pack, replay, action, e.at);
      const expected = replay.events.at(-1);
      exact(e, Object.keys(expected));
      if (
        JSON.stringify(
          Object.keys(e)
            .sort()
            .map((k) => [k, e[k]]),
        ) !==
        JSON.stringify(
          Object.keys(expected)
            .sort()
            .map((k) => [k, expected[k]]),
        )
      )
        fail("Progress has inconsistent assessment metadata.");
    }
    return replay;
  }
  function summary(pack, session, now) {
    return pack.concepts.map((c) => {
      const events = eventsFor(session, c.id);
      const answers = events.filter((e) => e.type === "answer");
      const first = answers.filter(
        (e, i) => answers.findIndex((x) => x.stage === e.stage) === i,
      );
      return {
        id: c.id,
        ...status(pack, session, c.id, now),
        attempts: answers.length,
        first_correct: first.filter(
          (e) => e.choice === c.questions[e.stage].correct,
        ).length,
        first_total: first.length,
        assisted: answers.filter((e) => e.helped).length,
        written: events.some((e) => e.type === "write"),
        reviewed: hasReview(session, c.id),
      };
    });
  }
  return {
    createSession,
    status,
    dispatch,
    importSession,
    summary,
    MAX_IMPORT,
  };
});
