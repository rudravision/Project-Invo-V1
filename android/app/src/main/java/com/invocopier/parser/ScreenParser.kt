package com.invocopier.parser

import com.invocopier.accessibility.InvoAccessibilityService.NodeRec
import com.invocopier.accessibility.InvoAccessibilityService.ScreenSnapshot

/**
 * What we managed to read off a trade page. A null field means "not visible",
 * never a guess - the caller must refuse to act when a needed field is missing.
 */
class TradePage(
    val asset: String?,
    val direction: String?,
    val leverage: Int?,
    val entry: String?,
    val size: String?,
    val closeLabel: String?,
    val mimicLabel: String?,
    val mimicClickable: Boolean,
    val sliderLine: String?,
    val readable: List<String>
) {

    val missing: List<String>
        get() {
            val m = ArrayList<String>()
            if (asset == null) m.add("asset")
            if (direction == null) m.add("direction")
            if (leverage == null) m.add("leverage")
            if (entry == null) m.add("entry price")
            if (mimicLabel == null) m.add("mimic button")
            return m
        }

    /** Enough to fill a size safely? Anything less and Phase 4 must refuse. */
    fun hasBasics(): Boolean =
        asset != null && direction != null && leverage != null && entry != null && mimicClickable

    fun summary(): String {
        val sb = StringBuilder()
        sb.append("asset       : ").append(asset ?: "?").append('\n')
        sb.append("direction   : ").append(direction ?: "?").append('\n')
        sb.append("leverage    : ").append(if (leverage == null) "?" else leverage.toString() + "x").append('\n')
        sb.append("entry price : ").append(entry ?: "?").append('\n')
        sb.append("size shown  : ").append(size ?: "?").append('\n')
        sb.append("mimic button: ")
        if (mimicLabel == null) {
            sb.append("NOT FOUND on this screen")
        } else {
            sb.append('"').append(mimicLabel).append('"')
            sb.append(if (mimicClickable) " (clickable - we can press it)" else " (visible but NOT clickable)")
        }
        sb.append('\n')
        sb.append("slider      : ").append(sliderLine ?: "none found (leverage may be typed, not slid)")
        sb.append('\n')
        sb.append("close button: ").append(closeLabel ?: "not found on this screen")
        return sb.toString()
    }
}

/**
 * Turns a screen of readable nodes into a TradePage. Every rule here is a plain
 * word/number search, so when INVO changes we only change a keyword, never a layout.
 */
object ScreenParser {

    private val leverageRe = Regex("(\\d{1,3}(?:\\.\\d{1,2})?)\\s*[xX]\\b")
    private val leverageRe2 = Regex("[xX](\\d{1,3})\\b")
    private val moneyRe = Regex("(\\d{1,3}(?:,\\d{3})+(?:\\.\\d+)?|\\d+(?:\\.\\d+)?)")
    private val namedAssetRe = Regex("(?i)updated\\s+([A-Za-z]{2,10})\\b")
    private val skipWords = setOf(
        "trade", "position", "order", "new", "close", "open", "updated", "closed",
        "opened", "the", "and", "for", "with", "from", "long", "short"
    )

    private val entryKeys = listOf(
        "entry price", "entry", "avg entry", "average entry", "open price",
        "fill price", "avg price", "average price", "mark price", "entry@"
    )
    private val sizeKeys = listOf("size", "amount", "margin", "quantity", "qty", "value")
    private val closeKeys = listOf("close position", "close all", "market close", "close")

