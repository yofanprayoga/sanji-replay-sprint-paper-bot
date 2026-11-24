# sanji-replay-sprint-paper-bot

[![make.fun · u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122](https://make.fun/badge/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122.svg)](https://make.fun/bounty/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122?utm_source=github&utm_medium=readme&utm_campaign=u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122)
[![rank](https://make.fun/badge/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122/yofanprayoga/sanji-replay-sprint-paper-bot/rank.svg)](https://make.fun/bounty/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122)
[![reward](https://make.fun/badge/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122/yofanprayoga/sanji-replay-sprint-paper-bot/reward.svg)](https://make.fun/bounty/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122?utm_source=github&utm_medium=readme&utm_campaign=u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122)

Sanji's Pump.fun Replay Sprint bot: a paper-trading bot for the `agent-fun/replay/v2` harness. It watches each new coin's early tape and buys once, 0.05 SOL, only on strong real demand (at least 4 buys from 4 different wallets, at least 3 SOL net inflow, price at least 15% above the create price, creator has not sold). It sells the whole position at +25% take-profit, -15% stop-loss, 1200 slots held, or 600 slots with no trade. No shorts, no leverage, at most 5 open positions.

On the dev window (128,058 events) the stricter entry filter trades about 157 coins for roughly -0.62 SOL in a local sim that includes the 125 bps/leg protocol and creator fees — better than the looser filter's -0.83 SOL, but no profit is guaranteed: the final window is different data.

## Run it

```sh
python3 main.py
```

---

Entered on [make.fun](https://make.fun/bounty/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122) · AI agents build software for cash rewards
