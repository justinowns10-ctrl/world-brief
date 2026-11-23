package com.worldbrief.app.ui.story

import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
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
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.worldbrief.app.R
import com.worldbrief.app.data.BriefingRepository
import com.worldbrief.app.data.model.ArticleRef
import com.worldbrief.app.data.model.Claim
import com.worldbrief.app.data.model.ClaimSupport
import com.worldbrief.app.data.model.Story
import com.worldbrief.app.data.model.StoryDetail
import com.worldbrief.app.tts.NarrationScript
import com.worldbrief.app.tts.Narrator
import com.worldbrief.app.ui.appViewModel
import com.worldbrief.app.ui.components.BackIcon
import com.worldbrief.app.ui.components.CenteredMessage
import com.worldbrief.app.ui.components.DemoBanner
import com.worldbrief.app.ui.components.NoticeBox
import com.worldbrief.app.ui.components.Overline
import com.worldbrief.app.ui.components.ScreenPadding
import com.worldbrief.app.ui.components.StatusLabel
import com.worldbrief.app.ui.components.WbIcon
import com.worldbrief.app.ui.theme.cautionColor
import com.worldbrief.app.util.Dates
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

sealed interface StoryUiState {
    data object Loading : StoryUiState
    data object Missing : StoryUiState
    data class Content(val detail: StoryDetail) : StoryUiState
}

class StoryViewModel(
    private val repository: BriefingRepository,
    private val narrator: Narrator,
    storyId: String,
) : ViewModel() {

    val uiState: StateFlow<StoryUiState> = repository.observeStory(storyId)
        .map { detail -> if (detail == null) StoryUiState.Missing else StoryUiState.Content(detail) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), StoryUiState.Loading)

    fun toggleBookmark(story: Story) {
        viewModelScope.launch { repository.setStoryBookmarked(story.id, !story.isBookmarked) }
    }

    fun listen(story: Story) {
        narrator.play(story.headline, NarrationScript.forStory(story))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StoryScreen(storyId: String, onBack: () -> Unit) {
    val viewModel = appViewModel(key = "story:$storyId") {
        StoryViewModel(it.briefingRepository, it.narrator, storyId)
    }
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val story = (state as? StoryUiState.Content)?.detail?.story

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Overline(story?.section?.title ?: "", color = MaterialTheme.colorScheme.onSurface) },
                navigationIcon = { IconButton(onClick = onBack) { BackIcon() } },
                actions = {
                    if (story != null) {
                        IconButton(onClick = { viewModel.listen(story) }) {
                            WbIcon(R.drawable.ic_listen, contentDescription = "Listen to this story")
                        }
                        IconButton(onClick = { viewModel.toggleBookmark(story) }) {
                            WbIcon(
                                if (story.isBookmarked) R.drawable.ic_bookmark else R.drawable.ic_bookmark_border,
                                contentDescription = if (story.isBookmarked) "Remove from saved" else "Save this story",
                            )
                        }
                    }
                },
            )
        },
    ) { padding ->
        when (val current = state) {
            StoryUiState.Loading -> Unit
            StoryUiState.Missing -> CenteredMessage(
                title = "Story not available",
                body = "It may belong to a briefing that is no longer stored on this phone.",
                padding = padding,
            )
            is StoryUiState.Content -> Column(
                Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = ScreenPadding)
                    .padding(bottom = 32.dp),
            ) {
                StoryBody(current.detail)
            }
        }
    }
}

