package com.invocopier.debug

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import com.invocopier.accessibility.InvoAccessibilityService
import com.invocopier.logging.EventLog
import org.json.JSONObject
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Development-only helper (added after the first Phase-1 field test).
 *
 * Problem it fixes: pressing "5. Dump this screen" brings OUR app to the front,
 * so the dump shows our own buttons instead of INVO's screen. With this receiver
 * the snapshot happens later, while INVO is visible:
 *
 *   adb shell am broadcast -a com.invocopier.DUMP --ei delay 4000
 *   adb shell am broadcast -a com.invocopier.DUMP --ei count 6 --ei every 6000
 *
 * The 2nd form takes 6 snapshots, 6 s apart, while you tap through INVO.
 * Read-only: it walks the node tree and writes text files. No clicks, no swipes.
 */
class UiDumpRequestReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val firstDelay = intent.getIntExtra("delay", 1500).coerceIn(0, 120000).toLong()
        val count = intent.getIntExtra("count", 1).coerceIn(1, 40)
        val every = intent.getIntExtra("every", 6000).coerceAtLeast(1000).toLong()
        val pending = goAsync()

        EventLog.line("DUMP_SCHEDULED count=" + count + " firstDelayMs=" + firstDelay + " everyMs=" + every)

        val worker = Thread {
            var i = 0
            while (i < count) {
                try {
                    Thread.sleep(if (i == 0) firstDelay else every)
                } catch (t: InterruptedException) {
                    break
                }
                i++
                dumpOnce(context, i)
            }
            try {
                pending.finish()
            } catch (t: Throwable) {
                EventLog.line("DUMP_FINISH_ERROR " + t)
            }
        }
        worker.isDaemon = true
        worker.start()
    }

    private fun dumpOnce(context: Context, seq: Int) {
        val svc = InvoAccessibilityService.instance
        if (svc == null) {
            EventLog.line("DUMP_FAILED seq=" + seq + " accessibility service is not running")
            return
        }

        // Accessibility node trees must be read on the main thread.
        val holder = arrayOfNulls<JSONObject>(1)
        val latch = CountDownLatch(1)
        Handler(Looper.getMainLooper()).post {
            try {
                holder[0] = svc.dumpActiveWindow()
            } catch (t: Throwable) {
                EventLog.line("DUMP_ERROR seq=" + seq + " " + t)
            }
            latch.countDown()
        }
        try {
            latch.await(5, TimeUnit.SECONDS)
        } catch (t: InterruptedException) {
            Thread.currentThread().interrupt()
        }

        val j = holder[0]
        if (j == null) {
            EventLog.line("DUMP_TIMEOUT seq=" + seq)
            return
        }
        j.put("ev", "UI_DUMP")
        j.put("seq", seq)
        EventLog.json(j)

        try {
            val dir = File(context.getExternalFilesDir(null) ?: context.filesDir, "dumps")
            if (!dir.exists()) dir.mkdirs()
            val out = File(dir, "ui-" + System.currentTimeMillis() + ".txt")
            out.writeText("pkg=" + j.optString("pkg") + " nodes=" + j.optInt("nodeCount") + "\n" + j.optString("tree"))
        } catch (t: Throwable) {
            EventLog.line("DUMP_WRITE_FAILED " + t)
        }
    }
}
