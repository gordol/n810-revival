/* Recognize Mesa's four-column texture matrix without evaluating vertices.
 * Draw-time validation proves its q row is [0,0,0,1]. */
static unsigned mbx_vgp_affine_uv(const struct tgsi_token *tokens){
 struct tgsi_parse_context p;unsigned output=~0U,phase=0,temp=0,base=0,found=~0U;
 if(tgsi_parse_init(&p,tokens)!=TGSI_PARSE_OK)return ~0U;
 while(!tgsi_parse_end_of_tokens(&p)){
  tgsi_parse_token(&p);
  if(p.FullToken.Token.Type==TGSI_TOKEN_TYPE_DECLARATION){
   const struct tgsi_full_declaration *d=&p.FullToken.FullDeclaration;
   if(d->Declaration.File==TGSI_FILE_OUTPUT&&d->Declaration.Semantic&&!d->Semantic.Index&&
    (d->Semantic.Name==TGSI_SEMANTIC_GENERIC||d->Semantic.Name==TGSI_SEMANTIC_TEXCOORD)&&d->Range.First==d->Range.Last)output=d->Range.First;
   continue;
  }
  if(p.FullToken.Token.Type!=TGSI_TOKEN_TYPE_INSTRUCTION)continue;
  const struct tgsi_full_instruction *i=&p.FullToken.FullInstruction;
  if(i->Instruction.Opcode==TGSI_OPCODE_END)break;
  const struct tgsi_full_src_register *a=&i->Src[0],*b=&i->Src[1],*c=&i->Src[2];
  const struct tgsi_full_dst_register *d=&i->Dst[0];
  if(i->Instruction.NumDstRegs==1&&d->Register.File==TGSI_FILE_OUTPUT&&d->Register.Index==output)found=~0U;
  if(i->Instruction.Saturate||i->Instruction.NumDstRegs!=1||d->Register.WriteMask!=15||d->Register.Indirect||d->Register.Dimension||
    a->Register.File!=TGSI_FILE_INPUT||a->Register.Index!=1||a->Register.Indirect||a->Register.Dimension||a->Register.Negate||a->Register.Absolute||
    b->Register.File!=TGSI_FILE_CONSTANT||b->Register.Indirect||b->Register.Negate||b->Register.Absolute||
    (b->Register.Dimension&&(b->Dimension.Indirect||b->Dimension.Index))||
    b->Register.SwizzleX!=0||b->Register.SwizzleY!=1||b->Register.SwizzleZ!=2||b->Register.SwizzleW!=3){phase=0;continue;}
  if(i->Instruction.Opcode==TGSI_OPCODE_MUL&&i->Instruction.NumSrcRegs==2&&d->Register.File==TGSI_FILE_TEMPORARY&&
    !a->Register.SwizzleX&&!a->Register.SwizzleY&&!a->Register.SwizzleZ&&!a->Register.SwizzleW){
   phase=1;temp=d->Register.Index;base=b->Register.Index;continue;
  }
  if(!phase||i->Instruction.Opcode!=TGSI_OPCODE_MAD||i->Instruction.NumSrcRegs!=3||
    a->Register.SwizzleX!=phase||a->Register.SwizzleY!=phase||a->Register.SwizzleZ!=phase||a->Register.SwizzleW!=phase||
    b->Register.Index!=base+phase||c->Register.File!=TGSI_FILE_TEMPORARY||c->Register.Index!=temp||c->Register.Indirect||c->Register.Dimension||c->Register.Negate||c->Register.Absolute||
    c->Register.SwizzleX!=0||c->Register.SwizzleY!=1||c->Register.SwizzleZ!=2||c->Register.SwizzleW!=3||
    d->Register.File!=(phase==3?TGSI_FILE_OUTPUT:TGSI_FILE_TEMPORARY)||d->Register.Index!=(phase==3?output:temp)){phase=0;continue;}
  if(phase==3){found=base;phase=0;}else ++phase;
 }
 tgsi_parse_free(&p);return found;
}
static bool mbx_vgp_affine_q(const void *uniforms,unsigned bytes,unsigned base){
 if(!uniforms||base>MBX_VGP_UNIFORM_LIMIT-4||bytes<(base+4)*16)return false;
 unsigned q[4];for(unsigned i=0;i<4;++i)memcpy(q+i,(const unsigned char *)uniforms+(base+i)*16+12,4);
 return !(q[0]&0x7fffffff)&&!(q[1]&0x7fffffff)&&!(q[2]&0x7fffffff)&&q[3]==0x3f800000U;
}
