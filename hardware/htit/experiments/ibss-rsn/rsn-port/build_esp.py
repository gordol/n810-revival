"""Build a namespaced RSN archive using the pinned WPA release and ESP toolchain."""
from upstream_adapter import add_driver_sequence_callback
from source_archive import archive as source_archive
import hashlib,pathlib,shutil,subprocess,tarfile
HERE=pathlib.Path(__file__).resolve().parent
REPO=HERE.parents[2]
DIGEST='08e23937e16d0155e55cab2b51f51fbe10d80a1aa91c4e15442645059b737ef6'
def build(framework,tool,output,debug=False):
    framework,tool,output=map(pathlib.Path,(framework,tool,output));output.mkdir(parents=True,exist_ok=True)
    archive=source_archive()
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=DIGEST:raise ValueError('Unknown upstream RSN archive')
    with tarfile.open(archive) as tar:tar.extractall(output,filter='data')
    root=output/'wpa_supplicant-2.12'
    for name in ('ibss_rsn.c','ibss_rsn.h'):shutil.copyfile(root/'wpa_supplicant'/name,output/name)
    add_driver_sequence_callback(output/'ibss_rsn.c')
    files=[output/'ibss_rsn.c',HERE/'rsn_port.c',HERE/'timers.c',HERE/'os_esp.c',HERE/'crypto_esp.c']
    files += [root/p for p in ('src/rsn_supp/wpa.c','src/rsn_supp/wpa_ie.c','src/rsn_supp/pmksa_cache.c',
        'src/ap/wpa_auth.c','src/ap/wpa_auth_ie.c','src/ap/pmksa_cache_auth.c','src/common/wpa_common.c',
        'src/common/ieee802_11_common.c','src/utils/common.c','src/utils/wpabuf.c','src/utils/bitfield.c',
        'src/utils/wpa_debug.c','src/crypto/sha1-prf.c','src/crypto/sha256-prf.c','src/crypto/sha1-tprf.c',
        'src/crypto/aes-wrap.c','src/crypto/aes-unwrap.c','src/crypto/aes-omac1.c')]
    sdk=framework/'tools/sdk/esp32'
    includes=[HERE,output,root/'src',root/'src/utils',sdk/'dio_qspi/include']
    includes += sorted(p for p in (sdk/'include').rglob('include') if p.is_dir())
    includes += [sdk/'include/newlib/platform_include',sdk/'include/freertos/include/esp_additions']
    includes += [sdk/'include/freertos/include/esp_additions/freertos',sdk/'include/freertos/include/freertos',sdk/'include/freertos/port/xtensa/include']
    flags=['-mlongcalls','-std=gnu99','-Os','-ffunction-sections','-fdata-sections','-fno-strict-aliasing',
        '-include',str(HERE/'platform_esp.h'),
        '-DCONFIG_IBSS_RSN','-DCONFIG_SHA256','-DCONFIG_NO_RANDOM_POOL','-DCONFIG_NO_RADIUS','-DCONFIG_NO_VLAN',
        '-DCONFIG_NO_TKIP','-DCONFIG_NO_STDOUT_DEBUG','-DCONFIG_NO_WPA_MSG','-DCONFIG_NO_CONFIG_WRITE',
        '-DMBEDTLS_CONFIG_FILE="mbedtls/esp_config.h"',*['-I'+str(p) for p in includes]]
    prefix=tool/'bin/xtensa-esp32-elf-';objects=[]
    if debug:
        flags.remove('-DCONFIG_NO_STDOUT_DEBUG');flags.remove('-DCONFIG_NO_WPA_MSG')
        files.remove(root/'src/utils/wpa_debug.c');files.append(HERE/'log_esp.c')
    for i,source in enumerate(files):
        obj=output/(str(i)+'-'+source.stem+'.o');objects.append(obj)
        result=subprocess.run([str(prefix)+'gcc',*flags,'-c',str(source),'-o',str(obj)],capture_output=True,text=True)
        if result.returncode:raise SystemExit(source.name+':\n'+result.stderr)
    defined=set()
    for obj in objects:
        for line in subprocess.check_output([str(prefix)+'nm','-g','--defined-only',str(obj)],text=True).splitlines():
            if line.split():defined.add(line.split()[-1])
    names={name:'pocket_wpa_'+name for name in defined if not name.startswith('pocket_')}
    mapping=output/'rename-symbols.txt';mapping.write_text(''.join(a+' '+b+'\n' for a,b in sorted(names.items())))
    for obj in objects:subprocess.run([str(prefix)+'objcopy','--redefine-syms='+str(mapping),str(obj)],check=True)
    target=output/'libpocket_rsn.a';target.unlink(missing_ok=True)
    subprocess.run([str(prefix)+'ar','rcs',str(target),*map(str,objects)],check=True)
    return target
if __name__=='__main__':
    import sys
    print(build(*sys.argv[1:]))
