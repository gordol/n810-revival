"""A failed swapoff must never be followed by zram reset."""
import os,pathlib,subprocess,tempfile
source=pathlib.Path(__file__).resolve().parents[1]/'device/n810-zram.init'
with tempfile.TemporaryDirectory() as directory:
 root=pathlib.Path(directory)
 (root/'tools').mkdir()
 (root/'sys').mkdir()
 for name in ('reset','disksize','comp_algorithm'): (root/'sys'/name).write_text('unchanged\n')
 device=str(root/'zram0')
 (root/'swaps').write_text(device+' partition 65532 4096 100\n')
 text=source.read_text().replace('PATH=/usr/sbin:/usr/bin:/sbin:/bin','PATH='+str(root/'tools')+':/usr/bin:/bin')
 text=text.replace('/etc/default/n810-zram',str(root/'defaults')).replace('/dev/zram0',device).replace('/proc/swaps',str(root/'swaps')).replace('/sys/block/zram0',str(root/'sys'))
 (root/'init').write_text(text)
 command=root/'tools/swapoff'
 command.write_text('#!/bin/sh\nexit 1\n');command.chmod(0o755)
 failed=subprocess.run(['sh',str(root/'init'),'stop'],capture_output=True)
 assert failed.returncode!=0
 assert (root/'sys/reset').read_text()=='unchanged\n'
 command.write_text('#!/bin/sh\nexit 0\n')
 subprocess.run(['sh',str(root/'init'),'stop'],check=True)
 assert (root/'sys/reset').read_text()=='1\n'
print('PASS: failed swapoff preserves zram; successful swapoff permits reset.')
