// Exercise the compiled router's receipt handlers without radio or wall-clock waits.
#include <sstream>
#include <functional>
#include <memory>
#include <map>
#include <set>
#include <vector>
#include <list>
#include <iostream>
#include <cassert>
#define private public
#define protected public
#include <Reticulum.h>
#include <Transport.h>
#include <LinkData.h>
#include <ResourceData.h>
#include <microStore/Adapters/UniversalFileSystem.h>
#include HTIT_ROUTER_SOURCE
#undef protected
#undef private

struct Sink final : RNS::InterfaceImpl {
    Sink() : InterfaceImpl("local-regression") { _IN=true;_OUT=true;_online=true;_bitrate=1000000; }
    std::vector<RNS::Bytes> frames;
    bool send_outgoing(const RNS::Bytes& data) override { frames.push_back(data);return true; }
};
static void require(bool ok, const char* why) { if(!ok)throw std::runtime_error(why); }
static RNS::Link active_link(const RNS::Destination& peer, RNS::Interface& iface) {
    RNS::Link link{RNS::Type::NONE};
    link._object=std::make_shared<RNS::LinkData>(peer);
    link._object->_link_id=RNS::Cryptography::random(16);
    link._object->_hash=link._object->_link_id;
    link._object->_derived_key=RNS::Cryptography::Token::generate_key();
    link._object->_status=RNS::Type::Link::ACTIVE;
    link._object->_attached_interface=iface;
    link.set_link_closed_callback(static_link_closed_callback);
    return link;
}
static void run() {
    static microStore::FileSystem filesystem{microStore::Adapters::UniversalFileSystem()};
    filesystem.init();RNS::Utilities::OS::register_filesystem(filesystem);
    RNS::Reticulum rns;
    rns.start();
    auto* sink=new Sink;
    RNS::Interface iface(sink);
    RNS::Transport::register_interface(iface);
    {
        MsgPack::Packer payload;
        payload.packArraySize(4);
        payload.pack(1.0);
        payload.packBinary(nullptr,0);
        payload.packBinary(nullptr,0);
        payload.packMapSize(0);
        uint8_t prefix[96]{};
        RNS::Bytes wire(prefix,sizeof(prefix));
        wire += RNS::Bytes(payload.data(),payload.size());
        auto decoded=LXMF::LXMessage::unpack_from_bytes(wire,LXMF::Type::Message::DIRECT,true);
        require(decoded.content().size()==0,"empty LXMF fields map decodes without out-of-bounds access");
    }
    {
        MsgPack::Packer payload;
        payload.packArraySize(4);
        payload.pack(1.0);
        payload.packBinary(nullptr,0);
        payload.packBinary(nullptr,0);
        uint8_t prefix[96]{};
        RNS::Bytes wire(prefix,sizeof(prefix));
        wire += RNS::Bytes(payload.data(),payload.size());
        const uint8_t truncated_bin32=0xc6;
        wire += RNS::Bytes(&truncated_bin32,1);
        bool rejected=false;
        try {
            LXMF::LXMessage::unpack_from_bytes(wire,LXMF::Type::Message::DIRECT,true);
        } catch (const std::exception&) { rejected=true; }
        require(rejected,"truncated MessagePack length is rejected without an out-of-bounds read");
    }
    {
        MsgPack::Packer payload;
        payload.packArraySize(4);
        payload.pack(1.0);
        payload.packBinary(nullptr,0);
        payload.packBinary(nullptr,0);
        uint8_t prefix[96]{};
        RNS::Bytes wire(prefix,sizeof(prefix));
        wire += RNS::Bytes(payload.data(),payload.size());
        const uint8_t oversized_bin32[]={0xc6,0xff,0xff,0xff,0xff};
        wire += RNS::Bytes(oversized_bin32,sizeof(oversized_bin32));
        bool rejected=false;
        try {
            LXMF::LXMessage::unpack_from_bytes(wire,LXMF::Type::Message::DIRECT,true);
        } catch (const std::exception&) { rejected=true; }
        require(rejected,"oversized MessagePack length is rejected before 32-bit wraparound");
    }
    {
        RNS::Identity departing,peer_identity;
        RNS::Destination recipient(peer_identity,RNS::Type::Destination::OUT,RNS::Type::Destination::SINGLE,"lxmf","delivery");
        RNS::Identity::remember(RNS::Identity::get_random_hash(),recipient.hash(),peer_identity.get_public_key());
        auto owner=std::make_unique<LXMF::LXMRouter>(departing);
        auto offset=[&](const void* field){return static_cast<const uint8_t*>(field)-reinterpret_cast<const uint8_t*>(owner.get());};
        std::cout << "ROUTER_LAYOUT size=" << sizeof(*owner)
                  << " delivered_callback=" << offset(&owner->_delivered_callback)
                  << " failed_callback=" << offset(&owner->_failed_callback)
                  << " pending_inbound=" << offset(&owner->_pending_inbound_pool)
                  << " direct_links=" << offset(&owner->_direct_links_pool) << '\n';
        auto peer_link=owner->get_link_for_destination(recipient.hash());
        require(bool(peer_link),"real outbound LXMF link created");
        auto* slot=find_router_registry_slot(recipient.hash());
        require(slot && slot->router==owner.get(),"outbound peer callback registered to router");
#ifndef HTIT_PROBE_LATE_CLOSE
        peer_link.teardown();
#endif
        owner.reset();
#ifdef HTIT_PROBE_LATE_CLOSE
        peer_link.teardown();
#endif
#ifndef HTIT_PROBE_STALE_CALLBACK
        require(!find_router_registry_slot(recipient.hash()),"router destruction removes outbound peer registry entries");
#endif
        RNS::Identity replacement_identity;
        auto replacement=std::make_unique<LXMF::LXMRouter>(replacement_identity);
#ifdef HTIT_PROBE_CROSS_PEER
        RNS::Identity second_peer_identity;
        RNS::Destination second_peer(second_peer_identity,RNS::Type::Destination::OUT,RNS::Type::Destination::SINGLE,"lxmf","delivery");
        RNS::Identity::remember(RNS::Identity::get_random_hash(),second_peer.hash(),second_peer_identity.get_public_key());
        auto proof_destination=second_peer;
#else
        auto proof_destination=recipient;
#endif
        auto new_link=replacement->get_link_for_destination(proof_destination.hash());
        new_link.status(RNS::Type::Link::ACTIVE);new_link.attached_interface(iface);
        new_link._object->_derived_key=RNS::Cryptography::Token::generate_key();
        int completed=0;
        replacement->register_delivered_callback([&](LXMF::LXMessage&){++completed;});
        LXMF::LXMessage message(proof_destination,replacement->delivery_destination(),RNS::Bytes("replacement proof"));
        require(replacement->send_via_link(message,new_link),"replacement router sends to proof peer");
        auto proof=RNS::Transport::receipts().back();
        LXMF::LXMRouter::static_proof_callback(proof);
        require(completed==1,"proof callback reaches replacement once without freed-router dispatch");
        new_link.teardown();replacement.reset();
        require(!find_router_registry_slot(recipient.hash()),"replacement destruction clears peer registry again");
    }
    {
        auto sync_router=std::make_unique<LXMF::LXMRouter>(RNS::Identity());
        _active_sync_router=sync_router.get();
        sync_router.reset();
#ifndef HTIT_PROBE_SYNC_CALLBACK
        require(_active_sync_router==nullptr,"router destruction clears propagation-sync callback owner");
#else
        static_list_failed_cb(RNS::RequestReceipt(RNS::Type::NONE));
#endif
    }
    RNS::Identity local, remote;
    LXMF::LXMRouter router(local);
    RNS::Destination peer(remote,RNS::Type::Destination::OUT,RNS::Type::Destination::SINGLE,"lxmf","delivery");
    auto* entry=find_empty_router_registry_slot();
    require(entry,"registry capacity");entry->in_use=true;entry->set_destination_hash(peer.hash());entry->router=&router;
    RNS::Identity other_identity;
    LXMF::LXMRouter other(other_identity);
    int other_failures=0;
    other.register_failed_callback([&](LXMF::LXMessage&){++other_failures;});
    int failures=0;
    router.register_failed_callback([&](LXMF::LXMessage& m){ require(m.state()==LXMF::Type::Message::FAILED,"failure state");++failures; });
    auto cache=[&](const RNS::Link& link) {
        auto* slot=router.find_direct_link_slot(peer.hash());
        if(!slot)slot=router.find_empty_direct_link_slot();
        require(slot,"cache capacity");slot->in_use=true;slot->set_destination_hash(peer.hash());slot->link=link;
    };
    auto send=[&](RNS::Link& link) {
        LXMF::LXMessage message(peer,router.delivery_destination(),RNS::Bytes("regression"));
        require(router.send_via_link(message,link),"send accepted");
        require(!RNS::Transport::receipts().empty(),"receipt created");
        auto receipt=RNS::Transport::receipts().back();
        require(bool(receipt.callbacks()._timeout_fn),"real timeout handler installed");
        return receipt;
    };
    bool unlocked=false,nested_called=false;
    RNS::PacketReceipt context_receipt;
    context_receipt.set_timeout(-1);
    context_receipt.set_timeout_handler([&](const RNS::PacketReceipt&){
        unlocked=!RNS::Transport::_jobs_running;
        RNS::PacketReceipt nested;
        nested.set_timeout(-1);
        nested.set_timeout_handler([&](const RNS::PacketReceipt&){nested_called=true;});
        RNS::Transport::_receipts.push_back(nested);
    });
    RNS::Transport::_receipts.push_back(context_receipt);
    RNS::Transport::_receipts_last_checked=-100;
    RNS::Transport::jobs();
    require(unlocked,"receipt callbacks run outside Transport housekeeping");
    require(!nested_called,"new callback-created receipts wait for next snapshot");
    RNS::Transport::_receipts_last_checked=-100;RNS::Transport::jobs();
    require(nested_called,"new receipt processed on next maintenance pass");
    auto first=active_link(peer,iface);cache(first);
    auto receipt=send(first);
    receipt.set_timeout(-1);
    RNS::Transport::_receipts_last_checked=-100;
    RNS::Transport::jobs();
    require(failures==1,"failure callback exactly once despite duplicate registry entries");
    require(!router.find_direct_link_slot(peer.hash()),"failed link evicted");
    require(first.status()==RNS::Type::Link::CLOSED,"failed link closed");
    receipt.check_timeout();require(failures==1,"repeat timeout ignored");
    auto old=active_link(peer,iface);cache(old);auto late=send(old);
    auto replacement=active_link(peer,iface);cache(replacement);
    late.set_timeout(-1);
    RNS::Transport::_receipts_last_checked=-100;
    RNS::Transport::jobs();
    require(failures==2,"late timeout reported once");
    auto* current=router.find_direct_link_slot(peer.hash());
    require(current && current->link.link_id()==replacement.link_id(),"late timeout and close preserve replacement");
    require(replacement.status()==RNS::Type::Link::ACTIVE,"replacement remains usable");
    auto next=send(replacement);require(bool(next),"fresh message uses replacement");
    LXMF::LXMessage opportunistic(peer,router.delivery_destination(),RNS::Bytes("datagram"),{},LXMF::Type::Message::OPPORTUNISTIC);
    require(router.send_opportunistic(opportunistic,remote),"opportunistic send accepted");
    auto datagram=RNS::Transport::receipts().back();
    datagram.set_timeout(-1);datagram.check_timeout();
    require(failures==3 && other_failures==0,"timeout reaches only its owning router");
    current=router.find_direct_link_slot(peer.hash());
    require(current && current->link.link_id()==replacement.link_id(),"datagram timeout preserves direct link");
    next.status(RNS::Type::PacketReceipt::DELIVERED);
    next.proved(true);next.set_timeout(-1);next.check_timeout();
    require(failures==3 && replacement.status()==RNS::Type::Link::ACTIVE,"delivered receipt does not invalidate link");
    std::cout << "PASS: failed-link eviction, single failure callback, repeated timeout, late-close generation guard, replacement send, opportunistic isolation, delivered receipt\n";
    // Keep two 30 KB transfers alive together. Packet metadata is ephemeral.
    auto bulk_link=active_link(peer,iface),other_link=active_link(peer,iface);
    auto body=RNS::Cryptography::random(30000);
    auto first_bulk=RNS::Resource(body,bulk_link).auto_compress(false).start();
    auto second_bulk=RNS::Resource(body,other_link).auto_compress(false).start();
    require(first_bulk.get_parts()>60 && second_bulk.get_parts()==first_bulk.get_parts(),"two full-size resources prepared");
    RNS::Bytes stream;
    for(const auto& chunk:first_bulk._object->_parts)stream.append(chunk);
    require(bulk_link.decrypt(stream).mid(RNS::Type::Resource::RANDOM_HASH_SIZE)==body,"resource encryption preserves payload");
    RNS::Packet expected(bulk_link,first_bulk._object->_parts[0]);
    expected.context(RNS::Type::Packet::RESOURCE);expected.pack();
    RNS::Bytes request;
    request.append(RNS::Type::Resource::HASHMAP_IS_NOT_EXHAUSTED);
    request.append(first_bulk.hash());
    request.append(first_bulk._object->_hashmap.left(RNS::Type::Resource::MAPHASH_LEN));
    first_bulk.request(request);
    require(sink->frames.back()==expected.raw(),"on-demand part matches standard Packet wire bytes");
    auto first_wire=sink->frames.back();
    first_bulk.request(request);
    require(sink->frames.back()==first_wire && first_bulk._object->_sent_parts==1,"retransmission identical; progress counts unique part once");
    // Feed received chunks through the real receiver and assembly path.
    RNS::Resource received(RNS::Bytes(RNS::Bytes::NONE),bulk_link);
    *received._object=*first_bulk._object;
    auto& rx=*received._object;
    rx._initiator=false;rx._status=RNS::Type::Resource::TRANSFERRING;
    rx._parts.assign(rx._total_parts,RNS::Bytes(RNS::Bytes::NONE));
    rx._part_sent.clear();rx._received_count=0;rx._consecutive_completed_height=-1;
    rx._outstanding_parts=rx._total_parts;rx._window=rx._total_parts;
    rx._hashmap_height=rx._total_parts;rx._req_sent=0;rx._assembly_lock=false;
    RNS::Packet duplicate(bulk_link,first_bulk._object->_parts[0]);
    received.receive_part(duplicate);received.receive_part(duplicate);
    require(rx._received_count==1,"duplicate resource part counted once");
    for(size_t i=first_bulk._object->_parts.size(); i-- > 1;) {
        RNS::Packet incoming(bulk_link,first_bulk._object->_parts[i]);
        received.receive_part(incoming);
    }
    require(received.status()==RNS::Type::Resource::COMPLETE && received.data()==body,"all 30 KB received, authenticated and assembled");
    first_bulk.cancel();second_bulk.cancel();
    std::cout << "PASS: overlapping 30 KB resources, standard wire bytes, retransmission, encrypted receive/assembly\n";
    auto queue_link=active_link(peer,iface);
    auto busy=RNS::Resource(RNS::Cryptography::random(1024),queue_link).start();
    auto queued=queue_link.request(RNS::Bytes("/deferred"),RNS::Cryptography::random(8192),nullptr,nullptr,nullptr,30);
    require(bool(queued) && queued._object->_resource.status()==RNS::Type::Resource::QUEUED,"large request queued behind active transfer");
    busy.cancel();queue_link.tick_resources();
    require(queued._object->_resource.status()==RNS::Type::Resource::ADVERTISED,"queued request resumes after link becomes free");
    queued._object->_resource.cancel();queued.request_timed_out({RNS::Type::NONE});
    std::cout << "PASS: queued large request resumes through cooperative maintenance\n";
    RNS::Transport::deregister_interface(iface);
}

int main() {
    try { run(); return 0; }
    catch(const std::exception& e) { std::cerr << "FAIL: " << e.what() << "\n"; return 1; }
}
