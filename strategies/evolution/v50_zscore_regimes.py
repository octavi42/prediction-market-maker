"""v50: Z-Score Regimes — Mean edge: -$2.59 (retail +$21, arb -$24)
Key change: Only quote when spread/volatility ratio exceeds threshold.
Introduced phi_factor (probability-adjusted vol) and sigma floor.
Retail edge tripled but arb losses still dominated — needed monopoly."""
from __future__ import annotations
import math
from orderbook_pm_challenge.strategy import BaseStrategy
from orderbook_pm_challenge.types import CancelAll, PlaceOrder, Side, StepState


class Strategy(BaseStrategy):
    def __init__(self):
        self.max_position = 400.0
        self.prev_mid = None
        self.vol_ema = 1.0
        self.vol_alpha = 0.12
        self.trend_ema = 0.0

    @staticmethod
    def _clip(x, lo, hi):
        return max(lo, min(hi, x))

    @staticmethod
    def _rounded_qty(q):
        return max(0.01, round(float(q), 2))

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

    def _sigma_eff(self, mid, steps_remaining):
        prob_est = self._clip(mid / 100.0, 0.02, 0.98)
        h = max(1.0, float(steps_remaining))
        sigma_floor = self._phi_factor(prob_est) * 39.9 / math.sqrt(h)
        return max(sigma_floor, self.vol_ema)

    @staticmethod
    def _regime_params(spread):
        if spread >= 5: return 0.65, 18.0, 300.0, True
        if spread == 4: return 1.15, 12.0, 180.0, True
        if spread == 3: return 1.25, 8.0, 100.0, True
        if spread == 2: return 1.00, 6.0, 60.0, False
        return None

    def _buy_capacity(self, price_ticks, free_cash):
        if price_ticks <= 0: return 0.0
        return max(0.0, free_cash * 100.0 / float(price_ticks))

    def _sell_capacity(self, price_ticks, free_cash):
        liability = max(0.01, 100.0 - float(price_ticks))
        return max(0.0, free_cash * 100.0 / liability)

    def _apply_inventory_skew(self, size, side, net_inv, pos_cap):
        if pos_cap <= 0: return 0.0
        if side == Side.BUY and net_inv > 0:
            size *= max(0.35, 1.0 - net_inv / (pos_cap * 1.1))
        elif side == Side.SELL and net_inv < 0:
            size *= max(0.35, 1.0 - abs(net_inv) / (pos_cap * 1.1))
        return size

    def _size_from_z(self, z, threshold_z, base_size, size_cap, extreme=False):
        delta = max(0.0, z - threshold_z)
        size = base_size + 18.0 * (delta * delta)
        if extreme: size *= 1.20
        return min(size_cap, size)

    def on_step(self, state):
        actions = [CancelAll()]  # BUG FIX: added ()

        comp_bid = state.competitor_best_bid_ticks
        comp_ask = state.competitor_best_ask_ticks
        if comp_bid is None or comp_ask is None:
            return actions
        if comp_bid < 1 or comp_ask > 99 or comp_bid >= comp_ask:
            return actions

        spread = comp_ask - comp_bid
        params = self._regime_params(spread)
        if params is None:
            return actions
        threshold_z, base_size, size_cap, allow_two_sided = params

        mid = 0.5 * (comp_bid + comp_ask)
        if self.prev_mid is not None:
            delta_mid = mid - self.prev_mid
            self.vol_ema = (1.0 - self.vol_alpha) * self.vol_ema + self.vol_alpha * abs(delta_mid)
            self.trend_ema = 0.80 * self.trend_ema + 0.20 * delta_mid
        self.prev_mid = mid

        fair_est = self._clip(mid + 0.30 * self.trend_ema, 1.0, 99.0)
        sigma_eff = self._sigma_eff(mid, state.steps_remaining)
        net_inv = state.yes_inventory - state.no_inventory

        pos_cap = float(self.max_position)
        if state.steps_remaining < 250:
            pos_cap = max(60.0, self.max_position * float(state.steps_remaining) / 250.0)

        extreme = (mid <= 15.0) or (mid >= 85.0)

        buy_price = min(99, comp_bid + 1) if spread >= 2 else None
        sell_price = max(1, comp_ask - 1) if spread >= 2 else None
        if buy_price is None or sell_price is None:
            return actions

        buy_edge = fair_est - float(buy_price)
        sell_edge = float(sell_price) - fair_est
        buy_z = buy_edge / sigma_eff if sigma_eff > 1e-12 else 0.0
        sell_z = sell_edge / sigma_eff if sigma_eff > 1e-12 else 0.0

        if not allow_two_sided:
            if buy_z <= 0.0 and sell_z <= 0.0:
                return actions
            if buy_z > sell_z or (abs(buy_z - sell_z) < 1e-9 and net_inv <= 0):
                if buy_z >= threshold_z:
                    size = self._size_from_z(buy_z, threshold_z, base_size, size_cap, extreme)
                    size = self._apply_inventory_skew(size, Side.BUY, net_inv, pos_cap)
                    size = min(size, max(0.0, pos_cap - net_inv))
                    size = min(size, self._buy_capacity(buy_price, state.free_cash))
                    if size >= 0.01:
                        actions.append(PlaceOrder(side=Side.BUY, price_ticks=int(buy_price), quantity=self._rounded_qty(size)))
            else:
                if sell_z >= threshold_z:
                    size = self._size_from_z(sell_z, threshold_z, base_size, size_cap, extreme)
                    size = self._apply_inventory_skew(size, Side.SELL, net_inv, pos_cap)
                    size = min(size, max(0.0, pos_cap + net_inv))
                    size = min(size, self._sell_capacity(sell_price, state.free_cash))
                    if size >= 0.01:
                        actions.append(PlaceOrder(side=Side.SELL, price_ticks=int(sell_price), quantity=self._rounded_qty(size)))
            return actions

        if buy_edge > 0.0 and buy_z >= threshold_z:
            buy_size = self._size_from_z(buy_z, threshold_z, base_size, size_cap, extreme)
            buy_size = self._apply_inventory_skew(buy_size, Side.BUY, net_inv, pos_cap)
            buy_size = min(buy_size, max(0.0, pos_cap - net_inv))
            buy_size = min(buy_size, self._buy_capacity(buy_price, state.free_cash))
            if buy_size >= 0.01:
                actions.append(PlaceOrder(side=Side.BUY, price_ticks=int(buy_price), quantity=self._rounded_qty(buy_size)))

        if sell_edge > 0.0 and sell_z >= threshold_z:
            sell_size = self._size_from_z(sell_z, threshold_z, base_size, size_cap, extreme)
            sell_size = self._apply_inventory_skew(sell_size, Side.SELL, net_inv, pos_cap)
            sell_size = min(sell_size, max(0.0, pos_cap + net_inv))
            sell_size = min(sell_size, self._sell_capacity(sell_price, state.free_cash))
            if sell_size >= 0.01:
                actions.append(PlaceOrder(side=Side.SELL, price_ticks=int(sell_price), quantity=self._rounded_qty(sell_size)))

        return actions
