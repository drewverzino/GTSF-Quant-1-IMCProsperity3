from datamodel import OrderDepth, Order, TradingState
from typing import List
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
                # VWAP-based market making
                bids = order_depth.buy_orders
                asks = order_depth.sell_orders

                if bids and asks:
                    vwap_bid = sum(p * v for p, v in bids.items()) / sum(bids.values())
                    vwap_ask = sum(p * -v for p, v in asks.items()) / sum(-v for v in asks.values())
                    fair_value = (vwap_bid + vwap_ask) / 2

                    spread = 1  # tighter spread for stable product
                    buy_price = int(fair_value - spread)
                    sell_price = int(fair_value + spread)

                    buy_qty = min(POSITION_LIMITS[product] - position, 5)
                    sell_qty = min(position + POSITION_LIMITS[product], 5)

                    if buy_qty > 0:
                        orders.append(Order(product, buy_price, buy_qty))
                    if sell_qty > 0:
                        orders.append(Order(product, sell_price, -sell_qty))

            elif product == "KELP":
                # Mean Reversion Strategy for KELP
                if order_depth.buy_orders and order_depth.sell_orders:
                    best_ask = min(order_depth.sell_orders.keys())
                    best_bid = max(order_depth.buy_orders.keys())
                    mid_price = (best_ask + best_bid) / 2
                    self.kelp_prices.append(mid_price)

                    window = 20
                    threshold = 1.5  # tighter threshold since kelp doesn't swing much

                    if len(self.kelp_prices) >= window:
                        avg_price = statistics.mean(self.kelp_prices[-window:])

                        if mid_price < avg_price - threshold and position < POSITION_LIMITS[product]:
                            buy_volume = min(POSITION_LIMITS[product] - position, 10)
                            orders.append(Order(product, best_ask, buy_volume))
                        elif mid_price > avg_price + threshold and position > -POSITION_LIMITS[product]:
                            sell_volume = min(position + POSITION_LIMITS[product], 10)
                            orders.append(Order(product, best_bid, -sell_volume))
                            
            result[product] = orders

        return result, conversions, traderData