#!/usr/bin/env python3
"""Draw the APRS packet inspector with fictional data, entirely offline.

Run from any directory in a terminal at least 100 columns by 40 rows.
Press any key to exit. This calls the real viewer's drawing functions directly;
it opens no receiver, service socket, saved history, or personal map pack.
"""
from pathlib import Path
import curses
import importlib.util

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'pocket/shell/vendor/packet-console/n810-aprs-view.py'
spec = importlib.util.spec_from_file_location('aprs_preview_view', SOURCE)
viewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(viewer)


def address(call, last=False):
    return bytes(ord(c) << 1 for c in call.ljust(6)) + bytes([0x61 if last else 0x60])


def preview(window):
    curses.curs_set(0)
    viewer.map_style.init_screen(window)
    state = viewer.State()
    state.map_engine_name = 'legacy'
    state.map_engine = None
    state.atlas = viewer._map.Atlas('/nonexistent-docs-map-directory')
    state.center = [0.0, 0.0]
    state.map_target = None
    state.roads = False
    state.help = False
    state.auto_fit = False
    state.debug = True
    state.debug_scroll = 0
    state.focus = 'detail'
    # DEMO labels and message contents are invented for documentation.
    for stamp, call, payload in [
        ('12:00:00', 'DEMO1', '>Offline documentation example'),
        ('12:00:05', 'DEMO2', '>Second fictional station'),
        ('12:00:10', 'DEMO1', '>Packet inspector demonstration'),
    ]:
        state.add(f'{stamp} {call}>APDEMO ctl=03 pid=f0 {payload}', historical=True)
    state.status = 'OFFLINE DOCUMENTATION FIXTURE | fictional packets'
    packet = state.packets[0]
    state.debug_key = packet['raw']  # Supply the capture directly; no socket lookup.
    frame = b'\0' + address('APDEMO') + address('DEMO1', last=True) + b'\x03\xf0' + packet['payload'].encode()
    state.debug_record = {'time': '2026-11-04T12:00:10+00:00', 'frame': frame.hex()}
    while True:
        viewer.draw(window, state, 160)
        viewer.finish_frame(window, state)
        window.refresh()
        if window.getch() != curses.KEY_RESIZE:
            break


if __name__ == '__main__':
    curses.wrapper(preview)
