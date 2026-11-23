/* ARM1136 guest driver for a bounded, host-generated MBX register trace.
 * Each record has three words: operation, address, value. */
.syntax unified
.cpu arm1136jf-s
.arm
.global _start
_start:
    @ Linux QEMU 9.1.3 implements SYS_ELAPSED with host monotonic nanoseconds.
    mov r0, #0x31               @ SYS_TICKFREQ
    svc 0x123456
    ldr r1, =1000000000
    cmp r0, r1
    bne failed
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
    beq begin_time
    cmp r5, #3                  @ end: repeat without resetting the board
    bne verify
    subs r12, r12, #1
    movne r4, r11
    bne next
    b end_time
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
@ Writable scratch RAM below the player, trace, and framebuffer references.
.equ CLOCK_RAM, 0x81f00000
begin_time:
    ldr r1, =CLOCK_RAM
    mov r0, #0x30               @ SYS_ELAPSED, two little-endian words
    svc 0x123456
    cmp r0, #0
    bne failed
    b next
end_time:
    ldr r1, =CLOCK_RAM + 8
    mov r0, #0x30
    svc 0x123456
    cmp r0, #0
    bne failed
    ldr r1, =CLOCK_RAM
    ldmia r1!, {r5,r6,r7,r8}   @ begin low/high, end low/high
    subs r7, r7, r5
    sbcs r8, r8, r6
    bcc failed
    @ Format the completed 64-bit interval after both samples have been taken.
    mov r6, r1
    mov r9, #16
hex_digit:
    mov r10, r8, lsr #28
    cmp r10, #10
    addlo r10, r10, #'0'
    addhs r10, r10, #87         @ 'a' - 10
    strb r10, [r6], #1
    lsl r8, r8, #4
    orr r8, r8, r7, lsr #28
    lsl r7, r7, #4
    subs r9, r9, #1
    bne hex_digit
    mov r10, #10
    strb r10, [r6], #1
    mov r10, #0
    strb r10, [r6]
    adr r1, duration_msg
    mov r0, #4
    svc 0x123456
    ldr r1, =CLOCK_RAM + 16
    mov r0, #4
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
duration_msg: .asciz "MBX_ELAPSED_NS "
fail_msg:  .asciz "MBX_FAILED\n"
