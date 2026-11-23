package com.worldbrief.app.ui.archive

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.worldbrief.app.R
import com.worldbrief.app.data.BriefingRepository
import com.worldbrief.app.data.model.BriefingSummary
import com.worldbrief.app.data.model.Story
import com.worldbrief.app.ui.appViewModel
import com.worldbrief.app.ui.components.ScreenPadding
import com.worldbrief.app.ui.components.StoryListItem
import com.worldbrief.app.ui.components.WbIcon
import com.worldbrief.app.util.Dates
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.mapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

@OptIn(FlowPreview::class, ExperimentalCoroutinesApi::class)
class ArchiveViewModel(private val repository: BriefingRepository) : ViewModel() {

    val briefings: StateFlow<List<BriefingSummary>> =
        repository.briefings.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    private val _query = MutableStateFlow("")
    val query: StateFlow<String> = _query.asStateFlow()

    /** null when there is no search in progress. */
    val results: StateFlow<List<Story>?> = _query
        .debounce(250)
        .mapLatest { text -> if (text.trim().length < 2) null else repository.search(text) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    fun setQuery(text: String) {
        _query.value = text
    }

    fun toggleBookmark(briefing: BriefingSummary) {
        viewModelScope.launch { repository.setBriefingBookmarked(briefing.id, !briefing.isBookmarked) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ArchiveScreen(onOpenBriefing: (String) -> Unit, onOpenStory: (String) -> Unit) {
    val viewModel = appViewModel { ArchiveViewModel(it.briefingRepository) }
    val briefings by viewModel.briefings.collectAsStateWithLifecycle()
    val query by viewModel.query.collectAsStateWithLifecycle()
    val results by viewModel.results.collectAsStateWithLifecycle()

    Scaffold(topBar = { TopAppBar(title = { Text("Archive", style = MaterialTheme.typography.titleLarge) }) }) { padding ->
        LazyColumn(Modifier.fillMaxSize(), contentPadding = padding) {
            item(key = "search") {
                OutlinedTextField(
                    value = query,
                    onValueChange = viewModel::setQuery,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = ScreenPadding, vertical = 8.dp),
                    singleLine = true,
                    label = { Text("Search downloaded briefings") },
                    leadingIcon = { WbIcon(R.drawable.ic_search, contentDescription = null) },
                    trailingIcon = {
                        if (query.isNotEmpty()) {
                            IconButton(onClick = { viewModel.setQuery("") }) {
                                WbIcon(R.drawable.ic_close, contentDescription = "Clear search")
                            }
                        }
                    },
                )
            }
            val found = results
            if (found != null) {
                if (found.isEmpty()) {
                    item(key = "none") { Hint("No story matches “${query.trim()}”.") }
                } else {
                    items(found, key = { "result-${it.id}" }) { story ->
                        StoryListItem(story, onClick = { onOpenStory(story.id) })
                    }
                }
            } else if (briefings.isEmpty()) {
                item(key = "empty") { Hint("No briefings have been downloaded yet.") }
            } else {
                items(briefings, key = { "briefing-${it.id}" }) { briefing ->
                    BriefingRowItem(
                        briefing = briefing,
                        onOpen = { onOpenBriefing(briefing.id) },
                        onToggleBookmark = { viewModel.toggleBookmark(briefing) },
                    )
                }
            }
        }
    }
}

@Composable
private fun Hint(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(horizontal = ScreenPadding, vertical = 20.dp),
    )
}

@Composable
fun BriefingRowItem(briefing: BriefingSummary, onOpen: () -> Unit, onToggleBookmark: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onOpen)
            .padding(start = ScreenPadding, end = 8.dp, top = 10.dp, bottom = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(Dates.longDate(briefing.date), style = MaterialTheme.typography.titleMedium)
            Text(
                "${briefing.storyCount} stor${if (briefing.storyCount == 1) "y" else "ies"}" +
                    if (briefing.isDemo) "  ·  demonstration" else "",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        IconButton(onClick = onToggleBookmark) {
            WbIcon(
                if (briefing.isBookmarked) R.drawable.ic_bookmark else R.drawable.ic_bookmark_border,
                contentDescription = if (briefing.isBookmarked) "Remove this date from saved" else "Save this date",
            )
        }
    }
    HorizontalDivider(Modifier.padding(horizontal = ScreenPadding), color = MaterialTheme.colorScheme.outlineVariant)
}
