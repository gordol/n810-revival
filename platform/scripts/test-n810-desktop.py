"""Verify desktop cancellation does not end X or change preferences."""
import pathlib,tempfile,os,subprocess
base=pathlib.Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as t:
 d=pathlib.Path(t); calls=d/'calls'; env=dict(os.environ,PATH=str(d)+':'+os.environ['PATH'],CALLS=str(calls))
 mocks={'n810-gui':'echo "gui $*" >> "$CALLS"; exit 0','n810-profile':'echo "profile $*" >> "$CALLS"','xfce4-session':'exit 0','n810-dialog':'exit 1','nohup':'echo "spawn $*" >> "$CALLS"'}
 for name,body in mocks.items():
  p=d/name;p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o755)
 calls.write_text(''); subprocess.run(['sh',str(base/'n810-desktop'),'switch','xfce'],env=env,check=True)
 assert calls.read_text().splitlines()==['gui status'],calls.read_text()
 calls.write_text(''); subprocess.run(['sh',str(base/'n810-desktop'),'switch','n810'],env=env,check=True)
 assert calls.read_text().splitlines()==['gui status'],calls.read_text()
 assert subprocess.run(['sh',str(base/'n810-desktop'),'switch','arbitrary-command'],env=env).returncode!=0
# The D-Bus backend must receive the config path before it starts xfconfd.
 with tempfile.TemporaryDirectory() as session_dir:
  sd=pathlib.Path(session_dir)
  for name in ['xrdb','xset','xmodmap']:
   q=sd/name;q.write_text('#!/bin/sh\nexit 0\n');q.chmod(0o755)
  q=sd/'n810-profile';q.write_text('#!/bin/sh\necho xfce\n');q.chmod(0o755)
  q=sd/'dbus-run-session';q.write_text('#!/bin/sh\ntest "$XDG_CONFIG_DIRS" = /usr/local/share/n810/xfce:/etc/xdg\n');q.chmod(0o755)
  session=(base.parents[1]/'historical/sidebar-desktop/session.sh').read_text().replace('PATH=/usr/local/bin:/usr/bin:/bin','PATH='+str(sd)+':/usr/bin:/bin')
  q=sd/'session.sh';q.write_text(session)
  subprocess.run(['sh',str(q)],env=env,check=True)
print('PASS: canceled desktop switch does not change profile, stop X or spawn restart; invalid target refused.')
