package com.worldbrief.app.data

import com.worldbrief.app.data.local.BookmarkEntity
import com.worldbrief.app.data.local.BriefingDao
import com.worldbrief.app.data.model.Briefing
import com.worldbrief.app.data.model.BriefingSummary
import com.worldbrief.app.data.model.Story
import com.worldbrief.app.data.model.StoryDetail
import com.worldbrief.app.data.remote.BriefingSource
import com.worldbrief.app.data.remote.HttpBriefingSource
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map

data class SyncResult(val ok: Boolean, val imported: Int, val message: String)

/**
 * Single source of truth for briefings. The UI reads only from the local
 * database; [refresh] copies new briefings into it from whichever source is
 * configured. If the source is unreachable, everything already stored stays
 * readable.
 */
class BriefingRepository(
    private val dao: BriefingDao,
    private val demoSource: BriefingSource,
    private val settings: SettingsRepository,
    private val serverSource: (url: String, token: String) -> BriefingSource = ::HttpBriefingSource,
) {
    val briefings: Flow<List<BriefingSummary>> =
        dao.observeBriefings().map { rows -> rows.map { it.toDomain() } }

    val bookmarkedBriefings: Flow<List<BriefingSummary>> =
        dao.observeBookmarkedBriefings().map { rows -> rows.map { it.toDomain() } }

    val bookmarkedStories: Flow<List<Story>> =
        dao.observeBookmarkedStories().map { rows -> rows.mapNotNull { it.toDomain() } }

    @OptIn(ExperimentalCoroutinesApi::class)
    fun observeLatestBriefing(): Flow<Briefing?> =
        dao.observeLatestBriefingId()
            .distinctUntilChanged()
            .flatMapLatest { id -> if (id == null) flowOf(null) else observeBriefing(id) }

    fun observeBriefing(id: String): Flow<Briefing?> =
        combine(dao.observeBriefing(id), dao.observeStories(id)) { briefing, stories ->
            briefing?.let { Briefing(it.toDomain(), stories.mapNotNull { row -> row.toDomain() }) }
        }

    fun observeStory(id: String): Flow<StoryDetail?> =
        combine(dao.observeStory(id), dao.observeArticles(id)) { story, articles ->
            story?.toDomain()?.let { StoryDetail(it, articles.map { row -> row.toDomain() }) }
        }

    suspend fun search(query: String): List<Story> =
        dao.searchStories(query.trim()).mapNotNull { it.toDomain() }

    suspend fun setStoryBookmarked(storyId: String, bookmarked: Boolean) = setBookmark("story", storyId, bookmarked)

    suspend fun setBriefingBookmarked(briefingId: String, bookmarked: Boolean) =
        setBookmark("briefing", briefingId, bookmarked)

    private suspend fun setBookmark(kind: String, refId: String, bookmarked: Boolean) {
        if (bookmarked) {
            dao.addBookmark(BookmarkEntity(kind, refId, System.currentTimeMillis()))
        } else {
            dao.removeBookmark(kind, refId)
        }
    }

    /** Downloads new or changed briefings. Never throws for network or data errors. */
    suspend fun refresh(): SyncResult {
        val current = settings.settings.first()
        val fromServer = current.usesServer
        val source = if (fromServer) serverSource(current.serverUrl, current.serverToken) else demoSource
        return try {
            val known = dao.briefingStamps().associate { it.id to it.generatedAt }
            val fetched = source.fetchNew(known)
            var imported = 0
            var rejected = 0
            for (dto in fetched) {
                if (validateBriefing(dto).isNotEmpty()) {
                    rejected++
                    continue
                }
                val records = dto.toRecords(System.currentTimeMillis())
                dao.replaceBriefing(records.briefing, records.sources, records.stories, records.articles)
                imported++
            }
            // Once real briefings arrive from the server, the bundled demo editions are removed.
            if (fromServer && imported > 0) dao.deleteDemoBriefings()
            val message = when {
                rejected > 0 -> "$imported new, $rejected rejected as malformed."
                imported == 0 -> "Up to date."
                imported == 1 -> "1 new briefing."
                else -> "$imported new briefings."
            }
            SyncResult(ok = rejected == 0, imported = imported, message = message)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            val reason = e.message?.takeIf { it.isNotBlank() } ?: e.javaClass.simpleName
            SyncResult(
                ok = false,
                imported = 0,
                message = if (fromServer) "Could not reach the server: $reason" else "Could not load briefings: $reason",
            )
        }
    }
}
