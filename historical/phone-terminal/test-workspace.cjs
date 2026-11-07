const assert=require('node:assert/strict');
const {terminalTarget,attachCommand,parseSessions,sessionListCommand}=require('./workspace.cjs');
assert.equal(terminalTarget('/terminal'),'pocket');
assert.equal(terminalTarget('/terminal?session=pocket'),'pocket');
assert.equal(terminalTarget('/terminal?session=%245'),'$5');
for(const url of ['/terminal?session=x;id','/terminal?command=id','/terminal?session=pocket&session=%245','/terminal?session=%24%28id%29','/other'])assert.equal(terminalTarget(url),null);
assert.throws(()=>attachCommand('pocket; id'));
assert.equal(attachCommand('$5'),"exec n810-tmux attach-session -f ignore-size -t '$5'");
assert.equal(attachCommand('pocket'),"exec n810-tmux attach-session -f ignore-size -t 'pocket'");
assert.deepEqual(parseSessions('$0\tpocket\n$5\tpocket-phone\ninvalid\tname\n'),[{id:'$0',name:'pocket'},{id:'$5',name:'pocket-phone'}]);
console.log('Shared default, validated session IDs, injection rejection and session listing passed.');

assert.deepEqual(parseSessions('$0|pocket\n$5|my view|extra\n'),[{id:'$0',name:'pocket'},{id:'$5',name:'my view|extra'}]);
assert.equal(/[\x00-\x1f]/.test(sessionListCommand()),false);
assert.match(sessionListCommand(),/session_id}\|#{session_name/);