    fun parse(snap: ScreenSnapshot, feedRow: String): TradePage {
        val labels = ArrayList<String>()
        for (n in snap.nodes) {
            val l = if (n.text.isNotBlank()) n.text else n.desc
            if (l.isNotBlank()) labels.add(l.replace('\n', ' ').trim())
        }
        val blob = labels.joinToString(" | ")

        // direction
        val direction = when {
            Regex("(?i)\\bLONG\\b").containsMatchIn(blob) &&
                !Regex("(?i)\\bSHORT\\b").containsMatchIn(blob) -> "LONG"
            Regex("(?i)\\bSHORT\\b").containsMatchIn(blob) &&
                !Regex("(?i)\\bLONG\\b").containsMatchIn(blob) -> "SHORT"
            Regex("(?i)\\bbuy\\b").containsMatchIn(blob) && !Regex("(?i)\\bsell\\b").containsMatchIn(blob) -> "LONG"
            Regex("(?i)\\bsell\\b").containsMatchIn(blob) && !Regex("(?i)\\bbuy\\b").containsMatchIn(blob) -> "SHORT"
            else -> null
        }

        // leverage
        var leverage: Int? = null
        for (l in labels) {
            if (l.lowercase().contains("leverage")) {
                val m = leverageRe.find(l) ?: leverageRe2.find(l)
                val v = m?.groupValues?.getOrNull(1)?.toDoubleOrNull()
                if (v != null && v >= 1 && v <= 300) {
                    leverage = v.toInt()
                    break
                }
            }
        }
        if (leverage == null) {
            val m = leverageRe.find(blob) ?: leverageRe2.find(blob)
            val v = m?.groupValues?.getOrNull(1)?.toDoubleOrNull()
            if (v != null && v >= 1 && v <= 300) leverage = v.toInt()
        }

        // asset - feed row first (it names the coin for asset-specific events)
        var asset: String? = null
        val named = namedAssetRe.find(feedRow)?.groupValues?.getOrNull(1)?.uppercase()
        if (named != null && !named.lowercase().let { skipWords.contains(it) }) asset = named
        if (asset == null) {
            for (l in labels) {
                val m = Regex("\\$([A-Z]{2,7})\\b").find(l)
                if (m != null && !skipWords.contains(m.groupValues[1].lowercase())) {
                    asset = m.groupValues[1]
                    break
                }
            }
        }
        if (asset == null) {
            for (l in labels) {
                val m = Regex("([A-Z]{2,7})(?:USDT|/USDT)").find(l)
                if (m != null) {
                    asset = m.groupValues[1]
                    break
                }
            }
        }
        if (asset == null) {
            val m = Regex("\\b([A-Z]{3,6})\\b").find(blob)
            if (m != null && !skipWords.contains(m.groupValues[1].lowercase())) asset = m.groupValues[1]
        }

        // entry price - only look at labels that mention an entry-ish word
        var entry: String? = null
        for (l in labels) {
            val ll = l.lowercase()
            var hit = false
            for (k in entryKeys) if (ll.contains(k)) hit = true
            if (!hit) continue
            val m = moneyRe.findAll(l).lastOrNull()
            if (m != null) {
                val num = m.groupValues[1].replace(",", "").toDoubleOrNull()
                if (num != null && num > 0.00001) {
                    entry = m.groupValues[1]
                    break
                }
            }
        }
        // Deliberately no fallback here: an unrelated number on the page is never
        // treated as the entry price. Missing means "ask the user for a capture".

        // size / margin as displayed
        var size: String? = null
        for (l in labels) {
            val ll = l.lowercase()
            var hit = false
            for (k in sizeKeys) if (ll.contains(k)) hit = true
            if (hit && moneyRe.containsMatchIn(l)) {
                size = if (l.length > 60) l.substring(0, 60) else l
                break
            }
        }

        // the button that matters
        var mimicLabel: String? = null
        var mimicClickable = false
        for (n in snap.nodes) {
            val l = if (n.text.isNotBlank()) n.text else n.desc
            if (l.isNotBlank() && l.lowercase().contains("mimic")) {
                mimicLabel = if (l.length > 60) l.substring(0, 60) else l
                mimicClickable = n.clickable
                if (mimicClickable) break
            }
        }

        // a close control, needed for Phase 7
        var closeLabel: String? = null
        for (n in snap.nodes) {
            val l = if (n.text.isNotBlank()) n.text else n.desc
            if (!n.clickable || l.isBlank()) continue
            val ll = l.lowercase()
            if (ll.contains("mimic")) continue
            for (k in closeKeys) {
                if (ll.startsWith(k)) {
                    closeLabel = if (l.length > 50) l.substring(0, 50) else l
                    break
                }
            }
            if (closeLabel != null) break
        }

        val readable = readableLines(snap, 26)

        return TradePage(
            asset = asset,
            direction = direction,
            leverage = leverage,
            entry = entry,
            size = size,
            closeLabel = closeLabel,
            mimicLabel = mimicLabel,
            mimicClickable = mimicClickable,
            sliderLine = sliderLine(snap),
            readable = readable
        )
    }

    /** Lines a human and I both need when a field comes back "?". */
    fun readableLines(snap: ScreenSnapshot, limit: Int): List<String> {
        val keys = listOf(
            "mimic", "long", "short", "leverage", "entry", "price", "size", "amount",
            "margin", "close", "position", "profit", "loss", "available", "balance",
            "usd", "tp", "sl", "liq", "max"
        )
        val out = ArrayList<String>()
        for (n in snap.nodes) {
            val l = if (n.text.isNotBlank()) n.text else n.desc
            if (l.isBlank()) continue
            val ll = l.lowercase().replace('\n', ' ')
            var hit = false
            for (k in keys) if (ll.contains(k)) hit = true
            if (!hit) continue
            val cut = if (ll.length > 72) ll.substring(0, 72) + ".." else ll
            out.add((if (n.clickable) "[tap] " else "      ") + cut + "  " + n.boundsText())
            if (out.size >= limit) break
        }
        return out
    }

    /** Page identification, so a capture list reads like a table of contents. */
    fun pageHint(snap: ScreenSnapshot): String {
        val out = ArrayList<String>()
        for (n in snap.nodes) {
            val l = if (n.text.isNotBlank()) n.text else n.desc
            if (l.isBlank()) continue
            val f = l.replace('\n', ' ').trim()
            if (f.length < 2) continue
            if (out.contains(f)) continue
            out.add(if (f.length > 45) f.substring(0, 45) + ".." else f)
            if (out.size >= 4) break
        }
        return out.joinToString(" / ")
    }

    private fun sliderLine(snap: ScreenSnapshot): String? {
        for (n in snap.nodes) {
            if (isSlider(n)) return (if (n.cls == "SeekBar") "SeekBar " else n.cls + " ") + n.boundsText()
        }
        return null
    }

    private fun isSlider(n: NodeRec): Boolean {
        val c = n.cls.lowercase()
        return c.contains("seekbar") || c.contains("slider") || c.contains("range")
    }
}
