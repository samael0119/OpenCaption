package dev.opencaption.opencaption

import android.os.Process
import java.io.File
import kotlin.math.roundToInt

/** Best-effort, permission-free load samples for the status bar. */
internal class RuntimeLoadSampler(
    private val cpuCount: Int = Runtime.getRuntime().availableProcessors().coerceAtLeast(1),
) {
    data class Sample(
        val wallMs: Long,
        val processCpuMs: Long,
    )

    private var previousGpuBusy: Long? = null
    private var previousGpuTotal: Long? = null

    fun begin(): Sample = Sample(
        wallMs = android.os.SystemClock.elapsedRealtime(),
        processCpuMs = Process.getElapsedCpuTime(),
    )

    /** CPU is normalized to total device capacity (100% = all cores). */
    fun processCpuPercent(start: Sample, end: Sample = begin()): Int? {
        val wallDelta = end.wallMs - start.wallMs
        val cpuDelta = end.processCpuMs - start.processCpuMs
        if (wallDelta <= 0L || cpuDelta < 0L) return null
        return ((cpuDelta.toDouble() * 100.0) / (wallDelta * cpuCount))
            .roundToInt()
            .coerceIn(0, 100)
    }

    /**
     * Qualcomm exposes an instantaneous percentage through KGSL. Other
     * Android kernels commonly expose cumulative devfreq busy/total counters;
     * use their delta when available. A missing or unreadable node is null,
     * never a fake zero.
     */
    fun gpuPercent(): Int? {
        val directPaths = listOf(
            "/sys/class/kgsl/kgsl-3d0/gpu_busy_percentage",
            "/sys/class/kgsl/kgsl-3d0/gpu_busy_percent",
        )
        for (path in directPaths) {
            val value = readInt(File(path))
            if (value != null) return value.coerceIn(0, 100)
        }
        val devfreq = File("/sys/class/devfreq")
        val candidates = devfreq.listFiles().orEmpty()
            .filter { file ->
                val name = file.name.lowercase()
                name.contains("gpu") || name.contains("kgsl") || name.contains("3d")
            }
        for (directory in candidates) {
            val busy = readLong(File(directory, "busy_time")) ?: continue
            val total = readLong(File(directory, "total_time")) ?: continue
            val oldBusy = previousGpuBusy
            val oldTotal = previousGpuTotal
            previousGpuBusy = busy
            previousGpuTotal = total
            if (oldBusy == null || oldTotal == null) continue
            val busyDelta = busy - oldBusy
            val totalDelta = total - oldTotal
            if (busyDelta < 0L || totalDelta <= 0L) continue
            return ((busyDelta.toDouble() * 100.0) / totalDelta)
                .roundToInt()
                .coerceIn(0, 100)
        }
        return null
    }

    private fun readInt(file: File): Int? =
        runCatching { file.readText().trim().toIntOrNull() }.getOrNull()

    private fun readLong(file: File): Long? =
        runCatching { file.readText().trim().toLongOrNull() }.getOrNull()
}
