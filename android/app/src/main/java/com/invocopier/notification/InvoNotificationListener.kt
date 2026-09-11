package com.invocopier.notification

import android.app.Notification
import android.content.Context
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import com.invocopier.config.CopierConfig
import com.invocopier.config.KillSwitch
import com.invocopier.logging.EventLog
import com.invocopier.parser.InvoEventParser
import com.invocopier.util.BundleDump
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * METHOD 1 + METHOD 2 probe.
 *
 * METHOD 1: does INVO post a real system notification at all?
 * METHOD 2: does that notification carry a PendingIntent we could fire instead
 *           of tapping anything?
 *
 * This class has ZERO ability to trade. It observes and records.
 */
class InvoNotificationListener : NotificationListenerService() {

    private var config: CopierConfig = CopierConfig.defaults()
    private var seenFingerprints = HashSet<String>()
    private var count = 0
    private var invoCount = 0

    override fun onCreate() {
        super.onCreate()
        EventLog.init(applicationContext)
        config = CopierConfig.load(applicationContext)
        instance = this
        val o = JSONObject()
        o.put("ev", "LISTENER_CREATED")
        o.put("pid", android.os.Process.myPid())
        o.put("androidSdk", Build.VERSION.SDK_INT)
        o.put("configSource", config.source)
        o.put("dryRun", config.dryRun)
        o.put("autoTrading", config.autoTradingEnabled)
        EventLog.json(o)
        EventLog.line("CONFIG\n" + config.summary())
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        EventLog.line("LISTENER_DESTROYED")
        super.onDestroy()
    }

    override fun onListenerConnected() {
        instance = this
        val o = JSONObject()
        o.put("ev", "LISTENER_CONNECTED")
        o.put("invoPackage", config.invoPackage)
        o.put("captureAllPackages", config.captureAllPackages)
        o.put("whitelisted", JSONArray(config.traders.keys.toList()))
        EventLog.json(o)
    }

    override fun onListenerDisconnected() {
        if (instance === this) instance = null
        EventLog.line("LISTENER_DISCONNECTED (Android unbound the service; it rebinds itself)")
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        if (sbn == null) return
        try {
            handle(sbn, "POSTED")
        } catch (t: Throwable) {
            EventLog.line("ERROR in onNotificationPosted: " + t)
        }
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification?) {
        if (sbn == null) return
        try {
            handle(sbn, "REMOVED")
        } catch (t: Throwable) {
            EventLog.line("ERROR in onNotificationRemoved: " + t)
        }
    }

