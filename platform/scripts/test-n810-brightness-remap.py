import pathlib, subprocess, tempfile
source=pathlib.Path(__file__).with_name('n810-fn-remap.c').resolve()
with tempfile.TemporaryDirectory() as tmp:
 p=pathlib.Path(tmp)
 (p/'screen').mkdir()
 (p/'test.c').write_text(f'#define SCREEN_RUN "{p / "screen"}"\n' + '''#define main remapper_main
#include "'''+str(source)+'''"
#undef main
#include <assert.h>
static void check(int *fds, struct remap_state *s, int code, int value, int count, int out, int out_value) {
 struct input_event e[8];
 assert(handle_key(fds[1],s,code,value)==0);
 ssize_t n=read(fds[0],e,sizeof(e));
 if (!count) { assert(n<0 && errno==EAGAIN); return; }
 assert(n==(ssize_t)(count*sizeof(*e)));
 assert(e[0].code==out && e[0].value==out_value);
 if(count==2) assert(e[1].code==out && e[1].value==0);
}
int main(void) {
 int fds[2]; struct remap_state s={0}; assert(pipe(fds)==0);
 assert(fcntl(fds[0],F_SETFL,O_NONBLOCK)==0);
 check(fds,&s,KEY_F15,1,0,0,0); check(fds,&s,KEY_F15,0,2,KEY_F15,1);
 check(fds,&s,KEY_F16,1,1,KEY_F16,1); check(fds,&s,KEY_F16,0,1,KEY_F16,0);
 check(fds,&s,KEY_F15,1,0,0,0); check(fds,&s,KEY_F16,1,1,KEY_BRIGHTNESSUP,1);
 check(fds,&s,KEY_F16,2,1,KEY_BRIGHTNESSUP,2);
 check(fds,&s,KEY_F15,0,0,0,0); check(fds,&s,KEY_F16,0,1,KEY_BRIGHTNESSUP,0);
 check(fds,&s,KEY_F15,1,0,0,0); check(fds,&s,KEY_F17,1,1,KEY_BRIGHTNESSDOWN,1);
 check(fds,&s,KEY_F17,0,1,KEY_BRIGHTNESSDOWN,0); check(fds,&s,KEY_F15,0,0,0,0);
 check(fds,&s,KEY_F17,1,1,KEY_F17,1); check(fds,&s,KEY_F17,0,1,KEY_F17,0);
 close(creat(SCREEN_RUN "/power-only",0600)); close(creat(SCREEN_RUN "/blanked",0600));
 check(fds,&s,KEY_A,1,0,0,0); check(fds,&s,KEY_A,0,0,0,0);
 check(fds,&s,KEY_B,1,0,0,0); unlink(SCREEN_RUN "/blanked");
 check(fds,&s,KEY_B,2,0,0,0); check(fds,&s,KEY_B,0,0,0,0);
 check(fds,&s,KEY_B,1,1,KEY_B,1); check(fds,&s,KEY_B,0,1,KEY_B,0);
 check(fds,&s,KEY_LEFTSHIFT,1,1,KEY_LEFTSHIFT,1);
 close(creat(SCREEN_RUN "/blanked",0600));
 check(fds,&s,KEY_Q,1,1,KEY_LEFTSHIFT,0); unlink(SCREEN_RUN "/blanked");
 check(fds,&s,KEY_Q,0,0,0,0); unlink(SCREEN_RUN "/power-only");
 puts("PASS: input inhibition, held-key cleanup and blocked release after wake");
 puts("PASS: fullscreen alone, standalone zoom buttons, brightness repeats and both release orders");
 return 0;
}
''')
 subprocess.run(['gcc','-Wall','-Wextra','-Werror',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
