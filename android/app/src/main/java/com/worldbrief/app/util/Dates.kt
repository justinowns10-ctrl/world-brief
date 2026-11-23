package com.worldbrief.app.util

import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Date formatting. Content is English, so formats are fixed to English. */
object Dates {
    private val long = DateTimeFormatter.ofPattern("EEEE, d MMMM yyyy", Locale.ENGLISH)
    private val medium = DateTimeFormatter.ofPattern("d MMM yyyy", Locale.ENGLISH)
    private val dateTime = DateTimeFormatter.ofPattern("d MMM yyyy, HH:mm", Locale.ENGLISH)

    /** "2026-11-23" becomes "Monday, 23 November 2026". Falls back to the input. */
    fun longDate(isoDate: String): String =
        runCatching { LocalDate.parse(isoDate.take(10)).format(long) }.getOrDefault(isoDate)

    fun mediumDate(isoDate: String): String =
        runCatching { LocalDate.parse(isoDate.take(10)).format(medium) }.getOrDefault(isoDate)

    /** A UTC instant shown in the device's time zone. */
    fun localDateTime(isoInstant: String, zone: ZoneId = ZoneId.systemDefault()): String =
        runCatching { Instant.parse(isoInstant).atZone(zone).format(dateTime) }.getOrDefault(isoInstant)
}
