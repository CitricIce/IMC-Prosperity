# IMC Prosperity 2025 — Market-Making Trading Bot

A Python market-making algorithm built for IMC Prosperity 2025, an algorithmic trading competition. The bot trades two products, EMERALDS and TOMATOES, using two different fair-value strategies.

## What it does

The bot runs inside IMC's trading simulator and submits buy/sell orders each tick based on the current order book. It has two strategies:

**EMERALDS — fixed fair value**
EMERALDS trades around a known, stable fair value (10,000). The bot:
- Takes any order priced better than fair value (buys underpriced asks, sells overpriced bids)
- Posts passive two-sided quotes around fair value, split into a tight layer (close to fair, higher priority) and a wide layer (further out, lower priority)

**TOMATOES — dynamic fair value**
TOMATOES has no fixed price, so the bot estimates fair value each tick:
- Tracks a slow-moving exponential moving average (EMA, alpha = 0.02) of the mid-price to smooth out noise
- Blends that EMA with a longer-range price anchor (75% EMA, 25% anchor) to get a fair value estimate
- Takes mispriced orders and posts passive quotes the same way as EMERALDS, but sizes them 70/30 (tight/wide) instead of 50/50

Both strategies respect a position limit of 50 per product and manage inventory by preferentially flattening toward neutral when trading at fair value.

## Files

- `45365_commented.py` — the trading algorithm, fully commented with variable explanations

## Tech

Python, using IMC's `datamodel` module (`OrderDepth`, `TradingState`, `Order`) provided by the competition framework.

## Results

- Improved performance 25% across competition rounds
- Iterated through four strategy versions in Round 3, testing each against the last
- Found and fixed fill-logic bugs that were causing missed and mispriced fills
- Tuned position management to keep inventory near neutral within the 50-unit limit

## What I Learned

- Small execution bugs can cost more than a weak strategy. Fixing fill logic mattered as much as tuning fair value.
- Stable and volatile products need different fair-value models. A fixed anchor worked for EMERALDS, but TOMATOES needed a moving estimate.
