/* SPDX-License-Identifier: MIT */
/* Exact Mesa fixed-function RGBA texture * varying RGBA, not arbitrary shaders. */
static bool mbx_modulate_fragment(const struct tgsi_token *tokens)
{
 struct tgsi_parse_context p;unsigned phase=0,temp=0,inputs=0;bool ok=true,ended=false;
 if(tgsi_parse_init(&p,tokens)!=TGSI_PARSE_OK)return false;
 while(!tgsi_parse_end_of_tokens(&p)&&ok){
  tgsi_parse_token(&p);
  if(p.FullToken.Token.Type==TGSI_TOKEN_TYPE_DECLARATION){
   const struct tgsi_full_declaration *d=&p.FullToken.FullDeclaration;
   if(d->Declaration.File==TGSI_FILE_INPUT){
    if(!d->Declaration.Semantic||d->Range.First!=d->Range.Last||d->Semantic.Index||d->Range.First>1){ok=false;break;}
    if(d->Semantic.Name!=(d->Range.First?TGSI_SEMANTIC_TEXCOORD:TGSI_SEMANTIC_COLOR)){ok=false;break;}
    inputs|=1U<<d->Range.First;
   }
   continue;
  }
  if(p.FullToken.Token.Type==TGSI_TOKEN_TYPE_PROPERTY){
   const struct tgsi_full_property *v=&p.FullToken.FullProperty;
   if(v->Property.PropertyName!=TGSI_PROPERTY_FS_COLOR0_WRITES_ALL_CBUFS||v->Property.NrTokens!=2||v->u[0].Data!=1)ok=false;
   continue;
  }
  if(p.FullToken.Token.Type!=TGSI_TOKEN_TYPE_INSTRUCTION){ok=false;break;}
  const struct tgsi_full_instruction *i=&p.FullToken.FullInstruction;
  if(i->Instruction.Opcode==TGSI_OPCODE_END){ended=phase==3&&inputs==3;break;}
  if(i->Instruction.Saturate||i->Instruction.NumDstRegs!=1||i->Dst[0].Register.Indirect||i->Dst[0].Register.Dimension||i->Dst[0].Register.WriteMask!=15){ok=false;break;}
  if(phase==0&&i->Instruction.Opcode==TGSI_OPCODE_MOV&&i->Instruction.NumSrcRegs==1&&i->Dst[0].Register.File==TGSI_FILE_TEMPORARY){
   struct tgsi_full_src_register source=i->Src[0];source.Register.SwizzleZ=2;
   if(i->Src[0].Register.SwizzleZ!=0||!mbx_texture_source(&source,TGSI_FILE_INPUT,1)){ok=false;break;}
   temp=i->Dst[0].Register.Index;phase=1;
  }else if(phase==1&&i->Instruction.Opcode==TGSI_OPCODE_TXP&&i->Instruction.NumSrcRegs==2&&i->Instruction.Texture&&i->Texture.Texture==TGSI_TEXTURE_2D&&i->Texture.NumOffsets==0&&i->Dst[0].Register.File==TGSI_FILE_TEMPORARY&&i->Dst[0].Register.Index==temp&&mbx_texture_source(&i->Src[0],TGSI_FILE_TEMPORARY,temp)&&i->Src[1].Register.File==TGSI_FILE_SAMPLER&&i->Src[1].Register.Index==0&&!i->Src[1].Register.Indirect&&!i->Src[1].Register.Dimension)phase=2;
  else if(phase==2&&i->Instruction.Opcode==TGSI_OPCODE_MUL&&i->Instruction.NumSrcRegs==2&&i->Dst[0].Register.File==TGSI_FILE_OUTPUT&&i->Dst[0].Register.Index==0&&mbx_texture_source(&i->Src[0],TGSI_FILE_TEMPORARY,temp)&&mbx_texture_source(&i->Src[1],TGSI_FILE_INPUT,0))phase=3;
  else ok=false;
 }
 tgsi_parse_free(&p);return ok&&ended;
}
