package com.worldbrief.app

import com.worldbrief.app.data.model.Section
import com.worldbrief.app.data.remote.BriefingDto
import com.worldbrief.app.data.remote.BriefingJson
import com.worldbrief.app.data.toRecords
import com.worldbrief.app.data.validateBriefing
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The bundled demo briefings are copies of contract/examples. If these parse
 * and validate, the app's reading of the contract matches the backend's.
 */
class DemoDataTest {
    private fun demoFiles(): List<File> =
        File("src/main/assets/demo").listFiles { file -> file.extension == "json" }.orEmpty().sortedBy { it.name }

    private fun load(file: File): BriefingDto =
        BriefingJson.decodeFromString(BriefingDto.serializer(), file.readText())

    @Test
    fun demoBriefingsParseAndValidate() {
        val files = demoFiles()
        assertTrue("no demo briefings found", files.isNotEmpty())
        for (file in files) {
            val dto = load(file)
            assertEquals("${file.name}: ${validateBriefing(dto)}", emptyList<String>(), validateBriefing(dto))
            assertTrue(dto.isDemo)
            for (story in dto.stories) assertNotNull("unknown section ${story.section}", Section.fromKey(story.section))
        }
    }

    @Test
    fun recordsKeepEveryStoryAndArticle() {
        val dto = load(demoFiles().last())
        val records = dto.toRecords(nowMillis = 0)
        assertEquals(dto.stories.size, records.stories.size)
        assertEquals(dto.stories.sumOf { it.articles.size }, records.articles.size)
        assertEquals(records.articles.size, records.articles.map { it.rowKey }.toSet().size)
    }

    @Test
    fun claimCitingUnknownArticleIsRejected() {
        val dto = load(demoFiles().last())
        val first = dto.stories.first()
        val brokenClaim = first.claims.first().let { claim ->
            claim.copy(evidence = claim.evidence.map { it.copy(articleId = "does-not-exist") })
        }
        val broken = dto.copy(stories = listOf(first.copy(claims = listOf(brokenClaim))) + dto.stories.drop(1))
        assertTrue(validateBriefing(broken).any { "unknown article" in it })
    }

    @Test
    fun unsupportedSchemaVersionIsRejected() {
        val dto = load(demoFiles().last()).copy(schemaVersion = 99)
        assertTrue(validateBriefing(dto).isNotEmpty())
    }
}
