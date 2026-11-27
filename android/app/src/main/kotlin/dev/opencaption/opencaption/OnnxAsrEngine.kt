package dev.opencaption.opencaption

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.io.File
import java.nio.FloatBuffer
import java.nio.IntBuffer
import java.nio.LongBuffer
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Pure-Kotlin ONNX Runtime ASR engine supporting non-autoregressive SenseVoice-Small
 * and FastConformer Parakeet-TDT-0.6B-v3 on top of the existing onnxruntime-android
 * dependency (zero extra native binaries).
 */
interface OnnxAsrBackend : AutoCloseable {
    val kind: String
    fun transcribe(samples: FloatArray, language: String): String
    fun setCancelled(value: Boolean)
}

object OnnxAsrFactory {
    fun isOnnxAsrPath(path: String): Boolean {
        if (path.isEmpty()) return false
        val dir = File(path)
        if (!dir.isDirectory) return false
        return File(dir, "model.int8.onnx").isFile || File(dir, "encoder.int8.onnx").isFile
    }

    fun load(modelDir: String, threads: Int): OnnxAsrBackend {
        val dir = File(modelDir)
        val nThreads = threads.coerceIn(1, 8)
        return when {
            File(dir, "model.int8.onnx").isFile -> SenseVoiceOnnxAsr(dir, nThreads)
            File(dir, "encoder.int8.onnx").isFile -> ParakeetTdtOnnxAsr(dir, nThreads)
            else -> throw IllegalArgumentException("unsupported_onnx_asr_dir:$modelDir")
        }
    }
}

private object AudioDsp {
    const val SAMPLE_RATE = 16000
    const val N_FFT = 512
    const val HALF_FFT = N_FFT / 2 + 1 // 257

    private val bitRev = IntArray(N_FFT).also { table ->
        val bits = 9 // log2(512)
        for (i in 0 until N_FFT) {
            var x = i
            var r = 0
            for (b in 0 until bits) {
                r = (r shl 1) or (x and 1)
                x = x ushr 1
            }
            table[i] = r
        }
    }

    private val cosTable = DoubleArray(N_FFT / 2) { i -> cos(-2.0 * PI * i / N_FFT) }
    private val sinTable = DoubleArray(N_FFT / 2) { i -> sin(-2.0 * PI * i / N_FFT) }

    fun fftPower512(frame: FloatArray, re: DoubleArray, im: DoubleArray, powerOut: FloatArray) {
        for (i in 0 until N_FFT) {
            val j = bitRev[i]
            re[j] = if (i < frame.size) frame[i].toDouble() else 0.0
            im[j] = 0.0
        }
        var len = 2
        while (len <= N_FFT) {
            val half = len ushr 1
            val step = N_FFT / len
            var i = 0
            while (i < N_FFT) {
                var k = 0
                for (j in 0 until half) {
                    val c = cosTable[k]
                    val s = sinTable[k]
                    val uR = re[i + j]
                    val uI = im[i + j]
                    val tR = re[i + j + half] * c - im[i + j + half] * s
                    val tI = re[i + j + half] * s + im[i + j + half] * c
                    re[i + j] = uR + tR
                    im[i + j] = uI + tI
                    re[i + j + half] = uR - tR
                    im[i + j + half] = uI - tI
                    k += step
                }
                i += len
            }
            len = len shl 1
        }
        for (k in 0 until HALF_FFT) {
            powerOut[k] = (re[k] * re[k] + im[k] * im[k]).toFloat()
        }
    }

    /** Kaldi triangular mel filterbank (HTK mel scale: 1127 * ln(1 + f / 700)). */
    fun kaldiMelBank(numBins: Int, lowFreq: Double, highFreq: Double): Array<FloatArray> {
        fun hzToMel(f: Double) = 1127.0 * ln(1.0 + f / 700.0)
        val melLow = hzToMel(lowFreq)
        val melHigh = hzToMel(highFreq)
        val melDelta = (melHigh - melLow) / (numBins + 1)
        val fftBinWidth = SAMPLE_RATE.toDouble() / N_FFT
        return Array(numBins) { bin ->
            val leftMel = melLow + bin * melDelta
            val centerMel = melLow + (bin + 1) * melDelta
            val rightMel = melLow + (bin + 2) * melDelta
            FloatArray(HALF_FFT) { k ->
                val mel = hzToMel(k * fftBinWidth)
                val up = (mel - leftMel) / (centerMel - leftMel)
                val down = (rightMel - mel) / (rightMel - centerMel)
                max(0.0, min(up, down)).toFloat()
            }
        }
    }

