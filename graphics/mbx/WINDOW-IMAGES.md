# Rendered window images (opt-in candidate)

Status: physical Nokia image residency, texture reuse and eight-reuse admission are verified. Ninety-six interaction snapshots matched exactly; separate capture-free controls measured a sustained-movement improvement. The feature remains opt-in; installed Pocket defaults were not changed.

The native renderer can materialize small immutable window batches into 128x128 RGBA images. After eight reuses, subsequent replay admits an eligible window to image storage. Movement then samples those images instead of replaying the window geometry. Admission requires sole native ownership; existing source references remain valid. Compiled geometry is retired when coordinates are rebased into the image. Changed content produces a replacement; large or ineligible batches retain the existing native geometry path. Terminal rendering is unchanged.

Enable all three explicitly: kernel `gpu_window_images=1`, Mesa `N810_MBX_WINDOW_IMAGES=1`, native `POCKET_SCENE_WINDOW_IMAGES=1`. Keep the established separate-alpha path enabled. The arena contains fourteen cache slots and two scratch slots, with a leading guard and a guard after every image (1,118,208 bytes total). Transparent images use GPU RGB and alpha passes followed by GPU channel merge. No image readback or reupload is required.

The wire carries session/generation/slot tokens, never caller-provided GPU addresses. Destination/source aliasing, stale generations, unsupported dimensions, invalid resource layouts and incomplete jobs are rejected. A completed image is published only after GPU completion and guard verification. New service sessions invalidate old tokens. Cache exhaustion fails closed in Mesa; the native admission budget avoids requesting more live slots than available.

`N810_MBX_TEXTURE_SUBSET=1` additionally lets a draw use a subset or reordering of the verified texture arena. It remaps draw indices to the resident descriptor order and omits unchanged texture payloads. Rendering a new window invalidates snapshots containing image tokens that may be retired; uploaded-only glyph snapshots survive. RGB and alpha passes both use compact texture references when their canonical bytes match. Kernel validation remains mandatory after compact expansion.

Local checks:

- `python3 tests/check_window_images.py`: sanitizer-backed token lifetime, mixed resources, all sixteen sampler addresses/pitches, texture subset and exact reference expansion.
- `python3 tests/check_prepared.py`: prepared commands and service ownership regression checks.
- ARM-emulated native desktop reference: cached replay exact, geometry/coverage preserved, translated composition within the existing one-step RGB565 channel bound. One reference scene differs from direct composition in 240 pixels by one blue step due to the intermediate RGBA image.
- Kernel import CRC verification and native/Mesa cross-builds pass.

Physical checks completed with the same guarded driver and 800x480 target, Balanced unchanged and background off. The bounded proof matched all 384,000 pixels exactly. Mixed changes and sustained movement each passed 48 full-frame comparisons with zero differing pixels, no GPU readback and no CPU presentation sink. All fault counters remained zero, normal module removal succeeded, and the prior VT, panel state, preferences and boot identity were restored. Bluetooth remained down and radio owners absent; SSH transport stayed available.

Capture-free timing controls (no per-frame screenshot, hash or file I/O):

| Workload | Baseline FPS | Candidate FPS | Baseline CPU ms/redraw | Candidate CPU ms/redraw | Peak RSS KiB before/after |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mixed content/focus/resize/move | 6.995 | 7.037 | 102.495 | 103.417 | 36152 / 36392 |
| Sustained window movement | 8.273 | 10.922 | 84.059 | 60.652 | 35924 / 36828 |

Movement improved 32.0% in FPS and reduced CPU per redraw 27.8%; the mixed workload is essentially unchanged. Mixed-workload texture uploads fell from 2,246,400 bytes to zero. Sustained movement rendered four tiles and sampled them 164 times instead of rebuilding their geometry. Both variants used the same guarded image arena; enabling it costs 1,118,208 kernel bytes in addition to process RSS. These are two bounded workloads, not an assertion that every app or large window gains the same amount. Large/ineligible batches retain GPU geometry replay.

All rendering still submits synchronously and the panel requested full-screen RFBI updates in these runs. Residency removes repeated window geometry and CPU readback; it does not remove final DMA presentation, model/text layout, or mandatory driver validation. This is not 30 FPS desktop performance.

Prepared host package: `outputs/gpu-window-images-20261109` in the project workspace. Final timing evidence: `timing/summary.json`; separate exact-pixel evidence: `results/summary.json`; framebuffer image: `results/verified-desktop.png`. The older 7.7299 FPS damage-only run used a different instrumentation context and is not the matched baseline above.

The first matched physical run measured baseline 5.2865 FPS /111.0271 CPU ms per redraw and eager images 3.1239 FPS /221.0666 CPU ms per redraw. Both used the same guarded image arena, 800x480 target, background off and Balanced. Eager image creation generated 100 images and 332 GPU jobs, with 39.76 MB texture uploads. Correcting compact reuse reduced transport but did not resolve the creation cost (3.1365 FPS). Do not promote eager image admission. Original installed defaults remain untouched.

