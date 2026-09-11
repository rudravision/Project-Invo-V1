package com.invocopier.config

import android.content.Context

/**
 * Physical emergency stop. Lives on the device (SharedPreferences), not in the
 * config file, so the two are independent keys: live execution requires BOTH
 *
 *   config file AUTOTRADING_ENABLED = true
 *   AND on-screen STOP released
 *
 * Default is ENGAGED = no execution, ever, until a human releases it.
 */
object KillSwitch {

    private const val PREFS = "invo_ctl"
    private const val KEY = "forced_stop"

    private fun prefs(context: Context) =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun isEngaged(context: Context): Boolean = prefs(context).getBoolean(KEY, true)

    fun setEngaged(context: Context, engaged: Boolean) {
        prefs(context).edit().putBoolean(KEY, engaged).apply()
    }

    fun toggle(context: Context): Boolean {
        val now = !isEngaged(context)
        setEngaged(context, now)
        return now
    }

    fun verdict(context: Context, config: CopierConfig): String = when {
        isEngaged(context) -> "BLOCKED_KILL_SWITCH"
        !config.autoTradingEnabled -> "BLOCKED_AUTOTRADING_DISABLED"
        config.dryRun -> "DRY_RUN_WOULD_SIMULATE"
        else -> "LIVE_WOULD_EXECUTE"
    }
}
