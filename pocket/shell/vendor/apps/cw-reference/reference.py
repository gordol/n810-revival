"""Offline scalar CW evidence and fixed-speed timing reference; no I/O backend."""
from dataclasses import dataclass
import math
from statistics import median
from concurrent.futures import CancelledError


@dataclass(frozen=True)
class Evidence:
    start_sample: int
    end_sample: int
    tone_power: float
    noise_power: float
    score: float


def power(samples, rate, frequency):
    """Rectangular-window tone mean-square estimate in normalized PCM units."""
    if not samples or not 0 < frequency < rate / 2:
        raise ValueError("nonempty window and frequency inside Nyquist required")
    coefficient = 2 * math.cos(2 * math.pi * frequency / rate)
    previous = before = 0.0
    for sample in samples:
        current = sample + coefficient * previous - before
        before, previous = previous, current
    magnitude = previous**2 + before**2 - coefficient * previous * before
    return max(0.0, 2 * magnitude / len(samples)**2)


def analyze(samples, rate=8000, tone=700, window_ms=20, *, cancelled=None, progress=None):
    """Nonoverlapping windows; incomplete final window is explicitly rejected."""
    count = round(rate * window_ms / 1000)
    if rate <= 0 or count < 2 or len(samples) % count:
        raise ValueError("positive rate and complete windows required")
    if not 0 < tone - 150 < tone + 150 < rate / 2:
        raise ValueError("tone and noise probes must fit inside Nyquist")
    result = []
    for start in range(0, len(samples), count):
        if cancelled is not None and cancelled():
            raise CancelledError('CW decode cancelled')
        block = samples[start:start + count]
        signal = power(block, rate, tone)
        noise = median(power(block, rate, f) for f in (tone - 150, tone + 150))
        score = (signal - noise) / (signal + noise + 1e-15)
        result.append(Evidence(start, start + count, signal, noise, score))
        if progress is not None:
            progress(start + count, len(samples))
    return result


def mark_symbol(duration_ms, dit_ms):
    """Half-open tolerance bands; ambiguous/invalid durations remain unknown."""
    if dit_ms <= 0:
        raise ValueError("positive dit duration required")
    units = duration_ms / dit_ms
    if 0.5 <= units < 1.5:
        return "."
    if 2.5 <= units < 3.5:
        return "-"
    return "?"


def marks(evidence, rate=8000, wpm=20, threshold=0.7):
    """Threshold only this timing baseline; return marks, not decoded text."""
    if rate <= 0 or wpm <= 0 or not -1 < threshold < 1:
        raise ValueError("invalid timing configuration")
    runs, start, end = [], None, None
    expected = 0
    for item in evidence:
        if item.start_sample != expected or item.end_sample <= expected:
            raise ValueError("evidence must be contiguous from sample zero")
        expected = item.end_sample
        if item.score >= threshold:
            if start is None:
                start = item.start_sample
            end = item.end_sample
        elif start is not None:
            runs.append(mark_symbol((end - start) * 1000 / rate, 1200 / wpm))
            start = None
    if start is not None:
        runs.append(mark_symbol((end - start) * 1000 / rate, 1200 / wpm))
    return "".join(runs)
