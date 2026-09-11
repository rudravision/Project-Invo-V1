package com.invocopier.diagnostics

import android.content.Context
import android.os.Handler
import android.os.Looper
import com.invocopier.accessibility.InvoAccessibilityService
import com.invocopier.config.CopierConfig
import com.invocopier.logging.EventLog
import com.invocopier.parser.ScreenParser
import org.json.JSONObject
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Guided screen capture, entirely by tapping buttons on the phone.
 *
 * Press it, then walk through INVO. Every few seconds the current screen is
 * photographed as readable text and the useful lines go into the result, which
 * "8. COPY RESULT" puts on the clipboard. No PC, no adb, no log reading.
 *
 * Read-only: it never clicks, scrolls or presses anything inside INVO.
 */
object CaptureTool {

    const val SECTION = "SCREEN CAPTURE"

    private val busy = AtomicBoolean(false)
    private val ui = Handler(Looper.getMainLooper())

    fun start(context: Context, pages: Int, gapSeconds: Int) {
        val app = context.applicationContext
        if (InvoAccessibilityService.instance == null) {
            Report.set(
                SECTION,
                "REFUSED - the screen reader service is not running.\n" +
                    "Turn the INVO Copier switch on in Android's accessibility settings, then press 11 again."
            )
            EventLog.line("CAPTURE_REFUSED reason=no-accessibility-service")
            return
        }
        if (!busy.compareAndSet(false, true)) {
            EventLog.line("CAPTURE_ALREADY_RUNNING")
            return
        }
        val n = pages.coerceIn(1, 8)
        val gap = gapSeconds.coerceIn(3, 30)
        val worker = Thread {
            try {
                run(app, n, gap)
            } catch (t: Throwable) {
                Report.set(SECTION, "CAPTURE CRASHED: " + t)
                EventLog.line("CAPTURE_ERROR " + t)
            } finally {
                busy.set(false)
            }
        }
        worker.isDaemon = true
        worker.start()
    }

    private fun run(app: Context, pages: Int, gap: Int) {
        val cfg = CopierConfig.load(app)
        val dir = File(app.getExternalFilesDir(null) ?: app.filesDir, "dumps")
        if (!dir.exists()) dir.mkdirs()

        val out = StringBuilder()
        out.append("Go to INVO now. One screen is photographed every ").append(gap)
            .append(" seconds, ").append(pages).append(" times.\n")
        out.append("Walk through, pausing on each: 1) the Notifications feed  2) a trader's trade page")
        .append("  3) the Mimic Trade page (do not swipe)  4) your positions  5) the close page.\n\n")
        EventLog.line("CAPTURE_START pages=" + pages + " gapS=" + gap)

        var got = 0
        var invoGot = 0
        var i = 0
        while (i < pages) {
            try {
                Thread.sleep(if (i == 0) 3000L else gap * 1000L)
            } catch (t: InterruptedException) {
                break
            }
            i++
            val snap = onMain<InvoAccessibilityService.ScreenSnapshot> {
                InvoAccessibilityService.instance?.readScreen()
            }
            if (snap == null || snap.nodes.isEmpty()) {
                out.append("screen ").append(i).append(" : NOTHING READ (screen off, or the app blocks reading)\n\n")
                EventLog.json(JSONObject().put("ev", "CAPTURE_EMPTY").put("seq", i))
                continue
            }
            got++
            val target = snap.pkg == cfg.invoPackage || snap.pkg.contains("involio")
            if (target) invoGot++
            val page = ScreenParser.parse(snap, "")
            out.append("screen ").append(i).append("  pkg=").append(snap.pkg)
            if (!target) out.append("   <-- not INVO, be quicker switching back")
            out.append("  nodes=").append(snap.nodeCount).append('\n')
            out.append("   reads as: ").append(ScreenParser.pageHint(snap)).append('\n')
            for (l in page.readable) out.append("      ").append(l).append('\n')
            if (page.mimicLabel != null) out.append("   >> control named Mimic: \"").append(page.mimicLabel).append("\"\n")
            if (page.sliderLine != null) out.append("   >> slider: ").append(page.sliderLine).append('\n')
            out.append('\n')

            val tree = onMain<String> {
                InvoAccessibilityService.instance?.dumpActiveWindow()?.optString("tree")
            } ?: ""
            try {
                File(dir, "snap-" + System.currentTimeMillis() + ".txt")
                    .writeText("pkg=" + snap.pkg + " nodes=" + snap.nodeCount + "\n" + tree)
            } catch (t: Throwable) {
                // disk problem must not stop the capture
            }
            EventLog.json(
                JSONObject()
                    .put("ev", "CAPTURE_PAGE")
                    .put("seq", i)
                    .put("pkg", snap.pkg)
                    .put("nodes", snap.nodeCount)
                    .put("invo", target)
                    .put("hint", ScreenParser.pageHint(snap))
            )
        }

        out.append("result: ").append(got).append(" of ").append(pages)
            .append(" screens photographed, ").append(invoGot).append(" of them INVO.\n")
        if (invoGot == 0) {
            out.append("VERDICT: FAILED - INVO was never in front while it photographed. Press 11 and move to INVO immediately.\n")
        } else if (got == 0) {
            out.append("VERDICT: FAILED - nothing was readable at all. Tell me and I will look at the screen reader setting.\n")
        } else {
            out.append("VERDICT: OK - send me all of the above with 8. COPY RESULT. That is the whole capture.\n")
        }
        Report.set(SECTION, out.toString())
        EventLog.line("CAPTURE_DONE pages=" + got + " invo=" + invoGot)
    }

    /** Accessibility nodes must be read on the main thread. */
    private fun <T> onMain(block: () -> T): T? {
        if (InvoAccessibilityService.instance == null) return null
        val holder = arrayOfNulls<Any>(1)
        val latch = CountDownLatch(1)
        ui.post {
            try {
                holder[0] = block()
            } catch (t: Throwable) {
                EventLog.line("CAPTURE_MAIN_ERROR " + t)
            }
            latch.countDown()
        }
        try {
            latch.await(7, TimeUnit.SECONDS)
        } catch (t: InterruptedException) {
            Thread.currentThread().interrupt()
        }
        @Suppress("UNCHECKED_CAST")
        return holder[0] as T?
    }
}
