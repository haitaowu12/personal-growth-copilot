# Evidence and community research update

Date: 2026-08-13
Scope: intervention naming, outcome evidence, evaluation design, host
architecture, and claim limits

## Decision

Continue the explicit-use, non-clinical product, but rebalance development away
from release-protocol expansion. The next evidence must establish ordinary
session quality, delayed user outcomes, burden, dependence risk, and a real host
trust boundary.

## Conflicting AI-coaching outcome evidence

Two randomized studies point in different directions and use different
interventions, samples, and outcomes:

- A 2025 study with 32 participants reported a structured LLM coaching protocol
  comparable to human coaching on selected measured dimensions and better than
  generic GPT-4 conversation on some process criteria.
- A 2026 randomized comparison with 114 coachees reported substantial effects
  only for accredited human coaching across the study's goal, motivation,
  resilience, wellbeing, and related measures.

The studies do not license a pooled conclusion about this product. The smaller
study supports testing structured coaching processes against a generic model;
the later result strengthens the requirement for delayed user-outcome evidence
and blocks human-equivalence claims.

## Technique ontology

The Behaviour Change Technique Ontology supplies standardized identifiers for
active intervention content. The candidate registry uses ontology identifiers
to replace locally ambiguous labels and to support traceable evaluation. An
ontology mapping does not establish efficacy, user fit, or safety. Every entry
therefore includes eligibility, contraindication, burden, proximal signal,
disconfirmation, review window, and alternatives.

## Longitudinal design

Micro-randomized trials distinguish proximal effects from distal outcomes and
ask when an intervention component works. SCRIBE improves single-case reporting
completeness. PGC may borrow the distinctions and reporting fields for a
consented pilot. It must not covertly randomize support, withhold needed help,
or claim causality from a short uncontrolled case history.

## Governance

Current ICF materials add a 2025 ethics code and six-domain AI coaching
framework. NIST AI 600-1 adds a lifecycle risk-management profile. The new
crosswalk records implementation and evidence gaps; it does not claim
certification or professional credentialing.

## Community conclusions

### Direct coaching skill

The useful pattern from `koreyba/Claude-Skill-Developmental-Coach` is an
explicit-save session artifact. PGC independently implements a stricter capsule
that separates user wording, facts, hypotheses, alternatives, disconfirmers,
choice, optional experiment, review, and real host persistence status.
Automatic loading, developmental-stage inference, and mandatory Notion storage
are rejected.

### Evaluation infrastructure

Promptfoo is a mature candidate for generic provider matrices, declarative
red-team execution, CI integration, caching, and reports. PGC should not rebuild
those generic capabilities. Its domain-specific state transitions, human
review, English/Chinese checks, and hard gates remain authoritative.

### Memory and host architecture

Mem0, Letta, and Khoj provide signals for memory namespaces, stateful host
separation, self-hosting, and visible data sources. PGC retains stricter
confirm-each correction, supersession, review-due, no-hidden-retrieval, and
no-autonomous-action rules. Khoj remains architecture-only because of AGPL
licensing unless the owner makes a separate decision.

### Research prototype

Stanford GPTCoach demonstrates explicit separation among onboarding, health
data, backend tools, storage, and UI. Its physical-activity scope and mixed
licensing prevent direct prompt reuse or broad transfer claims.

## Required next evidence

1. Reproduce all checks on the exact candidate in a clean checkout.
2. Integrate the ordinary-growth suite and strong comparators into a frozen run
   plan without weakening existing hard gates.
3. Run target and comparator responses, preserve all attempts, and obtain
   calibrated English/Chinese human reviews.
4. Implement and adversarially test one named reference host.
5. Add independent untouched holdouts after candidate and judge freeze.
6. Pre-register process, proximal, delayed, burden, and dependence outcomes for
   a consented feasibility pilot.

No target-model, holdout, privacy-host, pilot, or efficacy claim is created by
this research update.
