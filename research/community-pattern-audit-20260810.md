# Community pattern audit

Date: 2026-08-10

Method: repository metadata and text/code were inspected read-only at pinned
commits. No donor code, prompt block, questionnaire, scoring formula, or prose
was copied. Repositories without permissive licenses were idea-only evidence.
Community convergence is a design signal, not scientific validation.

## Repositories reviewed

| Repository | Pinned commit | License at review | Useful signal | Decision |
|---|---|---|---|---|
| [luhayden-blip/ai-life-coach](https://github.com/luhayden-blip/ai-life-coach) | `aa4d983d0ec8deead816c1bfa604bcd84195378c` | MIT | One-question Socratic rhythm, session modes, reflection before another question | Adapt the rhythm; reject implicit activation, forced age collection, hidden emotion scoring, therapy-shaped depth, fixed national hotlines, and giant final reports. |
| [AAAlenwow/lovemyself-skill](https://github.com/AAAlenwow/lovemyself-skill) | `c719e5e79852708f3e72833aad60c5b9cf31d2d8` | MIT | Traceable behavioral observations, user-correctable framing, privacy reminder | Adapt traceability; reject pseudo-validated scenario cards, forced tone menus, personality inference, and categorical minor exclusion. |
| [huyhungai/life-rpg-obsidian](https://github.com/huyhungai/life-rpg-obsidian) | `46c5902e3f774b590449f486537edbaf2199fc98` | MIT | Multiple life domains and longitudinal review | Use domain prompts only when relevant; reject RPG pressure, universal dashboards, point maximization, and shame-prone streaks. |
| [TravorShelby/daily-progress](https://github.com/TravorShelby/daily-progress) | `99c1b20b534ca4253d5ee41e93c7eece228aedb2` | CC BY-NC 4.0 | Pure tool-loop seams, injected time/storage/model, event visibility, undo concept | Idea-only. Keep deterministic seams and visible actions; reject AI-decided silent writes and arbitrary progress points. |
| [sukoji/persode](https://github.com/sukoji/persode) | `8fe78979f54cb9dba2f131196b8f425f0271fc47` | MIT | Honest mechanism evaluation, deterministic offline tests, disclosed negative results | Adopt the honesty/test pattern; reject emotion-salience retrieval, forgetting formulas, hidden intensity inference, and visual-journal expansion. |
| [shaoyang01/work-journal-agent](https://github.com/shaoyang01/work-journal-agent) | `08cb45d6e4f24522056057995ff57123c8846e54` | MIT | Typed events, local SQLite tests, explicit sources | Adapt schema discipline and deterministic validation; do not ingest work traces or infer personal growth automatically. |
| [cryptoriot666/echojournal](https://github.com/cryptoriot666/echojournal) | `05ed346ae9d18ead355066e673b7b4d622d9474f` | MIT | Reflection plus continuity in a journaling interface | Keep compact reflective continuity; reject raw-journal retention and unrestricted autobiographical memory. |
| [doublew6/riji-agent](https://github.com/doublew6/riji-agent) | `0397d81b107dcb0701e20a1e54ebcfe2e164cb69` | MIT | Precise local/cloud egress boundary, private flags, source IDs, capped retrieval, tests | Adopt explicit egress and provenance concepts; no default cloud retrieval or invisible personal-note access. |
| [beckspark/chiron](https://github.com/beckspark/chiron) | `a3cf82467e8a4c2dd75ba21e21c26f2c9dab2e52` | no root license found | MI-shaped stages, short specific replies, rubrics, scripted multi-turn evaluation, hard crisis route | Idea-only. Adapt evaluation dimensions and bounded response style; reject clinical case notes, silent stage inference, hidden reasoning persistence, and keyword-only safety claims. |
| [dadler6/pilot-tests-mi-chatbot](https://github.com/dadler6/pilot-tests-mi-chatbot) | `a715a24e8e86d68555a90adae4dc5aaf5aa6aceb` | no root license found | Independent harm/quality/sensing test categories | Idea-only. Expand adversarial and sensing cases; do not reuse binary fixtures or unlicensed material. |
| [occupyashanti/AI-life-coach](https://github.com/occupyashanti/AI-life-coach) | `3acacd695c2d8b9fc8d0b98a1cbf5d940fb78ec0` | no root license found | Basic goals, tracking, and conversational UI | No distinctive method adopted; basic patterns already supported by stronger primary evidence. |
| [smilior/ai-life-coach](https://github.com/smilior/ai-life-coach) | `d4cec4a240933ddc677430b8b06020747529f991` | no root license found | Solution-oriented chat sessions and small steps | Idea-only. Small experiments retained; no donor wording, code, or therapy protocol used. |

## Convergent patterns adopted

1. One primary question per turn, with a reflection before topic change.
2. Explicit modes for quick advice, dialogue, deeper context, and review.
3. A visible, revisable model built from traceable user evidence.
4. Separate current context, experiment, observation, and retained learning.
5. Local-first continuity with explicit consent, write previews, correction,
   export, and deletion semantics.
6. Short, situation-specific responses rather than generic encouragement.
7. Scripted multi-turn evaluation for flow, specificity, autonomy, model
   correction, action fit, safety, and dependence risks.
8. Deterministic code for structure and persistence; model judgment for
   language and hypotheses, never for silent irreversible writes.

## Patterns rejected

- automatic or broad emotional activation;
- AI-therapist identity, clinical case notes, diagnosis, or treatment claims;
- forced intimate disclosure, trauma excavation, or “deep” questioning as a
  default;
- hidden readiness, emotion, personality, attachment, or pathology scores;
- unvalidated quizzes presented as scientific measurement;
- AI-decided storage, invisible dossiers, raw journal ingestion, or third-party
  profiling;
- emotion-weighted memory resurfacing and self-reinforcing identity models;
- streak pressure, moralized scores, forced positivity, or gamified shame;
- fixed universal crisis resources without location/currentness checks;
- advice refusal when the user directly asks for an answer;
- engagement-maximizing language or substitution for human relationships.

## Clean-room conclusion

The strongest community contribution is workflow architecture and evaluation
discipline, not a ready-made psychological knowledge base. Runtime methods are
therefore grounded in primary evidence and official guidance. Community repos
inform interface and failure-mode design only.
