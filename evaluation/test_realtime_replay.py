from array import array
import unittest

from realtime_replay import PcmRing, BYTES_MS, is_exact_digital_silence


class RingTests(unittest.TestCase):
    def test_exact_zero_check_does_not_gate_quiet_audio(self):
        self.assertTrue(is_exact_digital_silence(bytes(320)))
        self.assertFalse(is_exact_digital_silence(bytes([1]) + bytes(319)))

    def collect(self, ring, data):
        out = []
        for start in range(0, len(data), 640):
            result = ring.push(data[start:start+640])
            if result:
                out.append(result)
        tail = ring.flush()
        if tail:
            out.append(tail)
        return out

    def test_fixed_preserves_all_pcm_and_short_tail(self):
        data = array('h', (i % 32000 for i in range(16000*7+123))).tobytes()
        ring = PcmRing(3000)
        rows = self.collect(ring, data)
        self.assertEqual(b''.join(r['pcm'] for r in rows), data)
        self.assertLessEqual(ring.high_water_bytes, 3020 * BYTES_MS)

    def test_silence_does_not_gate(self):
        rows = self.collect(PcmRing(3000, adaptive=True), bytes(7000*BYTES_MS))
        self.assertEqual([r['end_ms'] for r in rows], [3000, 6000, 7000])
        self.assertEqual(rows[0]['cut_reason'], 'target_fallback')

    def test_quiet_boundary_and_no_audio_loss(self):
        data = (array('h', [1000]*16000*3).tobytes() + bytes(100*BYTES_MS)
                + array('h', [1000]*16000).tobytes())
        rows = self.collect(PcmRing(3000, adaptive=True), data)
        self.assertEqual(rows[0]['cut_reason'], 'low_energy')
        self.assertTrue(3000 <= rows[0]['end_ms'] <= 3100)
        self.assertEqual(b''.join(r['pcm'] for r in rows), data)
        self.assertTrue(all(r['end_ms']-r['start_ms'] <= 4000 for r in rows))

    def test_overlap_no_duplicate_only_tail(self):
        rows = self.collect(PcmRing(3000, 500), bytes(3000*BYTES_MS))
        self.assertEqual(len(rows), 1)


if __name__ == '__main__':
    unittest.main()
