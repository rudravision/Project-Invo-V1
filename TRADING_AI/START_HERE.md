# Start Here

No technical knowledge needed. Read this once, then you only ever
double-click one file.

---

## What this thing is

Every evening, India's National Stock Exchange publishes a free file listing
what every stock did that day. This system downloads that file, keeps it
safely on your SSD, and each day tells you:

- **Which sectors are strong or weak** (a colour-coded heatmap)
- **Which stocks score best** on momentum and trend (a ranked shortlist)
- **How that ranking rule would have performed in the past** (a backtest)

It is a **research assistant**, not an auto-trader. It never places an order,
never touches your money, and never connects to your broker account for
trading. It gives you a shortlist to look at yourself.

**Cost: ₹0 per month.** Free public data, your own computer, your own SSD.

---

## What you do, in order

### Step 1 — Copy the folder to your SSD

Plug in your SanDisk SSD. Copy the whole `TRADING_AI` folder onto it.

Anywhere on the drive is fine. It does not matter what drive letter Windows
gives it (`D:`, `E:`, `F:`…) — the system works that out by itself, every time.

### Step 2 — Double-click `INSTALL.bat`

Once only. It spends 2–5 minutes installing itself **on the SSD**, so your
computer's own disk stays clean, and puts a **TRADING_AI** shortcut on your
desktop.

### Step 3 — Double-click `TRADING_AI` on your desktop

A window opens. That is the whole program. There are no commands to type.

Inside it:

1. Click the big blue **UPDATE & ANALYZE MARKET** button. It does everything
   in one go — checks your internet, downloads the days you are missing,
   checks the data, works out the sectors and the rankings, and saves a
   report. A progress bar tells you where it is. The window stays usable the
   whole time, and you can press **Stop**.
2. **Dashboard** — NIFTY 50, whether the market is rising or falling, how many
   stocks are up versus down, strongest and weakest sector, and whether your
   data is healthy.
3. **Sector Heatmap** — green is strong, red is weak. Click any sector to see
   its stocks ranked strongest to weakest.
4. **Trade Ideas** — top long candidates and top short candidates, each with
   entry, stop loss, target, how many shares to buy, and how much money is at
   risk.
5. **Charts** — click any stock symbol anywhere in the app.

**If anything is wrong**, the dashboard tells you in plain English with a
button to fix it. You will never see a message like `missing_candles: 7600`;
you will see "Historical database is incomplete" and a **REPAIR DATA** button.

**About the percentages.** Where you see something like "54% — based on 1,240
historical observations", that number is how often setups with that same score
actually rose the next day, measured on data the model had never seen. Where
there is not enough evidence, it says **"Insufficient data"** rather than
inventing a number. Nothing here guarantees a profit.

The old `CLICK_ME_FIRST.bat` menu still works if you prefer it, and the
command-line scripts are all still there for troubleshooting.

> **If it says Python is not installed:** it will show you exactly what to do.
> Python is free, from python.org. One thing matters: during installation,
> **tick the box that says "Add python.exe to PATH"** on the first screen.
> It's at the bottom and easy to miss. Then double-click the file again.

After that, you get a menu. Type a number, press Enter. That's the whole
interface.

### Step 3 — Press `1` (Check my computer and SSD are ready)

This looks at eight things and reports each in plain English: your SSD, free
space, internet, whether NSE answers, your database, and so on.

It only reads. It cannot break anything.

**What you want to see:** your SanDisk drive listed, with its free space.

> **If it says "SSD detected FAIL":** the check prints a table of every drive
> it can see. Find your SanDisk in that table, note its name, then open
> `config\paths.yaml` in Notepad and add that name under `ssd_name_hints`.
> That's a one-time fix.

### Step 4 — Press `2` (Test which market-data sources work)

**This is the important one.**

I built this system in a cloud sandbox that had no internet access to NSE. So
I genuinely do not know whether these data sources work from your home
connection. I refused to guess.

This step finds out for real. It takes about a minute and sends one small
polite request to each source.

Three possible outcomes:

- **"X sources work"** → excellent, go to Step 5.
- **"Sources answered but refused access"** → NSE is blocking automated
  requests from your network right now. Try again in a few hours. If it keeps
  happening, the broker-account route (menu option 7 area) solves it.
- **"Nothing worked"** → check your internet is on, and that a VPN or office
  firewall isn't in the way. NSE is also genuinely down sometimes in the
  evening.

