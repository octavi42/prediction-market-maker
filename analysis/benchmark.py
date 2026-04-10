"""Benchmark all milestone strategy versions and generate score progression chart."""
from __future__ import annotations
import os
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orderbook_pm_challenge.runner import run_batch

STRATEGIES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "strategies")
EVOLUTION_DIR = os.path.join(STRATEGIES_DIR, "evolution")

MILESTONES = [
    ("v01", "v01_foundation.py", "Foundation: multi-level quoting"),
    ("v10", "v10_asymmetric_skew.py", "Asymmetric inventory skew"),
    ("v50", "v50_zscore_regimes.py", "Z-score filtering + regimes"),
    ("v74", "v74_monopoly_breakthrough.py", "Monopoly regime discovery"),
    ("v97", "v97_retail_optimization.py", "Retail-aware sizing"),
    ("v99", "v99_retail_matching.py", "Probability-inverse sizing"),
    ("v109", os.path.join("..", "strategy.py"), "Final: tuned thresholds + max position"),
]

def run_benchmarks(n_sims=200, workers=4, seed_start=0):
    results = []
    for label, filename, description in MILESTONES:
        if filename.startswith(".."):
            path = os.path.join(STRATEGIES_DIR, "strategy.py")
        else:
            path = os.path.join(EVOLUTION_DIR, filename)

        print(f"Running {label}: {description}...", flush=True)
        try:
            r = run_batch(strategy_path=path, n_simulations=n_sims, workers=workers, seed_start=seed_start)
            neg = sum(1 for s in r.simulation_results if s.total_edge < 0)
            entry = {
                "version": label,
                "description": description,
                "mean_edge": round(r.mean_edge, 2),
                "mean_retail_edge": round(r.mean_retail_edge, 2),
                "mean_arb_edge": round(r.mean_arb_edge, 2),
                "negative_sims": neg,
                "total_sims": n_sims,
            }
            results.append(entry)
            print(f"  {label}: mean_edge=${entry['mean_edge']:.2f} (retail=${entry['mean_retail_edge']:.2f}, arb=${entry['mean_arb_edge']:.2f})")
        except Exception as e:
            print(f"  {label}: FAILED - {e}")
            results.append({"version": label, "description": description, "mean_edge": None, "error": str(e)})

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_path}")
    return results

if __name__ == "__main__":
    run_benchmarks()
