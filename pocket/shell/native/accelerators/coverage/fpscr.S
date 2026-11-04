/* SPDX-License-Identifier: MIT */
.syntax unified
.arch armv6
.fpu vfpv2
.arm
.text
.global n810_coverage_fpscr
.type n810_coverage_fpscr, %function
n810_coverage_fpscr:
    fmrx r0, fpscr
    bx lr
.size n810_coverage_fpscr, .-n810_coverage_fpscr
.section .note.GNU-stack,"",%progbits
