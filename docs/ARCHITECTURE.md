# Architecture and the phase map

## Signal detection is separated from trade execution, permanently

```
NotificationListenerService  ─┐
                              ├─> InvoEventParser (text -> trader/asset/action)
AccessibilityService         ─┘          │
                                         v
                                  RiskManager (limits, whitelist, dedupe)
                                         │  only if ALLOWED
                                         v
                                  TradeAutomationEngine (UI actions, verification)
                                         │
                                         v
                                  Room/SQLite: trade map + state machine + audit log
```

Nothing in the left column can spend money. Nothing in the right column runs unless
the middle column returned ALLOW. That is enforced by files, not by promises.

## Package layout (Phase 1 files are real, rest are next phases)

```
com.invocopier/
  notification/InvoNotificationListener.kt   Phase 1  - detects, METHOD 1 + 2 probe
  accessibility/InvoAccessibilityService.kt  Phase 1  - window probe + UI dumps, gestures added Phase 4
  parser/InvoEventParser.kt                  Phase 1  - text -> OPEN/UPDATE/CLOSE + fingerprint
  config/CopierConfig.kt, KillSwitch.kt      Phase 1  - editable limits, dual switch
  logging/EventLog.kt                        Phase 1  - jsonl + logcat
  util/BundleDump.kt                         Phase 1  - raw notification payload, no guessing
  ui/MainActivity.kt                         Phase 1  - status, self-test, STOP button
  risk/RiskManager.kt                        Phase 5  - size + limits gate
  state/TradeStateManager.kt                 Phase 5  - DETECTED/OPENING/OPEN/UPDATING/CLOSING/CLOSED/FAILED
  state/PositionMap.kt                       Phase 7  - source trade fingerprint -> my copied position
  database/                                  Phase 5  - Room (survives reboot and app kill)
  automation/TradeAutomationEngine.kt        Phase 4+ - selectors, verification, retry-safe
```

## What each phase may touch

| phase | new capability | money risk |
|---|---|---|
| 1 | read notifications, read UI tree | none |
| 2 | open the trade screen | none |
| 3 | read trader/asset/direction/leverage/entry from the screen | none |
| 4 | press `Mimic Trade`, read the order page | none |
| 5 | fill position size, stop before the swipe (dry-run) | none |
| 6 | one tiny live order, only with 3 switches on | small |
| 7 | auto-close when the trader closes | medium |
| 8 | mirror TP/SL/size changes | medium |
| 9 | whitelist of 3+ traders, exposure caps | medium |
| 10 | 24/7 box (cheap used phone or emulator on a VPS) | operational |

## Rules every later phase must keep

1. Re-verify on screen before acting: expected trader, asset, direction must match the notification, twice (page open, and again right before submit).
2. Missing field, unexpected dialog, unrecognised screen, duplicate fingerprint -> abort and log, never guess.
3. Every action is followed by a read-back verification; unverified -> `FAILED`, never blind retry.
4. Leverage is clamped to `MAX_LEVERAGE`; `COPY_EXACT_LEVERAGE=false` is the default.
5. State and the position map live in Room so a reboot or an INVO crash cannot lose track of an open copy.
6. Latency is measured per step (`postTime -> captured -> opened -> parsed -> submitted -> confirmed`) because that is the only number that decides whether the whole idea is worth running.
