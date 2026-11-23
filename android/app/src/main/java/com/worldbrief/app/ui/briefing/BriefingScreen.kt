package com.worldbrief.app.ui.briefing

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.worldbrief.app.R
import com.worldbrief.app.data.BriefingRepository
import com.worldbrief.app.data.model.Briefing
import com.worldbrief.app.data.model.Section
import com.worldbrief.app.tts.NarrationScript
import com.worldbrief.app.tts.Narrator
import com.worldbrief.app.ui.appViewModel
import com.worldbrief.app.ui.components.BackIcon
import com.worldbrief.app.ui.components.CenteredMessage
import com.worldbrief.app.ui.components.DemoBanner
import com.worldbrief.app.ui.components.GroupHeader
import com.worldbrief.app.ui.components.IconLabel
import com.worldbrief.app.ui.components.NoticeBox
import com.worldbrief.app.ui.components.Overline
import com.worldbrief.app.ui.components.ScreenPadding
import com.worldbrief.app.ui.components.StoryListItem
import com.worldbrief.app.ui.components.WbIcon
import com.worldbrief.app.util.Dates
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

sealed interface BriefingUiState {
    data object Loading : BriefingUiState
    data class Empty(val message: String?) : BriefingUiState
    data class Content(val briefing: Briefing, val syncMessage: String?) : BriefingUiState
}

private data class SyncStatus(val running: Boolean = false, val message: String? = null, val failed: Boolean = false)

/** Shows one briefing: the latest when [briefingId] is null, otherwise an archived one. */
class BriefingViewModel(
    private val repository: BriefingRepository,
    private val narrator: Narrator,
    private val briefingId: String?,
) : ViewModel() {

    private val sync = MutableStateFlow(SyncStatus(running = briefingId == null))

    val uiState: StateFlow<BriefingUiState> = combine(
        if (briefingId == null) repository.observeLatestBriefing() else repository.observeBriefing(briefingId),
        sync,
    ) { briefing, status ->
        when {
            briefing != null -> BriefingUiState.Content(briefing, status.message.takeIf { status.failed })
            status.running -> BriefingUiState.Loading
            else -> BriefingUiState.Empty(status.message)
        }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), BriefingUiState.Loading)

    init {
        if (briefingId == null) refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            sync.value = SyncStatus(running = true)
            val result = repository.refresh()
            sync.value = SyncStatus(running = false, message = result.message, failed = !result.ok)
        }
    }

    fun listen(briefing: Briefing) {
        narrator.play("Briefing, ${Dates.mediumDate(briefing.summary.date)}", NarrationScript.forBriefing(briefing))
    }

    fun toggleBookmark(briefing: Briefing) {
        viewModelScope.launch {
            repository.setBriefingBookmarked(briefing.summary.id, !briefing.summary.isBookmarked)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BriefingScreen(
    briefingId: String?,
    onBack: (() -> Unit)?,
    onOpenSection: (briefingId: String, section: Section) -> Unit,
    onOpenStory: (storyId: String) -> Unit,
) {
    val viewModel = appViewModel(key = "briefing:${briefingId ?: "latest"}") {
        BriefingViewModel(it.briefingRepository, it.narrator, briefingId)
    }
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val content = state as? BriefingUiState.Content

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Overline("World Brief", color = MaterialTheme.colorScheme.onSurface) },
                navigationIcon = {
                    if (onBack != null) IconButton(onClick = onBack) { BackIcon() }
                },
                actions = {
                    if (content != null) {
                        IconButton(onClick = { viewModel.toggleBookmark(content.briefing) }) {
                            val saved = content.briefing.summary.isBookmarked
                            WbIcon(
                                if (saved) R.drawable.ic_bookmark else R.drawable.ic_bookmark_border,
                                contentDescription = if (saved) "Remove this date from saved" else "Save this date",
                            )
                        }
                    }
                    if (briefingId == null) {
                        IconButton(onClick = viewModel::refresh) {
                            WbIcon(R.drawable.ic_sync, contentDescription = "Check for a new briefing")
                        }
                    }
                },
            )
        },
    ) { padding ->
        when (val current = state) {
            BriefingUiState.Loading -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }

            is BriefingUiState.Empty -> CenteredMessage(
                title = "No briefing yet",
                body = current.message ?: "Nothing has been downloaded.",
                padding = padding,
                actionLabel = "Try again",
                onAction = viewModel::refresh,
            )

            is BriefingUiState.Content -> BriefingContent(
                briefing = current.briefing,
                syncMessage = current.syncMessage,
                padding = padding,
                onListen = { viewModel.listen(current.briefing) },
                onOpenSection = { onOpenSection(current.briefing.summary.id, it) },
                onOpenStory = onOpenStory,
            )
        }
    }
}

