/* SPDX-License-Identifier: MIT
 * Original bounded TGSI-to-VGP compiler. All transform/lighting operations
 * remain in the GPU program, including input-independent arithmetic.
 * No device submission occurs here. Unsupported states fail explicitly.
 */
#ifndef MBX_VGP_SHADER_H
#define MBX_VGP_SHADER_H
#include <stdint.h>
#include <string.h>
#include "tgsi/tgsi_parse.h"
#include "pipe/p_defines.h"
#include "mbx_vgp_isa.h"
#define MBX_VGP_SHADER_LIMIT 128
/* Shared TA packing owns c83/c84 and c102. Reject layouts that would
 * alias it until the uniform remapper is implemented. */
#define MBX_VGP_UNIFORM_LIMIT 83
#define MBX_VGP_IMMEDIATE_LIMIT 6
struct mbx_vgp_shader {
 unsigned words[MBX_VGP_SHADER_LIMIT*2],count,constants,inputs;
 uint32_t immediate[16][4];unsigned immediates;
 unsigned output_temp[32];
};
static bool mbx_vgp_append(struct mbx_vgp_shader *p,unsigned op,unsigned dst,unsigned mask,struct mbx_vgp_source *src,unsigned ns)
{
 if(p->count==MBX_VGP_SHADER_LIMIT||mbx_vgp_encode(op,dst,mask,src,ns,p->words+2*p->count))return false;
 ++p->count;return true;
}
static bool mbx_vgp_compile(const struct tgsi_token *tokens,struct mbx_vgp_shader *out)
{
 struct mbx_vgp_shader p={0};struct tgsi_parse_context parse;bool valid=true,ended=false;unsigned defined[14]={0};
 for(unsigned i=0;i<32;++i)p.output_temp[i]=~0u;
 if(tgsi_parse_init(&parse,tokens)!=TGSI_PARSE_OK)return false;
 if(parse.FullHeader.Processor.Processor!=PIPE_SHADER_VERTEX){tgsi_parse_free(&parse);return false;}
 while(!tgsi_parse_end_of_tokens(&parse)&&valid){
  tgsi_parse_token(&parse);
  if(parse.FullToken.Token.Type==TGSI_TOKEN_TYPE_PROPERTY){
   const struct tgsi_full_property *prop=&parse.FullToken.FullProperty;
   if(prop->Property.PropertyName!=TGSI_PROPERTY_NEXT_SHADER||prop->Property.NrTokens!=2||prop->u[0].Data!=0)valid=false;
   continue;
  }
  if(parse.FullToken.Token.Type==TGSI_TOKEN_TYPE_DECLARATION){
   const struct tgsi_full_declaration *d=&parse.FullToken.FullDeclaration;
   if(d->Declaration.File==TGSI_FILE_OUTPUT){
    if(!d->Declaration.Semantic||d->Range.First!=d->Range.Last||d->Range.First>=32||d->Semantic.Index){valid=false;break;}
    if(d->Semantic.Name==TGSI_SEMANTIC_POSITION)p.output_temp[d->Range.First]=10;
    else if(d->Semantic.Name==TGSI_SEMANTIC_COLOR)p.output_temp[d->Range.First]=11;
    else valid=false;
   }
   continue;
  }
  if(parse.FullToken.Token.Type==TGSI_TOKEN_TYPE_IMMEDIATE){
   if(p.immediates==MBX_VGP_IMMEDIATE_LIMIT||parse.FullToken.FullImmediate.Immediate.DataType>TGSI_IMM_INT32||parse.FullToken.FullImmediate.Immediate.NrTokens!=5){valid=false;break;}
   for(unsigned j=0;j<4;++j)p.immediate[p.immediates][j]=parse.FullToken.FullImmediate.u[j].Uint;
   ++p.immediates;continue;
  }
  if(parse.FullToken.Token.Type!=TGSI_TOKEN_TYPE_INSTRUCTION){valid=false;break;}
  const struct tgsi_full_instruction *in=&parse.FullToken.FullInstruction;
  unsigned tgsi=in->Instruction.Opcode,op,ns;
  if(tgsi==TGSI_OPCODE_END){ended=true;break;}
  switch(tgsi){
   case TGSI_OPCODE_MOV:op=1;ns=1;break;case TGSI_OPCODE_RCP:op=5;ns=1;break;case TGSI_OPCODE_RSQ:op=6;ns=1;break;
   case TGSI_OPCODE_ADD:op=2;ns=2;break;case TGSI_OPCODE_MUL:op=4;ns=2;break;
   case TGSI_OPCODE_DP3:op=7;ns=2;break;case TGSI_OPCODE_DP4:op=8;ns=2;break;
   case TGSI_OPCODE_MIN:op=9;ns=2;break;case TGSI_OPCODE_MAX:op=10;ns=2;break;
   case TGSI_OPCODE_SLT:op=11;ns=2;break;case TGSI_OPCODE_MAD:op=3;ns=3;break;
   default:valid=false;continue;
  }
  if(in->Instruction.NumDstRegs!=1||in->Instruction.NumSrcRegs!=ns||in->Dst[0].Register.Indirect||in->Dst[0].Register.Dimension){valid=false;break;}
  unsigned dest=in->Dst[0].Register.Index,mask=in->Dst[0].Register.WriteMask;
  if(in->Dst[0].Register.File==TGSI_FILE_OUTPUT){if(dest>=32||p.output_temp[dest]==~0u){valid=false;break;}dest=p.output_temp[dest];}
  else if(in->Dst[0].Register.File!=TGSI_FILE_TEMPORARY||dest>=10){valid=false;break;}
  struct mbx_vgp_source src[3];unsigned scratch=12,constant=128,input=16;
  for(unsigned j=0;j<ns&&valid;++j){
   const struct tgsi_full_src_register *r=&in->Src[j];unsigned index=r->Register.Index,bank;
   if(r->Register.Indirect||(r->Register.Dimension&&(r->Dimension.Indirect||r->Dimension.Index))){valid=false;break;}
   switch(r->Register.File){
    case TGSI_FILE_INPUT:bank=0;if(index>=2){valid=false;break;}if(p.inputs<index+1)p.inputs=index+1;break;
    case TGSI_FILE_CONSTANT:bank=1;if(index>=MBX_VGP_UNIFORM_LIMIT){valid=false;break;}if(p.constants<index+1)p.constants=index+1;break;
    case TGSI_FILE_IMMEDIATE:bank=1;if(index>=p.immediates){valid=false;break;}index+=96;break;
    case TGSI_FILE_TEMPORARY:bank=2;if(index>=10)valid=false;break;
    case TGSI_FILE_OUTPUT:bank=2;if(index>=32||p.output_temp[index]==~0u){valid=false;break;}index=p.output_temp[index];break;
    default:valid=false;bank=0;break;
   }
   if(!valid)break;
   unsigned sw=r->Register.SwizzleX|(r->Register.SwizzleY<<2)|(r->Register.SwizzleZ<<4)|(r->Register.SwizzleW<<6);
   src[j]=(struct mbx_vgp_source){bank,index,sw,r->Register.Negate};
   /* One distinct input and constant per instruction. Resolve bank conflicts
    * into reserved scratch registers; never relax the ISA constraint. */
   bool stage=(bank==1&&constant!=128&&constant!=index)||(bank==0&&input!=16&&input!=index)||r->Register.Absolute;
   if(stage){
    if(scratch>13){valid=false;break;}
    struct mbx_vgp_source value=src[j];value.negative=0;
    if(r->Register.Absolute){struct mbx_vgp_source a[2]={value,value};a[1].negative=1;
     if(!mbx_vgp_append(&p,10,16+scratch,15,a,2)){valid=false;break;}}
    else if(!mbx_vgp_append(&p,1,16+scratch,15,&value,1)){valid=false;break;}
    src[j]=(struct mbx_vgp_source){2,scratch++,0xe4,r->Register.Negate};
   }else{if(bank==1)constant=index;if(bank==0)input=index;}
  }
  if(!valid||!mbx_vgp_append(&p,op,16+dest,mask,src,ns)){valid=false;break;}
  defined[dest]|=mask;
  if(in->Instruction.Saturate){
   struct mbx_vgp_source a[2]={{2,dest,0xe4,0},{1,114,0,0}};
   if(!mbx_vgp_append(&p,10,16+dest,mask,a,2)){valid=false;break;}
   a[1].index=115;if(!mbx_vgp_append(&p,9,16+dest,mask,a,2)){valid=false;break;}
  }
 }
 tgsi_parse_free(&parse);if(!valid||!ended||defined[10]!=15||defined[11]!=15)return false;
 struct mbx_vgp_source pos={2,10,0xe4,0},color={2,11,0xc6,0};
 if(!mbx_vgp_append(&p,1,0,15,&pos,1)||!mbx_vgp_append(&p,1,1,15,&color,1))return false;
 for(unsigned i=0;i<2;++i){struct mbx_vgp_source a[2]={pos,{1,112+i,0xe4,0}};if(!mbx_vgp_append(&p,8,7,1u<<i,a,2))return false;}
 *out=p;return true;
}
#endif
