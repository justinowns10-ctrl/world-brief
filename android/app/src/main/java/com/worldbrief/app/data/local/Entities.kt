package com.worldbrief.app.data.local

import androidx.room.Embedded
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(tableName = "briefings")
data class BriefingEntity(
    @PrimaryKey val id: String,
    val date: String,
    val generatedAt: String,
    val title: String,
    val overview: String,
    val isDemo: Boolean,
    /** Coverage notes, one per line. */
    val coverageNotes: String,
    val isPartial: Boolean,
    /** Reasons the briefing is partial, one per line. */
    val partialReasons: String,
    val downloadedAt: Long,
)

@Entity(
    tableName = "stories",
    foreignKeys = [
        ForeignKey(
            entity = BriefingEntity::class,
            parentColumns = ["id"],
            childColumns = ["briefingId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("briefingId")],
)
data class StoryEntity(
    @PrimaryKey val id: String,
    val briefingId: String,
    val position: Int,
    val section: String,
    val headline: String,
    /** Country names joined with ", ". */
    val countries: String,
    val eventDate: String?,
    val firstReportedAt: String,
    val status: String,
    val importance: Int,
    val isTopStory: Boolean,
    val summary: String,
    val whyItMatters: String?,
    val context: String?,
    val uncertainty: String?,
    val independentSourceCount: Int,
    /** Claims with their evidence, stored as the contract's JSON array. */
    val claimsJson: String,
)

@Entity(tableName = "sources")
data class SourceEntity(
    @PrimaryKey val id: String,
    val name: String,
    val country: String?,
    val type: String?,
    val homepage: String?,
)

@Entity(
    tableName = "articles",
    foreignKeys = [
        ForeignKey(
            entity = StoryEntity::class,
            parentColumns = ["id"],
            childColumns = ["storyId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("storyId"), Index("sourceId")],
)
data class ArticleEntity(
    /** storyId + ":" + articleId. The same article id can recur across briefings. */
    @PrimaryKey val rowKey: String,
    val storyId: String,
    val position: Int,
    val articleId: String,
    val sourceId: String,
    val title: String,
    val url: String,
    val publishedAt: String,
    val role: String,
)

/** kind is "story" or "briefing". No foreign key, so bookmarks survive a re-sync. */
@Entity(tableName = "bookmarks", primaryKeys = ["kind", "refId"])
data class BookmarkEntity(
    val kind: String,
    val refId: String,
    val createdAt: Long,
)

data class BriefingRow(
    @Embedded val briefing: BriefingEntity,
    val storyCount: Int,
    val isBookmarked: Boolean,
)

data class StoryRow(
    @Embedded val story: StoryEntity,
    val articleCount: Int,
    val isBookmarked: Boolean,
    val isDemo: Boolean,
)

data class ArticleRow(
    @Embedded val article: ArticleEntity,
    val sourceName: String?,
    val sourceCountry: String?,
    val sourceType: String?,
    val sourceHomepage: String?,
)

data class BriefingStamp(val id: String, val generatedAt: String)
