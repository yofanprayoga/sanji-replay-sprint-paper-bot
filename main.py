"""Sanji's Pump.fun Replay Sprint bot — agent-fun/replay/v2, Python 3.13 stdlib only.

How it trades (own design, fully deterministic):
- It watches each new coin from its CreateEvent and keeps a small tape of the
  early flow. It buys a coin once, 0.05 SOL, only when the tape looks like
  strong real demand: at least 4 buy trades from at least 4 different
  wallets, at least 3 SOL of net inflow, the price at least 15% above the
  create price, the creator has not sold, and real SOL reserves sit between
  0.5 and 80 SOL. The bar is deliberately high: on the dev window the looser
  filter traded 261 coins for a worse result, while this stricter filter
  trades about 157 and keeps more of the fee drag out.
- It sells the whole position when the value reaches +25% over cost, when it
  falls to -15% under cost, when the coin has been held 1200 slots, or when
  600 slots pass with no trade on it. No shorts, no leverage, at most 5 open
  positions, at most 16 orders per batch.
- Every decision is integer math on lamports and reserves (no floats), with
  no clock, no randomness, no environment and no network — two runs give
  byte-identical replies. stdout carries replies only.

The protocol words: hello gives capital and caps, each batch carries events,
marks, fills and account at its slot, and each reply echoes the batch seq
with its orders.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bot  # noqa: E402

LAMPORTS = makefun_bot.LAMPORTS_PER_SOL
BUY_SIZE = LAMPORTS // 20            # 0.05 SOL into one coin
ROUNDTRIP_MIN = LAMPORTS // 100      # 0.01 SOL, the round-trip minimum
REAL_MIN = LAMPORTS // 2             # 0.5 SOL of real reserves
REAL_MAX = LAMPORTS * 80             # 80 SOL of real reserves
TAPE_MIN_AGE = 5                     # slots after the create before a buy
TAPE_MIN_BUYS = 4
TAPE_MIN_BUYERS = 4
TAPE_MIN_FLOW = LAMPORTS * 3         # at least 3 SOL net inflow
RISE_MIN_BPS = 1500                  # price at least 15% above create
BUY_SLIP = 1500
SELL_SLIP = 10000
PROFIT_BPS = 12500                   # sell when value >= cost * 1.25
LOSS_BPS = 8500                      # sell when value <= cost * 0.85
HOLD_MAX = 1200
STALE_MAX = 600


class Coin:
    """The early tape of one mint, folded from batch events in stream order."""

    __slots__ = (
        "born", "q0", "t0", "flow", "n_buys",
        "wallets", "maker", "maker_sold", "last_seen",
    )

    def __init__(self, born, q0, t0, maker):
        self.born = born
        self.q0 = q0
        self.t0 = t0
        self.flow = 0
        self.n_buys = 0
        self.wallets = set()
        self.maker = maker
        self.maker_sold = False
        self.last_seen = born


coins = {}
closed = set()
open_since = {}


def risen(curve, coin):
    """True when the current price is at least RISE_MIN_BPS above the create
    price, checked by integer cross-multiplication so no float ever appears:
    q_now * t_create * 10000 >= q_create * t_now * (10000 + RISE_MIN_BPS)."""
    if coin.t0 == 0 or curve.virtual_token_reserves == 0:
        return False
    return (
        curve.virtual_quote_reserves * coin.t0 * 10000
        >= coin.q0 * curve.virtual_token_reserves * (10000 + RISE_MIN_BPS)
    )


def worth(tokens, curve):
    """Tokens valued at the current reserves, integer math only."""
    if curve.virtual_token_reserves == 0:
        return 0
    return tokens * curve.virtual_quote_reserves // curve.virtual_token_reserves


def absorb(batch):
    """Fold this batch's events into the tapes, in stream order."""
    for e in batch["events"]:
        mint = e["mint"]
        kind = e["event"]
        if kind == "CreateEvent":
            if mint not in coins:
                coins[mint] = Coin(
                    e["slot"],
                    int(e["virtual_quote_reserves"]),
                    int(e["virtual_token_reserves"]),
                    e["creator"],
                )
        elif kind == "TradeEvent":
            coin = coins.get(mint)
            if coin is None:
                coin = Coin(e["slot"], int(e["virtual_quote_reserves"]),
                            int(e["virtual_token_reserves"]), e["creator"])
                coins[mint] = coin
            sol = int(e["sol_amount"])
            if e["is_buy"]:
                coin.flow += sol
                coin.n_buys += 1
                coin.wallets.add(e["user"])
            else:
                coin.flow -= sol
                if e["user"] == coin.maker:
                    coin.maker_sold = True
            coin.last_seen = e["slot"]
        elif kind == "CompleteEvent":
            closed.add(mint)


