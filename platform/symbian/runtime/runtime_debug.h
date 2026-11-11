// SPDX-License-Identifier: MIT
#pragma once
#include <cstdlib>
#include <cstring>
inline bool n810_runtime_debug() {
 static const bool enabled=[] {const char *p=std::getenv("N810_SYMBIAN_DEBUG");return p&&!std::strcmp(p,"1");}();
 return enabled;
}
