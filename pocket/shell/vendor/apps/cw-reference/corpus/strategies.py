"""Experimental gain-invariant, dit-length integration front end; not production."""
import math
from statistics import median
from probabilistic import decode_logs
from reference import power
from reference import analyze


def matched(samples, rate=8000, tone=700, wpm=20):
    hop = round(rate * .01)
    width = round(rate * 1.2 / wpm)
    if not 5 <= wpm <= 30 or len(samples) > rate * 30:
        raise ValueError('bounded fixed initial speed required')
    # Centered integration preserves timestamps; no live-causality claim.
    powers, noises = [], []
    for start in range(0, len(samples), hop):
        center = start + hop // 2
        lo, hi = center - width // 2, center + (width - width // 2)
        block = [0.] * max(0, -lo) + samples[max(0, lo):min(len(samples), hi)] + [0.] * max(0, hi-len(samples))
        powers.append(power(block, rate, tone))
        noises.append((power(block, rate, tone-150) + power(block, rate, tone+150))/2)
    if not powers:
        return decode_logs([], [])
    sorted_power = sorted(powers)
    signal = median(sorted_power[int(len(sorted_power)*.8):])
    noise = max(1e-12, median(noises))
    if signal < noise * 4:
        return decode_logs([], [])
    active = [i for i, value in enumerate(powers) if value > signal*.25]
    if not active or median(powers[i]/max(noises[i],1e-12) for i in active) < 4:
        return decode_logs([], [])
    on, off = [], []
    for value in powers:
        amplitude = math.sqrt(max(0., value-noise) / max(signal-noise, 1e-12))
        idle = -.5 * (amplitude/.30)**2
        active = -.5 * ((amplitude-1)/.30)**2
        high = max(idle + math.log(.12), active + math.log(.88))
        mixture = high + math.log(math.exp(idle+math.log(.12)-high) + math.exp(active+math.log(.88)-high))
        scale = max(idle, mixture)
        off.append(max(-12, idle-scale))
        on.append(max(-12, mixture-scale))
    return decode_logs(on, off, wpm=wpm)


def agreement(readings):
    """Two nonempty normalized texts must agree; otherwise abstain."""
    counts = {}
    for text in readings:
        text = ''.join(char for char in text.upper() if char.isascii() and char.isalnum())
        if text:
            counts[text] = counts.get(text, 0) + 1
    if not counts:
        return None
    text = max(counts, key=counts.get)
    return text if counts[text] >= 2 else None


def route(samples, rate=8000, tone=700, wpm=20):
    """Frozen development heuristic: choose a method without transcript access."""
    count = round(rate*.01)
    padded = samples + [0.] * ((-len(samples)) % count)
    items = analyze(padded, rate, tone, 10)
    levels = sorted(item.tone_power for item in items)
    signal = median(levels[int(len(levels)*.8):]) if levels else 0.
    noise = max(1e-12, median(item.noise_power for item in items)) if items else 1e-12
    if signal < .002 or signal/noise < 12:
        return 'matched', dict(signal_power=signal, probe_ratio=signal/noise, reason='low absolute power or low probe ratio')
    threshold = max(signal*.25, noise*4)
    durations, length = [], 0
    for item in items:
        if item.tone_power >= threshold:
            length += .01
        elif length:
            durations.append(length)
            length = 0
    if length:
        durations.append(length)
    dit = 1.2/wpm
    residual = math.sqrt(sum(min((d/dit-1)**2,(d/dit-3)**2) for d in durations)/len(durations)) if durations else 0.
    return ('probabilistic' if residual > .2 else 'fixed'), dict(
        signal_power=signal, probe_ratio=signal/noise, timing_rms_dits=residual,
        reason='timing residual above0.2dit' if residual > .2 else 'strong regular keying')
