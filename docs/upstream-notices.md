# Upstream notices

This page identifies the upstream releases examined during the component review. Their original license texts remain in the repository. The release includes the corresponding license texts and attribution. Existing copyright holders and permissions remain intact.

## Terminal support

| Component | Source and retained notices |
| --- | --- |
| pyte 0.8.2 | [Published release](https://pypi.org/project/pyte/0.8.2/), [LGPL text](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/terminal/pyte-LICENSE.txt), and [authors](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/terminal/pyte-AUTHORS.txt). All nine bundled Python files match the wheel. Selectel and the pyte authors retain their notices. |
| Linux-derived pyte tables | Pyte identifies `VT100_MAP` and `IBMPC_MAP` as GPL material. Both match the 256-entry tables in [Linux v2.6.39](https://github.com/torvalds/linux/blob/v2.6.39/drivers/tty/vt/consolemap.c). The exact historical copy revision and GPL version remain unspecified in pyte's import. See [the component explanation](license-review.md#terminal-parser-and-character-tables). |
| Pygments-derived palette | Pyte credits Pygments in `graphics.py`. The retained [BSD-2-Clause text](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/pygments-2.1.3-LICENSE.txt) and [author list](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/pygments-2.1.3-AUTHORS.txt) come from release 2.1.3. This is a contemporaneous comparison release; pyte records no exact copied revision. |
| wcwidth 0.2.13 | [Published release](https://pypi.org/project/wcwidth/0.2.13/) and [complete notice](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/terminal/wcwidth-LICENSE.txt), including Jeff Quast's MIT grant and Markus Kuhn's permission notice. All six bundled Python files match the wheel. |

The wheel SHA-256 values match the existing terminal notice. Source files remain inspectable and replaceable. License compatibility for the Linux-derived tables remains under review.

## Native messaging build

These are the exact revisions in `pocket/shell/native/reticulum/dependencies.lock`. The review downloaded each listed license directly from that revision. Root license texts establish the recorded component terms; nested files still retain any more specific notices.

| Upstream | Pinned revision | Retained license |
| --- | --- | --- |
| [ArduinoJson](https://github.com/bblanchon/ArduinoJson) | `733bc4ee82630c88c0a619a883cd3a206efae977` | [MIT](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/arduinojson-LICENSE.txt) |
| [ArxContainer](https://github.com/hideakitai/ArxContainer) | `d6affcd0bc83219b863c20abf7c269214db8db2a` | [MIT](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/arxcontainer-LICENSE.txt) |
| [ArxTypeTraits](https://github.com/hideakitai/ArxTypeTraits) | `702de9cc59c7e047cdc169ae3547718b289d2c02` | [MIT](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/arxtypetraits-LICENSE.txt) |
| [Crypto](https://github.com/attermann/Crypto) | `984dc891330986c302a86c4e312d4f5abcc28359` | [MIT](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/crypto-LICENSE.txt) |
| [DebugLog](https://github.com/hideakitai/DebugLog) | `b581f7dde6c276c5df684e2328f406d9754d2f46` | [MIT](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/debuglog-LICENSE.txt) |
| [MsgPack](https://github.com/hideakitai/MsgPack) | `1f552c31b940d6e9063ee17a4b3fa10c47b27169` | [MIT](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/msgpack-LICENSE.txt) |
| [microStore](https://github.com/attermann/microStore) | `0f28567fe00ab8ab14624a34c2e9e0a000a44c46` | [Apache-2.0](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/microstore-LICENSE.txt) |
| [microReticulum](https://github.com/attermann/microReticulum) | `40fa628809d57140180c1c833559ab96fec992c1` | [Apache-2.0](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/microreticulum-LICENSE.txt) |
| [microLXMF](https://github.com/attermann/microLXMF) | `9876dfff8ec4a2ed1e28adef4375ec57b7e9eb4b` | [GPL-3.0-only](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/microlxmf-LICENSE.txt), as declared by the pinned `library.json`, which credits Torlando Tech LLC. |

The native library includes modified microLXMF sources and links microReticulum. The [component guide](license-review.md#native-messaging) explains the in-process relationship and GPL grants.

The Python parser has a separate lineage. `_umsgpack.py` exactly matches `RNS/vendor/umsgpack.py` in [RNS 1.5.7](https://pypi.org/project/rns/1.5.7/). It retains the MIT notice for u-msgpack-python by Ivan (Vanya) A. Sergeev; RNS's copy includes Python 3 adaptations of version 2.7.1. `parser.py` adapts that RNS release's `RNodeInterface.readLoop` and retains [Mark Qvist's complete permission notice](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/apps/domains/reticulum/THIRD-PARTY-NOTICES/RNS-1.5.7.txt).

## Radio and historical toolchain inputs

The optional RSN adapter fetches [wpa_supplicant 2.12](https://w1.fi/releases/wpa_supplicant-2.12.tar.gz). The verified archive SHA-256 is `08e23937e16d0155e55cab2b51f51fbe10d80a1aa91c4e15442645059b737ef6`. Its [README license section](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/wpa_supplicant-2.12-README.txt) gives BSD-3-Clause terms, and [COPYING](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/wpa_supplicant-2.12-COPYING.txt) records Jouni Malinen and contributors and the earlier licensing history.

The two p54 patches derive from Linux files whose headers declare GPL-2.0-only. The retained [Linux GPL text](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/linux-v5.15-COPYING.txt) accompanies that record. The C55x relocation patch derives from GNU assembler and BFD files granting GPL-2.0-or-later. Their [original COPYING file](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/c55x-binutils-COPYING.txt) is retained, and the patched file hashes match [the checkpoint pins](https://github.com/gordol/n810-revival/blob/main/historical/compute/open-c55x/control-candidate-pins.json).

Additional firmware, SDK, game, font, and dataset terms remain component-specific. The source inventory describes their review status in the [component guide](license-review.md).

## APRS and CCMP

The [aprslib Mic-E parser](https://github.com/rossengeorgiev/aprs-python/blob/c2a0f18ce028a4cced582567a73d57f0d03cd00f/aprslib/parsing/mice.py) supplies the source comparison for the shared APRS decoder. The development record establishes that the implementation was consulted when the decoder was written. The upstream `setup.py` identifies Rossen Georgiev and GPLv2. The [complete GPL text](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/aprslib-LICENSE.txt) and [attribution notice](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/aprslib-NOTICE.txt) accompany the source. The pinned comparison revision is recorded separately from the historically consulted moving `master` URL.

The CCMP test vectors exactly match [FreeBSD test_ccmp.c](https://github.com/freebsd/freebsd-src/blob/b3e7694832e81d7a904a10f525f8797b753bf0d3/tools/regression/net80211/ccmp/test_ccmp.c). Its [retained notice](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/freebsd-ccmp-NOTICE.txt) credits Sam Leffler and Errno Consulting and offers BSD-3-Clause or GPL version 2. The source identifies IEEE P802.11i/D7.0 section I.7.4 as the vector origin.

## JFFS2 extractor

The [Linux JFFS2 Rtime source](https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/tree/fs/jffs2/compr_rtime.c?h=v5.15.224) credits Red Hat, David Woodhouse, and creator Arjan van de Ven. The [retained notice](https://github.com/gordol/n810-revival/blob/main/licenses/upstream/jffs2-rtime-NOTICE.txt) includes the component's GPL-2.0-or-later grant and linking exception. The extractor's original contributions have a compatible grant, as described in [Licensing and attribution](licensing.md).