    private fun handle(sbn: StatusBarNotification, kind: String) {
        val pkg = sbn.packageName ?: return
        val isTarget = pkg == config.invoPackage ||
            (config.packageKeyword.isNotBlank() && pkg.lowercase(Locale.ROOT).contains(config.packageKeyword.lowercase(Locale.ROOT)))
        if (!isTarget && !config.captureAllPackages) return

        count++
        if (isTarget) invoCount++

        val o = JSONObject()
        o.put("ev", kind)
        o.put("target", isTarget)
        o.put("pkg", pkg)
        o.put("id", sbn.id)
        o.put("tag", sbn.tag ?: "")
        o.put("postTime", sbn.postTime)
        o.put("postTimeStr", hhmmss(sbn.postTime))
        o.put("receivedAt", System.currentTimeMillis())
        o.put("latencyMs", System.currentTimeMillis() - sbn.postTime)
        o.put("ongoing", sbn.isOngoing)
        o.put("clearable", sbn.isClearable)
        o.put("groupKey", sbn.groupKey ?: "")

        val n = sbn.notification
        if (n == null) {
            o.put("notification", "NULL")
            EventLog.json(o)
            return
        }

        val extras = n.extras
        val title = cs(extras, Notification.EXTRA_TITLE)
        val body = cs(extras, Notification.EXTRA_TEXT)
        val big = cs(extras, Notification.EXTRA_BIG_TEXT)
        val sub = cs(extras, Notification.EXTRA_SUB_TEXT)

        o.put("channelId", n.channelId ?: "")
        o.put("flags", n.flags)
        o.put("visibility", n.visibility)
        o.put("priority", n.priority)
        o.put("number", n.number)
        o.put("whenField", n.`when`)
        o.put("ticker", n.tickerText?.toString() ?: "")
        o.put("title", title)
        o.put("text", body)
        o.put("bigText", big)
        o.put("subText", sub)

        // ---- METHOD 2 probe: can a PendingIntent take us straight to the trade? ----
        o.put("hasContentIntent", n.contentIntent != null)
        o.put("hasDeleteIntent", n.deleteIntent != null)
        o.put("hasFullScreenIntent", n.fullScreenIntent != null)
        n.contentIntent?.let { pi ->
            val p = JSONObject()
            p.put("isActivity", try { pi.isActivity } catch (t: Throwable) { false })
            p.put("isBroadcast", try { pi.isBroadcast } catch (t: Throwable) { false })
            p.put("isService", try { pi.isService } catch (t: Throwable) { false })
            // Unwrapping is only possible when the creator allowed fill-in; a failure here is normal.
            p.put("unwrap", try {
                val i = pi.activity
                (i.component?.flattenToShortString() ?: "") + " data=" + (i.dataString ?: "") + " action=" + (i.action ?: "")
            } catch (t: Throwable) {
                "UNWRITABLE(" + t.javaClass.simpleName + ")"
            })
            o.put("contentIntent", p)
        }

        val acts = n.actions
        if (acts != null && acts.isNotEmpty()) {
            val arr = JSONArray()
            for (a in acts) {
                val aj = JSONObject()
                aj.put("title", a.title?.toString() ?: "")
                aj.put("hasIntent", a.intent != null)
                aj.put("action", a.intent?.action ?: "")
                arr.put(aj)
            }
            o.put("actions", arr)
        }

        o.put("extras", BundleDump.toJson(extras))

        if (isTarget) {
            val text = listOf(title, body, big, sub).filter { it.isNotBlank() }.joinToString(" | ")
            val parsed = InvoEventParser.parse(text, pkg, sbn.id, sbn.postTime)
            o.put("parse", parsed.toJson())
            o.put("whitelisted", config.isTraderWhitelisted(parsed.handle))
            o.put("allocationPercent", config.allocationFor(parsed.handle))
            o.put("leverageWouldBe", config.leverageToUse(parsed.leverageX))
            o.put("assetAllowed", config.assetAllowed(parsed.asset))
            o.put("deviceKillSwitch", KillSwitch.isEngaged(this))
            o.put("verdict", KillSwitch.verdict(this, config))
            o.put("wouldExecute", config.executionAllowed() && config.isTraderWhitelisted(parsed.handle) && !parsed.ambiguous)
            if (seenFingerprints.size > 4000) seenFingerprints.clear()
            if (!seenFingerprints.add(parsed.fingerprintExact)) {
                o.put("duplicateExact", true)
            }
            if (kind == "POSTED") lastTarget = sbn
        }

        EventLog.json(o)
    }

    private fun cs(b: Bundle?, key: String): String =
        try {
            b?.getCharSequence(key)?.toString() ?: ""
        } catch (t: Throwable) {
            ""
        }

    private fun hhmmss(ms: Long): String = try {
        SimpleDateFormat("HH:mm:ss", Locale.US).format(Date(ms))
    } catch (t: Throwable) {
        ""
    }

    companion object {

        @Volatile
        private var instance: InvoNotificationListener? = null

        /** Held in RAM only, for the "replay contentIntent" experiment. */
        @Volatile
        var lastTarget: StatusBarNotification? = null

        fun isReady(): Boolean = instance != null

        fun enabledInSettings(context: Context): Boolean {
            val flat = try {
                Settings.Secure.getString(
                    context.contentResolver, "enabled_notification_listeners"
                )
            } catch (t: Throwable) {
                null
            } ?: return false
            return flat.contains(context.packageName)
        }

        fun adbEnableCommand(context: Context): String =
            "adb shell cmd notification allow_listener " +
                context.packageName + "/" + InvoNotificationListener::class.java.name

        /** Entry point used by the UI for the METHOD 2 experiment. */
        fun replayLast(): String {
            val inst = instance ?: return "LISTENER_NOT_RUNNING (grant notification access first)"
            return inst.replayLastContentIntent()
        }
    }

    /**
     * METHOD 2 experiment run from the UI. Fires the stored PendingIntent of the
     * last INVO notification and reports whether INVO opened the right trade.
     * Read-only with respect to money: it cannot submit an order.
     */
    fun replayLastContentIntent(): String {
        val sbn = lastTarget ?: return "NO_INVO_NOTIFICATION_CAPTURED_YET"
        val pi = sbn.notification?.contentIntent ?: return "that notification has no contentIntent"
        return try {
            pi.send()
            "SENT_OK - look at the phone: did INVO open exactly that trader's trade page?"
        } catch (t: Throwable) {
            "SEND_FAILED " + t.javaClass.simpleName + ": " + t.message
        }
    }
}