## Shared installed graphics release

The verified artifacts through `14ecc22` are installed persistently on the Nokia at `/usr/local/lib/n810-graphics/releases/20261109-14ecc22`; `/usr/local/lib/n810-graphics/current` selects this release. `MANIFEST.json` pins the module, Mesa and native-library hashes. `defaults.json` lists the corresponding feature settings. Experimental checkpoint verification and the inactive partial-RFBI kernel are excluded.

An owner resolves `current` once at launch, verifies the manifest and kernel match, and uses that same release for its module and Mesa library. Existing running processes/modules retain their original code until the owner's next clean launch. The Symbian owner has been requested to adopt this shared path and verify its workload; Symbian adoption is not yet confirmed. Pocket-native window residency and presenter overlap require their native caller/settings and do not automatically change another presenter's code.

No module was left loaded by installation, and no service or radio was restarted. Previous private packages remain available for rollback. A future shared promotion retains the old `current` target as `previous`; release directories are retained. Never mix files from different releases or mutate a versioned release in place.

## Normal Pocket entry activation

`/usr/local/sbin/n810-pocket-console run` now selects the managed GPU desktop when `/usr/local/lib/n810-pocket/renderer` contains `gpu` (the installed default). `tui` selects the preserved console helper. The normal tmux workspace command remains separate.

The supervisor pins the shared graphics release, performs the existing GPU startup proof, and hands only an inherited bounded-render device and framebuffer to the `nokia` GUI process. It retains root for VT/service lifetime. Scene composition reuses the display's loaded native library, avoiding an obsolete second `window.so`. The current supervisor is detached from SSH; rendering has no benchmark timer. Live verification confirmed one shared renderer/Mesa mapping, UID1000, GPU transform/lighting/rasterization and zero CPU-raster triangles. Existing Nokia graphics checks pass. The user confirmed touch and keyboard on the normal GUI.

`/run/n810-pocket-native/active.json` identifies the actual supervisor/GUI and log path. Other device tests must arrange a clean supervisor stop before taking the exclusive GPU; never unload beneath the live GUI. The renderer selector, previous launcher backup under `/usr/local/lib/n810-pocket/normal-gpu-rollback-20261109`, and unchanged TUI session provide rollback. Current startup retains the existing GPU service's external-power readiness requirement. No reboot, radio restart or kernel replacement was performed.

## Bounded DMA and preparation follow-up

Release `20261109-8eee68a` is the shared selected build for the next normal Pocket launch. The preceding `20261109-14ecc22` release and managed source backups remain available. This promotion leaves Pocket stopped and the module unloaded for Symbian.

The first candidate combined exact-input window preparation caching, damaged-page mapping, session DMA-channel reuse and wider image admission. It passed pixels but regressed short movement timing (9.857 to 9.712 FPS), so wide admission is retained behind `POCKET_SCENE_WIDE_CACHE=1`; default remains four tiles per batch. Channel requests fell 49 to 1 and mapped pages 18,424 to 7,672, but DMA time improved only 37 ms over 48 frames. Those counters do not establish DMA as the primary limit.

A CPU-time diagnostic then identified repeated unchanged palette conversion and redundant visibility scans. The final combination caches palette conversion by exact inputs, reuses one visible-window list per compose, retains the four-tile cache default, and uses normal checkpoint verification for Pocket. It measured 13.919 FPS versus 9.857, 49.341 versus 68.824 CPU ms/redraw, and 37,924 versus 36,900 KiB peakRSS. This is 41.2% higher FPS and 28.3% less CPU in the matched movement workload. All 48 full-frame snapshots matched exactly, with no GPU readback/CPU sink, guard faults, reboot or persistent session change. Capture-free timing and pixel checks are separate; CPU profiling is diagnostic only.

The release's `pocket_module` defaults select bounded mapping, channel reuse and checkpoint verification. Mandatory admission, ownership, completion and DMA synchronization remain enabled; full checks run at resource changes/periodic checkpoints/close. Symbian keeps its own validated settings and must validate checkpoint mode before enabling it. The normal supervisor now updates its private module hash/settings from the selected release, so it cannot accidentally keep the template's former module hash. Evidence: project `outputs/desktop-next-20261109/summary.json` and saved raw logs.


## Retained-batch damage and output-tile comparison

Candidate `1bd916c` stores immutable batch bounds for admission and skips batches outside final DMA damage. Native reconstruction checks passed, and both 800x480 and 256x256 output-tile candidates matched all 48 physical mixed-interaction snapshots exactly. Tile partitioning does not change the full 800x480 destination or image quality.

