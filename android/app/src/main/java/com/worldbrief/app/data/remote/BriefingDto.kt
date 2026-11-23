package com.worldbrief.app.data.remote

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * Wire format, version 1. Mirrors contract/briefing.schema.json.
 * Unknown fields are ignored so the backend can add fields without breaking the app.
 */
val BriefingJson: Json = Json {
    ignoreUnknownKeys = true
    coerceInputValues = true
}

const val SUPPORTED_SCHEMA_VERSION = 1

@Serializable
data class BriefingDto(
    val schemaVersion: Int,
    val id: String,
    val date: String,
    val generatedAt: String,
    val title: String,
    val overview: String = "",
    val isDemo: Boolean = false,
    val publication: PublicationDto? = null,
    val coverage: CoverageDto? = null,
    val sources: List<SourceDto> = emptyList(),
    val stories: List<StoryDto> = emptyList(),
)

/** Absent means complete. "failed" and "pending" describe runs, not briefings, and never appear here. */
@Serializable
data class PublicationDto(
    val state: String = "complete",
    val reasons: List<String> = emptyList(),
)

@Serializable
data class CoverageDto(
    val sectionsWithoutCoverage: List<String> = emptyList(),
    val notes: List<String> = emptyList(),
)

@Serializable
data class SourceDto(
    val id: String,
    val name: String,
    val country: String? = null,
    val type: String? = null,
    val homepage: String? = null,
)

@Serializable
data class StoryDto(
    val id: String,
    val section: String,
    val headline: String,
    val countries: List<String> = emptyList(),
    val eventDate: String? = null,
    val firstReportedAt: String,
    val status: String,
    val importance: Int = 3,
    val topStory: Boolean = false,
    val summary: String,
    val claims: List<ClaimDto> = emptyList(),
    val whyItMatters: String? = null,
    val context: String? = null,
    val uncertainty: String? = null,
    val independentSourceCount: Int = 0,
    val articles: List<ArticleDto> = emptyList(),
)

@Serializable
data class ClaimDto(
    val id: String,
    val text: String,
    val support: String,
    val note: String? = null,
    val evidence: List<EvidenceDto> = emptyList(),
)

@Serializable
data class EvidenceDto(val articleId: String, val quote: String)

@Serializable
data class ArticleDto(
    val id: String,
    val sourceId: String,
    val title: String,
    val url: String,
    val publishedAt: String,
    val role: String = "original",
)

/** Response of GET /v1/briefings. */
@Serializable
data class BriefingListDto(val briefings: List<BriefingListItemDto> = emptyList())

@Serializable
data class BriefingListItemDto(val id: String, val generatedAt: String)
