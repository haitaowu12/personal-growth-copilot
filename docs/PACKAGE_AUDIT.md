# Package audit

Version: `0.5.0-alpha.1`

## Distribution contract

| Surface | Package evidence |
|---|---|
| Codex plugin identity | `plugins/personal-growth-copilot/.codex-plugin/plugin.json` |
| Repo marketplace | `.agents/plugins/marketplace.json` |
| Agent Skill entry point | `plugins/personal-growth-copilot/skills/personal-growth-copilot/SKILL.md` |
| UI prompt and invocation policy | `agents/openai.yaml`; implicit invocation is disabled |
| User installation workflow | `docs/INSTALLATION.md` |

## Skill completeness

The installable skill folder contains:

- one core instruction and workflow file;
- one host-facing prompt and invocation-policy file;
- task-routed knowledge, learning, and safety references;
- deterministic runtime helpers and the learning builder plus a pinned dependency manifest for
  context, records, validation, and safety state;
- portable record, session, evidence, safety, and learning assets.
- one source-grounded topic pack and offline player source, with a shared reducer
  tested in Node.js and strict Python schema/semantic validation.

The package has no required file outside its plugin folder. In particular, the
safety transition table and resource-resolver contract are bundled with the
skill rather than resolved from repository-only paths.

## Validation

The repository validation checks:

- plugin name, version, skill path, and absence of unbundled app, hook, or MCP
  declarations;
- marketplace source and install policy;
- explicit-only invocation metadata;
- every backtick-linked `references/`, `scripts/`, and `assets/` resource
  in `SKILL.md` and all reference files;
- version agreement across `VERSION`, plugin manifest, Python package, and
  release-status record;
- the existing privacy, consent, record, context, safety, evaluation, and
  fail-closed release controls.

Required checks:

```bash
.venv/bin/python /path/to/skill-creator/scripts/quick_validate.py \
  plugins/personal-growth-copilot/skills/personal-growth-copilot
.venv/bin/python /path/to/plugin-creator/scripts/validate_plugin.py \
  plugins/personal-growth-copilot
.venv/bin/python scripts/validate.py
.venv/bin/python -m unittest discover -s tests -v
```

These checks establish package structure and deterministic control behavior.
They do not establish therapeutic efficacy, production qualification, privacy
approval for a named host, or completion of the governed behavioral comparison.
Those gates remain explicitly blocked in `release/qualification.json`.
