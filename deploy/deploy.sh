#!/usr/bin/env bash
# Spike deploy loop: build React + API image → push → upgrade the service.
# Needs the objects in handoff.sql (Chris/CoCo) and a running podman machine (or ENGINE=docker). Usage: deploy/deploy.sh [--create]
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

CONN=${KW_CONNECTION:-workbench_deploy}
ENGINE=${ENGINE:-podman}
POOL=${KW_POOL:-SYSTEM_COMPUTE_POOL_CPU}  # handoff.sql 3a; KW_POOL=KW_SPIKE_POOL for 3b
REGISTRY=activecampaign-fm00411.registry.snowflakecomputing.com
REPO_URL=$REGISTRY/ai_platform/workbench/kw_images
TAG=$(git rev-parse --short HEAD)$(git diff --quiet || echo "-dirty$(date +%s)")
SPEC=$(mktemp)
sed "s/IMAGE_TAG/$TAG/" deploy/service.yaml > "$SPEC"

t0=$(date +%s)
# `snow spcs image-registry login` shells out to docker; this form works for podman too.
# The registry password is the whole token JSON (not its "token" field); SSO chatter precedes it on stdout.
snow spcs image-registry token -c "$CONN" --format JSON \
  | python3 -c 'import re,sys; print(re.search(r"\{.*\}", sys.stdin.read(), re.S).group(0).replace("\n", ""))' \
  | $ENGINE login "$REGISTRY" --username 0sessiontoken --password-stdin
$ENGINE build --platform linux/amd64 -f deploy/Dockerfile -t "$REPO_URL/kw-spike:$TAG" .
$ENGINE push "$REPO_URL/kw-spike:$TAG"
t1=$(date +%s)

# Deploy, wait for the new image to be READY, list the endpoint: one SQL file, so one SSO login
# (a poll per `snow` call meant a new browser login every 5 s).
SVC=AI_PLATFORM.WORKBENCH.KW_SPIKE
if [[ "${1:-}" == "--create" ]]; then
  DEPLOY="CREATE SERVICE $SVC IN COMPUTE POOL $POOL QUERY_WAREHOUSE = BIZ_AI_WH"
else
  DEPLOY="ALTER SERVICE $SVC"
fi
SQL=$(mktemp)
cat > "$SQL" <<SQLEOF
$DEPLOY FROM SPECIFICATION \$\$
$(cat "$SPEC")
\$\$;
-- Rolling restart: done once the container on image $TAG is READY (up to ~5 min).
EXECUTE IMMEDIATE \$\$
DECLARE s STRING; i INT DEFAULT 0;
BEGIN
  LOOP
    s := SYSTEM\$GET_SERVICE_STATUS('$SVC');
    IF ((CONTAINS(s, 'kw-spike:$TAG') AND CONTAINS(s, '"READY"')) OR CONTAINS(s, '"FAILED"') OR i >= 60) THEN
      RETURN s;
    END IF;
    SELECT SYSTEM\$WAIT(5);
    i := i + 1;
  END LOOP;
END;
\$\$;
SHOW ENDPOINTS IN SERVICE $SVC;
SQLEOF
out=$(snow sql -c "$CONN" -f "$SQL")
echo "$out"
t2=$(date +%s)
echo "image $TAG: build+push $((t1 - t0))s, rollout $((t2 - t1))s"
# Match the status JSON, not the echoed SQL (which also names the tag and READY).
[[ "$out" == *"kw-spike:$TAG\",\"restartCount"* && "$out" == *'"status":"READY"'* ]] \
  || { echo "not READY on $TAG; see: snow spcs service logs $SVC --container-name web --instance-id 0 -c $CONN"; exit 1; }
