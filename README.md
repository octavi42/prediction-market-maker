<p align="center">
  <img src="analysis/score_progression.png" alt="Strategy Evolution Chart" width="700">
</p>

<p align="center">
  <strong>A market-making strategy that placed #2 in Paradigm's Prediction Market Challenge</strong>
  <br>
  <em>110 strategy iterations. 8 hours. One hackathon.</em>
</p>

<p align="center">
  <a href="#how-the-market-works">How It Works</a> &bull;
  <a href="#the-strategy">Strategy</a> &bull;
  <a href="#key-discoveries">Discoveries</a> &bull;
  <a href="#what-failed">Failures</a> &bull;
  <a href="#quickstart">Run It</a>
</p>

---

## Results

| Metric | Value |
|--------|-------|
| **Final Placement** | **#2** out of all submissions |
| **Final Score** | $41.09 mean edge per simulation |
| **Strategy Iterations** | 110 versions |
| **Development Time** | 8 hours |
| **Edge Source** | ~60% monopoly regime, ~40% normal regime |

<details>
<summary>Final Leaderboard</summary>

| Rank | Author | Mean Edge |
|------|--------|-----------|
| #1 | @ryanli | $42.32 |
| **#2** | **@octavicristea** | **$41.09** |
| #3 | @zhimao_liu | $40.81 |
| #4 | @onurakpolat | $24.87 |
| #5 | @ChinesePowered | $23.90 |

</details>

## What You'll Learn

This repo is a complete case study in **market making for prediction markets** — the mechanics of quoting, adverse selection, inventory risk, and how to size orders. Useful background if you're interested in prediction market microstructure or quantitative trading concepts.

- **How market makers profit** — capturing the spread between uninformed flow and true probability
- **The monopoly regime** — the single insight worth more than 100 parameter tweaks
- **Why sizing matters more than you think** — and how to match expected retail order flow
- **Volatility-adjusted quote filtering** — when to quote and when to sit out
- **Inventory management** — how skew prevents catastrophic losses (removing it = -$7 swing)

## The Challenge

