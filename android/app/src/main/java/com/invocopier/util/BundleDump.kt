package com.invocopier.util

import android.graphics.Bitmap
import android.graphics.drawable.Icon
import android.os.Bundle
import android.os.Parcelable
import org.json.JSONArray
import org.json.JSONObject

/**
 * Turns any notification Bundle into JSON so we can see EXACTLY what INVO puts
 * in its notifications (trade id, symbol, deep link, etc).
 *
 * Defensive by design: an unreadable key must never crash the listener.
 */
object BundleDump {

    private const val MAX_KEYS = 200
    private const val MAX_STRING = 1200

    fun toJson(b: Bundle?): JSONObject {
        val o = JSONObject()
        if (b == null) {
            o.put("_bundle", "null")
            return o
        }
        val keys: Set<String> = try {
            b.keySet()
        } catch (t: Throwable) {
            o.put("_keySetError", t.toString())
            return o
        }
        var i = 0
        for (k in keys.sorted()) {
            if (i >= MAX_KEYS) {
                o.put("_truncatedKeys", keys.size - i)
                break
            }
            i++
            val v = try {
                b.get(k)
            } catch (t: Throwable) {
                o.put(k, "<unreadable:" + t.javaClass.simpleName + ">")
                continue
            }
            o.put(k, render(v, 0))
        }
        return o
    }

    private fun render(v: Any?, depth: Int): Any {
        if (v == null) return JSONObject.NULL
        return when (v) {
            is Bundle -> if (depth >= 2) "<nested bundle>" else toJson(v)
            is Bitmap -> "Bitmap " + v.width + "x" + v.height
            is Icon -> "Icon"
            is Boolean -> v
            is Number -> v
            is CharSequence -> clip(v.toString())
            is String -> clip(v)
            is Array<*> -> JSONArray().apply {
                for (e in v) put(render(e, depth + 1))
            }
            is IntArray -> JSONArray().apply { for (e in v) put(e) }
            is LongArray -> JSONArray().apply { for (e in v) put(e) }
            is BooleanArray -> JSONArray().apply { for (e in v) put(e) }
            is Parcelable -> clip(v.javaClass.simpleName + " " + safe(v))
            else -> clip(v.javaClass.simpleName + " " + safe(v))
        }
    }

    private fun safe(v: Any): String = try {
        v.toString()
    } catch (t: Throwable) {
        "<toStringError>"
    }

    private fun clip(s: String): String {
        val flat = s.replace('\n', ' ').replace('\r', ' ')
        return if (flat.length > MAX_STRING) {
            flat.substring(0, MAX_STRING) + "...(len=" + flat.length + ")"
        } else {
            flat
        }
    }
}
