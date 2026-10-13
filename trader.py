from datamodel import OrderDepth, TradingState, Order

# L = position limits per product (max absolute position, long or short)
# The exchange rejects all orders in a product if they'd push you past this limit
L = {"EMERALDS": 50, "TOMATOES": 50}

# F = fixed fair value for EMERALDS (10,000 XIRECs)
# EMERALDS is treated as a stable product with a known true price,
# so we hard-code this instead of estimating it dynamically
F = 10000


class Trader:
    def __init__(self):
        # self.t = exponential moving average (EMA) of TOMATOES mid-price
        # Starts as None; initialized on the first iteration
        self.t = None

    def run(self, state: TradingState):
        # r = result dict: maps each product name to its list of orders
        r = {}

        for p, d in state.order_depths.items():
            # pos = current position in product p (positive = long, negative = short)
            # Defaults to 0 if we haven't traded this product yet
            pos = state.position.get(p, 0)

            if p == "EMERALDS":
                r[p] = self.e(d, pos)   # Fixed fair value strategy
            elif p == "TOMATOES":
                r[p] = self.m(d, pos)   # Dynamic fair value (EMA-based) strategy

        # Return (orders, conversions, traderData)
        # conversions=0: no position conversions requested
        # traderData="": no state to persist (EMA is stored on the class instance instead)
        return r, 0, ""

    # -------------------------------------------------------------------------
    # EMERALDS strategy: market-make around F=10,000 (fixed fair value)
    # Take any mispriced bot orders, then post two-sided quotes near fair value
    # -------------------------------------------------------------------------
    def e(self, d: OrderDepth, pos: int):
        # o  = list of orders to send this iteration
        # mb = max buy quantity we can still send (headroom to long limit)
        # ms = max sell quantity we can still send (headroom to short limit)
        o = []
        mb = L["EMERALDS"] - pos
        ms = L["EMERALDS"] + pos

        # --- Take mispriced sell orders (buy below fair value) ---
        if d.sell_orders:
            for px in sorted(d.sell_orders):           # px = ask price level, cheapest first
                av = -d.sell_orders[px]                # av = available quantity at this ask
                                                       # (sell_orders quantities are negative, so negate)

                if px < F and mb > 0:
                    # Bot is selling below fair value — buy as much as we can
                    q = min(av, mb)
                    o.append(Order("EMERALDS", px, q))
                    mb -= q

                elif px == F and pos < 0 and mb > 0:
                    # We're short and the ask is exactly at fair value —
                    # buy just enough to flatten back to neutral (don't over-buy at fair)
                    q = min(av, -pos, mb)
                    o.append(Order("EMERALDS", px, q))
                    mb -= q

        # --- Take mispriced buy orders (sell above fair value) ---
        if d.buy_orders:
            for px in sorted(d.buy_orders, reverse=True):  # px = bid price, highest first
                av = d.buy_orders[px]                       # av = available quantity at this bid

                if px > F and ms > 0:
                    # Bot is buying above fair value — sell as much as we can
                    q = min(av, ms)
                    o.append(Order("EMERALDS", px, -q))
                    ms -= q

                elif px == F and pos > 0 and ms > 0:
                    # We're long and the bid is exactly at fair value —
                    # sell just enough to flatten back to neutral
                    q = min(av, pos, ms)
                    o.append(Order("EMERALDS", px, -q))
                    ms -= q

        # --- Post passive market-making quotes with remaining capacity ---
        if d.buy_orders and d.sell_orders:
            bb = max(d.buy_orders)   # bb = best bid (highest bot buy price)
            ba = min(d.sell_orders)  # ba = best ask (lowest bot sell price)

            # Tight quotes: 1 tick inside fair value (highest priority, best execution)
            tb = F - 1               # tb = tight bid price (just below fair)
            ta = F + 1               # ta = tight ask price (just above fair)

            # Wide quotes: 1 tick inside the current best bot bid/ask,
            # but still capped so they stay on the correct side of fair value
            wb = min(bb + 1, F - 1)  # wb = wide bid price
            wa = max(ba - 1, F + 1)  # wa = wide ask price

            if mb > 0:
                # tq = tight bid quantity (~half of remaining buy capacity)
                # wq = wide bid quantity  (the rest)
                tq = max(1, mb // 2)
                wq = mb - tq
                o.append(Order("EMERALDS", tb, tq))
                if wq > 0:
                    # If wb would overlap with tb, just reuse tb to avoid duplicate price levels
                    o.append(Order("EMERALDS", wb if wb != tb else tb, wq))

            if ms > 0:
                # tq = tight ask quantity (~half of remaining sell capacity)
                # wq = wide ask quantity  (the rest)
                tq = max(1, ms // 2)
                wq = ms - tq
                o.append(Order("EMERALDS", ta, -tq))
                if wq > 0:
                    o.append(Order("EMERALDS", wa if wa != ta else ta, -wq))

        return o

    # -------------------------------------------------------------------------
    # TOMATOES strategy: market-make around a dynamic EMA-based fair value
    # TOMATOES doesn't have a fixed price, so we estimate fair value each tick
    # -------------------------------------------------------------------------
    def m(self, d: OrderDepth, pos: int):
        if not d.buy_orders or not d.sell_orders:
            return []  # No market data — skip this iteration

        # o  = list of orders to send
        # mb = remaining buy capacity
        # ms = remaining sell capacity
        o = []
        mb = L["TOMATOES"] - pos
        ms = L["TOMATOES"] + pos

        bb = max(d.buy_orders)    # bb  = best bid  (highest bot buy price)
        ba = min(d.sell_orders)   # ba  = best ask  (lowest bot sell price)
        bw = min(d.buy_orders)    # bw  = worst bid (lowest bot buy price — far from mid)
        aw = max(d.sell_orders)   # aw  = worst ask (highest bot sell price — far from mid)

        mid  = (bb + ba) / 2      # mid  = midpoint of best bid/ask (short-term price signal)
        wall = (bw + aw) / 2      # wall = midpoint of worst bid/ask (longer-range anchor)

        # EMA (exponential moving average) of mid-price
        # Alpha=0.02 means the EMA reacts slowly — recent mid has only 2% weight each tick
        # This smooths out noise and tracks the trend rather than reacting to every wiggle
        self.t = mid if self.t is None else 0.02 * mid + 0.98 * self.t

        # fair = blended fair value estimate
        # 75% weight on the EMA (trend-following), 25% on the wall midpoint (structural anchor)
        fair = 0.25 * wall + 0.75 * self.t

        # --- Take mispriced sell orders (buy well below fair value) ---
        for px in sorted(d.sell_orders):     # px = ask price level, cheapest first
            av = -d.sell_orders[px]          # av = available quantity at this ask

            if px < fair - 1 and mb > 0:
                # Ask is more than 1 tick below fair — clear edge, buy it
                q = min(av, mb)
                o.append(Order("TOMATOES", px, q))
                mb -= q

            elif px <= fair and pos < 0 and mb > 0:
                # We're short and ask is at or below fair — buy to reduce short position
                q = min(av, -pos, mb)
                o.append(Order("TOMATOES", px, q))
                mb -= q

        # --- Take mispriced buy orders (sell well above fair value) ---
        for px in sorted(d.buy_orders, reverse=True):  # px = bid price, highest first
            av = d.buy_orders[px]                       # av = available quantity at this bid

            if px > fair + 1 and ms > 0:
                # Bid is more than 1 tick above fair — clear edge, sell into it
                q = min(av, ms)
                o.append(Order("TOMATOES", px, -q))
                ms -= q

            elif px >= fair and pos > 0 and ms > 0:
                # We're long and bid is at or above fair — sell to reduce long position
                q = min(av, pos, ms)
                o.append(Order("TOMATOES", px, -q))
                ms -= q

        # --- Compute passive market-making quote prices ---
        # tb = tight bid: 1 tick above best bot bid, but capped below fair and below best ask
        tb = min(bb + 1, int(fair) - 1)
        tb = min(tb, ba - 1)

        # ta = tight ask: 1 tick below best bot ask, but floored above fair and above best bid
        ta = max(ba - 1, int(fair) + 1)
        ta = max(ta, bb + 1)

        # wb = wide bid: 1 tick below tight bid, but must stay above the worst bot bid
        wb = max(min(tb - 1, int(fair) - 2), bw + 1)

        # wa = wide ask: 1 tick above tight ask, but must stay below the worst bot ask
        wa = min(max(ta + 1, int(fair) + 2), aw - 1)

        # --- Post passive quotes with remaining capacity ---
        if mb > 0:
            # tq = tight bid quantity (70% of remaining buy capacity — prioritize best price)
            # wq = wide bid quantity  (remaining 30%)
            tq = max(1, (7 * mb) // 10)
            wq = mb - tq
            o.append(Order("TOMATOES", tb, tq))
            if wq > 0:
                o.append(Order("TOMATOES", wb, wq))

        if ms > 0:
            # tq = tight ask quantity (70% of remaining sell capacity)
            # wq = wide ask quantity  (remaining 30%)
            tq = max(1, (7 * ms) // 10)
            wq = ms - tq
            o.append(Order("TOMATOES", ta, -tq))
            if wq > 0:
                o.append(Order("TOMATOES", wa, -wq))

        return o
