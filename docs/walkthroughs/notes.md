# Walkthrough notes — running log

Raw first impressions from #chris (dictated is fine), newest on top. The agent triages
each batch into backlog items or contract changes and marks it `→ triaged`.

## 2026-10-23 — published app (d1b6783)

- Save takes a noticeable moment; should feel lightweight. → measured: 1.7–2.2 s per save,
  lock wait 1 ms; ~11 Snowflake round trips per save. Trim trips + "Saving…" now; one-call
  save proc later.
- "Reload latest — discard my edits" is always shown. Should appear only on a conflict, next to
  (or instead of) Save. → UX-07.
- Search should run as you type (debounced), like most tools. → FIND-01/02.
- Full-screen browser: Name and Department stretch the full width; unnecessary. Department
  dropdown is unpleasant to use. → layout, UX-09.
- Remove Category for now (confusing); tags maybe later. → UX-03, FIND-05.
- Description and When to use as large multi-line fields: good.
- Start physical implementations (SQL) on the same edit screen: separate table, linked to the
  metric, rich SQL editor, collapsible for long SQL. → UX-01/02.
