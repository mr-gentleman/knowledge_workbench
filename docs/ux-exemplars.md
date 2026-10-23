# UX exemplars — a pattern library from sites that feel good

#claude 2026-10-23, from a live read of public pages (logged out, no cookie consent given).
Rules referenced: [ux-principles.md](ux-principles.md) (Goals 1–4, Rules 1–6, status vocabulary).
Journeys referenced: [plans/v1-journeys.md](plans/v1-journeys.md) (J1 find-or-add, J2 understand,
J3 fix-and-promote). Screenshots: [ux-exemplars/](ux-exemplars/).

**Why this exists:** UX decisions should cite a concrete example, not a vibe. Every pattern below
names where it was seen, which rule it serves, which journey uses it, and what it costs in
Streamlit vs React. That last column also feeds the pending SPCS/React spike decision.

## The two sides of the Workbench (#chris, 2026-10-23)

#chris's framing, mid-study: the Workbench is **two-sided**.

1. **Explore:** a dictionary you navigate, with visual interest. Search, browse, read, and
   understand at a glance (J1 find, J2).
2. **Edit:** write, save, validate, inspect, *and feel like you achieved something* (J1 add, J3).

Lolalytics, Letterboxd and BeerAdvocate are explore-side. Stripe is a read-side bridge (a
definition next to its code). Wikipedia, GitHub and Linear (added in a second pass) cover the
edit side: P15–P22.

## Sites and the job each exemplifies

