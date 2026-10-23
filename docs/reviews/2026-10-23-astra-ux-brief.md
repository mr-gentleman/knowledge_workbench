# Astra UX/product design brief — 2026-10-23

Source: GPT Astra, pasted by #chris into the ux-exemplars session. Verbatim below. Compared
claim by claim in [../ux-exemplars.md § Astra read](../ux-exemplars.md#astra-read--side-by-side).

---

Use this as the UX/product design brief for Knowledge Workbench. Incorporate it into your design research, planning, implementation, and review workflows. Treat the reference products as sources of patterns to evaluate, not a feature checklist.

## Product purpose and intended feel

Knowledge Workbench captures expert business and technical knowledge for use by humans and AI. It initially houses metrics and calculations, with potential expansion into fact tables, dimensions, joins, and higher-order business concepts.

The central user activities are:

1. Find relevant knowledge.
2. Understand its meaning and relationships.
3. Judge whether it is trustworthy.
4. Create, refine, validate, and maintain it.

The desired feel is spartan, modern, precise, responsive, and satisfying to operate. The user should feel they are working with a capable instrument for expressing expertise.

The content is primarily structured text and SQL. Descriptions and disambiguation are substantive knowledge, not incidental form fields. Rich-text styling is secondary. Visual polish should come from typography, hierarchy, spacing, responsive interactions, and clear feedback.

## Two connected experiences

**Discovery and exploration:** Search, browse, filter, understand categories, inspect entries, and follow relationships. Users should retain their orientation and easily return to their previous results.

**Authoring and refinement:** Edit names, descriptions, disambiguation, SQL implementations, and other relevant properties; understand save state; validate where supported; and manage candidate/canon status.

Design these as a coherent workflow. Moving between finding, understanding, and improving an entry should require little ceremony.

## Reference products and what to study

The following are research leads. Inspect actual product interactions, demos, or documentation. Distinguish observed behavior from inferred behavior; do not claim to have tested interactions that were inaccessible.

| Reference | Study for | Potential application |
|---|---|---|
| [Linear](https://linear.app/docs) | Overall interaction polish: lists, record details, properties, filtering, previews, and keyboard navigation | Fast movement between discovery and editing; compact controls; clear status; preserving context |
| [Sanity Studio](https://www.sanity.io/docs/content-lake/drafts-and-versions) | Structured authoring, document history, draft/published distinctions, and publishing actions | Thoughtful field grouping, save feedback, validation, and candidate/canon lifecycle design |
| [Atlan](https://docs.atlan.com/get-started/new-atlan-ui) | Business and technical knowledge within searchable asset profiles | Entry organization, ownership, relationships, and grouped metadata |
| [Notion wikis](https://www.notion.com/en-gb/help/wikis-and-verified-pages) | Readable knowledge with structured properties, ownership, and verification | Trust signals that remain visible in search and references |
| [Supabase Studio](https://supabase.com/features/sql-editor) | SQL editing within a larger application | Editor layout, code readability, contextual controls, and feedback |
| [dbt Catalog](https://docs.getdbt.com/docs/explore/explore-projects) | Resource discovery and technical relationships | Navigation among metrics, models, tables, and dependencies |
| [Scryfall](https://scryfall.com/advanced) | Expert discovery across objects with precise terminology and overlapping attributes | Simple search with room for advanced filtering; consistent entry structure; multiple discovery paths |
| [Moxfield](https://moxfield.com/) | Browsing and assembling a structured collection | Finding and connecting related objects while retaining the current work context |
| [regex101](https://regex101.com/) | Precise text input alongside explanations, tests, and feedback | The strongest conceptual reference for future authoring assistance and validation |
| [Desmos](https://www.desmos.com/calculator) | A quiet interface that supports sophisticated work and immediate feedback | Progressive disclosure, compact controls, and complexity revealed as needed |
| [Lichess analysis](https://lichess.org/analysis) and [Studies](https://lichess.org/study) | Expert reasoning, structured variations, annotations, and machine analysis | Human judgment supported by contextual machine feedback |
| [Shadertoy](https://www.shadertoy.com/) | Code, inputs, compilation, and output within one workspace | Connecting SQL implementations to checks and results |

BeerAdvocate and Lolalytics are additional exploratory references for categorization, filtering, and information density. Evaluate particular patterns without assuming their entire visual design or complexity fits this product.

Prioritize a focused first pass: Linear for interaction quality, Sanity for structured authoring, Scryfall for discovery, and regex101 for feedback. Consult the others to answer specific unresolved design questions.

## Design principles to apply

- **Organize around the user's work.** Database tables need not map directly to separate screens. A metric and its implementations may belong in the same working context even if stored separately.
- **Give meaning the best space.** Name, definition, disambiguation, and implementation deserve the strongest visual hierarchy.
- **Keep supporting metadata compact.** Ownership, author, timestamps, tags, and eventual usage statistics should support understanding without competing with it.
- **Preserve continuity.** Saving, validating, inspecting related entries, and returning to results should preserve work, selection, filters, and scroll position wherever practical.
- **Use progressive disclosure.** Keep frequent actions obvious. Reveal advanced options, history, diagnostics, and deeper relationships when useful.
- **Make status and feedback explicit.** Users should know what changed, whether it saved, what validation actually established, and what action remains.
- **Use restrained visual styling.** Color should communicate selection, state, hierarchy, or actionable feedback. Avoid ornamental dashboards and excessive badges.
- **Support efficient expert use.** Sensible tab order, keyboard access, visible focus, readable contrast, and predictable controls contribute to a polished experience.
- **Keep the workflow coherent.** Borrow patterns selectively and adapt them to one interaction model.

## Navigation and entry layout: starting hypotheses

Test these against realistic content before treating them as settled decisions.

For discovery, start by evaluating search plus shallow browsing by object type or business area. Tags and related-entry links can provide additional paths. Avoid assuming a deep folder tree is necessary: one metric may belong to several meaningful categories.

For an entry:

- **Top:** name, object type, candidate/canon status, and relevant primary action.
- **Main content:** business definition, disambiguation, and calculations or SQL implementations.
- **Secondary area:** ownership, author, timestamps, tags, and related objects.
- **On demand:** history, detailed diagnostics, and deeper technical relationships.

Choose inline editing, an explicit edit mode, a side panel, or a full detail page based on the real workflow and existing technical constraints. Do not assume one pattern is universally superior.

## Saving, validation, and canon status

Keep these concepts distinct:

- **Saved** means the work has persisted.
- **Candidate/canon** describes its knowledge lifecycle or approval status.
- **Validation** describes a particular check performed on a particular version.

A candidate can be fully saved. A canonical entry may eventually need proposed revisions. Inspect the existing lifecycle and persistence model before changing these behaviors; preserve established history and concurrency guarantees.

State validation results precisely. "SQL syntax check passed" does not establish that the metric is business-correct. Machine suggestions, automated checks, and human approval should be distinguishable.

## Future assistance: design room for it, but do not build it all now

Potential later capabilities include:

- SQL validation with contextual diagnostics.
- Suggestions about missing or ambiguous definitions.
- Related-metric and potential-duplicate detection.
- Usage statistics, such as questions answered using an entry.
- Quality assessments based on an explicit rubric.
- A test area showing how AI interprets an entry.

Favor specific, actionable feedback. Illustrative examples:

- "Does 'active' mean logged in, paid, or performed a qualifying action?"
- "Explain how this differs from Active Accounts."
- "Syntax check passed; business correctness has not been reviewed."
- "Potential overlap with Paid Subscribers: both use the same eligibility filter."

A generic "83/100" score is less useful unless its criteria and limitations are clear. Any future feedback should be tied to the content version evaluated and marked stale after relevant edits.

An especially promising later experiment is an AI interpretation preview: a paraphrase of the definition, example questions it should answer, and questions it should not answer. This could expose misunderstandings directly.

## Research and implementation workflow

Before proposing changes, read the current implementation and relevant product decisions. Identify which ideas fit the current scope and which would require a separate product or architecture decision.

Inspect references through concrete tasks:

1. Find an entry among many.
2. Open it and return without losing context.
3. Change descriptive text and a structured property.
4. Determine whether the change saved.
5. Inspect validation, publication/status changes, and history where available.

For each useful pattern, record:

- What was actually observed.
- Which user problem it solves.
- How it would translate to Knowledge Workbench.
- Whether it belongs now, later, or nowhere.
- Any meaningful implementation cost or tradeoff.

Then select a small, coherent set of improvements. Implement and review a complete workflow using realistic entries, long descriptions, multiple SQL implementations, similar metric names, and relevant failure states. Evaluate the experience through use, not screenshots alone.

For V1, prioritize finding an entry, understanding it, editing it comfortably, saving reliably, and understanding its status. Treat advanced grading, usage analytics, lineage visualizations, elaborate search syntax, and AI interpretation previews as future possibilities unless separately prioritized.

The success criterion is that an expert can express precise knowledge with little friction, understand the system's feedback, and trust what happened to their work.
