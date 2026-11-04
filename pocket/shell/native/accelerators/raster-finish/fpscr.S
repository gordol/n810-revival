/* SPDX-License-Identifier: MIT */
.syntax unified
.arch armv6
.fpu vfpv2
.arm
.text
.global n810_finish_fpscr
.type n810_finish_fpscr, %function
n810_finish_fpscr:
    fmrx r0, fpscr
    bx lr
.size n810_finish_fpscr, .-n810_finish_fpscr
.section .note.GNU-stack,"",%progbits
