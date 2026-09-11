package com.invocopier.diagnostics

import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import com.invocopier.accessibility.InvoAccessibilityService
import com.invocopier.config.CopierConfig
import com.invocopier.config.KillSwitch
import com.invocopier.logging.EventLog
import com.invocopier.parser.ScreenParser
import com.invocopier.parser.TradePage
import com.invocopier.watch.FeedParser
import com.invocopier.watch.FeedSignal
import org.json.JSONObject
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * The whole path, rehearsed on a real trade:
 *
 *   newest feed row from an approved trader -> open that trade -> read
 *   asset / direction / leverage / entry -> locate the Mimic control -> press it
 *   if allowed -> read the amount page -> stop there -> go back
 *
 * Pressing a button that opens a page is not an order: nothing can be placed from
 * here, because this class contains no swipe and no gesture, and the amount page
 * in INVO only fills when the user swipes it up by hand.
 *
 * Execution is additionally gated by config DRY_RUN + AUTOTRADING + the on-screen
 * STOP, and this build never uses that gate to press anything.
 */
object Rehearsal {

    const val SECTION = "DRY-RUN OF NEWEST TRADE"

    private val busy = AtomicBoolean(false)
    private val ui = Handler(Looper.getMainLooper())

    @Volatile
    var lastVerdict = "not run yet"
        private set

    fun start(context: Context) {
        val app = context.applicationContext
        if (!busy.compareAndSet(false, true)) {
            EventLog.line("REHEARSAL_ALREADY_RUNNING")
            return
        }
        val worker = Thread {
            try {
                run(app)
            } catch (t: Throwable) {
                lastVerdict = "CRASHED: " + t
                Report.set(SECTION, lastVerdict + "\n\nTell me this line; nothing was pressed.")
                EventLog.line("REHEARSAL_ERROR " + t)
            } finally {
                busy.set(false)
            }
        }
        worker.isDaemon = true
        worker.start()
    }

    private fun run(app: Context) {
        val out = StringBuilder()
        out.append("Rehearsal: read a live trade and prove the numbers are gettable.\n")
        out.append("Nothing here can swipe, so no order can be created or closed.\n\n")
        EventLog.line("REHEARSAL_START")

        if (InvoAccessibilityService.instance == null) {
            out.append("BLOCKED: the screen reader service is off, so INVO's screen cannot be read.\n")
            out.append("Fix: open our app, tap 4 (Grant screen access), switch INVO Copier on, then press 12 again.")
            finish(out)
            return
        }

        val cfg = CopierConfig.load(app)

        // ---- 1. make sure INVO is the visible app ----
        var pkg = onMain<String> { InvoAccessibilityService.instance?.foregroundPackage() } ?: ""
        if (pkg != cfg.invoPackage) {
            out.append("step 1: INVO is not in front (").append(if (pkg.isBlank()) "unknown" else pkg)
                .append(") - opening it\n")
            openInvo(app, cfg.invoPackage)
            sleep(4000)
            pkg = onMain<String> { InvoAccessibilityService.instance?.foregroundPackage() } ?: ""
            out.append("         now in front: ").append(if (pkg.isBlank()) "nothing" else pkg).append('\n')
        } else {
            out.append("step 1: INVO already in front\n")
        }

        // ---- 2. get to the feed ----
        var rows = readRows()
        if (rows.isEmpty()) {
            out.append("step 2: no feed rows on screen - tapping the Notifications tab\n")
            val tapped = onMain<Boolean> {
                InvoAccessibilityService.instance?.clickByTextOrDesc("Notifications Tab")
            } ?: false
            sleep(2500)
            rows = readRows()
            if (rows.isEmpty()) {
                out.append("         STILL EMPTY (tab tap ").append(if (tapped) "was accepted" else "failed")
                    .append("). Open INVO's Notifications page yourself, then press 12 again.\n")
                out.append("         What the screen does show right now:\n")
                appendScreenPeek(out)
                finish(out)
                return
            }
        }
        out.append("step 2: feed readable, ").append(rows.size).append(" rows\n")

        // ---- 3. newest row from a trader you approved ----
        var chosen: FeedSignal? = null
        val skipped = ArrayList<String>()
        for (r in rows) {
            val s = FeedParser.parse(r, cfg)
            if (s.whitelisted) {
                chosen = s
                break
            }
            if (skipped.size < 3) skipped.add("not yours (" + tiny(r) + ")")
        }
        for (x in skipped) out.append("         skipped: ").append(x).append('\n')
        val sig = chosen
        if (sig == null) {
            out.append("\nstep 3: NO ROW FROM YOUR APPROVED TRADERS (")
            out.append(cfg.traders.keys.joinToString(", ").ifEmpty { "none configured" })
            out.append(") in the feed right now.\n")
            out.append("        That is not a fault - nothing will trade until a real signal exists.\n")
            out.append("        Press 12 again after one of them posts, or press 11 and send me the capture.\n")
            finish(out)
            return
        }
        out.append("step 3: chosen \"").append(tiny(sig.row)).append("\"  handle=").append(sig.handle)
            .append(" action=").append(sig.action).append(" verdict=").append(sig.verdict).append('\n')

        // ---- 4. open it ----
        val key = if (sig.row.length > 55) sig.row.substring(0, 55) else sig.row
        val clicked = onMain<Boolean> {
            InvoAccessibilityService.instance?.clickByDescContains(key)
        } ?: false
        if (!clicked) {
            out.append("step 4: COULD NOT OPEN - that row did not accept a tap. Tell me this line.\n")
            finish(out)
            return
        }
        out.append("step 4: opened, reading the page\n")
        sleep(2800)

        val snap = onMain<InvoAccessibilityService.ScreenSnapshot> {
            InvoAccessibilityService.instance?.readScreen()
        }
        if (snap == null || snap.nodes.isEmpty()) {
            out.append("step 5: the page gave back no readable nodes. Screen reader was blocked mid-way.\n")
            goBack()
            finish(out)
            return
        }
        val page = ScreenParser.parse(snap, sig.row)
        out.append("step 5: page pkg=").append(snap.pkg).append(" nodes=").append(snap.nodeCount).append('\n')
        out.append(page.summary()).append('\n')

        // ---- 5. verdict + evidence ----
        val missing = page.missing
        out.append("step 6: verdict - ")
        when {
            page.hasBasics() -> out.append(
                "ALL NUMBERS READABLE and the Mimic control located. The next build can size the " +
                    "order and rehearse the press up to the swipe."
            )
            missing.contains("mimic button") -> out.append(
                "the Mimic control is not on this screen (it may sit lower down, or INVO opened a " +
                    "summary instead of the trade). Numbers found so far are above; the evidence below tells me what to select on."
            )
            else -> out.append("MISSING: ").append(missing.joinToString(", "))
                .append(" - not guessed. The evidence below is what I need to fix the wording.")
        }
        out.append("\n\nwhat the page actually says:\n")
        for (l in page.readable) out.append("   ").append(l).append('\n')

        logJson(sig, page, snap.pkg, snap.nodeCount)

        // ---- 6. leave the way we came ----
        out.append("\nstep 7: ").append(if (goBack()) "went back to the feed" else "back key refused, stay aware of where INVO is")
            .append('\n')
        out.append("safety: execution gate = ").append(KillSwitch.verdict(app, cfg))
            .append(", and this build has no swipe code at all.")
        finish(out)
    }

