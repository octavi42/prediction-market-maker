"""Generate charts for the README from benchmark results."""
from __future__ import annotations
import json
import os

def generate_charts():
    results_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark_results.json")
    if not os.path.exists(results_path):
        print("Run benchmark.py first to generate results.")
        return

    with open(results_path) as f:
        results = [r for r in json.load(f) if r.get("mean_edge") is not None]

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker
    except ImportError:
        print("pip install matplotlib to generate charts")
        return

    # ── Chart 1: Score Progression ──
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#0d1117')

    versions = [r["version"] for r in results]
    edges = [r["mean_edge"] for r in results]
    descriptions = [r["description"] for r in results]

    # Color gradient from red to green
    colors = []
    max_edge = max(edges)
    min_edge = min(edges)
    for e in edges:
        t = (e - min_edge) / (max_edge - min_edge) if max_edge > min_edge else 0.5
        r = int(255 * (1 - t))
        g = int(255 * t)
        colors.append(f'#{r:02x}{g:02x}40')

    bars = ax.bar(versions, edges, color=colors, edgecolor='#30363d', linewidth=0.5, width=0.6)

    # Add value labels on bars
    for bar, edge, desc in zip(bars, edges, descriptions):
        if edge >= 0:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.8,
                    f'${edge:.1f}', ha='center', va='bottom', fontsize=11,
                    fontweight='bold', color='#e6edf3')
        else:
            ax.text(bar.get_x() + bar.get_width() / 2, edge - 1.5,
                    f'${edge:.1f}', ha='center', va='top', fontsize=11,
                    fontweight='bold', color='#f85149')
        label = desc.split(':')[-1].strip() if ':' in desc else desc
        label_y = max(edge / 2, 2) if edge > 5 else 5
        if edge > 10:
            ax.text(bar.get_x() + bar.get_width() / 2, label_y,
                    label, ha='center', va='center', fontsize=7,
                    color='#e6edf3', rotation=90, alpha=0.8)

    ax.set_ylabel('Mean Edge ($)', fontsize=12, color='#e6edf3')
    ax.set_title('Strategy Evolution: From $0 to #3 on the Leaderboard',
                 fontsize=14, fontweight='bold', color='#e6edf3', pad=15)
    ax.tick_params(colors='#8b949e')
    ax.spines['bottom'].set_color('#30363d')
    ax.spines['left'].set_color('#30363d')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter('$%.0f'))
    ax.set_ylim(min(min(edges) * 1.3, -2), max(edges) * 1.15)

    plt.tight_layout()
    chart_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "score_progression.png")
    fig.savefig(chart_path, dpi=150, bbox_inches='tight', facecolor='#0d1117')
    print(f"Score progression chart saved to {chart_path}")
    plt.close()

    # ── Chart 2: Edge Breakdown (Retail vs Arb) ──
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#0d1117')

    retail = [r["mean_retail_edge"] for r in results]
    arb = [r["mean_arb_edge"] for r in results]
    x = range(len(versions))

    ax.bar(x, retail, color='#238636', edgecolor='#30363d', linewidth=0.5,
           width=0.6, label='Retail Edge (profit)')
    ax.bar(x, arb, color='#da3633', edgecolor='#30363d', linewidth=0.5,
           width=0.6, label='Arb Edge (cost)')

    for i, (re, ae) in enumerate(zip(retail, arb)):
        ax.text(i, re + 1, f'+${re:.0f}', ha='center', va='bottom',
                fontsize=9, color='#3fb950', fontweight='bold')
        ax.text(i, ae - 1, f'-${abs(ae):.0f}', ha='center', va='top',
                fontsize=9, color='#f85149', fontweight='bold')

    ax.set_xticks(list(x))
    ax.set_xticklabels(versions)
    ax.set_ylabel('Edge ($)', fontsize=12, color='#e6edf3')
    ax.set_title('Edge Breakdown: Retail Profit vs Arbitrageur Cost',
                 fontsize=14, fontweight='bold', color='#e6edf3', pad=15)
    ax.tick_params(colors='#8b949e')
    ax.spines['bottom'].set_color('#30363d')
    ax.spines['left'].set_color('#30363d')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.axhline(y=0, color='#484f58', linewidth=0.5, linestyle='--')
    ax.legend(loc='upper left', facecolor='#161b22', edgecolor='#30363d',
              labelcolor='#e6edf3')

    plt.tight_layout()
    chart_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edge_breakdown.png")
    fig.savefig(chart_path, dpi=150, bbox_inches='tight', facecolor='#0d1117')
    print(f"Edge breakdown chart saved to {chart_path}")
    plt.close()

if __name__ == "__main__":
    generate_charts()
