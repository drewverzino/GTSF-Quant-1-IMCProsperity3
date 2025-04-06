from datamodel import Order, OrderDepth, TradingState
from typing import Dict, List, Deque
from collections import deque
import jsonpickle
import statistics as stats


class Trader:
    LIMITS = {"RAINFOREST_RESIN": 50, "KELP": 50}

    # ── Resin parameters ────────────────────────────
    RESIN_ALPHA = 0.20
    RESIN_EDGE = 2
    PASSIVE_QTY = 3
    INV_SKEW = 0.04

    # ── Kelp parameters ─────────────────────────────
    KELP_ALPHA = 0.10
    KELP_WINDOW = 120         # ticks (~2 minutes)
    KELP_Z_THRESH = 1.2
    KELP_MEAN_SIZE = 5
    KELP_MOM_SIZE = 2
    MOMENTUM_LAG = 3           # consecutive returns

    # ── helpers ─────────────────────────────────────
    @staticmethod
    def _best(depth: OrderDepth):
        bid = max(depth.buy_orders.items()) if depth.buy_orders else (None, 0)
        ask = min(depth.sell_orders.items()
                  ) if depth.sell_orders else (None, 0)
        return bid, ask

    def run(self, state: TradingState):
        mem = jsonpickle.decode(state.traderData) if state.traderData else {}
        results: Dict[str, List[Order]] = {}

        for prod, depth in state.order_depths.items():
            (bid_px, bid_qty), (ask_px, ask_qty) = self._best(depth)
            if bid_px is None or ask_px is None:
                continue
            mid = (bid_px + ask_px) / 2
            pos, lim = state.position.get(prod, 0), self.LIMITS[prod]

            # ================= RESIN ====================
            if prod == "RAINFOREST_RESIN":
                fv_prev = mem.setdefault("fv_resin", mid)
                fv = self.RESIN_ALPHA * mid + (1 - self.RESIN_ALPHA) * fv_prev
                mem["fv_resin"] = fv

                skew = self.INV_SKEW * (pos / lim) * self.RESIN_EDGE * 2
                bid_target = int(fv - self.RESIN_EDGE - skew)

                ask_target = int(fv + self.RESIN_EDGE - skew)

                orders: List[Order] = []
                if ask_px < bid_target and pos < lim:
                    qty = min(-ask_qty, lim - pos)
                    if qty > 0:
                        orders.append(Order(prod, ask_px,  qty))
                if bid_px > ask_target and pos > -lim:
                    qty = min(bid_qty, lim + pos)
                    if qty > 0:
                        orders.append(Order(prod, bid_px, -qty))

                bid_qty = min(self.PASSIVE_QTY, lim - pos)
                if bid_qty > 0:
                    orders.append(Order(prod, bid_target,  bid_qty))
                ask_qty = min(self.PASSIVE_QTY, lim + pos)
                if ask_qty > 0:
                    orders.append(Order(prod, ask_target, -ask_qty))

                results[prod] = orders
                continue

            # ================= KELP =====================
            # rolling window for mid‑prices & returns
            roll: Deque = mem.setdefault(
                "kelp_roll", deque(maxlen=self.KELP_WINDOW))
            roll.append(mid)
            fv_prev = mem.setdefault("fv_kelp", mid)
            fv = self.KELP_ALPHA * mid + (1 - self.KELP_ALPHA) * fv_prev
            mem["fv_kelp"] = fv

            sigma = stats.stdev(roll) if len(roll) > 10 else 1
            z = (mid - fv) / sigma

            # momentum detection
            ret_hist: Deque = mem.setdefault(
                "kelp_ret", deque(maxlen=self.MOMENTUM_LAG))
            ret_hist.append(mid - roll[-2] if len(roll) > 1 else 0)
            same_sign_mom = len(ret_hist) == self.MOMENTUM_LAG and all(
                r > 0 for r in ret_hist) or all(r < 0 for r in ret_hist)

            orders: List[Order] = []

            # ---- mean‑reversion trade ----
            if abs(z) > self.KELP_Z_THRESH:
                if z > 0 and pos > -lim:               # price high → sell
                    px = int(mid) + 2                  # ensure int
                    qty = min(self.KELP_MEAN_SIZE, lim + pos)
                    if qty > 0:
                        print("SENDING", prod, px, -qty)
                        orders.append(Order(prod, px, -qty))
                if z < 0 and pos < lim:                # price low → buy
                    px = int(mid) - 2
                    qty = min(self.KELP_MEAN_SIZE, lim - pos)
                    if qty > 0:
                        print("SENDING", prod, px, qty)
                        orders.append(Order(prod, px,  qty))

            # ---- momentum cross ----
            elif same_sign_mom:
                if ret_hist[-1] > 0 and pos < lim:     # up trend → buy
                    orders.append(Order(prod, ask_px,  self.KELP_MOM_SIZE))
                if ret_hist[-1] < 0 and pos > -lim:    # down trend → sell
                    orders.append(Order(prod, bid_px, -self.KELP_MOM_SIZE))

        results[prod] = orders

        print(
            f"{state.timestamp} {prod} z={z:.2f} mom={same_sign_mom} pos={pos} orders={[(o.price,o.quantity) for o in orders]}")

        return results, 0, jsonpickle.encode(mem)
