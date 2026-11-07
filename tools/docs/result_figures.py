#!/usr/bin/env python3
"""Render figures from the published journal's retained measurements.

Requires Matplotlib. Run from any directory. Output is deterministic apart from
PNG encoder metadata. Regenerate the media review hashes after visual review.
"""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/assets/screenshots'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.spines.left': False, 'axes.axisbelow': True,
                     'figure.facecolor': '#faf9f5', 'axes.facecolor': '#faf9f5',
                     'text.color': '#243c35', 'axes.labelcolor': '#243c35'})


def save(fig, name):
    fig.savefig(OUT / name, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)


# Recovering the complete Wi-Fi firmware, 3 October 2026.
fig, ax = plt.subplots(figsize=(9, 3.8))
labels = ['Older firmware', 'Recovered complete image', 'Complete image, repeat']
received, sent = [18, 30, 60], [39, 30, 60]
values = [100 * n / d for n, d in zip(received, sent)]
ax.barh(labels, values, color=['#89958f', '#396b60', '#396b60'], height=.52)
ax.invert_yaxis(); ax.set_xlim(0, 118); ax.set_xticks([0, 25, 50, 75, 100]); ax.set_xlabel('Router replies received (%)')
ax.grid(axis='x', alpha=.15); ax.tick_params(axis='y', length=0)
for i, (v, n, d) in enumerate(zip(values, received, sent)):
    ax.text(v+2, i, f'{n}/{d}', va='center')
fig.suptitle('Firmware comparison with the other settings held fixed', x=.04, ha='left', fontsize=14, fontweight='bold')
fig.text(.04,.02,'3 October 2026 · Separate short trials; counts are printed beside each bar.',fontsize=9)
fig.tight_layout(rect=(0,.08,1,.92)); save(fig,'wifi-firmware-results.png')

# Measuring GPU throughput and display updates separately, 4 November 2026.
fig, ax = plt.subplots(figsize=(9, 4.4))
y=[0,1];control=[20.3895,30.7405];optimized=[21.4665,33.596]
a=ax.barh([v-.16 for v in y],control,height=.28,label='Control',color='#89958f')
b=ax.barh([v+.16 for v in y],optimized,height=.28,label='Optimized',color='#396b60')
ax.set_yticks(y,['Pocket UI active','Pocket UI paused']);ax.invert_yaxis();ax.set_xlim(0,40);ax.set_xlabel('Median application-reported frames per second')
ax.grid(axis='x',alpha=.15);ax.tick_params(axis='y',length=0)
for bars in (a,b):
    for bar in bars:ax.text(bar.get_width()+.5,bar.get_y()+bar.get_height()/2,f'{bar.get_width():.2f}',va='center')
ax.legend(loc='upper left',bbox_to_anchor=(0,-.24),ncol=2,frameon=False)
fig.suptitle('Background CPU work changes the gears result',x=.04,ha='left',fontsize=14,fontweight='bold')
fig.text(.04,.02,'4 November 2026 · 400 × 400 glxgears · Interval medians; display transfers measured separately.',fontsize=9)
fig.tight_layout(rect=(0,.08,1,.92));save(fig,'gpu-background-results.png')