    /** Slaney-normalized librosa/NeMo mel filterbank (0..8000 Hz, 128 bins). */
    fun slaneyMelBank(numBins: Int, lowFreq: Double, highFreq: Double): Array<FloatArray> {
        val fMin = 0.0
        val fSp = 200.0 / 3.0
        val minLogHz = 1000.0
        val minLogMel = (minLogHz - fMin) / fSp
        val logStep = ln(6.4) / 27.0

        fun hzToMel(f: Double): Double =
            if (f < minLogHz) (f - fMin) / fSp else minLogMel + ln(f / minLogHz) / logStep

        fun melToHz(m: Double): Double =
            if (m < minLogMel) fMin + fSp * m else minLogHz * kotlin.math.exp(logStep * (m - minLogMel))

        val melLow = hzToMel(lowFreq)
        val melHigh = hzToMel(highFreq)
        val hzPoints = DoubleArray(numBins + 2) { i ->
            melToHz(melLow + (melHigh - melLow) * i / (numBins + 1))
        }
        val fftFreqs = DoubleArray(HALF_FFT) { k -> k * (SAMPLE_RATE.toDouble() / N_FFT) }
        return Array(numBins) { bin ->
            val fLeft = hzPoints[bin]
            val fCenter = hzPoints[bin + 1]
            val fRight = hzPoints[bin + 2]
            val enorm = 2.0 / (fRight - fLeft)
            FloatArray(HALF_FFT) { k ->
                val f = fftFreqs[k]
                val lower = (f - fLeft) / (fCenter - fLeft)
                val upper = (fRight - f) / (fRight - fCenter)
                (max(0.0, min(lower, upper)) * enorm).toFloat()
            }
        }
    }

    fun loadTokens(file: File): Array<String> {
        val pairs = mutableListOf<Pair<Int, String>>()
        var maxId = -1
        file.forEachLine(Charsets.UTF_8) { raw ->
            if (raw.isEmpty()) return@forEachLine
            val split = raw.lastIndexOf(' ')
            if (split <= 0) return@forEachLine
            val id = raw.substring(split + 1).trim().toIntOrNull() ?: return@forEachLine
            val piece = raw.substring(0, split)
            pairs.add(id to piece)
            if (id > maxId) maxId = id
        }
        val table = Array(maxId + 1) { "" }
        for ((id, piece) in pairs) table[id] = piece
        return table
    }
}

/**
 * FunAudioLLM SenseVoice-Small INT8 ONNX (zh / en / ja / ko / yue).
 * Single-pass non-autoregressive CTC encoder (~80-150 ms per 4 s audio on mobile CPU).
 */
private class SenseVoiceOnnxAsr(dir: File, threads: Int) : OnnxAsrBackend {
    override val kind: String = "sensevoice_onnx"
    private val cancelled = AtomicBoolean(false)
    private val env = OrtEnvironment.getEnvironment()
    private val session: OrtSession
    private val tokens: Array<String>
    private val lfrM: Int
    private val lfrN: Int
    private val normalizeSamples: Boolean
    private val negMean: FloatArray
    private val invStddev: FloatArray
    private val langMap: Map<String, Int>
    private val withItnId: Int
    private val melBank = AudioDsp.kaldiMelBank(80, 20.0, 8000.0)
    private val hamming = FloatArray(400) { i ->
        (0.54 - 0.46 * cos(2.0 * PI * i / 399.0)).toFloat()
    }

