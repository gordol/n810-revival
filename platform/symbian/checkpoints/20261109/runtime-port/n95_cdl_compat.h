// Private-runtime compatibility for the validated RM-320 ROM only.
// Original ROM/DLL files are never changed or included in this source.
#pragma once
#include <mem/mem.h>
#include <cpu/arm_interface.h>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <stdexcept>

inline void apply_n95_cdl_cancel_compat(eka2l1::memory_system *memory,
                                      eka2l1::arm::core *cpu) {
    // This ROM's CDL DoCancel supplies an unrelated stack TRequestStatus to
    // REComSession::CancelNotifyOnChange. Its ECom implementation requires the
    // original notification status. During slow startup, CDL's shutdown timer
    // exposes this mismatch and CActive::Cancel then waits forever.
    // Version fingerprints cover the caller, callee and watcher vtable. These
    // are compatibility checks, not authentication of untrusted firmware.
    struct check {std::uint32_t address;unsigned length;std::uint64_t fingerprint;};
    const check checks[]={{0x834dca48,22,0xd9956f7928b53bc3ULL},
                          {0x804c6f78,30,0xc277e86c0a8634e5ULL},
                          {0x834dd4c0,20,0x783544a8dfd4a028ULL}};
    for(const auto &check:checks) {
        auto *bytes=static_cast<const std::uint8_t *>(memory->get_real_pointer(check.address));
        if(!bytes)throw std::runtime_error("N95 CDL compatibility region missing");
        std::uint64_t hash=14695981039346656037ULL;
        for(unsigned i=0;i<check.length;++i)hash=(hash^bytes[i])*1099511628211ULL;
        if(hash!=check.fingerprint)throw std::runtime_error("N95 CDL compatibility version mismatch");
    }
    // Independently implemented Thumb tail-call, preserving the caller's LR:
    // r1=&this->iStatus; r0=this->iEcom; tail-call CancelNotifyOnChange(r0,r1).
    // CActive::Cancel itself performs the subsequent WaitForRequest. No request
    // is fabricated: the real ECom server must process cancellation IPC 1.
    const std::uint16_t thunk[]={0x1d01,0x6a00,0x4b00,0x4718,0x6f79,0x804c};
    std::memcpy(memory->get_real_pointer(0x834dca48),thunk,sizeof(thunk));
    cpu->imb_range(0x834dca48,sizeof(thunk));
    std::printf("private_runtime_compat=n95_cdl_cancel original_files_unchanged=1\n");
}
