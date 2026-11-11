#ifndef MBX_CONSTANT_COLOR_H
#define MBX_CONSTANT_COLOR_H
/* Exactly the fixed-function fragment constant emitted for glColor. */
static bool mbx_fragment_constant(const struct tgsi_token *tokens){
 struct tgsi_parse_context p;bool moved=false,ended=false,valid=true,color_declared=false;
 if(tgsi_parse_init(&p,tokens)!=TGSI_PARSE_OK)return false;
 while(!tgsi_parse_end_of_tokens(&p)&&valid){
  tgsi_parse_token(&p);
  if(p.FullToken.Token.Type==TGSI_TOKEN_TYPE_DECLARATION){
   const struct tgsi_full_declaration *d=&p.FullToken.FullDeclaration;
   if(d->Declaration.File==TGSI_FILE_OUTPUT){
    if(color_declared||d->Range.First||d->Range.Last||!d->Declaration.Semantic||d->Semantic.Name!=TGSI_SEMANTIC_COLOR||d->Semantic.Index){valid=false;break;}
    color_declared=true;
   }else if(d->Declaration.File!=TGSI_FILE_CONSTANT){valid=false;break;}
   continue;
  }
  if(p.FullToken.Token.Type==TGSI_TOKEN_TYPE_PROPERTY){
   const struct tgsi_full_property *v=&p.FullToken.FullProperty;
   if(v->Property.PropertyName!=TGSI_PROPERTY_FS_COLOR0_WRITES_ALL_CBUFS||v->Property.NrTokens!=2||v->u[0].Data!=1)valid=false;
   continue;
  }
  if(p.FullToken.Token.Type!=TGSI_TOKEN_TYPE_INSTRUCTION){valid=false;break;}
  const struct tgsi_full_instruction *i=&p.FullToken.FullInstruction;
  if(i->Instruction.Opcode==TGSI_OPCODE_END){ended=moved;break;}
  if(moved||i->Instruction.Opcode!=TGSI_OPCODE_MOV||i->Instruction.Saturate||i->Instruction.NumDstRegs!=1||i->Instruction.NumSrcRegs!=1||
     i->Dst[0].Register.File!=TGSI_FILE_OUTPUT||i->Dst[0].Register.Index||i->Dst[0].Register.WriteMask!=15||i->Dst[0].Register.Indirect||i->Dst[0].Register.Dimension){valid=false;break;}
  struct tgsi_full_src_register src=i->Src[0];
  if(src.Register.Dimension&&(src.Dimension.Indirect||src.Dimension.Index)){valid=false;break;}
  src.Register.Dimension=0;valid=src.Register.File==TGSI_FILE_CONSTANT&&!src.Register.Index&&!src.Register.Indirect&&!src.Register.Negate&&!src.Register.Absolute&&src.Register.SwizzleX==0&&src.Register.SwizzleY==1&&src.Register.SwizzleZ==2&&src.Register.SwizzleW==3;moved=valid;
 }
 tgsi_parse_free(&p);return valid&&ended&&color_declared;
}

#endif
