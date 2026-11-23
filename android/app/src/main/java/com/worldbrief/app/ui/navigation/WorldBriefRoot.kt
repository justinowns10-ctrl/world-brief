package com.worldbrief.app.ui.navigation

import androidx.annotation.DrawableRes
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.worldbrief.app.R
import com.worldbrief.app.data.model.Section
import com.worldbrief.app.tts.NarrationState
import com.worldbrief.app.ui.LocalAppContainer
import com.worldbrief.app.ui.archive.ArchiveScreen
import com.worldbrief.app.ui.briefing.BriefingScreen
import com.worldbrief.app.ui.components.CenteredMessage
import com.worldbrief.app.ui.components.WbIcon
import com.worldbrief.app.ui.saved.SavedScreen
import com.worldbrief.app.ui.section.SectionScreen
import com.worldbrief.app.ui.settings.SettingsScreen
import com.worldbrief.app.ui.story.StoryScreen

/** Routes. Ids are dates and slugs, so they are safe inside a route path. */
object Routes {
    const val TODAY = "today"
    const val ARCHIVE = "archive"
    const val SAVED = "saved"
    const val SETTINGS = "settings"
    const val BRIEFING = "briefing/{briefingId}"
    const val SECTION = "section/{briefingId}/{sectionKey}"
    const val STORY = "story/{storyId}"

    fun briefing(id: String) = "briefing/$id"
    fun section(briefingId: String, section: Section) = "section/$briefingId/${section.key}"
    fun story(id: String) = "story/$id"
}

private data class TopLevel(val route: String, val label: String, @DrawableRes val icon: Int)

private val topLevel = listOf(
    TopLevel(Routes.TODAY, "Today", R.drawable.ic_today),
    TopLevel(Routes.ARCHIVE, "Archive", R.drawable.ic_archive),
    TopLevel(Routes.SAVED, "Saved", R.drawable.ic_bookmark_border),
    TopLevel(Routes.SETTINGS, "Settings", R.drawable.ic_settings),
)

@Composable
fun WorldBriefRoot() {
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val destination = backStackEntry?.destination

    Scaffold(
        // Each screen draws its own top bar and handles the status bar itself.
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = {
            Column {
                MiniPlayer(onOpenStory = { navController.navigate(Routes.story(it)) })
                NavigationBar {
                    topLevel.forEach { item ->
                        NavigationBarItem(
                            selected = destination?.hierarchy?.any { it.route == item.route } == true,
                            onClick = { navController.navigateTopLevel(item.route) },
                            icon = { WbIcon(item.icon, contentDescription = null) },
                            label = { Text(item.label) },
                        )
                    }
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = Routes.TODAY,
            modifier = Modifier.padding(padding).consumeWindowInsets(padding),
        ) {
            val openStory: (String) -> Unit = { navController.navigate(Routes.story(it)) }
            val openSection: (String, Section) -> Unit = { id, section ->
                navController.navigate(Routes.section(id, section))
            }
            val openBriefing: (String) -> Unit = { navController.navigate(Routes.briefing(it)) }
            val back: () -> Unit = { navController.popBackStack() }

            composable(Routes.TODAY) {
                BriefingScreen(briefingId = null, onBack = null, onOpenSection = openSection, onOpenStory = openStory)
            }
            composable(Routes.ARCHIVE) {
                ArchiveScreen(onOpenBriefing = openBriefing, onOpenStory = openStory)
            }
            composable(Routes.SAVED) {
                SavedScreen(onOpenBriefing = openBriefing, onOpenStory = openStory)
            }
            composable(Routes.SETTINGS) {
                SettingsScreen()
            }
            composable(Routes.BRIEFING) { entry ->
                val id = entry.arguments?.getString("briefingId")
                if (id == null) {
                    CenteredMessage("Not found", "That briefing could not be opened.")
                } else {
                    BriefingScreen(briefingId = id, onBack = back, onOpenSection = openSection, onOpenStory = openStory)
                }
            }
            composable(Routes.SECTION) { entry ->
                val id = entry.arguments?.getString("briefingId")
                val section = entry.arguments?.getString("sectionKey")?.let { Section.fromKey(it) }
                if (id == null || section == null) {
                    CenteredMessage("Not found", "That section could not be opened.")
                } else {
                    SectionScreen(briefingId = id, section = section, onBack = back, onOpenStory = openStory)
                }
            }
            composable(Routes.STORY) { entry ->
                val id = entry.arguments?.getString("storyId")
                if (id == null) {
                    CenteredMessage("Not found", "That story could not be opened.")
                } else {
                    StoryScreen(storyId = id, onBack = back)
                }
            }
        }
    }
}

private fun NavHostController.navigateTopLevel(route: String) {
    navigate(route) {
        popUpTo(graph.findStartDestination().id) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}

/** Playback bar shown above the navigation bar whenever narration is active. */
@Composable
private fun MiniPlayer(onOpenStory: (String) -> Unit) {
    val narrator = LocalAppContainer.current.narrator
    val state by narrator.state.collectAsStateWithLifecycle()
    if (!state.isActive) return

    Surface(color = MaterialTheme.colorScheme.surfaceContainerHigh) {
        Column {
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            if (state.segments.size > 1) {
                LinearProgressIndicator(
                    progress = { (state.index + 1).toFloat() / state.segments.size },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                val storyId = state.current?.storyId
                Column(
                    Modifier
                        .weight(1f)
                        .clickable(enabled = storyId != null) { storyId?.let(onOpenStory) }
                        .padding(vertical = 8.dp)
                ) {
                    Text(state.title, style = MaterialTheme.typography.labelLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    val detail = when (state.status) {
                        NarrationState.Status.ERROR -> state.error ?: "Playback failed."
                        NarrationState.Status.PREPARING -> "Starting the voice…"
                        else -> state.current?.let { "${it.label}  ·  ${state.index + 1} of ${state.segments.size}" }.orEmpty()
                    }
                    Text(
                        detail,
                        style = MaterialTheme.typography.labelMedium,
                        color = if (state.status == NarrationState.Status.ERROR) {
                            MaterialTheme.colorScheme.error
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        },
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (state.status != NarrationState.Status.ERROR) {
                    if (state.segments.size > 1) {
                        IconButton(onClick = { narrator.skip(-1) }) {
                            WbIcon(R.drawable.ic_skip_previous, contentDescription = "Previous story")
                        }
                    }
                    val playing = state.status == NarrationState.Status.PLAYING
                    IconButton(onClick = narrator::togglePlayPause) {
                        WbIcon(
                            if (playing) R.drawable.ic_pause else R.drawable.ic_play,
                            contentDescription = if (playing) "Pause" else "Resume",
                        )
                    }
                    if (state.segments.size > 1) {
                        IconButton(onClick = { narrator.skip(1) }) {
                            WbIcon(R.drawable.ic_skip_next, contentDescription = "Next story")
                        }
                    }
                }
                IconButton(onClick = narrator::stop) {
                    WbIcon(R.drawable.ic_close, contentDescription = "Stop listening")
                }
            }
        }
    }
}
