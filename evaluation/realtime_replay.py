"""Paced PCM experiment. No speech gating, no retries, one engine, one pending job."""
from array import array
from dataclasses import asdict
from pathlib import Path
from queue import Queue, Empty, Full
from statistics import median
import json
import resource
import tempfile
import threading
import time
import wave

from e2e_protocol import parse_output
from terminology import Terminology

RATE = 16000
BYTES_MS = 32


def is_exact_digital_silence(pcm: bytes) -> bool:
    """Return true only for PCM whose every sample byte is exactly zero.

    This mirrors Android's transport-level check. It is intentionally stricter
    than an RMS/VAD threshold so quiet speech is still sent to Gemma.
    """
    return not pcm or not any(pcm)


class PcmRing:
    """Bounded sliding PCM buffer; retains only overlap and not-yet-cut audio."""
    def __init__(self, target_ms, overlap_ms=0, adaptive=False):
        if target_ms <= 0 or not 0 <= overlap_ms < target_ms:
            raise ValueError("invalid target/overlap")
        if adaptive and (not 2500 <= target_ms <= 3000 or overlap_ms >= target_ms - 300):
            raise ValueError("adaptive target must be 2500..3000ms with overlap below minimum cut")
        self.target = target_ms
        self.overlap = overlap_ms
        self.adaptive = adaptive
        self.ready_ms = min(4000, target_ms + 300) if adaptive else target_ms
        self.pcm = bytearray()
        self.start_ms = 0
        self.high_water_bytes = 0

    def push(self, pcm):
        self.pcm.extend(pcm)
        self.high_water_bytes = max(self.high_water_bytes, len(self.pcm))
        if len(self.pcm) > (self.ready_ms + 20) * BYTES_MS:
            raise BufferError("PCM ring exceeded capacity")
        if len(self.pcm) < self.ready_ms * BYTES_MS:
            return None
        cut = self.target
        reason = "fixed"
        if self.adaptive:
            samples = array("h", self.pcm)
            candidates = []
            for ms in range(self.target - 300, self.ready_ms - 19, 20):
                block = samples[ms * 16:(ms + 20) * 16]
                candidates.append((sum(v * v for v in block) / len(block), ms + 10))
            energy, candidate = min(candidates, key=lambda item: (item[0], abs(item[1] - self.target)))
            # Relative energy is a cut preference, never a speech/noise classifier.
            if energy < median(e for e, _ in candidates) * .6:
                cut, reason = candidate, "low_energy"
            else:
                reason = "target_fallback"
        return self._take(cut, reason)

    def _take(self, cut, reason):
        result = dict(start_ms=self.start_ms, end_ms=self.start_ms + cut,
                      pcm=bytes(self.pcm[:cut * BYTES_MS]), cut_reason=reason)
        consumed = cut - self.overlap
        del self.pcm[:consumed * BYTES_MS]
        self.start_ms += consumed
        return result

    def flush(self):
        # Include even short novel tails; never silently discard the last words.
        if len(self.pcm) <= self.overlap * BYTES_MS:
            return None
        result = dict(start_ms=self.start_ms, end_ms=self.start_ms + len(self.pcm) // BYTES_MS,
                      pcm=bytes(self.pcm), cut_reason="eof")
        self.pcm.clear()
        return result


