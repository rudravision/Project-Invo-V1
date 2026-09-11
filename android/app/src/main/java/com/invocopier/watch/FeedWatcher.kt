package com.invocopier.watch

import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import com.invocopier.accessibility.InvoAccessibilityService
import com.invocopier.config.CopierConfig
import com.invocopier.logging.EventLog
import com.invocopier.parser.InvoAction
import org.json.JSONObject
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * PHASE 2 - detection only.
 *
 * Reads INVO's in-app Notifications feed (the Flutter contentDescription rows we
 * measured in docs/INVO_UI_FEED.md), notices rows that appeared since the last
 * poll, classifies them, and writes a FEED_NEW record.
 *
 * It never opens a trade, never taps the feed row, never touches Mimic Trade.
 * The only click it can make is the bottom "Notifications Tab" navigation, and
 * that is off unless the caller passes openApp=true.
 */
object FeedWatcher {

    @Volatile
    var running = false
        private set

    @Volatile
    var statusLine = "feed watch: not running"
        private set

    @Volatile
    var lastEvent = "(none yet)"
        private set

    private var intervalMs = 5000L
    private var autoOpen = false
    private var worker: Thread? = null

    @Volatile
    private var previousTop: String? = null

    private var seen = ArrayList<String>()
    private var polls = 0
    private var events = 0

    private val ui = Handler(Looper.getMainLooper())

    fun start(context: Context, intervalSeconds: Int, openApp: Boolean) {
        val app = context.applicationContext
        if (running) {
            EventLog.line("WATCH_ALREADY_RUNNING")
            return
        }
        if (InvoAccessibilityService.instance == null) {
            statusLine = "feed watch: REFUSED - screen reader service is not running"
            EventLog.line(statusLine)
            return
        }
        intervalMs = (intervalSeconds.coerceIn(2, 300) * 1000).toLong()
        autoOpen = openApp
        previousTop = loadTop(app)
        seen = loadSeen(app)
        running = true

        val t = Thread {
            EventLog.line(
                "WATCH_STARTED intervalMs=" + intervalMs + " openApp=" + openApp +
                    " baselineTop=" + (previousTop ?: "NONE(first run)") + " rememberedRows=" + seen.size
            )
            while (running) {
                val waitMs = try {
                    cycleOnce(app)
                } catch (e: Throwable) {
                    EventLog.line("WATCH_CYCLE_ERROR " + e)
                    4000L
                }
                try {
                    Thread.sleep(if (waitMs < 200L) 200L else waitMs)
                } catch (e: InterruptedException) {
                    break
                }
            }
            statusLine = "feed watch: stopped"
            EventLog.line("WATCH_STOPPED polls=" + polls + " events=" + events)
        }
        t.isDaemon = true
        worker = t
    }

    fun stop() {
        running = false
        val w = worker
        worker = null
        try {
            w?.interrupt()
        } catch (t: Throwable) {
            // ignore
        }
        EventLog.line("WATCH_STOP_REQUESTED")
    }

    fun report(context: Context): String {
        val cfg = CopierConfig.load(context)
        val sb = StringBuilder()
        sb.append("PHASE 2 - FEED WATCHER\n")
        sb.append("running        : ").append(if (running) "YES" else "NO").append("\n")
        sb.append("poll interval  : ").append(intervalMs / 1000).append(" s\n")
        sb.append("polls done     : ").append(polls).append("\n")
        sb.append("new events seen: ").append(events).append("\n")
        sb.append("last event     : ").append(lastEvent).append("\n")
        sb.append("screen reader  : ").append(if (InvoAccessibilityService.isReady()) "YES" else "NO").append("\n")
        sb.append("safety         : DRY_RUN=").append(cfg.dryRun)
            .append(" AUTOTRADING=").append(cfg.autoTradingEnabled).append("\n")
        sb.append("This build can only DETECT. It cannot open or place a trade.")
        return sb.toString()
    }

    private fun cycleOnce(app: Context): Long {
        val cfg = CopierConfig.load(app)
        val svc = InvoAccessibilityService.instance ?: run {
            statusLine = "feed watch: screen reader died - re-enable it"
            return 3000L
        }

        val pm = app.getSystemService(Context.POWER_SERVICE) as? android.os.PowerManager
        val awake = try {
            pm == null || pm.isInteractive
        } catch (t: Throwable) {
            true
        }
        if (!awake) {
            statusLine = "feed watch: running, screen is off"
            return intervalMs
        }

        var rows = onMain<List<String>> { svc.collectFeedRows() } ?: emptyList()

        if (rows.isEmpty() && autoOpen) {
            launchInvo(app, cfg.invoPackage)
            sleep(1800)
            onMain<Boolean> { svc.clickByDescContains("Notifications Tab") }
            sleep(1800)
            rows = onMain<List<String>> { svc.collectFeedRows() } ?: emptyList()
        }

        polls++
        heartbeat()
        if (rows.isEmpty()) {
            val fg = onMain<String> { svc.foregroundPackage() } ?: "?"
            statusLine = "feed watch: running, no feed rows visible (foreground=" + fg + ")"
            return if (autoOpen) 4000L else intervalMs
        }

        statusLine = "feed watch: running, " + rows.size + " rows, top=\"" + cut(rows[0]) + "\""

        val previous = previousTop
        val top = rows[0]
        if (top == previous) {
            return intervalMs
        }

        val baseline = previous == null
        val candidates = rows.takeWhile { it != previous }.take(5)
        previousTop = top
        saveTop(app, top)

        if (baseline) {
            EventLog.line("WATCH_BASELINE rows=" + rows.size + " - history, not treated as events")
            for (r in rows) remember(app, r)
            return intervalMs
        }

        var i = candidates.size - 1
        while (i >= 0) {
            val row = candidates[i]
            if (!seen.contains(row)) {
                remember(app, row)
                emit(row, cfg)
            } else {
                EventLog.line("FEED_IGNORED_DUPLICATE \"" + cut(row) + "\"")
            }
            i--
        }
        return intervalMs
    }

