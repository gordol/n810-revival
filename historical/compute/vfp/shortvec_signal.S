.syntax unified
.arch armv6
.fpu vfpv2
.text
.align 2
.global shortvec_signal_scalar
.type shortvec_signal_scalar, %function
shortvec_signal_scalar:
    vldr s9, 1f
    vldr s10, 2f
    vadd.f32 s8, s9, s10
    vmov r0, s8
    bx lr
.size shortvec_signal_scalar, .-shortvec_signal_scalar
.align 2
1: .word 0x3fa00000
2: .word 0x40200000
.section .note.GNU-stack,"",%progbits
