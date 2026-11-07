; One output: clamp16(floor(sum(x[k]*h[k], k=0..7) / 32768)).
; x at XAR0, h at XCDP, output at XAR1. Coefficients in internal memory.
; Caller: C54CM=0, FRCT=0, M40=1, SATD=0, SXMD=1; SMUL may be 0 or 1.
; AR0LC=AR1LC=CDPLC=0, no pointer wrap, valid return/stack context.
; Clobbers AC0/ACOV0; advances AR0/CDP by 8 and AR1 by 1 word.
; Integer products avoid the fractional -32768 * -32768 corner case.
; Only the final 40-bit sum is doubled, then saturated and high-word stored.
; No relocations, loops, BIOS calls, status setup, or completion signal.
 .text
 .global fir8_one
fir8_one:
 MPYM *AR0+,*CDP+,AC0
 MACM *AR0+,*CDP+,AC0
 MACM *AR0+,*CDP+,AC0
 MACM *AR0+,*CDP+,AC0
 MACM *AR0+,*CDP+,AC0
 MACM *AR0+,*CDP+,AC0
 MACM *AR0+,*CDP+,AC0
 MACM *AR0+,*CDP+,AC0
 MOV HI(saturate(AC0 << #1)),*AR1+
 RET
