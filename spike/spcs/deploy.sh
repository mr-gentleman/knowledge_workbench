#!/usr/bin/env bash
# Spike deploy loop: build React + API image → push → upgrade the service.
# Needs the objects in handoff.sql (Chris/CoCo) and a running podman machine (or ENGINE=docker). Usage: spike/spcs/deploy.sh [--create]
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

CONN=${KW_CONNECTION:-workbench_deploy}
ENGINE=${ENGINE:-podman}
POOL=${KW_POOL:-SYSTEM_COMPUTE_POOL_CPU}  # handoff.sql 3a; KW_POOL=KW_SPIKE_POOL for 3b
REGISTRY=activecampaign-fm00411.registry.snowflakecomputing.com
REPO_URL=$REGISTRY/ai_platform/workbench/kw_images
TAG=$(git rev-parse --short HEAD)$(git diff --quiet || echo "-dirty$(date +%s)")
SPEC=$(mktemp)
sed "s/IMAGE_TAG/$TAG/" spike/spcs/service.yaml > "$SPEC"

t0=$(date +%s)
# `snow spcs image-registry login` shells out to docker; this form works for podman too.
snow spcs image-registry token -c "$CONN" --format JSON \
  | python3 -c 'import json,re,sys; print(json.loads(re.search(r"\{.*\}", sys.stdin.read(), re.S).group(0))["token"])' \
  | $ENGINE login "$REGISTRY" --username 0sessiontoken --password-stdin
$ENGINE build --platform linux/amd64 -f spike/spcs/Dockerfile -t "$REPO_URL/kw-spike:$TAG" .
$ENGINE push "$REPO_URL/kw-spike:$TAG"
t1=$(date +%s)

if [[ "${1:-}" == "--create" ]]; then
  snow spcs service create AI_PLATFORM.WORKBENCH.KW_SPIKE -c "$CONN" \
    --compute-pool "$POOL" --spec-path "$SPEC" --query-warehouse BIZ_AI_WH
else
  snow spcs service upgrade AI_PLATFORM.WORKBENCH.KW_SPIKE -c "$CONN" --spec-path "$SPEC"
fi
# Wait for the new container to be ready (upgrade is a rolling restart).
for i in $(seq 60); do  # up to ~5 min
  status=$(snow sql -c "$CONN" --format json -q \
    "SELECT SYSTEM\$GET_SERVICE_STATUS('AI_PLATFORM.WORKBENCH.KW_SPIKE')" | grep -o '\\"status\\": *\\"[A-Z_]*' | head -1)
  echo "status: $status"
  [[ "$status" == *READY* ]] && break
  [[ "$status" == *FAILED* ]] && { echo "service FAILED; see: snow spcs service logs AI_PLATFORM.WORKBENCH.KW_SPIKE --container-name web --instance-id 0 -c $CONN"; exit 1; }
  sleep 5
done
t2=$(date +%s)
echo "image $TAG: build+push $((t1 - t0))s, rollout $((t2 - t1))s"
snow sql -c "$CONN" -q "SHOW ENDPOINTS IN SERVICE AI_PLATFORM.WORKBENCH.KW_SPIKE"
