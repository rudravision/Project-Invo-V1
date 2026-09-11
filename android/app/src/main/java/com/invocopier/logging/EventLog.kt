package com.invocopier.logging

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.ArrayDeque
import java.util.Date
import java.util.Locale

/**
 * Phase-1 log sink.
 *
 * Every event is written as ONE json line to
 *   <external files dir>/logs/invo-events-YYYYMMDD.jsonl
 * and mirrored to logcat with tag [INVO_P1].
 *
 * Nothing here can execute a trade. It only records.
 */
object EventLog {

    const val TAG = "INVO_P1"

    private val lock = Any()
    private val ring = ArrayDeque<String>()
    private val dayFmt = SimpleDateFormat("yyyyMMdd", Locale.US)
    private val timeFmt = SimpleDateFormat("HH:mm:ss.SSS", Locale.US)
    private var dir: File? = null

    fun init(context: Context) {
        synchronized(lock) {
            if (dir != null) return
            val base = context.getExternalFilesDir(null) ?: context.filesDir
            val d = File(base, "logs")
            if (!d.exists()) {
                d.mkdirs()
            }
            dir = d
        }
    }

    fun json(obj: JSONObject) {
        line(obj.toString())
    }

    fun line(text: String) {
        val now = Date()
        val stamped = timeFmt.format(now) + "\t" + text
        toLogcat(stamped)
        synchronized(lock) {
            ring.addLast(stamped)
            while (ring.size > 400) {
                ring.removeFirst()
            }
        }
        val d = dir
        if (d != null) {
            try {
                val f = File(d, "invo-events-" + dayFmt.format(now) + ".jsonl")
                f.appendText(stamped + "\n")
            } catch (t: Throwable) {
                Log.w(TAG, "file log failed: " + t)
            }
        }
    }

    /** Chopped because logcat truncates very long messages. */
    private fun toLogcat(s: String) {
        var i = 0
        while (i < s.length) {
            val end = if (i + 3000 < s.length) i + 3000 else s.length
            Log.i(TAG, s.substring(i, end))
            i = end
        }
    }

    fun logDir(): String = dir?.absolutePath ?: "(not initialised)"

    fun files(): List<File> {
        val d = dir ?: return emptyList()
        val list = d.listFiles { f -> f.name.startsWith("invo-events-") }
            ?: return emptyList()
        return list.sortedBy { it.name }
    }

    /** Last [n] lines of today's file (falls back to the in-memory ring). */
    fun tail(n: Int): String {
        val d = dir
        if (d != null) {
            try {
                val f = File(d, "invo-events-" + dayFmt.format(Date()) + ".jsonl")
                if (f.exists() && f.length() > 0) {
                    val all = f.readLines()
                    val from = if (all.size > n) all.size - n else 0
                    return all.subList(from, all.size).joinToString("\n")
                }
            } catch (t: Throwable) {
                Log.w(TAG, "tail failed: " + t)
            }
        }
        val fromRing = synchronized(lock) {
            if (ring.isEmpty()) {
                null
            } else {
                val all = ring.toList()
                val from = if (all.size > n) all.size - n else 0
                all.subList(from, all.size).joinToString("\n")
            }
        }
        return fromRing ?: "(no events yet)"
    }

    /** Everything on disk, for "copy all logs" / bug reports. */
    fun dumpAll(): String {
        val sb = StringBuilder()
        for (f in files()) {
            try {
                sb.append("=== ").append(f.name).append(" ===\n")
                sb.append(f.readText())
            } catch (t: Throwable) {
                sb.append("(could not read ").append(f.name).append(": ").append(t).append(")\n")
            }
        }
        if (sb.isEmpty()) sb.append("(empty)")
        return sb.toString()
    }
}
