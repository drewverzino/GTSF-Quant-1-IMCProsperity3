from datamodel import Order, OrderDepth, TradingState
from typing import Dict, List
import jsonpickle
import statistics as stats

class Trader:
    LIMITS = {
        "VOLCANIC_ROCK": 400,
        "VOLCANIC_ROCK_VOUCHER_9500": 200,
        "VOLCANIC_ROCK_VOUCHER_9750": 200,
        "VOLCANIC_ROCK_VOUCHER_10000": 200,
        "VOLCANIC_ROCK_VOUCHER_10250": 200,
        "VOLCANIC_ROCK_VOUCHER_10500": 200
    }

    STRIKE_PRICES = {
        "VOLCANIC_ROCK_VOUCHER_9500": 9500,
        "VOLCANIC_ROCK_VOUCHER_9750": 9750,
        "VOLCANIC_ROCK_VOUCHER_10000": 10000,
        "VOLCANIC_ROCK_VOUCHER_10250": 10250,
        "VOLCANIC_ROCK_VOUCHER_10500": 10500
    }

    VOL_MULTIPLIER = 1.5  # Controls how aggressively we act on mispricing
    WINDOW = 100  # How many recent prices to use for volatility and fair value

    @staticmethod
    def _best(depth: OrderDepth):
        bid = max(depth.buy_orders.items()) if depth.buy_orders else (None, 0)
        ask = min(depth.sell_orders.items()) if depth.sell_orders else (None, 0)
        return bid, ask

    def run(self, state: TradingState):
        mem = jsonpickle.decode(state.traderData) if state.traderData else {}
        results: Dict[str, List[Order]] = {}

        # Keep historical prices
        rock_price_hist = mem.setdefault("rock_prices", [])

        # Compute current VOLCANIC_ROCK mid-price
        if "VOLCANIC_ROCK" not in state.order_depths:
            return {}, 0, jsonpickle.encode(mem)
        rock_depth = state.order_depths["VOLCANIC_ROCK"]
        (bid_px, _), (ask_px, _) = self._best(rock_depth)
        if bid_px is None or ask_px is None:
            return {}, 0, jsonpickle.encode(mem)

        mid = (bid_px + ask_px) / 2
        rock_price_hist.append(mid)
        if len(rock_price_hist) > self.WINDOW:
            rock_price_hist.pop(0)

        # Compute stats
        avg_price = stats.mean(rock_price_hist)
        volatility = stats.pstdev(rock_price_hist) if len(rock_price_hist) > 1 else 0

        # Loop through all vouchers
        for voucher, strike in self.STRIKE_PRICES.items():
            if voucher not in state.order_depths:
                continue

            voucher_depth = state.order_depths[voucher]
            (v_bid, v_bid_qty), (v_ask, v_ask_qty) = self._best(voucher_depth)
            fair_value = max(0, avg_price - strike)
            threshold = self.VOL_MULTIPLIER * volatility

            pos = state.position.get(voucher, 0)
            lim = self.LIMITS[voucher]
            orders = []

            # Opportunity to buy voucher
            if v_ask is not None and v_ask < fair_value - threshold and pos < lim:
                buy_qty = min(-v_ask_qty, lim - pos)
                if buy_qty > 0:
                    orders.append(Order(voucher, v_ask, buy_qty))

            # Opportunity to sell voucher
            if v_bid is not None and v_bid > fair_value + threshold and pos > -lim:
                sell_qty = min(v_bid_qty, lim + pos)
                if sell_qty > 0:
                    orders.append(Order(voucher, v_bid, -sell_qty))

            if orders:
                results[voucher] = orders

        # Also store updated memory
        mem["rock_prices"] = rock_price_hist
        return results, 0, jsonpickle.encode(mem)
