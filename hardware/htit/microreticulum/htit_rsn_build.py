"""Explicit secure-IBSS target only; reuse the exact radio-tested wire driver."""
Import('env')
from pathlib import Path
project=Path(env.subst('$PROJECT_DIR'))
source=(project/'../experiments/ibss-rsn').resolve()
env.Append(CPPPATH=[str(source)])
library=env.BuildLibrary(str(Path(env.subst('$BUILD_DIR'))/'rsn-wire'),str(source),
    src_filter='+<ccmp.cpp> +<crypto_mbedtls.cpp> +<rsn_radio.cpp> +<rx_observer.cpp> +<tx_selector.cpp> +<runtime_diagnostics.cpp>')
env.Prepend(LIBS=[library])
env.Depends('$BUILD_DIR/${PROGNAME}.elf',library)

env.Append(LINKFLAGS=["-Wl,--wrap=osi_alarm_new","-Wl,--wrap=osi_alarm_free","-Wl,--wrap=esp_timer_create"])
