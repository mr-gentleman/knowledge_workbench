-- 001 — Knowledge Workbench: isolated landing tables (metrics-only V1)
--
-- Isolated from AI_PLATFORM.DICTIONARY on purpose: the app's write role gets
-- grants HERE only, so it physically cannot touch the production dictionary.
--
-- Field shapes borrowed from DICTIONARY.METRIC_CORE / METRIC_CALC where useful.
-- Snowflake does not enforce PK/UNIQUE on standard tables — the declared keys
-- below are documentation; the service layer enforces them (expected-revision
-- UPDATEs inside a transaction).

CREATE SCHEMA IF NOT EXISTS AI_PLATFORM.WORKBENCH
  COMMENT = 'Knowledge Workbench (Streamlit) — isolated human-authored knowledge. Not yet served.';

USE SCHEMA AI_PLATFORM.WORKBENCH;

-- ── ID sequences ────────────────────────────────────────────────────────────
-- Opaque, never reset, never reused. Gaps are fine.
-- Metric IDs start at 100000: legacy DICTIONARY ids span 2–90412, so new ids never look like old ones.
CREATE SEQUENCE IF NOT EXISTS seq_candidate_id START = 1    INCREMENT = 1 ORDER;
CREATE SEQUENCE IF NOT EXISTS seq_metric_id    START = 100000 INCREMENT = 1 ORDER;
CREATE SEQUENCE IF NOT EXISTS seq_calc_id      START = 1    INCREMENT = 1 ORDER;

