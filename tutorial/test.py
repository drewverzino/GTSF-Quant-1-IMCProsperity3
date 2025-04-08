from datamodel import OrderDepth, Order, TradingState
from typing import Dict, List
import statistics

POSITION_LIMITS = {
    "KELP": 50,
    "RAINFOREST_RESIN": 50
}

class Trader:
    def __init__(self):
        self.kelp_prices = []

    def run(self, state: TradingState):
        result = {}
        conversions = 0
        traderData = ""

        for product, order_depth in state.order_depths.items():
            orders: List[Order] = []
            position = state.position.get(product, 0)

            if product == "RAINFOREST_RESIN":
                # Tight-spread market making on stable asset
                if order_depth.buy_orders and order_depth.sell_orders:
                    best_bid = max(order_depth.buy_orders.keys())
                    best_ask = min(order_depth.sell_orders.keys())
                    mid_price = (best_bid + best_ask) / 2

                    buy_price = best_bid + 1  # be more aggressive
                    sell_price = best_ask - 1

                    buy_volume = min(POSITION_LIMITS[product] - position, 5)
                    sell_volume = min(POSITION_LIMITS[product] + position, 5)

                    if buy_volume > 0:
                        orders.append(Order(product, buy_price, buy_volume))
                    if sell_volume > 0:
                        orders.append(Order(product, sell_price, -sell_volume))

            elif product == "KELP":
                # Mean reversion strategy
                if order_depth.buy_orders and order_depth.sell_orders:
                    best_bid = max(order_depth.buy_orders.keys())
                    best_ask = min(order_depth.sell_orders.keys())
                    mid_price = (best_ask + best_bid) / 2
                    self.kelp_prices.append(mid_price)

                    window = 5
                    if len(self.kelp_prices) >= window:
                        moving_avg = statistics.mean(self.kelp_prices[-window:])
                        threshold = 1  # small deviation threshold

                        # Buy low (undervalued)
                        if mid_price < moving_avg - threshold and position < POSITION_LIMITS[product]:
                            buy_volume = min(POSITION_LIMITS[product] - position, 10)
                            orders.append(Order(product, best_ask, buy_volume))

                        # Sell high (overvalued)
                        elif mid_price > moving_avg + threshold and position > -POSITION_LIMITS[product]:
                            sell_volume = min(position + POSITION_LIMITS[product], 10)
                            orders.append(Order(product, best_bid, -sell_volume))

            result[product] = orders

        return result, conversions, traderData
