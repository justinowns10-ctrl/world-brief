package com.worldbrief.app.ui.components

import androidx.annotation.DrawableRes
import androidx.compose.foundation.BorderStroke
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.worldbrief.app.R
import com.worldbrief.app.data.model.Story
import com.worldbrief.app.data.model.StoryStatus
import com.worldbrief.app.ui.theme.cautionColor
import com.worldbrief.app.ui.theme.statusColor

val ScreenPadding = 20.dp

@Composable
fun WbIcon(
    @DrawableRes id: Int,
    contentDescription: String?,
    modifier: Modifier = Modifier,
    tint: Color = LocalContentColor.current,
) {
    Icon(painter = painterResource(id), contentDescription = contentDescription, modifier = modifier, tint = tint)
}

/** Small capital label used above groups of content. */
@Composable
fun Overline(text: String, modifier: Modifier = Modifier, color: Color = MaterialTheme.colorScheme.onSurfaceVariant) {
    Text(text = text.uppercase(), style = MaterialTheme.typography.labelSmall, color = color, modifier = modifier)
}

@Composable
fun GroupHeader(text: String) {
    Column(Modifier.padding(start = ScreenPadding, end = ScreenPadding, top = 28.dp, bottom = 4.dp)) {
        Overline(text, color = MaterialTheme.colorScheme.primary)
        Spacer(Modifier.height(8.dp))
        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
    }
}

@Composable
fun StatusLabel(status: StoryStatus, modifier: Modifier = Modifier) {
    val color = statusColor(status)
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(4.dp),
        color = Color.Transparent,
        border = BorderStroke(1.dp, color),
    ) {
        Text(
            text = status.label.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            color = color,
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
        )
    }
}

@Composable
fun DemoBanner(modifier: Modifier = Modifier) {
    NoticeBox(
        title = "Demonstration data",
        body = "These stories are invented samples, not real news. Connect the app to your World Brief server in Settings to load real briefings.",
        modifier = modifier,
    )
}

@Composable
fun NoticeBox(title: String, body: String, modifier: Modifier = Modifier) {
    val color = cautionColor()
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(8.dp),
        color = Color.Transparent,
        border = BorderStroke(1.dp, color),
    ) {
        Column(Modifier.padding(12.dp)) {
            Overline(title, color = color)
            Spacer(Modifier.height(4.dp))
            Text(body, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

/** One story in a list: status, headline, opening of the summary, sourcing. */
@Composable
fun StoryListItem(story: Story, onClick: () -> Unit, showSection: Boolean = true) {
    Column(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = ScreenPadding, vertical = 14.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (showSection) Overline(story.section.title)
            StatusLabel(story.status)
        }
        Spacer(Modifier.height(6.dp))
        Text(story.headline, style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(4.dp))
        Text(
            story.summary,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            maxLines = 3,
            overflow = TextOverflow.Ellipsis,
        )
        Spacer(Modifier.height(6.dp))
        Text(sourcingLine(story), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    HorizontalDivider(Modifier.padding(horizontal = ScreenPadding), color = MaterialTheme.colorScheme.outlineVariant)
}

fun sourcingLine(story: Story): String {
    val independent = story.independentSourceCount
    val sources = when (independent) {
        0 -> "${story.articleCount} report${if (story.articleCount == 1) "" else "s"}"
        1 -> "1 independent source"
        else -> "$independent independent sources"
    }
    return if (story.countries.isEmpty()) sources else "${story.countries.joinToString(", ")}  ·  $sources"
}

@Composable
fun CenteredMessage(
    title: String,
    body: String,
    padding: PaddingValues = PaddingValues(0.dp),
    actionLabel: String? = null,
    onAction: (() -> Unit)? = null,
) {
    Box(Modifier.fillMaxSize().padding(padding).padding(32.dp), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(title, style = MaterialTheme.typography.titleLarge, textAlign = TextAlign.Center)
            Spacer(Modifier.height(8.dp))
            Text(
                body,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
            if (actionLabel != null && onAction != null) {
                Spacer(Modifier.height(16.dp))
                Button(onClick = onAction) { Text(actionLabel) }
            }
        }
    }
}

@Composable
fun BackIcon() {
    WbIcon(R.drawable.ic_arrow_back, contentDescription = "Back")
}

@Composable
fun IconLabel(@DrawableRes icon: Int, text: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        WbIcon(icon, contentDescription = null, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(8.dp))
        Text(text)
    }
}
