"""Exercise production native dependency groups with changing input subsets."""
from pathlib import Path
import ast,subprocess,sys
src=Path(sys.argv[1]);base=Path(__file__).with_name('test_arm_vertex_deferred.py')
values={}
for node in ast.parse(base.read_text()).body:
 if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('prefix','main'):
  values[node.targets[0].id]=ast.literal_eval(node.value)
main=values['main'].replace('p->count=256;','p->count=256;p->reuse_inputs=false;p->reuse_mask=trial%2?UINT32_MAX:1u<<(trial%32);\n  uint32_t deps[MF_WORDS]={0};for(unsigned j=0;j<128;++j)deps[j]=1u<<(j/4);')
main=main.replace('p->vertex_ops[p->vertex_count++]=k;', '''for(unsigned s=0;s<3;++s)for(unsigned c=0;c<4;++c)p->dependencies[k]|=deps[o->src[s][c]];
   for(unsigned c=0;c<4;++c)if(o->mask&(1<<c))deps[o->dst+c]=p->dependencies[k];
   if(p->dependencies[k])p->vertex_ops[p->vertex_count++]=k;
   else p->uniform_ops[p->uniform_count++]=k;''')
main=main.replace('for(unsigned i=0;i<MF_WORDS;++i){\n    uint32_t bits=random32();','''p->dirty_inputs=iteration==0?UINT32_MAX:iteration%3==0?0:random32();
   for(unsigned i=0;i<MF_WORDS;++i){
    if(iteration && (i>=128 || !(p->dirty_inputs&(1u<<(i/4)))))continue;
    uint32_t bits=random32();''')
main=main.replace('mf_compile_native(p);assert(p->native_run);','mf_compile_all_native(p);assert(p->native_run);')
main=main.replace('p->native_run(p);','if(p->native_uniform_run)p->native_uniform_run(p);else for(unsigned j=0;j<p->uniform_count;++j)mf_execute(p,&p->ops[p->uniform_ops[j]]);\n   p->native_run(p);')
main=main.replace('PASS ARM1136 VFP native/C:', 'PASS ARM1136 deferred uniform/vertex partition/C:')
header=(src/'draw_mbx_fast_vs.h').read_text().split('static struct mf_program *mf_create')[0]
out=Path('/tmp/mbx-deferred-partition-test');out.mkdir(exist_ok=True);c=out/'test.c';c.write_text(values['prefix']+header+main)
subprocess.run(['arm-linux-gnueabi-gcc','-O3','-mcpu=arm1136jf-s','-marm','-mfpu=vfp','-mfloat-abi=softfp','-ffp-contract=off','-I'+str(src),str(c),'-lm','-o',str(out/'test')],check=True)
subprocess.run(['qemu-arm','-cpu','arm1136','-L','/usr/arm-linux-gnueabi',str(out/'test')],check=True)
