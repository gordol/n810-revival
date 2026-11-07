"""Production mf_run cache: changing constants/clamp, collisions and strides."""
from pathlib import Path
import ast,subprocess,sys
src=Path(sys.argv[1]);values={}
for n in ast.parse(Path(__file__).with_name('test_arm_vertex_jit.py').read_text()).body:
 if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='prefix':values['prefix']=ast.literal_eval(n.value)
h=(src/'draw_mbx_fast_vs.h').read_text()
stubs='''
#define PIPE_MAX_CONSTANT_BUFFERS 16
#define TGSI_SEMANTIC_COLOR 1
#define TGSI_SEMANTIC_BCOLOR 2
struct raster { bool clamp_vertex_color; };
struct draw { struct raster *rasterizer; };
struct draw_vertex_shader { struct draw *draw; struct { unsigned output_semantic_name[32]; } info; };
'''
main=r'''
int main(void){
 struct mf_program *p=calloc(1,sizeof(*p)),*q=calloc(1,sizeof(*q));assert(p&&q);
 p->inputs=2;p->outputs=1;p->constants=1;p->uniform_count=1;p->vertex_count=1;
 p->uniform_ops[0]=0;p->vertex_ops[0]=1;
 p->ops[0]=(struct mf_op){.dst=MF_RESULT,.opcode=TGSI_OPCODE_MUL,.mask=15};
 p->ops[1]=(struct mf_op){.dst=MF_RESULT+4,.opcode=TGSI_OPCODE_ADD,.mask=15};
 for(unsigned c=0;c<4;c++){
  p->ops[0].src[0][c]=MF_CONST+c;p->ops[0].src[1][c]=MF_CONST+c;
  p->ops[1].src[0][c]=c;p->ops[1].src[1][c]=MF_RESULT+c;
  p->output[0][c]=MF_RESULT+4+c;
 }
 p->output_contiguous[0]=true;*q=*p;
 p->result_cache=true;p->uniform_cache=true;p->cached_vertices=calloc(16,48);assert(p->cached_vertices);
 struct raster rast={0};struct draw draw={&rast};struct draw_vertex_shader vs={.draw=&draw};vs.info.output_semantic_name[0]=TGSI_SEMANTIC_COLOR;
 float constant[4]={0};const void *constants[16]={constant};unsigned sizes[16]={16};
 float input[32][3][4],a[32][2][4],b[32][2][4];unsigned long checked=0;
 for(unsigned mode=0;mode<2;mode++){p->result_cache=mode==0;
 for(unsigned trial=0;trial<10000;trial++){
  if(trial%13==0)for(unsigned c=0;c<4;c++)constant[c]=(int)(trial%17)-8+c*.125f;
  rast.clamp_vertex_color=trial%19<9;
  for(unsigned v=0;v<32;v++)for(unsigned i=0;i<3;i++)for(unsigned c=0;c<4;c++)input[v][i][c]=(float)((v%4)*3+i+c)-(trial/7%5);
  if(trial%11==0){uint32_t zero=0x80000000;memcpy(&input[0][0][0],&zero,4);}
  memset(a,0x6b,sizeof(a));memset(b,0x6b,sizeof(b));
  assert(mf_run(p,&vs,input[0],a[0],constants,sizes,32,sizeof(input[0]),sizeof(a[0])));
  assert(mf_run(q,&vs,input[0],b[0],constants,sizes,32,sizeof(input[0]),sizeof(b[0])));
  assert(!memcmp(a,b,sizeof(a)));checked+=32;
 }
 }
 assert(p->cache_hits>10000);printf("PASS cached mf_run: %lu vertices, %llu hits, constants/clamp/stride/signed-zero exact\n",checked,(unsigned long long)p->cache_hits);
 mf_destroy(p);mf_destroy(q);
}
'''
out=Path('/tmp/mbx-vertex-cache-test');out.mkdir(exist_ok=True);c=out/'test.c'
c.write_text(values['prefix']+h.split('static struct mf_program *mf_create')[0]+stubs+h[h.index('static uint64_t mf_wall_ns'):]+main)
subprocess.run(['cc','-O2','-fsanitize=address,undefined','-I'+str(src),str(c),'-lm','-o',str(out/'test')],check=True)
subprocess.run([str(out/'test')],check=True)
subprocess.run(['arm-linux-gnueabi-gcc','-O3','-mcpu=arm1136jf-s','-marm','-mfpu=vfp','-mfloat-abi=softfp','-I'+str(src),str(c),'-lm','-o',str(out/'test-arm')],check=True)
subprocess.run(['qemu-arm','-cpu','arm1136','-L','/usr/arm-linux-gnueabi',str(out/'test-arm')],check=True)
