"""Build-copy adaptations for the pinned native RNS/LXMF APIs; upstream trees stay clean."""
from pathlib import Path
import shutil,sys

def compact_resource_parts(text):
    """Keep ciphertext chunks, not persistent Packet/Destination/header graphs."""
    old='resource._object->_parts.push_back({Type::NONE});'
    assert text.count(old)==1
    text=text.replace(old,'resource._object->_parts.push_back({Bytes::NONE});')
    old='\t_object->_parts.reserve(hashmap_entries);'
    assert text.count(old)==1
    text=text.replace(old,old+'\n\t_object->_part_sent.assign(hashmap_entries, 0);')
    old='\t\tPacket part = Packet(_object->_link, chunk).context(Type::Packet::RESOURCE);\n\t\tpart.pack();\n\n'
    assert text.count(old)==1
    text=text.replace(old,'')
    old='\t\t_object->_parts.push_back(part);'
    assert text.count(old)==1
    text=text.replace(old,'\t\t_object->_parts.push_back(chunk);')
    a=text.index('\t\t\t\t// File this part into the slot.')
    b=text.index('\n\n\t\t\t\t_object->_rtt_rxd_bytes',a)
    text=text[:a]+'\t\t\t\t// Store received ciphertext directly; Packet wrappers add no data.\n\t\t\t\t_object->_parts[i] = part_data;'+text[b:]
    old='if (part) stream.append(part.data());'
    assert text.count(old)==1
    text=text.replace(old,'if (part) stream.append(part);')
    a=text.index('\t\t\tPacket& part = _object->_parts[i];')
    b=text.index('\n\t\t\t_object->_last_activity',a)
    text=text[:a]+"""\t\t\t// Resource chunks are already encrypted. Rebuilding this small packet
            // preserves the wire bytes while releasing its metadata after send.
            Packet part = Packet(_object->_link, _object->_parts[i]).context(Type::Packet::RESOURCE);
            part.send();
            if (part.sent() && !_object->_part_sent[i]) {
                _object->_part_sent[i] = 1;
                _object->_sent_parts++;
            }"""+text[b:]
    return text

def compact_resource_header(text):
    needle='std::vector<Packet> _parts;'
    assert text.count(needle)==1,'Pinned resource part storage changed'
    return text.replace(needle,'std::vector<Bytes, Utilities::Memory::ContainerAllocator<Bytes>> _parts;\n\t\tstd::vector<uint8_t, Utilities::Memory::ContainerAllocator<uint8_t>> _part_sent;')

def prepare_resource(source,target):
    s=compact_resource_parts(source.read_text())
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

QUEUED_REQUEST_PUMP = """
    // A request resource may be queued before it joins the outgoing set.
    // Retain pending receipts while advertising: callbacks can mutate the set.
    std::vector<RequestReceipt> pending(_object->_pending_requests.begin(),_object->_pending_requests.end());
    for(auto& request:pending)request.tick_queued_resource();
"""

QUEUED_REQUEST_METHOD = """
void RequestReceipt::tick_queued_resource() {
    assert(_object);
    if(_object->_status==Type::RequestReceipt::FAILED || _object->_status==Type::RequestReceipt::READY)return;
    if(_object->_resource && _object->_resource.status()==Type::Resource::QUEUED
        && _object->_link.status()==Type::Link::ACTIVE && _object->_link.ready_for_new_resource())
        _object->_resource.advertise_job();
}

"""