| Site | Page(s) studied | Job | Feel in one line |
|---|---|---|---|
| **Lolalytics** (#chris pick) | `/lol/heimerdinger/build/`, `/lol/tierlist/` | Stats/tables · click-to-filter · search | Every number is clickable and scoped; the page reads like a sentence first |
| **BeerAdvocate** (#chris pick) | `/beer/top-rated/`, `/beer/profile/23222/78820/`, `/search/?q=stout` | Entity detail · ratings/consensus · contribution | Old-school but trustworthy: score, sample size, spread, and who said what |
| **Letterboxd** | `/film/parasite-2019/`, `/films/popular/this/week/genre/thriller/` | Browse/filter · entity detail · look and feel | Calm slate palette, prose serif, quiet chrome; content is the page |
| **Stripe API docs** | `/api/subscriptions/object` | Definition beside code · navigation · search palette | The definition and its code are always on screen together |
| **Wikipedia** | `Churn_rate` with `?veaction=edit`, `?action=history`, `?diff=prev&oldid=…` | Writing/editing · history · diff | Editing looks like reading; every change has who, when, size and why |
| **GitHub** (logged out) | `dbt-labs/jaffle-shop` `models/marts/orders.sql`, code and blame views | Code provenance · disabled-with-reason | Every line of SQL knows who changed it and why |
| **Linear** (public docs + homepage demo) | `/docs/creating-issues`, `/docs/editor`, `linear.app` | Create and edit fast · activity feed | Keyboard-first creation; human and machine changes in one calm timeline |
| ~~dbt docs~~ | — | Domain analog | **Not studied:** GitLab's public dbt docs now sit behind a bot check and sign-in; dbt's MRR playbook demo returns 404. |

Edit-side caveat: I couldn't type in any of the editors. Wikipedia's editor opens but blocks
this IP range from publishing. GitHub's editor and the Linear app need a sign-in. So save,
commit and draft behavior come from what the pages show plus Linear's own docs, and I mark
anything I didn't observe directly.

---

## Patterns

Cost key: **S** = small (a day or less), **M** = a few days, **L** = fights the framework or
can't be done well. *Streamlit* means stock Streamlit plus light CSS; *React* means the SPCS spike stack.

### Explore side

#### P1 · Search suggestions after two keystrokes, with deep links per result
- **Seen:** Lolalytics header search. Typing `he` instantly shows grouped results
  (*Champion Builds*, then *Summoner Profile*). Each result row carries its own sub-actions
  (**Leaderboard · Counters · Pro Builds**) that jump straight to a tab of that entity. On a
  champion page it also offers "Heimerdinger **vs** X" matchups. Matching is substring-anywhere
  (`he` → Hecarim, As**he**, S**he**n). Stripe does the same as a `/`-triggered modal palette:
  title, a breadcrumb (*Billing › Subscriptions*), the first line of the description, and a
  keyboard footer (`↑↓ Navigate · ↵ Go`).
  ![Lolalytics search suggestions](ux-exemplars/lolalytics-search-suggest.jpg)
- **Why it works:** Goal 2 (fast: no results page, no Enter). Goal 1 (the next step sits on
  the result itself). Showing a description line and breadcrumb lets you recognize a match
  without opening it, which is exactly J1 Q2.
- **Workbench:** J1. Each suggestion shows name · department · `Candidate`/`Canon` pill ·
  `✓ Validated` · first description line. Sub-actions: **Open · View SQL · Edit**. The last
  row is always **Create "<query>"** (our empty-state rule, folded into the dropdown). `/` or
  ⌘K opens it from anywhere.
- **Cost:** Streamlit **M–L**. Search-as-you-type exists (unmerged), but a dropdown overlay
  with per-row actions and arrow-key navigation needs a custom component. React **S**
  (cmdk or similar).

#### P2 · Click any value to filter the page in place, and put the filter in the URL
- **Seen:** Lolalytics. Clicking the *middle* lane chip re-scopes the whole page with no full
  reload: URL → `?lane=middle`, title → "…for **middle** Heimerdinger", the summary sentence
  and every stat recompute. Item and rune tables say *"Click Items Below to Filter Builds by
  Item"*. Tier-list lane filters are plain links (`/lol/tierlist/?lane=middle`). Letterboxd
  encodes filters in the path (`/films/popular/this/week/genre/thriller/`).
- **Why it works:** Goal 2 (one click). Rule 1 (orientation): the filter state is in the
  title, the URL and the prose, so you always know what you're looking at. Filtered views can
  be shared as links.
- **Workbench:** J1/J2 list. Click a department pill, a status pill or an author on any row
  to filter by it. `?dept=finance&status=canon` makes "all canon Finance metrics" a link
  #chris can paste in Slack.
- **Cost:** Streamlit **S–M** (`st.query_params` works; making every value clickable is
  awkward). React **S**.

#### P3 · Facets that show their own size
- **Seen:** Lolalytics lane bar: each lane icon carries its share of games (top 67.9% · mid
  13.8% · …), plus a 93% ring on the portrait. Letterboxd's filter result is a sentence:
  *"There are 65,908 thrillers."*
- **Why it works:** Goal 3. You know whether a filter is worth clicking before you click it,
  and the result count confirms what the filter did.
- **Workbench:** J1 list. `Finance 42 · Marketing 7 · Sales 3`. Above results:
  *"12 Finance metrics · 4 canon."*
- **Cost:** Streamlit **S**. React **S**.

#### P4 · A one-sentence summary above the stats
- **Seen:** Lolalytics opens every champion page with generated prose: *"Heimerdinger top has
  a 52.32% win rate … rank 59 of 111 … graded B Tier … strong counter to Pantheon, Urgot &
  Kled…"*. Every noun in it is a link. The stat grid comes after the sentence.
- **Why it works:** Goal 3. The sentence states the conclusion and the grid backs it up, and
  each stat has a `?` tooltip that defines it.
- **Workbench:** J2 metric page header. *"Net New ARR is a **canon** Finance metric, validated
  on rev 4 (2 days ago). Used by 3 Looker reports."* It can be templated; no LLM needed. The
  `?` tooltips map to our glossary terms (`Candidate`, `Canon`, `Validated`).
- **Cost:** Streamlit **S**. React **S**.

#### P5 · Sample size next to every number
- **Seen:** Lolalytics shows `win rate` over `games` on every cell (*56.56% · 1,775*), and
  rank as *59 / 111*. BeerAdvocate shows *AVG 4.83 · pDev 7.25%*, *RATINGS 965 · 194 reviews*,
  and its list says *"Sorted by weighted rank (not shown)"*.
- **Why it works:** Goal 3 and trust. Matches the project rule "always report `n` alongside
  accuracy". A 60% from 27 games and a 52% from 6,216 games are visibly different claims.
- **Workbench:** Later (usage and eval columns), but set the convention now: any count or
  rate shows its denominator. *"Answered 14 questions · 86% thumbs-up (n=14)."*
- **Cost:** Streamlit **S**. React **S**.

#### P6 · Skeleton grid while loading
- **Seen:** Letterboxd browse renders the full poster grid as empty outlined tiles, with the
  filter bar and result sentence already in place, then fills them in.
  ![Letterboxd skeleton](ux-exemplars/letterboxd-browse-skeleton.jpg)
- **Why it works:** Goal 2 (it feels instant), and the layout doesn't jump. The waiting state
  is designed, which is one of the five states the contract process requires.
- **Workbench:** list first load, and the validation preview (`Validating…` shows a 10-row
  skeleton table).
- **Cost:** Streamlit **M**. `st.spinner` is the stock answer; true skeletons need
  placeholders and CSS, and reruns flash. React **S**.

#### P7 · Quiet filter bar as inline text dropdowns
- **Seen:** Letterboxd: `DECADE ˅  THRILLER ˅  SERVICE ˅  Sort by FILM POPULARITY ˅` as
  small caps in one line on the right of the section header. There are no boxes, and the active
  value replaces the label.
- **Why it works:** "Content first" and "Restraint". The controls recede until you want them.
- **Workbench:** list header. `DEPARTMENT ˅  STATUS ˅  Sort by RECENTLY CHANGED ˅`.
- **Cost:** Streamlit **M** (stock selectboxes are boxed and labelled; restyling them is
  fragile). React **S**.

### Entity page (the hinge between the two sides)

#### P8 · Definition and code side by side, code pane sticky
- **Seen:** Stripe API reference. Left column: attributes, each with name · `type` badge ·
  one-line definition, and nested fields behind **Show child attributes**. Right column:
  the object's JSON, in a sticky aside (`position: sticky`) that stays in view as you scroll
  the definitions. Header actions: **Ask about this section · Copy for LLM · View as
  Markdown**, plus a version selector.
  ![Stripe definition beside code](ux-exemplars/stripe-definition-beside-code.jpg)
- **Why it works:** Goal 3. The definition and its implementation are one glance apart, never
  a tab apart. "Content first": the page is the definition and the code.
- **Workbench:** J2/J3, and it settles the "SQL on the metric page" layout. Left: description,
  when to use, readiness. Right: sticky SQL card with the validation state and preview beneath.
  **Copy for LLM** is a natural fit (the Oracle is the consumer) and nearly free.
- **Cost:** Streamlit **M** (`st.columns` works; sticky right column needs CSS hacks that
  break on rerun). React **S**.

#### P9 · Score with a word, status pill, and a quiet meta line
- **Seen:** BeerAdvocate: a big **100** badge labelled *BA SCORE · World-Class*, the style
  link, *12% ABV*, a small green **Active** pill. Below it, one muted line:
  *"Suggest edit · Last rated Oct 16, 2026 · Shelf talker"*. Further down: *"Beer added
  Feb 26, 2012"*.
  ![BeerAdvocate entity](ux-exemplars/beeradvocate-entity.jpg)
- **Why it works:** Rule 3 in practice. Score (quality), *Active* (lifecycle) and *last rated*
  (freshness) are three different things in three different places and styles. Goal 1: the
  contribution action (*Suggest edit*) is always visible but never loud.
- **Workbench:** J2/J3 header. `Canon` pill (knowledge) · `✓ Validated` next to the SQL
  (validation) · `✓ Saved · rev 4` on the right (save). Meta line:
  *"Edit · Last validated 2 days ago · Added Oct 3 by Gabe"*.
- **Cost:** Streamlit **S**. React **S**.

#### P10 · Each contribution shown against the consensus
- **Seen:** BeerAdvocate reviews: every rating shows **rDev** (deviation from the beer's
  average, e.g. *rDev −29%*), plus a 1–5 rating-spread histogram. Letterboxd shows a ratings
  histogram and splits reviews into **Popular** and **Recent**.
- **Why it works:** Goal 3. You see agreement and outliers at a glance, without reading
  every entry.
- **Workbench:** V2 adjudication. Competing SQL implementations show their deviation from
  the canon result (*"returns 3.1% higher than canon for Sep"*). For V1, "Recent" ordering is
  enough for the history rail.
- **Cost:** Streamlit **S** (a bar chart). React **S**.

#### P11 · Secondary facts in tabs under the summary
- **Seen:** Letterboxd film page: synopsis first (in a serif), then a `CAST · CREW · DETAILS ·
  GENRES · RELEASES` tab strip in small caps. Lolalytics: `Build · Leaderboard · Counters ·
  ProBuilds` tabs under the stat block.
- **Why it works:** "Content first"; the long tail is one click away rather than stacked.
- **Workbench:** J2. Under the definition and SQL: `HISTORY · USED BY · RELATED · DETAILS`.
  V1 needs only History and Details.
- **Cost:** Streamlit **S** (`st.tabs`). React **S**.

### Look and feel

#### P12 · Cool slate dark palette, serif for prose, sans for UI
- **Seen:** Letterboxd: background `#14181c`, body text `#99aabb` (blue-grey), headings white,
  UI in Graphik (sans), synopsis and reviews in Tiempos (serif), tiny small-caps section
  labels. Stripe (light): `#f4f7fa` background, `#3c4257` text, system UI at 14px, Source Code
  Pro for code.
- **Why it works:** "Restraint", "cool slate neutrals with one cool accent". Letterboxd is
  almost #chris's palette as-is. A serif for the *definition* prose separates "knowledge" from
  "interface" without color.
- **Workbench:** adopt the slate scale. Consider a serif (or Inter at text optical size) for
  description and when-to-use, sans for chrome, mono for SQL. Ship light and dark from day one.
- **Cost:** Streamlit **M** (theme config covers colors; the type pairing and small caps need
  CSS injection). React **S**.

### Edit side and progress

#### P13 · Personal progress against a collection
- **Seen:** BeerAdvocate Top 250: *"✔ You rated 0 beers on this list. Log in to begin your
  beer adventure."* Lolalytics header: *"Emerald+ Champions Analysed: 4,925,020"*, a live
  corpus counter on every page.
  ![BeerAdvocate list](ux-exemplars/beeradvocate-top-list.jpg)
- **Why it works:** Goal 4 (fun) and #chris's "feeling like you're achieving something".
  The collection has a size, and you have a place in it.
- **Workbench:** #chris's ideas fit this pattern directly. A header strip like
  *"Finance: 42 metrics · 18 canon · avg freshness 9 days · ~31% of Looker Finance reports
  covered"*. After a save or promote, the relevant number ticks up with a brief highlight
  (calm motion). On the list: *"You've added 6 metrics this month."*
- **Cost:** Streamlit **S** for the numbers; **M** for an animated tick, which reruns fight.
  React **S**.

#### P14 · Agent-facing affordances on a human page
- **Seen:** Stripe: **Copy for LLM**, **View as Markdown**, **Ask about this section**.
- **Why it works:** the page's second reader is a machine, and Stripe says so openly.
- **Workbench:** the dictionary's real consumer is the Oracle. **Copy for LLM** (the exact
  serving payload for this metric) shows the SME what the agent will see, which also builds
  trust. Later: **Ask the Oracle about this metric** (cost-gated per CLAUDE.md).
- **Cost:** Streamlit **S**. React **S**.

### Edit side (second pass: Wikipedia, GitHub, Linear)

#### P15 · Editing looks like reading
- **Seen:** Wikipedia's visual editor opens *in place*. Same title, same typography, same
  layout. A slim toolbar appears under the `Read · Edit · View history` tabs, a *Short
  description* slot appears above the body, and **Publish changes…** sits top-right, greyed
  out until something changes. Linear's editor turns Markdown into rich text as you type
  (`**bold**`, `#` heading, `/` commands) with no separate preview.
  ![Wikipedia edit in place](ux-exemplars/wikipedia-edit-in-place.jpg)
- **Why it works:** Rule 1. You can tell you're editing (the tab, the toolbar), yet you're
  still looking at the page as readers will see it, so there's no form-vs-page mental switch.
  Rule 5: the one primary action is visible and disabled until it means something.
- **Workbench:** J1/J3, and it answers **D1** (view mode + Edit). Edit mode keeps the page
  layout and turns the fields editable in place, rather than swapping to a form. ⌘E toggles
  it. The Save button sits in the sticky header, disabled until dirty.
- **Cost:** Streamlit **L** (inputs look like inputs; in-place editing means a custom
  component). React **M** (contenteditable or a Tiptap-style editor; the SQL uses Monaco or
  CodeMirror).

#### P16 · The save asks "why?" (an edit summary)
- **Seen:** Wikipedia's button is **Publish changes…**, where the ellipsis means a dialog
  follows (the edit summary; I couldn't open it while blocked). Every history row then carries
  that summary: *"I realised that 'e.g.' was better / less ambiguous wording."*, or the honest
  fallback *"No edit summary"*. GitHub shows the last commit message above every file:
  *"Update project structure (#25)"*. (GitHub's commit dialog itself needs a sign-in; not seen.)
- **Why it works:** Goal 3 and trust. History stops being a list of timestamps and becomes
  a list of reasons, and the next editor learns *why* the SQL looks the way it does.
- **Workbench:** J3, plus the history rail (HIST-01/02). Add an optional one-line "What
  changed?" next to Save. It's required only when promoting or editing a canon metric.
  Blank shows *"No summary"*. Keep it to one field, never a form.
- **Cost:** Streamlit **S**. React **S**.

#### P17 · History rows: who · when · size of change · why · undo
- **Seen:** Wikipedia history: each row is *date · user · bytes after · **+31** / **−397**
  (green/red) · summary · undo · tags* (*Visual edit*, *Mobile edit*, *Newcomer task*,
  *Suggested: add links*). Bot edits are listed as plainly as human ones (*PrimeBOT*,
  *CutlassBot*). **undo** "reverts this edit and opens the edit form in preview mode", so it's
  never instant or destructive.
- **Why it works:** Rule 4 (recovery is one click, and it goes through a preview rather than
  a silent revert). The size delta tells you at a glance which edits matter.
- **Workbench:** J2 history rail. `rev 4 · Gabe · 2 days ago · SQL +3 lines · "exclude test
  accounts" · Restore…`. **Restore** opens the editor prefilled with the old revision; the user
  then saves it as a new revision. Tags show the source: `human`, `import`, and in V2
  `machine`.
- **Cost:** Streamlit **S–M**. React **S**.

#### P18 · Side-by-side diff with who/when/why headers
- **Seen:** Wikipedia diff. Two columns, each headed *"Revision as of 10:17, 19 May 2026
  (edit) (undo)"* · author · summary · tags, with **← Previous edit / Next edit →**. Changed
  words are highlighted inside the line. A **Visual / Wikitext** toggle and an **Inline**
  switch change the view.
  ![Wikipedia diff](ux-exemplars/wikipedia-diff.jpg)
- **Why it works:** Goal 3. Prev/next lets you walk the history one change at a time.
- **Workbench:** J3, plus the conflict pattern (*"Gabe saved a newer version… Changed: SQL,
  description"* → **View theirs** opens this diff). Diff the SQL and the description separately;
  where both revisions were validated, a *result* diff (row-count or value change) is the
  BI-specific bonus.
- **Cost:** Streamlit **M** (difflib to HTML works; word-level highlighting and the toggles
  take effort). React **S–M** (Monaco diff editor).

#### P19 · Line-level provenance (blame) with an age heat strip
- **Seen:** GitHub's code view has a byline above the file (*avatar · gwenwindflower · Update
  project structure (#25) · b232e30 · 2 years ago · History*) and *"77 lines (53 loc) · 1.42
  KB"*. The **Blame** toggle annotates each block with age, author and commit message
  (*"Fix fanout in customers model…"*), plus an **Older ▮▮▮▮ Newer** heat legend and a
  contributor count.
  ![GitHub blame](ux-exemplars/github-blame.jpg)
- **Why it works:** Goal 3 and trust. "Why is this `WHERE` clause here?" gets answered in
  place, which is exactly the forensic question BI asks about inherited SQL.
- **Workbench:** J2. A byline above the SQL card (*"Last changed by Gabe · 'exclude test
  accounts' · 2 days ago · History"*) adopts now. A blame toggle on the SQL comes later (it
  needs line-level revision mapping).
- **Cost:** byline: Streamlit **S**, React **S**. Blame: Streamlit **L**, React **M**.

#### P20 · Disabled action with the reason in a tooltip
- **Seen:** GitHub logged out: the pencil is visible but greyed, and hovering says *"You must
  be signed in to make or propose changes"*. Note the wording: **propose** changes is the
  path for people without write access (a fork and pull request).
- **Why it works:** exactly the existing "Disabled actions" rule. It also shows a two-tier
  model: some people *make* changes and others *propose* them.
- **Workbench:** J3. **Promote** is disabled with *"Needs: When to use · ✓ validated SQL"*.
  For V2, "propose" maps to editing a canon metric as a suggestion (a candidate revision) that
  an owner accepts, so canon is never casually overwritten.
- **Cost:** Streamlit **S** (the `help=` tooltip on buttons). React **S**.

#### P21 · Create from anywhere: shortcut, prefilled URL, and a quiet grace window
- **Seen (Linear docs):** **C** opens the create modal from anywhere. **Create issue from
  selection** turns highlighted text into an issue. `linear.new?title=…&status=…&assignee=me`
  pre-fills a new issue from a URL, so other tools can link straight into creation. And:
  *"Changes made to an issue's properties in the first 3 minutes are considered part of the
  issue creation process, and won't be added to the activity log."*
- **Why it works:** Goal 2. The grace window keeps history meaningful, because fixing a typo
  right after creating doesn't spawn rev 2, rev 3 and rev 4.
- **Workbench:** J1. `/new?name=Net+New+ARR&dept=finance` lets **the Oracle** link a
  prefilled *"Create this metric"* whenever it can't find one (a coverage loop), and the
  same link works from Slack. **C** or **N** on the list opens a new metric. Successive saves
  by the creator within a few minutes fold into one revision.
- **Cost:** Streamlit **S** for the URL prefill (`st.query_params`), **M** for keyboard
  shortcuts. The grace window is backend logic, and the same cost in either. React **S**.

#### P22 · One timeline for human and machine changes
- **Seen:** Linear homepage demo issue. The Activity feed mixes quiet one-liners (*"Linear
  created the issue via Slack on behalf of Karri · 2min ago"*, *"Triage Intelligence added the
  labels Performance and iOS"*, *"Linear moved from Todo to In Progress · just now"*) with
  comment cards from people. Machine actors are named and attributed like people, in muted
  text. The editor docs add: *"Referenced issues are added as related issues automatically"*
  via `@ENG-123`.
  ![Linear activity](ux-exemplars/linear-activity.jpg)
- **Why it works:** Rule 1 and trust. You can always tell what a person did from what a
  machine did, without a separate log. Events are quiet; comments get a card.
- **Workbench:** J2 history, and the V2 bridge. *"Forensics proposed this SQL from 3 Looker
  explores · 5 days ago"*, *"Validation passed on rev 4"*, *"Chris promoted to Canon"* in one
  feed. `@metric` mentions in a description auto-link related metrics (a cheap start on "related").
- **Cost:** Streamlit **S–M**. React **S**.

### Anti-patterns observed

- **Full-page search with a 10-result cap** (BeerAdvocate `/search`: ~675 ms to first byte,
  *"Results limited to 10 results. Log in or Join for more"*). Slow and gated. P1 is the fix.
- **Ads and banners competing with content** (all three consumer sites). Our version is
  stacked Streamlit banners; ux-principles already bans it.
- **Every pixel is data** (lower half of Lolalytics: dozens of tables). Right for a dashboard,
  too much for a dictionary page. Take the *interaction* (P2) and the *summary sentence* (P4),
  not the density.
- **Garish 404** (Lolalytics: a blue box on black). dbt's *"DAG! That wasn't supposed to
  happen"* with a single **Go Home** button is the better model for Rule 6.

---

## Adopt now / adopt with React / skip

| Pattern | Verdict | Note |
|---|---|---|
| P3 Facet counts · P4 Summary sentence · P5 `n` beside numbers · P9 Three-status header · P11 Tabs · P14 Copy for LLM | **Adopt now** | Cheap in either stack; pure content decisions |
| P2 Filters in URL | **Adopt now (partial)** | Query params now; click-any-value later |
| P13 Progress strip | **Adopt now (static)** | Numbers now; animated tick with React |
| P1 Suggest-as-you-type with row actions + ⌘K | **Adopt with React** | Strongest single "feels modern" moment; Streamlit can't do it well |
| P6 Skeletons · P7 Quiet inline filters · P8 Sticky SQL pane · P12 Type pairing | **Adopt with React** | Doable in Streamlit only with fragile CSS |
| P16 Edit summary · P17 History rows + Restore… · P19 SQL byline · P20 Disabled-with-reason · P21 Prefill URL | **Adopt now** | All S in Streamlit; P21 gives the Oracle a "create this metric" link |
| P15 Edit-in-place · P18 Word-level diff · P19 Blame · P21 Keyboard create | **Adopt with React** | P15 is the biggest edit-side "feels modern" item, and L in Streamlit |
| P22 Unified human + machine timeline | **Adopt now (simple), grow in V2** | Plain list now; machine events arrive with V2 |
| P10 Deviation vs consensus | **Defer to V2** | Belongs to adjudication |
| Lolalytics density, BeerAdvocate full-page search | **Skip** | See anti-patterns |

**For the React decision:** P1, P6, P7, P8 and the animated part of P13 are the patterns that
carry "fun, cool, modern" (Goal 4), and all of them are M–L in Streamlit and S in React. On the
edit side, P15 (edit in place) is L in Streamlit and M in React. That's the concrete evidence
the spike asked for.

## Proposed additions to ux-principles.md

1. **Every number shows its denominator** (`n`, `x / total`, or a time window). From P5.
2. **Filter state lives in the URL and in the heading.** A filtered view is a link, and the
   title says what's filtered. From P2.
3. **Summary before detail.** Entity pages open with one templated sentence stating the
   conclusion; stats and SQL follow. From P4.
4. **Definition and SQL are never more than a glance apart** (side by side on wide screens,
   SQL sticky). From P8.
5. **Progress is visible.** Collections show their size and the user's contribution; saves
   and promotions move a number. From P13.
6. **Design the waiting state.** Skeletons in the final layout, not spinners in empty space.
   From P6.
7. **Reference look:** add **Letterboxd** (dark slate, prose serif) and **Stripe API docs**
   (definition beside code) to the "looks cool" reference list.
8. **Editing looks like reading.** Edit mode keeps the page layout; fields become editable in
   place. From P15. (Resolves J1 D1 toward "view mode + Edit".)
9. **Every revision says who, when, how much and why.** An optional one-line summary on save,
   required for canon. From P16–P17.
10. **Undo is a preview, not a silent revert.** Restore opens the editor with the old content;
    saving it creates a new revision. From P17.
11. **Machines are named actors.** Imports, forensics and validation appear in the same
    history as people, attributed and visually quieter. From P22.

## Making it scoreable (#chris: "scoreable and highly iterable, not vibes")

A proposal: score each screen on numbers an agent can measure from a scripted run plus
screenshots, so #chris + AI can iterate without manual clicking.

| Measure | Target | How measured |
|---|---|---|
| Time to first suggestion (J1) | < 150 ms after keystroke | Browser script, network + DOM timing |
| Keystrokes to open an existing metric | ≤ 4 | Script types the shortest unique prefix |
| Clicks from list to `✓ Saved` for a new metric | ≤ 3 + typing | Script |
| Primary buttons per state | exactly 1 | DOM count of `.primary` per state |
| Status visible without scrolling after Save | yes | Screenshot + DOM `getBoundingClientRect` |
| Each of the five states (success/empty/waiting/failure/interrupted) designed | 5 / 5 | Script forces each; screenshot reviewed against P-patterns |
| Pattern adoption | count of P1–P22 present | Rubric per screen, 0/1/2 each, graded from screenshots |
| Acceptance checks (v1-journeys) | all pass | Existing walkthrough list, automated where possible |

The rubric gives a number per build (e.g. *"list screen 19/44"*) to compare across the
Streamlit and React spikes, and across iterations.

## Gaps — closer analogs still needed

- **Edit side: the moment of saving.** P15–P22 cover the structure of editing (in place,
  summaries, history, diff, provenance). Still unobserved: the save moment itself (optimistic
  UI, toast, the "done" feeling), because every editor needed a sign-in or blocked publishing.
  To close it: a signed-in Linear or Notion session by #chris, or a Wikipedia edit from an
  unblocked network (preview only, no publish).
- **Domain analog.** dbt docs demos are offline. Candidates: **DataHub** public demo, **Atlan**
  or **Select Star** product tours, **Metabase** docs screenshots of the Data Reference.
- **Dashboard-ish metric metadata** (questions answered, feedback average, Looker links).
  #chris: "can be later". Lolalytics is already the exemplar when it comes.

## Chris's notes — why each site feels good

*#chris: fill in. A line or two per site: what you notice first, what you'd steal, what bugs you.*

- **Lolalytics:** (from chat, 2026-10-23) Two letters in search and suggested champs pop up.
  Lots of juicy stats. Lots of filters and knobs: click a role, item, rune or patch and the page
  filters to it. Not a total analog; the filter interactivity and little stats are the draw.
  Maybe better suited to a data dashboard than a dictionary page.
- **BeerAdvocate:**
- **Letterboxd:**
- **Stripe API docs:**
- **Wikipedia:**
- **GitHub:**
- **Linear:**

## Astra read (optional) — side by side

*If #chris runs a GPT Astra read of the same sites, paste its findings here. One row per
pattern it found; mark agreements and disagreements with the P-numbers above.*

| Astra finding | Matches | Disagrees / new |
|---|---|---|
| | | |
