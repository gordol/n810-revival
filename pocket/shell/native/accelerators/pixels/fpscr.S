/* SPDX-License-Identifier: MIT */
.syntax unified
.arch armv6
.fpu vfpv2
.arm
.text
.global cw_pixels_fpscr
.type cw_pixels_fpscr, %function
cw_pixels_fpscr:
    fmrx r0, fpscr
    bx lr
.size cw_pixels_fpscr, .-cw_pixels_fpscr
.section .note.GNU-stack,"",%progbits
