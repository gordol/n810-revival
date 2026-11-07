# Licensing and attribution

Copyright © 2026 Thomas Gordon Lowrey IV (for his eligible original contributions).

## Software

This repository collects components with their own licenses. Its directory layout supplies no blanket replacement for those terms. Retain each component's source, attribution and license when redistributing it. A combined program must meet the terms of the components it incorporates, whether delivered as source or binaries.

The [original code grant](licenses/ORIGINAL-CODE-GPL.md) licenses the reviewed original software under **GPL-2.0-or-later**, with the existing **GPL-3.0-only** grant retained for 20 native messaging files. The [scope manifest](https://github.com/gordol/n810-revival/blob/main/LICENSE-SCOPE.json) records 847 entries: 827 GPL-2.0-or-later grants and 20 GPL-3.0-only grants. Eight entries cover original additions to console fonts; their Linux base glyphs keep GPL-2.0-only terms.

These grants permit commercial redistribution, including selling N810s with the covered software, subject to the applicable GPL obligations. Recipients receive those same GPL permissions. Distributed modified binaries require the corresponding source and notices specified by their license. Existing MIT grants and all upstream terms remain intact.

The grant covers rights held by the named licensor. Borrowed expression, third-party components, datasets and assets retain their own terms. Reviewed hashes identify the covered contributions; the grant follows those contributions into modified versions. The [component guide](docs/license-review.md) explains the source boundaries and the [upstream notices](docs/upstream-notices.md) identify retained licenses.

The stock Reticulum route has an additional permission for our original code to interoperate with Mark Qvist's Reticulum-License components. That permission applies only to our rights. The native microLXMF route retains its GPL-3.0-only dependencies. See the [grant](licenses/ORIGINAL-CODE-GPL.md#stock-reticulum-interoperability-permission) for the precise scope.

## Documentation

The [Cat Wormhole License 0.4](LICENSE.md) applies to Thomas Gordon Lowrey IV's original prose in `README.md` and Markdown files under `docs/`. It permits noncommercial use, modification and redistribution with attribution, and reserves the licensor's commercial rights. Its identifier is `LicenseRef-Cat-Wormhole-0.4`.

Quoted material, source excerpts, imported manuals, images, recordings and datasets retain their applicable terms. The documentation license's noncommercial and geographic conditions apply to its expressly covered material. The software grants above supply GPL permissions independently.

Version 0.3 remains in `licenses/Cat-Wormhole-0.3.md`. Earlier grants remain available for copies received under them. Version 0.4 requires covered distributed modifications to retain its terms and specifies source delivery for modified binaries within its scope.

## Contributions

Contributors retain ownership of their eligible original work. Contributions to GPL-covered software must provide compatible GPL permissions and accurate attribution. Those permissions already allow the maintainer and other recipients to modify the software and sell compliant copies or devices.

The [Contributor Agreement](CONTRIBUTOR-AGREEMENT.md) provides additional rights for specifically identified contributions when their owners explicitly accept it. It is relevant to Cat Wormhole-covered material and to rights beyond the public GPL grant. An unsigned agreement supplies no additional rights. [Contributors and attribution](CONTRIBUTORS.md) describes individual credit and the distinction between Git history, provenance and permission.

Copyright protects eligible expression within its legal scope. Ideas, methods and interface concepts are subject to the limits described by the [U.S. Copyright Office](https://www.copyright.gov/help/faq/faq-protect.html).

## Upstream components

| Material | Applicable terms and records |
| --- | --- |
| Linux kernel and derived patches | Linux file notices and GPL terms; pinned inputs in `platform/kernel/source.lock.json`. |
| Mesa and MBX checkpoints | Per-file MIT/GPL and upstream Mesa notices; frozen source manifests. |
| Pocket dependencies | Adjacent licenses and `pocket/shell/vendor/README.md`. |
| HTIT firmware and libraries | `hardware/htit/source-provenance.json` and each retained library license. |
| Fonts and maps | [Font provenance](licenses/FONTS.md) and [map attribution](licenses/MAP-DATA.md). |

Device releases must satisfy every included component's terms and ship the corresponding source required by the actual binaries. The source review records historical uncertainties explicitly; the custom license and contributor agreement have not received professional legal review.

HAIL ERIS. ALL HAIL DISCORDIA.
