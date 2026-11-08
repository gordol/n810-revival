# syntax=docker/dockerfile:1
FROM python:3.13-bookworm@sha256:cc55e4ded9c95f6ce2133b3d096db43f214d280c2a8af65d83e246c8fa7d168c AS toolchain
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git flex bison bc libssl-dev libelf-dev kmod curl ca-certificates xz-utils patch gcc-arm-linux-gnueabihf binutils-arm-linux-gnueabihf gcc-arm-linux-gnueabi g++-arm-linux-gnueabi meson ninja-build pkg-config python3-mako python3-packaging python3-yaml dpkg-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /src

FROM toolchain AS kernel
COPY platform/kernel/ platform/kernel/
RUN python3 platform/kernel/build.py --work /build/kernel --jobs 4

FROM kernel AS graphics
COPY graphics/mbx/ graphics/mbx/
RUN python3 graphics/mbx/build.py module --work /build/module --kernel-source /build/kernel/linux-5.15.224 --kernel-build /build/kernel/build
RUN python3 -m venv /opt/mesa-tools && /opt/mesa-tools/bin/pip install meson==1.5.2 Mako==1.3.5 packaging==24.1 PyYAML==6.0.2 setuptools==75.1.0
RUN --mount=type=cache,id=n810-mesa-inputs,target=/cache/mesa-inputs,sharing=locked PATH=/opt/mesa-tools/bin:$PATH python3 graphics/mbx/build.py mesa --work /build/mesa --jobs 4 --osmesa --download-cache /cache/mesa-inputs || { cat /build/mesa/logs/*.log; exit 1; }

FROM toolchain AS htit
COPY hardware/htit/requirements-build.txt /tmp/requirements-build.txt
RUN python3 -m venv /opt/htit && /opt/htit/bin/pip install -r /tmp/requirements-build.txt
COPY hardware/htit/ hardware/htit/
RUN python3 hardware/htit/build.py executor --pio /opt/htit/bin/pio --work /build/executor
RUN python3 hardware/htit/build.py hub --pio /opt/htit/bin/pio --work /build/hub

FROM toolchain AS source-check
COPY requirements-docs.lock /tmp/requirements-docs.lock
RUN python3 -m venv /opt/docs && /opt/docs/bin/pip install -r /tmp/requirements-docs.lock
COPY . .
RUN git init -q && git add . && python3 tools/check-journal.py --tracked && python3 tools/check-publication.py
RUN make pocket-smoke && make -C pocket native
RUN python3 -m unittest discover -s tools -p test_package_source.py -v
RUN /opt/docs/bin/python -m mkdocs build --strict

FROM toolchain AS map-deps
COPY requirements-maps.txt /tmp/requirements-maps.txt
RUN python3 -m venv /opt/maps && /opt/maps/bin/pip install -r /tmp/requirements-maps.txt

FROM source-check AS map-check
COPY --from=map-deps /opt/maps /opt/maps
RUN --network=none /opt/maps/bin/python -m unittest discover -s pocket/tests -p 'test_*pipeline.py' -v

# Exercise the complete source suite as a normal user, including Linux D-Bus
# bindings and the host wire protocol. Test execution is offline.
FROM map-check AS full-source-check
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-dbus python3-gi && rm -rf /var/lib/apt/lists/*
RUN /usr/bin/python3 -m venv --system-site-packages /opt/source-tests && /opt/source-tests/bin/pip install -r requirements-maps.txt -r hardware/htit/rfcomm-ble-hub/host/requirements.txt -r pocket/requirements-meshcore.txt -r hardware/htit/experiments/ibss-rsn/requirements-test.txt
RUN useradd --create-home source-tester && install -d -o source-tester -g source-tester /verification/source-tests
RUN --network=none runuser -u source-tester -- /opt/source-tests/bin/python tools/check-source.py --work /verification/source-tests/run --jobs 2
RUN --network=none runuser -u source-tester -- env POCKET_SOURCE=/src/pocket /opt/source-tests/bin/python -m unittest discover -s hardware/htit/rfcomm-ble-hub/tests -q
RUN --network=none runuser -u source-tester -- /opt/source-tests/bin/python -m unittest discover -s hardware/htit/experiments/ibss-rsn -p 'test_*.py' -q
RUN --network=none runuser -u source-tester -- env HTIT_RSN_WORK=/tmp/htit-rsn-ci /opt/source-tests/bin/python -m unittest discover -s hardware/htit/experiments/ibss-rsn/rsn-port -p test_rsn.py -q

# A fresh source-only build exercises the portable GUI with an explicit Mesa
# software context, plus ARM cross-builds. It does not establish hardware speed.
FROM full-source-check AS gui-check
RUN apt-get update && apt-get install -y --no-install-recommends libsdl2-dev libgl1-mesa-dev libgl1-mesa-dri xvfb xauth && rm -rf /var/lib/apt/lists/*
COPY --from=graphics /build/mesa/package /opt/arm-mesa
RUN make -C pocket graphics-native && python3 pocket/graphics/build_nokia.py --mesa-include /opt/arm-mesa/include --mesa-library /opt/arm-mesa/libOSMesa.so.8
RUN python3 -m unittest discover -s pocket/tests -p 'test_graphical_frontend.py' -v && python3 -m unittest discover -s pocket/tests -p 'test_*pixel*.py' -v && python3 -m unittest discover -s pocket/tests -p test_surface_native_backend.py -v
RUN python3 -m unittest discover -s pocket/tests -p test_nokia_graphics.py -v && python3 -m unittest discover -s pocket/tests -p test_smooth_font.py -v
RUN --network=none python3 pocket/shell/apps/doom-app/build.py --engine-only
RUN xvfb-run -a python3 pocket/graphics/check.py --allow-software

# Build evidence stays inside the image. No binary release is exported.
FROM gui-check AS release-check
COPY --from=graphics /build/module/package /verification/module
COPY --from=graphics /build/mesa/package /verification/mesa
COPY --from=htit /build/executor/BUILD.json /verification/executor.json
COPY --from=htit /build/hub/BUILD.json /verification/hub.json

FROM release-check AS package
RUN git init -q && git add . && python3 tools/package-source.py --output /out/source.tar.gz && python3 tools/package-source.py --docs-only --output /out/documentation.tar.gz
RUN python3 -c "import tarfile,json,hashlib; archives=['source','documentation']; [(lambda t,m: [(_ for _ in ()).throw(ValueError(n)) if hashlib.sha256(t.extractfile('n810-revival/'+n).read()).hexdigest()!=v['sha256'] or t.getmember('n810-revival/'+n).size!=v['size'] or oct(t.getmember('n810-revival/'+n).mode)!=v['mode'] else None for n,v in m['files'].items()])(t,json.load(t.extractfile('n810-revival/'+('SOURCE' if a=='source' else 'DOCS')+'-SNAPSHOT.json'))) for a in archives for t in [tarfile.open('/out/'+a+'.tar.gz')]]"
RUN mkdir /unpacked && tar xzf /out/source.tar.gz -C /unpacked && tar xzf /out/documentation.tar.gz -C /unpacked && cd /unpacked/n810-revival && make pocket-smoke && XDG_CACHE_HOME=/tmp/archive-native-cache make -C pocket native && /opt/docs/bin/python -m mkdocs build --strict
FROM scratch AS archives
COPY --from=package /out/ /
