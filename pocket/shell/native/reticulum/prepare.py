"""Build-copy adaptations for the pinned native RNS/LXMF APIs; upstream trees stay clean."""
from pathlib import Path
import shutil,sys

def prepare_resource(source,target):
    s=source.read_text()
    needle='\t// Allocate a receiver-side Resource via the minimal constructor.'
    assert s.count(needle)==1
    s=s.replace(needle,'''\t// Pocket owner frames are bounded; reject before allocating peer-sized vectors.
    \tif (adv._d > 33792 || adv._t > 34816 || adv._n > 128 || adv._l != 1 || adv._x) return {Type::NONE};

    '''+needle)
    a=s.index('\t\tif (_object->_compressed) {',s.index('void Resource::assemble()'))
    b=s.index('\n\t\t// Verify hash',a)
    s=s[:a]+'''\t\t// Reticulum compresses the body after the random prefix. Preserve stock wire format.
    \t\tBytes data = plaintext.mid(Type::Resource::RANDOM_HASH_SIZE);
    \t\tif (_object->_compressed) {
    \t\t\tstd::vector<uint8_t> output(33792);
    \t\t\tbz_stream stream{};
    \t\t\tstream.next_in = (char*)data.data(); stream.avail_in = data.size();
    \t\t\tstream.next_out = (char*)output.data(); stream.avail_out = output.size();
    \t\t\tif (BZ2_bzDecompressInit(&stream, 0, 1) != BZ_OK) throw std::runtime_error("Cannot initialize resource decompressor");
    \t\t\tconst int status = BZ2_bzDecompress(&stream);
    \t\t\tconst bool valid = status == BZ_STREAM_END && stream.avail_in == 0;
    \t\t\tconst size_t count = output.size()-stream.avail_out;
    \t\t\tBZ2_bzDecompressEnd(&stream);
    \t\t\tif (!valid) throw std::runtime_error("Invalid or oversized compressed resource");
    \t\t\tdata = Bytes(output.data(), count);
    \t\t}
    '''+s[b:]
    s=s.replace('const Bytes proof = proof_data.mid(hash_bytes);','const Bytes proof = proof_data.mid(hash_bytes);\n\tif (getenv("POCKET_RNS_TRACE")) fprintf(stderr,"native proof status=%d matches=%d callback=%d segments=%d/%d\\n",int(_object->_status),int(proof==_object->_expected_proof),int(_object->_callbacks._concluded!=nullptr),int(_object->_segment_index),int(_object->_total_segments));')
    result='#include <bzlib.h>\n#include <cstdio>\n#include <cstdlib>\n'+s
    if not target.exists() or target.read_text()!=result:target.write_text(result)

def prepare_packet(source,target):
    text=source.read_text()
    a=text.index('bool PacketReceipt::validate_link_proof(const Bytes& proof, const Link& link, const Packet& proof_packet)')
    b=text.index('// Validate a raw proof',a)
    part=text[a:b]
    assert part.count('if (false) {')==1
    assert part.count('if (true || proof.size() == EXPL_LENGTH) {')==1
    part=part.replace('if (true || proof.size() == EXPL_LENGTH) {','if (proof.size() == EXPL_LENGTH) {')
    part=part.replace('if (false) {','if (const_cast<Link&>(link).validate(signature, _object->_hash)) {')
    part=part.replace('assert(_object);', 'assert(_object);\n\tif(!link || _object->_destination.hash()!=link.link_id())return false;\n\tif (getenv("POCKET_RNS_TRACE")) fprintf(stderr,"native link proof size=%zu hash_match=%d\\n",proof.size(),int(proof.left(Type::Identity::HASHLENGTH/8)==_object->_hash));',1)
    part=part.replace('if (const_cast<Link&>(link).validate(signature, _object->_hash)) {','const bool valid=const_cast<Link&>(link).validate(signature,_object->_hash);\n\t\t\tif (getenv("POCKET_RNS_TRACE")) fprintf(stderr,"native link proof signature_valid=%d\\n",valid);\n\t\t\tif (valid) {')
    result='#include <cstdio>\n#include <cstdlib>\n'+text[:a]+part+text[b:]
    if not target.exists() or target.read_text()!=result:target.write_text(result)

def prepare_link(source,target):
    text=source.read_text()
    needle='PacketReceipt packet_receipt = request_packet.send();'
    assert text.count(needle)==1,'Pinned request receipt API changed'
    text=text.replace(needle,'PacketReceipt packet_receipt = request_packet.receipt_send();')
    if not target.exists() or target.read_text()!=text:target.write_text(text)

def prepare_identity(source,target):
    text=source.read_text()
    needle='''\t\t\t\t\telse {
    \t\t\t\t\t\t// DIVERGENCE: To lessen flash wear, only adding known destination if it's not already known
    \t\t\t\t\t\t// NOTE: A side-effect of this is timestamp will not be updated and record may expire sooner
    \t\t\t\t\t\tremember(packet.get_hash(), destination_hash, public_key, app_data);
    \t\t\t\t\t}'''
    needle=needle.replace('\n    ','\n')
    assert text.count(needle)==1,'Pinned announce-cache behavior changed'
    text=text.replace(needle,'\t\t\t\t\tremember(packet.get_hash(), destination_hash, public_key, app_data);')
    if not target.exists() or target.read_text()!=text:target.write_text(text)

