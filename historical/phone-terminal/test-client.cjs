const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const timers=new Map(),listeners={},elements={};let nextTimer=0;
function element(id){return elements[id]||=( {textContent:'',addEventListener(){},getBoundingClientRect(){return {left:0,top:0,width:800,height:480};}} );}
class Socket{
 static OPEN=1;static CONNECTING=0;static all=[];
 constructor(url){this.url=url;this.readyState=0;this.sent=[];Socket.all.push(this);}
 send(data){this.sent.push(JSON.parse(data));}
 open(){this.readyState=1;this.onopen();}
 close(code=1006){this.readyState=3;return this.onclose?.({code});}
}
const document={hidden:false,getElementById:element,querySelector:element,querySelectorAll:()=>[],addEventListener:(name,fn)=>listeners[name]=fn,documentElement:{}};
const context=vm.createContext({Terminal:class{open(){}reset(){}write(){}onData(){}},WebSocket:Socket,document,location:{host:'test.invalid'},window:{addEventListener(){}},setTimeout:(fn,delay)=>{const id=++nextTimer;timers.set(id,{fn,delay});return id;},clearTimeout:id=>timers.delete(id),fetch:async()=>({status:200}),Date,Math,JSON});
vm.runInContext(fs.readFileSync(__dirname+'/public/app.js','utf8'),context);
const first=Socket.all[0];assert.match(first.url,/session=pocket$/);first.open();
(async()=>{
 await first.close();assert.match(elements.connection.textContent,/retry in 1s/);
 const retry=[...timers.values()].find(t=>t.delay===1000);assert.ok(retry);retry.fn();
 assert.equal(Socket.all.length,2);const second=Socket.all[1];second.open();
 document.hidden=true;listeners.visibilitychange();assert.match(elements.connection.textContent,/Backgrounded/);
 document.hidden=false;listeners.visibilitychange();assert.equal(Socket.all.length,3);Socket.all[2].open();
 assert.equal(elements.connection.textContent,'Connected');
 // A failed session check completing after foreground attachment must not replace its status.
 let resolveFetch;context.fetch=()=>new Promise(r=>resolveFetch=r);
 const third=Socket.all[2],closing=third.close();
 listeners.visibilitychange();Socket.all[3].open();resolveFetch({status:200});await closing;
 assert.equal(elements.connection.textContent,'Connected');
 // Repeated startup failures exhaust the bounded retry budget.
 context.fetch=async()=>({status:200});
 for(let n=0;n<10;n++){
  const current=Socket.all.at(-1);await current.close();
  if(elements.connection.textContent.includes('tap Reconnect'))break;
  const timer=[...timers.entries()].filter(([,t])=>t.delay<=30000&&t.delay!==15000).at(-1);
  assert.ok(timer);timers.delete(timer[0]);timer[1].fn();
 }
 assert.match(elements.connection.textContent,/tap Reconnect/);
 elements.workspace.value='$5';elements.workspace.onchange();
 assert.match(Socket.all.at(-1).url,/session=%245$/);
 assert.match(elements['view-note'].textContent,/Independent/);
 assert.ok(Socket.all.every(s=>s.sent.every(m=>m.type==='visibility')));
 console.log('Client retry, background/foreground, asynchronous resume race and bounded failures passed; no input sent.');
})().catch(e=>{console.error(e);process.exitCode=1;});
