/* Eight binary32 additions per short-vector instruction, in retained batches. */
.syntax unified
.arch armv6
.fpu vfpv2
.text
.align 2
.global shortvec_add
.type shortvec_add, %function
shortvec_add:
    cmp r3, #0
    bxeq lr
    push {r4, r5, r6, lr}
    mov r5, r2
    mov r6, r3
    vmrs r4, fpscr
    vpush {d8-d15}
    bic r3, r4, #0x00370000
    orr r3, r3, #0x00070000
    vmsr fpscr, r3
.global shortvec_active_begin
shortvec_active_begin:
1:
    vldmia r0!, {s8-s15}
    vldmia r1!, {s16-s23}
    vadd.f32 s24, s8, s16
    vstmia r5!, {s24-s31}
    subs r6, r6, #1
    bne 1b
.global shortvec_active_end
shortvec_active_end:
    vmsr fpscr, r4
    vpop {d8-d15}
    pop {r4, r5, r6, pc}
.size shortvec_add, .-shortvec_add
.section .note.GNU-stack,"",%progbits
