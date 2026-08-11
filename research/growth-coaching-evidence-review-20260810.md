# Evidence review: conversational personal-growth copilot

Date: 2026-08-10

## Decision

Build a coaching-shaped conversational inquiry system, not an AI therapist.
The strongest transferable evidence supports collaboration, autonomy, clear
goals, user-owned plans, small behavioral techniques, progress review, and a
quality working agreement. None establishes that a general LLM can safely
diagnose, treat, or replace a qualified professional.

## What the evidence changes in the product

1. **Contract before depth.** Agree on the desired outcome and whether the user
   wants exploration, advice, practice, or review. Working-alliance evidence is
   about goal and task agreement as well as relationship quality; the product
   operationalizes the first two without anthropomorphizing the third.
2. **Reflect before another question.** MINT and SAMHSA guidance support
   reflection, open questions, summaries, and permission before advice. The
   skill uses those conversational practices but does not claim to deliver MI.
3. **One material question at a time.** This is a usability and anti-
   interrogation hypothesis informed by strong community convergence. It must
   be tested behaviorally rather than misrepresented as a clinical fact.
4. **Make the model visible.** Separate reports, observations, hypotheses,
   alternatives, unknowns, and corrections. This is a product integrity rule,
   not a psychological assessment.
5. **Fit techniques to barriers.** Goal clarity, if-then planning, mental
   contrasting, prompts, monitoring, environmental changes, and support are
   options. A taxonomy is not an efficacy ranking.
6. **Review for learning.** Compare intent and outcome, identify causes without
   blame, update the hypothesis, and change the next experiment.
7. **Protect autonomy and real-world connection.** Avoid pressure, shame,
   exclusivity, constant-availability language, or conversation-length goals.
8. **Keep clinical scope out.** AI wellness guidance and current LLM safety
   studies support explicit boundaries, dedicated crisis cases, minimal data,
   and qualified-human routing.
9. **Make consent and correction interactive controls.** The ICF AI coaching
   framework calls for explicit data-processing consent, client review and
   modification, understandable question context, and security/privacy
   controls. This supports the host-attested consent and correctable-record
   architecture, but it is professional guidance rather than efficacy proof.

## Thin or mixed evidence

- **AI life-coaching efficacy:** emerging studies do not yet establish broad,
  durable, independent effectiveness across personal-growth domains.
- **Socratic questioning as a universal sequence:** useful as collaborative
  inquiry, but clinical techniques should not be imported as a treatment
  protocol.
- **Emotion detection and stage-of-change inference:** model-generated states
  are fallible. The runtime may reflect user-reported emotion or readiness; it
  must not silently score them from language style.
- **Long-term memory:** continuity can improve relevance, but sensitive records
  create privacy, injection, misremembering, and self-sealing-profile risks.
- **Habit timelines:** formation varies widely. Any fixed day-count promise is
  unsupported.
- **Personality or wellness scores:** transparent user-supplied check-ins can be
  useful within person and context. Diagnostic or normative scores require
  validated instruments, authorized use, appropriate administration, and
  qualified interpretation outside this product's scope.
- **AI-coaching standards:** current professional frameworks contain useful
  governance requirements and aspirational capabilities. They are not evidence
  that an LLM understands context, measures growth validly, or produces durable
  benefit.

## Release implications

The new knowledge base can pass source and structural checks. Release remains
blocked until model outputs are run against the behavioral suite, scored by
calibrated reviewers, compared with the prior candidate where possible, tested
on untouched holdouts, and piloted under explicit consent and privacy controls.

Full citations, URLs, runtime uses, and limitations are machine-readable in
`provenance/evidence-sources.json`.
