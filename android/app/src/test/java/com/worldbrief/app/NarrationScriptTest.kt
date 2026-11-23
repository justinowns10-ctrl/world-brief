package com.worldbrief.app

import com.worldbrief.app.data.model.Briefing
import com.worldbrief.app.data.model.BriefingSummary
import com.worldbrief.app.data.model.Section
import com.worldbrief.app.data.model.Story
import com.worldbrief.app.data.model.StoryStatus
import com.worldbrief.app.tts.NarrationScript
import com.worldbrief.app.util.Dates
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NarrationScriptTest {
    private fun story(id: String, section: Section, status: StoryStatus = StoryStatus.VERIFIED, uncertainty: String? = null) = Story(
        id = id, briefingId = "2026-11-23", section = section, headline = "Headline $id", countries = emptyList(),
        eventDate = null, firstReportedAt = "2026-11-23T06:00:00Z", status = status, importance = 3,
        isTopStory = false, summary = "Summary $id", whyItMatters = "Reason $id", context = null,
        uncertainty = uncertainty, independentSourceCount = 2, claims = emptyList(), articleCount = 2,
        isBookmarked = false, isDemo = true,
    )

    private val briefing = Briefing(
        BriefingSummary("2026-11-23", "2026-11-23", "2026-11-23T13:00:00Z", "World Brief", "Overview.", true, emptyList(), false, emptyList(), 3, false),
        listOf(story("b", Section.AFRICA), story("a", Section.EUROPE), story("c", Section.EUROPE, StoryStatus.DISPUTED, "Accounts differ")),
    )

    @Test
    fun briefingIsReadInSectionOrderWithOneIntroduction() {
        val segments = NarrationScript.forBriefing(briefing)
        assertEquals(listOf(null, "a", "c", "b"), segments.map { it.storyId })
        assertTrue(segments[0].text.contains("Monday, 23 November 2026"))
        assertTrue(segments[0].text.contains("demonstration"))
        assertTrue(segments[1].text.startsWith("Europe. "))
        assertFalse(segments[2].text.startsWith("Europe. "))
    }

    @Test
    fun statusAndUncertaintyAreSpoken() {
        val text = NarrationScript.storyText(story("c", Section.EUROPE, StoryStatus.DISPUTED, "Accounts differ"))
        assertTrue(text.contains("disputed"))
        assertTrue(text.contains("What is uncertain: Accounts differ."))
        assertTrue(text.contains("Why it matters: Reason c."))
    }

    @Test
    fun datesFormat() {
        assertEquals("23 Nov 2026", Dates.mediumDate("2026-11-23"))
        assertEquals("not-a-date", Dates.longDate("not-a-date"))
    }
}
