package com.invocopier.parser

import org.json.JSONObject
import java.security.MessageDigest
import java.util.Locale

enum class InvoAction { OPEN, UPDATE, CLOSE, UNKNOWN }

/**
 * What we could read out of a notification's text.
 *
 * Phase 1 only LOGS this. It is never used to execute anything.
 * The important output is [complete]: if a field is null the later phases must
 * fall back to reading the INVO screen with AccessibilityService, so this class
 * is also our feasibility measurement.
 */
data class ParsedEvent(
    val handle: String?,
    val asset: String?,
    val action: InvoAction,
    val direction: String?,
    val leverageX: Int?,
    val entryPrice: String?,
    val openHits: Int,
    val updateHits: Int,
    val closeHits: Int,
    val ambiguous: Boolean,
    val fingerprintNoTime: String,
    val fingerprintExact: String
) {

    val complete: Boolean
        get() = handle != null && asset != null && action != InvoAction.UNKNOWN && direction != null

    fun toJson(): JSONObject {
        val o = JSONObject()
        o.put("handle", handle ?: "")
        o.put("asset", asset ?: "")
        o.put("action", action.name)
        o.put("direction", direction ?: "")
        o.put("leverage", leverageX ?: 0)
        o.put("entryPrice", entryPrice ?: "")
        o.put("hitsOpen", openHits)
        o.put("hitsUpdate", updateHits)
        o.put("hitsClose", closeHits)
        o.put("ambiguous", ambiguous)
        o.put("complete", complete)
        o.put("fpNoTime", fingerprintNoTime)
        o.put("fpExact", fingerprintExact)
        return o
    }

    companion object {

        private val handleRe = Regex("@([A-Za-z0-9_.]{2,32})")
        private val leverageRe = Regex("(\\d{1,3})\\s*x", RegexOption.IGNORE_CASE)
        private val directionRe = Regex("\\b(long|short|buy|sell)\\b", RegexOption.IGNORE_CASE)
        private val priceRe = Regex("\\$\\s?([0-9][0-9,]*(?:\\.[0-9]+)?)")
        private val tokenRe = Regex("\\b([A-Z][A-Z0-9]{1,9})\\b")

        private val stopWords = setOf(
            "LONG", "SHORT", "BUY", "SELL", "USD", "USDT", "USDC", "TP", "SL",
            "NEW", "OPEN", "OPENS", "OPENED", "CLOSE", "CLOSES", "CLOSED",
            "UPDATE", "UPDATES", "UPDATED", "TRADE", "TRADES", "POSITION", "POSITIONS",
            "AND", "THE", "AT", "IN", "ON", "FOR", "WITH", "PNL", "ROI", "MAX", "MIN",
            "APP", "INVO", "PERP", "PERPUSDT", "BTCUSDT", "ETHUSDT", "SIZE", "LEVERAGE",
            "HOURS", "MINUTES", "AM", "PM", "UTC", "IST"
        )

        private val openVerbs = listOf("opened", "opens", "new trade", "new position", "entered", "long entry", "short entry")
        private val updateVerbs = listOf(
            "updated", "update", "adjusted", "adjust", "changed", "modified",
            "increased", "decreased", "added to", "reduced", "moved", "partial", "tp ", "sl "
        )
        private val closeVerbs = listOf(
            "closed", "closes", "close ", "exited", "exits", "exit", "liquidated",
            "liquidation", "stopped out", "took profit", "tp hit", "sl hit", "no position", "flipped"
        )

        fun parse(text: String, packageName: String, notificationId: Int, postTime: Long): ParsedEvent {
            val lower = text.lowercase(Locale.ROOT)

            val openHits = openVerbs.count { lower.contains(it) }
            val updateHits = updateVerbs.count { lower.contains(it) }
            val closeHits = closeVerbs.count { lower.contains(it) }

            val best = maxOf(openHits, updateHits, closeHits)
            val ties = listOf(openHits, updateHits, closeHits).count { it == best && best > 0 }
            val ambiguous = best == 0 || ties > 1
            val action = when {
                best == 0 -> InvoAction.UNKNOWN
                ties > 1 -> InvoAction.UNKNOWN
                closeHits == best -> InvoAction.CLOSE
                updateHits == best -> InvoAction.UPDATE
                else -> InvoAction.OPEN
            }

            val handle = handleRe.find(text)?.groupValues?.getOrNull(1)?.let { "@" + it.lowercase(Locale.ROOT) }
            val asset = findAsset(text)
            val direction = directionRe.find(text)?.groupValues?.getOrNull(1)?.lowercase(Locale.ROOT)?.let {
                when (it) {
                    "long", "buy" -> "LONG"
                    else -> "SHORT"
                }
            }
            val leverage = leverageRe.find(text)?.groupValues?.getOrNull(1)?.toIntOrNull()
            val price = priceRe.find(text)?.groupValues?.getOrNull(1)

            val norm = normalise(text)
            val fpNoTime = sha(packageName + "|" + (handle ?: "-") + "|" + (asset ?: "-") + "|" + action.name + "|" + norm)
            val fpExact = sha(fpNoTime + "|" + notificationId + "|" + postTime)

            return ParsedEvent(
                handle = handle,
                asset = asset,
                action = action,
                direction = direction,
                leverageX = leverage,
                entryPrice = price,
                openHits = openHits,
                updateHits = updateHits,
                closeHits = closeHits,
                ambiguous = ambiguous,
                fingerprintNoTime = fpNoTime,
                fingerprintExact = fpExact
            )
        }

        private fun findAsset(text: String): String? {
            for (m in tokenRe.findAll(text)) {
                val tok = m.groupValues.getOrNull(1) ?: continue
                if (tok in stopWords) continue
                if (tok.length < 2) continue
                return tok
            }
            return null
        }

        private fun normalise(s: String): String =
            s.lowercase(Locale.ROOT).map { if (it.isLetterOrDigit()) it else ' ' }.joinToString("")
                .replace(Regex("\\s+"), " ").trim()

        private fun sha(s: String): String {
            return try {
                val d = MessageDigest.getInstance("SHA-256").digest(s.toByteArray(Charsets.UTF_8))
                val sb = StringBuilder()
                for (i in 0 until 8) {
                    val v = d[i].toInt() and 0xFF
                    if (v < 16) sb.append('0')
                    sb.append(Integer.toHexString(v))
                }
                sb.toString()
            } catch (t: Throwable) {
                "hashfail"
            }
        }
    }
}

/**
 * Entry point for everything that wants to know what a notification means.
 * Detection only: this object cannot click, swipe or submit anything.
 */
object InvoEventParser {

    fun parse(
        text: String,
        packageName: String,
        notificationId: Int,
        postTime: Long
    ): ParsedEvent = ParsedEvent.parse(text, packageName, notificationId, postTime)
}
