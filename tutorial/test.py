from datamodel import Order, OrderDepth, TradingState
from typing import Dict, List
import jsonpickle
import statistics as stats


class Trader:
    LIMITS = {"RAINFOREST_RESIN": 50, "KELP": 50}
    ALPHA = 0.2
    BASE_EDGE = 2
    VOL_WINDOW = 20
    INV_SKEW = 0.04
    PASSIVE_SIZE = 3          # qty posted on each side

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

            # ── rolling stats & fair value ────────────────────────────────
            roll = mem.setdefault("roll", {}).setdefault(prod, [])
            roll.append(mid)
            roll[-self.VOL_WINDOW:]
            fv_prev = mem.setdefault("fv", {}).get(prod, mid)
            fv = self.ALPHA * mid + (1 - self.ALPHA) * fv_prev
            mem["fv"][prod] = fv
            sigma = stats.stdev(roll) if len(roll) > 5 else 0
            edge = self.BASE_EDGE + 0.5 * sigma

            pos, lim = state.position.get(prod, 0), self.LIMITS[prod]
            skew = self.INV_SKEW * (pos / lim) * edge * 2
            bid_target = round(fv - edge - skew)
            ask_target = round(fv + edge - skew)

            orders: List[Order] = []

            # ── 1. cross the spread when advantageous ────────────────────
            if ask_px < bid_target and pos < lim:
                qty = min(-ask_qty, lim - pos)
                orders.append(Order(prod, ask_px, qty))
            if bid_px > ask_target and pos > -lim:
                qty = min(bid_qty, lim + pos)
                orders.append(Order(prod, bid_px, -qty))

            # ── 2. always quote passively at fv±edge ─────────────────────
            # cancel/replace logic is unnecessary – engine cancels resting
            passive_bid_qty = min(self.PASSIVE_SIZE, lim - pos)
            passive_ask_qty = min(self.PASSIVE_SIZE, lim + pos)
            if passive_bid_qty > 0:
                orders.append(Order(prod, bid_target, passive_bid_qty))
            if passive_ask_qty > 0:
                orders.append(Order(prod, ask_target, -passive_ask_qty))

            results[prod] = orders
            print(f"{state.timestamp} {prod} fv={fv:.1f} "
                  f"bidT={bid_target} askT={ask_target} pos={pos}")

        return results, 0, jsonpickle.encode(mem)
