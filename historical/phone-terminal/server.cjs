const fs = require('node:fs');
const path = require('node:path');
const https = require('node:https');
const crypto = require('node:crypto');
const {execFile} = require('node:child_process');
const pty = require('./runtime/node_modules/node-pty');
const {terminalTarget,attachCommand,parseSessions,sessionListCommand} = require('./workspace.cjs');
const {WebSocketServer} = require('./runtime/node_modules/ws');
const root = __dirname, run = path.join(root, '.private');
const config = JSON.parse(fs.readFileSync(path.join(run, 'config.json')));
const sshArgs = ['-S', config.controlPath, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=4', config.target];
const sessions = new Map(), attempts = new Map();
const expectedOrigin = `https://${config.bind}:${config.port}`;
function sameOrigin(req) {
 return req.headers.host === new URL(expectedOrigin).host && req.headers.origin === expectedOrigin;
}
const clients = new Set(), events = [];
let clientNumber = 0, statusCache, statusAt = 0, pendingStatus;
function diagnostic(event, fields={}) {
 events.push({at:new Date().toISOString(),event,...fields});
 if(events.length>100)events.shift();
 fs.writeFileSync(path.join(run,'connection-events.json'),JSON.stringify(events),{mode:0o600});
}
const files = {
 '/': ['public/device.html','text/html'], '/device':['public/device.html','text/html'], '/classic':['public/index.html','text/html'], '/device.css':['public/device.css','text/css'], '/device.js':['public/device.js','application/javascript'], '/device-input.js':['public/device-input.js','application/javascript'], '/app.js':['public/app.js','application/javascript'],
 '/xterm.js':['runtime/node_modules/@xterm/xterm/lib/xterm.js','application/javascript'],
 '/xterm.css':['runtime/node_modules/@xterm/xterm/css/xterm.css','text/css']
};
function authorized(req) {
 const token = /(?:^|; )session=([a-f0-9]+)/.exec(req.headers.cookie || '')?.[1];
 return sessions.get(token) > Date.now();
}
function reply(res, code, text, type='text/plain') {
 res.writeHead(code, {'Content-Type':type, 'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff', 'Referrer-Policy':'same-origin'});res.end(text);
}
function telemetry() {
 if (statusCache && Date.now()-statusAt < 30000) return Promise.resolve(statusCache);
 if (pendingStatus) return pendingStatus;
 pendingStatus = new Promise(resolve => {
  execFile('/usr/bin/ssh', [...sshArgs, 'n810-pocket-status --section all'], {timeout:10000,maxBuffer:16384}, (err,out) => {
   statusCache = err ? 'N810 SSH unavailable; status not current.' : out;
   statusAt=Date.now();pendingStatus=null;resolve(statusCache);
  });
 });
 return pendingStatus;
}
function remote(command){
 return new Promise((resolve,reject)=>execFile('/usr/bin/ssh',[...sshArgs,command],{timeout:10000,maxBuffer:16384},(err,out)=>err?reject(err):resolve(out)));
}
async function workspaceSessions(){return parseSessions(await remote(sessionListCommand()));}
let creatingView=false;
const server = https.createServer({key:fs.readFileSync(path.join(run,'key.pem')),cert:fs.readFileSync(path.join(run,'cert.pem'))}, async (req,res) => {
 if (req.headers.host !== new URL(expectedOrigin).host) return reply(res,403,'Host rejected');
 if (req.url==='/login' && req.method==='POST') {
  if (!sameOrigin(req)) {
   fs.writeFileSync(path.join(run,'last-origin-rejection.json'),JSON.stringify({origin:req.headers.origin||null,host:req.headers.host,fetchSite:req.headers['sec-fetch-site']||null,expectedOrigin}),{mode:0o600});
   return reply(res,403,'Origin rejected. Open the original phone terminal URL and reload the login page.');
  }
  const ip=req.socket.remoteAddress, a=attempts.get(ip)||{start:Date.now(),n:0};
  if(Date.now()-a.start>60000){a.start=Date.now();a.n=0;} attempts.set(ip,a);
  if(++a.n>5) return reply(res,429,'Wait a minute before trying again.');
  let body='';for await(const chunk of req){body+=chunk;if(body.length>1024)return reply(res,413,'Too large');}
  const password=new URLSearchParams(body).get('password')||'';
  const hash=x=>crypto.createHash('sha256').update(x).digest();
  if(!crypto.timingSafeEqual(hash(password),hash(config.password)))return reply(res,401,'Incorrect password.');
  const token=crypto.randomBytes(32).toString('hex');sessions.set(token,Date.now()+8*3600000);
  res.writeHead(303,{'Location':'/','Set-Cookie':`session=${token}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=28800`});return res.end();
 }
 if(['/session','/sessions','/new-view'].includes(req.url)&&!authorized(req))return reply(res,401,JSON.stringify({authenticated:false}),'application/json');
 if(!authorized(req)) return reply(res,200,'<!doctype html><meta name="viewport" content="width=device-width"><title>N810 login</title><body style="background:#14211c;color:#eee;font:20px system-ui;padding:2em"><h1>N810 pocket</h1><form action="/login" method="post"><label>Trial password <input name="password" type="password" required autofocus></label><button>Connect</button></form>','text/html');
 if(req.url==='/new-view'&&req.method==='POST'){
  if(!sameOrigin(req))return reply(res,403,'Origin rejected');
  if(creatingView)return reply(res,409,'A view is being created');
  creatingView=true;
  try{
   const existing=await workspaceSessions();
   if(existing.filter(s=>s.name.startsWith('phone-view-')).length>=8)return reply(res,409,'Independent view limit reached');
   const name='phone-view-'+crypto.randomBytes(4).toString('hex');
   const id=(await remote(`n810-tmux new-session -d -P -F '#{session_id}' -s ${name} -t pocket`)).trim();
   if(!/^\$\d+$/.test(id))throw Error('Session creation failed');
   return reply(res,201,JSON.stringify({id,name}),'application/json');
  }catch{return reply(res,503,'N810 session unavailable');}
  finally{creatingView=false;}
 }
 if(req.method!=='GET')return reply(res,405,'GET only');
 if(req.url==='/sessions'){
  try{return reply(res,200,JSON.stringify(await workspaceSessions()),'application/json');}
  catch{return reply(res,503,'N810 sessions unavailable');}
 }
 if(req.url==='/session')return reply(res,200,JSON.stringify({authenticated:true}),'application/json');
 if(req.url==='/status')return reply(res,200,await telemetry());
 const file=files[req.url];if(!file)return reply(res,404,'Not found');
 reply(res,200,fs.readFileSync(path.join(root,file[0])),file[1]);
});
const wss = new WebSocketServer({noServer:true,maxPayload:16384,perMessageDeflate:false});
server.on('upgrade',(req,socket,head)=>{
 const target=terminalTarget(req.url);
 if(!target||!authorized(req)||!sameOrigin(req)){
  diagnostic('handshake_rejected',{stage:!authorized(req)?'authentication':'origin_or_path'});
  socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n');return;
 }
 if(clients.size>=4){diagnostic('handshake_rejected',{stage:'capacity'});socket.end('HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\n\r\n');return;}
 wss.handleUpgrade(req,socket,head,ws=>wss.emit('connection',ws,target));
});
wss.on('connection',(ws,target)=>{
 clients.add(ws);const id=++clientNumber;diagnostic('connected',{id,clients:clients.size,view:target==='pocket'?'shared':'selected'});
 const command=attachCommand(target);
 let terminal,exited=false,lastPong=Date.now();
 try {terminal=pty.spawn('/usr/bin/ssh',[...sshArgs.slice(0,-1),'-o','ServerAliveInterval=30','-o','ServerAliveCountMax=3','-tt',config.target,command],{name:'xterm-256color',cols:100,rows:30,env:{...process.env,TERM:'xterm-256color',COLORTERM:'truecolor'}});} catch(e){clients.delete(ws);diagnostic('ssh_spawn_failed',{id});ws.close(1011,'SSH launch failed');return;}
 const heartbeat=setInterval(()=>{
  if(Date.now()-lastPong>120000){diagnostic('heartbeat_timeout',{id});ws.terminate();return;}
  if(ws.readyState===1)ws.ping();
 },30000);
 ws.on('pong',()=>lastPong=Date.now());
 ws.on('error',()=>diagnostic('socket_error',{id}));
 terminal.onData(data=>{if(ws.readyState===1){if(ws.bufferedAmount>2*1024*1024){diagnostic('slow_client',{id});ws.close(1013,'Client too slow');return;}ws.send(data);}});
 terminal.onExit(({exitCode,signal})=>{exited=true;diagnostic('ssh_exit',{id,exitCode,signal});ws.close(1011,'SSH connection ended');});
 ws.on('message',(data,binary)=>{
  if(binary)return;
  let message;try{message=JSON.parse(data.toString());}catch{ws.close(1008,'Reload terminal page');return;}
  if(message.type==='input'&&typeof message.data==='string')terminal.write(message.data);
  else if(message.type==='visibility'&&['visible','hidden'].includes(message.state))diagnostic('visibility',{id,state:message.state});
 });
 ws.on('close',code=>{
  clearInterval(heartbeat);clients.delete(ws);diagnostic('closed',{id,code,clients:clients.size});
  if(!exited){try{terminal.kill();}catch{diagnostic('ssh_cleanup_finished',{id});}}
 });
});
fs.writeFileSync(path.join(run,'server.pid'),String(process.pid),{mode:0o600});
server.listen(config.port,config.bind,()=>console.log(`Phone terminal ready: https://${config.bind}:${config.port}`));
function stop(){for(const ws of clients)ws.close(1001,'Server restarting');server.close();setTimeout(()=>process.exit(),500).unref();}
process.on('SIGTERM',stop);process.on('SIGINT',stop);
