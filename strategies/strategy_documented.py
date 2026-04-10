"""
Prediction Market Challenge - Winning Strategy (v109)
=====================================================
Placed #2 in Paradigm's Automated Research Hackathon (April 2026)

A market-making strategy for a binary prediction market order book.
Captures edge from retail order flow while minimizing losses to an
omniscient arbitrageur.

Two regimes:
  1. MONOPOLY — when competitor quotes vanish on one side, become the
     sole liquidity provider at extreme prices. This is where ~60% of
     total edge comes from.
  2. NORMAL — when both sides are quoted, place orders inside the
     competitor's spread, filtered by a z-score volatility model.

Key design principles:
  - Size inversely proportional to probability (14/prob) to match
    expected retail notional at every price level
  - Z-score filtering prevents quoting when spreads are stale
    (arbitrageur would sweep us)
  - Inventory skew widens our spread on the heavy side to encourage
    mean-reversion
  - Position limits scale down linearly near expiry to avoid
    settlement risk
"""

from __future__ import annotations
import math
from orderbook_pm_challenge.strategy import BaseStrategy
from orderbook_pm_challenge.types import CancelAll, PlaceOrder, Side, StepState


class Strategy(BaseStrategy):

    def __init__(self):
        self.max_position = 3000       # max net inventory (YES - NO)
        self.prev_mid = None           # previous midpoint for vol tracking
        self.vol_ema = 1.0             # exponential moving average of |mid changes|
        self.vol_alpha = 0.10          # EMA decay rate

    # ── Probability adjustment factor ──────────────────────────────
    # Near p=0.5 the market is most uncertain → full-size quotes.
    # Near p=0 or p=1 the true prob barely moves → scale down to
    # avoid getting picked off by the arbitrageur on stale quotes.
    @staticmethod
    def _phi_factor(prob: float) -> float:
        d = abs(prob - 0.5)
        if d > 0.45: return 0.20
        if d > 0.40: return 0.35
        if d > 0.35: return 0.50
        if d > 0.30: return 0.65
        if d > 0.20: return 0.82
        if d > 0.10: return 0.93
        return 1.0

    def on_step(self, state: StepState):
        comp_bid = state.competitor_best_bid_ticks
        comp_ask = state.competitor_best_ask_ticks
        actions = [CancelAll()]  # always cancel stale orders first

        # ══════════════════════════════════════════════════════════
        # REGIME 1: MONOPOLY
        # When the competitor has no bid or no ask, the true price
        # is near 0 or 1. We become the sole liquidity provider.
        # Retail MUST trade with us. Edge per fill is massive.
        # ══════════════════════════════════════════════════════════
        if comp_bid is None or comp_ask is None:
            net_inv = state.yes_inventory - state.no_inventory
            max_pos = float(self.max_position)

            # Wind down position near expiry to avoid settlement risk
            if state.steps_remaining < 200:
                max_pos = max(1.0, self.max_position * state.steps_remaining / 200)

            usable_cash = state.free_cash * 0.9  # keep 10% cash buffer

            # ── No competitor bid → price near 0 → buy cheap YES ──
            if comp_bid is None and comp_ask is not None:
                prob_est = max(0.005, (comp_ask - 2) / 100.0)
                # Monopoly sizing: 85/prob gives huge sizes at low prob
                # (where our edge per share is highest)
                base_size = max(20.0, 85.0 / max(0.005, prob_est))

                # Place buy orders at ticks 1-5 (prices $0.01 - $0.05)
                for tick in range(1, min(6, comp_ask)):
                    frac = 1.0 if tick <= 2 else 0.5
                    sz = min(base_size * frac, max(0.0, max_pos - net_inv))
                    if sz >= 0.01:
                        cost = tick / 100.0 * sz
                        if cost < usable_cash:
                            actions.append(PlaceOrder(
                                side=Side.BUY, price_ticks=tick, quantity=sz
                            ))
                            net_inv += sz
                            usable_cash -= cost

                # Also place a sell order just below competitor's ask
                # to capture any retail selling into us
                ask_tick = comp_ask - 1 if comp_ask >= 3 else None
                if ask_tick:
                    ss = min(base_size * 0.35, max(0.0, max_pos + (state.yes_inventory - state.no_inventory)))
                    if ss >= 0.01 and (1.0 - ask_tick / 100.0) * max(0, ss - state.yes_inventory) < usable_cash:
                        actions.append(PlaceOrder(
                            side=Side.SELL, price_ticks=ask_tick, quantity=ss
                        ))

            # ── No competitor ask → price near 1 → sell expensive YES ──
            elif comp_ask is None and comp_bid is not None:
                prob_est = min(0.995, (comp_bid + 2) / 100.0)
                base_size = max(20.0, 85.0 / max(0.005, 1.0 - prob_est))

                # Place sell orders at ticks 99-95 (prices $0.99 - $0.95)
                for tick in range(99, max(94, comp_bid), -1):
                    frac = 1.0 if tick >= 98 else 0.5
                    ss = min(base_size * frac, max(0.0, max_pos + net_inv))
                    if ss >= 0.01:
                        sell_cost = (1.0 - tick / 100.0) * ss
                        if sell_cost < usable_cash:
                            actions.append(PlaceOrder(
                                side=Side.SELL, price_ticks=tick, quantity=ss
                            ))
                            net_inv -= ss
                            usable_cash -= sell_cost

                # Also place a buy order just above competitor's bid
                bid_tick = comp_bid + 1 if comp_bid <= 97 else None
                if bid_tick:
                    bsz = min(base_size * 0.35, max(0.0, max_pos - (state.yes_inventory - state.no_inventory)))
                    if bsz >= 0.01:
                        cost = bid_tick / 100.0 * bsz
                        if cost < usable_cash:
                            actions.append(PlaceOrder(
                                side=Side.BUY, price_ticks=bid_tick, quantity=bsz
                            ))

            return actions

        # ══════════════════════════════════════════════════════════
        # REGIME 2: NORMAL (both competitor bid and ask present)
        # Quote inside the competitor's spread to get FIFO priority.
        # Only quote when the spread is wide enough to be profitable
        # after accounting for adverse selection from the arbitrageur.
        # ══════════════════════════════════════════════════════════
        mid = (comp_bid + comp_ask) / 2.0
        comp_spread = comp_ask - comp_bid

        # Track volatility via EMA of absolute mid changes
        if self.prev_mid is not None:
            self.vol_ema = (self.vol_alpha * abs(mid - self.prev_mid)
                           + (1.0 - self.vol_alpha) * self.vol_ema)
        self.prev_mid = mid

        # spread_value: how many ticks of "excess" spread beyond the
        # minimum 2-tick competitor spread. This is our potential edge.
        spread_value = (comp_spread - 2) / 2.0
        if spread_value < 0.5:
            return actions  # spread too tight, no edge available

        # ── Volatility-adjusted z-score filter ──
        # sigma_est: our estimate of how much the mid might move
        # z = spread_value / sigma_est: edge in units of volatility
        prob_est = max(0.02, min(0.98, mid / 100.0))
        phi = self._phi_factor(prob_est)
        horizon = max(1.0, float(state.steps_remaining))
        sigma_est = max(phi * 39.9 / math.sqrt(horizon), self.vol_ema)
        z = spread_value / sigma_est

        # Tiered threshold: require higher z for tight spreads
        # (where arb risk per tick is proportionally larger)
        if (spread_value >= 3.0 and z < 0.4) or (spread_value < 3.0 and z < 0.8):
            return actions  # not enough edge relative to volatility

        # ── Position management ──
        net_inv = state.yes_inventory - state.no_inventory
        max_pos = float(self.max_position)
        if state.steps_remaining < 200:
            max_pos = max(1.0, self.max_position * state.steps_remaining / 200)

        # ── Order sizing ──
        # Retail-matching: size = 14/prob makes our order size match
        # the expected retail fill at each probability level.
        # Bigger than retail → excess shares get swept by arb (negative edge).
        # Smaller than retail → we leave edge on the table.
        size = max(10.0, 14.0 / max(prob_est, 0.05))

        # ── Inventory skew ──
        # When we're long, widen the bid (less aggressive buying)
        # When we're short, widen the ask (less aggressive selling)
        # This encourages inventory mean-reversion without fully
        # stopping one side (which would miss retail flow).
        skew_rate = min(0.08, 2.8 / max(5.0, size))
        if net_inv > 0:
            bid_skew = int(round(net_inv * skew_rate))
            ask_skew = 0
        elif net_inv < 0:
            bid_skew = 0
            ask_skew = int(round(abs(net_inv) * skew_rate))
        else:
            bid_skew = 0
            ask_skew = 0

        # Place orders inside competitor spread, adjusted for skew
        bid = max(1, comp_bid + 1 - bid_skew)
        ask = min(99, comp_ask - 1 + ask_skew)
        if bid >= ask:
            return actions  # skew pushed our quotes to cross, skip

        # ── Place buy order ──
        if bid > comp_bid:
            buy_size = max(0.0, min(size, max_pos - net_inv))
            if buy_size >= 0.01 and bid / 100.0 * buy_size < state.free_cash:
                actions.append(PlaceOrder(
                    side=Side.BUY, price_ticks=bid, quantity=buy_size
                ))

        # ── Place sell order ──
        if ask < comp_ask:
            sell_size = max(0.0, min(size, max_pos + net_inv))
            if sell_size >= 0.01:
                actions.append(PlaceOrder(
                    side=Side.SELL, price_ticks=ask, quantity=sell_size
                ))

        return actions
