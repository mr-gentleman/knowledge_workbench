"""Persistence. Owns SQL and transaction boundaries; no business rules."""

from app.db import SCHEMA, query, session


class StaleEdit(Exception):
    """Someone saved a newer revision since this form was loaded."""


def _snapshot(record_type: str, table: str, key: str, record_id: int,
              action: str, actor: str, note: str | None, execute):
    # Snapshot = the committed row itself, so history can't drift from current state.
    execute(
        f"""INSERT INTO {SCHEMA}.revision
              (record_type, record_id, revision_no, action, snapshot, actor, change_note)
            SELECT ?, {key}::VARCHAR, revision_no, ?, OBJECT_CONSTRUCT(*), ?, ?
            FROM {SCHEMA}.{table} WHERE {key} = ?""",
        [record_type, action, actor, note, record_id],
    )


def _in_txn(fn):
    s = session()
    s.sql("BEGIN").collect()
    try:
        # Bind every statement, including the snapshot, to this transaction.
        def execute(sql, params=None):
            return s.sql(sql, params=params or []).collect()

        out = fn(execute)
        s.sql("COMMIT").collect()
        return out
    except Exception:
        s.sql("ROLLBACK").collect()
        raise


# ── candidates ──────────────────────────────────────────────────────────────

def list_candidates(search: str = ""):
    return query(
        f"""SELECT candidate_id, full_name, category, status,
                   promoted_metric_id, original_author, updated_by, updated_at
            FROM {SCHEMA}.metric_candidate
            WHERE ? = '' OR full_name ILIKE '%' || ? || '%'
            ORDER BY updated_at DESC""",
        [search, search],
    )


def get_candidate(candidate_id: int):
    rows = query(f"SELECT * FROM {SCHEMA}.metric_candidate WHERE candidate_id = ?", [candidate_id])
    return rows[0].as_dict() if rows else None


def find_by_exact_name(normalized_name: str):
    """Collisions across candidates and canon. Normalization rule lives in services."""
    return query(
        f"""SELECT 'candidate' AS kind, candidate_id AS id, full_name
            FROM {SCHEMA}.metric_candidate
            WHERE LOWER(TRIM(full_name)) = ? AND status = 'open'
            UNION ALL
            SELECT 'metric', metric_id, full_name
            FROM {SCHEMA}.metric_core
            WHERE LOWER(TRIM(full_name)) = ? AND status = 'active'""",
        [normalized_name, normalized_name],
    )


def insert_candidate(fields: dict, actor: str, source: str = "sme") -> int:
    def run(execute):
        cid = execute(f"SELECT {SCHEMA}.seq_candidate_id.NEXTVAL")[0][0]
        execute(
            f"""INSERT INTO {SCHEMA}.metric_candidate
                  (candidate_id, full_name, description, disambig, department, category,
                   source, original_author, created_by, updated_by)
                SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?""",
            [cid, fields["full_name"], fields.get("description"),
             fields.get("disambig"), fields.get("department"), fields.get("category"),
             source, fields.get("original_author") or actor, actor, actor],
        )
        _snapshot("metric_candidate", "metric_candidate", "candidate_id", cid, "create", actor, None, execute)
        return cid

    return _in_txn(run)


def update_candidate(candidate_id: int, expected_revision: int, fields: dict,
                     actor: str, note: str | None = None) -> int:
    def run(execute):
        res = execute(
            f"""UPDATE {SCHEMA}.metric_candidate
                SET full_name = ?, description = ?, disambig = ?, department = ?, category = ?,
                    revision_no = revision_no + 1,
                    updated_by = ?, updated_at = CURRENT_TIMESTAMP()
                WHERE candidate_id = ? AND revision_no = ?""",
            [fields["full_name"], fields.get("description"),
             fields.get("disambig"), fields.get("department"), fields.get("category"),
             actor, candidate_id, expected_revision],
        )
        if res[0][0] == 0:
            raise StaleEdit(candidate_id)
        _snapshot("metric_candidate", "metric_candidate", "candidate_id", candidate_id, "edit", actor, note, execute)
        return expected_revision + 1

    return _in_txn(run)


def history(record_type: str, record_id: int):
    return query(
        f"""SELECT revision_no, action, actor, acted_at, change_note, snapshot
            FROM {SCHEMA}.revision
            WHERE record_type = ? AND record_id = ?
            ORDER BY revision_no DESC""",
        [record_type, str(record_id)],
    )