The old movement benchmark starts and finishes a drag every frame, invalidating the full-width header on every operation. A separate continuous workload now presses once, performs 48 live movements, and releases once after 21 warmup frames. Its result must not be described as a speedup over the older 13.919 FPS test. One initial baseline had ambiguous outline/live setup and is excluded from speedup claims.

| Explicit live-drag workload | FPS | CPU ms/redraw | Peak RSS KiB |
| --- | ---: | ---: | ---: |
| Installed library, 800x480 output tile | 18.235 | 39.302 | 36476 |
| Batch-culling candidate, 800x480 output tile | 10.941 | 41.054 | 36992 |
| Batch-culling candidate, 256x256 output tiles | 16.940 | 44.027 | 37088 |

These bounded runs do not establish a net gain. Small tiles reduced observed raster time but multiplied full-transition jobs and regressed the mixed workload. No candidate was promoted: shared `current` remains `20261109-8eee68a`. All runs closed without GPU faults and restored the previous VT, panel, preferences and boot; Pocket remained stopped and the lock was released. Raw results and the excluded-baseline explanation are in project `outputs/batch-cull-20261109/summary.json` and `reports.json`.

The next local preparation change adds exact `damage_bounds` to the native model map, removing the temporary index export and its second traversal from pixel preparation. It does not consume damage or change TUI scheduling. Randomized mutation/removal/clear tests and pixel-desktop tests pass locally; this change has no physical CPU/FPS measurement yet and is not installed.


## Native damage bounds and atlas-page grouping candidate

`damage_bounds` reads the native dirty map directly, avoiding the temporary uint32 index export and second scan in pixel preparation. Older native libraries retain the previous index-based path. The new module cross-builds for ARM1136 with the existing soft-float ABI; host native-scene and pixel-desktop tests pass.

`POCKET_SCENE_PAGE_GROUPS=1` builds stable per-atlas-page primitive lists once for immutable geometry. Replay preserves page-major draw order and original order within each page, visits each page group directly, skips unused pages, and avoids the filtered vertex-array copy. Position, UV, color, blending, clipping and destination occlusion still use the existing draw path. This is CPU submission preparation; the MBX continues transform, lighting and rasterization.

Three local ARM-emulated text cases cover unclipped, clipped and translated output. All 1,152,000 RGB565 pixels match exactly for ordinary arrays, indexed arrays and VBO replay. In the single 800x480 output-target check, triangle candidate visits fall from 12,246 to 3,066, with no filtered vertex copies. These counts are not a physical FPS or CPU measurement. The earlier whole-batch damage-culling experiment is now opt-in via `POCKET_SCENE_DAMAGE_CULL=1` and is disabled in the next comparison.

The owner can select a manifest-pinned `_cellengine.abi3.so` and validated page-group default from an immutable graphics release. Old releases retain their existing native module and disabled grouping. Prepared comparison files are in project `outputs/damage-bounds-20261109`; shared `current` has not been changed by this candidate.


## Physical native-preparation result

Release `20261109-ab93286` contains direct native damage bounds, row-extrema scanning and opt-in compiled atlas-page groups selected by the normal Pocket owner. The preceding `20261109-8eee68a` release remains the rollback. Kernel module and Mesa are unchanged from that release; the shared quiet-Mesa source changes are merged separately in `14704e0`, not substituted during this comparison.

The initial 192-frame pair reduced app CPU 7.4% but measured 17.946 versus 17.379 FPS, with higher total system CPU in the candidate interval. Those results are retained. A single longer, 960-frame pair added process and vmstat snapshots only at the measurement boundaries. It measured:

| Warm live-drag workload | Installed baseline | Native preparation candidate |
| --- | ---: | ---: |
| Redraws / second | 18.100 | 19.023 |
| App CPU ms / redraw | 41.326 | 38.257 |
| Peak RSS KiB | 36868 | 36736 |
| Major faults during measurement | 0 | 0 |

This is 5.1% higher redraw throughput and 7.4% less app CPU per redraw. All 48 mixed-interaction screenshots matched exactly, including coverage. Both sustained runs completed 960 GPU jobs, with no GPU readback, CPU presentation sink, faults or paging activity. Process snapshots identify the existing power/LED/display shell services and charger IRQ as background CPU consumers; they do not establish a unique cause for the earlier short-run wall-time difference. Parent child-time fields must not be summed as independent execution time. Hardware work and RFBI presentation still remain; these are not 30 FPS desktop results or Room/background benchmarks.

The selected native library is pinned in the release manifest alongside its module/Mesa/window library. The normal owner selects that module and page-group policy on its next clean launch. It preserves the old module path when using an older release. The previous owner and source files are backed up under `/usr/local/lib/n810-pocket/backup-20261109-ab93286`. Promotion does not launch/restart Pocket, radios or the kernel. Evidence and all retained runs: project `outputs/damage-bounds-20261109/summary.json`, `reports.json` and `long-reports.json`.
