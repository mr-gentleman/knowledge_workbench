#!/usr/bin/env bash
# Deploy the app, then re-attach the PyPI artifact repository.
# Snowflake CLI 3.30 can't declare an artifact repository in snowflake.yml.
# `--replace` on an existing app only ALTERs what changed, so the repository
# normally survives — but if the app is ever recreated it would be lost and
# pyproject.toml packages would stop installing. Re-setting it is idempotent.
set -euo pipefail
cd "$(dirname "$0")/.."

CONN="${CONN:-workbench_deploy}"
APP="AI_PLATFORM.WORKBENCH.KNOWLEDGE_WORKBENCH"
REPO="snowflake.snowpark.pypi_shared_repository"

snow streamlit deploy --replace -c "$CONN" "$@"
snow sql -c "$CONN" -q "ALTER STREAMLIT $APP SET ARTIFACT_REPOSITORIES = ($REPO)"
snow sql -c "$CONN" --format json -q "SHOW STREAMLITS LIKE 'KNOWLEDGE_WORKBENCH' IN SCHEMA AI_PLATFORM.WORKBENCH" | grep -q pypi_shared_repository \
  && echo "OK: artifact repository attached" \
  || { echo "ERROR: artifact repository not attached" >&2; exit 1; }
