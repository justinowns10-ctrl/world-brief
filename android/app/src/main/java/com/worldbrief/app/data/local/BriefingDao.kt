package com.worldbrief.app.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

private const val BRIEFING_ROW =
    "SELECT b.*, " +
        "(SELECT COUNT(*) FROM stories s WHERE s.briefingId = b.id) AS storyCount, " +
        "EXISTS(SELECT 1 FROM bookmarks k WHERE k.kind = 'briefing' AND k.refId = b.id) AS isBookmarked " +
        "FROM briefings b"

private const val STORY_ROW =
    "SELECT s.*, " +
        "(SELECT COUNT(*) FROM articles a WHERE a.storyId = s.id) AS articleCount, " +
        "EXISTS(SELECT 1 FROM bookmarks k WHERE k.kind = 'story' AND k.refId = s.id) AS isBookmarked, " +
        "(SELECT b.isDemo FROM briefings b WHERE b.id = s.briefingId) AS isDemo " +
        "FROM stories s"

@Dao
abstract class BriefingDao {

    @Query("$BRIEFING_ROW ORDER BY b.date DESC")
    abstract fun observeBriefings(): Flow<List<BriefingRow>>

    @Query("$BRIEFING_ROW WHERE b.id = :id")
    abstract fun observeBriefing(id: String): Flow<BriefingRow?>

    @Query("SELECT id FROM briefings ORDER BY date DESC LIMIT 1")
    abstract fun observeLatestBriefingId(): Flow<String?>

    @Query("$BRIEFING_ROW WHERE b.id IN (SELECT refId FROM bookmarks WHERE kind = 'briefing') ORDER BY b.date DESC")
    abstract fun observeBookmarkedBriefings(): Flow<List<BriefingRow>>

    @Query("$STORY_ROW WHERE s.briefingId = :briefingId ORDER BY s.position")
    abstract fun observeStories(briefingId: String): Flow<List<StoryRow>>

    @Query("$STORY_ROW WHERE s.id = :id")
    abstract fun observeStory(id: String): Flow<StoryRow?>

    @Query("$STORY_ROW WHERE s.id IN (SELECT refId FROM bookmarks WHERE kind = 'story') ORDER BY s.firstReportedAt DESC")
    abstract fun observeBookmarkedStories(): Flow<List<StoryRow>>

    @Query(
        "$STORY_ROW WHERE s.headline LIKE '%' || :query || '%' OR s.summary LIKE '%' || :query || '%' " +
            "ORDER BY s.firstReportedAt DESC LIMIT 60"
    )
    abstract suspend fun searchStories(query: String): List<StoryRow>

    @Query(
        "SELECT a.*, src.name AS sourceName, src.country AS sourceCountry, src.type AS sourceType, " +
            "src.homepage AS sourceHomepage " +
            "FROM articles a LEFT JOIN sources src ON src.id = a.sourceId " +
            "WHERE a.storyId = :storyId ORDER BY a.position"
    )
    abstract fun observeArticles(storyId: String): Flow<List<ArticleRow>>

    @Query("SELECT id, generatedAt FROM briefings")
    abstract suspend fun briefingStamps(): List<BriefingStamp>

    @Upsert
    abstract suspend fun upsertBriefing(briefing: BriefingEntity)

    @Upsert
    abstract suspend fun upsertSources(sources: List<SourceEntity>)

    @Insert
    abstract suspend fun insertStories(stories: List<StoryEntity>)

    @Insert
    abstract suspend fun insertArticles(articles: List<ArticleEntity>)

    @Query("DELETE FROM stories WHERE briefingId = :briefingId")
    abstract suspend fun deleteStories(briefingId: String)

    @Query("DELETE FROM briefings WHERE isDemo = 1")
    abstract suspend fun deleteDemoBriefings()

    /** Replaces one briefing atomically. Deleting its stories cascades to their articles. */
    @Transaction
    open suspend fun replaceBriefing(
        briefing: BriefingEntity,
        sources: List<SourceEntity>,
        stories: List<StoryEntity>,
        articles: List<ArticleEntity>,
    ) {
        upsertBriefing(briefing)
        upsertSources(sources)
        deleteStories(briefing.id)
        insertStories(stories)
        insertArticles(articles)
    }

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    abstract suspend fun addBookmark(bookmark: BookmarkEntity)

    @Query("DELETE FROM bookmarks WHERE kind = :kind AND refId = :refId")
    abstract suspend fun removeBookmark(kind: String, refId: String)
}
