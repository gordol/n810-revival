#pragma once
#include <cstdint>
extern "C" {
#include "native_memory.h"
}
namespace eka2l1::mem {
// EKA2 applications discover these shared mappings through HAL/driver APIs.
// Native ARM workers cannot access the emulator's C9200000 kernel window.
// This interval is above both models' user-global sections and below the
// native syscall trampoline; allocation remains owned by the memory model.
inline constexpr std::uint32_t native_kernel_begin = 0xa1000000U;
inline constexpr std::uint32_t native_kernel_end = 0xaf000000U;
static_assert(native_kernel_begin >= 0xa0000000U);
static_assert(native_kernel_begin < native_kernel_end);
static_assert(native_kernel_end < 0xb0000000U);
inline std::uint32_t native_kernel_boundary(std::uint32_t original,bool end,bool old) {
 return !old && native_runtime_enabled() ? (end?native_kernel_end:native_kernel_begin) : original;
}
}