    init {
        val opts = OrtSession.SessionOptions().apply {
            setIntraOpNumThreads(threads)
            setInterOpNumThreads(1)
            setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        }
        session = opts.use { env.createSession(File(dir, "model.int8.onnx").path, it) }
        tokens = AudioDsp.loadTokens(File(dir, "tokens.txt"))
        val meta = session.metadata.customMetadata
        lfrM = meta["lfr_window_size"]?.toIntOrNull() ?: 7
        lfrN = meta["lfr_window_shift"]?.toIntOrNull() ?: 6
        normalizeSamples = (meta["normalize_samples"]?.toIntOrNull() ?: 0) != 0
        negMean = parseCsvFloats(meta["neg_mean"] ?: "")
        invStddev = parseCsvFloats(meta["inv_stddev"] ?: "")
        langMap = mapOf(
            "auto" to (meta["lang_auto"]?.toIntOrNull() ?: 0),
            "zh" to (meta["lang_zh"]?.toIntOrNull() ?: 3),
            "en" to (meta["lang_en"]?.toIntOrNull() ?: 4),
            "yue" to (meta["lang_yue"]?.toIntOrNull() ?: 7),
            "ja" to (meta["lang_ja"]?.toIntOrNull() ?: 11),
            "ko" to (meta["lang_ko"]?.toIntOrNull() ?: 12),
        )
        withItnId = meta["with_itn"]?.toIntOrNull() ?: 14
    }

    override fun setCancelled(value: Boolean) { cancelled.set(value) }

    override fun transcribe(samples: FloatArray, language: String): String {
        if (samples.isEmpty() || cancelled.get()) return ""
        var peak = 0f
        for (s in samples) {
            val a = if (s < 0f) -s else s
            if (a > peak) peak = a
        }
        val normalized = if (peak > 0.004f && peak < 0.12f) {
            val gain = min(4.0f, 0.25f / peak)
            FloatArray(samples.size) { i -> (samples[i] * gain).coerceIn(-0.98f, 0.98f) }
        } else {
            samples
        }
        val fbank = extractKaldiFbank(normalized)
        if (fbank.isEmpty() || cancelled.get()) return ""
        val (lfr, tLfr) = applyLfrAndCmvn(fbank)
        if (tLfr <= 0 || cancelled.get()) return ""
        val langId = langMap[language] ?: langMap["auto"] ?: 0

        val xShape = longArrayOf(1L, tLfr.toLong(), (80 * lfrM).toLong())
        OnnxTensor.createTensor(env, FloatBuffer.wrap(lfr), xShape).use { xTensor ->
            OnnxTensor.createTensor(env, IntBuffer.wrap(intArrayOf(tLfr)), longArrayOf(1)).use { lenTensor ->
                OnnxTensor.createTensor(env, IntBuffer.wrap(intArrayOf(langId)), longArrayOf(1)).use { langTensor ->
                    OnnxTensor.createTensor(env, IntBuffer.wrap(intArrayOf(withItnId)), longArrayOf(1)).use { normTensor ->
                        val inputs = mapOf(
                            "x" to xTensor,
                            "x_length" to lenTensor,
                            "language" to langTensor,
                            "text_norm" to normTensor,
                        )
                        session.run(inputs).use { result ->
                            val tensor = result[0] as OnnxTensor
                            val shape = tensor.info.shape
                            val tOut = shape[1].toInt()
                            val vocab = shape[2].toInt()
                            val buf = tensor.floatBuffer
                            return decodeCtc(buf, tOut, vocab)
                        }
                    }
                }
            }
        }
    }

    private fun extractKaldiFbank(samples: FloatArray): Array<FloatArray> {
        val scale = if (normalizeSamples) 1.0f else 32768.0f
        val padded = if (samples.size < 400) {
            FloatArray(400).also { samples.copyInto(it) }
        } else {
            samples
        }
        val numFrames = 1 + (padded.size - 400) / 160
        val out = Array(numFrames) { FloatArray(80) }
        val win = FloatArray(400)
        val re = DoubleArray(AudioDsp.N_FFT)
        val im = DoubleArray(AudioDsp.N_FFT)
        val power = FloatArray(AudioDsp.HALF_FFT)

        for (t in 0 until numFrames) {
            val offset = t * 160
            var sum = 0.0
            for (i in 0 until 400) {
                val v = padded[offset + i] * scale
                win[i] = v
                sum += v
            }
            val mean = (sum / 400.0).toFloat()
            for (i in 0 until 400) win[i] -= mean
            for (i in 399 downTo 1) win[i] -= 0.97f * win[i - 1]
            win[0] *= (1.0f - 0.97f)
            for (i in 0 until 400) win[i] *= hamming[i]

            AudioDsp.fftPower512(win, re, im, power)
            val row = out[t]
            for (m in 0 until 80) {
                val weights = melBank[m]
                var energy = 0.0
                for (k in 0 until AudioDsp.HALF_FFT) {
                    val w = weights[k]
                    if (w != 0f) energy += w * power[k]
                }
                row[m] = ln(max(energy, 1.1920929e-7)).toFloat()
            }
        }
        return out
    }

