/* SPDX-License-Identifier: MIT */
.syntax unified
.arch armv6
.fpu vfpv2
.arm
.text
.global n810_normals_fpscr
.type n810_normals_fpscr, %function
n810_normals_fpscr:
    fmrx r0, fpscr
    bx lr
.size n810_normals_fpscr, .-n810_normals_fpscr
.section .note.GNU-stack,"",%progbits
