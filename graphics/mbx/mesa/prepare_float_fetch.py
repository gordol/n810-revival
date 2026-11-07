"""Exact common float expansion inside Mesa's existing indexed fetch loop."""
def prepare_float_fetch(path):
 s=path.read_text()
 if '#include "mbx_float_fetch.h"' in s:return
 a='#define DRAW_DBG 0';assert s.count(a)==1
 s=s.replace(a,'#include "mbx_float_fetch.h"\n\n'+a)
 a='\n      int copy_size;\n';assert s.count(a)==1
 s=s.replace(a,a+'      unsigned mbx_float_words;\n')
 a='         copy_size = tg->attrib[attr].copy_size;';assert s.count(a)==1
 s=s.replace(a,'''         if(tg->attrib[attr].mbx_float_words){
            mbx_float_fetch4(dst,src,tg->attrib[attr].mbx_float_words);
            continue;
         }
'''+a)
 a='      tg->attrib[i].copy_size = -1;';assert s.count(a)==1
 s=s.replace(a,'''      if(getenv("N810_MBX_FLOAT_FETCH") && !strcmp(getenv("N810_MBX_FLOAT_FETCH"),"1") &&
         key->element[i].type==TRANSLATE_ELEMENT_NORMAL &&
         key->element[i].output_format==PIPE_FORMAT_R32G32B32A32_FLOAT){
         switch(key->element[i].input_format){
         case PIPE_FORMAT_R32_FLOAT:tg->attrib[i].mbx_float_words=1;break;
         case PIPE_FORMAT_R32G32_FLOAT:tg->attrib[i].mbx_float_words=2;break;
         case PIPE_FORMAT_R32G32B32_FLOAT:tg->attrib[i].mbx_float_words=3;break;
         case PIPE_FORMAT_R32G32B32A32_FLOAT:tg->attrib[i].mbx_float_words=4;break;
         default:break;
         }
      }
'''+a)
 path.write_text(s)
