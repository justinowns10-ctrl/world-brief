package com.worldbrief.app.ui.saved

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
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
import com.worldbrief.app.data.model.BriefingSummary
import com.worldbrief.app.data.model.Story
import com.worldbrief.app.ui.appViewModel
import com.worldbrief.app.ui.archive.BriefingRowItem
import com.worldbrief.app.ui.components.CenteredMessage
import com.worldbrief.app.ui.components.GroupHeader
import com.worldbrief.app.ui.components.StoryListItem
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class SavedViewModel(private val repository: BriefingRepository) : ViewModel() {
    val stories: StateFlow<List<Story>> =
        repository.bookmarkedStories.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val briefings: StateFlow<List<BriefingSummary>> =
        repository.bookmarkedBriefings.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    fun removeBriefing(briefing: BriefingSummary) {
        viewModelScope.launch { repository.setBriefingBookmarked(briefing.id, false) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SavedScreen(onOpenBriefing: (String) -> Unit, onOpenStory: (String) -> Unit) {
    val viewModel = appViewModel { SavedViewModel(it.briefingRepository) }
    val stories by viewModel.stories.collectAsStateWithLifecycle()
    val briefings by viewModel.briefings.collectAsStateWithLifecycle()

    Scaffold(topBar = { TopAppBar(title = { Text("Saved", style = MaterialTheme.typography.titleLarge) }) }) { padding ->
        if (stories.isEmpty() && briefings.isEmpty()) {
            CenteredMessage(
                title = "Nothing saved",
                body = "Use the bookmark on a story or a date to keep it here.",
                padding = padding,
            )
        } else {
            LazyColumn(Modifier.fillMaxSize(), contentPadding = padding) {
                if (briefings.isNotEmpty()) {
                    item(key = "dates-header") { GroupHeader("Saved dates") }
                    items(briefings, key = { "briefing-${it.id}" }) { briefing ->
                        BriefingRowItem(
                            briefing = briefing,
                            onOpen = { onOpenBriefing(briefing.id) },
                            onToggleBookmark = { viewModel.removeBriefing(briefing) },
                        )
                    }
                }
                if (stories.isNotEmpty()) {
                    item(key = "stories-header") { GroupHeader("Saved stories") }
                    items(stories, key = { "story-${it.id}" }) { story ->
                        StoryListItem(story, onClick = { onOpenStory(story.id) })
                    }
                }
            }
        }
    }
}
