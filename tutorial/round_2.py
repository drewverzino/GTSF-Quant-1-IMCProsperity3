from datamodel import Order, OrderDepth, TradingState
from typing import Dict, List, Deque
from collections import deque
import jsonpickle
import statistics as stats

class Trader:
    # Position limits for the relevant products
    LIMITS = {
        "RAINFOREST_RESIN": 50,
        "KELP": 50,
        "SQUID_INK": 50,
        "CROISSANTS": 250,
        "JAMS": 350,
        "DJEMBES": 60,
        "PICNIC_BASKET1": 60,
        "PICNIC_BASKET2": 100
    }

    # Parameters for the profit-focused PICNIC_BASKET1 arbitrage
    # We use a rolling window for the recent differences to capture volatility
    DIFF_WINDOW = 40             # Number of ticks to compute average and stdev
    SIGMA_MULTIPLIER = 1.5       # Trade only if difference exceeds (mean + multiplier * sigma)
    BASKET_TRADE_SIZE = 2        # Trade one basket at a time

    # Minimum liquidity required for execution (example: volume must be at least 5)
    MIN_LIQUIDITY = 10

    DIFF_WINDOW_2 = 50            # separate window
    SIGMA_MULTIPLIER_2 = 2.0      # can tweak differently for PB2
    BASKET2_TRADE_SIZE = 1

    # Helper: get best bid and ask from order depth
    @staticmethod
    def _best(depth: OrderDepth):
        bid = max(depth.buy_orders.items()) if depth.buy_orders else (None, 0)
        ask = min(depth.sell_orders.items()) if depth.sell_orders else (None, 0)
        return bid, ask

    def run(self, state: TradingState):
        # Load previous memory or initialize it
        mem = jsonpickle.decode(state.traderData) if state.traderData else {}

        # (A) Ensure the memory keys for basket1 are present (unchanged):
        mem.setdefault("basket_diff_history", deque(maxlen=self.DIFF_WINDOW))

        # (B) Ensure a separate memory key for basket2:
        mem.setdefault("basket2_diff_history", deque(maxlen=self.DIFF_WINDOW_2))

        results: Dict[str, List[Order]] = {}

        # Precompute best bid/ask for the relevant products
        bests = {}
        for prod in ["PICNIC_BASKET1", "CROISSANTS", "JAMS", "DJEMBES"]:
            if prod in state.order_depths:
                (bid_px, bid_vol), (ask_px, ask_vol) = self._best(state.order_depths[prod])
                bests[prod] = {"bid_px": bid_px, "bid_vol": bid_vol, "ask_px": ask_px, "ask_vol": ask_vol}

        # Helper to safely compute the mid-price for a product
        def safe_mid(prod: str):
            data = bests.get(prod)
            if data is None: 
                return None
            b = data["bid_px"]
            a = data["ask_px"]
            return (b + a)/2 if (b is not None and a is not None) else None

        # Compute mid-prices for basket and its components
        basket_mid = safe_mid("PICNIC_BASKET1")
        croissant_mid = safe_mid("CROISSANTS")
        jams_mid = safe_mid("JAMS")
        djembes_mid = safe_mid("DJEMBES")

        if None in (basket_mid, croissant_mid, jams_mid, djembes_mid):
            # If any of the essential data is missing, do nothing.
            print("Missing essential price data, skipping tick.")
        else:
            # Components effective price: 6 CROISSANTS + 3 JAMS + 1 DJEMBE
            comp_price = 6 * croissant_mid + 3 * jams_mid + 1 * djembes_mid

            # Difference: how much cheaper (or expensive) the basket is relative to its components
            diff = comp_price - basket_mid

            # Update the history for dynamic thresholding
            mem["basket_diff_history"].append(diff)

            # Only proceed if we have enough history data to compute statistics
            if len(mem["basket_diff_history"]) >= self.DIFF_WINDOW:
                avg_diff = stats.mean(mem["basket_diff_history"])
                sigma_diff = stats.pstdev(mem["basket_diff_history"])  # population standard deviation

                # Define our dynamic threshold
                dynamic_threshold = avg_diff + self.SIGMA_MULTIPLIER * sigma_diff

                # Debug log the dynamic threshold and current diff
                print(f"Basket diff: {diff:.2f}, Avg: {avg_diff:.2f}, Sigma: {sigma_diff:.2f}, Threshold: {dynamic_threshold:.2f}")

                # Retrieve current positions
                pos_basket = state.position.get("PICNIC_BASKET1", 0)
                pos_c = state.position.get("CROISSANTS", 0)
                pos_j = state.position.get("JAMS", 0)
                pos_d = state.position.get("DJEMBES", 0)

                # Check liquidity for basket and components
                basket_ask_vol = bests["PICNIC_BASKET1"]["ask_vol"]
                basket_bid_vol = bests["PICNIC_BASKET1"]["bid_vol"]
                croissant_ask_vol = bests["CROISSANTS"]["ask_vol"]
                croissant_bid_vol = bests["CROISSANTS"]["bid_vol"]
                jams_ask_vol = bests["JAMS"]["ask_vol"]
                jams_bid_vol = bests["JAMS"]["bid_vol"]
                djembes_ask_vol = bests["DJEMBES"]["ask_vol"]
                djembes_bid_vol = bests["DJEMBES"]["bid_vol"]

                # Two scenarios: components are overpriced relative to basket, or vice versa.
                # (A positive diff means components are more expensive than the basket.)
                if diff > dynamic_threshold:
                    # Strategy: Buy PICNIC_BASKET1 (which is cheap) and short the components.
                    # Check position limits and liquidity
                    if pos_basket < self.LIMITS["PICNIC_BASKET1"] and basket_ask_vol >= self.MIN_LIQUIDITY:
                        basket_ask_px = bests["PICNIC_BASKET1"]["ask_px"]
                        results.setdefault("PICNIC_BASKET1", []).append(Order("PICNIC_BASKET1", basket_ask_px, self.BASKET_TRADE_SIZE))
                    # Short component legs cautiously, ensuring sufficient liquidity
                    if pos_c > -self.LIMITS["CROISSANTS"] and croissant_bid_vol >= self.MIN_LIQUIDITY:
                        results.setdefault("CROISSANTS", []).append(Order("CROISSANTS", bests["CROISSANTS"]["bid_px"], -6))
                    if pos_j > -self.LIMITS["JAMS"] and jams_bid_vol >= self.MIN_LIQUIDITY:
                        results.setdefault("JAMS", []).append(Order("JAMS", bests["JAMS"]["bid_px"], -3))
                    if pos_d > -self.LIMITS["DJEMBES"] and djembes_bid_vol >= self.MIN_LIQUIDITY:
                        results.setdefault("DJEMBES", []).append(Order("DJEMBES", bests["DJEMBES"]["bid_px"], -1))
                elif diff < -dynamic_threshold:
                    # Opposite scenario: Sell PICNIC_BASKET1 (if it's overvalued) and buy the components.
                    if pos_basket > -self.LIMITS["PICNIC_BASKET1"] and basket_bid_vol >= self.MIN_LIQUIDITY:
                        basket_bid_px = bests["PICNIC_BASKET1"]["bid_px"]
                        results.setdefault("PICNIC_BASKET1", []).append(Order("PICNIC_BASKET1", basket_bid_px, -self.BASKET_TRADE_SIZE))
                    if pos_c < self.LIMITS["CROISSANTS"] and croissant_ask_vol >= self.MIN_LIQUIDITY:
                        results.setdefault("CROISSANTS", []).append(Order("CROISSANTS", bests["CROISSANTS"]["ask_px"], 6))
                    if pos_j < self.LIMITS["JAMS"] and jams_ask_vol >= self.MIN_LIQUIDITY:
                        results.setdefault("JAMS", []).append(Order("JAMS", bests["JAMS"]["ask_px"], 3))
                    if pos_d < self.LIMITS["DJEMBES"] and djembes_ask_vol >= self.MIN_LIQUIDITY:
                        results.setdefault("DJEMBES", []).append(Order("DJEMBES", bests["DJEMBES"]["ask_px"], 1))
                else:
                    # If the diff is not extreme, do not initiate any new trades.
                    print("No strong arbitrage signal on this tick.")
            else:
                print("Building diff history, waiting for enough data...")

        needed_prods = ["PICNIC_BASKET2", "CROISSANTS", "JAMS"]
        bests = {}
        for prod in needed_prods:
            if prod not in state.order_depths:
                continue
            (bid_px, bid_vol), (ask_px, ask_vol) = self._best(state.order_depths[prod])
            bests[prod] = {
                "bid_px": bid_px, 
                "bid_vol": bid_vol,
                "ask_px": ask_px, 
                "ask_vol": ask_vol
            }

        # Helper to compute midprice if we have both bid & ask
        def safe_mid(prod: str):
            if prod not in bests: 
                return None
            b = bests[prod]["bid_px"]
            a = bests[prod]["ask_px"]
            return (b + a)/2 if (b is not None and a is not None) else None

        # --- PICNIC_BASKET2 Arbitrage ---
        basket2_mid = safe_mid("PICNIC_BASKET2")
        cro_mid = safe_mid("CROISSANTS")
        jams_mid = safe_mid("JAMS")

        if all(x is not None for x in [basket2_mid, cro_mid, jams_mid]):
            # Components for PB2 => 4 CROISSANTS + 2 JAMS
            comp_price_2 = 4 * cro_mid + 2 * jams_mid
            diff_2 = comp_price_2 - basket2_mid  # +ve => components > basket2

            # Store in separate history deque
            mem["basket2_diff_history"].append(diff_2)

            # If we have enough data, compute dynamic threshold
            if len(mem["basket2_diff_history"]) >= self.DIFF_WINDOW_2:
                avg_diff_2 = stats.mean(mem["basket2_diff_history"])
                sigma_diff_2 = stats.pstdev(mem["basket2_diff_history"])
                threshold_2 = avg_diff_2 + self.SIGMA_MULTIPLIER_2 * sigma_diff_2

                # Log for debugging
                print(f"[PB2] diff: {diff_2:.1f}, avg: {avg_diff_2:.1f}, stdev: {sigma_diff_2:.1f}, threshold: {threshold_2:.1f}")

                # Retrieve current positions
                pos_b2 = state.position.get("PICNIC_BASKET2", 0)
                pos_c = state.position.get("CROISSANTS", 0)
                pos_j = state.position.get("JAMS", 0)

                # Liquidity checks
                b2_ask_px = bests["PICNIC_BASKET2"]["ask_px"]
                b2_ask_vol = bests["PICNIC_BASKET2"]["ask_vol"]
                b2_bid_px = bests["PICNIC_BASKET2"]["bid_px"]
                b2_bid_vol = bests["PICNIC_BASKET2"]["bid_vol"]

                c_ask_px = bests["CROISSANTS"]["ask_px"]
                c_ask_vol = bests["CROISSANTS"]["ask_vol"]
                c_bid_px = bests["CROISSANTS"]["bid_px"]
                c_bid_vol = bests["CROISSANTS"]["bid_vol"]

                j_ask_px = bests["JAMS"]["ask_px"]
                j_ask_vol = bests["JAMS"]["ask_vol"]
                j_bid_px = bests["JAMS"]["bid_px"]
                j_bid_vol = bests["JAMS"]["bid_vol"]

                # If diff_2 > threshold_2 => basket2 is cheaper, so buy basket2, short components
                if diff_2 > threshold_2:
                    # Buy 1 PB2 if we have room
                    if pos_b2 < self.LIMITS["PICNIC_BASKET2"] and b2_ask_px and b2_ask_vol <= -self.MIN_LIQUIDITY:
                        results.setdefault("PICNIC_BASKET2", [])
                        results["PICNIC_BASKET2"].append(Order("PICNIC_BASKET2", b2_ask_px, self.BASKET2_TRADE_SIZE))
                    # Short components: 4 CROISSANTS, 2 JAMS
                    if pos_c > -self.LIMITS["CROISSANTS"] and c_bid_px and c_bid_vol >= self.MIN_LIQUIDITY:
                        results.setdefault("CROISSANTS", [])
                        results["CROISSANTS"].append(Order("CROISSANTS", c_bid_px, -4))
                    if pos_j > -self.LIMITS["JAMS"] and j_bid_px and j_bid_vol >= self.MIN_LIQUIDITY:
                        results.setdefault("JAMS", [])
                        results["JAMS"].append(Order("JAMS", j_bid_px, -2))

                # If diff_2 < -threshold_2 => basket2 is expensive, so sell basket2, buy components
                elif diff_2 < -threshold_2:
                    if pos_b2 > -self.LIMITS["PICNIC_BASKET2"] and b2_bid_px and b2_bid_vol >= self.MIN_LIQUIDITY:
                        results.setdefault("PICNIC_BASKET2", [])
                        results["PICNIC_BASKET2"].append(Order("PICNIC_BASKET2", b2_bid_px, -self.BASKET2_TRADE_SIZE))
                    if pos_c < self.LIMITS["CROISSANTS"] and c_ask_px and c_ask_vol <= -self.MIN_LIQUIDITY:
                        results.setdefault("CROISSANTS", [])
                        results["CROISSANTS"].append(Order("CROISSANTS", c_ask_px, 4))
                    if pos_j < self.LIMITS["JAMS"] and j_ask_px and j_ask_vol <= -self.MIN_LIQUIDITY:
                        results.setdefault("JAMS", [])
                        results["JAMS"].append(Order("JAMS", j_ask_px, 2))
                else:
                    print("[PB2] No strong mispricing signal.")
            else:
                print("[PB2] Not enough data to compute threshold yet.")
        else:
            print("[PB2] Missing data for basket2 or components.")

        # (C) End with flush (unchanged)
        # logger.flush(state, results, 0, jsonpickle.encode(mem))
        return results, 0, jsonpickle.encode(mem)