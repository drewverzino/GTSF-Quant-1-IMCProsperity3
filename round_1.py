from datamodel import Order, OrderDepth, TradingState
from typing import Dict, List, Deque
from collections import deque
import jsonpickle
import statistics as stats

class Trader:
    LIMITS = {
        "RAINFOREST_RESIN": 50,
        "KELP": 50,
        "SQUID_INK": 50
    }

    # Resin Parameters
    RESIN_ALPHA = 0.1
    RESIN_EDGE = 1
    PASSIVE_QTY = 12
    INV_SKEW = 0.03

    # Squid Ink Pair Trading Params
    SQUID_WINDOW = 100
    SQUID_SPREAD_THRESHOLD = 2.5
    SQUID_TRADE_SIZE = 5

    @staticmethod
    def _best(depth: OrderDepth):
        bid = max(depth.buy_orders.items()) if depth.buy_orders else (None, 0)
        ask = min(depth.sell_orders.items()) if depth.sell_orders else (None, 0)
        return bid, ask

    def run(self, state: TradingState):
        mem = jsonpickle.decode(state.traderData) if state.traderData else {}
        results: Dict[str, List[Order]] = {}

        for prod, depth in state.order_depths.items():
            orders: List[Order] = []
            (bid_px, bid_qty), (ask_px, ask_qty) = self._best(depth)
            if bid_px is None or ask_px is None:
                continue

            mid = (bid_px + ask_px) / 2
            pos = state.position.get(prod, 0)
            lim = self.LIMITS.get(prod, 0)

            # ─── RAINFOREST_RESIN: Market Making ─────────────────────
            if prod == "RAINFOREST_RESIN":
                fv_prev = mem.setdefault("fv_resin", mid)
                fv = self.RESIN_ALPHA * mid + (1 - self.RESIN_ALPHA) * fv_prev
                mem["fv_resin"] = fv

                skew = self.INV_SKEW * (pos / lim) * self.RESIN_EDGE * 2
                bid_target = int(fv - self.RESIN_EDGE - skew)
                ask_target = int(fv + self.RESIN_EDGE - skew)

                # Cross opportunities
                if ask_px < bid_target and pos < lim:
                    qty = min(-ask_qty, lim - pos)
                    if qty > 0:
                        orders.append(Order(prod, ask_px, qty))
                if bid_px > ask_target and pos > -lim:
                    qty = min(bid_qty, lim + pos)
                    if qty > 0:
                        orders.append(Order(prod, bid_px, -qty))

                # Passive quotes
                if (lim - pos) > 0:
                    orders.append(Order(prod, bid_target, min(self.PASSIVE_QTY, lim - pos)))
                if (lim + pos) > 0:
                    orders.append(Order(prod, ask_target, -min(self.PASSIVE_QTY, lim + pos)))

            # ─── KELP: Temporarily Disabled ─────────────────────────
            elif prod == "KELP":
                continue  # Do not trade kelp for now

            # ─── SQUID_INK: Pair Trading via Spread Reversion ──────
            elif prod == "SQUID_INK":
                paired_mid = (state.order_depths["KELP"].buy_orders and state.order_depths["KELP"].sell_orders)
                if not paired_mid:
                    continue

                # Squid mid and rolling window
                roll: Deque[float] = mem.setdefault("squid_roll", deque(maxlen=self.SQUID_WINDOW))
                roll.append(mid)

                if len(roll) < self.SQUID_WINDOW:
                    continue

                mean_price = stats.mean(roll)
                deviation = mid - mean_price

                if deviation > self.SQUID_SPREAD_THRESHOLD and pos > -lim:
                    qty = min(self.SQUID_TRADE_SIZE, lim + pos)
                    orders.append(Order(prod, bid_px, -qty))  # Sell high
                elif deviation < -self.SQUID_SPREAD_THRESHOLD and pos < lim:
                    qty = min(self.SQUID_TRADE_SIZE, lim - pos)
                    orders.append(Order(prod, ask_px, qty))  # Buy low

            results[prod] = orders

        return results, 0, jsonpickle.encode(mem)
