"""Summarize hybrid_bench.py output: python3 summarize.py results.json"""
import json
import statistics
import sys


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p / 100 * (len(xs) - 1)))]


r = json.load(open(sys.argv[1]))
qh = r.get("query_history", {})
print("session", r.get("session"), "| query_history", r.get("query_history_found"), "| dropped", r.get("dropped"))
print(f"SELECT 1 round trip: p50 {statistics.median(r['round_trip_ms']):.0f} ms")
for k in ("stale_check_standard", "stale_check_hybrid"):
    c = r[k]
    print(f"{k}: outcome {c['outcome']}, rows {c.get('rows')}")
print("\nclick-to-commit (warm)      n   p50   p95   max")
for v, runs in r["warm"].items():
    t = [x["total_ms"] for x in runs]
    print(f"{v:24} {len(t):4} {pct(t, 50):5.0f} {pct(t, 95):5.0f} {max(t):5.0f}")
print("\ncold (after idle):")
for v, c in r["cold"].items():
    print(f"  {v:24} {c['total_ms']:5.0f} ms  warehouse before: {c.get('warehouse_state_before')}")
print("\nper statement, warm p50 (client ms | server total / compile / exec ms)")
for v, runs in r["warm"].items():
    print(" ", v)
    for i, name in enumerate(s[0] for s in runs[0]["steps"]):
        client = [x["steps"][i][2] for x in runs]
        rows = [qh[x["steps"][i][1]] for x in runs if x["steps"][i][1] in qh]
        server = ""
        if rows:
            server = " | " + " / ".join(
                f"{statistics.median(q[f] or 0 for q in rows):.0f}"
                for f in ("total_elapsed_time", "compilation_time", "execution_time"))
        print(f"    {name:16} {statistics.median(client):5.0f}{server}")
print("\ncold per statement (client ms | server total / compile / exec / queued_prov ms)")
for v, c in r["cold"].items():
    parts = []
    for name, qid, ms in c["steps"]:
        q = qh.get(qid)
        extra = (f" [{q['total_elapsed_time']}/{q['compilation_time']}/{q['execution_time']}"
                 f"/{q['queued_provisioning_time']}]") if q else ""
        parts.append(f"{name} {ms:.0f}{extra}")
    print(f"  {v}: " + ", ".join(parts))
