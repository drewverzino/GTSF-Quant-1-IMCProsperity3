from datamodel import OrderDepth, Order, TradingState
from typing import Dict, List
import statistics

POSITION_LIMITS = {
    "KELP": 50,
    "RAINFOREST_RESIN": 50,
    "SQUID_INK": 50
}

class Trader:
    def __init__(self):
        self.prices_history = {
            "KELP": [],
            "RAINFOREST_RESIN": [],
            "SQUID_INK": []
        }

    def run(self, state: TradingState):
        result = {}
        conversions = 0
        traderData = ""

        for product, order_depth in state.order_depths.items():
            orders: List[Order] = []
            position = state.position.get(product, 0)

            if order_depth.buy_orders and order_depth.sell_orders:
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                mid_price = (best_bid + best_ask) / 2
                self.prices_history[product].append(mid_price)

                # --- SQUID INK: Trend Following (Reversed from Mean Reversion) ---
                if product == "SQUID_INK" and len(self.prices_history[product]) >= 20:
                    short_ma = statistics.mean(self.prices_history[product][-5:])
                    long_ma = statistics.mean(self.prices_history[product][-20:])
                    threshold = 1  # add noise buffer

                    if short_ma > long_ma + threshold and position < POSITION_LIMITS[product]:
                        # Strong upward momentum → Buy
                        buy_qty = min(POSITION_LIMITS[product] - position, 10)
                        orders.append(Order(product, best_ask, buy_qty))
                    elif short_ma < long_ma - threshold and position > -POSITION_LIMITS[product]:
                        # Downward trend → Sell
                        sell_qty = min(position + POSITION_LIMITS[product], 10)
                        orders.append(Order(product, best_bid, -sell_qty))

                # --- RAINFOREST RESIN: Market Making (Stable) ---
                elif product == "RAINFOREST_RESIN":
                    spread = 1
                    buy_price = int(mid_price - spread)
                    sell_price = int(mid_price + spread)
                    buy_qty = min(POSITION_LIMITS[product] - position, 10)
                    sell_qty = min(POSITION_LIMITS[product] + position, 10)
                    if buy_qty > 0:
                        orders.append(Order(product, buy_price, buy_qty))
                    if sell_qty > 0:
                        orders.append(Order(product, sell_price, -sell_qty))

                # --- KELP: Momentum Strategy ---
                elif product == "KELP" and len(self.prices_history[product]) >= 10:
                    short_ma = statistics.mean(self.prices_history[product][-3:])
                    long_ma = statistics.mean(self.prices_history[product][-10:])
                    if short_ma > long_ma and position < POSITION_LIMITS[product]:
                        buy_qty = min(POSITION_LIMITS[product] - position, 10)
                        orders.append(Order(product, best_ask, buy_qty))
                    elif short_ma < long_ma and position > -POSITION_LIMITS[product]:
                        sell_qty = min(position + POSITION_LIMITS[product], 10)
                        orders.append(Order(product, best_bid, -sell_qty))

            result[product] = orders

        return result, conversions, traderData
