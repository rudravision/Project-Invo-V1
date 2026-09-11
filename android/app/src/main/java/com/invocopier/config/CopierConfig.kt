package com.invocopier.config

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.util.Locale

data class TraderRule(
    val handle: String,
    val enabled: Boolean,
    val allocationPercent: Double
)

/**
 * Single source of truth for every risk/behaviour switch.
 *
 * Load order (first hit wins):
 *   1. <external files dir>/invo_config.json   <- you push this with adb, no rebuild needed
 *   2. app/src/main/assets/invo_config.json    <- compiled default
 *   3. hard-coded [defaults]                   <- used if the json is broken
 *
 * FAIL-SAFE: a broken/unreadable config never crashes the app and never
 * silently enables live trading, because the defaults are dry-run + kill-switch off.
 */
data class CopierConfig(
    val invoPackage: String,
    val packageKeyword: String,
    val captureAllPackages: Boolean,
    val dryRun: Boolean,
    val autoTradingEnabled: Boolean,
    val maxLeverage: Int,
    val copyExactLeverage: Boolean,
    val maxPositionUsd: Double,
    val maxTotalExposureUsd: Double,
    val maxDailyLossUsd: Double,
    val maxOpenPositions: Int,
    val allowedAssets: List<String>,
    val traders: Map<String, TraderRule>,
    val source: String
) {

    fun isTraderWhitelisted(handle: String?): Boolean {
        if (handle.isNullOrBlank()) return false
        return traders[handle.lowercase(Locale.ROOT)]?.enabled == true
    }

    fun allocationFor(handle: String?): Double =
        handle?.let { traders[it.lowercase(Locale.ROOT)]?.allocationPercent } ?: 0.0

    /** Empty list == no asset restriction. */
    fun assetAllowed(asset: String?): Boolean {
        if (asset.isNullOrBlank()) return false
        if (allowedAssets.isEmpty()) return true
        return allowedAssets.any { it.equals(asset, ignoreCase = true) }
    }

    /**
     * Leverage we are actually allowed to use.
     * Never returns more than maxLeverage, even when the trader used 40x.
     */
    fun leverageToUse(traderLeverage: Int?): Int {
        if (copyExactLeverage && traderLeverage != null) {
            return traderLeverage.coerceAtMost(maxLeverage).coerceAtLeast(1)
        }
        return maxLeverage.coerceAtLeast(1)
    }

    /** Live execution is only ever possible when BOTH switches are on and dry-run is off. */
    fun executionAllowed(): Boolean =
        autoTradingEnabled && !dryRun

    fun summary(): String {
        val sb = StringBuilder()
        sb.append("config source = ").append(source).append('\n')
        sb.append("invoPackage   = ").append(invoPackage).append(" (keyword '").append(packageKeyword).append("')\n")
        sb.append("captureAllPkgs= ").append(captureAllPackages).append('\n')
        sb.append("DRY_RUN       = ").append(dryRun).append('\n')
        sb.append("AUTOTRADING   = ").append(autoTradingEnabled).append('\n')
        sb.append("execution     = ").append(if (executionAllowed()) "LIVE (danger)" else "BLOCKED").append('\n')
        sb.append("leverage      = ").append(maxLeverage).append("x  copyExact=").append(copyExactLeverage).append('\n')
        sb.append("maxPosition   = $").append(maxPositionUsd).append("  maxExposure=$").append(maxTotalExposureUsd)
            .append("  maxDailyLoss=$").append(maxDailyLossUsd).append('\n')
        sb.append("maxOpen       = ").append(maxOpenPositions).append('\n')
        sb.append("assets        = ").append(if (allowedAssets.isEmpty()) "(any)" else allowedAssets.joinToString(",")).append('\n')
        sb.append("traders       = ").append(
            if (traders.isEmpty()) "(empty)" else traders.values.joinToString(", ") { r ->
                r.handle + (if (r.enabled) "" else "(off)") + ":" + r.allocationPercent + "%"
            }
        )
        return sb.toString()
    }

    companion object {

        fun defaults(): CopierConfig = CopierConfig(
            invoPackage = "com.involio.app",
            packageKeyword = "invo",
            captureAllPackages = true,
            dryRun = true,
            autoTradingEnabled = false,
            maxLeverage = 5,
            copyExactLeverage = false,
            maxPositionUsd = 10.0,
            maxTotalExposureUsd = 30.0,
            maxDailyLossUsd = 20.0,
            maxOpenPositions = 3,
            allowedAssets = emptyList(),
            traders = emptyMap(),
            source = "built-in defaults"
        )

        fun load(context: Context): CopierConfig {
            val external = File(context.getExternalFilesDir(null) ?: context.filesDir, "invo_config.json")
            if (external.exists()) {
                val text = try {
                    external.readText()
                } catch (t: Throwable) {
                    null
                }
                if (text != null) {
                    val cfg = parse(text, "file:" + external.absolutePath)
                    if (cfg != null) return cfg
                    return defaults().copy(source = "BROKEN file:" + external.absolutePath + " -> defaults")
                }
            }
            val assetText = try {
                context.assets.open("invo_config.json").bufferedReader().use { it.readText() }
            } catch (t: Throwable) {
                null
            }
            if (assetText != null) {
                val cfg = parse(assetText, "assets/invo_config.json")
                if (cfg != null) return cfg
                return defaults().copy(source = "BROKEN assets config -> defaults")
            }
            return defaults()
        }

        private fun parse(text: String, source: String): CopierConfig? {
            return try {
                val o = JSONObject(text)
                val traders = LinkedHashMap<String, TraderRule>()
                val tj = o.optJSONObject("traders")
                if (tj != null) {
                    val keys = tj.keys()
                    while (keys.hasNext()) {
                        val k = keys.next()
                        val v = tj.optJSONObject(k) ?: continue
                        traders[k.lowercase(Locale.ROOT)] = TraderRule(
                            handle = k,
                            enabled = v.optBoolean("enabled", false),
                            allocationPercent = v.optDouble("allocation_percent", 0.0)
                        )
                    }
                }
                val assets = ArrayList<String>()
                val aj = o.optJSONArray("allowed_assets")
                if (aj != null) {
                    for (i in 0 until aj.length()) {
                        val s = aj.optString(i, "")
                        if (s.isNotBlank()) assets.add(s.uppercase(Locale.ROOT))
                    }
                }
                defaults().copy(
                    invoPackage = o.optString("invo_package", defaults().invoPackage),
                    packageKeyword = o.optString("package_keyword", defaults().packageKeyword),
                    captureAllPackages = o.optBoolean("capture_all_packages", true),
                    dryRun = o.optBoolean("DRY_RUN", true),
                    autoTradingEnabled = o.optBoolean("AUTOTRADING_ENABLED", false),
                    maxLeverage = o.optInt("MAX_LEVERAGE", 5),
                    copyExactLeverage = o.optBoolean("COPY_EXACT_LEVERAGE", false),
                    maxPositionUsd = o.optDouble("MAX_POSITION_USD", 10.0),
                    maxTotalExposureUsd = o.optDouble("MAX_TOTAL_EXPOSURE_USD", 30.0),
                    maxDailyLossUsd = o.optDouble("MAX_DAILY_LOSS_USD", 20.0),
                    maxOpenPositions = o.optInt("MAX_OPEN_POSITIONS", 3),
                    allowedAssets = assets,
                    traders = traders,
                    source = source
                )
            } catch (t: Throwable) {
                null
            }
        }
    }
}
