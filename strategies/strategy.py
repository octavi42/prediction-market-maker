from __future__ import annotations
import math
from orderbook_pm_challenge.strategy import BaseStrategy
from orderbook_pm_challenge.types import CancelAll, PlaceOrder, Side, StepState
class Strategy(BaseStrategy):
    def __init__(self):
        self.max_position = 3000; self.prev_mid = None; self.vol_ema = 1.0; self.vol_alpha = 0.10
    @staticmethod
    def _pf(p):
        d = abs(p - 0.5)
        if d > 0.45: return 0.20
        if d > 0.40: return 0.35
        if d > 0.35: return 0.50
        if d > 0.30: return 0.65
        if d > 0.20: return 0.82
        if d > 0.10: return 0.93
        return 1.0
    def on_step(self, state):
        cb = state.competitor_best_bid_ticks; ca = state.competitor_best_ask_ticks
        actions = [CancelAll()]
        if cb is None or ca is None:
            ni = state.yes_inventory - state.no_inventory; mp = float(self.max_position)
            if state.steps_remaining < 200: mp = max(1.0, self.max_position * state.steps_remaining / 200)
            uc = state.free_cash * 0.9
            if cb is None and ca is not None:
                pe = max(0.005, (ca-2)/100.0); bs = max(20.0, 85.0/max(0.005,pe))
                for t in range(1, min(6, ca)):
                    f = 1.0 if t <= 2 else 0.5; sz = min(bs*f, max(0.0, mp-ni))
                    if sz >= 0.01:
                        c = t/100.0*sz
                        if c < uc: actions.append(PlaceOrder(side=Side.BUY, price_ticks=t, quantity=sz)); ni+=sz; uc-=c
                at = ca-1 if ca >= 3 else None
                if at:
                    ss = min(bs*0.35, max(0.0, mp+(state.yes_inventory-state.no_inventory)))
                    if ss >= 0.01 and (1.0-at/100.0)*max(0,ss-state.yes_inventory) < uc:
                        actions.append(PlaceOrder(side=Side.SELL, price_ticks=at, quantity=ss))
            elif ca is None and cb is not None:
                pe = min(0.995, (cb+2)/100.0); bs = max(20.0, 85.0/max(0.005,1.0-pe))
                for t in range(99, max(94, cb), -1):
                    f = 1.0 if t >= 98 else 0.5; ss = min(bs*f, max(0.0, mp+ni))
                    if ss >= 0.01:
                        sc = (1.0-t/100.0)*ss
                        if sc < uc: actions.append(PlaceOrder(side=Side.SELL, price_ticks=t, quantity=ss)); ni-=ss; uc-=sc
                bt = cb+1 if cb <= 97 else None
                if bt:
                    bsz = min(bs*0.35, max(0.0, mp-(state.yes_inventory-state.no_inventory)))
                    if bsz >= 0.01:
                        c = bt/100.0*bsz
                        if c < uc: actions.append(PlaceOrder(side=Side.BUY, price_ticks=bt, quantity=bsz))
            return actions
        mid = (cb+ca)/2.0; cs = ca-cb
        if self.prev_mid is not None: self.vol_ema = self.vol_alpha*abs(mid-self.prev_mid)+(1.0-self.vol_alpha)*self.vol_ema
        self.prev_mid = mid
        sv = (cs-2)/2.0
        if sv < 0.5: return actions
        pe = max(0.02, min(0.98, mid/100.0)); pf = self._pf(pe)
        h = max(1.0, float(state.steps_remaining)); se = max(pf*39.9/math.sqrt(h), self.vol_ema)
        z = sv/se
        if (sv >= 3.0 and z < 0.4) or (sv < 3.0 and z < 0.8): return actions
        ni = state.yes_inventory-state.no_inventory; mp = float(self.max_position)
        if state.steps_remaining < 200: mp = max(1.0, self.max_position*state.steps_remaining/200)
        size = max(10.0, 14.0/max(pe, 0.05))
        sr = min(0.08, 2.8/max(5.0, size))
        if ni > 0: bsk = int(round(ni*sr)); ask = 0
        elif ni < 0: bsk = 0; ask = int(round(abs(ni)*sr))
        else: bsk = 0; ask = 0
        b = max(1, cb+1-bsk); a = min(99, ca-1+ask)
        if b >= a: return actions
        if b > cb:
            bsz = max(0.0, min(size, mp-ni))
            if bsz >= 0.01 and b/100.0*bsz < state.free_cash:
                actions.append(PlaceOrder(side=Side.BUY, price_ticks=b, quantity=bsz))
        if a < ca:
            ssz = max(0.0, min(size, mp+ni))
            if ssz >= 0.01: actions.append(PlaceOrder(side=Side.SELL, price_ticks=a, quantity=ssz))
        return actions
