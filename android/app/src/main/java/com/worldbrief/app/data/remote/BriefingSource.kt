package com.worldbrief.app.data.remote

import android.content.res.AssetManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * Where briefings come from. The rest of the app only sees this interface, so
 * the provider (bundled demo data, the home backend, something else later) can
 * change without touching storage or UI.
 */
interface BriefingSource {
    /**
     * Returns briefings that are new or changed.
     * @param known briefing id to generatedAt for everything already stored.
     */
    suspend fun fetchNew(known: Map<String, String>): List<BriefingDto>
}

/** Demonstration briefings bundled in the APK under assets/demo. */
class AssetBriefingSource(private val assets: AssetManager) : BriefingSource {
    override suspend fun fetchNew(known: Map<String, String>): List<BriefingDto> = withContext(Dispatchers.IO) {
        assets.list(DIRECTORY).orEmpty()
            .filter { it.endsWith(".json") }
            .sorted()
            .map { name ->
                val text = assets.open("$DIRECTORY/$name").bufferedReader().use { it.readText() }
                BriefingJson.decodeFromString(BriefingDto.serializer(), text)
            }
            .filter { known[it.id] != it.generatedAt }
    }

    private companion object {
        const val DIRECTORY = "demo"
    }
}

/**
 * The World Brief backend (FastAPI on the desktop). Plain HttpURLConnection:
 * three GET requests do not justify a networking library yet.
 * The app never talks to LM Studio; only to this API.
 */
class HttpBriefingSource(baseUrl: String, private val token: String) : BriefingSource {
    private val base = baseUrl.trim().trimEnd('/')

    override suspend fun fetchNew(known: Map<String, String>): List<BriefingDto> = withContext(Dispatchers.IO) {
        val listing = BriefingJson.decodeFromString(BriefingListDto.serializer(), get("/v1/briefings"))
        listing.briefings
            .filter { ID_PATTERN.matches(it.id) && known[it.id] != it.generatedAt }
            .take(MAX_PER_SYNC)
            .map { BriefingJson.decodeFromString(BriefingDto.serializer(), get("/v1/briefings/${it.id}")) }
    }

    private fun get(path: String): String {
        val connection = URL(base + path).openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 8_000
            connection.readTimeout = 20_000
            connection.setRequestProperty("Authorization", "Bearer $token")
            connection.setRequestProperty("Accept", "application/json")
            val code = connection.responseCode
            if (code !in 200..299) {
                throw IOException(
                    when (code) {
                        401, 403 -> "The server rejected the access token."
                        404 -> "The server has no briefings at that address."
                        else -> "The server answered with HTTP $code."
                    }
                )
            }
            return connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private companion object {
        const val MAX_PER_SYNC = 30
        val ID_PATTERN = Regex("""\d{4}-\d{2}-\d{2}""")
    }
}