def exit_due(value, cost, held_for, stale_for):
    """One predicate for every exit, so the four reasons stay in one place:
    take-profit, stop-loss, held too long, or gone stale."""
    return (
        value * 10000 >= cost * PROFIT_BPS
        or value * 10000 <= cost * LOSS_BPS
        or held_for >= HOLD_MAX
        or stale_for >= STALE_MAX
    )


def sell_side(state, slot):
    """Exits, decided before any new buy so a freed slot can be reused only
    once its fill lands. Returns the sell orders for this batch."""
    for mint in state.positions:
        if mint not in open_since:
            open_since[mint] = slot
    for mint in list(open_since):
        if mint not in state.positions:
            del open_since[mint]
    orders = []
    for mint, holding in list(state.positions.items()):
        curve = state.curves.get(mint)
        if curve is None or curve.complete:
            continue
        cost = holding.cost_lamports
        if cost <= 0 or holding.token_amount <= 0:
            continue
        value = worth(holding.token_amount, curve)
        held_for = slot - open_since.get(mint, slot)
        stale_for = slot - coins[mint].last_seen if mint in coins else 0
        if exit_due(value, cost, held_for, stale_for):
            orders.append({
                "side": "sell", "mint": mint,
                "token_amount": holding.token_amount,
                "max_slippage_bps": SELL_SLIP,
            })
    return orders


def entry_ready(coin, curve, slot):
    """One predicate for every entry condition, so the buy gate stays in one
    place: tape old enough, enough distinct buyers and inflow, price risen,
    creator still holding, and reserves in range."""
    if slot - coin.born < TAPE_MIN_AGE:
        return False
    if coin.n_buys < TAPE_MIN_BUYS or len(coin.wallets) < TAPE_MIN_BUYERS:
        return False
    if coin.flow < TAPE_MIN_FLOW or coin.maker_sold:
        return False
    if not risen(curve, coin):
        return False
    real_sol = curve.real_quote_reserves
    return REAL_MIN <= real_sol <= REAL_MAX


def buy_side(state, batch, slot, orders):
    """Entries, one buy per coin, in batch event order. Appends to orders."""
    tx = state.tx_fee_lamports()
    free = state.free_cash_lamports()
    for o in orders:
        free -= tx  # sells also pay the tx fee
    slots_open = state.hello["caps"]["max_open_positions"] - state.committed_position_count()
    for e in batch["events"]:
        if len(orders) >= state.hello["caps"]["max_orders_per_batch"] or slots_open <= 0:
            break
        mint = e["mint"]
        if mint in closed:
            continue
        coin = coins.get(mint)
        curve = state.curves.get(mint)
        if coin is None or curve is None or curve.complete:
            continue
        if not entry_ready(coin, curve, slot):
            continue
        cap = state.max_buy_lamports(mint)
        if cap < ROUNDTRIP_MIN:
            continue
        closed.add(mint)
        amount = cap if cap < BUY_SIZE else BUY_SIZE
        if free < amount + tx:
            continue
        orders.append({
            "side": "buy", "mint": mint,
            "quote_lamports": amount,
            "max_slippage_bps": BUY_SLIP,
        })
        free -= amount + tx
        slots_open -= 1


def on_batch(state, batch):
    slot = batch["slot"]
    absorb(batch)
    orders = sell_side(state, slot)
    buy_side(state, batch, slot, orders)
    return orders


def on_hello(state):
    return None


def on_done(state, done):
    return None


if __name__ == "__main__":
    makefun_bot.run(on_batch, on_hello=on_hello, on_done=on_done)
