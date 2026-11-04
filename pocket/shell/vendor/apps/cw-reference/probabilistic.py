"""Bounded segmental beam decoder using explicit duration/observation models."""
from dataclasses import dataclass
import math
from typing import Optional
from concurrent.futures import CancelledError
from statistics import median
from decode import MORSE, wav_evidence

PREFIXES = {code[:i] for code in MORSE for i in range(1, len(code) + 1)}


@dataclass(frozen=True)
class Candidate:
    text: str
    log_score: float


@dataclass(frozen=True)
class Result:
    text: str
    alternatives: tuple
    score_margin: Optional[float]
    uncertain: bool
    frames: int


def _logadd(a, b):
    high = max(a, b)
    return high + math.log(math.exp(a - high) + math.exp(b - high))


def observation_logs(evidence, *, min_power=.002, fade_probability=.12):
    """Lognormal power emissions with a key-down fade mixture; not calibrated."""
    if not 0 < fade_probability < 1 or not math.isfinite(min_power) or min_power <= 0:
        raise ValueError('invalid observation model')
    if not evidence:
        return [], []
    if any(not all(math.isfinite(v) and v >= 0 for v in (e.tone_power, e.noise_power))
           for e in evidence):
        raise ValueError('finite nonnegative powers required')
    levels = sorted(e.tone_power for e in evidence)
    signal = median(levels[max(0, int(len(levels) * .8)):])
    noise = max(1e-9, median(e.noise_power for e in evidence))
    if signal < min_power or signal < noise * 4:
        return [], []
    # Common normalizing constants and log-Jacobians cancel between states.
    on, off = [], []
    for item in evidence:
        value = math.log(max(noise * .1, item.tone_power))
        idle = -.5 * ((value - math.log(noise)) / 1.2)**2
        active = -.5 * ((value - math.log(signal)) / 1.2)**2
        marked = _logadd(math.log1p(-fade_probability) + active,
                         math.log(fade_probability) + idle)
        scale = max(idle, marked)
        on.append(max(-12., marked - scale))
        off.append(max(-12., idle - scale))
    return on, off


