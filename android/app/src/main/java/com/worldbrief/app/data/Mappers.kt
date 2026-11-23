package com.worldbrief.app.data

import com.worldbrief.app.data.local.ArticleEntity
import com.worldbrief.app.data.local.ArticleRow
import com.worldbrief.app.data.local.BriefingEntity
import com.worldbrief.app.data.local.BriefingRow
import com.worldbrief.app.data.local.SourceEntity
import com.worldbrief.app.data.local.StoryEntity
import com.worldbrief.app.data.local.StoryRow
import com.worldbrief.app.data.model.ArticleRef
import com.worldbrief.app.data.model.BriefingSummary
import com.worldbrief.app.data.model.Claim
import com.worldbrief.app.data.model.ClaimSupport
import com.worldbrief.app.data.model.Evidence
import com.worldbrief.app.data.model.Section
import com.worldbrief.app.data.model.Source
import com.worldbrief.app.data.model.Story
import com.worldbrief.app.data.model.StoryStatus
import com.worldbrief.app.data.remote.BriefingDto
import com.worldbrief.app.data.remote.BriefingJson
import com.worldbrief.app.data.remote.ClaimDto
import com.worldbrief.app.data.remote.SUPPORTED_SCHEMA_VERSION
import kotlinx.serialization.builtins.ListSerializer

private val claimListSerializer = ListSerializer(ClaimDto.serializer())

/**
 * Checks a downloaded briefing before it is stored. Returns the problems found;
 * an empty list means it can be stored. The backend validates too, but the app
 * does not trust the network.
 */
fun validateBriefing(dto: BriefingDto): List<String> {
    val problems = mutableListOf<String>()
    if (dto.schemaVersion != SUPPORTED_SCHEMA_VERSION) {
        problems += "unsupported schema version ${dto.schemaVersion}"
        return problems
    }
    if (dto.id.isBlank()) problems += "briefing has no id"
    val sourceIds = dto.sources.map { it.id }.toSet()
    val storyIds = mutableSetOf<String>()
    for (story in dto.stories) {
        if (!storyIds.add(story.id)) problems += "duplicate story id ${story.id}"
        if (story.articles.isEmpty()) problems += "story ${story.id} lists no articles"
        val articleIds = story.articles.map { it.id }.toSet()
        for (article in story.articles) {
            if (article.sourceId !in sourceIds) problems += "story ${story.id}: unknown source ${article.sourceId}"
            if (!article.url.startsWith("https://") && !article.url.startsWith("http://")) {
                problems += "story ${story.id}: article ${article.id} has no usable link"
            }
        }
        for (claim in story.claims) {
            if (claim.evidence.isEmpty()) problems += "story ${story.id}: claim ${claim.id} has no evidence"
            for (evidence in claim.evidence) {
                if (evidence.articleId !in articleIds) {
                    problems += "story ${story.id}: claim ${claim.id} cites unknown article ${evidence.articleId}"
                }
            }
        }
    }
    return problems
}

data class BriefingRecords(
    val briefing: BriefingEntity,
    val sources: List<SourceEntity>,
    val stories: List<StoryEntity>,
    val articles: List<ArticleEntity>,
)

/** Stories in a section this app version does not know are skipped, not guessed. */
fun BriefingDto.toRecords(nowMillis: Long): BriefingRecords {
    val known = stories.filter { Section.fromKey(it.section) != null }
    return BriefingRecords(
        briefing = BriefingEntity(
            id = id,
            date = date,
            generatedAt = generatedAt,
            title = title,
            overview = overview,
            isDemo = isDemo,
            coverageNotes = coverage?.notes.orEmpty().joinToString("\n"),
            isPartial = publication?.state == "partial",
            partialReasons = publication?.reasons.orEmpty().joinToString("\n"),
            downloadedAt = nowMillis,
        ),
        sources = sources.map { SourceEntity(it.id, it.name, it.country, it.type, it.homepage) },
        stories = known.mapIndexed { index, s ->
            StoryEntity(
                id = s.id,
                briefingId = id,
                position = index,
                section = s.section,
                headline = s.headline,
                countries = s.countries.joinToString(", "),
                eventDate = s.eventDate,
                firstReportedAt = s.firstReportedAt,
                status = s.status,
                importance = s.importance,
                isTopStory = s.topStory,
                summary = s.summary,
                whyItMatters = s.whyItMatters,
                context = s.context,
                uncertainty = s.uncertainty,
                independentSourceCount = s.independentSourceCount,
                claimsJson = BriefingJson.encodeToString(claimListSerializer, s.claims),
            )
        },
        articles = known.flatMap { s ->
            s.articles.mapIndexed { index, a ->
                ArticleEntity(
                    rowKey = "${s.id}:${a.id}",
                    storyId = s.id,
                    position = index,
                    articleId = a.id,
                    sourceId = a.sourceId,
                    title = a.title,
                    url = a.url,
                    publishedAt = a.publishedAt,
                    role = a.role,
                )
            }
        },
    )
}

fun BriefingRow.toDomain(): BriefingSummary = BriefingSummary(
    id = briefing.id,
    date = briefing.date,
    generatedAt = briefing.generatedAt,
    title = briefing.title,
    overview = briefing.overview,
    isDemo = briefing.isDemo,
    coverageNotes = briefing.coverageNotes.split("\n").filter { it.isNotBlank() },
    isPartial = briefing.isPartial,
    partialReasons = briefing.partialReasons.split("\n").filter { it.isNotBlank() },
    storyCount = storyCount,
    isBookmarked = isBookmarked,
)

fun StoryRow.toDomain(): Story? {
    val section = Section.fromKey(story.section) ?: return null
    val claims = runCatching { BriefingJson.decodeFromString(claimListSerializer, story.claimsJson) }
        .getOrDefault(emptyList())
        .map { c ->
            Claim(
                id = c.id,
                text = c.text,
                // Anything unrecognised is shown as the weaker "partial", never as supported.
                support = when (c.support) {
                    "supported" -> ClaimSupport.SUPPORTED
                    "unchecked" -> ClaimSupport.UNCHECKED
                    else -> ClaimSupport.PARTIAL
                },
                note = c.note,
                evidence = c.evidence.map { Evidence(it.articleId, it.quote) },
            )
        }
    return Story(
        id = story.id,
        briefingId = story.briefingId,
        section = section,
        headline = story.headline,
        countries = story.countries.split(", ").filter { it.isNotBlank() },
        eventDate = story.eventDate,
        firstReportedAt = story.firstReportedAt,
        status = StoryStatus.fromKey(story.status),
        importance = story.importance,
        isTopStory = story.isTopStory,
        summary = story.summary,
        whyItMatters = story.whyItMatters,
        context = story.context,
        uncertainty = story.uncertainty,
        independentSourceCount = story.independentSourceCount,
        claims = claims,
        articleCount = articleCount,
        isBookmarked = isBookmarked,
        isDemo = isDemo,
    )
}

fun ArticleRow.toDomain(): ArticleRef = ArticleRef(
    id = article.articleId,
    source = Source(
        id = article.sourceId,
        name = sourceName ?: article.sourceId,
        country = sourceCountry,
        type = sourceType,
        homepage = sourceHomepage,
    ),
    title = article.title,
    url = article.url,
    publishedAt = article.publishedAt,
    role = article.role,
)