    private fun readRows(): List<String> =
        onMain<List<String>> { InvoAccessibilityService.instance?.collectFeedRows() } ?: emptyList()

    private fun appendScreenPeek(out: StringBuilder) {
        val snap = onMain<InvoAccessibilityService.ScreenSnapshot> {
            InvoAccessibilityService.instance?.readScreen()
        } ?: return
        out.append("   pkg=").append(snap.pkg).append('\n')
        for (l in ScreenParser.readableLines(snap, 8)) out.append("   ").append(l).append('\n')
    }

    private fun goBack(): Boolean {
        val ok = onMain<Boolean> { InvoAccessibilityService.instance?.goBack() } ?: false
        sleep(1200)
        return ok
    }

    private fun openInvo(app: Context, pkg: String) {
        val i: Intent? = app.packageManager.getLaunchIntentForPackage(pkg)
        if (i == null) {
            EventLog.line("REHEARSAL_NO_INVO package=" + pkg)
            return
        }
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        try {
            app.startActivity(i)
        } catch (t: Throwable) {
            EventLog.line("REHEARSAL_LAUNCH_FAILED " + t)
        }
    }

    private fun logJson(sig: FeedSignal, page: TradePage, pkg: String, nodes: Int) {
        val o = JSONObject()
        o.put("ev", "REHEARSAL_READ")
        o.put("pkg", pkg)
        o.put("nodes", nodes)
        o.put("row", sig.row)
        o.put("handle", sig.handle)
        o.put("action", sig.action.name)
        o.put("asset", page.asset ?: "")
        o.put("direction", page.direction ?: "")
        o.put("leverage", page.leverage ?: -1)
        o.put("entry", page.entry ?: "")
        o.put("mimic", page.mimicLabel ?: "")
        o.put("mimicClickable", page.mimicClickable)
        o.put("slider", page.sliderLine ?: "")
        o.put("complete", page.hasBasics())
        EventLog.json(o)
    }

    private fun finish(out: StringBuilder) {
        val text = out.toString()
        lastVerdict = if (text.contains("verdict - ")) {
            text.substringAfter("verdict - ").substringBefore("\n")
        } else {
            text.substringBefore("\n")
        }
        Report.set(SECTION, text)
        EventLog.line("REHEARSAL_RESULT\n" + text)
    }

    private fun tiny(s: String): String {
        val f = s.replace('\n', ' ').trim()
        return if (f.length > 60) f.substring(0, 60) + ".." else f
    }

    private fun sleep(ms: Long) {
        try {
            Thread.sleep(ms)
        } catch (t: InterruptedException) {
            Thread.currentThread().interrupt()
        }
    }

    /** Node reads must happen on the main thread; the worker waits for the result. */
    private fun <T> onMain(block: () -> T): T? {
        if (InvoAccessibilityService.instance == null) return null
        val holder = arrayOfNulls<Any>(1)
        val latch = CountDownLatch(1)
        ui.post {
            try {
                holder[0] = block()
            } catch (t: Throwable) {
                EventLog.line("REHEARSAL_MAIN_ERROR " + t)
            }
            latch.countDown()
        }
        try {
            latch.await(8, TimeUnit.SECONDS)
        } catch (t: InterruptedException) {
            Thread.currentThread().interrupt()
        }
        @Suppress("UNCHECKED_CAST")
        return holder[0] as T?
    }
}
