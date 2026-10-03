const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const assets = path.join(__dirname, "../plugins/personal-growth-copilot/skills/personal-growth-copilot/assets/learning");
const core = require(path.join(assets, "core.js"));
const pack = require(path.join(assets, "requirements-writing.json"));
const digest = "a".repeat(64);
const key = `pgc-learning:${pack.id}:${digest}`;
const epoch = "2026-09-07T12:00:00.000Z";
const current = "2026-10-03T12:00:00.000Z";
let base = core.createSession(pack, digest, epoch);
for (const choice of ["a", "c"])
  base = core.dispatch(pack, base, {type: "answer", concept: "obligation", choice}, epoch);

function storage(initial = JSON.stringify(base)) {
  return {
    value: initial, failRead: false, failWrite: false, failRemove: false,
    getItem() { if (this.failRead) throw Error("read denied"); return this.value; },
    setItem(k, value) { if (this.failWrite) throw Error("quota denied"); this.value = value; },
    removeItem() { if (this.failRemove) throw Error("remove denied"); this.value = null; },
  };
}

// Run the actual complete player. This small DOM stub checks handler/state
// behavior, not browser rendering, focus containment, or accessibility.
function player(localStorage) {
  const nodes = [], ids = new Map(), windowHandlers = new Map(), downloads = [], blobs = new Map();
  let modalFailure = false;
  class Element {
    constructor(tag) {
      this.tag = tag; this.children = []; this.listeners = new Map();
      this.textContent = ""; this.className = ""; this.isConnected = true;
      this.returnValue = ""; this.value = ""; nodes.push(this);
    }
    set id(value) { this._id = value; ids.set(value, this); }
    get id() { return this._id; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    setAttribute() {}
    addEventListener(type, callback) { this.listeners.set(type, callback); }
    fire(type, extra = {}) { return this.listeners.get(type)?.({target: this, ...extra}); }
    focus() { document.activeElement = this; }
    remove() { this.isConnected = false; }
    showModal() { if (modalFailure) throw Error("modal unavailable"); }
    close(value = "") { this.returnValue = value; this.fire("close"); }
    click() {
      if (this.tag === "a") downloads.push({name: this.download, blob: blobs.get(this.href)});
      else return this.fire("click");
    }
  }
  const document = {
    activeElement: null,
    createElement: tag => new Element(tag),
    createTextNode: text => ({textContent: text}),
    getElementById: id => ids.get(id),
    querySelector: () => ids.get("wordmark"),
  };
  document.body = new Element("body");
  for (const id of ["topic-data", "workspace", "navigation", "context", "notice", "storage", "export", "import", "clear", "wordmark"]) {
    const node = new Element("div"); node.id = id;
  }
  ids.get("topic-data").textContent = JSON.stringify({pack, digest});
  document.activeElement = ids.get("wordmark");
  const window = {LearningCore: core, addEventListener: (type, fn) => windowHandlers.set(type, fn)};
  class Clock extends Date { constructor(value) { super(arguments.length ? value : current); } }
  const context = vm.createContext({document, window, localStorage, Date: Clock, Blob,
    URL: {
      createObjectURL(blob) { const url = `blob:test-${blobs.size}`; blobs.set(url, blob); return url; },
      revokeObjectURL() {},
    },
    setTimeout() {},
  });
  const source = fs.readFileSync(path.join(assets, "player.js"), "utf8");
  assert.ok(source.endsWith("})();\n"));
  // Expose closure state/functions only in this test context; no duplicated logic.
  const instrumented = source.slice(0, -6) + `
    globalThis.inspectPlayer = {
      act, tell, writing, confirmAction,
      state: () => ({session, saved, dirtyDraft, storageSnapshot, storageWarning, confirmationOpen})
    };
  })();\n`;
  vm.runInContext(instrumented, context);
  const api = context.inspectPlayer;
  return {
    api, ids, nodes, downloads,
    notice: () => ids.get("notice"),
    toggle(checked) {
      const input = ids.get("storage").children[0].children[0];
      input.checked = checked; return input.fire("change");
    },
    event(type, event) { return windowHandlers.get(type)(event); },
    write(text) { return api.act({type: "write", concept: "obligation", text}); },
    async clear() {
      const pending = ids.get("clear").fire("click");
      nodes.findLast(n => n.tag === "dialog" && n.isConnected).close("accept");
      await pending;
    },
    failModal(value) { modalFailure = value; },
  };
}

test("actual draft save keeps storage failure visible through the routine success notice, and explicit retry resolves it", () => {
  const store = storage(), tab = player(store);
  tab.api.writing(pack.concepts[0]);
  const draft = tab.ids.get("draft");
  draft.value = "The booking service shall save this synthetic learner response.";
  draft.fire("input");
  store.failWrite = true;
  tab.nodes.findLast(n => n.textContent === "Save draft & self-review").fire("click");
  assert.equal(tab.api.state().saved, false);
  assert.equal(tab.api.state().dirtyDraft, false);
  assert.match(tab.notice().textContent, /Saving failed/);
  assert.match(tab.notice().textContent, /Draft retained in this tab/);
  assert.equal(tab.notice().className, "error");
  tab.api.tell("Another routine notice.");
  assert.match(tab.notice().textContent, /Saving failed/);
  let warned = false;
  tab.event("beforeunload", {preventDefault() { warned = true; }});
  assert.equal(warned, true);
  store.failWrite = false;
  tab.toggle(true);
  assert.equal(tab.api.state().saved, true);
  assert.equal(tab.api.state().storageWarning, null);
  assert.equal(tab.notice().className, "");
  assert.equal(JSON.parse(store.value).events.at(-1).text, draft.value);
});

test("a stale tab cannot overwrite newer bytes even before receiving a storage event or by re-enabling saving", () => {
  const store = storage(), a = player(store), b = player(store);
  a.write("The booking service shall retain the distinct response from A.");
  const newer = store.value;
  b.write("The booking service shall retain the distinct response from B.");
  assert.equal(store.value, newer);
  assert.equal(b.api.state().saved, false);
  assert.match(b.api.state().session.events.at(-1).text, /from B/);
  assert.match(b.notice().textContent, /No browser copy was overwritten/);
  b.toggle(true);
  assert.equal(store.value, newer);
  assert.equal(b.api.state().saved, false);
});

test("storage events disable saving without discarding local work, and a clear cannot be silently restored", () => {
  const store = storage(), a = player(store), b = player(store);
  a.write("The booking service shall retain the newer response from A.");
  b.event("storage", {key, storageArea: store});
  assert.equal(b.api.state().saved, false);
  assert.equal(b.api.state().session.events.length, base.events.length);
  b.api.tell("Routine feedback.");
  assert.match(b.notice().textContent, /changed in another tab/);
  store.removeItem(key);
  a.event("storage", {key: null, storageArea: store});
  a.write("A stale open tab still retains this later response in memory.");
  assert.equal(store.value, null);
  assert.equal(a.api.state().saved, false);
  a.toggle(true);
  assert.equal(store.value, null);
});

test("exact-byte comparison detects a removed browser copy even when its storage event was missed", () => {
  const store = storage(), tab = player(store);
  store.removeItem(key);
  tab.write("The booking service shall retain this response only in the tab.");
  assert.equal(store.value, null);
  assert.equal(tab.api.state().saved, false);
});

test("comparison uses exact saved bytes, including semantically equivalent replacements", () => {
  const store = storage(), tab = player(store);
  const replacement = JSON.stringify(base, null, 2);
  store.value = replacement;
  tab.write("The booking service shall retain this response only in the tab.");
  assert.equal(store.value, replacement);
  assert.equal(tab.api.state().saved, false);
});

test("explicit saving can create the first browser copy when the known snapshot is empty", () => {
  const store = storage(null), tab = player(store);
  assert.equal(tab.api.state().saved, false);
  tab.toggle(true);
  assert.equal(tab.api.state().saved, true);
  assert.equal(JSON.parse(store.value).pack_digest, digest);
  assert.equal(tab.api.state().storageWarning, null);
});

test("opt-out preserves a changed browser copy and always turns saving off", () => {
  const store = storage(), a = player(store), b = player(store);
  a.write("The booking service shall retain the current response from A.");
  const newer = store.value;
  b.toggle(false);
  assert.equal(store.value, newer);
  assert.equal(b.api.state().saved, false);
  assert.match(b.notice().textContent, /browser copy was retained/);
  a.toggle(false);
  assert.equal(store.value, null);
  assert.equal(a.api.state().storageWarning, null);
});

test("explicit clear resets local progress but retains changed browser bytes and explains the partial clear", async () => {
  const store = storage(), a = player(store), b = player(store);
  a.write("The booking service shall retain the current response from A.");
  const newer = store.value;
  await b.clear();
  assert.equal(store.value, newer);
  assert.equal(b.api.state().session.events.length, 0);
  assert.equal(b.api.state().saved, false);
  assert.match(b.notice().textContent, /Tab progress cleared/);
  assert.match(b.notice().textContent, /browser copy was retained/);
  b.api.tell("Routine feedback.");
  assert.match(b.notice().textContent, /browser copy was retained/);
  await a.clear();
  assert.equal(store.value, null);
  assert.equal(a.api.state().storageWarning, null);
});

test("failed removal stays visible until an explicit successful clear", async () => {
  const store = storage(), tab = player(store), original = store.value;
  store.failRemove = true;
  tab.toggle(false);
  assert.equal(store.value, original);
  assert.equal(tab.api.state().saved, false);
  tab.api.tell("Routine feedback.");
  assert.match(tab.notice().textContent, /could not be removed/);
  store.failRemove = false;
  await tab.clear();
  assert.equal(store.value, null);
  assert.equal(tab.api.state().storageWarning, null);
});

test("unknown initial storage bytes cannot be overwritten or deleted after a read failure", async () => {
  const store = storage(), original = store.value;
  store.failRead = true;
  const tab = player(store);
  store.failRead = false;
  tab.toggle(true);
  assert.equal(store.value, original);
  assert.equal(tab.api.state().saved, false);
  await tab.clear();
  assert.equal(store.value, original);
  assert.match(tab.notice().textContent, /unverified browser copy was retained/);
});

test("unrelated storage and queued old events do not disable a current saved copy", () => {
  const store = storage(), tab = player(store);
  tab.event("storage", {key: "another-key", storageArea: store});
  tab.event("storage", {key, storageArea: {}});
  tab.event("storage", {key, storageArea: store, newValue: "old queued bytes"});
  assert.equal(tab.api.state().saved, true);
  assert.equal(tab.api.state().storageWarning, null);
});

test("a modal setup failure cancels safely and allows the next confirmation", async () => {
  const tab = player(storage());
  tab.failModal(true);
  assert.equal(await tab.api.confirmAction("Title", "Message", "Accept"), false);
  assert.equal(tab.api.state().confirmationOpen, false);
  assert.match(tab.notice().textContent, /could not open the confirmation/);
  tab.failModal(false);
  const next = tab.api.confirmAction("Title", "Message", "Accept");
  tab.nodes.findLast(n => n.tag === "dialog" && n.isConnected).close("accept");
  assert.equal(await next, true);
});

test("at the event cap, the actual player separately exports recorded history and unsaved draft recovery without losing either", async () => {
  const capped = {...base, events: [...base.events,
    ...Array.from({length: 1998}, () => ({type: "study", concept: "obligation", at: epoch}))]};
  const recorded = JSON.stringify(capped), store = storage(recorded), tab = player(store);
  assert.equal(tab.api.state().session.events.length, 2000);
  tab.api.writing(pack.concepts[0]);
  const recovery = tab.nodes.findLast(n => n.textContent === "Download unsaved draft");
  assert.equal(recovery.disabled, true);
  const draft = tab.ids.get("draft");
  draft.value = "The booking service shall retain this unsaved boundary-case response.";
  draft.fire("input");
  tab.nodes.findLast(n => n.textContent === "Save draft & self-review").fire("click");
  assert.equal(tab.api.state().dirtyDraft, true);
  assert.match(tab.notice().textContent, /Progress limit reached/);
  assert.equal(recovery.disabled, false);
  tab.ids.get("export").fire("click");
  assert.match(tab.notice().textContent, /unsaved draft is not included and remains in this tab/);
  recovery.fire("click");
  assert.equal(tab.downloads.length, 2);
  const history = await tab.downloads[0].blob.text();
  assert.equal(history, recorded);
  assert.equal(core.importSession(pack, digest, history, current).events.length, 2000);
  const rescueBytes = await tab.downloads[1].blob.text(), rescue = JSON.parse(rescueBytes);
  assert.equal(rescue.type, "draft-recovery");
  assert.equal(rescue.text, draft.value);
  assert.match(rescue.notice, /not a replayable progress file/);
  assert.throws(() => core.importSession(pack, digest, rescueBytes, current));
  assert.equal(tab.api.state().dirtyDraft, true);
  assert.equal(tab.api.state().session.events.length, 2000);
  assert.equal(store.value, recorded);
  assert.match(tab.notice().textContent, /draft remains unsaved/);
});

function pendingImport(tab, record) {
  const bytes = JSON.stringify(record);
  let release;
  const reading = new Promise(resolve => { release = () => resolve(bytes); });
  const input = tab.ids.get("import");
  input.files = [{size: Buffer.byteLength(bytes), text: () => reading}];
  return {release, result: input.fire("change")};
}
function lastDialog(tab) {
  return tab.nodes.findLast(n => n.tag === "dialog" && n.isConnected);
}

test("editing during an import read is not discarded before fresh confirmation, and cancel retains the draft", async () => {
  const store = storage(), tab = player(store), before = JSON.stringify(tab.api.state().session);
  const incoming = pendingImport(tab, base);
  tab.api.writing(pack.concepts[0]);
  const draft = tab.ids.get("draft");
  draft.value = "The learner wrote this while the selected file was still being read.";
  draft.fire("input");
  incoming.release();
  await new Promise(setImmediate);
  assert.equal(tab.api.state().dirtyDraft, true);
  assert.equal(JSON.stringify(tab.api.state().session), before);
  assert.ok(lastDialog(tab).children.some(n => /including unsaved text/.test(n.textContent)));
  lastDialog(tab).close("cancel");
  await incoming.result;
  assert.equal(tab.api.state().dirtyDraft, true);
  assert.match(draft.value, /while the selected file/);
  assert.equal(JSON.stringify(tab.api.state().session), before);
  assert.equal(store.value, before);
});

test("clear during an import read remains cleared unless a new replacement is explicitly accepted", async () => {
  const store = storage(), tab = player(store);
  const incoming = pendingImport(tab, base);
  await tab.clear();
  assert.equal(tab.api.state().session.events.length, 0);
  incoming.release();
  await new Promise(setImmediate);
  assert.equal(tab.api.state().session.events.length, 0);
  assert.equal(store.value, null);
  lastDialog(tab).close("cancel");
  await incoming.result;
  assert.equal(tab.api.state().session.events.length, 0);
  assert.equal(store.value, null);
});

test("out-of-order import reads cannot silently replace an already accepted newer import", async () => {
  const store = storage(), tab = player(store), browserBefore = store.value;
  const older = core.dispatch(pack, base, {type: "write", concept: "obligation", text: "An older selected record with a distinct synthetic response."}, epoch);
  const newer = core.dispatch(pack, base, {type: "write", concept: "obligation", text: "A newer selected record with another synthetic response."}, epoch);
  const a = pendingImport(tab, older), b = pendingImport(tab, newer);
  b.release();
  await new Promise(setImmediate);
  lastDialog(tab).close("accept");
  await b.result;
  assert.equal(JSON.stringify(tab.api.state().session), JSON.stringify(newer));
  a.release();
  await new Promise(setImmediate);
  assert.equal(JSON.stringify(tab.api.state().session), JSON.stringify(newer));
  lastDialog(tab).close("cancel");
  await a.result;
  assert.equal(JSON.stringify(tab.api.state().session), JSON.stringify(newer));
  assert.equal(store.value, browserBefore);
  assert.equal(tab.api.state().saved, false);
});