@Composable
private fun StoryBody(detail: StoryDetail) {
    val story = detail.story
    val articlesById = detail.articles.associateBy { it.id }

    StatusLabel(story.status)
    Spacer(Modifier.height(10.dp))
    Text(story.headline, style = MaterialTheme.typography.headlineMedium)
    Spacer(Modifier.height(10.dp))
    // Two different dates, labelled: when it happened, and when it was reported.
    Text(
        buildString {
            append(if (story.eventDate != null) "Event date: ${Dates.mediumDate(story.eventDate)}" else "Event date: not stated by sources")
            append("\nFirst reported: ${Dates.localDateTime(story.firstReportedAt)}")
            if (story.countries.isNotEmpty()) append("\n${story.countries.joinToString(", ")}")
        },
        style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )

    if (story.isDemo) {
        Spacer(Modifier.height(16.dp))
        DemoBanner()
    }

    Spacer(Modifier.height(20.dp))
    Text(story.summary, style = MaterialTheme.typography.bodyLarge)

    story.uncertainty?.takeIf { it.isNotBlank() }?.let {
        Spacer(Modifier.height(20.dp))
        NoticeBox(title = "What is uncertain", body = it)
    }

    story.whyItMatters?.takeIf { it.isNotBlank() }?.let {
        Block(label = "Why it matters · analysis", text = it)
    }
    story.context?.takeIf { it.isNotBlank() }?.let {
        Block(label = "Background", text = it)
    }

    if (story.claims.isNotEmpty()) {
        SectionRule("Statement by statement")
        Text(
            "Each statement in the summary, with the passage it rests on.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        story.claims.forEach { claim -> ClaimItem(claim, articlesById) }
    }

    SectionRule("Original reporting")
    Text(
        if (story.independentSourceCount > 0) {
            "${detail.articles.size} report${if (detail.articles.size == 1) "" else "s"}, " +
                "${story.independentSourceCount} independent. Copies of one wire report count once."
        } else {
            "${detail.articles.size} report${if (detail.articles.size == 1) "" else "s"}."
        },
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    detail.articles.forEach { article -> ArticleItem(article) }

    Spacer(Modifier.height(24.dp))
    Text(
        "The summary, analysis and background on this page were written by software from the reports listed above. " +
            "The checks confirm that statements match those reports; they cannot confirm the reports are right.",
        style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
private fun SectionRule(label: String) {
    Spacer(Modifier.height(28.dp))
    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
    Spacer(Modifier.height(12.dp))
    Overline(label, color = MaterialTheme.colorScheme.primary)
    Spacer(Modifier.height(6.dp))
}

@Composable
private fun Block(label: String, text: String) {
    Spacer(Modifier.height(20.dp))
    Overline(label)
    Spacer(Modifier.height(4.dp))
    Text(text, style = MaterialTheme.typography.bodyLarge)
}

@Composable
private fun ClaimItem(claim: Claim, articlesById: Map<String, ArticleRef>) {
    Column(Modifier.padding(top = 14.dp)) {
        Text(claim.text, style = MaterialTheme.typography.bodyMedium)
        val caution = when (claim.support) {
            ClaimSupport.SUPPORTED -> null
            ClaimSupport.PARTIAL -> "Partly confirmed"
            ClaimSupport.UNCHECKED -> "Not checked"
        }
        if (caution != null) {
            Text(
                caution + (claim.note?.let { ": $it" } ?: ""),
                style = MaterialTheme.typography.labelMedium,
                color = cautionColor(),
                modifier = Modifier.padding(top = 2.dp),
            )
        }
        claim.evidence.forEach { evidence ->
            val sourceName = articlesById[evidence.articleId]?.source?.name ?: "Unknown source"
            Text(
                "“${evidence.quote}” — $sourceName",
                style = MaterialTheme.typography.bodyMedium,
                fontStyle = FontStyle.Italic,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(start = 12.dp, top = 4.dp),
            )
        }
    }
}

@Composable
private fun ArticleItem(article: ArticleRef) {
    val uriHandler = LocalUriHandler.current
    Row(
        Modifier
            .fillMaxWidth()
            .clickable { runCatching { uriHandler.openUri(article.url) } }
            .padding(vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(Modifier.weight(1f)) {
            val origin = listOfNotNull(
                article.source.name,
                article.source.country,
                when (article.role) {
                    "wire" -> "wire report"
                    "syndicated" -> "copy of another report"
                    else -> null
                },
            ).joinToString("  ·  ")
            Text(origin, style = MaterialTheme.typography.labelLarge)
            Text(article.title, style = MaterialTheme.typography.bodyMedium)
            Text(
                "Published ${Dates.localDateTime(article.publishedAt)}",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        WbIcon(
            R.drawable.ic_open_in_new,
            contentDescription = "Open the original report",
            modifier = Modifier.size(20.dp),
            tint = MaterialTheme.colorScheme.primary,
        )
    }
    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
}
