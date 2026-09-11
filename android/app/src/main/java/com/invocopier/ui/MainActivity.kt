package com.invocopier.ui

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.widget.Button
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.invocopier.R
import com.invocopier.accessibility.InvoAccessibilityService
import com.invocopier.config.CopierConfig
import com.invocopier.diagnostics.Phase1SelfTest
import com.invocopier.config.KillSwitch
import com.invocopier.logging.EventLog
import com.invocopier.notification.InvoNotificationListener
import com.invocopier.watch.FeedWatcher

class MainActivity : AppCompatActivity() {

    private lateinit var statusText: TextView
    private lateinit var logText: TextView
    private lateinit var logScroll: ScrollView
    private lateinit var killButton: Button

    private val handler = Handler(Looper.getMainLooper())
    private var config: CopierConfig = CopierConfig.defaults()
    private var lastLogLength = -1

    private val ticker = object : Runnable {
        override fun run() {
            render()
            handler.postDelayed(this, 800)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        statusText = findViewById(R.id.statusText)
        logText = findViewById(R.id.logText)
        logScroll = findViewById(R.id.logScroll)
        killButton = findViewById(R.id.killButton)

        EventLog.init(this)
        config = CopierConfig.load(this)
        EventLog.line("UI_OPENED\n" + config.summary())

        findViewById<Button>(R.id.btnGrantListener).setOnClickListener {
            openSettings(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
        }
        findViewById<Button>(R.id.btnCopyAdb).setOnClickListener {
            copy(InvoNotificationListener.adbEnableCommand(this), "adb enable command")
        }
        findViewById<Button>(R.id.btnSelfTest).setOnClickListener { selfTest() }
        findViewById<Button>(R.id.btnOpenInvo).setOnClickListener { openInvo() }
        findViewById<Button>(R.id.btnGrantA11y).setOnClickListener {
            openSettings(Settings.ACTION_ACCESSIBILITY_SETTINGS)
        }
        findViewById<Button>(R.id.btnDump).setOnClickListener { dumpUi() }
        findViewById<Button>(R.id.btnReplay).setOnClickListener {
            val r = InvoNotificationListener.replayLast()
            EventLog.line("METHOD2_REPLAY $r")
            Toast.makeText(this, r, Toast.LENGTH_LONG).show()
            render()
        }
        findViewById<Button>(R.id.btnFullTest).setOnClickListener {
            Phase1SelfTest.start(applicationContext)
            Toast.makeText(this, "Go to INVO now and tap through it for 35 seconds.", Toast.LENGTH_LONG).show()
            render()
        }
        findViewById<Button>(R.id.btnCopyResult).setOnClickListener {
            copy(Phase1SelfTest.summary + "\n\n" + FeedWatcher.report(this), "Phase 1 + 2 result")
            logText.text = Phase1SelfTest.summary
        }
        findViewById<Button>(R.id.btnWatch).setOnClickListener {
            if (FeedWatcher.running) {
                FeedWatcher.stop()
                toast("Feed watch stopped")
            } else {
                FeedWatcher.start(applicationContext, 5, false)
                toast("Watching INVO feed - keep INVO open on its Notifications page")
            }
            render()
        }
        findViewById<Button>(R.id.btnWatchOpen).setOnClickListener {
            if (FeedWatcher.running) FeedWatcher.stop()
            FeedWatcher.start(applicationContext, 5, true)
            toast("Watching and re-opening INVO when needed")
            render()
        }
        findViewById<Button>(R.id.btnCopyLogs).setOnClickListener {
            copy(EventLog.dumpAll(), "all logs")
        }
        findViewById<Button>(R.id.btnCopyLogPath).setOnClickListener {
            copy(EventLog.logDir(), "log folder path")
        }
        killButton.setOnClickListener {
            val engaged = KillSwitch.toggle(this)
            EventLog.line(if (engaged) "KILL_SWITCH_ENGAGED all execution blocked" else "KILL_SWITCH_RELEASED")
            render()
        }

        when (intent?.getStringExtra("action")) {
            "selftest" -> handler.postDelayed({ selfTest() }, 600)
            "dump" -> handler.postDelayed({ dumpUi() }, 600)
        }
    }

    override fun onResume() {
        super.onResume()
        handler.post(ticker)
    }

    override fun onPause() {
        handler.removeCallbacks(ticker)
        super.onPause()
    }

    private fun render() {
        val sb = StringBuilder()
        val invo = try {
            packageManager.getPackageInfo(config.invoPackage, 0)
        } catch (t: Throwable) {
            null
        }
        sb.append("app build    : ").append(APP_BUILD).append('\n')
        sb.append("Android ").append(Build.VERSION.RELEASE).append(" (sdk ").append(Build.VERSION.SDK_INT).append(")\n")
        sb.append("INVO package   : ")
        sb.append(if (invo == null) "NOT FOUND -> fix invo_package in invo_config.json" else "installed, v" + (invo.versionName ?: "?")).append('\n')
        sb.append("Notif access   : ")
        sb.append(if (InvoNotificationListener.enabledInSettings(this)) "GRANTED" else "NOT GRANTED  <-- do STEP 4").append('\n')
        sb.append("Listener alive : ").append(if (InvoNotificationListener.isReady()) "YES" else "NO").append('\n')
        sb.append("A11y service   : ").append(if (InvoAccessibilityService.isReady()) "ENABLED" else "not enabled (only needed for UI dumps)").append('\n')
        sb.append("Mode           : ").append(if (config.dryRun) "DRY_RUN" else "LIVE").append("  autotrading=").append(config.autoTradingEnabled).append('\n')
        sb.append("Kill switch    : ").append(if (KillSwitch.isEngaged(this)) "STOPPED (safe)" else "RUNNING").append('\n')
        sb.append("Log folder     : ").append(EventLog.logDir()).append('\n')
        sb.append("Feed watch     : ").append(FeedWatcher.statusLine).append('\n')
        statusText.text = sb.toString()

        killButton.text = if (KillSwitch.isEngaged(this)) "STOP ENGAGED — nothing will trade" else "STOP RELEASED — tap to halt"
        killButton.setBackgroundColor(ContextCompat.getColor(this, if (KillSwitch.isEngaged(this)) R.color.safe else R.color.danger))

        val tail = EventLog.tail(80)
        if (tail.length != lastLogLength) {
            lastLogLength = tail.length
            logText.text = tail
            logScroll.post { logScroll.fullScroll(ScrollView.FOCUS_DOWN) }
        }
    }

    private fun openSettings(action: String) {
        try {
            val i = Intent(action)
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(i)
        } catch (t: Throwable) {
            toast("Your Settings app hides that screen. Search 'Notification access' inside Settings instead.")
        }
    }

    private fun openInvo() {
        val i = packageManager.getLaunchIntentForPackage(config.invoPackage)
        if (i == null) {
            toast("INVO not found (package " + config.invoPackage + ")")
            return
        }
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivity(i)
    }

    /** Proves the whole pipe works even if INVO never posts a notification. */
    private fun selfTest() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val ch = NotificationChannel(CHANNEL, "INVO Copier self-test", NotificationManager.IMPORTANCE_HIGH)
        nm.createNotificationChannel(ch)

        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 41)
            EventLog.line("SELFTEST needs the 'Notifications' permission - allow it, then tap Run self-test again")
            toast("Allow notifications, then tap 'Run self-test' again")
            return
        }