    private fun applyLfrAndCmvn(feats: Array<FloatArray>): Pair<FloatArray, Int> {
        val tOrig = feats.size
        val leftPad = (lfrM - 1) / 2
        val tPadded = tOrig + leftPad
        val tLfr = (tOrig + lfrN - 1) / lfrN
        val featDim = 80 * lfrM
        val out = FloatArray(tLfr * featDim)
        val hasCmvn = negMean.size == featDim && invStddev.size == featDim

        for (i in 0 until tLfr) {
            val dstBase = i * featDim
            val srcStart = i * lfrN
            for (j in 0 until lfrM) {
                val pIdx = min(srcStart + j, tPadded - 1)
                val origIdx = max(0, pIdx - leftPad)
                val src = feats[origIdx]
                val colBase = dstBase + j * 80
                if (hasCmvn) {
                    for (d in 0 until 80) {
                        val flatD = j * 80 + d
                        out[colBase + d] = (src[d] + negMean[flatD]) * invStddev[flatD]
                    }
                } else {
                    src.copyInto(out, colBase)
                }
            }
        }
        return out to tLfr
    }

    private fun decodeCtc(buf: FloatBuffer, tOut: Int, vocab: Int): String {
        fun argmaxAt(t: Int): Int {
            val base = t * vocab
            var bestId = 0
            var bestVal = buf.get(base)
            for (v in 1 until vocab) {
                val x = buf.get(base + v)
                if (x > bestVal) {
                    bestVal = x
                    bestId = v
                }
            }
            return bestId
        }
        // Check header frames (0: language, 2: acoustic event) for non-speech/BGM.
        if (tOut > 4) {
            val langTok = tokens.getOrNull(argmaxAt(0)).orEmpty()
            val eventTok = tokens.getOrNull(argmaxAt(2)).orEmpty()
            if (langTok == "<|nospeech|>" ||
                eventTok == "<|BGM|>" ||
                eventTok == "<|Applause|>" ||
                eventTok == "<|Laughter|>"
            ) {
                return ""
            }
        }
        val sb = StringBuilder()
        var prevId = -1
        val startT = if (tOut > 4) 4 else 0
        for (t in startT until tOut) {
            val bestId = argmaxAt(t)
            if (bestId != prevId && bestId != 0 && bestId < tokens.size) {
                val piece = tokens[bestId]
                if (!piece.startsWith("<|") && piece != "<unk>" && piece != "<s>" && piece != "</s>") {
                    sb.append(piece)
                }
            }
            prevId = bestId
        }
        val text = sb.toString()
            .replace('\u2581', ' ')
            .replace(Regex("\\s+"), " ")
            .trim()
        // Suppress SenseVoice single-token CTC default-prior hallucinations on noise/silence.
        val stripped = text.trimEnd('.', '。', ',', '，', '!', '！', '?', '？').lowercase()
        if (stripped.isEmpty() || stripped in setOf("the", "i", "a", "我", "嗯", "啊")) {
            return ""
        }
        return text
    }

    private fun parseCsvFloats(csv: String): FloatArray {
        if (csv.isBlank()) return FloatArray(0)
        val parts = csv.split(',')
        return FloatArray(parts.size) { parts[it].trim().toFloatOrNull() ?: 0f }
    }

    override fun close() {
        session.close()
    }
}

/**
 * NVIDIA NeMo Parakeet-TDT-0.6B-v3 INT8 ONNX (25 European languages, ultra-fast English).
 * FastConformer encoder + 2-layer LSTM prediction network + TDT duration joiner.
 */
private class ParakeetTdtOnnxAsr(dir: File, threads: Int) : OnnxAsrBackend {
    override val kind: String = "parakeet_tdt_onnx"
    private val cancelled = AtomicBoolean(false)
    private val env = OrtEnvironment.getEnvironment()
    private val encoder: OrtSession
    private val decoder: OrtSession
    private val joiner: OrtSession
    private val tokens: Array<String>
    private val vocabSize: Int
    private val blankId: Int
    private val predLayers: Int
    private val predHidden: Int
    private val featDim: Int
    private val decInNames: List<String>
    private val decOutNames: List<String>
    private val melBank: Array<FloatArray>
    private val hann = FloatArray(400) { i ->
        // Periodic Hann window matching PyTorch/NeMo torch.hann_window(400, periodic=True)
        (0.5 - 0.5 * cos(2.0 * PI * i / 400.0)).toFloat()
    }