def prepare_link(source,target):
    text=source.read_text()
    needle='PacketReceipt packet_receipt = request_packet.send();'
    assert text.count(needle)==1,'Pinned request receipt API changed'
    text=text.replace(needle,'PacketReceipt packet_receipt = request_packet.receipt_send();')
    needle='\tfor (auto& r : outgoing) r.__watchdog_job();'
    assert text.count(needle)==1,'Pinned resource maintenance changed'
    text=text.replace(needle,needle+QUEUED_REQUEST_PUMP)
    pos=text.index('void RequestReceipt::response_resource_progress(')
    text=text[:pos]+QUEUED_REQUEST_METHOD+text[pos:]
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
    direct_timeout="""
                receipt.set_timeout_handler([owner = _delivery_destination.hash(), failed_link = link](const PacketReceipt& failed) mutable {
                    // Consume the proof before callbacks: teardown can re-enter the router.
                    PendingProofSlot* proof=find_pending_proof_slot(failed.hash());
                    if(!proof)return;
                    const Bytes hash=proof->message_hash_bytes();
                    proof->clear();
                    auto* entry=find_router_registry_slot(owner);
                    if(!entry || !entry->router)return;
                    auto* router=entry->router;
                    // A restarted peer cannot know this link. Invalidate only this generation.
                    auto* cached=router->find_direct_link_slot(failed_link.destination().hash());
                    if(cached && cached->link && cached->link.link_id()==failed_link.link_id())
                        cached->clear();
                    if(failed_link.status()!=RNS::Type::Link::CLOSED)failed_link.teardown();
                    if(router->_failed_callback) {
                        LXMessage message{Bytes(),Bytes()};
                        message.hash(hash);message.state(Type::Message::FAILED);
                        router->_failed_callback(message);
                    }
                });
    """
    opportunistic_timeout="""
                receipt.set_timeout_handler([owner = _delivery_destination.hash()](const PacketReceipt& failed) mutable {
                    // Consume the proof before callbacks: teardown can re-enter the router.
                    PendingProofSlot* proof=find_pending_proof_slot(failed.hash());
                    if(!proof)return;
                    const Bytes hash=proof->message_hash_bytes();
                    proof->clear();
                    auto* entry=find_router_registry_slot(owner);
                    if(!entry || !entry->router)return;
                    auto* router=entry->router;
                    if(router->_failed_callback) {
                        LXMessage message{Bytes(),Bytes()};
                        message.hash(hash);message.state(Type::Message::FAILED);
                        router->_failed_callback(message);
                    }
                });
    """
    needle='receipt.set_delivery_callback(static_proof_callback);'
    assert text.count(needle)==2
    parts=text.split(needle)
    text=parts[0]+needle+direct_timeout+parts[1]+needle+opportunistic_timeout+parts[2]
    needle="if (slot) {\n\t\tslot->clear();\n\t\tDEBUG(\"  Removed link from cache\");"
    assert text.count(needle)==1
    text=text.replace(needle,needle.replace("if (slot)","if (slot && slot->link && slot->link.link_id() == link.link_id())"))
    old='\t// Unregister from global registry\n\tRouterRegistrySlot* slot = find_router_registry_slot(_delivery_destination.hash());\n\tif (slot) {\n\t\tslot->clear();\n\t}'
    assert text.count(old)==1,'Pinned router registry cleanup changed'
    text=text.replace(old,'\tfor (auto& slot : _router_registry_pool) {\n\t\tif (slot.in_use && slot.router == this) {\n\t\t\tslot.clear();\n\t\t}\n\t}')
    needle='static RouterRegistrySlot _router_registry_pool[ROUTER_REGISTRY_SIZE];'
    assert text.count(needle)==1
    text=text.replace(needle,needle+'\nstatic LXMRouter* _active_sync_router = nullptr;')
    needle='// Static router pointer for sync callbacks (raw function pointers required by RequestReceipt)\nstatic LXMRouter* _active_sync_router = nullptr;\n\n'
    assert text.count(needle)==1
    text=text.replace(needle,'')
    needle='LXMRouter::~LXMRouter() {\n'
    assert text.count(needle)==1
    text=text.replace(needle,needle+'\tif (_active_sync_router == this) {\n\t\t_active_sync_router = nullptr;\n\t}\n')
    needle='\n\t\t// Register link callbacks (using static functions)'
    assert text.count(needle)==1
    text=text.replace(needle,'\n\t\tif (reg_slot) {\n\t\t\treg_slot->router = this;\n\t\t}\n'+needle)
    needle='\tTRACE("LXMRouter destroyed");'
    assert text.count(needle)==1
    text=text.replace(needle, '\tfor(auto& proof:_pending_proofs_pool)proof.clear();\n'+needle)
    if not target.exists() or target.read_text()!=text:target.write_text(text)

