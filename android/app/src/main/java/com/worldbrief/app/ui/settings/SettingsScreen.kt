package com.worldbrief.app.ui.settings

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.worldbrief.app.data.BriefingRepository
import com.worldbrief.app.data.SettingsRepository
import com.worldbrief.app.data.SyncResult
import com.worldbrief.app.data.ThemeMode
import com.worldbrief.app.data.UserSettings
import com.worldbrief.app.ui.appViewModel
import com.worldbrief.app.ui.components.Overline
import com.worldbrief.app.ui.components.ScreenPadding
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class SyncUiState(val running: Boolean = false, val result: SyncResult? = null)

class SettingsViewModel(
    private val settingsRepository: SettingsRepository,
    private val briefingRepository: BriefingRepository,
) : ViewModel() {

    /** null until the saved settings have been read. */
    val settings: StateFlow<UserSettings?> =
        settingsRepository.settings.stateIn(viewModelScope, SharingStarted.Eagerly, null)

    private val _sync = MutableStateFlow(SyncUiState())
    val sync: StateFlow<SyncUiState> = _sync.asStateFlow()

    fun setTheme(mode: ThemeMode) = viewModelScope.launch { settingsRepository.setThemeMode(mode) }
    fun setTextScale(scale: Float) = viewModelScope.launch { settingsRepository.setTextScale(scale) }
    fun setSpeechRate(rate: Float) = viewModelScope.launch { settingsRepository.setSpeechRate(rate) }

    /** Saves the server details, then tries a sync so the user sees at once whether they work. */
    fun saveServerAndSync(url: String, token: String) {
        viewModelScope.launch {
            settingsRepository.setServer(url, token)
            _sync.value = SyncUiState(running = true)
            _sync.value = SyncUiState(result = briefingRepository.refresh())
        }
    }
}

private val textSizes = listOf(0.9f to "Small", 1f to "Standard", 1.15f to "Large", 1.3f to "Larger")
private val speeds = listOf(0.75f, 1f, 1.25f, 1.5f, 2f)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen() {
    val viewModel = appViewModel { SettingsViewModel(it.settingsRepository, it.briefingRepository) }
    val settings by viewModel.settings.collectAsStateWithLifecycle()
    val sync by viewModel.sync.collectAsStateWithLifecycle()

    Scaffold(topBar = { TopAppBar(title = { Text("Settings", style = MaterialTheme.typography.titleLarge) }) }) { padding ->
        val current = settings ?: return@Scaffold
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = ScreenPadding)
                .padding(bottom = 32.dp),
        ) {
            Group("Appearance")
            ChipRow(
                options = listOf(ThemeMode.SYSTEM to "Match phone", ThemeMode.LIGHT to "Light", ThemeMode.DARK to "Dark"),
                selected = current.themeMode,
                onSelect = { viewModel.setTheme(it) },
            )

            Group("Text size")
            ChipRow(options = textSizes, selected = current.textScale, onSelect = { viewModel.setTextScale(it) })

            Group("Narration speed")
            ChipRow(
                options = speeds.map { it to "${it.toString().removeSuffix(".0")}×" },
                selected = current.speechRate,
                onSelect = { viewModel.setSpeechRate(it) },
            )

            Group("World Brief server")
            ServerForm(current, sync, onSave = viewModel::saveServerAndSync)

            Group("About")
            Text(
                "World Brief 0.1.0, prototype. Briefings are prepared by your own server and stored on this phone, " +
                    "so downloaded editions stay readable when the server is off.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun Group(title: String) {
    Spacer(Modifier.height(24.dp))
    Overline(title, color = MaterialTheme.colorScheme.primary)
    Spacer(Modifier.height(8.dp))
}

@Composable
private fun <T> ChipRow(options: List<Pair<T, String>>, selected: T, onSelect: (T) -> Unit) {
    Row(
        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        options.forEach { (value, label) ->
            FilterChip(selected = value == selected, onClick = { onSelect(value) }, label = { Text(label) })
        }
    }
}

@Composable
private fun ServerForm(settings: UserSettings, sync: SyncUiState, onSave: (String, String) -> Unit) {
    var url by rememberSaveable(settings.serverUrl) { mutableStateOf(settings.serverUrl) }
    var token by rememberSaveable(settings.serverToken) { mutableStateOf(settings.serverToken) }

    Text(
        if (settings.usesServer) "Briefings come from your server." else "No server set. The app is showing demonstration data.",
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Spacer(Modifier.height(8.dp))
    OutlinedTextField(
        value = url,
        onValueChange = { url = it },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
        label = { Text("Server address") },
        placeholder = { Text("http://192.168.1.20:8000") },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
    )
    Spacer(Modifier.height(8.dp))
    OutlinedTextField(
        value = token,
        onValueChange = { token = it },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
        label = { Text("Access token") },
        visualTransformation = PasswordVisualTransformation(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
    )
    Spacer(Modifier.height(12.dp))
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Button(onClick = { onSave(url, token) }, enabled = !sync.running && url.isNotBlank()) {
            Text("Save and sync")
        }
        if (settings.usesServer) {
            OutlinedButton(onClick = { onSave("", "") }, enabled = !sync.running) { Text("Use demo data") }
        }
        if (sync.running) CircularProgressIndicator(modifier = Modifier.size(24.dp))
    }
    sync.result?.let { result ->
        Spacer(Modifier.height(8.dp))
        Text(
            result.message,
            style = MaterialTheme.typography.bodyMedium,
            color = if (result.ok) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.error,
        )
    }
    Spacer(Modifier.height(8.dp))
    Text(
        "Use the address of the computer running the World Brief backend. Plain http addresses work in debug builds only.",
        style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}