    init {
        val encOpts = OrtSession.SessionOptions().apply {
            setIntraOpNumThreads(threads)
            setInterOpNumThreads(1)
            setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        }
        encoder = encOpts.use { env.createSession(File(dir, "encoder.int8.onnx").path, it) }
        val smallOpts = OrtSession.SessionOptions().apply {
            setIntraOpNumThreads(min(threads, 2))
            setInterOpNumThreads(1)
            setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        }
        decoder = smallOpts.use { env.createSession(File(dir, "decoder.int8.onnx").path, it) }
        val joinOpts = OrtSession.SessionOptions().apply {
            setIntraOpNumThreads(min(threads, 2))
            setInterOpNumThreads(1)
            setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        }
        joiner = joinOpts.use { env.createSession(File(dir, "joiner.int8.onnx").path, it) }
        tokens = AudioDsp.loadTokens(File(dir, "tokens.txt"))

        val meta = encoder.metadata.customMetadata
        featDim = meta["feat_dim"]?.toIntOrNull() ?: 128
        vocabSize = meta["vocab_size"]?.toIntOrNull() ?: 8192
        blankId = vocabSize
        predLayers = meta["pred_rnn_layers"]?.toIntOrNull() ?: 2
        predHidden = meta["pred_hidden"]?.toIntOrNull() ?: 640
        val rawInputs = decoder.inputNames.toList()
        decInNames = if (rawInputs.containsAll(listOf("targets", "target_length", "states.1", "onnx::Slice_3"))) {
            listOf("targets", "target_length", "states.1", "onnx::Slice_3")
        } else {
            rawInputs
        }
        val rawOutputs = decoder.outputNames.toList()
        decOutNames = if (rawOutputs.containsAll(listOf("outputs", "prednet_lengths", "states", "162"))) {
            listOf("outputs", "prednet_lengths", "states", "162")
        } else {
            rawOutputs
        }
        melBank = AudioDsp.slaneyMelBank(featDim, 0.0, 8000.0)
    }

    override fun setCancelled(value: Boolean) { cancelled.set(value) }

