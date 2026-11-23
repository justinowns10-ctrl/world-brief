package com.worldbrief.app.data.model

/** Whether a section is a geographic region or a subject area. */
enum class SectionKind { REGION, TOPIC }

/** Sections of a briefing. Keys match the `section` enum in contract/briefing.schema.json. */
enum class Section(val key: String, val title: String, val kind: SectionKind) {
    EUROPE("europe", "Europe", SectionKind.REGION),
    MIDDLE_EAST("middle_east", "Middle East", SectionKind.REGION),
    EAST_ASIA("east_asia", "East Asia", SectionKind.REGION),
    SOUTH_SOUTHEAST_ASIA("south_southeast_asia", "South & Southeast Asia", SectionKind.REGION),
    AFRICA("africa", "Africa", SectionKind.REGION),
    LATIN_AMERICA("latin_america", "Latin America", SectionKind.REGION),
    OTHER_REGIONS("other_regions", "Other Regions", SectionKind.REGION),
    SCIENCE("science", "Science", SectionKind.TOPIC),
    TECHNOLOGY("technology", "Technology", SectionKind.TOPIC),
    ENERGY("energy", "Energy", SectionKind.TOPIC),
    ECONOMICS("economics", "International Economics", SectionKind.TOPIC),
    HUMANITARIAN("humanitarian", "Humanitarian Affairs", SectionKind.TOPIC);

    companion object {
        fun fromKey(key: String): Section? = entries.firstOrNull { it.key == key }
        val regions: List<Section> get() = entries.filter { it.kind == SectionKind.REGION }
        val topics: List<Section> get() = entries.filter { it.kind == SectionKind.TOPIC }
    }
}

enum class StoryStatus(val key: String, val label: String) {
    VERIFIED("verified", "Verified"),
    PRELIMINARY("preliminary", "Preliminary"),
    DISPUTED("disputed", "Disputed");

    companion object {
        fun fromKey(key: String): StoryStatus = entries.firstOrNull { it.key == key } ?: PRELIMINARY
    }
}

enum class ClaimSupport { SUPPORTED, PARTIAL }

data class Evidence(val articleId: String, val quote: String)

data class Claim(
    val id: String,
    val text: String,
    val support: ClaimSupport,
    val note: String?,
    val evidence: List<Evidence>,
)

data class Source(
    val id: String,
    val name: String,
    val country: String?,
    val type: String?,
    val homepage: String?,
)

/** One outlet's report on a story. [publishedAt] is the reporting date, not the event date. */
data class ArticleRef(
    val id: String,
    val source: Source,
    val title: String,
    val url: String,
    val publishedAt: String,
    val role: String,
)

data class Story(
    val id: String,
    val briefingId: String,
    val section: Section,
    val headline: String,
    val countries: List<String>,
    /** Day the event happened, when the sources say; null when unknown. */
    val eventDate: String?,
    /** Earliest time any listed outlet reported it. */
    val firstReportedAt: String,
    val status: StoryStatus,
    val importance: Int,
    val isTopStory: Boolean,
    val summary: String,
    val whyItMatters: String?,
    val context: String?,
    val uncertainty: String?,
    val independentSourceCount: Int,
    val claims: List<Claim>,
    val articleCount: Int,
    val isBookmarked: Boolean,
    val isDemo: Boolean,
)

data class StoryDetail(val story: Story, val articles: List<ArticleRef>)

data class BriefingSummary(
    val id: String,
    val date: String,
    val generatedAt: String,
    val title: String,
    val overview: String,
    val isDemo: Boolean,
    val coverageNotes: List<String>,
    val storyCount: Int,
    val isBookmarked: Boolean,
)

data class Briefing(val summary: BriefingSummary, val stories: List<Story>) {
    val topStories: List<Story> get() = stories.filter { it.isTopStory }
    fun storiesIn(section: Section): List<Story> = stories.filter { it.section == section }
}
