# The map has an edge

Prepared regional maps made it onto the N810. The device could open overview
and detail views, pan and zoom within prepared coverage, and keep the last
supported image when a request went outside it. That last behavior matters:
an unavailable tile should say *unavailable*, not quietly invent detail.

The data path worked better than the interaction. In the recorded regional
trial, scripted settling took **2.37–4.26 seconds**, cold detail took
**5.58 seconds**, and relaunch output was confirmed at **77.84 seconds**.
Those numbers describe that workload. They are not stylus-to-pixel latency.
Physical pan and zoom still felt slow, and sustained drag was not accepted.

The project kept older installed versions and a separate settings checkpoint
while trying the new map behavior. Switching code and restoring an older
profile are different operations; the latter changes a user's layout and
preferences.

Next measurement: split data lookup, preparation, composition, terminal
output, and physical input. The test that matters is plain: put the stylus
down, move the map, and see it follow.

[Status](../status.md) · [Journal](../journal.md)