def prepare_lxmf_message(source,target):
    text=source.read_text()
    needle='\t\tfields_p += unpacker.indices[unpacker.index()];'
    assert text.count(needle)==1,'Pinned LXMF fields cursor changed'
    replacement='''\t\tconst size_t field_index = unpacker.index();
\t\tif (field_index > unpacker.indices.size()) {
\t\t\tthrow std::runtime_error("LXMF fields cursor out of range");
\t\t}
\t\tconst size_t fields_offset = field_index < unpacker.indices.size()
\t\t\t? unpacker.indices[field_index] : packed_payload.size();
\t\tif (fields_offset > packed_payload.size()) {
\t\t\tthrow std::runtime_error("LXMF fields offset out of range");
\t\t}
\t\tfields_p += fields_offset;'''
    text=text.replace(needle,replacement)
    if not target.exists() or target.read_text()!=text:target.write_text(text)

RECEIPT_SNAPSHOT = """			// Timeout callbacks can send (for example, closing an expired link).
            // Snapshot under housekeeping, dispatch after releasing _jobs_running.
            if (OS::time() > (_receipts_last_checked + _receipts_check_interval)) {
                receipt_ticks = _receipts;
                while (_receipts.size() > Type::Transport::MAX_RECEIPTS) {
                    PacketReceipt culled = _receipts.front();
                    _receipts.pop_front();
                    culled.set_timeout(-1);
                }
                _receipts_last_checked = OS::time();
            }
"""

RECEIPT_DISPATCH = """

    // Callbacks may append receipts or tear down links. Retain a separate
    // snapshot so neither re-entry nor new sends invalidate this iteration.
    for (auto receipt : receipt_ticks) {
        try {
            receipt.check_timeout();
            if (receipt.status() != Type::PacketReceipt::SENT) _receipts.remove(receipt);
        } catch (const std::exception& e) {
            ERRORF("Receipt timeout failed: %s", e.what());
        }
    }

"""

def prepare_tree(source,target):
    shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.git','.github','Packet.h'))
    transport=target/'src/microReticulum/Transport.cpp'
    text=transport.read_text()
    # Local vendored trees already contain the deferred dispatch patch.
    if 'std::list<PacketReceipt> receipt_ticks;' not in text:
        needle='\tstd::map<Bytes, Interface> path_requests;'
        assert text.count(needle)==1,'Pinned Transport jobs declaration changed'
        text=text.replace(needle,'\tstd::list<PacketReceipt> receipt_ticks;\n'+needle,1)
        a=text.index('\t\t\t// Process receipts list for timed-out packets',text.index('void Transport::jobs()'))
        b=text.index('\n\t\t\t//',a+10)
        text=text[:a]+RECEIPT_SNAPSHOT+text[b:]
        needle='\t_jobs_running = false;'
        pos=text.index(needle,text.index('void Transport::jobs()'))+len(needle)
        text=text[:pos]+RECEIPT_DISPATCH+text[pos:]
        transport.write_text(text)
    link_header=target/'src/microReticulum/Link.h'
    text=link_header.read_text();needle='\t\tvoid __response_timeout_job();'
    assert text.count(needle)==1,'Pinned request receipt declaration changed'
    link_header.write_text(text.replace(needle,needle+'\n\t\tvoid tick_queued_resource();'))
    resource_data=target/'src/microReticulum/ResourceData.h'
    resource_data.write_text(compact_resource_header(resource_data.read_text()))
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
    path=target/'MsgPack/Unpacker.h'
    import hashlib
    upstream=(source/'MsgPack/Unpacker.h').read_bytes()
    assert hashlib.sha256(upstream).hexdigest()=='4de797546ea6a9d1cb40ad23a3bc31185970bc792456cfc7534b9959483421a8','Pinned MessagePack source changed'
    local=(Path(__file__).parent.parent/'executor-libs/MsgPack/MsgPack/Unpacker.h').read_text()
    if path.read_text()!=local:path.write_text(local)

if __name__=='__main__':
    mode,source,target=sys.argv[1:]
    globals()['prepare_'+mode](Path(source),Path(target))
