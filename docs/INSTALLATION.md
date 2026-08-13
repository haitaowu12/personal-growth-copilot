# Installation

Personal Growth Copilot is distributed as a versioned Codex plugin through this
repository's marketplace. The plugin contains one explicit-invocation Agent
Skill and requires no MCP server, account, credential, or network service.

## Install as a Codex plugin

Pin the published alpha while the behavioral qualification gates remain open:

```bash
codex plugin marketplace add haitaowu12/personal-growth-copilot --ref v0.4.0-alpha.12
codex plugin add personal-growth-copilot@personal
```

Start a new Codex task after installation. Invoke the skill explicitly:

```text
Use $personal-growth-copilot to help me understand a recurring pattern and
choose one small experiment for the next week.
```

Confirm discovery with:

```bash
codex plugin list --marketplace personal
```

## Install only the Agent Skill

Ask Codex's built-in skill installer to install the tagged skill folder:

```text
Use $skill-installer to install personal-growth-copilot from
https://github.com/haitaowu12/personal-growth-copilot at ref
v0.4.0-alpha.12, path
plugins/personal-growth-copilot/skills/personal-growth-copilot.
```

A SKILL.md-compatible host can import the same folder without the marketplace.
Keep the complete folder together; `SKILL.md` depends on its adjacent
`agents/`, `references/`, `scripts/`, and `assets/` resources.

## Update

```bash
codex plugin marketplace upgrade personal
codex plugin add personal-growth-copilot@personal
```

Start a new task after updating so the host loads the new skill version.

## Runtime and privacy boundary

- Conversational use requires only the installed skill.
- Deterministic record, context, and safety helpers require Python 3.11 or
  later plus the pinned packages in the skill's `scripts/requirements.txt`
  when a host chooses to run them.
- Persistence is off unless the user explicitly requests a save and the host
  implements the preview-token-commit contract.
- The plugin bundles no MCP server, hooks, telemetry client, credentials, or
  background process.
- This is a research alpha. It is not therapy, crisis care, or professional
  medical, legal, clinical, employment, safeguarding, or financial advice.

## Repository layout

```text
.agents/plugins/marketplace.json
plugins/personal-growth-copilot/
├── .codex-plugin/plugin.json
└── skills/personal-growth-copilot/
    ├── SKILL.md
    ├── agents/openai.yaml
    ├── references/
    ├── scripts/
    └── assets/
```
