/* Test harness: record the leaf's preserved state, then restore the caller. */
.syntax unified
.arch armv6
.fpu vfpv2
.text
.align 2
.global shortvec_context
.type shortvec_context, %function
shortvec_context:
    push {r4, r5, r6, lr}
    ldr r4, [sp, #16]
    vpush {d8-d15}
    vmrs r6, fpscr
    vldmia r4, {d8-d15}
    bl shortvec_add
    add r5, r4, #64
    vstmia r5, {d8-d15}
    vmrs r5, fpscr
    str r5, [r4, #128]
    vmsr fpscr, r6
    vpop {d8-d15}
    pop {r4, r5, r6, pc}
.size shortvec_context, .-shortvec_context

.global shortvec_get_fpscr
.type shortvec_get_fpscr, %function
shortvec_get_fpscr:
    vmrs r0, fpscr
    bx lr
.size shortvec_get_fpscr, .-shortvec_get_fpscr

.global shortvec_set_fpscr
.type shortvec_set_fpscr, %function
shortvec_set_fpscr:
    vmsr fpscr, r0
    bx lr
.size shortvec_set_fpscr, .-shortvec_set_fpscr
.section .note.GNU-stack,"",%progbits
