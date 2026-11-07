import math
import random
import unittest
from reference import analyze, marks, mark_symbol, power


class ReferenceTests(unittest.TestCase):
    def test_power_scale_and_rejection(self):
        tone = [0.4 * math.sin(2 * math.pi * 700 * i / 8000) for i in range(160)]
        self.assertAlmostEqual(power(tone, 8000, 700), 0.08, places=10)
        self.assertLess(power(tone, 8000, 850), 1e-20)

    def test_silence_is_not_a_mark(self):
        evidence = analyze([0.0] * 480)
        self.assertEqual(marks(evidence), "")
        self.assertTrue(all(e.score == 0 for e in evidence))

    def test_seeded_noise_preserves_soft_values(self):
        rng = random.Random(810)
        evidence = analyze([rng.gauss(0, 0.1) for _ in range(8000)])
        self.assertTrue(all(math.isfinite(e.score) and -1 <= e.score <= 1 for e in evidence))
        self.assertTrue(all(e.noise_power > 0 for e in evidence))
        self.assertLess(sum(e.score >= 0.7 for e in evidence), 10)

    def test_dit_dah_with_noise_and_trailing_mark(self):
        rng = random.Random(6100)
        samples = []
        for on, milliseconds in [(False, 60), (True, 60), (False, 60), (True, 180)]:
            for _ in range(milliseconds * 8):
                i = len(samples)
                samples.append((0.4 * math.sin(2 * math.pi * 700 * i / 8000) if on else 0)
                               + rng.gauss(0, 0.02))
        self.assertEqual(marks(analyze(samples)), ".-")

    def test_timing_boundaries(self):
        for duration, symbol in [(29, "?"), (30, "."), (89, "."), (90, "?"),
                                 (149, "?"), (150, "-"), (209, "-"), (210, "?")]:
            self.assertEqual(mark_symbol(duration, 60), symbol)

    def test_incomplete_capture_and_invalid_configuration(self):
        for args in [([0] * 161,), ([0] * 160, 8000, 50)]:
            with self.assertRaises(ValueError):
                analyze(*args)
        with self.assertRaises(ValueError):
            marks([], wpm=0)


if __name__ == "__main__":
    unittest.main()
