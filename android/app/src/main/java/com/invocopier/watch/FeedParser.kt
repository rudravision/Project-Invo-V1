package com.invocopier.watch

import com.invocopier.config.CopierConfig
import com.invocopier.parser.InvoAction
import com.invocopier.parser.InvoEventParser

/**
 * One row of INVO's in-app Notifications feed, understood.
 *
 * Real captured format (Flutter puts it all in contentDescription):
 *   "Bones   \u00B7  16h @bones updated trade"
 *   "meduolis   \u00B7  9h @booobsas updated DOGE"
 */
data class FeedSignal(
    val row: String,
    val displayName: String,
    val ageLabel: String,
    val handle: String,
    val action: InvoAction,
    val asset: String,
    val ambiguous: Boolean,
    val whitelisted: Boolean,
    val assetAllowed: Boolean,
    val verdict: String
)

object FeedParser {

    private val handleRe = Regex("@([A-Za-z0-9_.]{2,32})")
    private val ageRe = Regex("(\\d+\\s*[smhdw]|now|today)", RegexOption.IGNORE_CASE)
    private const val DOT = '\u00B7'

    fun parse(row: String, cfg: CopierConfig): FeedSignal {
        val bits = row.split(DOT)
        val display = (bits.firstOrNull() ?: "").trim()
        val tail = if (bits.size > 1) bits.drop(1).joinToString(" ").trim() else row

        val age = ageRe.find(tail)?.value?.replace(" ", "") ?: ""
        val handle = handleRe.find(tail)?.value?.lowercase() ?: ""

        val parsed = InvoEventParser.parse(tail, "invo.feed", 0, 0L)
        val whitelisted = cfg.isTraderWhitelisted(handle)
        val assetAllowed = parsed.asset == null || cfg.assetAllowed(parsed.asset)

        val verdict = when {
            handle.isEmpty() -> "IGNORE_NO_HANDLE"
            parsed.ambiguous -> "IGNORE_AMBIGUOUS_ACTION"
            !whitelisted -> "IGNORE_NOT_WHITELISTED"
            !assetAllowed -> "IGNORE_ASSET_NOT_ALLOWED"
            else -> "SIGNAL_" + parsed.action.name
        }

        return FeedSignal(
            row = row,
            displayName = display,
            ageLabel = age,
            handle = handle,
            action = parsed.action,
            asset = parsed.asset ?: "",
            ambiguous = parsed.ambiguous,
            whitelisted = whitelisted,
            assetAllowed = assetAllowed,
            verdict = verdict
        )
    }
}
