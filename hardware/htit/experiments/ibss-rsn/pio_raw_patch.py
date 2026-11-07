"""Applied ONLY by the explicit WIP radio-probe environment."""
Import('env')
import importlib.util
import json
from pathlib import Path

project=Path(env.subst('$PROJECT_DIR'))
project=(project/env.GetProjectOption('custom_rsn_sources','.')).resolve()
spec=importlib.util.spec_from_file_location('ibss_sdk_patch',project/'patch_sdk.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
framework=Path(env.PioPlatform().get_package_dir('framework-arduinoespressif32'))
tool=Path(env.PioPlatform().get_package_dir('toolchain-xtensa-esp32'))
folder=Path(env.subst('$BUILD_DIR'))/'protected-data-sdk'
archive=folder/'libnet80211.a'
digest=module.patch_archive(framework/'tools/sdk/esp32/lib/libnet80211.a',archive,
                          tool/'bin/xtensa-esp32-elf-ar',
                          env.GetProjectOption('custom_rsn_auth','no')=='yes')
rx_enabled=env.GetProjectOption('custom_rx_descriptor_gate','no')=='yes'
observer_enabled=env.GetProjectOption('custom_rx_observer','no')=='yes'
if rx_enabled and observer_enabled:raise ValueError('Choose one receive diagnostic')
rx_folder=folder/'rx-diagnostic-sdk'
# Remove the old generated location, which would shadow the stock SDK via the
# TX library search path even when this diagnostic is disabled.
(folder/'libpp.a').unlink(missing_ok=True)
rx_digest=module.RX_ARCHIVE_SHA
dependencies=[env.File(str(archive))]
if rx_enabled:
    rx_archive=rx_folder/'libpp.a'
    rx_digest=module.patch_rx_archive(framework/'tools/sdk/esp32/lib/libpp.a',rx_archive,
                                    tool/'bin/xtensa-esp32-elf-ar')
    env.Prepend(LIBPATH=[str(rx_folder)])
    dependencies.append(env.File(str(rx_archive)))
if observer_enabled:
    observer_folder=folder/'rx-observer-sdk';rx_archive=observer_folder/'libpp.a'
    rx_digest=module.observer_archive(framework/'tools/sdk/esp32/lib/libpp.a',rx_archive,
        tool/'bin/xtensa-esp32-elf-ar',tool/'bin/xtensa-esp32-elf-objcopy',
        env.GetProjectOption('custom_tx_selector','no')=='yes')
    env.Prepend(LIBPATH=[str(observer_folder)])
    dependencies.append(env.File(str(rx_archive)))
env.Prepend(LIBPATH=[str(folder)])
# LIBPATH alone is not a relink dependency. Pin the actual patched contents so
# changing a patch without changing C++ cannot silently reuse an older ELF/bin.
env.Depends('$BUILD_DIR/${PROGNAME}.elf',env.Value(digest+rx_digest))
env.Depends('$BUILD_DIR/${PROGNAME}.elf',dependencies)
env.Append(LINKFLAGS=['-Wl,-Map,'+str(folder/'radio.map')])
(folder/'patch-receipt.json').write_text(json.dumps(dict(original_sha256=module.ARCHIVE_SHA,
    patched_sha256=digest,rx_diagnostic_enabled=rx_enabled,
    rx_observer_enabled=observer_enabled,
    rsn_auth_enabled=env.GetProjectOption('custom_rsn_auth','no')=='yes',
    tx_selector_enabled=env.GetProjectOption('custom_tx_selector','no')=='yes',
    rx_original_sha256=module.RX_ARCHIVE_SHA,rx_patched_sha256=rx_digest,
    scope='build-local protected TX; optional authentication subtype, DMA observer and TX selector; shared SDK untouched'),indent=2)+'\n')
