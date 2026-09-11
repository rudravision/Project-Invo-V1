# What INVO's screen actually exposes (measured, not assumed)

Captured live from the phone with the Phase-1 accessibility dumper.
Device: Motorola, Android 12 (sdk 31). INVO `com.involio.app` v1.0.59, single Flutter
`MainActivity`, one `FrameLayout` host. Raw tree: 51 nodes, **no OCR needed**.

## Screen: in-app Notifications feed  (this is our signal source)

```
View desc=Notifications [click]                         <- page title
ScrollView
  View desc="meduolis   ·  9h  @booobsas updated DOGE"   [click]
  View desc="Prince     ·  14h @luxora closed trade"     [click]
  View desc="Bones      ·  16h @bones updated trade"     [click]
  View desc="Prince     ·  16h @luxora opened new trade" [click]
  View desc="Bones      ·  21h @bones closed trade"      [click]
  ...
```

Every event is **one clickable node whose `contentDescription` already contains
everything we need**, in this shape:

`<Display Name> · <age> @<handle> <event text>`

| part | example | use |
|---|---|---|
| display name | `Bones` | verification only |
| age | `16h`, `9h`, `1d` | staleness guard (see caveat) |
| handle | `@bones` | whitelist key |
| event text | `opened new trade` / `closed trade` / `updated DOGE` / `closed HYPE` | OPEN / UPDATE / CLOSE + asset when named |

Bottom navigation (deterministic, semantic, no coordinates):

```
Button desc="Home Tab 1 of 5"          -> go home
Button desc="Notifications Tab 4 of 5" -> open this feed   <- how we get here programmatically
Button desc="Mimic Tab 3 of 5"         -> Mimic page
```
Also present: `View desc=Create [click]` (composer, never touch it).

## Backup path: read the feed (METHOD 4) - confirmed viable

1. Make sure INVO is foreground (`getLaunchIntentForPackage`), on the feed
   (`clickByDescContains("Notifications Tab 4 of 5")`).
2. Collect every clickable node whose `desc` contains `@`.
3. Newest is at the top. A new event = items above the previous top item.
4. Parse handle + event text, check whitelist + risk, then (Phase 3) click that
   same node to open the trade detail and read asset/direction/leverage/entry.

## Caveats found in the real data (these change the design)

1. **INVO does post system notifications** - proved by Android's own per-channel
   counters on Settings -> Apps -> Invo -> Notifications:
   - `All Invo notifications` = ON
   - `Miscellaneous` - **~9 notifications per day**  (this is the trade-alert stream)
   - `High Importance Notifications` - ~1 per week
   Our 35-second Phase-1 window simply missed them, which is why the log said 0.
   ~9 per day means one every 2-3 hours, so any feasibility test must run for hours,
   not seconds. **METHOD 1 is therefore the primary trigger** (event arrives pushed,
   ~0 latency) and the feed watcher is the backup/verification path. The first real
   capture will show whether the title/text is informative or generic, and whether
   `contentIntent` jumps straight to the trade page (METHOD 2).
2. **Age is hour-granular** (`9h`, `16h`, `1d`) — the feed label cannot tell us how
   stale a signal is to the minute. So "seconds between trader action and our action"
   is unmeasurable from the feed; we measure poll-cycle latency and treat any item
   older than `MAX_SIGNAL_AGE` as stale (configurable, default: skip anything not
   within the same session).
3. **The same text appears more than once** (two identical `@luxora closed trade 14h`
   rows). So dedupe cannot be by text alone — it is by list position diff, and the
   trade identity comes from the detail page (Phase 3), not the feed row.
4. Feed rows carry no direction/leverage/price. Those must come from the detail
   screen, which we have not captured yet (next data needed).

## How Phases 3+ are measured from the phone only (build P1.4)

No PC is involved in gathering data any more. Two buttons:

| Button | What it does | What comes back |
|---|---|---|
| 11. SNAP 5 PAGES | photographs whatever screen is in front, every 8 s, 5 times, while you walk through INVO | per page: package, node count, and every line containing trade words, with bounds and whether it is tappable |
| 12. READ TOP TRADE | opens the newest feed row from an approved trader, reads the page, presses nothing, goes back | asset / direction / leverage / entry, the Mimic control and its bounds, plus a "MISSING:" list |

Both write into the same result text, so 8. COPY RESULT carries everything to me in one paste.
Snapshots and node trees are also saved under the app's external `dumps/` folder for deep dives.

`12` deliberately stops at "read": this build contains no swipe and no gesture code,
so it cannot open, size or close a position by itself.

## The real execution surface: a trader's trade cards (captured 2026-09-11, build P1.4)

INVO opens on its trader list, not on the notification feed. Tapping a trader card
(`@bones`) opens their page, and *that* page is where the money data lives. Verbatim,
two clickable cards from your phone:

```
btc 40x short $77,713.00 +5.30% exit price $77,610.00 hold time 8 minutes     (50,603-1030,968)
btc 40x short $77,672.00 +6.26% $77,550.50                                    (50,1375-1030,1705)
mimic trade                                                                    (90,1565-990,1665)
```

Measured facts, in order of how much they change the design:

1. **One node holds the whole trade.** asset, leverage, direction, entry price, PnL,
   exit price and hold time arrive as a single `contentDescription` string. No page
   walking, no OCR, no opening a detail screen to get the numbers.
2. **The card that still has an open trade carries its own `Mimic Trade` button,
   inside the card's own bounds.** The closed card (the one with `exit price`) has no
   button. So "open trade" and "here is how you copy it" are structurally linked, and
   a card can be matched to its button by geometry rather than by layout guessing.
3. The bottom nav is present on these pages as `Button desc="Mimic Tab 3 of 5"`, i.e.
   the same semantic labelling as the Notifications tab, so navigation stays by label.
4. Cards look like `"<asset> <lev>x <long|short> $<entry> [<pnl>%] [exit price $<x>]
   [hold time <n> <unit>]"` - one regex, and any INVO wording change shows up as an
   explicit "no card matched" verdict instead of a silent wrong number.

Consequence for the phases: the Notifications feed is demoted to a *trigger* (it tells
us which trader moved, nothing more); the trader page is where every number is read and
where `Mimic Trade` is pressed. `MovesReader` parses these cards and pairs each with its
button; `Rehearsal.profilePath` uses it, locates only, and never taps the button.