    override fun transcribe(samples: FloatArray, language: String): String {
        if (samples.size < 400 || cancelled.get()) return ""
        // Gently normalize quiet speech windows (never amplifying loud crowd noise)
        // so Parakeet-TDT does not drop low-volume commentary or interview lines.
        var peak = 0f
        for (s in samples) {
            val a = if (s < 0f) -s else s
            if (a > peak) peak = a
        }
        val normalizedSamples = if (peak > 0.004f && peak < 0.12f) {
            val gain = min(4.0f, 0.25f / peak)
            FloatArray(samples.size) { i -> (samples[i] * gain).coerceIn(-0.98f, 0.98f) }
        } else {
            samples
        }
        val (features, numFrames) = extractNemoFeatures(normalizedSamples)
        if (numFrames <= 0 || cancelled.get()) return ""

        // 1. Run FastConformer encoder -> [1, encDim, tEnc]
        var encDim = 0
        var tEnc = 0
        var encData = FloatArray(0)
        OnnxTensor.createTensor(
            env,
            FloatBuffer.wrap(features),
            longArrayOf(1L, featDim.toLong(), numFrames.toLong()),
        ).use { sigTensor ->
            OnnxTensor.createTensor(
                env,
                LongBuffer.wrap(longArrayOf(numFrames.toLong())),
                longArrayOf(1L),
            ).use { lenTensor ->
                encoder.run(mapOf("audio_signal" to sigTensor, "length" to lenTensor)).use { res ->
                    val outTensor = res[0] as OnnxTensor
                    val lenOut = res[1] as OnnxTensor
                    val shape = outTensor.info.shape
                    encDim = shape[1].toInt()
                    val fullT = shape[2].toInt()
                    val validT = lenOut.longBuffer.get(0).toInt().coerceIn(0, fullT)
                    tEnc = validT
                    val fb = outTensor.floatBuffer
                    encData = FloatArray(encDim * fullT)
                    fb.get(encData)
                    // Copy out transposed frame-major [tEnc, encDim] for cache-friendly joiner loop
                    val frameMajor = FloatArray(tEnc * encDim)
                    for (d in 0 until encDim) {
                        val rowBase = d * fullT
                        for (t in 0 until tEnc) {
                            frameMajor[t * encDim + d] = encData[rowBase + t]
                        }
                    }
                    encData = frameMajor
                }
            }
        }
        if (tEnc <= 0 || cancelled.get()) return ""

        // 2. Greedy TDT decoding (durations = [0, 1, 2, 3, 4])
        val stateSize = predLayers * predHidden
        var stateH = FloatArray(stateSize)
        var stateC = FloatArray(stateSize)
        var decStep = runDecoder(blankId, stateH, stateC)
        var decOut = decStep.output
        stateH = decStep.nextH
        stateC = decStep.nextC

        val emitted = ArrayList<Int>(64)
        var t = 0
        var symbolsAtFrame = 0
        val maxSymbolsPerFrame = 8
        val encFrame = FloatArray(encDim)

        while (t < tEnc && !cancelled.get()) {
            encData.copyInto(encFrame, 0, t * encDim, (t + 1) * encDim)
            val (tokenId, durationSkip) = runJoiner(encFrame, encDim, decOut)
            if (tokenId != blankId) {
                emitted.add(tokenId)
                decStep = runDecoder(tokenId, stateH, stateC)
                decOut = decStep.output
                stateH = decStep.nextH
                stateC = decStep.nextC
                symbolsAtFrame++
                if (durationSkip > 0) {
                    t += durationSkip
                    symbolsAtFrame = 0
                } else if (symbolsAtFrame >= maxSymbolsPerFrame) {
                    t += 1
                    symbolsAtFrame = 0
                }
            } else {
                t += max(1, durationSkip)
                symbolsAtFrame = 0
            }
        }

        val sb = StringBuilder()
        for (id in emitted) {
            if (id in tokens.indices) {
                val piece = tokens[id]
                if (!piece.startsWith("<|") && piece != "<unk>" && piece != "<pad>" && piece != "<blk>") {
                    sb.append(piece)
                }
            }
        }
        return sb.toString()
            .replace('\u2581', ' ')
            .replace(Regex("\\s+"), " ")
            .trim()
    }

    private class DecoderResult(val output: FloatArray, val nextH: FloatArray, val nextC: FloatArray)

    private fun runDecoder(tokenId: Int, stateH: FloatArray, stateC: FloatArray): DecoderResult {
        val stateShape = longArrayOf(predLayers.toLong(), 1L, predHidden.toLong())
        OnnxTensor.createTensor(env, IntBuffer.wrap(intArrayOf(tokenId)), longArrayOf(1, 1)).use { tgt ->
            OnnxTensor.createTensor(env, IntBuffer.wrap(intArrayOf(1)), longArrayOf(1)).use { tLen ->
                OnnxTensor.createTensor(env, FloatBuffer.wrap(stateH), stateShape).use { s1 ->
                    OnnxTensor.createTensor(env, FloatBuffer.wrap(stateC), stateShape).use { s2 ->
                        val inputs = mapOf(
                            decInNames[0] to tgt,
                            decInNames[1] to tLen,
                            decInNames[2] to s1,
                            decInNames[3] to s2,
                        )
                        decoder.run(inputs).use { res ->
                            val outBuf = (res.get(decOutNames[0]).get() as OnnxTensor).floatBuffer
                            val out = FloatArray(predHidden).also { outBuf.get(it) }
                            val nextH = FloatArray(stateH.size).also { (res.get(decOutNames[2]).get() as OnnxTensor).floatBuffer.get(it) }
                            val nextC = FloatArray(stateC.size).also { (res.get(decOutNames[3]).get() as OnnxTensor).floatBuffer.get(it) }
                            return DecoderResult(out, nextH, nextC)
                        }
                    }
                }
            }
        }
    }