-- ── metric_candidate ───────────────────────────────────────────────────────
-- Every new metric assertion starts here (SME input, import, later: machine).
-- "Draft" is a UI label; a candidate may be incomplete. Only a name is required.
CREATE TABLE IF NOT EXISTS metric_candidate (
    candidate_id        NUMBER        NOT NULL,
    full_name           VARCHAR       NOT NULL,   -- the one name (no short/full split)
    description         VARCHAR,
    disambig            VARCHAR,                  -- when to use it / how it differs from similar metrics
    department          VARCHAR,                  -- finance | marketing | sales | customer | product | bi_meta | misc
    category            VARCHAR,
    source              VARCHAR       NOT NULL,   -- sme | import | extraction | conversation | feedback
    -- open → promoted | rejected. Only deliberate actions change it. "Not ready yet"
    -- (no description, SQL fails) is a computed checklist, never a stored status.
    status              VARCHAR       NOT NULL DEFAULT 'open',  -- open | promoted | rejected
    promoted_metric_id  NUMBER,                   -- the canon this candidate became
    duplicate_of_metric_id NUMBER,                -- rejected as a duplicate of this canon (a naming/synonym signal)
    original_author     VARCHAR,                  -- who wrote the content (NULL = unknown, don't guess)
    revision_no         NUMBER        NOT NULL DEFAULT 1,
    created_by          VARCHAR       NOT NULL,   -- who typed/imported it (trusted viewer identity)
    created_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_by          VARCHAR       NOT NULL,
    updated_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_metric_candidate PRIMARY KEY (candidate_id)
);

-- ── metric_core ─────────────────────────────────────────────────────────────
-- Canonical identity. A row exists only after promotion (needs ≥1 PI that passed
-- its SQL check). Losing the last usable PI later does NOT unmint.
CREATE TABLE IF NOT EXISTS metric_core (
    metric_id           NUMBER        NOT NULL,
    slug                VARCHAR       NOT NULL,
    full_name           VARCHAR       NOT NULL,
    description         VARCHAR       NOT NULL,
    department          VARCHAR,                  -- finance | marketing | sales | customer | product | bi_meta | misc
    category            VARCHAR,
    disambig            VARCHAR,                  -- when to use it / how it differs from similar metrics
    -- Retired = not served. The WHY lives in the revision's change_note, not the status.
    status              VARCHAR       NOT NULL DEFAULT 'active',  -- active | retired
    superseded_by       NUMBER,                   -- optional "see instead" pointer (duplicate, renamed, replaced)
    origin_candidate_id NUMBER        NOT NULL,
    original_author     VARCHAR,
    revision_no         NUMBER        NOT NULL DEFAULT 1,
    created_by          VARCHAR       NOT NULL,
    created_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_by          VARCHAR       NOT NULL,
    updated_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_metric_core PRIMARY KEY (metric_id),
    CONSTRAINT uq_metric_core_slug UNIQUE (slug)
);

-- ── metric_calc (Metric Physical Implementation / PI) ──────────────────────
-- Attachment rule (V1, fixed after acceptance):
--   authored with candidate  → metric_id NULL, origin_candidate_id set
--   candidate promotes       → metric_id set,  origin_candidate_id preserved
--   added to existing metric → metric_id set,  origin_candidate_id NULL
-- No reassignment in V1: wrong attachment = new PI + retire the old one.
CREATE TABLE IF NOT EXISTS metric_calc (
    calc_id             NUMBER        NOT NULL,
    metric_id           NUMBER,
    origin_candidate_id NUMBER,
    disambig            VARCHAR,                  -- how this PI differs from its siblings: "monthly", "by cohort", …
    source              VARCHAR       NOT NULL,   -- sme | import | extraction | conversation | feedback
    sql_text            VARCHAR,                  -- content, never executed on save; may be unfinished
    source_table        VARCHAR,                  -- AC.SCHEMA.TABLE; must match an active fact_table_core row to promote
    is_default          BOOLEAN       NOT NULL DEFAULT FALSE,
    status              VARCHAR       NOT NULL DEFAULT 'active',  -- active | retired
    -- Validation is bound to the exact revision it checked. Edit SQL → stale.
    -- Running a check updates these in place; it is NOT a content revision.
    validated_revision_no NUMBER,
    validation_status   VARCHAR,                  -- passed | failed | NULL (never checked)
    validation_message  VARCHAR,
    validation_query_id VARCHAR,
    validated_at        TIMESTAMP_TZ,
    -- What the Oracle uses: the latest revision that PASSED. Advances only on a pass,
    -- so a broken edit to live SQL saves fine and the Oracle keeps the last good one.
    served_revision_no  NUMBER,
    original_author     VARCHAR,
    revision_no         NUMBER        NOT NULL DEFAULT 1,
    created_by          VARCHAR       NOT NULL,
    created_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_by          VARCHAR       NOT NULL,
    updated_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_metric_calc PRIMARY KEY (calc_id)
);

-- ── fact_table_core ────────────────────────────────────────────────────────
-- Physical table knowledge. No candidate/canon split: identity = the table's name.
-- Keyed on the fully qualified name (Snowflake's internal TABLE_ID changes on every
-- CREATE OR REPLACE). A rename = edit table_name_full + the PIs' SQL in one pass.
-- Joins and dimensions are separate components — deliberately not here.
CREATE TABLE IF NOT EXISTS fact_table_core (
    table_name_full     VARCHAR       NOT NULL,   -- AC.SCHEMA.TABLE (always 3-part)
    display_name        VARCHAR,                  -- "MRR Rollup"
    description         VARCHAR,                  -- what is this?
    disambig            VARCHAR,                  -- when to use this table instead of a similar one
    gotchas             VARCHAR,                  -- how you get a wrong number from it
    required_filter     VARCHAR,                  -- filters every query must apply (until fixed upstream)
    grain               VARCHAR,                  -- "one row per ACCOUNTID per DATE_CST per MRR_TYPE"
    primary_key         VARCHAR,                  -- the columns that enforce the grain
    time_dimension      VARCHAR,
    department          VARCHAR,                  -- finance | marketing | sales | customer | product | bi_meta | misc
    source              VARCHAR       NOT NULL,   -- sme | import | extraction | conversation | feedback
    status              VARCHAR       NOT NULL DEFAULT 'active',  -- active | retired (why → change_note)
    original_author     VARCHAR,
    revision_no         NUMBER        NOT NULL DEFAULT 1,
    created_by          VARCHAR       NOT NULL,
    created_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_by          VARCHAR       NOT NULL,
    updated_at          TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT pk_fact_table_core PRIMARY KEY (table_name_full)
);

-- ── revision ────────────────────────────────────────────────────────────────
-- Append-only. One successful content-changing save = one row with the COMPLETE
-- post-save snapshot. Written in the same transaction as the current-state row.
CREATE TABLE IF NOT EXISTS revision (
    record_type         VARCHAR       NOT NULL,   -- metric_candidate | metric_core | metric_calc | fact_table_core
    record_id           VARCHAR       NOT NULL,   -- numeric ids as text, or a table name
    revision_no         NUMBER        NOT NULL,
    action              VARCHAR       NOT NULL,   -- create | edit | promote | reject | retire | import
    snapshot            VARIANT       NOT NULL,
    schema_version      NUMBER        NOT NULL DEFAULT 1,  -- keeps old payloads interpretable
    actor               VARCHAR       NOT NULL,
    acted_at            TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    change_note         VARCHAR,
    CONSTRAINT pk_revision PRIMARY KEY (record_type, record_id, revision_no)
);
