; Experimental TI c55_std, large-memory-model leaf.
; Intended C prototype: void n810_fir8_std(const short *x, const short *h, short *y);
; XAR0=x, XAR1=h, XAR2=y. Standard C entry modes are required, including
; M40=0, FRCT=SATD=C54CM=C16=0, CPL=SXMD=ARMS=1 and linear pointers.
; SMUL may be either value and is preserved (the C convention normally uses 1).
; Eight internal coefficient words, eight input words, one output word.
; Inline body avoids CALL/branch relocations and leaves SP/SSP/RETA/CFCT alone
; until the final RET. Caller-saved AC0/XAR0/XAR1/XCDP are clobbered.
; Callee-saved T2/T3/XAR5-XAR7/XDP are untouched. Restore M40=0.
; Not an interrupt entry, Gateway task or arbitrary-mode register entry point.
 .text
 .global _n810_fir8_std
_n810_fir8_std:
 MOV XAR1,XCDP
 MOV XAR2,XAR1
 BSET #10,ST1_55
 MPYM *AR0+,*CDP+,AC0
 MACM *AR0+,*CDP+,AC0
 MACM *AR0+,*CDP+,AC0
 MACM *AR0+,*CDP+,AC0
 MACM *AR0+,*CDP+,AC0
 MACM *AR0+,*CDP+,AC0
 MACM *AR0+,*CDP+,AC0
 MACM *AR0+,*CDP+,AC0
 MOV HI(saturate(AC0 << #1)),*AR1+
 BCLR #10,ST1_55
 RET
