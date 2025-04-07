from datamodel import Order, OrderDepth, TradingState
from typing import Dict, List, Deque
from collections import deque
import jsonpickle
import statistics as stats

class Trader:
    # Position limits for each product.
    LIMITS = {
        "RAINFOREST_RESIN": 50,
        "KELP": 50,
        "SQUID_INK": 50  # Added limit for Squid Ink
    }

    # ── Resin (RAINFOREST_RESIN) parameters ───────────────────────────
    RESIN_ALPHA = 0.1       # EMA smoothing factor for fair value
    RESIN_EDGE = 1          # Base edge value for quotes
    PASSIVE_QTY = 12        # Order size for passive quotes
    INV_SKEW = 0.03         # Inventory skew factor to adjust prices

    # ── Kelp (KELP) parameters ────────────────────────────────────────
    KELP_ALPHA = 0.10       # EMA smoothing factor for fair value
    KELP_WINDOW = 50        # Rolling window length (ticks)
    KELP_BREAKOUT_FACTOR = 0.5  # Fraction of recent range for breakout
    KELP_MOM_SIZE = 2       # Order size for breakout trades

    # ── Squid Ink (SQUID_INK) parameters (Mean Reversion) ─────────────
    SQUID_WINDOW = 40        # Rolling window length for mid-price
    SQUID_MR_THRESHOLD = 10  # Price deviation threshold (in SeaShells)
    SQUID_MR_SIZE = 5        # Order size for reversion trades

    # ── Helper: get best bid and ask ───────────────────────────────────
    @staticmethod
    def _best(depth: OrderDepth):
        """
        Returns:
          (best_bid_px, best_bid_volume), (best_ask_px, best_ask_volume)
        If no bids or asks, returns (None, 0).
        """
        bid = max(depth.buy_orders.items()) if depth.buy_orders else (None, 0)
        ask = min(depth.sell_orders.items()) if depth.sell_orders else (None, 0)
        return bid, ask

    def run(self, state: TradingState):
        # Load memory (rolling windows, last fair values, etc.) from previous tick
        mem = jsonpickle.decode(state.traderData) if state.traderData else {}

        results: Dict[str, List[Order]] = {}

        for prod, depth in state.order_depths.items():
            orders: List[Order] = []

            # Extract best bid & ask
            (bid_px, bid_qty), (ask_px, ask_qty) = self._best(depth)
            if bid_px is None or ask_px is None:
                continue  # Cannot trade if incomplete data

            mid = (bid_px + ask_px) / 2
            pos = state.position.get(prod, 0)
            lim = self.LIMITS.get(prod, 0)

            # ─────────────────────────────────────────────────────────
            # RAINFOREST_RESIN: Market-Making with EMA fair value
            # ─────────────────────────────────────────────────────────
            if prod == "RAINFOREST_RESIN":
                fv_prev = mem.setdefault("fv_resin", mid)
                fv = self.RESIN_ALPHA * mid + (1 - self.RESIN_ALPHA) * fv_prev
                mem["fv_resin"] = fv

                # Inventory-based skew: push quotes away if we have a large position
                skew = self.INV_SKEW * (pos / lim) * self.RESIN_EDGE * 2
                bid_target = int(fv - self.RESIN_EDGE - skew)
                ask_target = int(fv + self.RESIN_EDGE - skew)

                # 1) Aggressive crossing if spread is very favorable
                # Buy if ask < our ideal bid_target, provided we have room
                if ask_px < bid_target and pos < lim:
                    qty = min(-ask_qty, lim - pos)  # ask_qty is negative volume
                    if qty > 0:
                        orders.append(Order(prod, ask_px, qty))
                # Sell if bid > our ideal ask_target
                if bid_px > ask_target and pos > -lim:
                    qty = min(bid_qty, lim + pos)
                    if qty > 0:
                        orders.append(Order(prod, bid_px, -qty))

                # 2) Passive quotes: place resting orders around fair value
                passive_bid_qty = min(self.PASSIVE_QTY, lim - pos)
                passive_ask_qty = min(self.PASSIVE_QTY, lim + pos)
                if passive_bid_qty > 0:
                    orders.append(Order(prod, bid_target, passive_bid_qty))
                if passive_ask_qty > 0:
                    orders.append(Order(prod, ask_target, -passive_ask_qty))

                results[prod] = orders
                continue

            # ─────────────────────────────────────────────────────────
            # KELP: Breakout / Momentum Strategy
            # ─────────────────────────────────────────────────────────
            if prod == "KELP":
                roll: Deque[float] = mem.setdefault("kelp_roll", deque(maxlen=self.KELP_WINDOW))
                roll.append(mid)

                if len(roll) > 0:
                    avg_price = stats.mean(roll)
                else:
                    avg_price = mid

                recent_high = max(roll)
                recent_low = min(roll)
                breakout_threshold = self.KELP_BREAKOUT_FACTOR * (recent_high - recent_low)

                # If price breaks above the high + threshold => buy
                if mid > (recent_high + breakout_threshold) and pos < lim:
                    buy_qty = min(self.KELP_MOM_SIZE, lim - pos)
                    if buy_qty > 0:
                        orders.append(Order(prod, ask_px, buy_qty))

                # If price breaks below the low - threshold => sell
                if mid < (recent_low - breakout_threshold) and pos > -lim:
                    sell_qty = min(self.KELP_MOM_SIZE, lim + pos)
                    if sell_qty > 0:
                        orders.append(Order(prod, bid_px, -sell_qty))

                results[prod] = orders

                # Debug logging for KELP
                print(
                    f"{state.timestamp} {prod} | mid={mid:.2f}, avg={avg_price:.2f}, "
                    f"high={recent_high:.2f}, low={recent_low:.2f}, "
                    f"thresh={breakout_threshold:.2f}, pos={pos}, "
                    f"orders={[ (o.price, o.quantity) for o in orders]}"
                )
                continue

            # ─────────────────────────────────────────────────────────
            # SQUID_INK: Mean-Reversion Strategy
            # ─────────────────────────────────────────────────────────
            if prod == "SQUID_INK":
                # Maintain a rolling window of mid prices
                roll_sq: Deque[float] = mem.setdefault("squid_ink_roll", deque(maxlen=self.SQUID_WINDOW))
                roll_sq.append(mid)

                if len(roll_sq) > 0:
                    avg_price = stats.mean(roll_sq)
                else:
                    avg_price = mid

                # Check deviation from the rolling average
                deviation = mid - avg_price

                # If price is above average by more than threshold => SELL
                if deviation > self.SQUID_MR_THRESHOLD and pos > -lim:
                    sell_qty = min(self.SQUID_MR_SIZE, lim + pos)
                    if sell_qty > 0:
                        orders.append(Order(prod, bid_px, -sell_qty))

                # If price is below average by more than threshold => BUY
                elif deviation < -self.SQUID_MR_THRESHOLD and pos < lim:
                    buy_qty = min(self.SQUID_MR_SIZE, lim - pos)
                    if buy_qty > 0:
                        orders.append(Order(prod, ask_px, buy_qty))

                results[prod] = orders

                # Debug logging for SQUID_INK
                print(
                    f"{state.timestamp} {prod} | mid={mid:.2f}, avg={avg_price:.2f}, "
                    f"dev={deviation:.2f}, pos={pos}, orders={[ (o.price, o.quantity) for o in orders]}"
                )
                continue

        # Return the new orders + 0 conversions + updated memory
        return results, 0, jsonpickle.encode(mem)
