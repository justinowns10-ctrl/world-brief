package com.worldbrief.app.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.map
import java.io.IOException

enum class ThemeMode { SYSTEM, LIGHT, DARK }

data class UserSettings(
    val themeMode: ThemeMode = ThemeMode.SYSTEM,
    val textScale: Float = 1f,
    val speechRate: Float = 1f,
    /** Base address of the World Brief backend, e.g. http://192.168.1.20:8000. Blank = demo data. */
    val serverUrl: String = "",
    val serverToken: String = "",
) {
    val usesServer: Boolean get() = serverUrl.isNotBlank()
}

private val Context.settingsStore: DataStore<Preferences> by preferencesDataStore(name = "settings")

/**
 * User preferences. Stored in the app's private storage. The access token is
 * kept here in plain form, which is acceptable for a home-network prototype;
 * move it to encrypted storage before the server is reachable from outside.
 */
class SettingsRepository(context: Context) {
    private val store = context.applicationContext.settingsStore

    val settings: Flow<UserSettings> = store.data
        .catch { error -> if (error is IOException) emit(emptyPreferences()) else throw error }
        .map { prefs ->
            UserSettings(
                themeMode = prefs[THEME]?.let { name -> ThemeMode.entries.firstOrNull { it.name == name } }
                    ?: ThemeMode.SYSTEM,
                textScale = prefs[TEXT_SCALE] ?: 1f,
                speechRate = prefs[SPEECH_RATE] ?: 1f,
                serverUrl = prefs[SERVER_URL].orEmpty(),
                serverToken = prefs[SERVER_TOKEN].orEmpty(),
            )
        }

    suspend fun setThemeMode(mode: ThemeMode) {
        store.edit { it[THEME] = mode.name }
    }

    suspend fun setTextScale(scale: Float) {
        store.edit { it[TEXT_SCALE] = scale.coerceIn(0.8f, 1.6f) }
    }

    suspend fun setSpeechRate(rate: Float) {
        store.edit { it[SPEECH_RATE] = rate.coerceIn(0.5f, 2.5f) }
    }

    suspend fun setServer(url: String, token: String) {
        store.edit {
            it[SERVER_URL] = url.trim().trimEnd('/')
            it[SERVER_TOKEN] = token.trim()
        }
    }

    private companion object {
        val THEME = stringPreferencesKey("theme_mode")
        val TEXT_SCALE = floatPreferencesKey("text_scale")
        val SPEECH_RATE = floatPreferencesKey("speech_rate")
        val SERVER_URL = stringPreferencesKey("server_url")
        val SERVER_TOKEN = stringPreferencesKey("server_token")
    }
}
