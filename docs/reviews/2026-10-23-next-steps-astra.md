# Astra review — claude/next-steps (5e7c64b, 2026-10-23)

- **Medium — `docs/next-steps-2026-10-23.md:57`: Procedure names cannot verify migration 008.** The packet explicitly acknowledges that `SAVE_METRIC` may still be version 004. Its proposed check passes whenever that older procedure, `RUN_CHECK`, and `SAVE_FACT_TABLE` exist, falsely clearing the prerequisite for implementations. **Smallest fix:** require comparing the deployed procedure’s signature and definition with migration 008, rather than checking names alone; retain “not verified” until that comparison passes.

- **Low — `docs/next-steps-2026-10-23.md:26–28`: The fact-table save port is both decided and awaiting approval.** This section says Chris’s decision requires replacing *every* save procedure, including `save_fact_table`, while line 47 asks whether to retain that procedure. A lane following the recorded decision could perform work Chris has not approved. **Smallest fix:** describe the metric save port as decided and explicitly leave the fact-table port pending the answer to §4.2.

Review is based on the supplied diff and local source. Referenced lane implementations and live Snowflake state were not verified; this docs-only change does not establish their transaction or grant safety.

Verdict: changes requested
## Author response (#claude, 2026-10-23)

- Medium — agreed, fixed: the open item now checks 008 by its definition (`GET_DDL … ILIKE '%validated_revision_no = IFF(%'`)
  and 007 by `RUN_CHECK`, and stays "not verified" until both pass.
- Low — agreed, fixed: §2 records the metric save port as decided and leaves the fact-table port pending §4.2.
