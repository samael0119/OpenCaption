package dev.opencaption.opencaption

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioAttributes
import android.media.AudioPlaybackCaptureConfiguration
import android.media.AudioRecordingConfiguration
import android.media.MediaRecorder
import android.media.audiofx.NoiseSuppressor
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.os.PowerManager
import android.provider.Settings
import android.view.WindowManager
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.common.model.DownloadConditions
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateLanguage
import com.google.mlkit.nl.translate.TranslateRemoteModel
import com.google.mlkit.nl.translate.Translation
import com.google.mlkit.nl.translate.Translator
import com.google.mlkit.nl.translate.TranslatorOptions
import java.io.File
import java.util.concurrent.PriorityBlockingQueue
import java.util.concurrent.ScheduledThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.locks.ReentrantReadWriteLock
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong
import kotlin.concurrent.read
import kotlin.concurrent.write
import kotlin.math.sqrt

private const val E2E_WATCHDOG_MS = 15_000L
private val hintUnsafeCharacters = Regex("[\\u0000-\\u001f\\u007f\\u200b-\\u200f\\u202a-\\u202e<>`{}]")
private val hintPromptInjection = Regex(
    "<\\s*/?\\s*(?:system|user|assistant|developer|think|analysis)\\s*>|" +
        "(?:ignore|disregard|forget)\\s+(?:all\\s+)?(?:the\\s+)?" +
        "(?:previous|prior|above|these)?\\s*(?:instructions?|rules?|prompts?)|" +
        "(?:system|developer|assistant|user)\\s*(?:message|prompt|instruction)\\s*[:：]|" +
        "(?:output|respond|answer)\\s+(?:only|as|in\\s+(?:json|xml|yaml))\\b|" +
        "(?:jailbreak|prompt\\s+injection)",
    RegexOption.IGNORE_CASE,
)

/** User context is data, never a second instruction channel. */
private fun sanitizeHintData(value: String): String {
    val normalized = value
        .replace(hintUnsafeCharacters, " ")
        .replace(Regex("\\s+"), " ")
        .trim()
    if (normalized.isEmpty() || hintPromptInjection.containsMatchIn(normalized)) return ""
    return normalized.take(240).trimEnd()
}

class CaptionEngine(private val activity: MainActivity, private val events: EngineEvents) : EngineHost {
    private val main = Handler(Looper.getMainLooper())
    private val native = NativeEngine()
    private val e2eBackend = FlavorBackendFactory.create(activity)
    private val sessionLog = SessionLog(activity)
    private val recording = AtomicBoolean(false)
    private val serial = AtomicLong()
    private val queue = PriorityBlockingQueue<Job>()
    private val engineLock = ReentrantReadWriteLock()
    private val cancelledIds = java.util.concurrent.ConcurrentHashMap.newKeySet<String>()
    private val preemptedIds = java.util.concurrent.ConcurrentHashMap.newKeySet<String>()
    private val discardE2eOnPause = AtomicBoolean(false)
    @Volatile private var epoch = 0L
    @Volatile private var accepting = false
    @Volatile private var prepared = false
    @Volatile private var activeJob: Job? = null
    @Volatile private var recorder: AudioRecord? = null
    private var noiseSuppressor: NoiseSuppressor? = null
    private var captureThread: Thread? = null
    private var config: EngineConfig? = null
    @Volatile private var liveE2eHints = ""
    private var translator: Translator? = null
    private var permission: ((Result<Boolean>) -> Unit)? = null
    private val mlModel = TranslateRemoteModel.Builder(TranslateLanguage.CHINESE).build()
    private val modelManager = RemoteModelManager.getInstance()
    private val audioManager = activity.getSystemService(AudioManager::class.java)
    private val powerManager = activity.getSystemService(PowerManager::class.java)
    private var thermalListener: PowerManager.OnThermalStatusChangedListener? = null
    private val worker: Thread
    private val watchdog = ScheduledThreadPoolExecutor(1) { runnable ->
        Thread(runnable, "caption-watchdog").apply { isDaemon = true }
    }.apply { removeOnCancelPolicy = true }
    private val loadSampler = RuntimeLoadSampler()
    private val micCallback = object : AudioManager.AudioRecordingCallback() {
        override fun onRecordingConfigChanged(configs: MutableList<AudioRecordingConfiguration>) {
            if (Build.VERSION.SDK_INT >= 29 && recording.get() && configs.any {
                it.clientAudioSessionId == recorder?.audioSessionId && it.isClientSilenced
            }) interrupt("microphone_interrupted")
        }
    }

