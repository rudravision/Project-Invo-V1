"""
One plain-English instruction per trade, for someone who is not a trader.

Design rules, in priority order:

1. **Never sound more certain than the evidence.** If the probability is
   "Insufficient data", the instruction says so in words rather than
   printing a confident order. A beginner cannot judge which numbers are
   solid, so the wording has to do it for them.

2. **Every figure is in rupees as well as percent.** "Stop loss at 4.8%"
   means nothing to a new trader; "if it drops to Rs 2,154 you lose about
   Rs 2,475" is a decision they can actually make.

3. **State the holding horizon truthfully.** This system holds only
   end-of-day data. It cannot see intraday price movement, so it cannot
   give intraday entries or exits. The measured horizon is the NEXT
   SESSION, and the wording says exactly that.

4. **Say when not to trade.** If the strategy's own backtest lost money,
   the card carries a paper-trading warning instead of an instruction.
   A tidy one-line order from a losing strategy is the most dangerous
   thing this program could print.
"""
from __future__ import annotations

import dataclasses
import math

# What the probability was actually measured over. Changing the calibration
# horizon must change this text too.
HORIZON_DAYS = 1
HORIZON_TEXT = ("the next trading session (buy at tomorrow's open, review at "
                "tomorrow's close)")

# This system stores one row per stock per day. There is no intraday feed,
# so no honest intraday instruction can be produced.
INTRADAY_NOTE = (
    "This program uses end-of-day prices only. It cannot see what happens "
    "during the day, so it cannot tell you intraday entries or exits. Every "
    "instruction here is for the next session as a whole.")


def rupees(v: float | None) -> str:
    """Indian-format rupees, no decimals - beginners read whole numbers."""
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "-"
    n = int(round(abs(v)))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-Rs " if v < 0 else "Rs ") + s


def _pct(a: float, b: float) -> float:
    return ((a / b) - 1.0) * 100.0 if b else 0.0


