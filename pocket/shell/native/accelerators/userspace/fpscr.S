/* SPDX-License-Identifier: MIT */
.syntax unified
.arch armv6
.fpu vfpv2
.arm
.text
.global n810_project_fpscr
.type n810_project_fpscr, %function
n810_project_fpscr:
    fmrx r0, fpscr
    bx lr
.size n810_project_fpscr, .-n810_project_fpscr
.section .note.GNU-stack,"",%progbits
