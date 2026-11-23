package com.worldbrief.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.worldbrief.app.data.UserSettings
import com.worldbrief.app.ui.LocalAppContainer
import com.worldbrief.app.ui.navigation.WorldBriefRoot
import com.worldbrief.app.ui.theme.WorldBriefTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val container = (application as WorldBriefApp).container
        setContent {
            val settings by container.settingsRepository.settings.collectAsStateWithLifecycle(initialValue = UserSettings())
            CompositionLocalProvider(LocalAppContainer provides container) {
                WorldBriefTheme(themeMode = settings.themeMode, textScale = settings.textScale) {
                    WorldBriefRoot()
                }
            }
        }
    }
}