@dataclasses.dataclass
class Instruction:
    headline: str            # the one line a beginner reads
    steps: list              # ordered, concrete actions
    confidence: str          # honest statement about the probability
    checks: str              # how many confirmations agree
    warnings: list           # anything that should stop them
    tradeable: bool          # False = do not place this trade
    horizon: str = HORIZON_TEXT

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def instruction(c: dict, *, strategy_is_profitable: bool | None = None,
                calibrated: bool = True) -> Instruction:
    """Turn one candidate dict into a plain instruction.

    `strategy_is_profitable` is the verdict from the last backtest:
    True/False/None(not run). It controls whether this is presented as a
    trade or as paper practice.
    """
    sym = c.get("symbol", "?")
    side = (c.get("side") or "LONG").upper()
    signal = (c.get("signal") or "").upper()
    qty = int(c.get("quantity") or 0)
    entry = float(c.get("entry") or 0)
    stop = float(c.get("stop") or 0)
    target = float(c.get("target") or 0)
    profit = float(c.get("expected_profit") or 0)
    loss = float(c.get("expected_loss") or 0)
    prob = c.get("probability") or {}
    conf = c.get("confirmation_summary") or {}

    warnings: list[str] = []
    buy_word = "BUY" if side == "LONG" else "SHORT-SELL"
    exit_word = "Sell" if side == "LONG" else "Buy back"

    # ---- is this tradeable at all? ---------------------------------------
    tradeable = True
    if signal == "AVOID":
        tradeable = False
        warnings.append(
            f"Marked AVOID: this trade is against the overall market "
            f"direction. Skip it.")
    if not prob.get("available"):
        warnings.append(
            "No reliable probability yet for this stock's score. "
            "The program has not seen enough similar past cases to say how "
            "often this worked. Treat it as unproven.")
    if strategy_is_profitable is False:
        tradeable = False
        warnings.append(
            "The strategy's own backtest LOST money over your history. "
            "Practise on paper - write the trade down and check it in a few "
            "days - rather than risking real money.")
    elif strategy_is_profitable is None:
        warnings.append(
            "The backtest has not been run on your data yet, so there is no "
            "evidence this strategy makes money. Run RUN BACKTEST first.")
    if not calibrated:
        warnings.append(
            "Probabilities have not been built yet. Press Rebuild "
            "Calibration on the dashboard.")

    # ---- headline --------------------------------------------------------
    if not tradeable:
        headline = f"DO NOT TRADE {sym} today."
    elif qty <= 0:
        headline = f"No position size fits your capital for {sym}."
        tradeable = False
    else:
        headline = (f"{buy_word} {qty} shares of {sym} at about "
                    f"{rupees(entry)} per share "
                    f"({rupees(qty * entry)} total).")

    # ---- steps -----------------------------------------------------------
    steps: list[str] = []
    if tradeable and qty > 0:
        steps.append(
            f"1. Place the order near the opening price, around "
            f"{rupees(entry)}. If it opens far above this, skip the trade - "
            f"do not chase it.")
        steps.append(
            f"2. Set a stop loss at {rupees(stop)} "
            f"({abs(_pct(stop, entry)):.1f}% away). If it hits, you lose "
            f"about {rupees(loss)}. Place this immediately, not later.")
        steps.append(
            f"3. {exit_word} at {rupees(target)} "
            f"({abs(_pct(target, entry)):.1f}% away) for a profit of about "
            f"{rupees(profit)}.")
        steps.append(
            f"4. This is measured over {HORIZON_TEXT}. If neither level is "
            f"reached, review it at the close rather than holding on hope.")
        rr = c.get("rr")
        if rr:
            steps.append(
                f"5. You are risking {rupees(loss)} to make {rupees(profit)} "
                f"- about 1 to {rr}. Never move the stop loss further away "
                f"to avoid taking a loss.")

    # ---- confidence ------------------------------------------------------
    if prob.get("available"):
        n = prob.get("n_observations")
        confidence = (
            f"In the past, trades scoring like this one went the right way "
            f"{prob.get('display')} of the time, out of {n:,} similar cases "
            f"the program had never seen before. That is a slight lean, not "
            f"a promise.")
    else:
        confidence = (
            "No probability can be shown for this trade. The program needs "
            "at least 200 past cases with a similar score before it will "
            "quote a number, and it does not have them. Anyone who gives "
            "you a confident percentage here is guessing.")

    # ---- confirmations ---------------------------------------------------
    if conf:
        checks = conf.get("text", "")
        missing = conf.get("failed_labels") or []
        unknown = conf.get("unknown_labels") or []
        if missing:
            checks += ". Not agreeing: " + ", ".join(missing).lower()
        if unknown:
            checks += ". Cannot check: " + ", ".join(unknown).lower()
    else:
        checks = "No confirmation checks were run."

    return Instruction(headline=headline, steps=steps, confidence=confidence,
                       checks=checks, warnings=warnings, tradeable=tradeable)


def session_advice(*, blocked: bool, strategy_is_profitable: bool | None,
                   n_long: int, n_short: int) -> dict:
    """The single paragraph shown above the list, in plain words."""
    if blocked:
        return {"tone": "bad",
                "title": "No trades today",
                "text": ("The data did not pass its checks, so the program "
                         "will not suggest anything. This is deliberate - "
                         "trading on incomplete data is worse than not "
                         "trading. Press REPAIR DATA.")}
    if strategy_is_profitable is False:
        return {"tone": "bad",
                "title": "Paper trading only",
                "text": ("The strategy lost money in its own backtest on "
                         "your history. The ideas below are shown so you can "
                         "follow along and learn, not so you can place them. "
                         "Write them down, check them in a week, and see for "
                         "yourself before risking anything.")}
    if strategy_is_profitable is None:
        return {"tone": "warn",
                "title": "Not verified yet",
                "text": ("You have not run a backtest on your own data, so "
                         "there is no evidence yet that this makes money. "
                         "Run RUN BACKTEST and TEST SETTINGS first.")}
    if n_long + n_short == 0:
        return {"tone": "warn", "title": "Nothing qualifies today",
                "text": ("No stock passed the filters. Doing nothing is a "
                         "position too - it costs you nothing.")}
    return {"tone": "good",
            "title": f"{n_long + n_short} ideas for the next session",
            "text": ("Risk only what you planned per trade, place the stop "
                     "loss at the same time as the buy, and accept that a "
                     "fair share of these will lose. " + INTRADAY_NOTE)}
