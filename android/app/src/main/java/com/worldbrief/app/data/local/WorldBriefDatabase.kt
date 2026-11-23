package com.worldbrief.app.data.local

import androidx.room.Database
import androidx.room.RoomDatabase

/**
 * Local cache of downloaded briefings. This is what keeps the app usable when
 * the desktop is off. Schema history is exported to app/schemas; any change to
 * the entities needs a version bump and a Migration.
 */
@Database(
    entities = [
        BriefingEntity::class,
        StoryEntity::class,
        SourceEntity::class,
        ArticleEntity::class,
        BookmarkEntity::class,
    ],
    version = 1,
    exportSchema = true,
)
abstract class WorldBriefDatabase : RoomDatabase() {
    abstract fun briefingDao(): BriefingDao
}