    private fun runJoiner(encFrame: FloatArray, encDim: Int, decOut: FloatArray): Pair<Int, Int> {
        OnnxTensor.createTensor(env, FloatBuffer.wrap(encFrame), longArrayOf(1, encDim.toLong(), 1)).use { eT ->
            OnnxTensor.createTensor(env, FloatBuffer.wrap(decOut), longArrayOf(1, predHidden.toLong(), 1)).use { dT ->
                joiner.run(mapOf("encoder_outputs" to eT, "decoder_outputs" to dT)).use { res ->
                    val tensor = res[0] as OnnxTensor
                    val buf = tensor.floatBuffer
                    val total = buf.remaining()
                    val numTokens = vocabSize + 1 // 8193 (0..8191 + blank 8192)
                    var bestTok = 0
                    var bestTokVal = buf.get(0)
                    for (i in 1 until min(numTokens, total)) {
                        val v = buf.get(i)
                        if (v > bestTokVal) {
                            bestTokVal = v
                            bestTok = i
                        }
                    }
                    var bestDur = 0
                    if (total > numTokens) {
                        var bestDurVal = buf.get(numTokens)
                        for (d in 1 until (total - numTokens)) {
                            val v = buf.get(numTokens + d)
                            if (v > bestDurVal) {
                                bestDurVal = v
                                bestDur = d
                            }
                        }
                    }
                    return bestTok to bestDur
                }
            }
        }
    }

    /**
     * NeMo AudioToMelSpectrogramPreprocessor (128-dim Slaney mel, preemph=0.97,
     * center-padded 512 FFT / 400 Hann window / 160 hop, log(x + 2^-24), per_feature z-norm).
     */
    private fun extractNemoFeatures(samples: FloatArray): Pair<FloatArray, Int> {
        val n = samples.size
        // Pre-emphasis
        val pre = FloatArray(n)
        pre[0] = samples[0]
        for (i in 1 until n) pre[i] = samples[i] - 0.97f * samples[i - 1]

        // Center-pad by n_fft / 2 = 256 on both sides with reflect padding (matching torch.stft center=True)
        val pad = AudioDsp.N_FFT / 2
        val padded = FloatArray(n + 2 * pad)
        pre.copyInto(padded, pad)
        for (i in 0 until pad) {
            val leftIdx = min(pad - i, n - 1)
            val rightIdx = max(0, n - 2 - i)
            padded[i] = pre[leftIdx]
            padded[pad + n + i] = pre[rightIdx]
        }
        val numFrames = 1 + n / 160
        // Output layout: [featDim, numFrames] (feature-major for encoder input [1, 128, T])
        val feats = FloatArray(featDim * numFrames)
        val win = FloatArray(AudioDsp.N_FFT)
        val re = DoubleArray(AudioDsp.N_FFT)
        val im = DoubleArray(AudioDsp.N_FFT)
        val power = FloatArray(AudioDsp.HALF_FFT)
        val winOffset = (AudioDsp.N_FFT - 400) / 2 // 56 (centered 400-sample Hann inside 512 FFT)
        val logGuard = 5.9604645e-8 // 2^-24

        for (t in 0 until numFrames) {
            val start = t * 160
            win.fill(0f)
            for (i in 0 until 400) {
                val idx = start + winOffset + i
                if (idx in padded.indices) {
                    win[winOffset + i] = padded[idx] * hann[i]
                }
            }
            AudioDsp.fftPower512(win, re, im, power)
            for (m in 0 until featDim) {
                val weights = melBank[m]
                var e = 0.0
                for (k in 0 until AudioDsp.HALF_FFT) {
                    val w = weights[k]
                    if (w != 0f) e += w * power[k]
                }
                feats[m * numFrames + t] = ln(e + logGuard).toFloat()
            }
        }

        // Per-feature normalization (NeMo normalize="per_feature", Bessel ddof=1)
        val denom = max(1, numFrames - 1).toDouble()
        for (m in 0 until featDim) {
            val base = m * numFrames
            var sum = 0.0
            for (t in 0 until numFrames) sum += feats[base + t]
            val mean = sum / numFrames
            var varSum = 0.0
            for (t in 0 until numFrames) {
                val d = feats[base + t] - mean
                varSum += d * d
            }
            val invStd = 1.0 / (sqrt(varSum / denom) + 1e-5)
            for (t in 0 until numFrames) {
                feats[base + t] = ((feats[base + t] - mean) * invStd).toFloat()
            }
        }
        return feats to numFrames
    }

    override fun close() {
        encoder.close()
        decoder.close()
        joiner.close()
    }
}
