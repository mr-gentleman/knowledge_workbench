# Working in tandem — Claude + Codex + Chris

Status: **PROPOSED** by #claude 2026-10-21, requested by #chris. Codex: respond in
the "Codex response" section at the bottom (don't edit the proposal above it); Chris
decides. Once accepted, AGENTS.md gets a one-line pointer here.

## What went wrong on 2026-10-21 (the reason for this file)

1. **Duplicate work.** Claude and Codex both implemented REL-01 in parallel; one copy
   was thrown away.
2. **Invisible work.** Claude's branches were local only, so Codex built on a `main`
   missing them. Three branches then needed conflict resolution.
3. **Unreviewed main.** A fix went straight to `main`; the reviewer then found a
   correctness gap (DEC-004) after it had landed.
4. **Append conflicts.** Both agents added sections at the end of `features.md`;
   branches that each merge cleanly conflict with each other.
5. **"Latest edit wins" on decisions.** Nothing said what happens when one agent
   disagrees with the other's recorded decision.

## The rules

**1. GitHub is the only shared state.** Neither agent can see the other's machine or
chat. Unpushed work doesn't exist for the other agent. Push a branch as soon as it
has a first commit; never leave finished work local.

**2. Claim before you build.** Before starting a backlog item, set its row in
`docs/features.md` to `DOING` with your owner tag (`owner #claude`) and push that
one-line change **directly to `main`**. This is the only allowed direct-to-main
commit (status/claim lines only). Before claiming, fetch and check nobody else has
it. Release the claim (back to `TODO`) if you stop.

**3. One item, one branch, one PR.** Branch `claude/<ID>-<topic>` or
`codex/<ID>-<topic>`, cut from the latest `origin/main`. Keep it small. Rebase onto
`main` before asking for review.

**4. The other agent reviews; Chris merges.** Nothing else reaches `main`.
- Whoever can opens the PR (Claude has no `gh` here; Chris can open it from the
  "Compare & pull request" banner).
- The PR description carries: what changed, why, the AGENTS.md bloat check, and
  evidence labelled by kind (source reading / local tests / preview / published app).
  This replaces separate handoff files.
- The reviewer posts findings as a PR comment. If it can't comment, it gives Chris
  the text to paste. Each finding: severity, concrete failure scenario, smallest fix.
- The author fixes on the same branch or replies why not. Disagreements go to Chris
  in the PR, not into silent edits.
- Neither agent edits the other's open branch without being asked.

**5. Decisions are append-only.** `docs/decisions.md` entries are never rewritten by
the other agent — not even "fixed". To disagree: add a new entry that supersedes it
(`Supersedes DEC-00N`, with the evidence), in a PR, so Chris accepts or rejects it.
New entries start `Status: proposed`; Chris flips them to `accepted` on merge.
Number collisions (both took DEC-005) are fixed at merge by renumbering the later one.

**6. Shared files: edit your rows, don't append at the end.**
- `features.md`: change only the rows you own or claimed. Put completion evidence in
  that row's evidence cell, not in a new section at the bottom.
- New rows go in their section's table, not the end of the file.
- `decisions.md` is the exception: append-only by design (rule 5).

**7. Who wins.** Code: whatever Chris merges. A decision: the latest *accepted*
entry, never just the latest edit. A factual dispute ("is the session shared?"):
the evidence, cited — query IDs, test output, a link.

**8. Every commit says who made it.** End each commit message with
`Agent: <tool> / <model>` (e.g. `Agent: claude / claude-opus-5-5`, `Agent: human / chris`).
Git history is the changelog; there is no separate changelog file (it would conflict
constantly). Details and the `git log` one-liner are in AGENTS.md. A convention, not a gate:
`.githooks/commit-msg` only prints a reminder.

## Small conveniences (not rules)

- Start each session with `git fetch` and read `features.md` DOING rows: they're the
  live view of who is doing what.
- Prefer naming the backlog ID in commit subjects (`REL-07: ...`).
- When you finish reviewing, say "approve" or "changes requested" explicitly.

## Codex response

_(Codex: agree / disagree / amend, per rule. Chris decides.)_
