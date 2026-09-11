package com.invocopier.accessibility

import android.accessibilityservice.AccessibilityService
import android.os.Build
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.invocopier.config.CopierConfig
import com.invocopier.logging.EventLog
import org.json.JSONObject

/**
 * METHOD 3 feasibility probe ONLY.
 *
 * In Phase 1 this service does not click, does not scroll and does not gesture.
 * It answers one question, with data instead of guesses:
 *
 *   "Does the INVO app expose readable text nodes, or will we be forced into OCR?"
 *
 * It records which window is in the foreground, and the UI button can dump the
 * current node tree of INVO's screen to the same log file.
 */
class InvoAccessibilityService : AccessibilityService() {

    private var config: CopierConfig = CopierConfig.defaults()
    private var lastWindowKey: String = ""

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        EventLog.init(applicationContext)
        config = CopierConfig.load(applicationContext)
        val o = JSONObject()
        o.put("ev", "ACCESSIBILITY_CONNECTED")
        o.put("androidSdk", Build.VERSION.SDK_INT)
        o.put("invoPackage", config.invoPackage)
        EventLog.json(o)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        val e = event ?: return
        if (e.eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) return
        val pkg = e.packageName?.toString() ?: return
        val key = pkg + "|" + (e.className?.toString() ?: "")
        if (key == lastWindowKey) return
        lastWindowKey = key
        val isTarget = pkg == config.invoPackage ||
            (config.packageKeyword.isNotBlank() && pkg.contains(config.packageKeyword, ignoreCase = true))
        val o = JSONObject()
        o.put("ev", "WINDOW")
        o.put("target", isTarget)
        o.put("pkg", pkg)
        o.put("windowClass", e.className?.toString() ?: "")
        EventLog.json(o)
    }

    override fun onInterrupt() {
        EventLog.line("ACCESSIBILITY_INTERRUPTED")
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        EventLog.line("ACCESSIBILITY_DESTROYED")
        super.onDestroy()
    }

    /**
     * Dump the active window as a compact node tree.
     * This is the in-app equivalent of `uiautomator dump`, and it works even when
     * a PC is not connected.
     */
    fun dumpActiveWindow(): JSONObject {
        val out = JSONObject()
        val root = try {
            rootInActiveWindow
        } catch (t: Throwable) {
            null
        }
        if (root == null) {
            out.put("error", "rootInActiveWindow is null (screen off, or app blocks inspection)")
            return out
        }
        val sb = StringBuilder()
        val n = walk(root, 0, sb, 0)
        out.put("pkg", root.packageName?.toString() ?: "")
        out.put("nodeCount", n)
        out.put("tree", sb.toString())
        return out
    }

    private fun walk(node: AccessibilityNodeInfo?, depth: Int, sb: StringBuilder, idx: Int): Int {
        if (node == null || idx >= MAX_NODES || depth > MAX_DEPTH) return idx
        var i = idx + 1
        val cls = node.className?.toString()?.substringAfterLast('.') ?: "?"
        sb.append("  ".repeat(depth)).append(cls)
        try {
            val id = node.viewIdResourceName
            if (!id.isNullOrBlank()) sb.append(" id=").append(id)
        } catch (t: Throwable) {
            // ignore
        }
        val text = try { node.text?.toString() } catch (t: Throwable) { null }
        if (!text.isNullOrBlank()) sb.append(" text=").append(tiny(text))
        val desc = try { node.contentDescription?.toString() } catch (t: Throwable) { null }
        if (!desc.isNullOrBlank()) sb.append(" desc=").append(tiny(desc))
        if (node.isClickable) sb.append(" [click]")
        val b = android.graphics.Rect()
        try {
            node.getBoundsInScreen(b)
            sb.append(" bounds=").append(b.toShortString())
        } catch (t: Throwable) {
            // ignore
        }
        sb.append('\n')
        val cc = node.childCount
        var c = 0
        while (c < cc) {
            i = walk(node.getChild(c), depth + 1, sb, i)
            c++
        }
        return i
    }

    fun foregroundPackage(): String = try {
        rootInActiveWindow?.packageName?.toString() ?: ""
    } catch (t: Throwable) {
        ""
    }

    /**
     * Feed rows = clickable nodes whose contentDescription contains an @handle.
     * Returned top-to-bottom, which for INVO means newest-first.
     */
    fun collectFeedRows(): List<String> {
        val root = try { rootInActiveWindow } catch (t: Throwable) { null } ?: return emptyList()
        val out = ArrayList<Pair<Int, String>>()
        walkFeed(root, out, 0)
        return out.sortedBy { it.first }.map { it.second }
    }

    private fun walkFeed(node: AccessibilityNodeInfo?, out: ArrayList<Pair<Int, String>>, guardIn: Int): Int {
        var guard = guardIn
        if (node == null || guard > 4000) return guard
        guard++
        try {
            val d = node.contentDescription?.toString() ?: ""
            if (d.contains("@") && node.isClickable) {
                val r = android.graphics.Rect()
                node.getBoundsInScreen(r)
                out.add(Pair(r.top, d.replace('\n', ' ').trim()))
            }
        } catch (t: Throwable) {
            // ignore one bad node
        }
        val cc = node.childCount
        var c = 0
        while (c < cc && guard <= 4000) {
            guard = walkFeed(node.getChild(c), out, guard)
            c++
        }
        return guard
    }

    /** Semantic click: find a clickable node by its description and tap it. */
    fun clickByDescContains(needle: String): Boolean {
        val root = try { rootInActiveWindow } catch (t: Throwable) { null } ?: return false
        val node = findClickableByDesc(root, needle, 0) ?: return false
        return try {
            node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        } catch (t: Throwable) {
            false
        }
    }

    private fun findClickableByDesc(
        node: AccessibilityNodeInfo?,
        needle: String,
        depth: Int
    ): AccessibilityNodeInfo? {
        if (node == null || depth > 30) return null
        val d = try { node.contentDescription?.toString() ?: "" } catch (t: Throwable) { "" }
        if (d.contains(needle, ignoreCase = true) && node.isClickable) return node
        val cc = node.childCount
        var c = 0
        while (c < cc) {
            val found = findClickableByDesc(node.getChild(c), needle, depth + 1)
            if (found != null) return found
            c++
        }
        return null
    }

    private fun tiny(s: String): String {
        val f = s.replace('\n', ' ').trim()
        return if (f.length > 90) f.substring(0, 90) + ".." else f
    }

    companion object {

        private const val MAX_NODES = 900
        private const val MAX_DEPTH = 28

        @Volatile
        var instance: InvoAccessibilityService? = null

        fun isReady(): Boolean = instance != null

        fun adbEnableCommand(context: android.content.Context): String =
            "adb shell settings put secure enabled_accessibility_services " +
                context.packageName + "/" + InvoAccessibilityService::class.java.name
    }
}
