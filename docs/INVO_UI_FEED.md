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

## How we will read events (METHOD 4, confirmed viable)

1. Make sure INVO is foreground (`getLaunchIntentForPackage`), on the feed
   (`clickByDescContains("Notifications Tab 4 of 5")`).
2. Collect every clickable node whose `desc` contains `@`.
3. Newest is at the top. A new event = items above the previous top item.
4. Parse handle + event text, check whitelist + risk, then (Phase 3) click that
   same node to open the trade detail and read asset/direction/leverage/entry.

## Caveats found in the real data (these change the design)

1. **No system notification was ever seen** (`INVO notifications today: 0`, while 15
   other apps posted). The feed is therefore the primary source, not a fallback.
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
