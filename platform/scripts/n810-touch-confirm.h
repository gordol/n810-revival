/* Two separate pen releases must agree before accepting a calibration point. */
#ifndef N810_TOUCH_CONFIRM_H
#define N810_TOUCH_CONFIRM_H
#include <math.h>
struct touch_confirmation { int pending; double x, y; };
static int confirm_touch(struct touch_confirmation *state, double x, double y,
                         double tolerance_x, double tolerance_y)
{
    if (state->pending && fabs(x-state->x)<=tolerance_x && fabs(y-state->y)<=tolerance_y) {
        state->x=(state->x+x)/2; state->y=(state->y+y)/2;
        state->pending=0; return 1;
    }
    if(state->pending) { state->pending=0; return -1; }
    state->x=x; state->y=y; state->pending=1; return 0;
}
#endif
