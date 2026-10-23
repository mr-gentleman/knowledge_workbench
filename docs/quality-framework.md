# Quality framework and scorecard

Requested by #chris; authored by #codex, 2026-10-23.
The three goals and evidence tracks reflect Chris's direction. The grading and
rollup rules below are proposed operating defaults, ready for review.
This is a quality view, not a second backlog. Actions belong in features.md.

## Stable goals

| Domain | Goal | Judge against |
|---|---|---|
| Engineering | Reliable, lean, modular software that is easy to maintain, update, and scale for realistic demand. | Correctness and data integrity; ease of a representative change; clear ownership of rules; proportionate complexity/dependencies; measured performance and capacity. Reuse AGENTS.md's seven checks. |
| UX | A dream to use: understandable, responsive, satisfying, and inviting to discovery and contribution. | Can users find, understand, edit, recover, and know what happened with little friction? Include pleasure and visual coherence, not just task completion. |
| Product / features | Solve the critical workflows exceptionally well, with a small, coherent feature set. | Importance of the user problem; end-to-end usefulness; adoption/value; benefit relative to cognitive and maintenance cost. A rare high-value extra can earn its place. Cheap implementation alone cannot. |

Keep these goals stable across iterations. Change a goal or acceptance bar explicitly
with Chris and record why; never lower it to make a grade improve. Scope can evolve.
Scale means meeting a stated, plausible workload and having a practical upgrade path,
not building infrastructure for hypothetical millions of users.

## Two independent dimensions: quality and evidence

Use three evidence columns for every assessed unit. They are complementary, not
three scores to average.

| Track | Question | Evidence |
|---|---|---|
| P — Predictive | Based on inspection and controlled checks, should this work well? | AI/expert rubric review, source reading, automated tests, benchmarks. Say which actually ran; a mock test establishes only what it models. |
| W — Workshop | Can we demonstrate the intended outcome with Chris in the loop? | Realistic task walkthrough, observed hesitation/errors, completion time, satisfaction, failure/recovery drills. Engineering can demonstrate a representative code change or rollback; product can test whether a feature earns its complexity. |
| L — Live | Does it deliver under real use by intended users? | User feedback, task outcomes, repeat use, errors, latency, support burden, incidents, and actual maintenance experience. A developer smoke test on a deployed app is not evidence of adoption. |

A unit may be P:Green, W:Yellow, L:Not assessed. That is useful information, not
a contradiction to hide. A live failure overrides an optimistic prediction for
the behavior it actually tests. Logs alone cannot establish that users enjoy the
app; a happy workshop cannot establish transaction safety or broad adoption.

Evidence maturity is shown by which columns have current evidence. Never treat
a mature but failing feature as high quality, or an untested feature as bad.

## One grading vocabulary

Use the existing engineering colors across all three domains:

| Grade | Meaning |
|---|---|
| Green — meets the bar | Relevant agreed checks pass; no known material gap within the stated scope. |
| Yellow — needs improvement | Useful, but a specific friction, weakness, or uncertainty needs a bounded improvement. |
| Red — fails the bar | A critical outcome fails, a material integrity/reliability risk exists, or the feature's cost is unjustified by its value. |
| Not assessed | No adequate current evidence for this track. Missing evidence is not Green or Red. |

An uncertainty with no assessment is Not assessed; an observed weakness with
uncertain extent can be Yellow. State the distinction.
Do not add 0–100 scores, decimal precision, or another maturity ladder initially.
Green is a maintained standard, not permission to add polish indefinitely.

Each grade must name the outcome, evidence (date, revision/environment, sample),
and reason. Workshop/live evidence includes who or which cohort, number of attempts,
and observation window. Note gaps and material changes that make evidence stale.
Retain old evidence in history; do not silently carry it onto changed behavior.

## Bottom-up assessment, three overall grades

Start with roughly 3–5 meaningful units per domain. Split only when it helps isolate
a decision or owner. No requirement to grade every file, widget, or function.

- Engineering units: persistence/history; SQL execution; frontend state; deployment
  and operability. Map each to concrete modules/files, without rewarding file count.
- UX units: find and open; understand a metric; edit and save; run SQL and interpret
  feedback; recover from a conflict. A component can have its own row if it is a
  recurring source of friction across journeys.
- Product units: discovery; coherent authoring; trust/promotion. Grade whether each
  capability belongs and solves its problem, not whether it has many subfeatures.

The same capability can appear in all domains, with different questions.
Correctly implemented functionality can still be unpleasant or unnecessary.

For each domain, agree which units are **core** for the current milestone before
scoring. Optional units remain visible but cannot inflate the grade.

**Rollup rule, applied separately to P, W, and L:**
1. Any core Red → domain Red.
2. Otherwise any core Yellow → domain Yellow.
3. All core units Green with current evidence → domain Green.
4. Otherwise → Not assessed / incomplete, showing assessed coverage and known grades.
   Missing core assessments never permit an overall Green.

