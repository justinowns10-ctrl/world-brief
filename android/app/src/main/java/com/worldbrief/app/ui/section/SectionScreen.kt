package com.worldbrief.app.ui.section

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.worldbrief.app.data.BriefingRepository
import com.worldbrief.app.data.model.Section
import com.worldbrief.app.data.model.Story
import com.worldbrief.app.ui.appViewModel
import com.worldbrief.app.ui.components.BackIcon
import com.worldbrief.app.ui.components.CenteredMessage
import com.worldbrief.app.ui.components.StoryListItem
import com.worldbrief.app.util.Dates
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn

class SectionViewModel(repository: BriefingRepository, briefingId: String, section: Section) : ViewModel() {
    /** null while loading. */
    val stories: StateFlow<List<Story>?> = repository.observeBriefing(briefingId)
        .map { briefing -> briefing?.storiesIn(section).orEmpty() }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SectionScreen(briefingId: String, section: Section, onBack: () -> Unit, onOpenStory: (String) -> Unit) {
    val viewModel = appViewModel(key = "section:$briefingId:${section.key}") {
        SectionViewModel(it.briefingRepository, briefingId, section)
    }
    val stories by viewModel.stories.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(section.title, style = MaterialTheme.typography.titleLarge)
                        Text(
                            Dates.mediumDate(briefingId),
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                },
                navigationIcon = { IconButton(onClick = onBack) { BackIcon() } },
            )
        },
    ) { padding ->
        val list = stories
        when {
            list == null -> Unit
            list.isEmpty() -> CenteredMessage(
                title = "No stories",
                body = "This edition has no story in ${section.title}.",
                padding = padding,
            )
            else -> LazyColumn(Modifier.fillMaxSize(), contentPadding = padding) {
                items(list, key = { it.id }) { story ->
                    StoryListItem(story, onClick = { onOpenStory(story.id) }, showSection = false)
                }
            }
        }
    }
}
