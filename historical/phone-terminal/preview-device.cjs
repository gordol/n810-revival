// Loopback-only responsive QA. No SSH, credentials, radio or terminal input.
const fs=require('node:fs'),http=require('node:http'),path=require('node:path');
const root=__dirname;
const fixture=fs.readFileSync(path.join(root,'../verification/tui-theme-2026-10-16/device-comparison/after.ansi'),'utf8').replace(/\n/g,'\r\n');
const files={'/':['public/index.html','text/html'],'/app.js':['public/app.js','application/javascript'],'/device':['public/device.html','text/html'],'/device.js':['public/device.js','application/javascript'],'/device-input.js':['public/device-input.js','application/javascript'],'/device.css':['public/device.css','text/css'],'/xterm.js':['runtime/node_modules/@xterm/xterm/lib/xterm.js','application/javascript'],'/xterm.css':['runtime/node_modules/@xterm/xterm/css/xterm.css','text/css']};
http.createServer((req,res)=>{
 if(req.url==='/preview.js'){
  res.setHeader('Content-Type','application/javascript');
  return res.end(`window.fetch=async()=>({ok:true,status:200,json:async()=>[{id:'$0',name:'pocket'}],text:async()=>'Offline layout preview — no device connection'});window.WebSocket=class{static OPEN=1;static CONNECTING=0;constructor(){this.readyState=0;setTimeout(()=>{this.readyState=1;this.onopen?.();this.onmessage?.({data:${JSON.stringify('\x1b[2J\x1b[H'+fixture)}});},20);}send(data){const m=JSON.parse(data);if(m.type==='input')document.documentElement.dataset.previewInput=JSON.stringify(m.data);}close(code=1000){this.readyState=3;this.onclose?.({code});}};`);
 }
 const f=files[req.url];if(!f){res.writeHead(404);return res.end();}
 res.setHeader('Content-Type',f[1]);let body=fs.readFileSync(path.join(root,f[0]));
 if(req.url==='/'||req.url==='/device')body=body.toString().replace('<script src="/app.js">','<script src="/preview.js"></script><script src="/app.js">').replace('<title>N810 pocket</title>','<title>N810 offline layout preview</title>');
 res.end(body);
}).listen(8767,'127.0.0.1',()=>console.log('Offline layout QA: http://127.0.0.1:8767'));