    /** Proof-of-life so a day-long unattended run can be verified afterwards. */
    private fun heartbeat() {
        if (polls % 60 == 0) {
            EventLog.line(
                "WATCH_HEARTBEAT polls=" + polls + " events=" + events +
                    " remembered=" + seen.size + " " + statusLine
            )
        }
    }

    private fun emit(row: String, cfg: CopierConfig) {
        val s = FeedParser.parse(row, cfg)
        events++
        lastEvent = s.verdict + " " + s.handle + " " + s.action
        val o = JSONObject()
        o.put("ev", "FEED_NEW")
        o.put("row", s.row)
        o.put("display", s.displayName)
        o.put("handle", s.handle)
        o.put("action", s.action.name)
        o.put("asset", s.asset)
        o.put("ageLabel", s.ageLabel)
        o.put("whitelisted", s.whitelisted)
        o.put("assetAllowed", s.assetAllowed)
        o.put("ambiguous", s.ambiguous)
        o.put("verdict", s.verdict)
        o.put("openWouldBe", if (s.action == InvoAction.OPEN) cfg.leverageToUse(null) else 0)
        o.put("note", "detection only - Phase 2 never opens or places a trade")
        EventLog.json(o)
    }

    private fun cut(s: String): String = if (s.length > 60) s.substring(0, 60) + ".." else s

    private fun remember(app: Context, row: String) {
        if (!seen.contains(row)) seen.add(row)
        while (seen.size > 300) seen.removeAt(0)
        saveSeen(app)
    }

    private fun launchInvo(context: Context, pkg: String) {
        try {
            val i = context.packageManager.getLaunchIntentForPackage(pkg)
            if (i == null) {
                EventLog.line("WATCH_LAUNCH_FAIL no launcher intent for " + pkg)
                return
            }
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(i)
        } catch (t: Throwable) {
            EventLog.line("WATCH_LAUNCH_ERROR " + t)
        }
    }

    private fun sleep(ms: Long) {
        try {
            Thread.sleep(ms)
        } catch (t: InterruptedException) {
            Thread.currentThread().interrupt()
        }
    }

    /** Accessibility APIs must be touched from the main thread. */
    @Suppress("UNCHECKED_CAST")
    private fun <T> onMain(block: () -> T): T? {
        val holder = arrayOfNulls<Any>(1)
        val latch = CountDownLatch(1)
        ui.post {
            try {
                holder[0] = block()
            } catch (t: Throwable) {
                EventLog.line("WATCH_UI_ERROR " + t)
            }
            latch.countDown()
        }
        return try {
            if (latch.await(6, TimeUnit.SECONDS)) holder[0] as T? else null
        } catch (t: InterruptedException) {
            null
        }
    }

    private fun stateFile(app: Context, name: String): File {
        val dir = File(app.filesDir, "state")
        if (!dir.exists()) dir.mkdirs()
        return File(dir, name)
    }

    private fun loadTop(app: Context): String? = try {
        val f = stateFile(app, "feed-top.txt")
        val text = if (f.exists()) f.readText().trim() else ""
        if (text.isEmpty()) null else text
    } catch (t: Throwable) {
        null
    }

    private fun saveTop(app: Context, top: String) {
        try {
            stateFile(app, "feed-top.txt").writeText(top)
        } catch (t: Throwable) {
            EventLog.line("WATCH_STATE_WRITE_FAILED " + t)
        }
    }

    private fun loadSeen(app: Context): ArrayList<String> {
        val out = ArrayList<String>()
        try {
            val f = stateFile(app, "feed-seen.txt")
            if (f.exists()) {
                for (line in f.readLines()) {
                    val s = line.trim()
                    if (s.isNotEmpty()) out.add(s)
                }
            }
        } catch (t: Throwable) {
            // start fresh
        }
        return out
    }

    private fun saveSeen(app: Context) {
        try {
            stateFile(app, "feed-seen.txt").writeText(seen.joinToString("\n"))
        } catch (t: Throwable) {
            // ignore
        }
    }
}
