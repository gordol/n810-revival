function terminalTarget(rawUrl){
 const url=new URL(rawUrl,'https://local.invalid');
 if(url.pathname!=='/terminal'||[...url.searchParams.keys()].some(k=>k!=='session')||url.searchParams.getAll('session').length>1)return null;
 const target=url.searchParams.get('session')||'pocket';
 return target==='pocket'||/^\$\d+$/.test(target)?target:null;
}
function attachCommand(target){
 if(target!=='pocket'&&!/^\$\d+$/.test(target))throw Error('Invalid session target');
 return `exec n810-tmux attach-session -f ignore-size -t '${target}'`;
}
function sessionListCommand(){return "n810-tmux list-sessions -F '#{session_id}|#{session_name}'";}
function parseSessions(text){
 return text.trim().split('\n').flatMap(line=>{const match=/^(\$\d+)[|\t](.*)$/.exec(line);return match?[{id:match[1],name:match[2].replace(/[\x00-\x1f]/g,'')}]:[];});
}
module.exports={terminalTarget,attachCommand,parseSessions,sessionListCommand};
