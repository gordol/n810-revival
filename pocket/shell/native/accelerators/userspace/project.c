/* SPDX-License-Identifier: MIT */
#include <float.h>
#include <math.h>
#include <stddef.h>
#ifndef PROJECT_NAME
#error PROJECT_NAME selects the build variant
#endif
/* camera: origin, right, down, forward (three doubles each), span x/y, focal. */
int PROJECT_NAME(const double *c, const double *points, double *out, size_t n)
{
    size_t i;
    for (i = 0; i < n; ++i) {
        double x = points[3*i]-c[0], y = points[3*i+1]-c[1], z = points[3*i+2]-c[2];
        double depth = 0.0, right = 0.0, down = 0.0, scale = 1.0;
        double bound;
        depth += x*c[9]; depth += y*c[10]; depth += z*c[11];
        right += x*c[3]; right += y*c[4]; right += z*c[5];
        down += x*c[6]; down += y*c[7]; down += z*c[8];
        /* The Python reference may use compensated summation. Defer the whole
         * batch if rounding could change its perspective threshold decision. */
        bound = 16*DBL_EPSILON*(fabs(x*c[9])+fabs(y*c[10])+fabs(z*c[11]));
        if (c[14] != 0.0 && fabs(fabs(depth)-1e-9) <= bound)
            return -4;
        if (c[14] != 0.0 && fabs(depth) > 1e-9)
            scale = c[14]/depth;
        out[3*i] = right*scale/c[12]+0.5;
        out[3*i+1] = down*scale/c[13]+0.5;
        out[3*i+2] = depth;
    }
    return 0;
}
