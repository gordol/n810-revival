/* ARM1136 guest driver for a bounded, host-generated MBX register trace.
 * Each record has three words: operation, address, value. */
.syntax unified
.cpu arm1136jf-s
.arm
.global _start
_start:
    ldr r4, =0x83000000
next:
    ldmia r4!, {r5-r7}
    cmp r5, #0                  @ register or RAM write
    streq r7, [r6]
    beq next
    cmp r5, #1                  @ expected register or RAM value
    bne control
    ldr r8, [r6]
    cmp r8, r7
    beq next
    b failed
control:
    cmp r5, #2                  @ begin: remember frame sequence and repeat count
    moveq r11, r4
    moveq r12, r7
    adreq r1, begin_msg
    beq message
    cmp r5, #3                  @ end: repeat without resetting the board
    bne verify
    subs r12, r12, #1
    movne r4, r11
    bne next
    adr r1, end_msg
    b message
verify:
    cmp r5, #4                  @ validation only: compare visible RGB
    bne finish
    ldr r8, =0x80010000
pixel:
    ldr r9, [r8], #4
    ldr r10, [r6], #4
    eor r9, r9, r10
    lsls r9, r9, #8
    bne failed
    subs r7, r7, #1
    bne pixel
    b next
message:
    mov r0, #4                  @ semihost SYS_WRITE0
    svc 0x123456
    b next
failed:
    adr r1, fail_msg
    mov r0, #4
    svc 0x123456
finish:
    mov r0, #0x18               @ semihost SYS_EXIT
    ldr r1, =0x20026
    svc 0x123456
    b .
begin_msg: .asciz "MBX_BEGIN\n"
end_msg:   .asciz "MBX_END\n"
fail_msg:  .asciz "MBX_FAILED\n"