        val pi = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val n = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle("@bones opened new trade")
            .setContentText("BTC LONG 40x entry \$78,524 (SELFTEST)")
            .setStyle(
                NotificationCompat.BigTextStyle().bigText(
                    "Trader: Bones\nAsset: BTC\nDirection: Long\nLeverage: 40x\n" +
                        "Entry price: \$78,524\n\nSynthetic notification - proves the listener pipeline works."
                )
            )
            .setContentIntent(pi)
            .setAutoCancel(true)
            .addAction(0, "Mimic Trade", pi)
            .build()
        nm.notify(777, n)
        EventLog.line("SELFTEST_POSTED id=777 - a NOTIF_POSTED record should appear below")
        render()
    }

    private fun dumpUi() {
        val svc = InvoAccessibilityService.instance
        if (svc == null) {
            toast("Enable the screen reader service first (Grant screen access).")
            EventLog.line("UI_DUMP_SKIPPED accessibility not enabled")
            render()
            return
        }
        val j = svc.dumpActiveWindow()
        j.put("ev", "UI_DUMP")
        EventLog.json(j)
        toast("Screen tree written to the log")
        render()
    }

    private fun copy(text: String, label: String) {
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(ClipData.newPlainText(label, text))
        toast("Copied " + label + " to clipboard")
    }

    private fun toast(s: String) {
        Toast.makeText(this, s, Toast.LENGTH_SHORT).show()
    }

    companion object {
        private const val CHANNEL = "invo_copier_test"
        /** Bump this with every published change so it is obvious on screen which build is installed. */
        const val APP_BUILD = "P1.3"
    }
}
