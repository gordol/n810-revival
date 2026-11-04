"""Private coordination listings, separate from observed APRS stations."""
import json
from functools import lru_cache
from pathlib import Path
from data_paths import data_root
from paint import ink

PATH = data_root()/'repeaters/repeaters.json'


def signature():
    try:return PATH.stat().st_mtime_ns
    except OSError:return None


@lru_cache(maxsize=2)
def load(revision):
    if revision is None:return ()
    try:
        data=json.loads(PATH.read_text())
        return tuple(dict(row,edition=data['edition']) for row in data['repeaters']
                     if row.get('lat') is not None and row.get('lon') is not None)
    except (OSError,ValueError,KeyError):return ()


BANDS=('6m','2m','1.25m','70cm','33cm','Other')
# Increasing frequency: red, orange, yellow, green, violet; unknown bands neutral.
COLORS=((255,125,125),(255,185,100),(245,230,120),(120,225,170),(195,160,255),(220,220,220))
def band(frequency):
    for low,high,name in ((50,54,'6m'),(144,148,'2m'),(222,225,'1.25m'),(420,450,'70cm'),(902,928,'33cm')):
        if low<=frequency<=high:return name
    return 'Other'

def annotate(image,view,overlay,occupied,enabled=BANDS,show_labels=True):
    hits=[];labels=0
    for row in load(signature()):
        group=band(row['rx_mhz'])
        if group not in enabled:continue
        x,y=map(round,view.project(row['lon'],row['lat']))
        if not (0<=x<image.width and 0<=y<image.height) or (x,y) in occupied:continue
        color=ink(*COLORS[BANDS.index(group)],background=(25,25,25))
        overlay[y*image.width+x]=('R',color);hits.append((x,y,1,row));occupied.add((x,y))
        label=f"{row['call']} {row['rx_mhz']:g}"
        cells={(xx,y) for xx in range(x+2,x+2+len(label))}
        if show_labels and labels<12 and x+2+len(label)<image.width and not occupied.intersection(cells):
            for i,char in enumerate(label):overlay[y*image.width+x+2+i]=(char,color)
            hits.append((x+2,y,len(label),row));occupied.update(cells);labels+=1
    return tuple(hits)
