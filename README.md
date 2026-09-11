# INVO Copier — Phase 1

A phone app that **watches** the INVO app's trade notifications and writes down what it sees.
No trading yet. No money moves yet. That is all Phase 1 does, on purpose.

## Start here

1. Read **`docs/PHASE_1.md`** and follow STEP 1 → STEP 7 in order.
2. Send me the files listed in STEP 7.
3. Phase 2 starts only after Phase 1 produced log output.

## Layout

```
android/     the Android Studio project (this is what you Open in Studio)
config/      invo_config.json - editable risk + whitelist settings
tools/       optional PC helpers (need Python 3, use ADB only)
docs/        PHASE_1.md = the instructions, ARCHITECTURE.md = the plan
```

`tools/`:

| command | what it does |
|---|---|
| `python tools/p1_doctor.py --save` | checks adb / device / permissions / app installed, prints the fix for each failure |
| `python tools/p1_logs.py --timeline` | pulls the phone's log file and prints the Phase-1 verdict |
| `python tools/p1_ui.py --grep mimic` | dumps the INVO screen's accessibility node tree (proves whether OCR is needed) |

## Safety rules baked into the code (not just the docs)

* `DRY_RUN=true` and `AUTOTRADING_ENABLED=false` are the compiled defaults. A broken or missing config file falls back to those.
* Live execution needs **three** independent switches: config `AUTOTRADING_ENABLED=true`, config `DRY_RUN=false`, **and** the on-screen STOP button released. Missing any one = nothing happens.
* The `Mimic Trade` / swipe / submit code does not exist in Phase 1 — there is nothing to accidentally trigger.
* Trader handle, asset, direction and leverage are parsed from the notification, but only ever written to the log. `verdict` in each record shows what a later phase *would* have done.
* Never put your INVO password, seed phrase, or API keys in any file here. The app uses the phone's already-logged-in INVO session and nothing else.

## Honest caveats

* Automating the INVO UI may conflict with their Terms of Service, and a wrong assumption can lose money. Start with the smallest possible live order, watch it yourself, and keep the STOP button pressed whenever you are not watching.
* This is a copy-trading tool, not investment advice. Expect drawdowns.
