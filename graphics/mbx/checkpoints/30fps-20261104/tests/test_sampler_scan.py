"""Differential check of the actual Mesa routine, including holes and rebinding."""
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'mesa'))
from prepare_sampler_scan import prepare_sampler_scan

def function(text):
    start = text.index('static void\nupdate_tgsi_samplers(')
    end = text.index('\n\nstatic void\nupdate_fragment_shader', start)
    return text[start:end]

source = Path(sys.argv[1]).read_text()
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    patched = root / 'derived.c'
    patched.write_text(source)
    prepare_sampler_scan(patched)
    once = patched.read_text()
    prepare_sampler_scan(patched)
    assert once == patched.read_text()
    routines = function(source).replace('update_tgsi_samplers', 'reference') + '\n' + function(once).replace('update_tgsi_samplers', 'candidate')
    header = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define PIPE_MAX_SAMPLERS 32
#define PIPE_SHADER_VERTEX 0
#define PIPE_SHADER_FRAGMENT 4
#define PIPE_SHADER_GEOMETRY 3
#define TGSI_FILE_SAMPLER 0
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define MIN2(a,b) ((a)<(b)?(a):(b))
struct softpipe_resource {unsigned timestamp;};
struct softpipe_tex_tile_cache {struct softpipe_resource *texture; unsigned timestamp,id;};
struct shader {int max_sampler;};
struct fragment {struct {int file_max[1];} info;};
struct softpipe_context {
 struct shader *vs,*gs; struct fragment *fs_variant;
 struct softpipe_tex_tile_cache *tex_cache[6][128];
 unsigned num_sampler_views[6];
};
#define softpipe_resource(x) (x)
static unsigned calls[768], count, sampler_calls[6], sampler_count;
static void set_shader_sampler(struct softpipe_context *c,unsigned sh,int max)
{(void)c; sampler_calls[sampler_count++]=sh*65536+(unsigned)(max+1);}
static void sp_tex_tile_cache_validate_texture(struct softpipe_tex_tile_cache *c)
{calls[count++]=c->id;}
'''
    body = r'''
static uint32_t seed=0x381467ad;
static unsigned random_word(void) {seed=seed*1664525+1013904223;return seed;}
int main(void) {
 struct shader vs={-1},gs={7};struct fragment fs={{{-1}}};
 struct softpipe_context a={.vs=&vs,.fs_variant=&fs},b;
 struct softpipe_resource resources[6][128];
 struct softpipe_tex_tile_cache original[6][128],modified[6][128];
 unsigned expected[768],expected_samplers[6];
 for(unsigned trial=0;trial<12000;trial++) {
  a.gs=trial&1?&gs:NULL;
  for(unsigned sh=0;sh<6;sh++) {
   unsigned bound=trial<129?trial:random_word()%129;
   a.num_sampler_views[sh]=bound;
   for(unsigned i=0;i<128;i++) {
    resources[sh][i].timestamp=random_word();
    original[sh][i]=(struct softpipe_tex_tile_cache){
      .texture=i<bound && (i+1==bound || random_word()%3)?&resources[sh][i]:NULL,
      .timestamp=trial%3?random_word():resources[sh][i].timestamp,.id=sh*128+i};
    modified[sh][i]=original[sh][i];
    a.tex_cache[sh][i]=&original[sh][i];
   }
  }
  b=a;
  for(unsigned sh=0;sh<6;sh++)for(unsigned i=0;i<128;i++)b.tex_cache[sh][i]=&modified[sh][i];
  count=sampler_count=0;reference(&a);
  unsigned expected_count=count,expected_sampler_count=sampler_count;
  memcpy(expected,calls,count*sizeof(*calls));memcpy(expected_samplers,sampler_calls,sampler_count*sizeof(*sampler_calls));
  count=sampler_count=0;candidate(&b);
  assert(count==expected_count && sampler_count==expected_sampler_count);
  assert(!memcmp(expected,calls,count*sizeof(*calls)));
  assert(!memcmp(expected_samplers,sampler_calls,sampler_count*sizeof(*sampler_calls)));
  for(unsigned sh=0;sh<6;sh++)for(unsigned i=0;i<128;i++)assert(original[sh][i].timestamp==modified[sh][i].timestamp);
 }
 puts("PASS: 12000 actual-source comparisons, 0..128 bound slots, holes, changed/unchanged timestamps, all stages; patch idempotent");
}
'''
    c = root / 'test.c'
    c.write_text(header + routines + body)
    binary = root / 'test'
    subprocess.run(['cc', '-O2', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', str(c), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
