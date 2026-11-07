const fs=require('node:fs'),https=require('node:https'),assert=require('node:assert/strict');
const {WebSocket}=require('./runtime/node_modules/ws');
const c=JSON.parse(fs.readFileSync(__dirname+'/.private/config.json'));
const ca=fs.readFileSync(__dirname+'/.private/cert.pem');
const origin=`https://${c.bind}:${c.port}`;
function request(path,method='GET',body='',cookie='',extra={}){return new Promise((resolve,reject)=>{
 const r=https.request(origin+path,{ca,servername:'',method,headers:{Origin:origin,Cookie:cookie,'Content-Type':'application/x-www-form-urlencoded',...extra}},res=>{let data='';res.on('data',d=>data+=d);res.on('end',()=>resolve({code:res.statusCode,data,headers:res.headers}));});r.on('error',reject);r.end(body);
});}
(async()=>{
 const page=await request('/');
 assert.match(page.data,/Trial password/);
 assert.equal(page.headers['referrer-policy'],'same-origin');
 assert.equal((await request('/login','POST','password=x','',{Origin:'null'})).code,403);
 assert.equal((await request('/login','POST','password=x','',{Host:'attacker.invalid'})).code,403);
 assert.equal((await request('/login','POST','password=x','',{Origin:'https://example.com'})).code,403);
 const login=await request('/login','POST',new URLSearchParams({password:c.password}).toString());assert.equal(login.code,303);
 const cookie=login.headers['set-cookie'][0].split(';')[0];
 assert.match((await request('/','GET','',cookie)).data,/Virtual N810 terminal/);
 for(const asset of ['/device.css','/device.js','/device-input.js'])assert.equal((await request(asset,'GET','',cookie)).code,200);
 assert.match((await request('/classic','GET','',cookie)).data,/Fixed 100×30 cells/);
 await new Promise((resolve,reject)=>{const ws=new WebSocket(origin.replace('https:','wss:')+'/terminal',{ca,origin:'https://example.com',headers:{Cookie:cookie}});ws.on('unexpected-response',(_req,res)=>{try{assert.equal(res.statusCode,403);res.resume();resolve();}catch(e){reject(e);}});ws.on('open',()=>{ws.close();reject(Error('Cross-origin WebSocket accepted'));});ws.on('error',()=>{});});
 assert.match((await request('/status','GET','',cookie)).data,/Battery:/);
 const choices=JSON.parse((await request('/sessions','GET','',cookie)).data);assert.ok(choices.some(s=>s.name==='pocket'));
 assert.equal((await request('/new-view','POST','','',{Origin:'https://example.com'})).code,401);
 assert.equal((await request('/new-view','POST','',cookie,{Origin:'https://example.com'})).code,403);
 let independent=choices.find(s=>s.name==='pocket-phone');
 if(process.argv.includes('--new-view')){const created=await request('/new-view','POST','',cookie);assert.equal(created.code,201);independent=JSON.parse(created.data);console.log('Explicit independent view created without launching apps.');}
 function terminal(target='pocket'){return new Promise((resolve,reject)=>{
  const ws=new WebSocket(origin.replace('https:','wss:')+'/terminal?session='+encodeURIComponent(target),{ca,origin,headers:{Cookie:cookie}});
  const timeout=setTimeout(()=>{ws.terminate();reject(Error('terminal timeout'));},10000);
  ws.once('error',reject);ws.once('message',()=>{clearTimeout(timeout);resolve(ws);});
 });}
 const first=await terminal(),second=await terminal(independent?.id||'pocket');
 console.log('Two concurrent browsers received real SSH/tmux output; no input sent.');
 first.terminate();
 const resumed=await terminal();assert.equal(second.readyState,WebSocket.OPEN);
 console.log('Abrupt disconnect/reconnect succeeded; other browser remained connected.');
 await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(Error('heartbeat timeout')),35000);second.once('ping',()=>{clearTimeout(timeout);resolve();});});
 assert.equal(second.readyState,WebSocket.OPEN);second.close();resumed.close();
 console.log('Idle connection received server heartbeat and stayed open.');
 console.log('Login, origin rejection, authenticated assets/status and terminal verified.');
})().catch(e=>{console.error(e.message);process.exitCode=1;});
