import math
import random
import struct
import tempfile
import unittest
import wave
from concurrent.futures import CancelledError
from pathlib import Path
from decode import MORSE, decode_samples, decode_wav, decode_evidence
from reference import Evidence


def fixture(text, rate=8000, wpm=20, noise=0.01, seed=810, tone=700):
    """Deterministic synthetic PCM, standard 1/3/7-unit spacing."""
    codes = {v: k for k, v in MORSE.items()}
    rng = random.Random(seed)
    samples = []
    def append(on, units):
        for _ in range(round(rate * 1.2 / wpm * units)):
            i = len(samples)
            samples.append(max(-1, min(1, (0.4 * math.sin(2 * math.pi * tone * i / rate)
                                         if on else 0) + rng.gauss(0, noise))))
    append(False, 3)
    for wi, word in enumerate(text.split()):
        if wi:
            append(False, 7)
        for ci, char in enumerate(word):
            if ci:
                append(False, 3)
            for mi, mark in enumerate(codes[char]):
                if mi:
                    append(False, 1)
                append(True, 1 if mark == '.' else 3)
    return samples


def write_wav(path, samples, rate=8000):
    with wave.open(str(path), 'wb') as audio:
        audio.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        audio.writeframes(b''.join(struct.pack('<h', round(x * 32767)) for x in samples))


class DecoderTests(unittest.TestCase):
    def test_wav_progress_cancel_limits_and_truncation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.wav'
            write_wav(path, fixture('SOS') + [0.] * 3)
            updates = []
            with wave.open(str(path), 'rb') as audio:
                total = audio.getnframes()
            self.assertEqual(decode_wav(path, progress=lambda n, t: updates.append((n, t))), 'SOS')
            self.assertEqual(updates[-1], (total, total))
            self.assertTrue(all(a[0] < b[0] for a, b in zip(updates, updates[1:])))
            updates.clear()
            with self.assertRaises(CancelledError):
                decode_wav(path, cancelled=lambda: len(updates) >= 2,
                           progress=lambda n, t: updates.append((n, t)))
            self.assertEqual(len(updates), 2)
            for limits in ({'max_frames': 80}, {'max_seconds': .01}, {'max_bytes': 44}):
                with self.assertRaisesRegex(ValueError, 'limit'):
                    decode_wav(path, **limits)
            path.write_bytes(path.read_bytes()[:-2])
            with self.assertRaisesRegex(ValueError, 'truncated'):
                decode_wav(path)

    def test_sample_stream_avoids_whole_input_copy(self):
        class IndexedOnly:
            def __len__(self):
                return 160
            def __iter__(self):
                yield from [0.] * 160
            def __getitem__(self, key):
                raise AssertionError('whole input slicing is not supported')
        self.assertEqual(decode_samples(IndexedOnly()), '')

    def test_cooperative_cancel_and_progress(self):
        updates = []
        with self.assertRaises(CancelledError):
            decode_samples([0.] * 800, cancelled=lambda: len(updates) >= 2,
                           progress=lambda done, total: updates.append((done, total)))
        self.assertEqual(updates, [(80, 800), (160, 800)])
        updates.clear()
        self.assertEqual(decode_samples([0.] * 81,
                         progress=lambda done, total: updates.append((done, total))), '')
        self.assertEqual(updates, [(80, 160), (160, 160)])
        with self.assertRaises(CancelledError):
            decode_samples([], cancelled=lambda: True)

    def test_recording_to_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'known.wav'
            write_wav(path, fixture('CQ N0DEM SOS 73'))
            self.assertEqual(decode_wav(path), 'CQ N0DEM SOS 73')

    def test_alphabet_digits_and_fixed_speeds(self):
        for speed in (10, 15, 20, 25, 30):
            text = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789'
            self.assertEqual(decode_samples(fixture(text, wpm=speed), wpm=speed), text)

    def test_no_text_on_silence_and_seeded_low_noise(self):
        self.assertEqual(decode_samples([0.] * 8000), '')
        for seed in range(10):
            rng = random.Random(seed)
            self.assertEqual(decode_samples([rng.gauss(0, 0.02) for _ in range(8000)]), '')

    def test_unknown_mark_and_discontinuity(self):
        self.assertEqual(decode_evidence([Evidence(0, 960, .08, 0., 1.)]), '?')
        with self.assertRaises(ValueError):
            decode_evidence([Evidence(1, 160, .08, 0., 1.)])

    def test_empty_partial_and_invalid(self):
        self.assertEqual(decode_samples([]), '')
        self.assertEqual(decode_samples([0.] * 81), '')
        for samples in ([float('nan')], [1.1]):
            with self.assertRaises(ValueError):
                decode_samples(samples)
        with self.assertRaises(ValueError):
            decode_samples([], wpm=31)

    def test_reject_stereo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stereo.wav'
            with wave.open(str(path), 'wb') as audio:
                audio.setparams((2, 2, 8000, 0, 'NONE', 'not compressed'))
                audio.writeframes(bytes(320))
            with self.assertRaises(ValueError):
                decode_wav(path)


if __name__ == '__main__':
    unittest.main()
