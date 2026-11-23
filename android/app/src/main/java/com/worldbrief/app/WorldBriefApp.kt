package com.worldbrief.app

import android.app.Application
import android.content.Context
import androidx.room.Room
import com.worldbrief.app.data.BriefingRepository
import com.worldbrief.app.data.SettingsRepository
import com.worldbrief.app.data.local.WorldBriefDatabase
import com.worldbrief.app.data.remote.AssetBriefingSource
import com.worldbrief.app.tts.Narrator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

/**
 * Hand-written dependency container. The object graph is five objects; a DI
 * framework would add build steps without removing any code.
 */
class AppContainer(context: Context) {
    private val appContext = context.applicationContext
    val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    private val database: WorldBriefDatabase by lazy {
        Room.databaseBuilder(appContext, WorldBriefDatabase::class.java, "worldbrief.db").build()
    }

    val settingsRepository: SettingsRepository by lazy { SettingsRepository(appContext) }

    val briefingRepository: BriefingRepository by lazy {
        BriefingRepository(
            dao = database.briefingDao(),
            demoSource = AssetBriefingSource(appContext.assets),
            settings = settingsRepository,
        )
    }

    val narrator: Narrator by lazy { Narrator(appContext) }

    init {
        // Keep narration speed in step with the saved setting.
        appScope.launch {
            settingsRepository.settings.map { it.speechRate }.distinctUntilChanged().collect { narrator.setRate(it) }
        }
    }
}

class WorldBriefApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
