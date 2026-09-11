# PHASE 1 — build and run the notification logger

Only one job: prove we can **see** INVO's notifications, and record what they contain.
It cannot trade. There is no trade code in this phase.

Everything below is copy-paste. `>` means "type this in the terminal".

---

## STEP 1 — install the two free things

1. **Android Studio** (free): https://developer.android.com/studio → big blue *Download Android Studio* → run it → on the first wizard choose **Standard** everywhere and finish (it installs the SDK for you).
2. Nothing else. No Python needed for Phase 1 (the optional `tools/*.py` helpers need Python 3, which most Macs already have; on Windows you'd get it from the Microsoft Store → "Python 3.12").

Verify:

```
> "C:\Users\%USERNAME%\AppData\Local\Android\Sdk\platform-tools\adb.exe" version      (Windows)
> ~/Library/Android/sdk/platform-tools/adb version                                    (Mac)
```

Expected: `Android Debug Bridge version 1.0.41`. If that path fails, adb is still missing → Studio → Settings → Languages & Frameworks → Android SDK → **SDK Tools** tab → tick *Android SDK Platform-Tools* → Apply.

---

## STEP 2 — turn on USB debugging on the phone

1. Settings → About phone → tap **Build number** 7 times → "You are now a developer".
2. Settings → System → **Developer options** → turn on **USB debugging**.
3. Plug the phone in with a data cable. On the phone popup *Allow USB debugging?* → tick "Always allow" → **Allow**.

Verify:

```
> adb devices
```

Expected:

```
List of devices attached
R58xxxxxxx    device
```

If it says `unauthorized`, look at the phone and tap Allow. If it says `offline`, re-plug.

---

## STEP 3 — build the APK

1. Open Android Studio → **Open** → select the **`android`** folder of this project (not the project root) → OK.
2. Wait. Bottom-right progress bar: *Gradle sync* … *Downloading Gradle 8.9* … it can take 5–15 minutes the first time. Do nothing until it stops.
   - If Studio complains that the Gradle wrapper jar is missing: **File → Settings → Build, Execution, Deployment → Build Tools → Gradle** → *Use Gradle from* → **'gradle-wrapper.properties' file** → OK → then **File → Sync Project with Gradle Files**.
3. Top menu: **Build → Build APK(s)** (older Studio: *Build → Make Module 'app'*).

Expected output window:

```
BUILD SUCCESSFUL in 1m 12s
BUILD OUTPUTS APKS app/build/outputs/apk/debug/app-debug.apk
```

If instead you see errors: **Copy the whole red error box and send it to me.** Do not try to fix Android code yourself.

---

## STEP 4 — install it, grant notification access

In Studio just press the green **▶ Run** button with the phone connected. That installs and launches it.

Or with the terminal:

```
> adb install -r android/app/build/outputs/apk/debug/app-debug.apk
> adb shell cmd notification allow_listener com.invocopier/com.invocopier.notification.InvoNotificationListener
> adb shell settings get secure enabled_notification_listeners
```

Expected last line:

```
com.invocopier/com.invocopier.notification.InvoNotificationListener
```

Then open the app **INVO Copier P1** on the phone. The status box must say:

```
Notif access   : GRANTED
Listener alive : YES
Mode           : DRY_RUN
Kill switch    : STOPPED (safe)
```

Also expected in the log area on the first line pair:

```
LISTENER_CONNECTED  ... "invoPackage":"com.involio.app" ...
```

---

## STEP 5 — test 1: prove the pipe works (no INVO needed)

On the phone press **3. Run self-test** (allow the *Notifications* permission if asked, then press it again).

Expected: a fake `@bones opened new trade` notification appears on your phone, and in the app's log area you immediately get a line containing

```
{"ev":"POSTED","pkg":"com.invocopier","title":"@bones opened new trade", ... "parse":{"action":"OPEN","asset":"BTC","handle":"@bones","leverage":40 ...
```

✅ If you see that, the whole detection pipeline works and the code is fine.

---

## STEP 6 — test 2: real INVO notifications (the important one)

1. On the phone open INVO, follow the traders you want, and make sure **INVO's own in-app alert/notification settings are switched on** (their profile/settings screen, not Android's).
2. Keep the INVO Copier P1 app open on a second screen or just leave it in background — it runs as a system service, it does not need to be visible.
3. Wait for real events (or trigger one: have a trader open/update/close, or reopen a trade page in INVO). Spend 10–20 minutes in INVO normally.
4. **Also do this while you are in INVO** (this is what saves us Phase 2 and 3): open one trader's trade detail page, then the **Mimic Trade** page, then your own positions page. On each of those screens, come back to INVO Copier P1 and press **5. Dump this screen**. If it says *accessibility not enabled*, press **4. Grant screen access** first, enable *INVO Copier (screen reader)* in the list, then retry.

Verify from the PC, live:

```
> adb logcat -v time -s INVO_P1:V
```

You should see lines with `INVO_P1` scrolling past whenever INVO posts something.

---

## STEP 7 — send me the results

```
> python tools/p1_logs.py --timeline
> python tools/p1_doctor.py --save
> python tools/p1_ui.py --grep trade
```

That writes `reports/phase1-report.md`, `reports/doctor-*.txt`, `reports/ui-*.txt`.

Paste to me:

1. the whole `reports/phase1-report.md`,
2. the console output of `p1_logs.py`,
3. one or two `reports/ui-*.txt` dumps taken on the Mimic Trade page,
4. if anything failed: the exact red text from Studio or the terminal.

If you can't run Python, do this instead and send me the two files:

```
> adb pull /sdcard/Android/data/com.invocopier/files/logs
> adb shell uiautomator dump /sdcard/ui.xml
> adb pull /sdcard/ui.xml
```

---

## What I decide from your data

| What the logs show | What happens next |
|---|---|
| INVO posts notifications with a usable title/text | Phase 2 opens the trade from the notification (fastest path) |
| Notification exists but has no useful text | Phase 2 opens it, then reads the screen with Accessibility |
| Notification has a `contentIntent` that opens the right trade | We skip all tapping and go straight to the trade page |
| **Zero** INVO notifications captured | METHOD 4: poll INVO's in-app notification screen with Accessibility every few seconds |
| `ui-*.txt` shows the real texts / resource-ids | I write the semantic selectors from them (no coordinates) |
| `ui-*.txt` shows almost no nodes | Only then do we consider OCR (`mlkit` text recognition, still free/offline) |

**Phase 2 does not start until Steps 5 and 6 both produce output.**
