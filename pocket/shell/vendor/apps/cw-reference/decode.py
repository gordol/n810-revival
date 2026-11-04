"""Fixed-speed offline PCM-to-Morse-text reference."""
import argparse
import math
import os
import struct
import wave
from itertools import islice
from contextlib import contextmanager
from concurrent.futures import CancelledError
from reference import Evidence, analyze, mark_symbol

_CODES = '.- -... -.-. -.. . ..-. --. .... .. .--- -.- .-.. -- -. --- .--. --.- .-. ... - ..- ...- .-- -..- -.-- --.. ----- .---- ..--- ...-- ....- ..... -.... --... ---.. ----.'
MORSE = dict(zip(_CODES.split(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'))


def decode_evidence(evidence, rate=8000, wpm=20, threshold=0.7, min_power=0.002):
    """Decode contiguous windows; '?' preserves malformed marks/gaps/codes."""
    if (not all(math.isfinite(x) for x in (rate, wpm, threshold, min_power))
            or rate <= 0 or wpm <= 0 or not -1 < threshold < 1 or min_power < 0):
        raise ValueError('invalid decoder configuration')
    def runs():
        expected, previous, length = 0, None, 0
        for item in evidence:
            if item.start_sample != expected or item.end_sample <= expected:
                raise ValueError('evidence must be contiguous from sample zero')
            if not all(math.isfinite(x) for x in (item.score, item.tone_power, item.noise_power)):
                raise ValueError('nonfinite evidence')
            on = item.score >= threshold and item.tone_power >= min_power
            if previous is not None and on != previous:
                yield previous, length
                length = 0
            length += item.end_sample - item.start_sample
            expected, previous = item.end_sample, on
        if previous is not None:
            yield previous, length
    text, code = [], ''
    def flush():
        nonlocal code
        if code:
            text.append(MORSE.get(code, '?'))
            code = ''
    gap = None
    for on, length in runs():
        if not on:
            gap = length / rate * wpm / 1.2
            continue
        if code and gap is not None:
            if gap < 2:
                if not 0.5 <= gap < 1.5:
                    code += '?'
            else:
                flush()
                if gap >= 5:
                    text.append(' ')
                elif not 2.5 <= gap < 3.5:
                    text.append('?')
        code += mark_symbol(length * 1000 / rate, 1200 / wpm)
        gap = None
    flush()
    return ''.join(text).strip()


def _configuration(rate, tone, wpm):
    if not math.isfinite(rate) or rate <= 0 or not math.isfinite(wpm) or wpm <= 0:
        raise ValueError('positive finite rate and WPM required')
    if not math.isfinite(tone) or not 0 < tone - 150 < tone + 150 < rate / 2:
        raise ValueError('tone and noise probes must fit inside Nyquist')
    count = round(rate / 100)
    if count < 2 or 1200 / wpm < 40:
        raise ValueError('10 ms windows require dit duration of at least 40 ms')
    return count


def _evidence(blocks, rate, tone, count, total, cancelled, progress):
    offset = 0
    for block in blocks:
        if cancelled is not None and cancelled():
            raise CancelledError('CW decode cancelled')
        if any(not math.isfinite(x) or abs(x) > 1 for x in block):
            raise ValueError('finite normalized PCM required')
        actual = len(block)
        if not actual:
            continue
        block.extend([0.] * (count - actual))
        item = analyze(block, rate, tone, 10)[0]
        yield Evidence(offset, offset + count, item.tone_power, item.noise_power, item.score)
        offset += count
        if progress is not None:
            progress(min(offset, total), total)
    if cancelled is not None and cancelled():
        raise CancelledError('CW decode cancelled')


def decode_samples(samples, rate=8000, tone=700, wpm=20, min_power=0.002,
                   *, cancelled=None, progress=None):
    """Decode sized finite mono PCM using one 10 ms working window."""
    count = _configuration(rate, tone, wpm)
    if cancelled is not None and cancelled():
        raise CancelledError('CW decode cancelled')
    iterator = iter(samples)
    blocks = iter(lambda: list(islice(iterator, count)), [])
    total = len(samples) + (-len(samples)) % count
    return decode_evidence(_evidence(blocks, rate, tone, count, total, cancelled, progress),
                           rate, wpm, min_power=min_power)


@contextmanager
def wav_evidence(path, tone=700, wpm=20, *, cancelled=None, progress=None,
                 max_seconds=30, max_frames=240000, max_bytes=1048576):
    """Yield (rate, evidence iterator) while the bounded mono WAV is open."""
    if any(not math.isfinite(x) or x <= 0 for x in (max_seconds, max_frames, max_bytes)):
        raise ValueError('positive finite WAV limits required')
    if cancelled is not None and cancelled():
        raise CancelledError('CW decode cancelled')
    with open(path, 'rb') as source:
        if os.fstat(source.fileno()).st_size > max_bytes:
            raise ValueError('WAV exceeds byte limit')
        with wave.open(source, 'rb') as audio:
            if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or audio.getcomptype() != 'NONE':
                raise ValueError('uncompressed mono 16-bit PCM WAV required')
            rate, frames = audio.getframerate(), audio.getnframes()
            count = _configuration(rate, tone, wpm)
            if rate > 48000 or frames > max_frames or frames / rate > max_seconds:
                raise ValueError('WAV exceeds duration/sample/rate limit')
            def blocks():
                remaining = frames
                while remaining:
                    if cancelled is not None and cancelled():
                        raise CancelledError('CW decode cancelled')
                    size = min(count, remaining)
                    raw = audio.readframes(size)
                    if len(raw) != size * 2:
                        raise ValueError('truncated WAV')
                    remaining -= size
                    yield [x[0] / 32768 for x in struct.iter_unpack('<h', raw)]
            yield rate, _evidence(blocks(), rate, tone, count, frames, cancelled, progress)


def decode_wav(path, tone=700, wpm=20, min_power=0.002, *, cancelled=None,
               progress=None, max_seconds=30, max_frames=240000, max_bytes=1048576):
    """Stream bounded mono S16 PCM WAV; callbacks run on the calling thread."""
    with wav_evidence(path, tone, wpm, cancelled=cancelled, progress=progress,
                      max_seconds=max_seconds, max_frames=max_frames, max_bytes=max_bytes) as (rate, items):
        return decode_evidence(items, rate, wpm, min_power=min_power)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wav')
    parser.add_argument('--tone', type=float, default=700)
    parser.add_argument('--wpm', type=float, default=20)
    parser.add_argument('--min-power', type=float, default=0.002)
    parser.add_argument('--auto', action='store_true', help='Suggest pitch/speed from the first five seconds')
    parser.add_argument('--probabilistic', action='store_true', help='Experimental bounded duration/likelihood beam decoder')
    args = parser.parse_args()
    try:
        if args.auto:
            import sys
            from acquire import suggest_wav
            suggestion = suggest_wav(args.wav)
            args.tone, args.wpm = suggestion['tone'], suggestion['wpm']
            print(f"Suggested {args.tone:g} Hz, {args.wpm:g} WPM; timing cost "
                  f"{suggestion['timing_cost']:.4f}; speed candidates "
                  f"{suggestion['speed_candidates']}", file=sys.stderr)
            if suggestion['ambiguous']:
                raise ValueError('ambiguous speed: supply --tone and --wpm without --auto')
        if args.probabilistic:
            import sys
            from probabilistic import decode_wav as probabilistic_wav
            result = probabilistic_wav(args.wav, tone=args.tone, wpm=args.wpm, min_power=args.min_power)
            print(result.text)
            print(f'Uncertain: {result.uncertain}; model score margin: {result.score_margin}; '
                  f'alternatives: {[candidate.text for candidate in result.alternatives]}', file=sys.stderr)
        else:
            print(decode_wav(args.wav, args.tone, args.wpm, args.min_power))
    except (ValueError, OSError, wave.Error) as error:
        parser.exit(2, f'{error}\n')


if __name__ == '__main__':
    main()
