const term=new Terminal({cols:100,rows:30,fontSize:14,fontFamily:'monospace',cursorBlink:false,scrollback:500,theme:{background:'#080e0b'},allowProposedApi:false});
term.open(document.getElementById('terminal'));
let socket, retryTimer, attempt=0, stopped=false, selectedSession='pocket';
const connection=document.getElementById('connection');
function status(text){connection.textContent=text;}
function send(s){if(socket?.readyState===WebSocket.OPEN)socket.send(JSON.stringify({type:'input',data:s}));}
function connect(){
 clearTimeout(retryTimer);
 if(document.hidden||stopped||socket?.readyState===WebSocket.OPEN||socket?.readyState===WebSocket.CONNECTING)return;
 status(attempt?'Reconnecting…':'Connecting…');
 let connectedAt=0;
 const current=new WebSocket(`wss://${location.host}/terminal?session=${encodeURIComponent(selectedSession)}`);socket=current;
 const timeout=setTimeout(()=>{if(current.readyState===WebSocket.CONNECTING)current.close();},15000);
 current.onopen=()=>{clearTimeout(timeout);if(document.hidden){current.close(1000,'Phone backgrounded');return;}connectedAt=Date.now();status('Connected');term.reset();current.send(JSON.stringify({type:'visibility',state:'visible'}));};
 current.onmessage=e=>term.write(e.data);
 current.onerror=()=>status('Connection interrupted');
 current.onclose=async e=>{
  clearTimeout(timeout);if(socket!==current)return;socket=null;
  if(document.hidden){status('Backgrounded — apps continue');return;}
  if(stopped)return;
  if(connectedAt&&Date.now()-connectedAt>30000)attempt=0;
  try{const r=await fetch('/session');if(r.status===401){stopped=true;status('Login expired — reload to sign in');return;}}catch{}
  if(socket||document.hidden||stopped)return;
  if(attempt>=8){status(`Disconnected (${e.code}) — tap Reconnect`);return;}
  const delay=Math.min(30000,1000*2**attempt++);
  status(`Disconnected (${e.code}); retry in ${delay/1000}s`);
  retryTimer=setTimeout(connect,delay);
 };
}
const workspace=document.getElementById('workspace');
async function loadSessions(){
 try{
  const response=await fetch('/sessions');if(!response.ok)return;
  const choices=await response.json();workspace.replaceChildren();
  const shared=document.createElement('option');shared.value='pocket';shared.textContent='Shared device console';workspace.append(shared);
  for(const choice of choices){if(choice.name==='pocket')continue;const option=document.createElement('option');option.value=choice.id;option.textContent=choice.name;workspace.append(option);}
  workspace.value=selectedSession;
 }catch{}
}
function selectSession(target){
 selectedSession=target;workspace.value=target;attempt=0;stopped=false;clearTimeout(retryTimer);
 document.getElementById('view-note').textContent=target==='pocket'?'Shared console: tab changes also appear on the N810.':'Independent selection; grouped views still share apps and pane contents.';
 const previous=socket;socket=null;if(previous)previous.close(1000,'View switched');connect();
}
workspace.onchange=()=>selectSession(workspace.value);
document.getElementById('new-view').onclick=async()=>{
 try{
  const response=await fetch('/new-view',{method:'POST'});
  if(!response.ok){status('Could not create view — try again');return;}
  const view=await response.json();await loadSessions();selectSession(view.id);
 }catch{status('N810 session unavailable');}
};
loadSessions();
document.getElementById('reconnect').onclick=()=>{attempt=0;stopped=false;connect();};
document.addEventListener('visibilitychange',()=>{
 if(document.hidden){clearTimeout(retryTimer);if(socket?.readyState===WebSocket.OPEN){socket.send(JSON.stringify({type:'visibility',state:'hidden'}));socket.close(1000,'Phone backgrounded');}status('Backgrounded — apps continue');}
 else{attempt=0;connect();}
});
window.addEventListener('online',()=>{attempt=0;connect();});
window.addEventListener('pageshow',()=>connect());
connect();
term.onData(send);
const keys={up:'\x1b[A',down:'\x1b[B',right:'\x1b[C',left:'\x1b[D',enter:'\r',esc:'\x1b',tab:'\t',menu:'\x1b[1;2P',home:'\x1b[1;2Q',full:'\x1b[1;2R',next:'\x1b[1;2S',prev:'\x1b[15;2~',plus:'+',minus:'-',fit:'f',packets:'p',inspect:'x'};
document.querySelectorAll('[data-key]').forEach(b=>b.onclick=()=>send(keys[b.dataset.key]));
document.getElementById('keyboard').onclick=()=>term.focus();
document.getElementById('screen').onclick=()=>document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen?.();
document.getElementById('refresh').onclick=async()=>{const el=document.getElementById('status');el.textContent='Reading…';try{el.textContent=await(await fetch('/status')).text();}catch{el.textContent='Status unavailable';}};
// Only send terminal mouse coordinates when the foreground program requests them.
let touchStart;
const canvas=document.querySelector('.xterm-screen');
canvas.addEventListener('pointerdown',e=>{if(e.pointerType==='touch')touchStart={x:e.clientX,y:e.clientY};});
canvas.addEventListener('pointerup',e=>{
 if(e.pointerType!=='touch'||!touchStart)return;
 const start=touchStart;touchStart=null;
 if(Math.hypot(start.x-e.clientX,start.y-e.clientY)>10||term.modes.mouseTrackingMode==='none')return;
 const r=canvas.getBoundingClientRect(),x=Math.min(100,Math.max(1,Math.floor((e.clientX-r.left)/r.width*100)+1)),y=Math.min(30,Math.max(1,Math.floor((e.clientY-r.top)/r.height*30)+1));
 send(`\x1b[<0;${x};${y}M\x1b[<0;${x};${y}m`);
});