    private class Job(val order: Long, val priority: Int, val requiresAccepting: Boolean,
        val id: String, val epoch: Long, val run: () -> Unit, val dropped: () -> Unit) : Comparable<Job> {
        override fun compareTo(other: Job): Int {
            val byPriority = priority.compareTo(other.priority)
            return if (byPriority != 0) byPriority else order.compareTo(other.order)
        }
    }

    init {
        audioManager.registerAudioRecordingCallback(micCallback, main)
        if (Build.VERSION.SDK_INT >= 29) {
            thermalListener = PowerManager.OnThermalStatusChangedListener { status ->
                if (status >= PowerManager.THERMAL_STATUS_SEVERE) interrupt("thermal")
            }.also { powerManager.addThermalStatusListener(it) }
        }
        worker = Thread({
            while (true) {
                val job = try { queue.take() } catch (_: InterruptedException) { break }
                if ((job.epoch >= 0 && (job.epoch != epoch || (job.requiresAccepting && !accepting))) ||
                    cancelledIds.remove(job.id)) { job.dropped(); continue }
                activeJob = job
                native.setCancelled(false)
                native.setTranslationCancelled(false)
                try {
                    job.run()
                } catch (error: Throwable) {
                    sessionLog.write("worker_failure job=${job.id}", error)
                    report("worker_failure")
                } finally { activeJob = null }
            }
        }, "caption-inference").apply { isDaemon = true; start() }
    }
    private fun post(action: () -> Unit) { main.post(action) }
    private fun error(code: String) = FlutterError(code, code, null)
    private fun report(code: String, ms: Long = 0) { val e = epoch; post { events.diagnostic(e, code, ms) {} } }
    private fun enqueue(id: String, e: Long, priority: Int, requiresAccepting: Boolean = true,
        dropped: () -> Unit = {}, run: () -> Unit) {
        queue.put(Job(serial.incrementAndGet(), priority, requiresAccepting, id, e, run, dropped))
    }
    override fun requestMicrophone(callback: (Result<Boolean>) -> Unit) {
        sessionLog.begin()
        sessionLog.write("start_requested")
        if (activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            sessionLog.write("microphone_permission_already_granted")
            callback(Result.success(true)); return
        }
        if (permission != null) { callback(Result.failure(error("permission_pending"))); return }
        permission = callback
        activity.requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 701)
    }
    fun permissionResult(granted: Boolean) { permission?.invoke(Result.success(granted)); permission = null }
    fun lifecycle(state: String) { sessionLog.write("lifecycle_$state recording=${recording.get()}") }
    fun trace(text: String) { sessionLog.write(text) }

    /** Update only the bounded E2E hint string; the next window observes it. */
    override fun updateHints(hints: String) {
        liveE2eHints = sanitizeHintData(hints)
    }

    override fun prepare(config: EngineConfig, callback: (Result<Unit>) -> Unit) {
        if (recording.get()) { callback(Result.failure(error("recording"))); return }
        accepting = false
        val runtime = Runtime.getRuntime()
        sessionLog.write(
            "prepare_queued mode=${config.mode} threads=${config.threads} " +
                "java_heap_used=${runtime.totalMemory() - runtime.freeMemory()} java_heap_max=${runtime.maxMemory()}",
        )
        sessionLog.write(
            "models asr=${File(config.asrPath).name}:${File(config.asrPath).length()} " +
                "vad=${File(config.vadPath).name}:${File(config.vadPath).length()} " +
                "translation=${File(config.translationPath).name}:${if (config.translationPath.isEmpty()) 0 else File(config.translationPath).length()}",
        )
        enqueue("prepare", -1, priority = 0, requiresAccepting = false, dropped = {
            sessionLog.write("prepare_timeout")
            post { callback(Result.failure(error("prepare_timeout"))) }
        }) {
            try {
                sessionLog.write("prepare_begin")
                captureThread?.join()
                engineLock.write {
                    native.release(); e2eBackend?.close(); translator?.close(); translator = null
                    prepared = false
                    this.config = config
                    liveE2eHints = sanitizeHintData(config.names)
                    if (config.mode == "e2e") {
                        checkNotNull(e2eBackend) { "e2e_backend_missing" }.also {
                            it.load(config.asrPath, config.threads.toInt())
                            // Make the context ready before capture starts. The
                            // first audio window will use this system hint; no
                            // extra dummy inference is performed.
                            it.setHints(liveE2eHints)
                            sessionLog.write("e2e_context_ready chars=${liveE2eHints.length} ignored=${if (liveE2eHints.isEmpty()) 1 else 0}")
                            sessionLog.write("e2e_runtime ${it.runtimeInfo()}")
                        }
                    } else {
                        native.load(
                            config.asrPath,
                            config.vadPath,
                            if (config.mode == "qwen") config.translationPath else "",
                            config.threads.toInt(),
                            sessionLog.fd,
                        )
                    }
                    if (config.mode == "mlKit") {
                        sessionLog.write("mlkit_prepare_begin")
                        if (!Tasks.await(modelManager.isModelDownloaded(mlModel))) throw IllegalStateException("mlkit_missing")
                        translator = Translation.getClient(TranslatorOptions.Builder()
                            .setSourceLanguage(TranslateLanguage.ENGLISH).setTargetLanguage(TranslateLanguage.CHINESE).build())
                        sessionLog.write("mlkit_prepare_ok")
                    }
                }
                prepared = true
                sessionLog.write("prepare_ok")
                post { callback(Result.success(Unit)) }
            } catch (error: Throwable) {
                sessionLog.write("prepare_failed", error)
                engineLock.write { native.release(); translator?.close(); translator = null }
                post { callback(Result.failure(error("model_prepare_failed"))) }
            }
        }
    }

    override fun start(epoch: Long) {
        sessionLog.write("audio_start_begin epoch=$epoch")
        check(activity.foreground || PlaybackCaptionService.active) { "app_not_foreground" }
        check(prepared) { "models_not_prepared" }
        check(!recording.get() && captureThread?.isAlive != true) { "capture_still_stopping" }
        this.epoch = epoch; accepting = true; cancelledIds.clear(); discardE2eOnPause.set(false)
        val minimum = AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        sessionLog.write("audio_min_buffer=$minimum")
        check(minimum > 0) { "audio_format_unsupported" }
        val e2e = config?.mode == "e2e"
        val audioSource = if (e2e) MediaRecorder.AudioSource.VOICE_RECOGNITION else MediaRecorder.AudioSource.MIC
        val builder = AudioRecord.Builder()
        val playback = activity.playbackSelected
        if (playback) {
            check(Build.VERSION.SDK_INT >= 29) { "playback_unsupported" }
            val projection = checkNotNull(PlaybackCaptionService.instance?.projection) { "playback_authorization_required" }
            builder.setAudioPlaybackCaptureConfig(AudioPlaybackCaptureConfiguration.Builder(projection)
                .addMatchingUsage(AudioAttributes.USAGE_MEDIA).addMatchingUsage(AudioAttributes.USAGE_GAME)
                .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN).excludeUid(android.os.Process.myUid()).build())
        } else builder.setAudioSource(audioSource)
        val record = builder
            .setAudioFormat(AudioFormat.Builder().setSampleRate(16000).setChannelMask(AudioFormat.CHANNEL_IN_MONO)
                .setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
            .setBufferSizeInBytes(maxOf(minimum * 2, 4096)).build()
        if (record.state != AudioRecord.STATE_INITIALIZED || record.sampleRate != 16000) {
            record.release(); throw IllegalStateException("audio_format_unsupported")
        }
        recorder = record
        noiseSuppressor = if (!playback && e2e && NoiseSuppressor.isAvailable()) {
            try {
                NoiseSuppressor.create(record.audioSessionId)?.also { it.enabled = true }
            } catch (error: Throwable) {
                sessionLog.write("noise_suppressor_failed", error)
                null
            }
        } else null
        try {
            native.resetVad(); record.startRecording()
            check(record.recordingState == AudioRecord.RECORDSTATE_RECORDING) { "audio_start_failed" }
            recording.set(true)
        } catch (failure: Exception) {
            noiseSuppressor?.release(); noiseSuppressor=null
            record.release(); recorder=null
            throw failure
        }
        sessionLog.write("audio_start_ok source=${if (playback) "PLAYBACK_CAPTURE" else if (e2e) "VOICE_RECOGNITION" else "MIC"} session=${record.audioSessionId} sample_rate=${record.sampleRate} noise_suppressor=${noiseSuppressor?.enabled == true} background=${PlaybackCaptionService.active}")
        PlaybackCaptionService.instance?.update("正在采集本设备音频…")
        activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        captureThread = Thread({ capture(record, epoch) }, "caption-audio").also { it.start() }
    }

    private fun capture(record: AudioRecord, e: Long) {
        android.os.Process.setThreadPriority(android.os.Process.THREAD_PRIORITY_AUDIO)
        val pcm = ShortArray(320)
        val buffer = AudioBuffer()
        val e2e = config?.mode == "e2e"
        // Gemma consumes fixed continuous windows and does its own speech
        // decision. Avoid allocating/running the cascade-only gate and
        // pause segmenter on that path; RMS below is only a level meter.
        val segmenter = if (e2e) null else EnergySegmenter()
        val signalGate = if (e2e) null else AudioSignalGate()
        var window = 0L; var meterAt = 0L
        var e2eStart = 0L
        var levelLogAt = 0L; var peakRms = 0.0
        var firstFrame = true
        var silentFrames = 0
        sessionLog.write("capture_begin segmentation=${if (e2e) "fixed_windows" else "pause_boundaries"} frame_ms=20 silence_ms=600 minimum_ms=800 maximum_ms=5000 e2e_window_ms=5000 e2e_overlap_ms=0")
        try {
            while (recording.get()) {
                var count = 0
                while (count < pcm.size && recording.get()) {
                    val n = record.read(pcm, count, pcm.size - count, AudioRecord.READ_BLOCKING)
                    if (n <= 0) { if (recording.get()) throw IllegalStateException("audio_read"); break }
                    count += n
                }
                if (count != pcm.size || !recording.get()) break
                val floats = FloatArray(count) { pcm[it] / 32768f }
                buffer.append(floats)
                // Calculate a cheap level meter for the UI. The Gemma path
                // does not use it as a speech gate; fixed windows are always
                // submitted unless the PCM is exactly zero.
                val rms = sqrt(floats.sumOf { it.toDouble() * it } / count).coerceIn(0.0, 1.0)
                silentFrames = if (pcm.all { it == 0.toShort() }) silentFrames + 1 else 0
                if (activity.playbackSelected && silentFrames > 0 && silentFrames % 500 == 0) {
                    sessionLog.write("playback_zero_audio duration_ms=${silentFrames * 20} possible_policy_block=true")
                    post { PlaybackCaptionService.instance?.update("未收到播放音频：请开始播放；目标 App 也可能禁止音频采集。") }
                }
                val gatedSpeech = signalGate?.update(floats, rms) ?: true
                val update = segmenter?.update(buffer.total, buffer.oldest, count, rms, gatedSpeech)
                // E2E capture is continuous; the gate is meter-only and must
                // never make the UI claim that recording has stopped.
                val speech = if (e2e) true else update?.speech ?: gatedSpeech
                peakRms = maxOf(peakRms, rms)
                if (firstFrame) {
                    firstFrame = false
                    sessionLog.write("capture_first_frame_ok rms=$rms")
                }
                if (buffer.total - levelLogAt >= 16000) {
                    levelLogAt = buffer.total
                    sessionLog.write("audio_level peak_rms=$peakRms speech=$speech")
                    peakRms = 0.0
                }
                if (buffer.total - meterAt >= 3200) {
                    meterAt = buffer.total
                    val ms = buffer.total / 16
                    post { events.activity(e, rms, speech, ms) {} }
                }
                update?.boundary?.let { boundary ->
                    val snapshot = buffer.slice(boundary.start, boundary.end)
                    val begin = boundary.start / 16; val end = boundary.end / 16
                    window++
                    sessionLog.write(
                        "segment_submit window=$window reason=${boundary.reason} samples=${snapshot.size}",
                    )
                    submitAsr(e, window, 1, begin, end, snapshot, true)
                }
                // End-to-end speech models are themselves capable of rejecting
                // non-speech. Fixed windows avoid an energy gate permanently
                // suppressing commentary whose level resembles a crowd bed.
                if (e2e && buffer.total - e2eStart >= 80000) {
                    val endSample = e2eStart + 80000
                    val snapshot = buffer.slice(e2eStart, endSample)
                    window++
                    if (isExactDigitalSilence(snapshot)) {
                        sessionLog.write("segment_skip window=$window reason=e2e_exact_zero samples=${snapshot.size}")
                        report("e2e_skipped_exact_zero", snapshot.size.toLong())
                    } else {
                        sessionLog.write("segment_submit window=$window reason=e2e_fixed samples=${snapshot.size}")
                        submitEndToEnd(e, window, e2eStart / 16, endSample / 16, snapshot)
                    }
                    e2eStart = endSample
                }
            }
        } catch (error: Throwable) {
            sessionLog.write("capture_failed", error)
            if (recording.get()) post { interrupt("microphone_unavailable") }
        } finally {
            if (config?.mode == "e2e" && !discardE2eOnPause.get() && buffer.total - e2eStart >= 16000) {
                val snapshot = buffer.slice(maxOf(buffer.oldest, e2eStart), buffer.total)
                if (snapshot.size >= 16000) {
                    window++
                    if (isExactDigitalSilence(snapshot)) {
                        sessionLog.write("segment_skip window=$window reason=e2e_exact_zero_flush samples=${snapshot.size}")
                        report("e2e_skipped_exact_zero", snapshot.size.toLong())
                    } else {
                        sessionLog.write("segment_submit window=$window reason=e2e_flush samples=${snapshot.size}")
                        submitEndToEnd(e, window, e2eStart / 16, buffer.total / 16, snapshot)
                    }
                }
            }
            try { record.stop() } catch (_: Throwable) {}
            noiseSuppressor?.release(); noiseSuppressor = null
            record.release(); recorder = null
            sessionLog.write("capture_stopped")
        }
    }

    private fun submitAsr(e: Long, window: Long, revision: Long, start: Long, end: Long,
        pcm: FloatArray, finalResult: Boolean) {
        queue.filter { it.priority == 4 && it.epoch == e }.forEach { queue.remove(it) }
        if (queue.count { it.epoch == e && it.id.startsWith("asr-") } >= 8) {
            post { events.gap(e, start, end) {} }; return
        }
        activeJob?.takeIf { it.priority == 3 }?.let {
            preemptedIds.add(it.id)
            native.setTranslationCancelled(true)
            sessionLog.write("translation_preempt_requested id=${it.id}")
        }
        enqueue("asr-$window-$revision", e, priority = if (finalResult) 1 else 4,
            dropped = { if (finalResult) post { events.gap(e, start, end) {} } }) {
            val began = SystemClock.elapsedRealtime()
            var outputCharacters = 0
            try {
                sessionLog.write("asr_begin samples=${pcm.size} final=$finalResult")
                val text = engineLock.read { native.transcribe(pcm, config?.names ?: "") }
                val noSpeech = native.lastNoSpeechProbability()
                val tokenProbability = native.lastAverageTokenProbability()
                sessionLog.write("asr_confidence no_speech=$noSpeech avg_token=$tokenProbability")
                if (text.isBlank() || noSpeech >= 0.65 || tokenProbability < 0.16) {
                    sessionLog.write("asr_filtered_noise characters=${text.length}")
                    report("asr_filtered_noise")
                    return@enqueue
                }
                outputCharacters = text.length
                sessionLog.write("asr_ok characters=${text.length}")
                sessionLog.write("asr_text=${text.replace(Regex("[\\r\\n]+"), " ").take(240)}")
                if (e == epoch && accepting) post { events.recognition(RecognitionEvent(e, window, revision, start, end, text, finalResult)) {} }
            } catch (error: Throwable) {
                sessionLog.write("asr_failed final=$finalResult", error)
                if (finalResult && e == epoch && accepting) post { events.gap(e, start, end) {} }
            }
            val elapsed = SystemClock.elapsedRealtime() - began
            val audioMs = maxOf(1L, pcm.size.toLong() / 16L)
            report("asr_ms", elapsed)
            report("asr_rtf_milli", elapsed * 1000L / audioMs)
            if (outputCharacters > 0 && elapsed > 0) {
                report("asr_characters_per_second", outputCharacters * 1000L / elapsed)
            }
        }
    }

    private fun submitEndToEnd(e: Long, window: Long, start: Long, end: Long, pcm: FloatArray) {
        val submittedAt = SystemClock.elapsedRealtime()
        // Do not let slow inference turn into an ever-growing stale subtitle
        // queue. Keep the active job and replace any pending E2E window with
        // the newest overlapping window.
        val stale = queue.filter { it.epoch == e && it.id.startsWith("e2e-") }
        if (stale.isNotEmpty()) {
            stale.forEach(queue::remove)
            sessionLog.write("e2e_queue_replaced count=${stale.size} newest=$window")
            report("e2e_queue_replaced", stale.size.toLong())
        }
        enqueue("e2e-$window", e, priority = 1) {
            val began = SystemClock.elapsedRealtime()
            val loadStart = loadSampler.begin()
            val thermal = if (Build.VERSION.SDK_INT >= 29) powerManager.currentThermalStatus else -1
            val nativeHeapMb = android.os.Debug.getNativeHeapAllocatedSize() / 1_000_000L
            val pending = queue.count { it.epoch == e && it.id.startsWith("e2e-") }
            sessionLog.write("e2e_resources window=$window queue_wait_ms=${began-submittedAt} pending=$pending thermal=$thermal native_heap_bytes=${android.os.Debug.getNativeHeapAllocatedSize()} source=${if (activity.playbackSelected) "playback" else "microphone"}")
            report("e2e_queue_depth", pending.toLong())
            report("e2e_thermal_status", thermal.toLong())
            report("e2e_native_heap_mb", nativeHeapMb)
            try {
                sessionLog.write("e2e_begin samples=${pcm.size}")
                checkNotNull(e2eBackend).setHints(liveE2eHints)
                val completed = AtomicBoolean(false)
                val timedOut = AtomicBoolean(false)
                val cancellationLock = Any()
                val timeout = watchdog.schedule({
                    synchronized(cancellationLock) { if (completed.compareAndSet(false, true)) {
                        timedOut.set(true)
                        sessionLog.write("e2e_timeout window=$window limit_ms=$E2E_WATCHDOG_MS")
                        report("e2e_timeout", E2E_WATCHDOG_MS)
                        e2eBackend?.cancel()
                    } }
                }, E2E_WATCHDOG_MS, TimeUnit.MILLISECONDS)
                val raw = try {
                    checkNotNull(e2eBackend).infer(pcm)
                } finally {
                    synchronized(cancellationLock) {
                        if (completed.compareAndSet(false, true)) timeout.cancel(false)
                    }
                }
                if (timedOut.get()) throw IllegalStateException("e2e_timeout")
                sessionLog.write("e2e_raw=${raw.replace(Regex("[\\r\\n]+"), " ").take(400)}")
                when (val parsed = E2eProtocol.parseFor(raw, activity.captionTask)) {
                    E2eProtocol.Result.NoSpeech -> {
                        sessionLog.write("e2e_filtered_no_s window=$window")
                        report("e2e_filtered_no_speech")
                    }
                    is E2eProtocol.Result.Invalid -> {
                        sessionLog.write("e2e_parse_failed window=$window reason=${parsed.reason}")
                        report("e2e_parse_failed")
                    }
                    is E2eProtocol.Result.Subtitle -> {
                        sessionLog.write(
                            "e2e_ok english=${parsed.english.length} chinese=${parsed.chinese.length}",
                        )
                        if (e == epoch && accepting) post {
                            events.bilingual(
                                BilingualEvent(
                                    e, window, start, end, parsed.english, parsed.chinese,
                                ),
                            ) {}
                        }
                    }
                }
            } catch (error: Throwable) {
                sessionLog.write("e2e_failed window=$window", error)
                if (e == epoch && accepting) post { events.gap(e, start, end) {} }
            } finally {
                val elapsed = SystemClock.elapsedRealtime() - began
                val loadEnd = loadSampler.begin()
                val cpuPercent = loadSampler.processCpuPercent(loadStart, loadEnd)
                val gpuPercent = loadSampler.gpuPercent()
                sessionLog.write(
                    "e2e_performance window=$window inference_ms=$elapsed audio_ms=${end-start} " +
                        "rtf_milli=${elapsed * 1000L / maxOf(1L, end-start)} " +
                        "cpu_process_pct=${cpuPercent ?: -1} gpu_pct=${gpuPercent ?: -1}",
                )
                if (cpuPercent != null) report("cpu_process_load_percent", cpuPercent.toLong())
                if (gpuPercent != null) report("gpu_load_percent", gpuPercent.toLong())
                report("e2e_ms", elapsed)
                report("e2e_rtf_milli", elapsed * 1000L / maxOf(1L, end - start))
            }
        }
    }

    /**
     * Playback capture can legally return exact zero PCM while the source app
     * is paused or blocks capture. This is a transport condition, not speech
     * silence; avoid spending a full multimodal inference on it. Near-zero or
     * low-level audio is deliberately kept for Gemma to judge.
     */
    private fun isExactDigitalSilence(samples: FloatArray): Boolean = samples.all { it == 0f }

    override fun pause() {
        sessionLog.write("pause")
        recording.set(false)
        val activeE2e = activeJob?.id?.startsWith("e2e-") == true
        val pendingE2e = queue.any { it.epoch == epoch && it.id.startsWith("e2e-") }
        if (activeE2e || pendingE2e) {
            discardE2eOnPause.set(true)
            accepting = false
            queue.filter { it.epoch == epoch && it.id.startsWith("e2e-") }
                .forEach { if (queue.remove(it)) it.dropped() }
            if (activeE2e) {
                sessionLog.write("e2e_pause_cancel_requested id=${activeJob?.id}")
                e2eBackend?.cancel()
            }
        }
        PlaybackCaptionService.instance?.update("已暂停 · 返回 OpenCaption 继续")
        try { recorder?.stop() } catch (_: Throwable) {}
        activity.window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        queue.filter { it.priority == 4 }.forEach { queue.remove(it) }
    }
    override fun drain(callback: (Result<Unit>) -> Unit) {
        val drainEpoch = epoch
        Thread({
            captureThread?.join()
            enqueue("drain-${serial.incrementAndGet()}", drainEpoch, priority = 2, requiresAccepting = false,
                dropped = { post { callback(Result.failure(error("drain_cancelled"))) } }) {
                sessionLog.write("asr_drain_complete epoch=$drainEpoch")
                post { callback(Result.success(Unit)) }
            }
        }, "caption-drain").apply { isDaemon = true; start() }
    }
    fun interrupt(code: String) {
        sessionLog.write("interrupt code=$code recording=${recording.get()}")
        if (!recording.get()) return
        val e = epoch; pause(); post { events.interrupted(e, code) {} }
    }
    override fun cancel() {
        sessionLog.write("cancel")
        accepting = false; native.setCancelled(true); native.setTranslationCancelled(true); e2eBackend?.cancel()
        queue.filter { it.epoch >= 0 }.forEach { if (queue.remove(it)) it.dropped() }
    }
    override fun release(callback: (Result<Unit>) -> Unit) {
        activity.stopPlayback()
        pause(); cancel(); prepared = false
        enqueue("release", -1, priority = 0, requiresAccepting = false) {
            captureThread?.join()
            engineLock.write { native.release(); e2eBackend?.close(); translator?.close(); translator = null }
            sessionLog.write("session_release_ok")
            sessionLog.close()
            post { callback(Result.success(Unit)) }
        }
    }
    override fun translate(epoch: Long, id: String, text: String, payload: String, callback: (Result<String>) -> Unit) {
        val replied = AtomicBoolean(false)
        fun reply(result: Result<String>) { if (replied.compareAndSet(false, true)) post { callback(result) } }
        if (queue.count { it.priority == 3 } >= 1) {
            reply(Result.failure(error("translation_queue_full")))
            return
        }
        enqueue(id, epoch, priority = 3, requiresAccepting = false,
            dropped = { reply(Result.failure(error("cancelled"))) }) {
            val began = SystemClock.elapsedRealtime()
            var outputCharacters = 0
            try {
                sessionLog.write("translation_begin mode=${config?.mode}")
                val result = engineLock.read {
                    if (config?.mode == "mlKit") Tasks.await(translator!!.translate(text))
                    else native.translate(payload)
                }
                outputCharacters = result.length
                sessionLog.write("translation_ok characters=${result.length}")
                sessionLog.write("translation_raw=${result.replace(Regex("[\\r\\n]+"), " ").take(320)}")
                if (prepared && epoch == this.epoch && !cancelledIds.remove(id)) reply(Result.success(result))
                else reply(Result.failure(error("cancelled")))
            } catch (failure: Throwable) {
                cancelledIds.remove(id)
                val code = if (preemptedIds.remove(id)) "translation_preempted" else "translation_failed"
                sessionLog.write("translation_failed id=$id code=$code", failure)
                reply(Result.failure(error(code)))
            }
            val elapsed = SystemClock.elapsedRealtime() - began
            report("translation_ms", elapsed)
            if (outputCharacters > 0 && elapsed > 0) {
                report("translation_characters_per_second", outputCharacters * 1000L / elapsed)
            }
        }
    }
    override fun cancelTranslation(id: String) {
        if (activeJob?.id == id && activeJob?.priority == 3) {
            cancelledIds.add(id)
            native.setTranslationCancelled(true)
        }
        queue.filter { it.id == id }.forEach { if (queue.remove(it)) it.dropped() }
    }
    override fun mlKitReady(callback: (Result<Boolean>) -> Unit) {
        modelManager.isModelDownloaded(mlModel).addOnSuccessListener { callback(Result.success(it)) }
            .addOnFailureListener { callback(Result.failure(error("mlkit_status"))) }
    }
    override fun downloadMlKit(callback: (Result<Unit>) -> Unit) {
        modelManager.download(mlModel, DownloadConditions.Builder().requireWifi().build())
            .addOnSuccessListener { callback(Result.success(Unit)) }
            .addOnFailureListener { callback(Result.failure(error("mlkit_download"))) }
    }
    override fun deleteMlKit(callback: (Result<Unit>) -> Unit) {
        if (prepared) { callback(Result.failure(error("model_in_use"))); return }
        modelManager.deleteDownloadedModel(mlModel).addOnSuccessListener { callback(Result.success(Unit)) }
            .addOnFailureListener { callback(Result.failure(error("mlkit_delete"))) }
    }
    override fun openAppSettings() {
        activity.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${activity.packageName}")))
    }
    fun destroy() {
        audioManager.unregisterAudioRecordingCallback(micCallback)
        if (Build.VERSION.SDK_INT >= 29) thermalListener?.let { powerManager.removeThermalStatusListener(it) }
        release {
            sessionLog.uninstallCrashHandler()
            worker.interrupt()
        }
    }
}
