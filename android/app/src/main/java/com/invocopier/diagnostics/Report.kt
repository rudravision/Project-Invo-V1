package com.invocopier.diagnostics

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Plain-language findings from the buttons, so that ONE tap on "8. COPY RESULT"
 * carries everything back. Sections are capped so the clipboard stays usable.
 *
 * Nothing here executes anything - it is a text buffer with a size limit.
 */
object Report {

    private const val MAX_SECTION = 5200

    private val lock = Any()
    private val sections = LinkedHashMap<String, String>()
    private val timeFmt = SimpleDateFormat("HH:mm:ss", Locale.US)

    fun set(section: String, body: String) {
        val clipped = if (body.length > MAX_SECTION) {
            body.substring(0, MAX_SECTION) + "\n.. (cut off - full text is saved in the app's dumps folder)"
        } else {
            body
        }
        synchronized(lock) {
            sections[section] = timeFmt.format(Date()) + "\n" + clipped
        }
    }

    fun section(name: String): String = synchronized(lock) { sections[name] ?: "(not run yet)" }

    fun combined(): String = synchronized(lock) {
        if (sections.isEmpty()) {
            "(nothing captured yet - press 11 or 12 first)"
        } else {
            sections.entries.joinToString("\n\n") { it.key + ":\n" + it.value }
        }
    }
}
