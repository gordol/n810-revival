from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parent
source=(root.parent/'after/drivers/tty/vt/vt.c').read_text()
parts=[]
for name in ('con_scroll','insert_char','delete_char','rgb_from_256','rgb_foreground','rgb_background','vc_t416_color'):
 # con_scroll has a driver callback, so select its definition explicitly.
 needle=('static void '+name+'(') if name!='vc_t416_color' else 'static int '+name+'('
 at=source.index(needle)
 start=at;brace=source.index('{',at);depth=1;end=brace+1
 while depth:
  if source[end]=='{':depth+=1
  elif source[end]=='}':depth-=1
  end+=1
 if name=='rgb_from_256':parts.append('struct rgb { u8 r,g,b; };\n')
 parts.append(source[start:end]+'\n')
fb=(root.parent/'after/drivers/video/fbdev/core/fbcon.c').read_text()
start=fb.index('static bool fbcon_rgb_supported(')
end=fb.index('static void fbcon_clear(',start)
with tempfile.TemporaryDirectory(prefix='n810-vt-rgb-') as directory:
 out=Path(directory)
 (out/'vt-functions.inc').write_text('\n'.join(parts))
 (out/'fb-functions.inc').write_text(fb[start:end])
 subprocess.run(['cc','-std=gnu11','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(out),'-I'+str(root/'include'),'-I'+str(root.parent/'after/include'),str(root/'test.c'),'-o',str(out/'test-rgb')],check=True)
 subprocess.run([str(out/'test-rgb')],check=True)
