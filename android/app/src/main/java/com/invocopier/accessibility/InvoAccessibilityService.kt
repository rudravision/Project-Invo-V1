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

    /**
     * One readable node with its geometry, for the parsers. Bounds are included so
     * that a later phase can act on a slider if it ever has to, but nothing here
     * presses anything by itself.
     */
    class NodeRec(
        val cls: String,
        val id: String,
        val text: String,
        val desc: String,
        val clickable: Boolean,
        val left: Int,
        val top: Int,
        val right: Int,
        val bottom: Int
    ) {
        val label: String get() = if (text.isNotBlank()) text else desc

        fun boundsText(): String = "(" + left + "," + top + "-" + right + "," + bottom + ")"
    }

    class ScreenSnapshot(val pkg: String, val nodeCount: Int, val nodes: List<NodeRec>)

    /** Read the whole foreground screen as data. Nothing is clicked or scrolled. */
    fun readScreen(): ScreenSnapshot {
        val root = try {
            rootInActiveWindow
        } catch (t: Throwable) {
            null
        } ?: return ScreenSnapshot("", 0, emptyList())
        val out = ArrayList<NodeRec>()
        val n = readWalk(root, out, 0)
        return ScreenSnapshot(root.packageName?.toString() ?: "", n, out)
    }

    private fun readWalk(node: AccessibilityNodeInfo?, out: ArrayList<NodeRec>, idxIn: Int): Int {
        var idx = idxIn
        if (node == null || idx >= MAX_NODES) return idx
        idx++
        try {
            val cls = node.className?.toString()?.substringAfterLast('.') ?: "?"
            val txt = try {
                node.text?.toString()?.trim() ?: ""
            } catch (t: Throwable) {
                ""
            }
            val dsc = try {
                node.contentDescription?.toString()?.trim() ?: ""
            } catch (t: Throwable) {
                ""
            }
            val clk = try {
                node.isClickable
            } catch (t: Throwable) {
                false
            }
            val vid = try {
                (node.viewIdResourceName ?: "").substringAfterLast('/')
            } catch (t: Throwable) {
                ""
            }
            var l = 0
            var t0 = 0
            var r = 0
            var b = 0
            try {
                val rect = android.graphics.Rect()
                node.getBoundsInScreen(rect)
                l = rect.left
                t0 = rect.top
                r = rect.right
                b = rect.bottom
            } catch (t: Throwable) {
                // bounds stay zero
            }
            if (txt.isNotBlank() || dsc.isNotBlank() || clk) {
                out.add(
                    NodeRec(cls, vid, txt.replace('\n', ' '), dsc.replace('\n', ' '), clk, l, t0, r, b)
                )
            }
        } catch (t: Throwable) {
            // ignore one bad node
        }
        val cc = try {
            node.childCount
        } catch (t: Throwable) {
            0
        }
        var c = 0
        while (c < cc && idx < MAX_NODES) {
            idx = readWalk(node.getChild(c), out, idx)
            c++
        }
        return idx
    }

    /** Semantic click on anything whose text or description contains [needle]. */
    fun clickByTextOrDesc(needle: String): Boolean {
        val root = try {
            rootInActiveWindow
        } catch (t: Throwable) {
            null
        } ?: return false
        val node = findClickableText(root, needle, 0) ?: return false
        return try {
            node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        } catch (t: Throwable) {
            false
        }
    }

    private fun findClickableText(
        node: AccessibilityNodeInfo?,
        needle: String,
        depth: Int
    ): AccessibilityNodeInfo? {
        if (node == null || depth > 30) return null
        val t = try {
            node.text?.toString() ?: ""
        } catch (e: Throwable) {
            ""
        }
        val d = try {
            node.contentDescription?.toString() ?: ""
        } catch (e: Throwable) {
            ""
        }
        if ((t.contains(needle, ignoreCase = true) || d.contains(needle, ignoreCase = true)) && node.isClickable) {
            return node
        }
        val cc = node.childCount
        var c = 0
        while (c < cc) {
            val found = findClickableText(node.getChild(c), needle, depth + 1)
            if (found != null) return found
            c++
        }
        return null
    }

    /**
     * Scroll the page once. Used only when a field we need sits below the fold,
     * so a missing value is not mistaken for an unreadable app.
     */
    fun scrollForward(): Boolean {
        val root = try {
            rootInActiveWindow
        } catch (t: Throwable) {
            null
        } ?: return false
        val target = findScrollable(root, 0) ?: return false
        return try {
            target.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD)
        } catch (t: Throwable) {
            false
        }
    }

    private fun findScrollable(node: AccessibilityNodeInfo?, depth: Int): AccessibilityNodeInfo? {
        if (node == null || depth > 25) return null
        val ok = try {
            node.isScrollable
        } catch (t: Throwable) {
            false
        }
        if (ok) return node
        val cc = node.childCount
        var c = 0
        while (c < cc) {
            val found = findScrollable(node.getChild(c), depth + 1)
            if (found != null) return found
            c++
        }
        return null
    }

    /**
     * Tap the thing a description points at, even when Flutter marks only an
     * ancestor clickable. Tries the node itself, then the nearest clickable
     * ancestor, then a single short gesture at its centre.
     */
    fun clickByDescSmart(needle: String): Boolean {
        val root = try {
            rootInActiveWindow
        } catch (t: Throwable) {
            null
        } ?: return false
        val node = findByDesc(root, needle, 0) ?: return false
        val selfClickable = try {
            node.isClickable
        } catch (t: Throwable) {
            false
        }
        if (selfClickable) {
            val ok = try {
                node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            } catch (t: Throwable) {
                false
            }
            if (ok) return true
        }
        var parent: AccessibilityNodeInfo? = null
        try {
            parent = node.parent
        } catch (t: Throwable) {
            parent = null
        }
        var hops = 0
        while (parent != null && hops < 5) {
            val pClick = try {
                parent.isClickable
            } catch (t: Throwable) {
                false
            }
            if (pClick) {
                val ok = try {
                    parent.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                } catch (t: Throwable) {
                    false
                }
                if (ok) return true
            }
            parent = try {
                parent.parent
            } catch (t: Throwable) {
                null
            }
            hops++
        }
        val rect = android.graphics.Rect()
        val haveRect = try {
            node.getBoundsInScreen(rect)
            true
        } catch (t: Throwable) {
            false
        }
        if (!haveRect || rect.isEmpty) return false
        return tapAt(rect.centerX(), rect.centerY())
    }

    private fun findByDesc(
        node: AccessibilityNodeInfo?,
        needle: String,
        depth: Int
    ): AccessibilityNodeInfo? {
        if (node == null || depth > 30) return null
        val d = try {
            node.contentDescription?.toString() ?: ""
        } catch (t: Throwable) {
            ""
        }
        if (d.contains(needle, ignoreCase = true)) return node
        val cc = node.childCount
        var c = 0
        while (c < cc) {
            val found = findByDesc(node.getChild(c), needle, depth + 1)
            if (found != null) return found
            c++
        }
        return null
    }

    /**
     * One short touch, fired and trusted: the caller checks what the screen did next
     * rather than waiting for a gesture callback on this same thread.
     */
    private fun tapAt(x: Int, y: Int): Boolean = try {
        val path = android.graphics.Path()
        path.moveTo(x.toFloat(), y.toFloat())
        val stroke = android.accessibilityservice.GestureDescription.StrokeDescription(path, 0, 90)
        val gd = android.accessibilityservice.GestureDescription.Builder().addStroke(stroke).build()
        dispatchGesture(gd, null, null)
    } catch (t: Throwable) {
        false
    }

    /** System back key, used to leave a page we only opened to look at. */
    fun goBack(): Boolean = try {
        performGlobalAction(GLOBAL_ACTION_BACK)
    } catch (t: Throwable) {
        false
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
