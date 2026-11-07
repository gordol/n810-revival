#include <MsgPack.h>

#include <array>
#include <cstdint>

static bool decode(const uint8_t* wire, size_t size, bool expected) {
    MsgPack::Unpacker unpacker;
    if (!unpacker.feed(wire, size)) return false;

    std::array<uint8_t, 4> value{};
    if (unpacker.deserialize(value) != expected) return false;
    return !expected || (value[0] == 1 && value[3] == 4);
}

int main() {
    const uint8_t bin8_ok[] = {0xc4, 4, 1, 2, 3, 4};
    const uint8_t bin8_large[] = {0xc4, 5, 1, 2, 3, 4, 5};
    const uint8_t bin16_ok[] = {0xc5, 0, 4, 1, 2, 3, 4};
    const uint8_t bin16_large[] = {0xc5, 0, 5, 1, 2, 3, 4, 5};
    const uint8_t bin32_ok[] = {0xc6, 0, 0, 0, 4, 1, 2, 3, 4};
    const uint8_t bin32_large[] = {0xc6, 0, 0, 0, 5, 1, 2, 3, 4, 5};

    return decode(bin8_ok, sizeof(bin8_ok), true)
        && decode(bin8_large, sizeof(bin8_large), false)
        && decode(bin16_ok, sizeof(bin16_ok), true)
        && decode(bin16_large, sizeof(bin16_large), false)
        && decode(bin32_ok, sizeof(bin32_ok), true)
        && decode(bin32_large, sizeof(bin32_large), false)
        ? 0 : 1;
}