Always show coverage (e.g. 3/4 core units assessed) and the limiting unit.
This is a conservative bottleneck rollup, not an average. Ten polished controls
cannot cancel out a broken save. Peripheral weaknesses stay in the detail and
do not automatically block a milestone; explain any material exception.

The headline is three grades: Engineering, UX, Product. Each headline names its
evidence track and scope; the adjacent P/W/L cells preserve the full picture.
Use the track relevant to the claim: pre-release forecast = P, demonstrated
experience = W, field performance = L. Do not silently switch tracks between
reviews or label a workshop grade as live success. A known material failure in
another track must be visible beside the headline.

## Lean scorecard

Maintain this section at meaningful checkpoints. These initial rows are ungraded:
creating this framework is not an assessment of the current app.
Before the first review, agree the small core-unit list and its acceptance checks.

### Overall

Assessment date: not yet assessed. Revision/environment: not yet selected.
Milestone and headline evidence track: to be selected.

| Domain | Headline | P | W | L | Core coverage P/W/L | Limiting unit / next evidence | Trend |
|---|---|---|---|---|---|---|---|
| Engineering | Not assessed | Not assessed | Not assessed | Not assessed | — | Establish baseline | — |
| UX | Not assessed | Not assessed | Not assessed | Not assessed | — | Establish baseline | — |
| Product | Not assessed | Not assessed | Not assessed | Not assessed | — | Establish baseline | — |

### Unit rows — copy only as needed

| Domain / unit / core? | Outcome and acceptance bar | P | W | L | Evidence links + date/revision/sample | Smallest next action / backlog ID |
|---|---|---|---|---|---|---|
| Example only: UX / edit and save / core | User saves definition + SQL, recognizes success, and retains work on failure | Not assessed | Not assessed | Not assessed | No assessment performed | Define walkthrough |

For a hypothetical result: P Green, W Yellow, L Not assessed could mean tests pass,
but Chris cannot find the save confirmation. The UX workshop rollup is Yellow;
the next action addresses that feedback, not more tests of already-proven behavior.

## Measurement without a telemetry project

Pick one or two useful signals per unit; add more only for a concrete decision.

| Domain | Starting signals |
|---|---|
| Engineering | Failed saves / save attempts (separate handled conflicts from system errors); p95 save latency with sample size; integrity incidents; effort and regressions from a representative maintenance change. |
| UX | Unassisted completion / attempts; time and hesitation on a named task; recovery success; a short “clear and pleasant?” rating with the user's reason. |
| Product | Successful useful tasks; repeat use among users who have a reason to return; contribution/discovery outcomes; features unused or bypassed and why. |

Set acceptance thresholds before judging results, using current needs and a baseline.
Record numerator/denominator, workload, and time window. Low-volume internal use
often calls for raw counts and interviews, not impressive-looking percentages.
No errors in two attempts is limited evidence. Visits/clicks alone are not value,
and fewer clicks alone is not better UX. Actual SME use counts as live evidence;
the app does not need to be public on the internet.

## Improvement loop and ownership

1. Choose a core unit and stable outcome; agree a small acceptance bar.
2. Assess with the available evidence and expose what remains unknown.
3. Select the highest-impact gap: correctness first, then blocked core work,
   then frequent friction or compelling product value.
4. Make the smallest coherent improvement, or remove an unjustified feature.
5. Repeat the relevant check; update the unit and domain rollup.
6. Record trend as improving / flat / regressing / not comparable, with the actual
   outcome change. More evidence is progress in confidence, not automatically quality.

Keep a short dated snapshot of the overall table and changed unit grades here at
milestone reviews, linking detailed evidence elsewhere. Compare the same tasks,
criteria, and cohorts; mark comparisons invalid when scope or workload changed.
No per-commit grading ceremony. Reassess touched units after meaningful changes,
after workshops, and at milestone/live-use reviews. A 10–15 minute routine update
should suffice; evidence collection itself may take longer.

AI proposes predictive grades and targeted checks; Chris supplies workshop judgment
and decides scope/tradeoffs; live users and operational evidence test the claims.
Review independence should match risk under the existing engineering rules.
Do not ask Chris to certify code safety from appearance.

Start manually in Markdown. Use existing tests, walkthrough notes, and logs.
No new dashboard, scoring service, automatic telemetry system, or duplicated task
tracker is required. features.md remains the only action/status backlog.

## Related guidance

- [AGENTS.md](../AGENTS.md): engineering checks and evidence discipline.
- [features.md](features.md): action/status backlog.
- Product-focus branch: docs/ux-principles.md and docs/plans/v1-journeys.md
  hold UX goals and walkthrough contracts; link locally once merged.
- This framework organizes evaluation; it does not settle frontend, lifecycle,
  release scope, or other decisions currently spread across branches.
