"""Build the isolated namespaced upstream RSN core with the pinned SDK."""
Import('env')
import importlib.util
import sys
from pathlib import Path
project=Path(env.subst('$PROJECT_DIR'))
project=(project/env.GetProjectOption('custom_rsn_sources','.')).resolve()
sys.path.insert(0,str(project/'rsn-port'))
spec=importlib.util.spec_from_file_location('rsn_esp_build',project/'rsn-port/build_esp.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
archive=module.build(Path(env.PioPlatform().get_package_dir('framework-arduinoespressif32')),
    Path(env.PioPlatform().get_package_dir('toolchain-xtensa-esp32')),
    Path(env.subst('$BUILD_DIR'))/'rsn-core',env.GetProjectOption('custom_rsn_debug','no')=='yes')
env.Append(LIBS=[env.File(str(archive))])
env.Depends('$BUILD_DIR/${PROGNAME}.elf',env.File(str(archive)))