### Step 5 — Press `3` (Download real NSE market data)

Downloads about four months of daily data for the NIFTY 200 stocks.

Before it downloads a single byte, it tells you how many megabytes it expects
to use and asks you to confirm. It's roughly 30 MB — nothing on a 2 TB drive.

It only fetches days you don't already have. Running it again tomorrow costs
one day's download, not the whole lot.

**If you skipped Step 4, this refuses to run.** That's deliberate — it won't
download blind, and it will never invent data to look busy.

### Step 6 — Press `4` (Show me today's rankings and sector heatmap)

The actual output. Sector heatmap, ranked stock shortlist, and a backtest.

No internet needed — it reads what's already on your SSD.

### Step 7 — Press `5` (Open the visual dashboard)

The same information as charts and colour-coded tables in your web browser,
instead of text.

It runs on your own computer. Nothing is uploaded anywhere. Close it by
pressing `Ctrl+C` in the black window.

---

## Just want to look around first?

Press **`9`** for practice data.

This loads invented random numbers so you can click through the heatmap,
rankings and dashboard and see what everything looks like — without needing
the internet to cooperate.

It is labelled **PRACTICE** everywhere it appears, and the system deliberately
**refuses to give you trading signals** from it. That refusal is intentional:
fake data must never be able to masquerade as a real recommendation.

---

## The one thing you must understand

Sometimes, instead of a stock shortlist, you will see this:

```
WARNING: SIGNAL DISABLED - DATA QUALITY FAILURE
```

**This is the system working correctly, not breaking.**

It means something was wrong with the data — it was stale, a price looked
impossible, days were missing, or a stock split made the numbers lie. Rather
than hand you a confident-looking recommendation built on bad numbers, it
stops and tells you.

A wrong signal costs you money. A refused signal costs you nothing. So when
you see that message: don't trade on it, and run option `1` to find out why.

---

## Your routine, once set up

Each evening after about 7 PM (NSE publishes around 6:30 PM):

1. Double-click `CLICK_ME_FIRST.bat`
2. Press `3` — get today's data
3. Press `4` — see the rankings
4. Press `0` — quit safely

Once a week, press `6` to back everything up.

That's it.

---

## Menu reference

| Key | What it does |
|---|---|
| `1` | Check everything is ready. Read-only, always safe. |
| `2` | Test which data sources actually work |
| `3` | Download real market data (only the days you're missing) |
| `4` | Today's heatmap, rankings and backtest |
| `5` | Visual dashboard in your browser |
| `6` | Back up your data, with verification |
| `7` | Set up phone alerts via Telegram (optional, free) |
| `8` | What this is costing you (should say ₹0) |
| `9` | Load practice data for a safe try-out |
| `0` | Quit safely — makes the SSD safe to unplug |

---

## If something goes wrong

**Press `1` first.** It diagnoses most problems and tells you the fix in
plain English.

Common things:

| You see | What it means | Fix |
|---|---|---|
| "Python is not installed" | Python missing | Install from python.org, **tick "Add to PATH"** |
| "SSD detected FAIL" | Drive not recognised | Add its name to `config\paths.yaml` (Step 3 above) |
| "Disk space FAIL" | SSD nearly full | Free up space |
| "Market data source FAIL" | NSE unreachable | Check internet; try again later |
| "SIGNAL DISABLED" | Data quality problem | Working as intended — don't trade, press `1` |

**Always safe to do:** unplug the SSD after pressing `0`. Your raw downloaded
files are permanently read-only, so nothing can quietly corrupt your history.

---

## What this will never do

- Place a trade or touch your money
- Buy anything or sign you up for a paid service
- Upload your data anywhere
- Delete your files
- Pretend it has data when it doesn't

---

## Worth knowing, when you're ready

Two honest notes, not urgent:

**A free broker account is the biggest upgrade available to you, and it costs
₹0.** Opening an Upstox or ICICIdirect account unlocks live prices and
minute-by-minute history that the free public files don't include. Details in
`docs/FREE_DATA_LIMITATIONS.md`.

**Free data has real limits, and I've written them down honestly.** That same
document lists exactly where free data falls short, what a paid fix would
cost, and — importantly — where I think paying is *not* worth it. Most of it
isn't.

Nothing will ever be purchased automatically.

---

*This is a research tool. It is not investment advice. Rankings are a starting
point for your own judgement, not instructions. Never risk money you cannot
afford to lose.*
