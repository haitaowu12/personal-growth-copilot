(function () {
  "use strict";
  const { pack, digest } = JSON.parse(
    document.getElementById("topic-data").textContent,
  );
  const core = window.LearningCore;
  const now = () => new Date().toISOString();
  const key = `pgc-learning:${pack.id}:${digest}`;
  let session = core.createSession(pack, digest, now()),
    saved = false,
    selected = null,
    dirtyDraft = false,
    displayedStage = null;
  const main = document.getElementById("workspace"),
    nav = document.getElementById("navigation"),
    aside = document.getElementById("context");
  const notice = document.getElementById("notice");
  function el(tag, text, cls) {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  }
  function button(text, fn, cls) {
    const b = el("button", text, cls);
    b.type = "button";
    b.addEventListener("click", fn);
    return b;
  }
  function tell(text, error = false) {
    notice.textContent = text;
    notice.className = error ? "error" : "";
  }
  function last(type, id) {
    return session.events.findLast((e) => e.type === type && e.concept === id);
  }
  function confirmLeave() {
    return (
      !dirtyDraft ||
      window.confirm("Your unsaved draft will be lost. Leave this exercise?")
    );
  }
  function storageUI() {
    const box = document.getElementById("storage");
    box.replaceChildren();
    const label = el("label"),
      input = el("input");
    input.type = "checkbox";
    input.checked = saved;
    input.addEventListener("change", () => {
      if (input.checked) {
        try {
          localStorage.setItem(key, JSON.stringify(session));
          saved = true;
          tell(
            "Progress is saved in this browser. Written exercises are included. Exports and browser backups are separate copies.",
          );
        } catch (_) {
          saved = false;
          tell(
            "Browser storage is unavailable. Progress remains in this tab; export it before closing.",
            true,
          );
        }
      } else {
        // Opt-out takes effect even if the browser refuses deletion.
        saved = false;
        try {
          localStorage.removeItem(key);
          tell(
            "This lesson’s browser copy was removed. Current tab progress remains. Downloaded files and backups are unchanged.",
          );
        } catch (_) {
          tell(
            "Saving is off for this tab, but the old browser copy could not be removed. Use browser site-data controls to remove it before reopening.",
            true,
          );
        }
      }
      storageUI();
    });
    label.append(
      input,
      document.createTextNode("Save progress on this device"),
    );
    box.append(label);
  }
  function persist() {
    if (!saved) return;
    try {
      localStorage.setItem(key, JSON.stringify(session));
    } catch (_) {
      saved = false;
      storageUI();
      tell(
        "Saving failed. This tab has newer progress than the browser copy. Export before closing.",
        true,
      );
    }
  }
  function act(action) {
    try {
      session = core.dispatch(pack, session, action, now());
      persist();
      return true;
    } catch (e) {
      tell(e.message, true);
      return false;
    }
  }
  function download(name, text) {
    const url = URL.createObjectURL(
      new Blob([text], { type: "application/json" }),
    );
    const a = el("a");
    a.href = url;
    a.download = name;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function go(id) {
    if (!confirmLeave()) return;
    dirtyDraft = false;
    selected = id;
    render();
    main.focus();
  }
  function firstAvailable() {
    return (
      pack.concepts.find(
        (c) =>
          !["locked", "complete"].includes(
            core.status(pack, session, c.id, now()).stage,
          ),
      )?.id || pack.concepts[0].id
    );
  }
  function navigation() {
    nav.replaceChildren();
    const home = button(
      "Your learning path",
      () => go(null),
      selected === null ? "active" : "",
    );
    nav.append(home);
    if (selected === null) home.setAttribute("aria-current", "page");
    const labels = {
      locked: "Complete earlier practice",
      diagnostic: "Start with a question",
      lesson: "Worked example",
      practice: "Practise the method",
      transfer: "Apply in a new setting",
      writing: "Write and self-review",
      review: "Review is due",
      complete: "Practice complete",
    };
    for (const [i, c] of pack.concepts.entries()) {
      const st = core.status(pack, session, c.id, now());
      const b = button(
        `${String(i + 1).padStart(2, "0")}  ${c.title}`,
        () => go(c.id),
        selected === c.id ? "active" : "",
      );
      b.append(el("small", labels[st.stage]));
      b.disabled = st.stage === "locked";
      if (selected === c.id) b.setAttribute("aria-current", "page");
      nav.append(b);
    }
  }
  function evidence(c) {
    aside.replaceChildren();
    aside.append(el("h3", "Evidence, not a score"));
    const rows = core.summary(pack, session, now());
    const completed = rows.filter((r) => r.reviewed).length;
    aside.append(
      el("div", `${completed} / ${pack.concepts.length}`, "metric"),
      el("p", "concepts practised and self-reviewed"),
    );
    if (c) {
      const r = rows.find((x) => x.id === c.id);
      aside.append(
        el(
          "p",
          `${r.first_correct}/${r.first_total} first answers correct · ${r.assisted} supported or repeated attempts`,
        ),
      );
      aside.append(
        el(
          "p",
          "Writing checks are your own assessment. Quiz results do not establish independent writing skill.",
        ),
      );
      aside.append(el("h3", "Source notes"));
      for (const id of c.source_ids) {
        const s = pack.sources.find((x) => x.id === id),
          block = el("div", undefined, "source");
        const a = el("a", s.title);
        a.href = s.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.addEventListener("click", () =>
          act({ type: "study", concept: c.id }),
        );
        block.append(
          a,
          el("p", s.section),
          el("p", `Inspected ${s.accessed} · selected material`),
        );
        aside.append(block);
      }
      aside.append(
        button(
          "Read explanation & limits",
          () => {
            if (!act({ type: "study", concept: c.id })) return;
            const block = el("div", undefined, "source");
            block.append(
              el("h3", "Explanation"),
              el("p", c.explanation),
              el("p", c.misconception),
            );
            for (const id of c.source_ids) {
              const s = pack.sources.find((x) => x.id === id);
              block.append(el("p", s.claim), el("p", s.limits));
            }
            aside.replaceChildren(block);
            aside.append(
              button("Back to progress", () => evidence(c), "quiet"),
            );
          },
          "quiet",
        ),
      );
      const report = el("div", undefined, "report");
      report.append(
        el("h3", "Something unclear?"),
        el(
          "p",
          "Export a topic issue for the author. It contains topic identity and category, never your answers.",
        ),
      );
      for (const [category, label] of [
        ["confusing", "Confusing wording"],
        ["answer-key", "Question or answer issue"],
        ["source", "Source needs review"],
      ]) {
        report.append(
          button(
            label,
            () => {
              download(
                `${pack.id}-issue.json`,
                JSON.stringify(
                  {
                    schema_version: "1.0",
                    type: "improvement-candidate",
                    topic: pack.id,
                    version: pack.version,
                    digest,
                    concept: c.id,
                    question_stage: displayedStage,
                    category,
                    created_at: now(),
                    status: "unreviewed",
                  },
                  null,
                  2,
                ),
              );
              tell(
                "Issue file prepared for download. Nothing was sent and no lesson content changed.",
              );
            },
            "quiet",
          ),
        );
      }
      aside.append(report);
    } else {
      aside.append(
        el(
          "p",
          "No account. No tracking. Works offline. Source links open only when you choose them.",
        ),
      );
      aside.append(
        el("h3", "Keep your work"),
        el(
          "p",
          "Progress starts in this tab only. Enable device saving or export a file before closing. Avoid confidential project or personal information.",
        ),
      );
      aside.append(
        el("h3", "Review policy"),
        el(
          "p",
          `First review: ${pack.review_days[0]} days after self-review. Later reviews: ${pack.review_days.at(-1)} days after a correct answer; one day after a wrong answer. These intervals are a starting policy, not a personalized prediction.`,
        ),
      );
    }
  }
  function overview() {
    main.append(
      el("p", "LEARN · PRACTISE · RETURN", "eyebrow"),
      el("h1", pack.title),
      el("p", pack.subtitle, "intro"),
      el(
        "p",
        `${pack.minutes}-minute starting session · ${pack.concepts.length} concepts · source-grounded examples`,
        "meta",
      ),
    );
    const list = el("ol", undefined, "path");
    for (const c of pack.concepts) list.append(el("li", c.objective));
    main.append(list);
    main.append(
      button(
        session.events.length ? "Continue practice" : "Start practice",
        () => go(firstAvailable()),
        "primary",
      ),
    );
    main.append(
      el("div", undefined, "rule"),
      el("h3", "How this works"),
      el(
        "p",
        "Try a short scenario first. A wrong answer opens a worked example and practice. A correct answer moves to a new application. Then write your own response, self-review it, and return for retrieval.",
      ),
    );
    const rows = core.summary(pack, session, now());
    for (const row of rows.filter((r) => r.due)) {
      const c = pack.concepts.find((x) => x.id === row.id);
      const d = el("div", undefined, "progress-row");
      d.append(
        el("span", c.title),
        el(
          "span",
          row.stage === "review"
            ? "Review due now"
            : `Review ${new Date(row.due).toLocaleDateString()}`,
        ),
      );
      main.append(d);
    }
    main.append(el("p", pack.content_notice, "notice-box"));
  }
  function worked(c) {
    main.append(el("p", c.explanation, "intro"));
    for (const [label, text] of [
      ["Draft", c.example.before],
      ["Worked example", c.example.after],
      ["Why it helps", c.example.why],
    ]) {
      const block = el("div", undefined, "example");
      block.append(el("span", label, "label"), el("p", text));
      main.append(block);
    }
    main.append(
      el("p", c.misconception),
      button(
        "Try a practice question",
        () => {
          if (act({ type: "study", concept: c.id })) render();
        },
        "primary",
      ),
    );
  }
  function question(c, stage) {
    const q = c.questions[stage],
      form = el("form"),
      field = el("fieldset");
    field.append(el("legend", q.prompt));
    for (const option of q.choices) {
      const label = el("label", undefined, "choice"),
        input = el("input");
      input.type = "radio";
      input.name = "answer";
      input.value = option.id;
      input.required = true;
      label.append(input, el("span", option.text));
      field.append(label);
    }
    const check = el("button", "Check answer", "primary");
    check.type = "submit";
    const hintArea = el("p", undefined, "hint");
    hintArea.setAttribute("aria-live", "polite");
    const hint = button(
      "Give me a hint",
      () => {
        if (act({ type: "hint", concept: c.id })) {
          hintArea.textContent = q.hint;
          hint.disabled = true;
        }
      },
      "quiet",
    );
    const actions = el("div", undefined, "actions");
    actions.append(check, hint);
    form.append(field, actions, hintArea);
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const chosen = new FormData(form).get("answer");
      if (!chosen) return;
      if (!act({ type: "answer", concept: c.id, choice: chosen })) return;
      field.disabled = true;
      check.disabled = true;
      hint.disabled = true;
      const receipt = session.events.at(-1),
        correct = chosen === q.correct;
      const feedback = el(
        "section",
        undefined,
        `feedback${correct ? "" : " wrong"}`,
      );
      feedback.tabIndex = -1;
      feedback.append(
        el(
          "h3",
          correct
            ? "That follows from the scenario."
            : "Look at the evidence again.",
        ),
        el("p", q.choices.find((x) => x.id === chosen).feedback),
      );
      if (!correct)
        feedback.append(
          el(
            "p",
            `Supported answer: ${q.choices.find((x) => x.id === q.correct).text}`,
          ),
        );
      feedback.append(
        el(
          "p",
          receipt.helped
            ? "Support or a prior attempt was used. This is practice evidence."
            : "First answer without recorded support for this question.",
          "meta",
        ),
      );
      const next = button(
        stage === "review" ? "See your review status" : "Continue",
        () => {
          render();
          main.focus();
        },
        "primary",
      );
      feedback.append(next);
      form.append(feedback);
      feedback.focus();
      evidence(c);
      navigation();
    });
    main.append(form);
  }
  function writing(c, edit = false) {
    main.append(el("p", c.writing.prompt, "intro"));
    const label = el("label", "Your response");
    label.htmlFor = "draft";
    const draft = el("textarea");
    draft.id = "draft";
    draft.maxLength = 4000;
    draft.value = last("write", c.id)?.text || "";
    draft.addEventListener("input", () => {
      dirtyDraft = true;
    });
    main.append(
      label,
      draft,
      el(
        "p",
        "10–4,000 characters. Use invented examples; omit confidential information.",
        "meta",
      ),
    );
    const reviewArea = el("section");
    const save = button(
      "Save draft & self-review",
      () => {
        if (!act({ type: "write", concept: c.id, text: draft.value })) return;
        dirtyDraft = false;
        renderChecks();
        tell(
          saved
            ? "Draft saved in this browser."
            : "Draft retained in this tab. Export or enable device saving to keep it.",
        );
      },
      "primary",
    );
    main.append(save, reviewArea);
    function renderChecks() {
      reviewArea.replaceChildren();
      reviewArea.append(el("h3", "Check your work"));
      reviewArea.append(
        el(
          "p",
          "Select only criteria your draft meets. Leave uncertain items unchecked. This is self-review, not automated grading.",
        ),
      );
      const inputs = [];
      for (const criterion of c.writing.criteria) {
        const l = el("label", undefined, "check"),
          i = el("input");
        i.type = "checkbox";
        i.value = criterion.id;
        inputs.push(i);
        l.append(i, el("span", criterion.text));
        reviewArea.append(l);
      }
      const example = el("div");
      reviewArea.append(
        button(
          "Compare a worked response",
          () => {
            example.replaceChildren(
              el("p", c.writing.example),
              el("p", c.writing.notes, "meta"),
            );
          },
          "quiet",
        ),
        example,
      );
      reviewArea.append(
        button(
          "Record self-review",
          () => {
            if (dirtyDraft) {
              tell(
                "Save your changed draft before recording its self-review.",
                true,
              );
              return;
            }
            if (
              act({
                type: "self-review",
                concept: c.id,
                criteria: inputs.filter((i) => i.checked).map((i) => i.value),
              })
            ) {
              render();
              main.focus();
            }
          },
          "primary",
        ),
      );
    }
    if (last("write", c.id) && !edit) renderChecks();
  }
  function completion(c, s) {
    main.append(
      el("p", "Practice recorded", "tag"),
      el("h2", "Leave room for recall."),
      el(
        "p",
        `Your next question is due ${new Date(s.due).toLocaleString()}. Return without looking at the explanation first.`,
        "intro",
      ),
    );
    main.append(
      el(
        "p",
        `${s.self_checks} of ${s.criteria_count} writing criteria checked by you. ${s.self_checks < s.criteria_count ? "Unmet or uncertain criteria remain worth revising." : "A tutor can review your draft for evidence beyond this self-check."}`,
      ),
    );
    main.append(
      el(
        "p",
        "Completing this practice does not certify mastery. Review answers test a limited skill; later repetitions are not unseen assessments.",
        "meta",
      ),
    );
    const actions = el("div", undefined, "actions");
    const next = pack.concepts.find(
      (x) =>
        !["complete", "locked"].includes(
          core.status(pack, session, x.id, now()).stage,
        ),
    );
    actions.append(
      button(
        next ? "Continue to the next task" : "Back to your learning path",
        () => go(next?.id || null),
        "primary",
      ),
    );
    actions.append(
      button(
        "Revise my draft",
        () => {
          main.replaceChildren(
            el("p", c.title, "eyebrow"),
            el("h2", "Revise your response"),
          );
          writing(c, true);
        },
        "quiet",
      ),
    );
    main.append(actions);
    main.append(
      el("div", undefined, "rule"),
      el("h3", "Your saved draft"),
      el("p", last("write", c.id).text),
    );
  }
  function render() {
    main.replaceChildren();
    navigation();
    const c = pack.concepts.find((x) => x.id === selected);
    evidence(c);
    if (!c) {
      overview();
      return;
    }
    const s = core.status(pack, session, c.id, now());
    displayedStage = s.stage;
    main.append(
      el(
        "p",
        `${String(pack.concepts.indexOf(c) + 1).padStart(2, "0")} / ${String(pack.concepts.length).padStart(2, "0")} · ${s.stage.toUpperCase()}`,
        "eyebrow",
      ),
    );
    if (s.stage !== "complete") main.append(el("h2", c.title));
    if (["diagnostic", "practice", "transfer", "review"].includes(s.stage))
      question(c, s.stage);
    else if (s.stage === "lesson") worked(c);
    else if (s.stage === "writing") writing(c);
    else if (s.stage === "complete") completion(c, s);
    else main.append(el("p", "Complete the prerequisite practice first."));
  }
  document.querySelector(".wordmark").addEventListener("click", (e) => {
    e.preventDefault();
    go(null);
  });
  document.getElementById("export").addEventListener("click", () => {
    if (dirtyDraft) {
      tell(
        "Save your draft before exporting; unsaved text is not included.",
        true,
      );
      return;
    }
    download(`${pack.id}-progress.json`, JSON.stringify(session));
    tell(
      "Progress file prepared for download. It includes written exercises. Keep it private or remove text before sharing.",
    );
  });
  document.getElementById("import").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      if (file.size > core.MAX_IMPORT)
        throw new Error("Progress file exceeds 1 MB.");
      const candidate = core.importSession(
        pack,
        digest,
        await file.text(),
        now(),
      );
      if (
        !window.confirm(
          "Replace current tab progress with this imported record? Device saving will be turned off.",
        )
      )
        return;
      // Do not mutate a previously saved browser copy during import.
      session = candidate;
      saved = false;
      dirtyDraft = false;
      selected = null;
      storageUI();
      render();
      tell(
        "Imported into this tab. Device saving is off; any prior browser copy remains until you save or clear it.",
      );
    } catch (error) {
      tell(
        `Import rejected. ${error.message} Current progress is unchanged.`,
        true,
      );
    } finally {
      e.target.value = "";
    }
  });
  document.getElementById("clear").addEventListener("click", () => {
    if (
      !window.confirm(
        "Clear this topic’s progress from this tab and browser? Downloaded files, other topic versions, and backups will remain.",
      )
    )
      return;
    let removed = true;
    try {
      localStorage.removeItem(key);
    } catch (_) {
      removed = false;
    }
    session = core.createSession(pack, digest, now());
    saved = false;
    selected = null;
    dirtyDraft = false;
    storageUI();
    render();
    tell(
      removed
        ? "This topic’s tab and browser progress cleared. Other copies remain unchanged."
        : "Tab progress cleared. The browser copy could not be removed; use browser site-data controls. Downloaded files and backups remain.",
      !removed,
    );
  });
  window.addEventListener("beforeunload", (e) => {
    if (dirtyDraft || (!saved && session.events.length)) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
  try {
    const stored = localStorage.getItem(key);
    if (stored) {
      session = core.importSession(pack, digest, stored, now());
      saved = true;
    }
  } catch (error) {
    tell(
      `Saved progress could not be loaded: ${error.message} Start in this tab or import a valid export.`,
      true,
    );
  }
  storageUI();
  render();
})();
