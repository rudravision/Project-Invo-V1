package com.invocopier.diagnostics

import android.content.Context
import android.os.Handler
import android.os.Looper
import com.invocopier.accessibility.InvoAccessibilityService
import com.invocopier.config.CopierConfig
import com.invocopier.logging.EventLog
import com.invocopier.notification.InvoNotificationListener
import org.json.JSONObject
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * One button that answers the two questions Phase 1 exists for, in plain words:
 *
 *   1. Does INVO post real system notifications we can read?
 *   2. Can we read INVO's screen content (or will we need OCR)?
 *
 * Question 2 is measured by dumping the foreground screen 8 times, 4 seconds
 * apart, WHILE the user walks through INVO. No adb, no PC commands.
 *
 * Read-only. This class cannot click, swipe or submit anything.
 */
object Phase1SelfTest {

    private val busy = AtomicBoolean(false)
    private val ui = Handler(Looper.getMainLooper())

    @Volatile
    var summary: String = "not run yet"
        private set

    private val keywords = listOf(
        "mimic", "long", "short", "leverage", "position", "profit",
        "loss", "swipe", "size", "entry", "close", "available", "margin"
    )

    fun start(context: Context) {
        if (!busy.compareAndSet(false, true)) return
        val app = context.applicationContext
        val cfg = CopierConfig.load(app)
        summary = "RUNNING - go to INVO now and tap through: feed, a trade, the Mimic Trade page, your positions."
        EventLog.line("SELFTEST_STARTED - switch to INVO and browse for 35 seconds")

        val worker = Thread {
            try {
                runAll(app, cfg)
            } catch (t: Throwable) {
                summary = "SELFTEST CRASHED: " + t
                EventLog.line("SELFTEST_ERROR " + t)
            } finally {
                busy.set(false)
            }
        }
        worker.isDaemon = true
        worker.start()
    }

    private fun runAll(app: Context, cfg: CopierConfig) {
        val out = StringBuilder()
        out.append("INVO COPIER - PHASE 1 RESULT\n")
        out.append("device              : Android ").append(android.os.Build.VERSION.RELEASE)
            .append(" (sdk ").append(android.os.Build.VERSION.SDK_INT).append(")\n")
        out.append("notification access : ").append(yesNo(InvoNotificationListener.enabledInSettings(app))).append("\n")
        out.append("listener running    : ").append(yesNo(InvoNotificationListener.isReady())).append("\n")
        out.append("screen reader on    : ").append(yesNo(InvoAccessibilityService.isReady())).append("\n")
        out.append("INVO installed      : ").append(invoVersion(app, cfg.invoPackage)).append("\n")

        val posted = countInvoNotifications(app, cfg.invoPackage)
        val other = countAllNotifications(app)
        out.append("INVO notifications today : ").append(posted)
            .append("   (other apps: ").append(other).append(")\n")
        out.append("Q1 NOTIFICATIONS    : ")
            out.append(
                when {
                    posted > 0 -> "YES - INVO posts readable notifications. Phase 2 can open trades straight from them."
                    posted == 0 && InvoNotificationListener.isReady() ->
                        "NONE SEEN YET - either INVO posts nothing, or no trader event happened during the test. Keep the app running and check again after a real trade signal."
                    else -> "CANNOT TELL - the listener is not running. Grant notification access first."
                }
            ).append("\n")

        // ---- Q2: can we read INVO's screens? ----
        if (!InvoAccessibilityService.isReady()) {
            out.append("Q2 SCREEN READING     : SKIPPED - enable the screen reader switch in the app first.\n")
        } else {
            out.append("measuring INVO screens for 35 s - open INVO and tap through it now\n")
            EventLog.line("SELFTEST_WATCH_START switch to INVO now")
            var bestNodes = 0
            var bestPkg = ""
            var bestHits = 0
            var bestSample = ""
            var invoScreens = 0
            val dir = File(app.getExternalFilesDir(null) ?: app.filesDir, "dumps")
            if (!dir.exists()) dir.mkdirs()

            var i = 0
            while (i < 8) {
                try {
                    Thread.sleep(if (i == 0) 4000L else 4000L)
                } catch (t: InterruptedException) {
                    break
                }
                i++
                val j = dumpOnMain() ?: continue
                val pkg = j.optString("pkg")
                val nodes = j.optInt("nodeCount")
                val tree = j.optString("tree")
                val lower = tree.lowercase()
                var hits = 0
                for (k in keywords) if (lower.contains(k)) hits++
                try {
                    File(dir, "selftest-" + i + ".txt").writeText("pkg=" + pkg + " nodes=" + nodes + "\n" + tree)
                } catch (t: Throwable) {
                    // ignore write failure
                }
                val o = JSONObject()
                o.put("ev", "SELFTEST_SCREEN")
                o.put("seq", i)
                o.put("pkg", pkg)
                o.put("nodes", nodes)
                o.put("keywordHits", hits)
                EventLog.json(o)

                if (pkg == cfg.invoPackage || pkg.contains("involio")) {
                    invoScreens++
                    if (nodes > bestNodes || hits > bestHits) {
                        bestNodes = nodes
                        bestHits = hits
                        bestPkg = pkg
                        bestSample = firstTexts(tree)
                    }
                }
            }
            out.append("screens captured for INVO : ").append(invoScreens).append("\n")
            out.append("Q2 SCREEN READING     : ")
            out.append(
                when {
                    invoScreens == 0 ->
                        "NO DATA - INVO was never in the foreground during the test. Press the button again and switch to INVO immediately."
                    bestNodes <= 2 ->
                        "BLOCKED - INVO showed only " + bestNodes + " node(s). It exposes no text, so Phase 3 will need on-device OCR (free, ML Kit)."
                    bestHits == 0 ->
                        "PARTIAL - " + bestNodes + " nodes visible but no trade words found. Take a screenshot of the INVO page you were on and send it to me."
                    else ->
                        "WORKS - " + bestNodes + " nodes, " + bestHits + " trade words readable. No OCR needed. Sample: " + bestSample
                }
            ).append("\n")
            if (bestPkg.isNotEmpty()) out.append("measured screen         : ").append(bestPkg).append("\n")
        }

        out.append("(nothing can trade: DRY_RUN=").append(cfg.dryRun)
            .append(", AUTOTRADING=").append(cfg.autoTradingEnabled).append(")")
        summary = out.toString()
        EventLog.line("SELFTEST_RESULT\n" + summary)
    }