@Composable
private fun BriefingContent(
    briefing: Briefing,
    syncMessage: String?,
    padding: PaddingValues,
    onListen: () -> Unit,
    onOpenSection: (Section) -> Unit,
    onOpenStory: (String) -> Unit,
) {
    val summary = briefing.summary
    LazyColumn(Modifier.fillMaxSize(), contentPadding = padding) {
        item(key = "masthead") {
            Column(Modifier.padding(horizontal = ScreenPadding).padding(top = 4.dp)) {
                Text(Dates.longDate(summary.date), style = MaterialTheme.typography.headlineMedium)
                Spacer(Modifier.height(8.dp))
                Text(summary.overview, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.height(4.dp))
                Text(
                    "Prepared ${Dates.localDateTime(summary.generatedAt)}",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(16.dp))
                FilledTonalButton(onClick = onListen) { IconLabel(R.drawable.ic_listen, "Listen to this briefing") }
                if (syncMessage != null) {
                    Spacer(Modifier.height(12.dp))
                    Text(
                        "$syncMessage Showing the last downloaded briefing.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
                if (summary.isPartial) {
                    Spacer(Modifier.height(16.dp))
                    NoticeBox(
                        title = "Partial edition",
                        body = summary.partialReasons.joinToString(" ").ifBlank {
                            "The run that produced this briefing did not finish everything it set out to do."
                        },
                    )
                }
                if (summary.isDemo) {
                    Spacer(Modifier.height(16.dp))
                    DemoBanner()
                }
            }
        }

        val top = briefing.topStories
        if (top.isNotEmpty()) {
            item(key = "top-header") { GroupHeader("Leading developments") }
            items(top, key = { "top-${it.id}" }) { story ->
                StoryListItem(story, onClick = { onOpenStory(story.id) })
            }
        }

        item(key = "regions-header") { GroupHeader("Regions") }
        items(Section.regions, key = { "section-${it.key}" }) { section ->
            SectionRow(section, briefing, onOpenSection)
        }

        item(key = "topics-header") { GroupHeader("Topics") }
        items(Section.topics, key = { "section-${it.key}" }) { section ->
            SectionRow(section, briefing, onOpenSection)
        }

        if (summary.coverageNotes.isNotEmpty() && !summary.isDemo) {
            item(key = "coverage") {
                Column(Modifier.padding(horizontal = ScreenPadding, vertical = 20.dp)) {
                    Overline("About this edition")
                    Spacer(Modifier.height(6.dp))
                    summary.coverageNotes.forEach { note ->
                        Text(note, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
        item(key = "end") { Spacer(Modifier.height(24.dp)) }
    }
}

@Composable
private fun SectionRow(section: Section, briefing: Briefing, onOpen: (Section) -> Unit) {
    val stories = briefing.storiesIn(section)
    val enabled = stories.isNotEmpty()
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(enabled = enabled) { onOpen(section) }
            .padding(horizontal = ScreenPadding, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                section.title,
                style = MaterialTheme.typography.titleMedium,
                color = if (enabled) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                // An empty section is stated, not hidden: silence about a region is information too.
                stories.firstOrNull()?.headline ?: "No story selected in this edition",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        if (enabled) {
            Text("${stories.size}", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
            WbIcon(R.drawable.ic_chevron_right, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
    HorizontalDivider(Modifier.padding(horizontal = ScreenPadding), color = MaterialTheme.colorScheme.outlineVariant)
}
