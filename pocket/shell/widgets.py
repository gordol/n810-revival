"""Small panel presentations; shared display clock and synthetic demo link state."""
import time_display
from collections import namedtuple

Link = namedtuple('Link','connected source')


class Clock:
    def __init__(self):self.minute=None;self.labels=()
    def read(self,timestamp):
        minute=(int(timestamp//60),time_display.ZONE)
        if minute!=self.minute:
            now=time_display.now_at(timestamp)
            self.labels=(now.strftime('%b %d'),now.strftime('%H:%M %Z'))
            self.minute=minute
        return self.labels
    def delay(self,timestamp):return 60-timestamp%60


class CalendarView:
    def __init__(self):self.offset=0
    def key(self,key):
        if key not in ('left','right','up','down','home'):return False
        if key=='home':self.offset=0
        else:self.offset+=-1 if key in ('left','up') else 1
        self.offset=max(-1200,min(1200,self.offset))
        return True
    def lines(self,timestamp):
        import calendar
        today=time_display.now_at(timestamp).date()
        total=today.year*12+today.month-1+self.offset
        year,month=divmod(total,12);month+=1
        rows=[f'{calendar.month_name[month]} {year}','', ' Mon  Tue  Wed  Thu  Fri  Sat  Sun']
        for week in calendar.monthcalendar(year,month):
            row=''
            for day in week:
                current=day and year==today.year and month==today.month and day==today.day
                row+=f'[{day:2}] ' if current else f' {day:2}  ' if day else '     '
            rows.append(row)
        return tuple(rows)+('', 'Arrows: month    Home: today')


def link_label(link,ascii=False):
    return ('+' if link.connected else '-')+' demo ' if ascii else ('●' if link.connected else '○')+' demo '
