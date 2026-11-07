/* Terminal sequences only; no device control API. */
class N810Keyboard{
 constructor(){this.mods={fn:0,shift:0,ctrl:0};this.symbols=false;}
 latch(name){this.mods[name]=(this.mods[name]+1)%3;}
 clear(){for(const k in this.mods)this.mods[k]=0;}
 key(code){
  const named={up:'\x1b[A',down:'\x1b[B',left:'\x1b[D',right:'\x1b[C',enter:'\r',backspace:'\x7f',space:' ',tab:'\t',esc:'\x1b'};
  const fn={q:'1',w:'2',e:'3',r:'4',t:'5',y:'6',u:'7',i:'8',o:'9',p:'0',a:'!',s:'"',d:'@',f:'#',g:'\\',h:'/',j:'(',k:')',l:'*',"'":'?',z:'\t',x:'^',c:'~',v:'%',b:'&',n:'$',m:'|',';':'`','-':'_','+':'=',backspace:'\x1b[3~',up:'\x1b[5~',down:'\x1b[6~',left:'\x1b[H',right:'\x1b[F'};
  const shifted={';':':',',':'<','.':'>','-':'_',"'":'"'};
  let value=named[code]??code;
  if(this.mods.fn){value=fn[code]??value;if(this.mods.shift)value=({j:'[',k:']',g:'{',h:'}'})[code]??value;}
  else if(this.mods.shift)value=/^[a-z]$/.test(code)?code.toUpperCase():shifted[code]??value;
  if(this.mods.ctrl&&value.length===1){const n=value.toUpperCase().charCodeAt(0);if(n>=64&&n<=95)value=String.fromCharCode(n-64);}
  for(const k in this.mods)if(this.mods[k]===1)this.mods[k]=0;
  return value;
 }
}
window.N810Keyboard=N810Keyboard;
