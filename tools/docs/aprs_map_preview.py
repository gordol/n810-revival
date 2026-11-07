#!/usr/bin/env python3
"""Display the real APRS map with invented stations, entirely offline.

Supply the existing public geography pack directory with --maps PATH.
Use a terminal of at least 100 columns by 30 rows. p toggles the packet panel,
x toggles the inspector, Tab changes panel focus, arrows navigate, +/- zoom,
and q exits. All packet positions are fictional points around Mount Rainier.
The map files are read-only inputs; this fixture reads no station history and
opens no service or radio connection. --describe prints the fixture inventory.
"""
import argparse
import curses
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('docs_aprs', ROOT/'tools/docs/aprs_preview.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
viewer = fixture.viewer

PACKETS = [
    ('12:00:00', 'DEMO1', '!4650.00N/12155.00W>West trailhead'),
    ('12:00:10', 'DEMO2', '!4654.00N/12140.00W>North lookout'),
    ('12:00:20', 'DEMO3', '!4643.00N/12143.00W>South camp'),
    ('12:00:30', 'DEMO4', '!4650.00N/12130.00W>East trailhead'),
    ('12:00:40', 'DEMO5', '!4657.00N/12153.00W>Ridge station'),
    ('12:00:50', 'DEMO2', '>Fictional status report'),
    ('12:01:00', 'DEMO1', '!4651.00N/12152.00W>Walking toward the ridge'),
]


def run(window, maps, show_packets):
    curses.curs_set(0)
    window.keypad(True)
    viewer.map_style.init_screen(window)
    state = viewer.State()
    viewer.init_map(state, str(maps), 'next', 'color')
    state.center = [46.85, -121.75]
    state.selected = 0
    state.my_call = 'DEMO1'
    state.debug = False
    state.debug_key = None
    state.debug_record = None
    state.debug_scroll = 0
    state.map_target = None
    state.roads = True
    state.terrain = True
    state.help = False
    state.auto_fit = False
    state.focus = 'detail'
    for stamp, call, payload in PACKETS:
        state.add(f'{stamp} {call}>APDEMO ctl=03 pid=f0 {payload}', historical=True)
    state.status = 'OFFLINE DEMO: fictional stations and packets'
    state.transport_read_time = None
    panels = viewer.trial_panels(state)
    if show_packets:
        panels.toggle('packets')
    span = 80.0
    while True:
        # Supply each selected packet's invented raw capture directly. This
        # keeps inspector rendering entirely separate from snapshot sockets.
        packet = viewer.selected_row(state)
        if packet:
            state.debug_key = packet['raw']
            frame = b'\0' + fixture.address('APDEMO') + fixture.address(packet['call'], last=True) + b'\x03\xf0' + packet['payload'].encode()
            state.debug_record = {'time': '2026-11-04T'+packet['time']+'+00:00', 'frame': frame.hex()}
        viewer.draw(window, state, span)
        viewer.finish_frame(window, state)
        key = window.getch()
        if key in (ord('q'), 27): break
        if key == curses.KEY_RESIZE:
            viewer.erase_view(window, state)
        elif viewer.trial_panel_key(state,key): pass
        elif key in (curses.KEY_DOWN,curses.KEY_UP) and panels.focus != 'map':
            viewer.move_selection(state, 1 if key==curses.KEY_DOWN else -1)
        elif key in (curses.KEY_LEFT,curses.KEY_RIGHT,curses.KEY_DOWN,curses.KEY_UP):
            if key in (curses.KEY_LEFT,curses.KEY_RIGHT):state.center[1] += (-1 if key==curses.KEY_LEFT else 1)*.05
            else:state.center[0] += (-1 if key==curses.KEY_DOWN else 1)*.04
        elif key in (ord('+'),ord('=')):span=max(20,span/1.5)
        elif key==ord('-'):span=min(100,span*1.5)
        elif key==ord('t'):state.terrain=not state.terrain
        elif key==ord('r'):state.roads=not state.roads


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--maps', type=Path)
    parser.add_argument('--packets', action='store_true')
    parser.add_argument('--describe', action='store_true')
    args=parser.parse_args()
    if args.describe:
        print('Offline APRS documentation fixture')
        print(f'{len(PACKETS)} invented packets / {len({p[1] for p in PACKETS})} fictional stations')
        print('Geography: public Mount Rainier region; station positions invented.')
    else:
        if args.maps is None:parser.error('--maps is required for a map view')
        curses.wrapper(run, args.maps, args.packets)
