import pathlib, subprocess, tempfile
source=pathlib.Path(__file__).with_name('n810-fn-remap.c').read_text()
with tempfile.TemporaryDirectory() as d:
 p=pathlib.Path(d)
 text='#define SCREEN_RUN "'+d+'"\n#define main remapper_main\n'+source+'\n#undef main\n'
 text+='''
int main(void) {
 int fds[2]; struct remap_state state={0}; struct input_event e;
 if(pipe(fds)) return 1;
 fcntl(fds[0],F_SETFL,O_NONBLOCK);
 if(handle_key(fds[1],&state,KEY_A,1) || read(fds[0],&e,sizeof(e))!=sizeof(e) || e.value!=1) return 2;
 int lock=open(SCREEN_RUN "/locked",O_CREAT|O_WRONLY,0600);if(lock<0)return 3;close(lock);
 if(handle_key(fds[1],&state,KEY_B,1) || read(fds[0],&e,sizeof(e))!=sizeof(e) || e.code!=KEY_A || e.value!=0)return 4;
 if(read(fds[0],&e,sizeof(e))>=0 || errno!=EAGAIN)return 5;
 if(handle_key(fds[1],&state,KEY_F20,1) || state.fn)return 6;
 unlink(SCREEN_RUN "/locked");
 if(handle_key(fds[1],&state,KEY_B,0) || handle_key(fds[1],&state,KEY_F20,0))return 7;
 if(read(fds[0],&e,sizeof(e))>=0 || errno!=EAGAIN)return 8;
 if(handle_key(fds[1],&state,KEY_C,1) || read(fds[0],&e,sizeof(e))!=sizeof(e) || e.code!=KEY_C || e.value!=1)return 9;
 int quiet=open(SCREEN_RUN "/quiet-charging",O_CREAT|O_WRONLY,0600);if(quiet<0)return 10;close(quiet);
 if(handle_key(fds[1],&state,KEY_D,1) || read(fds[0],&e,sizeof(e))!=sizeof(e) || e.code!=KEY_C || e.value!=0)return 11;
 if(read(fds[0],&e,sizeof(e))>=0 || errno!=EAGAIN)return 12;
 unlink(SCREEN_RUN "/quiet-charging");
 if(handle_key(fds[1],&state,KEY_D,0) || read(fds[0],&e,sizeof(e))>=0 || errno!=EAGAIN)return 13;
 puts("PASS: quiet mode suppresses input and consumes blocked releases");
 puts("PASS: lock releases held keys, suppresses Fn/input, consumes blocked releases, restores typing");return 0;
}
'''
 (p/'test.c').write_text(text)
 subprocess.run(['gcc','-Wall','-Wextra','-Werror',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
