"""Shared terminal colors for N810 radio tab bars and list selections."""
import curses
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location('radio_theme', Path(__file__).with_name('n810-radio-theme.py'))
theme = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(theme)

colored = False


def init_screen(win):
    global colored
    colored = False
    try:
        if not curses.has_colors(): return
        curses.start_color()
        if curses.COLORS < 8 or curses.COLOR_PAIRS <= 14: return
        try:
            curses.use_default_colors(); background=-1
        except curses.error:
            background=curses.COLOR_BLACK
        theme.activate()
        background=theme.color('background')
        curses.init_pair(11,background,theme.color('text'))
        curses.init_pair(12,theme.color('accent'),background)
        curses.init_pair(13,theme.color('text'),background)
        curses.init_pair(14,theme.color('text'),background)
        win.bkgd(' ',curses.color_pair(14))
        colored = True
    except curses.error:
        pass


def tab_styles(active):
    if colored:
        if active: return curses.color_pair(12)|curses.A_BOLD, curses.color_pair(12)|curses.A_BOLD
        return curses.color_pair(13), curses.color_pair(14)
    return (curses.A_BOLD, curses.A_REVERSE|curses.A_BOLD) if active else (curses.A_NORMAL,curses.A_NORMAL)


def selection():
    return curses.color_pair(11)|curses.A_BOLD if colored else curses.A_REVERSE


def label():
    return curses.A_BOLD


def border():
    return curses.A_NORMAL


def accent():
    return curses.color_pair(12)|curses.A_BOLD if colored else curses.A_BOLD
