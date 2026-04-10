"""v74: Monopoly Breakthrough — Mean edge: $40.64 (up from -$2.59)
THE pivotal version. When competitor quotes vanish on one side, the true
price is near 0 or 1. Instead of doing nothing, build an aggressive
single-sided ladder. Retail has no choice but to trade with us.
This single change went from negative to +$40 mean edge."""
from __future__ import annotations
import math
from orderbook_pm_challenge.strategy import BaseStrategy
from orderbook_pm_challenge.types import CancelAll, PlaceOrder, Side, StepState

class Strategy(BaseStrategy):
    def __init__(self):
        self.max_position = 1000
        self.prev_mid = None
        self.vol_ema = 1.0
        self.vol_alpha = 0.10
    @staticmethod
    def _phi_factor(prob):
        d = abs(prob - 0.5)
        if d > 0.45: return 0.20
        if d > 0.40: return 0.35
        if d > 0.35: return 0.50
        if d > 0.30: return 0.65
        if d > 0.20: return 0.82
        if d > 0.10: return 0.93
        return 1.0
    def on_step(self, state):
        comp_bid = state.competitor_best_bid_ticks
        comp_ask = state.competitor_best_ask_ticks
        actions = [CancelAll()]
        if comp_bid is None or comp_ask is None:
            net_inv = state.yes_inventory - state.no_inventory
            max_pos = float(self.max_position)
            if state.steps_remaining < 200:
                max_pos = max(1.0, self.max_position * state.steps_remaining / 200)
            usable_cash = state.free_cash * 0.9
            if comp_bid is None and comp_ask is not None:
                prob_est = max(0.005, (comp_ask - 2) / 100.0)
                base_size = max(20.0, 38.0 / max(0.005, prob_est))
                max_tick = min(5, comp_ask - 1)
                for tick in range(1, max_tick + 1):
                    frac = 1.0 if tick <= 2 else 0.5
                    sz = min(base_size * frac, max(0.0, max_pos - net_inv))
                    if sz >= 0.01:
                        cost = tick / 100.0 * sz
                        if cost < usable_cash:
                            actions.append(PlaceOrder(side=Side.BUY, price_ticks=tick, quantity=sz))
                            net_inv += sz
                            usable_cash -= cost
                ask_tick = comp_ask - 1 if comp_ask >= 3 else None
                if ask_tick is not None:
                    ss = min(base_size * 0.35, max(0.0, max_pos + (state.yes_inventory - state.no_inventory)))
                    sell_collateral = (1.0 - ask_tick / 100.0) * max(0, ss - state.yes_inventory)
                    if ss >= 0.01 and sell_collateral < usable_cash:
                        actions.append(PlaceOrder(side=Side.SELL, price_ticks=ask_tick, quantity=ss))
            elif comp_ask is None and comp_bid is not None:
                prob_est = min(0.995, (comp_bid + 2) / 100.0)
                base_size = max(20.0, 38.0 / max(0.005, 1.0 - prob_est))
                min_tick = max(95, comp_bid + 1)
                for tick in range(99, min_tick - 1, -1):
                    frac = 1.0 if tick >= 98 else 0.5
                    ss = min(base_size * frac, max(0.0, max_pos + net_inv))
                    if ss >= 0.01:
                        sell_collateral = (1.0 - tick / 100.0) * ss
                        if sell_collateral < usable_cash:
                            actions.append(PlaceOrder(side=Side.SELL, price_ticks=tick, quantity=ss))
                            net_inv -= ss
                            usable_cash -= sell_collateral
                bid_tick = comp_bid + 1 if comp_bid <= 97 else None
                if bid_tick is not None:
                    bs = min(base_size * 0.35, max(0.0, max_pos - (state.yes_inventory - state.no_inventory)))
                    if bs >= 0.01:
                        cost = bid_tick / 100.0 * bs
                        if cost < usable_cash:
                            actions.append(PlaceOrder(side=Side.BUY, price_ticks=bid_tick, quantity=bs))
            return actions
        mid = (comp_bid + comp_ask) / 2.0
        comp_spread = comp_ask - comp_bid
        if self.prev_mid is not None:
            self.vol_ema = self.vol_alpha * abs(mid - self.prev_mid) + (1.0 - self.vol_alpha) * self.vol_ema
        self.prev_mid = mid
        s_value = (comp_spread - 2) / 2.0
        if s_value < 0.5:
            return actions
        prob_est = max(0.02, min(0.98, mid / 100.0))
        pf = self._phi_factor(prob_est)
        h = max(1.0, float(state.steps_remaining))
        sigma_est = max(pf * 39.9 / math.sqrt(h), self.vol_ema)
        z = s_value / sigma_est
        if s_value >= 1.5:
            if z < 0.5: return actions
        else:
            if z < 0.6: return actions
        net_inv = state.yes_inventory - state.no_inventory
        max_pos = float(self.max_position)
        if state.steps_remaining < 200:
            max_pos = max(1.0, self.max_position * state.steps_remaining / 200)
        size = max(5.0, 24.0 * (z / 1.15) ** 2)
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
        bid = max(1, comp_bid + 1 - bid_skew)
        ask = min(99, comp_ask - 1 + ask_skew)
        if bid >= ask:
            return actions
        # No artificial 0.45 cap — just check actual cash
        if bid > comp_bid:
            buy_size = max(0.0, min(size, max_pos - net_inv))
            if buy_size >= 0.01:
                cost = bid / 100.0 * buy_size
                if cost < state.free_cash:
                    actions.append(PlaceOrder(side=Side.BUY, price_ticks=bid, quantity=buy_size))
        if ask < comp_ask:
            sell_size = max(0.0, min(size, max_pos + net_inv))
            if sell_size >= 0.01:
                actions.append(PlaceOrder(side=Side.SELL, price_ticks=ask, quantity=sell_size))
        return actions