def decode_logs(on, off, *, wpm=20, frame_ms=10, beam=24, max_frames=3000,
                cancelled=None, progress=None, character_prior=None, duration_frames=None):
    """Semi-Markov search; durations Gaussian, symbols constrained by Morse tree."""
    if (not isinstance(beam, int) or not isinstance(max_frames, int) or not 1 <= max_frames <= 3000
            or len(on) != len(off) or len(on) > max_frames or not 1 <= beam <= 64
            or not all(math.isfinite(v) for v in (*on, *off))
            or not math.isfinite(wpm) or not 5 <= wpm <= 30 or frame_ms != 10):
        raise ValueError('bounded finite 10 ms observations, 5–30 WPM and beam 1–64 required')
    if cancelled is not None and cancelled():
        raise CancelledError('CW probabilistic decode cancelled')
    if character_prior is not None and not callable(character_prior):
        raise ValueError('character_prior must be callable')

    def language_score(prefix, character):
        if character_prior is None:
            return 0.
        value = character_prior(prefix, character)
        if not math.isfinite(value) or abs(value) > 1.5:
            raise ValueError('character prior must be finite and bounded to +/-1.5')
        return value

    labels = ('dot', 'dash', 'intra', 'letter', 'word')
    if duration_frames is not None:
        if (set(duration_frames) != set(labels) or
                any(not math.isfinite(v) or not 1 <= v <= 250 for v in duration_frames.values()) or
                not duration_frames['dot'] < duration_frames['dash'] or
                not duration_frames['intra'] < duration_frames['letter'] < duration_frames['word']):
            raise ValueError('ordered bounded dot/dash and gap duration means required')
    count = len(on)
    if not count:
        return Result('', (), None, True, 0)
    # Only clip certain exterior silence; ambiguous observations remain in search.
    active = [i for i in range(count) if on[i] > off[i]]
    if not active:
        return Result('', (), None, True, count)
    first, last = active[0], active[-1] + 1
    dit_frames = 1200 / wpm / frame_ms
    longest_mark = duration_frames['dash'] if duration_frames else 3*dit_frames
    if len(active) == last-first and last-first > math.ceil(longest_mark*1.45):
        # Do not invent key-up gaps to explain a continuous unmodulated carrier.
        return Result('', (), None, True, count)
    on, off = on[first:last], off[first:last]
    length = len(on)
    sums = []
    for values in (on, off):
        prefix = [0.]
        for value in values:
            prefix.append(prefix[-1] + value)
        sums.append(prefix)
    dit = 1200 / wpm / frame_ms
    options = {}
    for label, units in zip(labels, (1, 3, 1, 3, 7)):
        mean = duration_frames[label] if duration_frames else units * dit
        sigma = max(1., .18 * mean)
        lo, hi = max(1, math.floor(mean - 2.5 * sigma)), math.ceil(mean + 2.5 * sigma)
        weights = [(duration, -.5 * ((duration - mean) / sigma)**2)
                   for duration in range(lo, hi + 1)]
        normalizer = math.log(sum(math.exp(score) for _, score in weights))
        options[label] = [(duration, score - normalizer) for duration, score in weights]
    # A bounded bucket for each possible segment end; key=(next_on, code, text).
    pending = {0: {(True, '', ''): 0.}}
    finals = {}
    for start in range(length + 1):
        if cancelled is not None and cancelled():
            raise CancelledError('CW probabilistic decode cancelled')
        bucket = pending.pop(start, {})
        states = sorted(bucket.items(), key=lambda item: item[1], reverse=True)[:beam]
        for (next_on, code, text), score in states:
            if start == length:
                if code in MORSE:
                    score += language_score(text, MORSE[code])
                    value = (text + MORSE[code]).strip()
                elif not code:
                    value = text.strip()
                else:
                    continue
                finals[value] = max(finals.get(value, -math.inf), score)
                continue
            choices = ((1, '.'), (3, '-')) if next_on else ((1, ''), (3, 'letter'), (7, 'word'))
            for units, symbol in choices:
                new_code, new_text = code, text
                context_score = 0.
                if next_on:
                    new_code += symbol
                    if new_code not in PREFIXES:
                        continue
                elif symbol:
                    if code not in MORSE:
                        continue
                    context_score = language_score(text, MORSE[code])
                    new_text += MORSE[code]
                    if symbol == 'word':
                        context_score += language_score(new_text, ' ')
                        new_text += ' '
                    new_code = ''
                label = ('dot' if units == 1 else 'dash') if next_on else {1:'intra',3:'letter',7:'word'}[units]
                for duration, prior in options[label]:
                    end = start + duration
                    if end > length:
                        break
                    prefix = sums[0 if next_on else 1]
                    value = score + context_score + prior - math.log(len(choices)) + prefix[end] - prefix[start]
                    target = pending.setdefault(end, {})
                    key = (not next_on, new_code, new_text)
                    if value > target.get(key, -math.inf):
                        target[key] = value
                    if len(target) > beam * 2:
                        pending[end] = dict(sorted(target.items(), key=lambda item: item[1], reverse=True)[:beam])
        if progress is not None:
            progress(start, length)
    if not finals:
        return Result('?', (), None, True, count)
    ranked = sorted(finals.items(), key=lambda item: item[1], reverse=True)[:5]
    alternatives = tuple(Candidate(text, score) for text, score in ranked)
    margin = ranked[0][1] - ranked[1][1] if len(ranked) > 1 else None
    return Result(ranked[0][0], alternatives, margin, margin is None or margin < 3., count)


def decode_evidence(evidence, *, rate=8000, wpm=20, beam=24, min_power=.002,
                    cancelled=None, progress=None):
    """Consume at most 3000 contiguous equal-duration frames of real-audio power."""
    items = []
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError('positive finite sample rate required')
    end, width = 0, None
    for item in evidence:
        if len(items) == 3000:
            raise ValueError('probabilistic preview exceeds 3000 frames')
        if item.start_sample != end or item.end_sample <= end:
            raise ValueError('contiguous evidence required')
        size = item.end_sample - item.start_sample
        if size != round(rate * .01):
            raise ValueError('10 ms evidence required')
        if width is not None and size != width:
            raise ValueError('equal-duration evidence required')
        end, width = item.end_sample, size
        items.append(item)
        if cancelled is not None and cancelled():
            raise CancelledError('CW probabilistic decode cancelled')
    on, off = observation_logs(items, min_power=min_power)
    return decode_logs(on, off, wpm=wpm, beam=beam, cancelled=cancelled, progress=progress)


def decode_wav(path, tone=700, wpm=20, min_power=.002, *, beam=24,
               cancelled=None, progress=None):
    """Read bounded mono audio; progress callback receives (phase, done, total)."""
    capture_progress = (lambda n, total: progress('analysis', n, total)) if progress else None
    search_progress = (lambda n, total: progress('search', n, total)) if progress else None
    with wav_evidence(path, tone, wpm, cancelled=cancelled,
                      progress=capture_progress) as (rate, items):
        return decode_evidence(items, rate=rate, wpm=wpm, beam=beam, min_power=min_power,
                               cancelled=cancelled, progress=search_progress)
