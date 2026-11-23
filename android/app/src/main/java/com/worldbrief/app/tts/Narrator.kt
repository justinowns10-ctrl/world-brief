package com.worldbrief.app.tts

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import java.util.Locale

data class NarrationState(
    val status: Status = Status.IDLE,
    val title: String = "",
    val segments: List<NarrationSegment> = emptyList(),
    val index: Int = 0,
    val rate: Float = 1f,
    val error: String? = null,
) {
    enum class Status { IDLE, PREPARING, PLAYING, PAUSED, ERROR }

    val current: NarrationSegment? get() = segments.getOrNull(index)
    val isActive: Boolean get() = status != Status.IDLE
}

/**
 * Speaks briefings with the device's text-to-speech engine. Works offline once
 * a voice is installed.
 *
 * Android's TextToSpeech cannot pause mid-sentence, so narration is cut into
 * segments (one per story). Pause stops the current segment; resume starts that
 * segment again from its beginning.
 *
 * Not yet done: playback from a foreground service with lock-screen controls
 * and audio focus. Until then Android may stop playback if it reclaims the app
 * while the screen is off.
 */
class Narrator(context: Context) {
    private val appContext = context.applicationContext
    private val mainHandler = Handler(Looper.getMainLooper())
    private val _state = MutableStateFlow(NarrationState())
    val state: StateFlow<NarrationState> = _state.asStateFlow()

    private var engine: TextToSpeech? = null
    private var engineReady = false
    private var activeUtterance: String? = null
    private var counter = 0

    private val listener = object : UtteranceProgressListener() {
        override fun onStart(utteranceId: String?) = Unit

        override fun onDone(utteranceId: String?) = onUtteranceDone(utteranceId)

        @Deprecated("Deprecated in Java")
        override fun onError(utteranceId: String?) = onUtteranceError(utteranceId)

        override fun onError(utteranceId: String?, errorCode: Int) = onUtteranceError(utteranceId)
    }

    @Synchronized
    fun play(title: String, segments: List<NarrationSegment>, startIndex: Int = 0) {
        if (segments.isEmpty()) return
        activeUtterance = null
        engine?.stop()
        _state.value = NarrationState(
            status = NarrationState.Status.PREPARING,
            title = title,
            segments = segments,
            index = startIndex.coerceIn(0, segments.lastIndex),
            rate = _state.value.rate,
        )
        if (engineReady) speakCurrent() else startEngine()
    }

    @Synchronized
    fun pause() {
        if (_state.value.status != NarrationState.Status.PLAYING) return
        activeUtterance = null
        engine?.stop()
        _state.update { it.copy(status = NarrationState.Status.PAUSED) }
    }

    @Synchronized
    fun resume() {
        if (_state.value.status != NarrationState.Status.PAUSED) return
        if (engineReady) speakCurrent() else startEngine()
    }

    fun togglePlayPause() {
        when (_state.value.status) {
            NarrationState.Status.PLAYING -> pause()
            NarrationState.Status.PAUSED -> resume()
            else -> Unit
        }
    }

    @Synchronized
    fun skip(delta: Int) {
        val current = _state.value
        if (!current.isActive || current.segments.isEmpty()) return
        val target = (current.index + delta).coerceIn(0, current.segments.lastIndex)
        if (target == current.index) return
        _state.value = current.copy(index = target)
        if (current.status == NarrationState.Status.PLAYING) speakCurrent()
    }

    /** Takes effect immediately; the current segment restarts at the new speed. */
    @Synchronized
    fun setRate(rate: Float) {
        val clamped = rate.coerceIn(0.5f, 2.5f)
        if (clamped == _state.value.rate) return
        _state.update { it.copy(rate = clamped) }
        if (_state.value.status == NarrationState.Status.PLAYING) speakCurrent()
    }

    @Synchronized
    fun stop() {
        activeUtterance = null
        engine?.stop()
        reset()
    }

    private fun startEngine() {
        if (engine != null) return // already starting
        // The callback is posted so that it always runs after `engine` is assigned.
        engine = TextToSpeech(appContext) { status -> mainHandler.post { onEngineInit(status) } }
    }

    @Synchronized
    private fun onEngineInit(status: Int) {
        val tts = engine
        if (status != TextToSpeech.SUCCESS || tts == null) {
            tts?.shutdown()
            engine = null
            fail("Text-to-speech is not available on this device.")
            return
        }
        val language = tts.setLanguage(Locale.US)
        if (language == TextToSpeech.LANG_MISSING_DATA || language == TextToSpeech.LANG_NOT_SUPPORTED) {
            tts.shutdown()
            engine = null
            fail("No English voice is installed. Add one in the phone's text-to-speech settings.")
            return
        }
        tts.setOnUtteranceProgressListener(listener)
        engineReady = true
        val current = _state.value.status
        if (current == NarrationState.Status.PREPARING || current == NarrationState.Status.PAUSED) speakCurrent()
    }

    private fun speakCurrent() {
        val tts = engine ?: return
        val current = _state.value
        val segment = current.current
        if (segment == null) {
            reset()
            return
        }
        tts.setSpeechRate(current.rate)
        val id = "wb-${++counter}"
        activeUtterance = id
        val text = segment.text.take(TextToSpeech.getMaxSpeechInputLength() - 1)
        val result = tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, id)
        if (result == TextToSpeech.ERROR) {
            activeUtterance = null
            fail("Playback could not start.")
        } else {
            _state.update { it.copy(status = NarrationState.Status.PLAYING, error = null) }
        }
    }

    @Synchronized
    private fun onUtteranceDone(utteranceId: String?) {
        // Segments interrupted by pause, skip or stop report a stale id and are ignored.
        if (utteranceId == null || utteranceId != activeUtterance) return
        activeUtterance = null
        val current = _state.value
        if (current.index >= current.segments.lastIndex) {
            reset()
        } else {
            _state.value = current.copy(index = current.index + 1)
            speakCurrent()
        }
    }

    @Synchronized
    private fun onUtteranceError(utteranceId: String?) {
        if (utteranceId == null || utteranceId != activeUtterance) return
        activeUtterance = null
        fail("The speech engine reported an error.")
    }

    private fun reset() {
        _state.value = NarrationState(rate = _state.value.rate)
    }

    private fun fail(message: String) {
        _state.update { it.copy(status = NarrationState.Status.ERROR, error = message) }
    }
}
