; Local encoding proof. This is wrapping addition, not the Q15 FIR kernel.
; Same pointer/return contract as copy8; additionally requires SATA=0.
; Clobbers T0 and arithmetic status (CARRY/ACOVx); caller must preserve it.
 .text
 .global add1_8
add1_8:
 MOV *AR0+,T0
 ADD #1,T0
 MOV T0,*AR1+
 MOV *AR0+,T0
 ADD #1,T0
 MOV T0,*AR1+
 MOV *AR0+,T0
 ADD #1,T0
 MOV T0,*AR1+
 MOV *AR0+,T0
 ADD #1,T0
 MOV T0,*AR1+
 MOV *AR0+,T0
 ADD #1,T0
 MOV T0,*AR1+
 MOV *AR0+,T0
 ADD #1,T0
 MOV T0,*AR1+
 MOV *AR0+,T0
 ADD #1,T0
 MOV T0,*AR1+
 MOV *AR0+,T0
 ADD #1,T0
 MOV T0,*AR1+
 RET