[Paradigm's Automated Research Hackathon](https://www.optimizationarena.com/hackathon) (April 9, 2026) challenged participants to build a market-making strategy for a simulated binary prediction market.

**The setup:**
- A binary YES/NO contract that settles to $1 or $0
- A FIFO limit order book with integer tick prices (1-99 cents)
- Your strategy can only place **passive** (limit) orders
- 2,000 steps per simulation, scored across many simulations

**Scoring** is based on **edge** — how good your fill price was compared to the true probability at the moment of the fill. This is not P&L; it measures pure pricing skill:
```
Buy edge  = quantity x (true_probability - fill_price)
Sell edge = quantity x (fill_price - true_probability)
```
Positive edge = you bought below fair value or sold above it. The final score is the **mean total edge across all simulations**.

## How the Market Works

Every step, four agents interact with the order book in this order:

```
    ┌──────────────────────────────────────────────┐
    │              Each Step (in order)              │
    │                                                │
    │  1. Competitor replenishes its ladder           │
    │  2. YOUR STRATEGY places/cancels orders         │
    │  3. True probability updates (random walk)      │
    │  4. Arbitrageur sweeps mispriced orders          │
    │  5. Retail sends random market orders            │
    │  6. Fills recorded, edge computed                │
    └──────────────────────────────────────────────┘
```

**The agents you're competing against:**

| Agent | Behavior | Impact on You |
|-------|----------|---------------|
| **Competitor** | Static hidden ladder on both sides. Replenishes consumed levels. | Sets the baseline spread you must beat. |
| **Arbitrageur** | Knows the true probability. Sweeps every mispriced order **before** retail arrives. | Your enemy. Every bad quote gets taken at a loss. |
| **Retail** | Random market orders, ~0.25/step, ~$4.5 mean notional. | Your profit source. Uninformed flow = positive edge. |

**The core tension:** Every order you place will be seen by the arbitrageur first. If your price is wrong, the arb takes it. Only the orders that survive the arb get filled by retail (where you make money).

<img src="analysis/edge_breakdown.png" alt="Edge Breakdown: Retail vs Arb" width="700">

*Green = edge earned from retail fills (profit). Red = edge lost to arbitrageur fills (cost of doing business). Net = your score.*

## The Strategy

> Full documented code: [`strategies/strategy_documented.py`](strategies/strategy_documented.py)
> Competition submission: [`strategies/strategy.py`](strategies/strategy.py)

The strategy operates in two distinct regimes:

### Regime 1: Monopoly (60% of total edge)

When the competitor's bid or ask disappears, the true price is near 0 or 1. **We become the only liquidity provider.** Retail has no choice but to trade with us at our prices.

```python
# Price near 0 → buy YES shares for almost nothing
# Size inversely proportional to probability: 85/prob
# At prob=0.02, we post 4,250 shares at $0.01-$0.05
base_size = max(20.0, 85.0 / max(0.005, prob_est))

for tick in range(1, min(6, comp_ask)):
    # Full size at ticks 1-2, half size at 3-5
    frac = 1.0 if tick <= 2 else 0.5
    sz = min(base_size * frac, max(0.0, max_pos - net_inv))
```

Why this works: at extreme prices, the arbitrageur has nothing to sweep — our quotes are on the right side of true value. Every retail fill is pure profit.

### Regime 2: Normal (40% of total edge)

When both sides are present, we quote inside the competitor's spread — but only when it's profitable.

**Z-score filter:** We estimate how much the true probability might move (volatility) and only quote when the available spread is wide enough to justify the risk:

```python
spread_value = (comp_spread - 2) / 2.0  # excess spread beyond minimum
sigma_est = max(phi_factor * 39.9 / sqrt(steps_remaining), vol_ema)
z = spread_value / sigma_est  # edge in units of volatility

# Tiered threshold: stricter for tight spreads (higher arb risk per tick)
if spread_value >= 3.0 and z < 0.4: return  # skip
if spread_value <  3.0 and z < 0.8: return  # skip
```

**Retail-matching sizing:** Order size = `14/prob`, which matches the expected retail fill size at each probability level. Post more than retail will fill → excess shares get swept by the arb. Post less → leaving edge on the table.

**Inventory skew:** When net inventory builds up, we widen our quote on the heavy side to encourage mean-reversion:

```python
skew_rate = min(0.08, 2.8 / max(5.0, size))
bid_skew = int(round(net_inv * skew_rate)) if net_inv > 0 else 0
```

**A note on the magic numbers:** Constants like `39.9`, `85`, `0.08`, and `2.8` were not derived analytically — they were found through systematic parameter sweeps across hundreds of simulations. The [evolution milestones](strategies/evolution/) show how these values converged. Interestingly, the volatility formula `phi_factor * 39.9 / sqrt(steps_remaining)` independently converged on the same structure as the [analytical solution](https://www.paradigm.xyz/2024/11/pm-amm) from Paradigm's pm-AMM paper, where volatility is determined by price and time to expiry.

## Key Discoveries

### 1. The Monopoly Regime is Everything

Before discovering monopoly mode (v60), the strategy earned ~$15/sim from retail but lost ~$24/sim to the arb — net negative. After adding monopoly: net **+$40/sim**. One regime change flipped the entire strategy from losing to winning.

When the competitor's quotes vanish on one side, the true probability is extreme (near 0 or 1). The arbitrageur has nothing to sweep because our prices are already on the right side of true value.

### 2. Size = 85/prob in Monopoly

The monopoly sizing formula went through many iterations:
- `38/prob` (v74): $44.41 local
- `85/prob` (v108): $46.35 local
- `100/prob`: $46.02 local (worse — cash constraints start binding)

The sweet spot is aggressive but not so aggressive that you run out of collateral.

### 3. Retail-Matching Sizing in Normal Regime

Retail fills ~$4.5 mean notional. At prob=0.5, that's ~9 shares. If we post 50 shares, 9 get filled by retail (+edge) and 41 sit there waiting to be swept by the arb (-edge).

The fix: `size = 14/prob`. At p=0.5 → size=28. At p=0.05 → size=280. This roughly matches expected retail at every price level.

### 4. Inventory Skew is Make-or-Break

Without inventory skew, the strategy score drops by **$7** (from $47 to $40). Unbounded inventory builds up on one side, and settlement risk dominates.

The skew formula `min(0.08, 2.8/size)` was found through parameter search. It widens quotes just enough to encourage mean-reversion without giving up too much retail flow.

### 5. Z-Score Filtering Saves ~$5/sim

Without the z-score filter, we'd quote on every step regardless of spread width. The arbitrageur sweeps stale quotes whenever the spread doesn't justify the risk. The tiered threshold (strict for tight spreads, loose for wide) was the final +$0.35 improvement.

## What Failed

These all scored **worse** than the final strategy. The "Delta" column shows the change vs the final v109 baseline ($46.70 local). Counter-intuitive failures are the most instructive:

| What We Tried | Expected | Delta vs Final | Why It Failed |
|---------------|----------|----------------|---------------|
| Multi-level normal quoting (5 price levels) | More fills = more edge | **-$7.50** | More arb exposure per step vastly outweighed extra retail |
| Smaller normal sizes (10/prob, 12/prob) | Less arb damage | **-$0.50 to -$1.00** | Retail fill reduction exceeded arb savings |
| No cash buffer (using 100% of cash) | More capital deployed | **-$1.20** (some seeds) | Inconsistent across seeds; cash crunch in bad scenarios |
| Adaptive z-threshold based on inventory | Smarter filtering | **-$0.30** | Added noise without improving edge/risk tradeoff |
| 3-tier z-threshold system | Finer-grained control | **$0.00** | Large-spread threshold never actually binds (z always >>0.4) |
| Higher sigma prior (45, 50) | More conservative | **-$0.20** | Filtered too many profitable opportunities |
| Monopoly size 100/prob or 120/prob | More monopoly edge | **-$0.70 to -$9.00** | Cash constraints and position limits start binding |

## Strategy Evolution

The journey from v1 to v109, with 7 milestone versions. Note that scores aren't strictly monotonic — some versions traded off one dimension to unlock gains in the next (v97 reduced normal-regime size to set up v99's retail-matching formula):

| Version | Key Change | Mean Edge | Retail | Arb | What Changed |
|---------|-----------|-----------|--------|-----|--------------|
| **v01** | Foundation | -$17.25 | +$6.87 | -$24.12 | Multi-level quoting, basic inventory skew |
| **v10** | Asymmetric skew | $4.18 | +$8.77 | -$4.59 | Only penalize the oversized side |
| **v50** | Z-score regimes | -$2.59 | +$21.24 | -$23.83 | Volatility-adjusted filtering, probability factors |
| **v74** | Monopoly discovery | **$40.64** | +$65.70 | -$25.06 | Single-sided ladder when competitor vanishes |
| **v97** | Retail optimization | $37.41 | +$54.96 | -$17.55 | Flat size=10 to minimize arb exposure |
| **v99** | Retail matching | $42.95 | +$66.26 | -$23.31 | Size = 14/prob to match retail notional |
| **v109** | Final tuning | **$46.70** | +$72.82 | -$26.11 | mono=85/prob, pos=3000, tiered z-threshold |

> All milestone versions with detailed comments are in [`strategies/evolution/`](strategies/evolution/)

## Quickstart

```bash
# 1. Install dependencies
uv sync --dev

# 2. Run the winning strategy (200 simulations)
uv run orderbook-pm run strategies/strategy.py --simulations 200 --workers 4

# 3. Run a milestone version to compare
uv run orderbook-pm run strategies/evolution/v01_foundation.py --simulations 200 --workers 4
```

### Generate Charts

```bash
# Run benchmarks for all milestone versions
python analysis/benchmark.py

# Generate charts from results
python analysis/generate_charts.py
```

### Run Tests

```bash
uv run pytest
```

## Project Structure

```
.
├── strategies/
│   ├── strategy.py              # Competition submission (minified)
│   ├── strategy_documented.py   # Same strategy, fully documented
│   └── evolution/               # 7 milestone versions showing the journey
│       ├── v01_foundation.py
│       ├── v10_asymmetric_skew.py
│       ├── v50_zscore_regimes.py
│       ├── v74_monopoly_breakthrough.py
│       ├── v97_retail_optimization.py
│       ├── v99_retail_matching.py
│       └── (v109 = strategies/strategy.py)
├── analysis/
│   ├── benchmark.py             # Run all milestones and save results
│   ├── generate_charts.py       # Generate README charts
│   └── benchmark_results.json   # Cached results
├── orderbook_pm_challenge/      # Simulation engine (provided by Paradigm)
├── docs/                        # Challenge specification
├── examples/                    # Starter strategy
└── tests/                       # Test suite
```

## Tools

Development was accelerated using [Claude Code](https://claude.ai/claude-code) for rapid iteration, parameter search, and analysis during the 8-hour hackathon window.

## License

MIT

---

<p align="center">
  If you found this useful, <a href="#">star the repo</a> — it helps others find it.
</p>
