"""Summarize save_path_bench.py output.  python3 summarize_save_path.py results.json

SPCS estimate = laptop wall time − statements × (laptop round trip − SPCS round trip). SPCS gaps between
statements measured 10–20 ms (FINDINGS.md); 15 ms is used. An estimate, not a measurement.
"""
import json
import statistics
import sys

SPCS_RTT_MS = 15
d = json.load(open(sys.argv[1]))
qh = d["query_history"]
rtt = statistics.median(d["round_trip_ms"])
print(f"laptop SELECT 1 p50 {rtt:.0f} ms; rounds {d['rounds']}; checks {d['checks']}\n")


def p(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(q * (len(xs) - 1)))]


print("| variant | save p50 | save p95 | refresh p50 | statements | server p50 (save) | SPCS est. save | SPCS est. save+refresh |")
print("|---|---|---|---|---|---|---|---|")
for key, runs in d["runs"].items():
    save = [r["save_ms"] for r in runs]
    refresh = [r["refresh_ms"] for r in runs]
    n = round(statistics.median(len(r["save_qids"]) for r in runs))
    server = [sum(qh[q]["total"] for q in r["save_qids"] if q in qh) for r in runs]
    est = statistics.median(save) - n * (rtt - SPCS_RTT_MS)
    est_r = statistics.median(refresh) - 3 * (rtt - SPCS_RTT_MS)
    print(f"| {key} | {statistics.median(save):.0f} | {p(save, .95):.0f} | {statistics.median(refresh):.0f} | {n} "
          f"| {statistics.median(server):.0f} | ~{est:.0f} | ~{est + est_r:.0f} |")
