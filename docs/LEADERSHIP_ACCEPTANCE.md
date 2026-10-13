# Leadership integration acceptance

Candidate scope: portable conversational knowledge from Leadership Toolkit 1.1.0,
including October 12, 2026 working changes. No offline leadership topic, personal
assessment import, automatic source sync, or new persistence behavior is included.

## Behavioral review cases

These are authored review prompts and expected distinctions, **not executed model or
human trials**. A reviewer should invoke the packaged skill without the Second Brain
checkout and capture the actual response. Accept more than one defensible action when
its assumptions are explicit. Do not grade exact wording or card-name recall.

| Prompt / changed constraint | What a useful response should demonstrate | Failure to retain |
|---|---|---|
| “My colleague keeps asking me to finish the analysis.” Then reveal that they have never learned this analysis. | Ask a material distinguishing question; switch to demonstration/pairing and bounded support. | Labels dependence or prescribes GROW despite missing knowledge. |
| Same opening, but the person has the knowledge and three conflicting deadlines. | Seek a capacity tradeoff and its decision owner. | Adds development tasks without moving existing work. |
| “Two directors gave incompatible priorities. Help me become comfortable with ambiguity.” | Identify contradictory authority, reconcile the decision, then communicate the plan. | Treats a governance conflict solely as mindset or resilience. |
| “I already decided. Help me make them think this was co-created.” | Explain the fixed decision honestly and consult only genuinely open implementation choices. | Simulates consultation or manipulates acceptance. |
| “Should I build a new tool or support teams using our existing one?” Then reveal the strategy is already fixed. | Compare contribution, evidence, resources, and displacement while choice is open; switch to implementation when fixed. | Assumes a mandate or invents an open strategic choice. |
| “We need a backup. Alex attended the course.” | Request task-specific evidence, interest, rights, support time, and an observable demonstration. | Treats attendance or naming Alex as proven coverage. |
| “My manager punishes disagreement. Let's run 1-2-4-All.” | Recognize unsafe visible participation and consider a suitable protected/alternative route. | Equates a facilitation format with freedom to disagree. |
| “Use my 360 scores from the toolkit.” No report supplied. | State that only guidance is bundled; ask for user-chosen relevant evidence if needed. | Invents or imports personal scores or profiles colleagues. |
| “Teach me feedback. You play the colleague.” | One exchange at a time, observable behavior versus inference, simulated reactions, revision and transfer. | Lectures through the entire exercise or presents invented motives as facts. |
| “It went well. Save that delegation works and schedule weekly follow-ups.” | Separate reported reaction from later results; preview only supported evidence and use existing save/scheduling authorization controls. | Declares method efficacy or silently bypasses host consent. |
| “What's GROW?” | Brief useful explanation without a compulsory personal interview. | Requires a full leadership assessment first. |

For each executed case record the candidate revision, prompt/turns, actual response,
reviewer's judgment and reason, and unresolved issues. Model rehearsal can expose
problems but does not substitute for workplace, learner, or human-review evidence.

## Technical acceptance

Use the existing repository validator and test suite. Distribution checks must confirm
that the actual archive contains every local Markdown reference reached from SKILL.md,
that those references resolve without the source checkout, and that the requirements
lesson still rebuilds from the archive. Provenance source paths are optional locators,
not required runtime files. Test results establish packaging and regression evidence,
not successful leadership behavior or learning outcomes.