    private fun dumpOnMain(): JSONObject? {
        val svc = InvoAccessibilityService.instance ?: return null
        val holder = arrayOfNulls<JSONObject>(1)
        val latch = CountDownLatch(1)
        ui.post {
            try {
                holder[0] = svc.dumpActiveWindow()
            } catch (t: Throwable) {
                EventLog.line("SELFTEST_DUMP_ERROR " + t)
            }
            latch.countDown()
        }
        try {
            latch.await(6, TimeUnit.SECONDS)
        } catch (t: InterruptedException) {
            Thread.currentThread().interrupt()
        }
        return holder[0]
    }

    /** First few readable strings from the node tree, as evidence. */
    private fun firstTexts(tree: String): String {
        val found = ArrayList<String>()
        for (raw in tree.split('\n')) {
            val idx = raw.indexOf("text=")
            if (idx >= 0) {
                val v = raw.substring(idx + 5).trim()
                if (v.isNotEmpty() && !found.contains(v)) {
                    found.add(v)
                    if (found.size >= 4) break
                }
            }
        }
        return found.joinToString(" | ")
    }

    private fun countInvoNotifications(context: Context, pkg: String): Int =
        countLines(context, "\"ev\":\"POSTED\"", "\"" + pkg + "\"")

    private fun countAllNotifications(context: Context): Int =
        countLines(context, "\"ev\":\"POSTED\"", "\"target\":false")

    private fun countLines(context: Context, needleA: String, needleB: String): Int {
        var n = 0
        for (f in EventLog.files()) {
            try {
                for (line in f.readLines()) {
                    if (line.contains(needleA) && line.contains(needleB)) n++
                }
            } catch (t: Throwable) {
                // ignore unreadable file
            }
        }
        return n
    }

    private fun invoVersion(context: Context, pkg: String): String = try {
        "yes, v" + (context.packageManager.getPackageInfo(pkg, 0).versionName ?: "?")
    } catch (t: Throwable) {
        "NO - package " + pkg + " not found (tell me and I will change it)"
    }

    private fun yesNo(b: Boolean): String = if (b) "YES" else "NO"
}
