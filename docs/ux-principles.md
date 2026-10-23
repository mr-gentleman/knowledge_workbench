# UX principles

Standing UX guidance for the Workbench. #chris #claude 2026-10-23, merging a GPT Astra
discussion with established practice (Nielsen's heuristics, Apple HIG, Linear/Notion/Google
Docs conventions). Borrow tried-and-true patterns; don't invent interaction behavior per screen.
Journey contracts live in [plans/v1-journeys.md](plans/v1-journeys.md).

## Goals — explicit

1. **Easy to use** — the next step is obvious without instructions.
2. **Fast** — few clicks, instant feedback, keyboard works.
3. **Easy to understand** — status, meaning, and consequences are plain.
4. **Fun, cool, modern** — it should feel good to open. This is a requirement, not polish
   to add later: the app is the first impression SMEs get of contributing knowledge.

### What "looks cool" means here

Draft — #chris refines. Reference points: **Linear, Raycast, Vercel dashboard, Apple Notes.**

- **Content first.** The definition and SQL are the page; chrome, metadata, and secondary
  actions recede. Generous whitespace; no boxes inside boxes.
- **Restraint.** One typeface (system UI or Inter) plus one monospace for SQL. A small type
  scale (title / section / body / caption). Cool slate neutrals with **one** cool accent
  (#chris's palette: cool summer with a wintry lean). Color carries meaning — status — not decoration.
- **Calm, quick motion.** Subtle transitions on state changes (saved, validated); nothing that
  makes you wait.
- **Keyboard-friendly.** ⌘K / `/` to search, ⌘S to save, Esc to cancel.
- **Anti-patterns:** default-Streamlit look; stacked colored banners; walls of form fields;
  messages that scroll away; three buttons of equal weight.

## App-wide rules

1. **Orientation** — I can tell which record is open and whether I'm viewing or editing.
2. **Persistence** — unsaved / saving / saved / failed is always visible; never scrolled away.
3. **Knowledge status ≠ save status** — *saved* is not *validated* is not *canon*. Different
   words, styles, and places on the page.
4. **Recovery** — nothing discards my work without saying so. Destructive actions are red and
   never the primary button.
5. **One next step** — one primary action per state; a disabled action says why.
6. **Plain errors** — what happened, who/when if known, what it means for me, what to do next.

When the same decision comes up in two journeys, promote it to a rule here.

## Status vocabulary

Use these exact words everywhere.

| Kind | States | Where / how |
|---|---|---|
| Save | `● Unsaved changes` · `Saving…` · `✓ Saved · rev N · just now` · `Couldn't save — <reason>` | Small text, right side of the sticky record header; plus a corner toast on save/failure |
| Validation | `Not validated` · `Validating…` · `✓ Validated` · `✗ SQL failed` | Next to the SQL, with the preview or error beneath |
| Knowledge | `Candidate` · `Canon` | Pill next to the title; canon uses the accent |

## Patterns

**Save** — sticky header status (above) + toast. Save is disabled when nothing changed. ⌘S
saves. A successful save never clears the page's context.

**Conflict** — say who and when, what changed, and keep my work by default:
> **Gabe saved a newer version 3 minutes ago** while you were editing. Changed: SQL, description.
> **[Keep my edits & view theirs]** · [Discard mine, load theirs] (red, secondary)

**Validation** — runs only when the SQL changed; a pass sticks to that SQL revision. Show a
row preview on pass; on failure show Snowflake's message in plain form and keep the SQL.
A failed validation never makes the save look failed (rule 3).

**Empty states** — say what goes here and offer the action: a search with no results offers
**Create "<query>"**; a metric with no SQL offers **Add SQL**.

**Disabled actions** — visible, with the reason beside them
(`✓ SQL validated · ✗ "When to use" missing`), not hidden.

**Leaving with unsaved edits** — in-app navigation asks *"Discard unsaved changes?"* with
Keep editing as the default. (Browser reload/close can't always be intercepted; say so in the
editor rather than pretend.)

## Process — per journey

1. **Scenario** — #chris supplies a realistic task.
2. **Contract (pre-code)** — the agent drafts answers to the six questions below, recommends
   the simplest behavior consistent with the rules, flags only decisions that materially
   change the experience, and writes observable acceptance checks. #chris accepts or overrides.
3. **Build** — no scope beyond the contract; extras are proposed separately (AGENTS.md
   "Product focus").
4. **Walkthrough (post-code)** — #chris runs the journey with realistic content against the
   acceptance checks ("I clicked Save — show me how I know it worked"). Gaps are fixed in the
   same milestone.

Contract questions: (1) What is the user trying to accomplish? (2) What must they understand
before acting? (3) What is the obvious next action? (4) What changes after it? (5) What if they
hesitate, interrupt, or fail? (6) How do they know they're done? Cover success, empty, waiting,
failure, and interrupted-work states.
