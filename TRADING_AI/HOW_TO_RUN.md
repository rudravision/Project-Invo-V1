# How To Run TRADING_AI

Written for someone who has never used a command line. Follow it top to
bottom. Nothing here can break your computer.

---

## Part 1 — Get the new files onto your SSD

### Step 1. Make a safety copy first

Open `G:\Trading\`

Right-click the `TRADING_AI` folder → **Copy**. Then right-click on empty
space → **Paste**.

You now have `TRADING_AI - Copy`. Leave it alone. If anything ever goes
wrong, that copy is your way back.

### Step 2. Download the new version

Open this link in your browser (you must be signed in to GitHub):

https://github.com/rudravision/Project-Invo-V1/tree/arena/01a0cf67-project-invo-v1

On that page:

1. Click the green **Code** button (top right area).
2. Click **Download ZIP**.

A file lands in your Downloads folder.

### Step 3. Unzip it

Right-click the downloaded ZIP → **Extract All...** → **Extract**.

You get a folder with a long name starting `Project-Invo-V1-arena-`.
Open it. Inside is a folder called **`TRADING_AI`**. Open that one too.

You should now be looking at files like `TRADING_AI.bat`, `INSTALL.bat`,
`app`, `scripts`, `docs`.

### Step 4. Copy the new files over the old ones

1. Press **Ctrl + A** to select everything in that folder.
2. Press **Ctrl + C** to copy.
3. Go to `G:\Trading\TRADING_AI`
4. Press **Ctrl + V** to paste.

Windows will ask what to do about files that already exist. Choose:

> **Replace the files in the destination**

**This is safe.** The download contains program files only. Your database,
your downloaded prices, your backups, your logs and your settings are not in
it, so they cannot be overwritten.

---

## Part 2 — Install

Double-click **`INSTALL.bat`** in `G:\Trading\TRADING_AI`.

A black window opens and text scrolls past. This takes 2–5 minutes. It is
adding one new component the window needs.

If Windows shows a blue "Windows protected your PC" box, click **More info**
→ **Run anyway**. That box appears for any file downloaded from the internet.

When it finishes it says **INSTALL COMPLETE** and puts a **TRADING_AI**
shortcut on your desktop. Press any key to close the black window.

---

## Part 3 — Start it

Double-click **TRADING_AI** on your desktop.

Two things appear:

- a **small black window** — leave it open, it is the engine. Closing it
  shuts the program down.
- the **TRADING_AI window** — this is the actual program.

---

## Part 4 — First run

### You will see a red banner. That is correct.

It will say something like *"Historical database is incomplete"*. Your
database currently holds about 9,000 records and is missing most of its
history. The program is refusing to give you trade ideas from incomplete
data. **That is it working properly, not a fault.**

### Click the big blue button: UPDATE & ANALYZE MARKET

It is on the left-hand side.

Now wait. A progress bar shows what it is doing — checking sources,
downloading, checking data quality, ranking stocks.

**The first run downloads 5 years of history, so it will take a while.**
Plan for anywhere between half an hour and a few hours depending on your
internet. Leave it running and go do something else. You can keep clicking
around the window while it works — it will not freeze, and there is a
**Stop** button if you need it.

Every run after this one only fetches the new days, so it will take a minute
or two, not hours.

### When it finishes

The red banner should turn green. Then look at, in this order:

1. **Dashboard** — NIFTY 50, is the market rising or falling, how many stocks
   are up versus down, strongest and weakest sector.
2. **Sector Heatmap** — green is strong, red is weak. Click any sector to see
   its stocks ranked strongest to weakest.
3. **Trade Ideas** — top long candidates and top short candidates. Each one
   shows entry price, stop loss, target, how many shares, and how much money
   is at risk.
4. **Charts** — click any stock symbol anywhere in the program.

### One more click, once

Go to **Dashboard** → **Rebuild Calibration**.

This works out the probabilities by checking how often each type of setup
actually rose in the past. Until you do this, every probability will read
**"Insufficient data"** — because it genuinely is. Do it once after your
first big download, then again every few months.

---

## Part 5 — Setting your money

Go to **Settings**, or use the Capital & Risk box at the top of **Trade
Ideas**.

| Setting | What it means | Suggested |
|---|---|---|
| Trading capital | Total money you are trading with | your real figure |
| Max risk per trade | Most you accept losing on one trade | 1% |
| Max positions | How many trades open at once | 5 |
| Max daily loss | Stop for the day if you lose this much | 3% |

With ₹10,00,000 capital and 1% risk, each trade risks ₹10,000 — and the
program works out the share quantity for you from the stop-loss distance.
That is why two stocks at the same price get different quantities.

Click **SAVE SETTINGS**. There is a **RESET TO SAFE DEFAULTS** button if you
ever want to start over.

---

## If something goes wrong

**The program tells you in plain English with a button to fix it.** You
should never see a technical code. If you see a red banner, read it and press
the button it offers — usually **REPAIR DATA** or **UPDATE NOW**.

| Problem | What to do |
|---|---|
| Nothing happens when I double-click TRADING_AI | Run `INSTALL.bat` again |
| "TRADING_AI is not installed yet" | Run `INSTALL.bat` |
| Window opens but is blank | Wait 10 seconds, then press **F5** |
| Download keeps failing | Check your internet, then go to **Data Sources** → **TEST ALL SOURCES** |
| Red banner will not go away | Press **REPAIR DATA**, let it finish, then **UPDATE & ANALYZE MARKET** |
| I want to undo everything | Delete `G:\Trading\TRADING_AI` and rename `TRADING_AI - Copy` back to `TRADING_AI` |

---

## Things worth knowing

- **It never places a trade.** It never touches your broker or your money.
  It produces a shortlist for you to look at yourself.
- **The percentages are measured, not invented.** "54% — based on 1,240
  historical observations" means that out of 1,240 similar past setups, 54%
  rose the next day. Where there is not enough evidence it says
  **"Insufficient data"** rather than making a number up.
- **It will be wrong regularly.** A 54% edge is a slight lean, not a
  prediction. This is a research tool, not a profit machine.
- **It costs ₹0 per month.** Free public data, your computer, your SSD.
- **The old command-line scripts still work.** Nothing was removed. You just
  do not need them any more.
