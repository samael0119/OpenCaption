package dev.opencaption.opencaption

import org.junit.Assert.*
import org.junit.Test

/** Replay recorded arrivals/services through the product queue, without a model. */
class E2eQueueReplayTest {
    data class Trace(val id: Long, val begin: Long, val end: Long, val cost: Double)
    data class Running(val chunk: E2eAudioChunk, val started: Double, val finished: Double)
    data class Outcome(val chunk: E2eAudioChunk, val state: String, val at: Double,
        val started: Double? = null)

    @Test fun measuredNormalAndInjectedSlowTracesAccountForEveryAudioInterval() {
        val rows = javaClass.getResourceAsStream("/s0_service_trace.tsv")!!.bufferedReader().use { it.readLines() }
            .filter { !it.startsWith("#") }.map { it.split('\t') }
        val slowDrops = mutableMapOf<String, Long>()
        for (policy in listOf("fixed_5000", "pause_600_max_5000")) {
            val traces = rows.filter { it[0] == policy }.map {
                Trace(it[1].toLong(), it[2].toDouble().toLong(), it[3].toDouble().toLong(), it[4].toDouble())
            }
            val costs = traces.associate { it.id to it.cost }
            for (slow in listOf(false, true)) {
                val queue = E2eAudioQueue(); queue.reset(1)
                val accounted = mutableListOf<E2eAudioChunk>()
                val outcomes = mutableListOf<Outcome>()
                var active: Running? = null
                var droppedMs = 0L; var merges = 0
                fun drop(chunk: E2eAudioChunk, state: String, now: Double) {
                    accounted.add(chunk); droppedMs += chunk.endMs - chunk.startMs
                    outcomes.add(Outcome(chunk, state, now))
                }
                fun take(now: Double) {
                    val taken = queue.take(1, now.toLong())
                    taken.expired?.let { drop(it, "expired", now) }
                    val chunk = taken.chunk
                    if (chunk == null) { queue.finish(1); active = null; return }
                    assertTrue("pending age bounded", now - chunk.submittedAt <= 5000)
                    // A merged request has no measured service in S0: use the sum
                    // of original costs, explicitly a conservative simulation.
                    val ids = chunk.pcm.map { it.toLong() }.toSet()
                    val cost = ids.sumOf { costs.getValue(it) } + if (slow && chunk.endMs <= 30000) 4000 else 0
                    active = Running(chunk, now, now + cost)
                }
                fun complete() {
                    val old = active!!; accounted.add(old.chunk); active = null
                    outcomes.add(Outcome(old.chunk, "delivered", old.finished, old.started))
                    if (queue.finish(1)) take(old.finished)
                }
                for (t in traces) {
                    while (active != null && active!!.finished <= t.end) complete()
                    val chunk = E2eAudioChunk(1, t.id, t.begin, t.end,
                        FloatArray(((t.end-t.begin)*16).toInt()) { t.id.toFloat() }, t.end)
                    val result = queue.offer(chunk)
                    result.dropped?.let { drop(it, "replaced", t.end.toDouble()) }
                    if (result.merged) merges++
                    if (result.schedule) take(t.end.toDouble())
                    assertTrue(queue.pendingCount() <= 1)
                }
                while (active != null) complete()
                assertEquals(0, queue.pendingCount())
                val ordered = accounted.sortedBy { it.startMs }
                assertEquals(0L, ordered.first().startMs)
                assertEquals(traces.last().end, ordered.last().endMs)
                assertTrue(ordered.zipWithNext().all { (a,b) -> a.endMs == b.startMs })
                assertEquals(traces.last().end, ordered.sumOf { it.endMs-it.startMs })
                val delivered = outcomes.filter { it.state == "delivered" }
                assertTrue(delivered.zipWithNext().all { (a,b) -> a.at <= b.started!! })
                if (!slow) assertEquals("normal coverage $policy", 0L, droppedMs)
                if (slow) {
                    slowDrops[policy] = droppedMs
                    assertTrue("recovers after transient overload", outcomes
                        .filter { it.chunk.endMs > 40000 }.all { it.state == "delivered" })
                }
                // Machine-readable product-queue evidence in the JUnit XML's
                // system-out; this is virtual-clock eligibility, not correct
                // model text or measured UI latency. Do not hide missing audio.
                for (outcome in outcomes) {
                    val c = outcome.chunk
                    println(listOf("product_queue_interval", policy, slow, outcome.state,
                        c.startMs, c.endMs, c.submittedAt, outcome.started ?: -1.0,
                        outcome.at).joinToString("\t"))
                }
                println("product_queue policy=$policy slow=$slow drops_ms=$droppedMs merges=$merges accounted=${ordered.size} age_ms=5000 simulated=true")
            }
        }
        assertTrue("pause policy must not lose more audio in the frozen overload trace",
            slowDrops.getValue("pause_600_max_5000") <= slowDrops.getValue("fixed_5000"))
    }
}
