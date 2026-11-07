import pathlib,tempfile,subprocess,os
base=pathlib.Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory() as t:
 d=pathlib.Path(t); bindir=d/'bin';bindir.mkdir();run=d/'run';run.mkdir();log=d/'calls'
 env=dict(os.environ,PATH=str(bindir)+':/usr/bin:/bin',CALLS=str(log))
 mocks={'id':'echo 0','start-stop-daemon':'echo "daemon $*" >> "$CALLS"; exit 0','chvt':'echo "chvt $*" >> "$CALLS"','n810-mode':'echo normal','telinit':'echo "telinit $*" >> "$CALLS"','getent':'echo nokia','chown':':'}
 for name,body in mocks.items():
  p=bindir/name;p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o755)
 launcher=d/'launcher';s=(base.parent/'historical/sidebar-desktop/n810-gui-launch').read_text().replace('PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','PATH='+env['PATH']).replace('/run/n810-gui',str(run)).replace('/usr/local/sbin/n810-mode',str(bindir/'n810-mode'));launcher.write_text(s)
 (run/'console-vt').write_text('1\n')
 for action,expected in [('start','chvt 8'),('console','chvt 1')]:
  log.write_text('');subprocess.run(['sh',str(launcher),action],env=env,check=True)
  calls=log.read_text();assert expected in calls and '--retry' not in calls,calls
 (run/'console-vt').write_text('8\n');assert subprocess.run(['sh',str(launcher),'console'],env=env).returncode!=0
 table=d/'inittab';normal='1:2345:respawn:/sbin/getty --noclear 38400 tty1';table.write_text(normal+'\n')
 login=d/'login';login.write_text((base/'scripts/n810-login').read_text().replace('PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','PATH='+env['PATH']).replace('/etc/inittab',str(table)))
 subprocess.run(['sh',str(login),'on'],env=env,check=True);assert '--autologin nokia' in table.read_text()
 subprocess.run(['sh',str(login),'off'],env=env,check=True);assert table.read_text()==normal+'\n'
 table.write_text('1:2345:respawn:custom\n');assert subprocess.run(['sh',str(login),'on'],env=env).returncode!=0;assert 'custom' in table.read_text()
print('PASS: GUI resume/console never stop X; invalid VT refused; autologin on/off roundtrip and custom getty refusal.')
