package com.worldbrief.app.tts

import com.worldbrief.app.data.model.Briefing
import com.worldbrief.app.data.model.Section
import com.worldbrief.app.data.model.Story
import com.worldbrief.app.data.model.StoryStatus
import com.worldbrief.app.util.Dates

/** One spoken unit. Playback can pause, resume and skip between segments. */
data class NarrationSegment(val storyId: String?, val label: String, val text: String)

/** Turns briefings and stories into text for speech. Pure Kotlin, unit tested. */
object NarrationScript {

    fun forBriefing(briefing: Briefing): List<NarrationSegment> {
        val segments = mutableListOf<NarrationSegment>()
        val summary = briefing.summary
        val intro = buildString {
            append("${summary.title}. ${Dates.longDate(summary.date)}. ")
            if (summary.isDemo) append("This is demonstration content, not real news. ")
            append(summary.overview)
        }
        segments += NarrationSegment(null, "Introduction", intro)
        for (section in Section.entries) {
            val stories = briefing.storiesIn(section)
            stories.forEachIndexed { index, story ->
                val prefix = if (index == 0) "${section.title}. " else ""
                segments += NarrationSegment(story.id, section.title, prefix + storyText(story))
            }
        }
        return segments
    }

    fun forStory(story: Story): List<NarrationSegment> =
        listOf(NarrationSegment(story.id, story.section.title, storyText(story)))

    /**
     * Spoken form of a story. Status and uncertainty are read out, because a
     * listener cannot see the labels a reader sees.
     */
    fun storyText(story: Story): String = buildString {
        append(sentence(story.headline))
        when (story.status) {
            StoryStatus.PRELIMINARY -> append(" This report is preliminary.")
            StoryStatus.DISPUTED -> append(" Accounts of this are disputed.")
            StoryStatus.VERIFIED -> Unit
        }
        append(' ').append(sentence(story.summary))
        story.whyItMatters?.takeIf { it.isNotBlank() }?.let { append(" Why it matters: ").append(sentence(it)) }
        story.uncertainty?.takeIf { it.isNotBlank() }?.let { append(" What is uncertain: ").append(sentence(it)) }
    }

    private fun sentence(text: String): String {
        val trimmed = text.trim()
        return if (trimmed.isEmpty() || trimmed.last() in ".!?") trimmed else "$trimmed."
    }
}
