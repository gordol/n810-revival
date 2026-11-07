const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ctx={window:{}};vm.createContext(ctx);vm.runInContext(fs.readFileSync(__dirname+'/public/device-input.js','utf8'),ctx);const Keys=ctx.window.N810Keyboard,k=new Keys();
assert.equal(k.key('q'),'q');k.latch('fn');assert.equal(k.key('q'),'1');assert.equal(k.key('q'),'q');
k.latch('fn');k.latch('fn');assert.equal(k.key('m'),'|');assert.equal(k.key('up'),'\x1b[5~');assert.equal(k.mods.fn,2);k.latch('fn');assert.equal(k.mods.fn,0);
k.latch('ctrl');assert.equal(k.key('c'),'\x03');assert.equal(k.key('c'),'c');
k.latch('shift');assert.equal(k.key('a'),'A');assert.equal(k.key('a'),'a');
k.latch('shift');k.latch('fn');assert.equal(k.key('j'),'[');assert.equal(k.mods.fn,0);assert.equal(k.mods.shift,0);
k.latch('ctrl');k.latch('ctrl');k.clear();assert.equal(k.key('d'),'d');assert.equal(k.key('enter'),'\r');assert.equal(k.key('backspace'),'\x7f');
console.log('Virtual keyboard: literal input, one-shot/locked Fn/Shift/Ctrl, overlay symbols/navigation and clear passed; no network/device calls.');