def prepare_lxmf(source,target):
    text=source.read_text()
    needle='PacketReceipt receipt = packet.send();'
    assert text.count(needle)==2,'Pinned LXMF receipt API changed'
    text=text.replace(needle,'PacketReceipt receipt = packet.receipt_send();')
    timeout="""
                receipt.set_timeout_handler([](const PacketReceipt& failed) {
                    PendingProofSlot* proof=find_pending_proof_slot(failed.hash());
                    if(!proof)return;
                    const Bytes hash=proof->message_hash_bytes();
                    proof->clear();
                    for(size_t i=0;i<ROUTER_REGISTRY_SIZE;++i) {
                        auto* router=_router_registry_pool[i].router;
                        if(_router_registry_pool[i].in_use&&router&&router->_failed_callback) {
                            LXMessage message{Bytes(),Bytes()};
                            message.hash(hash);message.state(Type::Message::FAILED);
                            router->_failed_callback(message);
                        }
                    }
                });
    """
    needle='receipt.set_delivery_callback(static_proof_callback);'
    assert text.count(needle)==2
    text=text.replace(needle,needle+timeout)
    needle='\tTRACE("LXMRouter destroyed");'
    assert text.count(needle)==1
    text=text.replace(needle, '\tfor(auto& proof:_pending_proofs_pool)proof.clear();\n'+needle)
    if not target.exists() or target.read_text()!=text:target.write_text(text)

def prepare_stamper(source,target):
    text=source.read_text().replace('#include "Type.h"','#include <LXMF/Type.h>')
    signature='Bytes LXStamper::stamp_workblock(const Bytes& material, uint16_t expand_rounds) {'
    assert text.count(signature)==1
    text=text.replace(signature,'static Bytes pocket_stamp_workblock(const Bytes& material, uint16_t expand_rounds, std::atomic<bool>* cancel) {\n\tif(cancel && cancel->load())return {};')
    needle='for (uint16_t n = 0; n < expand_rounds; n++) {'
    assert text.count(needle)==1
    text=text.replace(needle,needle+'\n\t\tif(cancel && cancel->load())return {};')
    text=text.replace('Bytes packed_n = msgpack_pack_uint16(n);','Bytes packed_n = LXStamper::msgpack_pack_uint16(n);')
    needle='// Count leading zero bits in SHA256(workblock + stamp)'
    assert text.count(needle)==1
    text=text.replace(needle,'Bytes LXStamper::stamp_workblock(const Bytes& material, uint16_t expand_rounds) {\n\treturn pocket_stamp_workblock(material,expand_rounds,nullptr);\n}\n\n'+needle)
    needle='Bytes workblock = stamp_workblock(message_id, expand_rounds);'
    assert text.count(needle)==1
    text=text.replace(needle,'Bytes workblock = pocket_stamp_workblock(message_id,expand_rounds,cancel);\n\tif(cancel && cancel->load())return {Bytes(),0};')
    if not target.exists() or target.read_text()!=text:target.write_text(text)

def prepare_transport(source,target):
    text=source.read_text()
    start=text.index('/*static*/ void Transport::jobs() {')
    end=text.index('/*static*/',start+12)
    part=text[start:end]
    needle='std::map<Bytes, Interface> path_requests;'
    assert part.count(needle)==1
    part=part.replace(needle,'std::set<Link> resource_ticks;\n#if RNS_NEIGHBOR_PROBING\n\tbool scan_neighbors = false;\n#endif\n\t'+needle)
    a=part.index('\t\t\t\t// Pump each active link')
    b=part.index('\n\t\t\t\t_links_last_checked',a)
    part=part[:a]+'\t\t\t\tresource_ticks = active_links;\n'+part[b:]
    assert part.count('_scan_neighbor_stats();')==1
    part=part.replace('_scan_neighbor_stats();','scan_neighbors = true;')
    needle='\t_jobs_running = false;'
    assert part.count(needle)==1
    deferred='''
    // Watchdogs and probes can send packets. Run them after releasing the
    // maintenance flag, otherwise outbound waits forever on this same task.
#if RNS_NEIGHBOR_PROBING
    if (scan_neighbors) {
        try { _scan_neighbor_stats(); }
        catch (const std::exception& e) { ERRORF("Neighbor probe failed: %s", e.what()); }
    }
#endif
    for (auto link : resource_ticks) {
        if (link.status() != Type::Link::CLOSED) {
            try { link.tick_resources(); }
            catch (const std::exception& e) { ERRORF("Resource watchdog failed: %s", e.what()); }
        }
    }
'''
    part=part.replace(needle,needle+deferred)
    result=text[:start]+part+text[end:]
    if not target.exists() or target.read_text()!=result:target.write_text(result)

def prepare_tree(source,target):
    shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.git','.github','Packet.h'))
    prepare_transport(source/'src/microReticulum/Transport.cpp',target/'src/microReticulum/Transport.cpp')
    path=target/'src/microReticulum/Packet.h'
    text=(source/'src/microReticulum/Packet.h').read_text()
    for needle,replacement in (('int16_t _timeout = 0;','double _timeout = 0;'),('set_timeout(int16_t timeout)','set_timeout(double timeout)')):
     assert text.count(needle)==1,'Pinned packet receipt timeout type changed'
     text=text.replace(needle,replacement)
    if not path.exists() or path.read_text()!=text:path.write_text(text)

def prepare_msgpack(source,target):
    shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.git','Packer.h','Unpacker.h'))
    for name,needle,replacement in (
     ('Packer.h','    private:\n        void packRawByte','    public:\n        void packRawByte'),
     ('Unpacker.h','    class Unpacker {\n','    class Unpacker {\n    public:\n')):
     path=target/'MsgPack'/name;text=(source/'MsgPack'/name).read_text()
     assert text.count(needle)==1,(name,'Pinned MessagePack header changed')
     text=text.replace(needle,replacement)
     if not path.exists() or path.read_text()!=text:path.write_text(text)

if __name__=='__main__':
    mode,source,target=sys.argv[1:]
    globals()['prepare_'+mode](Path(source),Path(target))
