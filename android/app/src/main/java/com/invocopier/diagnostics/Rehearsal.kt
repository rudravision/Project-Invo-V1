package com.invocopier.diagnostics

import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import com.invocopier.accessibility.InvoAccessibilityService
import com.invocopier.config.CopierConfig
import com.invocopier.config.KillSwitch
import com.invocopier.logging.EventLog
import com.invocopier.parser.MovesReader
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

        // ---- 2. get to the event feed ----
        // Always tap the Notifications tab first: INVO opens on its trader
        // leaderboard, where clickable @handles also appear (as trader cards, not
        // events). Tapping an already-selected tab is a no-op, so this is safe.
        var rows = goToFeed(cfg, out)
        out.append("step 2: ").append(rows.size).append(" clickable rows after navigating\n")
        appendPageHint(out)
        var rowIdx = 0
        for (r in rows) {
            rowIdx++
            if (rowIdx > 6) break
            out.append("         row ").append(rowIdx).append(": ").append(tiny(r))
                .append(if (isEventRow(r)) "" else "   <- not an event, will not be opened").append('\n')
        }
        val events = ArrayList<String>()
        for (r in rows) if (isEventRow(r)) events.add(r)
        if (events.isEmpty()) {
            // INVO's trader cards carry every number we need, and each open card has
            // its own Mimic Trade button, so a trader page is a better target than the
            // notification feed when no fresh event happens to be on screen.
            val cardRow = firstApprovedCard(rows, cfg)
            if (cardRow == null) {
                out.append("\nstep 3: REFUSED - this page has neither a trade event nor a trader from ")
                    .append("your list (")
                    .append(cfg.traders.keys.joinToString(", ").ifEmpty { "none configured" })
                    .append("). Tap 11 to photograph the pages, or open the Notifications page and press 12.\n")
                finish(out)
                return
            }
            profilePath(app, cfg, cardRow, out)
            return
        }

        // ---- 3. newest event from a trader you approved ----
        var chosen: FeedSignal? = null
        val skipped = ArrayList<String>()
        for (r in events) {
            val sig2 = FeedParser.parse(r, cfg)
            if (sig2.whitelisted) {
                chosen = sig2
                break
            }
            if (skipped.size < 3) skipped.add("not yours (" + tiny(r) + ")")
        }
        for (x in skipped) out.append("         skipped: ").append(x).append('\n')
        val approved = chosen != null
        val sig: FeedSignal = chosen ?: FeedParser.parse(events[0], cfg)
        if (approved) {
            out.append("step 3: chosen \"").append(tiny(sig.row)).append("\"  handle=").append(sig.handle)
                .append(" action=").append(sig.action).append(" verdict=").append(sig.verdict).append('\n')
        } else {
            out.append("\nstep 3: your approved traders (")
                .append(cfg.traders.keys.joinToString(", ").ifEmpty { "none configured" })
                .append(") have nothing in this feed right now, so this run is MEASUREMENT ONLY.\n")
            out.append("        Opening the newest event (")
                .append(sig.handle.ifEmpty { "no handle found" })
                .append(") purely to learn how a trade page is laid out.\n")
            out.append("        That trader is NOT on your list, so nothing could ever trade from it.\n")
        }

        // ---- 4. open it ----
        val key = if (sig.row.length > 55) sig.row.substring(0, 55) else sig.row
        val clicked = onMain<Boolean> {
            InvoAccessibilityService.instance?.clickByDescSmart(key)
        } ?: false
        if (!clicked) {
            out.append("step 4: that row would not take a tap - reading the trader's own page instead\n")
            openInvo(app, cfg.invoPackage)
            sleep(3500)
            val listRows = readRows()
            val cardRow = firstApprovedCard(listRows, cfg)
            if (cardRow == null) {
                out.append("        REFUSED - ").append(sig.handle)
                    .append(" was not on INVO's opening page either (rows seen: ").append(listRows.size)
                    .append("). Tell me this line.\n")
                finish(out)
                return
            }
            profilePath(app, cfg, cardRow, out)
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
        var page = ScreenParser.parse(snap, sig.row)
        out.append("step 5: page pkg=").append(snap.pkg).append(" nodes=").append(snap.nodeCount).append('\n')
        if (!page.hasBasics()) {
            val scrolled = onMain<Boolean> { InvoAccessibilityService.instance?.scrollForward() } ?: false
            sleep(1200)
            val again = onMain<InvoAccessibilityService.ScreenSnapshot> {
                InvoAccessibilityService.instance?.readScreen()
            }
            if (scrolled && again != null && again.nodes.isNotEmpty()) {
                val p2 = ScreenParser.parse(again, sig.row)
                val before = page.missing.size
                if (p2.missing.size < before) {
                    page = p2
                    out.append("         scrolled once and found more: missing went from ").append(before)
                        .append(" field(s) to ").append(page.missing.size).append('\n')
                } else {
                    out.append("         scrolled once; nothing new was readable\n")
                }
            } else {
                out.append("         page does not scroll, so what we see is all there is\n")
            }
        }
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

        logJson(sig, page, snap.pkg, snap.nodeCount, approved)

        // ---- 6. leave the way we came ----
        out.append("\nstep 7: ").append(if (goBack()) "went back to the feed" else "back key refused, stay aware of where INVO is")
            .append('\n')
        out.append("safety: execution gate = ").append(KillSwitch.verdict(app, cfg))
            .append(", and this build has no swipe code at all.")
        if (!approved) {
            out.append("\nnote: MEASUREMENT ONLY - ").append(sig.handle.ifEmpty { "unknown trader" })
                .append(" is not on your approved list, so this row can never become an order.")
        }
        finish(out)
    }

    /** A real event row names an action, or uses the middle dot from the captured format. */
    private fun isEventRow(row: String): Boolean {
        if (row.contains('\u00B7')) return true
        val low = row.lowercase()
        return low.contains("opened") || low.contains("updated") ||
            low.contains("closed") || low.contains("new trade") || low.contains("mimic")
    }

    private fun appendPageHint(out: StringBuilder) {
        val snap = onMain<InvoAccessibilityService.ScreenSnapshot> {
            InvoAccessibilityService.instance?.readScreen()
        } ?: return
        out.append("         page reads as: ").append(ScreenParser.pageHint(snap)).append('\n')
    }

    /**
     * Reach INVO's event feed, retrying: right after launch the bottom navigation
     * is often not drawn yet, and a single blind tap is not enough.
     */
    private fun goToFeed(cfg: CopierConfig, out: StringBuilder): List<String> {
        // cfg is kept here so navigation and feed reading stay in one place for Phase 4
        var best: List<String> = emptyList()
        var attempt = 0
        while (attempt < 4) {
            attempt++
            val tapped = onMain<Boolean> {
                val svc = InvoAccessibilityService.instance ?: return@onMain false
                svc.clickByTextOrDesc("Notifications Tab") || svc.clickByTextOrDesc("Notification")
            } ?: false
            sleep(1500)
            val rows = readRows()
            if (rows.any { isEventRow(it) }) {
                out.append("         event feed reached on attempt ").append(attempt)
                    .append(if (tapped) " (nav tap worked)" else " (already there)").append('\n')
                return rows
            }
            if (rows.size > best.size) best = rows
            out.append("         attempt ").append(attempt).append(": ").append(rows.size)
                .append(" rows, no events (nav tap ").append(if (tapped) "accepted" else "nothing found").append(")\n")
            sleep(1200)
        }
        return best
    }

    private fun handleOf(row: String): String =
        Regex("@([A-Za-z0-9_.]{2,32})").find(row)?.value?.lowercase() ?: ""

    /** A clickable trader card on INVO's list, for a trader you approved. */
    private fun firstApprovedCard(rows: List<String>, cfg: CopierConfig): String? {
        for (r in rows) {
            if (isEventRow(r)) continue
            val h = handleOf(r)
            if (h.isNotEmpty() && cfg.isTraderWhitelisted(h)) return r
        }
        return null
    }

    /**
     * Open an approved trader's page and read their trade cards. Nothing is pressed:
     * the Mimic button is located and reported, never tapped, in this build.
     */
    private fun profilePath(app: Context, cfg: CopierConfig, cardRow: String, out: StringBuilder) {
        out.append("\nstep 3: no fresh event on this page, but ").append(handleOf(cardRow))
            .append(" is on your approved list - opening their trades instead.\n")
        val key = if (cardRow.length > 55) cardRow.substring(0, 55) else cardRow
        val tapped = onMain<Boolean> {
            InvoAccessibilityService.instance?.clickByDescSmart(key)
        } ?: false
        if (!tapped) {
            out.append("step 4: REFUSED - that trader's card did not accept a tap.\n")
            finish(out)
            return
        }
        sleep(2600)
        val snap = onMain<InvoAccessibilityService.ScreenSnapshot> {
            InvoAccessibilityService.instance?.readScreen()
        }
        if (snap == null || snap.nodes.isEmpty()) {
            out.append("step 4: REFUSED - their page gave back no readable nodes.\n")
            goBack()
            finish(out)
            return
        }
        val cards = MovesReader.read(snap)
        out.append("step 4: their page read (pkg=").append(snap.pkg).append(", nodes=").append(snap.nodeCount)
            .append(") - ").append(cards.size).append(" trade card(s) matched\n")
        var openCount = 0
        var idx = 0
        for (c in cards) {
            idx++
            if (idx > 8) break
            if (c.open) openCount++
            out.append("   card ").append(idx).append(": ").append(c.oneLine()).append('\n')
        }
        val target = cards.firstOrNull { it.open && it.mimicFound }
        out.append("step 5: verdict - ")
        when {
            cards.isEmpty() -> out.append(
                "no card matched my pattern here. Everything readable is listed below so I can fix the wording."
            )
            openCount == 0 -> out.append(
                "this trader has no open trade on screen right now, so there is nothing to copy. Not a fault."
            )
            target == null -> out.append(
                "an open trade was read but its Mimic button was not located on this screen - it may need one scroll."
            )
            else -> out.append("READY: ")
                .append(target.asset).append(" ").append(target.direction)
                .append(" at ").append(target.leverage).append("x with a Mimic button in reach. ")
                .append("Next build can size the order and stop before the swipe.")
        }
        if (target != null) {
            out.append("\n   target card text: ").append(tiny(target.raw)).append('\n')
            out.append("   ").append(target.mimicLine).append('\n')
            val o = JSONObject()
            o.put("ev", "MOVE_READY")
            o.put("trader", handleOf(cardRow))
            o.put("asset", target.asset)
            o.put("direction", target.direction)
            o.put("leverage", target.leverage)
            o.put("entry", target.entry)
            o.put("pnl", target.pnl)
            o.put("mimic", target.mimicLine)
            EventLog.json(o)
        } else if (cards.isNotEmpty()) {
            val o = JSONObject()
            o.put("ev", "MOVE_SCAN")
            o.put("trader", handleOf(cardRow))
            o.put("cards", cards.size)
            o.put("open", openCount)
            o.put("mimicLocated", false)
            EventLog.json(o)
        }
        if (target == null) {
            out.append("\nwhat the page says:\n")
            for (l in ScreenParser.readableLines(snap, 20)) out.append("   ").append(l).append('\n')
        }
        out.append("\nstep 6: ").append(if (goBack()) "went back" else "back key refused")
            .append(". Nothing was pressed: this build has no code that taps a Mimic button.\n")
        out.append("safety: execution gate = ").append(KillSwitch.verdict(app, cfg))
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

    private fun logJson(sig: FeedSignal, page: TradePage, pkg: String, nodes: Int, approved: Boolean) {
        val o = JSONObject()
        o.put("ev", "REHEARSAL_READ")
        o.put("approvedTrader", approved)
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
    private fun <T> onMain(block: () -> T?): T? {
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
