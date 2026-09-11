package com.invocopier.watch

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.invocopier.logging.EventLog

/**
 * Lets the PC turn the Phase-2 watcher on/off without opening the app:
 *
 *   adb shell am broadcast -a com.invocopier.WATCH --es cmd start --ei interval 5 --ez open true
 *   adb shell am broadcast -a com.invocopier.WATCH --es cmd status
 *   adb shell am broadcast -a com.invocopier.WATCH --es cmd stop
 *
 * Read-only control. It cannot enable live trading; that needs the config file
 * plus the on-screen STOP switch.
 */
class WatchCommandReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val cmd = intent.getStringExtra("cmd") ?: "status"
        when (cmd) {
            "start" -> {
                val interval = intent.getIntExtra("interval", 5)
                val open = intent.getBooleanExtra("open", false)
                FeedWatcher.start(context, interval, open)
            }
            "stop" -> FeedWatcher.stop()
            else -> EventLog.line("WATCH_STATUS " + FeedWatcher.statusLine)
        }
    }
}
