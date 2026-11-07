; Local encoding proof. Caller supplies initialized XAR0 and XAR1.
; Eight 16-bit words, linear addressing, no 16-bit pointer boundary crossing.
; Clobbers T0 and advances AR0 and AR1 by eight words. Valid return context.
 .text
 .global copy8
copy8:
 MOV *AR0+,T0
 MOV T0,*AR1+
 MOV *AR0+,T0
 MOV T0,*AR1+
 MOV *AR0+,T0
 MOV T0,*AR1+
 MOV *AR0+,T0
 MOV T0,*AR1+
 MOV *AR0+,T0
 MOV T0,*AR1+
 MOV *AR0+,T0
 MOV T0,*AR1+
 MOV *AR0+,T0
 MOV T0,*AR1+
 MOV *AR0+,T0
 MOV T0,*AR1+
 RET
