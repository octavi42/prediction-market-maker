from __future__ import annotations

from orderbook_pm_challenge.strategy import BaseStrategy
from orderbook_pm_challenge.types import CancelAll, PlaceOrder, Side, StepState


class Strategy(BaseStrategy):
    """Adaptive market maker v1.

    Core ideas:
    - Use competitor midpoint as fair value proxy
    - Quote inside competitor spread for FIFO priority on retail
    - Inventory skew to mean-revert position
    - Position limits with late-game wind-down
    - Multi-level quoting: tight level for retail capture, wide level for safety
    """

    def __init__(self):
        self.max_position = 50
        self.prev_mid = None
        self.vol_ema = 0.0

    def on_step(self, state: StepState):
        comp_bid = state.competitor_best_bid_ticks
        comp_ask = state.competitor_best_ask_ticks

        actions = [CancelAll()]

        if comp_bid is None or comp_ask is None:
            return actions

        mid = (comp_bid + comp_ask) / 2.0
        net_inv = state.yes_inventory - state.no_inventory
        comp_spread = comp_ask - comp_bid

        # Track volatility via mid changes
        if self.prev_mid is not None:
            self.vol_ema = 0.15 * abs(mid - self.prev_mid) + 0.85 * self.vol_ema
        self.prev_mid = mid

        # Inventory skew: shift both quotes to encourage position reduction
        # When long YES (net_inv > 0): shift down → lower ask attracts buyers
        # When short YES (net_inv < 0): shift up → higher bid attracts sellers
        skew = int(round(net_inv * 0.05))

        # Position limits with late-game wind-down
        max_pos = self.max_position
        if state.steps_remaining < 300:
            max_pos = max(1, self.max_position * state.steps_remaining / 300)

        # --- Level 1: Tight quotes (inside competitor) ---
        # Goal: FIFO priority for retail flow
        if comp_spread >= 5:
            bid1 = comp_bid + 2
            ask1 = comp_ask - 2
        elif comp_spread >= 4:
            bid1 = comp_bid + 1
            ask1 = comp_ask - 1
        elif comp_spread == 3:
            bid1 = comp_bid + 1
            ask1 = comp_ask - 1
        else:
            # Tight competitor - quote at their level
            bid1 = comp_bid
            ask1 = comp_ask

        # Apply inventory skew
        bid1 = max(1, bid1 - skew)
        ask1 = min(99, ask1 - skew)

        # Ensure valid spread
        if bid1 >= ask1:
            center = round(mid)
            bid1 = max(1, center - 1)
            ask1 = min(99, center + 1)

        # Sizing for level 1
        size1 = 4.0
        buy1 = max(0.0, min(size1, max_pos - net_inv))
        sell1 = max(0.0, min(size1, max_pos + net_inv))

        if buy1 > 0:
            cost = bid1 / 100.0 * buy1
            if cost < state.free_cash:
                actions.append(
                    PlaceOrder(side=Side.BUY, price_ticks=bid1, quantity=buy1)
                )

        if sell1 > 0:
            actions.append(
                PlaceOrder(side=Side.SELL, price_ticks=ask1, quantity=sell1)
            )

        # --- Level 2: Wider quotes (at or outside competitor) ---
        # Goal: catch large retail that walks through, safer from arb
        bid2 = max(1, comp_bid - 1 - skew)
        ask2 = min(99, comp_ask + 1 - skew)

        size2 = 3.0
        buy2 = max(0.0, min(size2, max_pos - net_inv - buy1))
        sell2 = max(0.0, min(size2, max_pos + net_inv - sell1))

        if buy2 > 0 and bid2 < bid1:
            cost = bid2 / 100.0 * buy2
            if cost < state.free_cash:
                actions.append(
                    PlaceOrder(side=Side.BUY, price_ticks=bid2, quantity=buy2)
                )

        if sell2 > 0 and ask2 > ask1:
            actions.append(
                PlaceOrder(side=Side.SELL, price_ticks=ask2, quantity=sell2)
            )

        return actions
