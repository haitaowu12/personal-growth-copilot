# Target provider adapters

`codex_cli_adapter.py` is an authored-target adapter, not a production runtime.
It invokes one fresh ephemeral Codex CLI turn with an empty declared tool set,
a no-tools prompt, and a read-only sandbox; it rejects the turn if the Codex
event stream records a command, MCP call, web search, or other non-message
item, contains a malformed line, or omits a provider thread ID. It loads the
exact committed governed system profile and bundle from the same bytes it hashes,
verifies and snapshots the exact inference executable and output schema before
use, and emits stdio-v3. This is evidence enforcement after the model turn, not
protection against a tool accessing readable host data before rejection. The adapter does
not prove the remote model's immutable backend identity, provide a network
sandbox, or make human labels independent.

Required runtime environment names:

- `PGC_EVAL_REPO_ROOT`: absolute, resolved clean exact checkout matching the
  target config;
- `PGC_CODEX_BIN`: absolute, resolved exact Codex CLI executable path;
- `PGC_CODEX_AUTH_ROOT`: absolute, resolved private Codex authentication root,
  passed only at execution and never written into config or evidence.

All three supplied paths must exist and may not themselves be symlinks. The
repository and authentication paths must be directories; `PGC_CODEX_BIN` must
be an executable regular file matching the exact runtime hash in the target
config.

Freeze `host=codex-cli`, a concrete model name, a declared model version, empty
tool permissions, and settings containing only `reasoning_effort`. Run this
adapter with dedicated evaluation credentials under the separately reviewed
restricted account/container required by `docs/TARGET_EXECUTION.md`; never point
it at a personal auth root on a host containing private data. The adapter
intentionally does not load case files
or embed case IDs, expected events, forbidden labels, branch predicates, or
rubric scores in the model prompt.

`codex_cli_review_adapter.py` is a separate development-only adapter for
system-blinded auxiliary review. It receives only a transcript, structured
observations, the rubric, and bounded event/hard-failure codebooks. It snapshots
the exact inference runtime and review-output schema, rejects tools and unknown
events, and returns a hash-bound review. Its output is marked non-qualifying and
cannot replace calibrated human reviewers, bilingual adjudication, or signed
reviewer attestations.

Both adapters permit a maximum 512 MiB inference executable. The bound is large
enough for the current standalone Codex runtime while remaining a bounded,
no-follow, exact-hash read rather than an unrestricted executable load.
