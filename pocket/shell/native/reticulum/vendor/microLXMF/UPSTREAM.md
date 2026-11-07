# Native microLXMF source

Based on `torlando-tech/microLXMF` main at
`d18b6e699e869eccdde811c67097aff2b508be7c`.

The local changes clear stale router and propagation-sync ownership, bound
nested LXMF field parsing, reject invalid metadata-cache hash lengths, and
adapt a MessagePack vector assignment for the ESP32 allocator. The Nokia
native build also carries the bounded MessagePack `Unpacker.h` in
`../../patches/Unpacker.h`.

The source was first validated on the HTIT WIP branch
`wip/microlxmf-upstream-hardening` at `bcebfad`. Keep this vendored copy in
sync with that branch until the fixes land upstream.

The upstream GPL-3.0 license is included in `LICENSE`. The modified MsgPack
parser retains its upstream MIT license in `../../patches/MsgPack-LICENSE`.