def run(args):
    from gemma_replay import load_runtime, normalized_audio, write_chunk
    output = args.output or Path("evaluation/results/realtime.jsonl")
    output.parent.mkdir(parents=True, exist_ok=True)
    initialization = time.monotonic()
    runtime = load_runtime(args)
    initialization_ms = round((time.monotonic() - initialization) * 1000)
    terminology = Terminology()
    lock = threading.Lock()
    counts = dict(subtitle=0, transcription=0, invalid=0, no_speech=0, error=0, dropped=0, skipped_silence=0)
    try:
        with output.open("w") as report, tempfile.TemporaryDirectory(prefix="caption-rt-") as temp:
            def emit(record):
                with lock:
                    report.write(json.dumps(record, ensure_ascii=False) + "\n")
                    report.flush()

            emit(dict(type="config", initialization_ms=initialization_ms, model=str(args.model),
                      threads=args.threads, target_ms=args.window_ms, overlap_ms=args.overlap_ms,
                      adaptive=args.adaptive_cut, max_output_tokens=args.max_new_tokens,
                      hints=args.hints[:240], pending_capacity=1))
            emit(dict(type="prompt_config", system_profile=args.system_profile,
                      system_message=runtime.system_message))
            for pass_id, source in enumerate(args.audio * args.repeat, 1):
                normalized = Path(temp) / "normalized.wav"
                normalized_audio(source, normalized)
                pending = Queue(maxsize=1)
                done = threading.Event()
                stop = threading.Event()
                origin = time.monotonic()
                now_ms = lambda: round((time.monotonic() - origin) * 1000)

                def capture():
                    ring = PcmRing(args.window_ms, args.overlap_ms, args.adaptive_cut)
                    index = 0
                    max_late = 0

                    def submit(segment, final=False):
                        nonlocal index
                        index += 1
                        segment.update(index=index, source=str(source), **{"pass": pass_id},
                                       ready_ms=now_ms())
                        if is_exact_digital_silence(segment["pcm"]):
                            segment.pop("pcm")
                            segment.update(type="window", status="skipped_silence",
                                          reason="exact_zero_audio", output_ms=now_ms())
                            emit(segment)
                            counts["skipped_silence"] += 1
                            return
                        if final:
                            # Capture has ended: do not evict a whole pending
                            # sentence just to submit a tiny EOF remainder.
                            while not stop.is_set():
                                try:
                                    pending.put(segment, timeout=.1)
                                    return
                                except Full:
                                    continue
                            return
                        try:
                            pending.put_nowait(segment)
                        except Full:
                            try:
                                old = pending.get_nowait()
                            except Empty:
                                old = None
                            if old is not None:
                                emit({k: v for k, v in old.items() if k != "pcm"} |
                                     dict(type="window", status="dropped", reason="pending_replaced"))
                                counts["dropped"] += 1
                            pending.put_nowait(segment)

                    try:
                        with wave.open(str(normalized), "rb") as audio:
                            frames = 0
                            while not stop.is_set():
                                pcm = audio.readframes(320)
                                if not pcm:
                                    break
                                frames += len(pcm) // 2
                                if stop.wait(max(0, origin + frames / RATE - time.monotonic())):
                                    break
                                max_late = max(max_late, now_ms() - round(frames * 1000 / RATE))
                                segment = ring.push(pcm)
                                if segment:
                                    submit(segment)
                            tail = ring.flush()
                            if tail and not stop.is_set():
                                submit(tail, final=True)
                        emit(dict(type="capture_summary", **{"pass": pass_id},
                                  segments=index, audio_ms=round(frames * 1000 / RATE),
                                  max_capture_late_ms=max_late, ring_peak_bytes=ring.high_water_bytes))
                    except Exception as error:
                        counts["error"] += 1
                        emit(dict(type="capture_error", error=repr(error)))
                    finally:
                        done.set()

                producer = threading.Thread(target=capture, name="pcm-capture")
                producer.start()
                try:
                    while not done.is_set() or not pending.empty():
                        try:
                            segment = pending.get(timeout=.1)
                        except Empty:
                            continue
                        pcm = segment.pop("pcm")
                        started_ms = now_ms()
                        chunk = Path(temp) / "segment.wav"
                        record = segment | dict(type="window", inference_start_ms=started_ms,
                                                queue_wait_ms=started_ms-segment["ready_ms"])
                        try:
                            write_chunk(chunk, pcm)
                            raw = runtime.infer(chunk)
                            parsed = parse_output(raw, args.task)
                            record.update(asdict(parsed), raw=raw)
                            if parsed.status == "subtitle":
                                record.update(chinese_original=parsed.chinese,
                                              chinese=terminology.correct(parsed.english, parsed.chinese))
                        except Exception as error:
                            record.update(status="error", error=repr(error))
                        ended_ms = now_ms()
                        counts[record["status"]] += 1
                        record.update(output_ms=ended_ms, inference_ms=ended_ms-started_ms,
                                      end_to_output_ms=ended_ms-segment["end_ms"],
                                      start_to_output_ms=ended_ms-segment["start_ms"],
                                      peak_rss_mb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024, 1))
                        emit(record)
                finally:
                    stop.set()
                    producer.join(timeout=2)
            emit(dict(type="summary", **counts))
    finally:
        runtime.close()
    print(json.dumps(dict(output=str(output), **counts)), flush=True)
    return int(counts["error"] > 0)
