package com.invocopier.parser

import com.invocopier.accessibility.InvoAccessibilityService.ScreenSnapshot

/**
 * One trade card on a trader's page, as INVO actually renders it.
 *
 * Captured verbatim from the phone (build P1.4, 2026-09-11):
 *   "btc 40x short \$77,713.00 +5.30% exit price \$77,610.00 hold time 8 minutes"
 *   "btc 40x short \$77,672.00 +6.26% \$77,550.50"
 * The second one has no exit price, so it is still open, and it carries its own
 * "Mimic Trade" button inside the same box.
 */
class MoveCard(
    val asset: String,
    val leverage: Int,
    val direction: String,
    val entry: String,
    val pnl: String,
    val exitPrice: String,
    val holdTime: String,
    val raw: String,
    val top: Int,
    val bottom: Int,
    var mimicFound: Boolean = false,
    var mimicLine: String = ""
) {

    /** A card with an exit price has already been closed by the trader. */
    val open: Boolean get() = exitPrice.isEmpty()

    fun oneLine(): String {
        val sb = StringBuilder()
        sb.append(asset).append(" ").append(direction).append(" ").append(leverage).append("x")
        sb.append(" entry ").append(entry)
        if (pnl.isNotEmpty()) sb.append("  pnl ").append(pnl)
        if (exitPrice.isNotEmpty()) sb.append("  CLOSED at ").append(exitPrice)
        if (holdTime.isNotEmpty()) sb.append("  held ").append(holdTime)
        sb.append(if (mimicFound) "   [Mimic button on this card]" else "   [no Mimic button]")
        return sb.toString()
    }
}

/**
 * Turns a trader's page into a list of MoveCards and finds each card's own Mimic
 * button by geometry, because that is how INVO lays them out.
 */
object MovesReader {

    private val cardRe = Regex(
        "(?i)^\\s*\\$?([a-z][a-z0-9]{1,9})\\s+(\\d{1,3})x\\s+(long|short)\\s+\\$?([\\d.,]+)(.*)$"
    )
    private val pnlRe = Regex("([+-]\\d+(?:\\.\\d+)?%|\\d+(?:\\.\\d+)?%)")
    private val exitRe = Regex("(?i)exit price\\s*\\$?([\\d.,]+)")
    private val holdRe = Regex("(?i)hold time\\s+([a-z0-9 .]{1,24})")
    private val junk = setOf("LONG", "SHORT", "OPEN", "CLOSE", "CLOSED", "TP", "SL", "MAX", "TODAY")

    fun read(snap: ScreenSnapshot): List<MoveCard> {
        val out = ArrayList<MoveCard>()
        for (n in snap.nodes) {
            if (!n.clickable) continue
            val label = (if (n.text.isNotBlank()) n.text else n.desc).replace('\n', ' ').trim()
            if (label.isBlank()) continue
            val m = cardRe.find(label) ?: continue
            val asset = m.groupValues[1].uppercase()
            if (junk.contains(asset)) continue
            val lev = m.groupValues[2].toIntOrNull() ?: continue
            if (lev < 1 || lev > 300) continue
            val rest = m.groupValues[5]
            out.add(
                MoveCard(
                    asset = asset,
                    leverage = lev,
                    direction = m.groupValues[3].uppercase(),
                    entry = clean(m.groupValues[4]),
                    pnl = pnlRe.find(rest)?.value ?: "",
                    exitPrice = clean(exitRe.find(rest)?.groupValues?.getOrNull(1) ?: ""),
                    holdTime = (holdRe.find(rest)?.groupValues?.getOrNull(1) ?: "").trim(),
                    raw = label,
                    top = n.top,
                    bottom = n.bottom
                )
            )
        }
        attachMimicButtons(snap, out)
        return out
    }

    /** A card owns the Mimic button whose vertical centre falls inside the card's box. */
    private fun attachMimicButtons(snap: ScreenSnapshot, cards: List<MoveCard>) {
        val buttons = ArrayList<Triple<Int, Int, String>>()
        for (n in snap.nodes) {
            val label = (if (n.text.isNotBlank()) n.text else n.desc).lowercase()
            if (!n.clickable || !label.contains("mimic") || label.contains("tab")) continue
            buttons.add(Triple((n.top + n.bottom) / 2, n.top, n.left.toString() + "," + n.top + "-" + n.right + "," + n.bottom))
        }
        for (c in cards) {
            for (b in buttons) {
                if (b.first >= c.top - 60 && b.first <= c.bottom + 60) {
                    c.mimicFound = true
                    c.mimicLine = "mimic button at (" + b.third + ")"
                    break
                }
            }
        }
    }

    private fun clean(s: String): String = s.trim().trimEnd('.', ',')
}
