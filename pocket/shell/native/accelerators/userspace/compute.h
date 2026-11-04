/* SPDX-License-Identifier: MIT */
#ifndef N810_COMPUTE_H
#define N810_COMPUTE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
enum { N810_COMPUTE_ABI=1, N810_PROJECT_MAX_POINTS=65536 };
enum { N810_BACKEND_AUTO=0, N810_BACKEND_SOFT=1, N810_BACKEND_VFP=2 };
enum { N810_INVALID_BUFFER=-1, N810_INVALID_NUMBER=-2,
       N810_VFP_UNAVAILABLE=-3, N810_PERSPECTIVE_AMBIGUOUS=-4 };
uint32_t n810_compute_abi(void);
int n810_compute_vfp(void);
/* Camera is 15 binary64 values: origin xyz; right xyz; down xyz; forward xyz;
 * span_x, span_y, focal. Input and output are count triples. Valid typed ranges
 * and normal double alignment are the caller's responsibility. Output must be
 * disjoint from input and camera. Zero count accepts null pointers.
 * Returns 1/2 for selected software/VFP backend, or a negative error.
 * On any negative return discard the whole output, including any written prefix.
 * All source values must be finite and within +/-1e12, spans magnitude >=1e-12.
 * Near the perspective threshold, -4 requires the caller's reference path.
 * This synchronous primitive allocates no memory and changes no device state. */
int n810_project(const double *camera, const double *points, double *output,
                 size_t count, int backend);
#ifdef __cplusplus
}
#endif
#endif
