"""v10: Asymmetric Skew — Mean edge: $4.18 (up from -$17.25)
Key change: Only penalize the oversized side of inventory.
Previously skew shifted BOTH quotes, causing us to chase bad fills."""
from __future__ import annotations
from orderbook_pm_challenge.strategy import BaseStrategy
from orderbook_pm_challenge.types import CancelAll, PlaceOrder, Side, StepState

class Strategy(BaseStrategy):
    """v10a: asymmetric skew=0.04"""
    def __init__(self):
        self.max_position = 120
    def on_step(self, state: StepState):
        comp_bid = state.competitor_best_bid_ticks
        comp_ask = state.competitor_best_ask_ticks
        actions = [CancelAll()]
        if comp_bid is None or comp_ask is None:
            return actions
        if comp_ask - comp_bid < 5:
            return actions
        net_inv = state.yes_inventory - state.no_inventory
        max_pos = float(self.max_position)
        if state.steps_remaining < 300:
            max_pos = max(1.0, self.max_position * state.steps_remaining / 300)
        if net_inv > 0:
            bid_skew = int(round(net_inv * 0.04))
            ask_skew = 0
        elif net_inv < 0:
            bid_skew = 0
            ask_skew = int(round(abs(net_inv) * 0.04))
        else:
            bid_skew = 0
            ask_skew = 0
        bid = max(1, comp_bid + 1 - bid_skew)
        ask = min(99, comp_ask - 1 + ask_skew)
        if bid >= ask:
            return actions
        size = 15.0
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
