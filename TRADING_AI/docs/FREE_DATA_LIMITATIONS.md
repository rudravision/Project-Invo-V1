# Where Free Data Is Not Good Enough

Free public data is genuinely excellent for **daily, end-of-day, cross-sectional
research on liquid Indian equities**. That is the bulk of what this system does,
and for that purpose it is not meaningfully worse than paid data.

It is **not** equivalent to institutional-grade data. Below is an honest
component-by-component account of where it falls short, what it costs to fix,
and whether fixing it is actually worth the money.

No purchase has been made. Nothing will be purchased automatically.

---

## 1. Tick-level / order-book data — **NOT AVAILABLE FREE**

| | |
|---|---|
| **What's missing** | Full tick data, order-book depth beyond L1, trade-by-trade prints |
| **Free substitute** | None. Broker websockets give throttled snapshots (typically a few per second), not every tick |
| **What breaks** | Microstructure research, realistic slippage modelling, HFT, precise VWAP execution studies |
| **Paid fix** | NSE official tick data (via the exchange's data licensing), or vendors such as GDFL / TrueData |
| **Indicative cost** | NSE historical tick/L2 licensing runs into **lakhs of ₹ per year**. Vendor tick packages typically **₹15,000–₹60,000+ one-off or annual**, varying by depth and history |
| **Measurable benefit** | Slippage estimates accurate to ~1–2 bps instead of the flat 10 bps assumed in `CostModel` |
| **Verdict** | **Not worth it.** A swing/positional system rebalancing weekly is dominated by signal quality, not by microstructure. Revisit only if you go intraday-systematic |

---

## 2. Deep historical intraday — **PARTIALLY AVAILABLE**

| | |
|---|---|
| **What's missing** | Many years of 1-minute candles across a wide universe |
| **Free substitute** | Broker APIs give intraday history, but depth is limited and varies by broker; ICICI Breeze is documented as the most generous (~3 years of 1-second, longer for 1-minute) |
| **What breaks** | Intraday strategy backtests with a statistically meaningful sample; intraday ML features |
| **Paid fix** | GDFL, TrueData, or a broker's extended historical package |
| **Indicative cost** | Roughly **₹10,000–₹30,000/year** for retail-grade 1-minute history across NSE cash + F&O (verify current pricing — vendor rates change) |
| **Measurable benefit** | Enables honest intraday backtesting. Without it, any intraday claim is unfalsifiable |
| **Verdict** | **Worth it only if you actually trade intraday.** Open a free ICICIdirect/Upstox account first and see whether the free depth is sufficient. Cost ₹0 to find out |

---

## 3. Real-time streaming quotes — **AVAILABLE FREE, WITH CONDITIONS**

| | |
|---|---|
| **What's missing** | Nothing, if you have a broker account |
| **Free substitute** | Upstox / Fyers / Dhan / Angel One websockets are free with an account |
| **Catch** | Access token **expires daily** (SEBI rule) — needs a daily login step. From 01-Apr-2026 a **static IP** is mandatory for API-based trading |
| **Paid fix** | Not needed |
| **Verdict** | **Do not pay.** Open a free broker account. This is the single highest-value ₹0 action available to you |

---

## 4. Historical option chain / expired-contract OI — **LARGELY UNAVAILABLE FREE**

| | |
|---|---|
| **What's missing** | Historical option chains, IV surfaces, expired-contract intraday data |
| **Free substitute** | NSE F&O bhavcopy gives **EOD** OI and settle per contract — genuinely useful, and this system ingests it. Live chains available via broker APIs. Historical *intraday* chains are not free |
| **What breaks** | Options backtesting, IV-rank signals, gamma-exposure studies |
| **Paid fix** | Upstox Plus expired-instrument API; vendors selling options history |
| **Indicative cost** | Upstox Plus is a modest monthly add-on; third-party options history datasets commonly **₹10,000–₹50,000** |
| **Measurable benefit** | Only matters if you trade options systematically |
| **Verdict** | **Defer.** EOD OI from the free bhavcopy covers OI-buildup and PCR signals, which is most of the retail-usable edge |

---

## 5. Delivery data — **AVAILABLE FREE, SINGLE POINT OF FAILURE**

| | |
|---|---|
| **Status** | `sec_bhavdata_full` is free and complete |
| **Risk** | **No free backup exists.** If NSE changes or removes that file, delivery-based features go dark |
| **Mitigation in code** | Delivery features are optional; the ranker degrades gracefully without them rather than crashing |
| **Verdict** | Accept the risk. Keep every downloaded file immutably — the archive you build *is* your backup, and it gets more valuable the longer you run |

---

## 6. Corporate actions / adjusted prices — **THE BIGGEST REAL WEAKNESS**

| | |
|---|---|
| **What's missing** | A clean, machine-readable, historically complete split/bonus/dividend adjustment factor series |
| **Free substitute** | NSE publishes corporate actions, but stitching them into a correct adjusted price series is fiddly and error-prone. Yahoo provides adjusted prices but with known India-specific quirks |
| **What breaks** | **Backtests silently produce wrong results.** An unadjusted 1:5 split looks like an −80% crash |
| **Mitigation in code** | `app/data/quality.py` flags any overnight move >20% as a possible corporate action (`WARN`) and >60% as an `ERROR` that blocks signals. It **flags rather than silently "fixes"** — a wrong auto-adjustment is worse than a visible warning |
| **Paid fix** | A vendor with a curated adjustment-factor series (TrueData, Refinitiv, or similar) |
| **Indicative cost** | Bundled into data subscriptions, typically **₹10,000+/year** at the retail end |
| **Measurable benefit** | Removes a genuine source of backtest error. This is the free-data gap most likely to actually mislead you |
| **Verdict** | **The one worth watching.** Start free with the flagging approach, inspect the warnings manually for your ~200-stock universe (a handful of events per month — very manageable), and only pay if manual handling becomes a burden |

---

## 7. Fundamentals — **THIN**

| | |
|---|---|
| **Free substitute** | Index files carry P/E, P/B, dividend yield at the index level. Company-level quarterly fundamentals are not cleanly available free |
| **Verdict** | This system is price/volume-driven, so this is not on the critical path. Revisit only if you add fundamental factors |

---

## Summary — recommended spend, in priority order

| Priority | Action | Cost | Why |
|---|---|---|---|
| 1 | Open a free broker account (Upstox or ICICIdirect) | **₹0** | Unlocks real-time quotes and intraday history. Biggest gain per rupee, and the rupee count is zero |
| 2 | Run the system on free EOD data for 2–3 months | **₹0** | Find out empirically whether your edge needs better data. Most don't |
| 3 | Manually review corporate-action warnings | **₹0** | Closes the most dangerous free-data gap with attention instead of money |
| 4 | *Only if going intraday:* 1-minute history vendor | ~₹10–30k/yr | Makes intraday backtests honest |
| 5 | *Only if trading options:* options history | ~₹10–50k | Narrow use case |
| — | Tick/L2 data | Lakhs | **Not justified** for this system |

**Current monthly cost: ₹0.** Tracked in `scripts/cost_tracker.py`.

> All prices above are indicative ranges gathered during research on
> 23-Sep-2026 and **have not been re-confirmed with vendors**. Get a current
> quote before committing to anything.
