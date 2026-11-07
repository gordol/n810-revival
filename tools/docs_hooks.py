"""Include repository manuals in the site while keeping their source beside code."""
from pathlib import Path
import json
import posixpath
import re
from mkdocs.structure.files import File

ROOT = Path(__file__).resolve().parents[1]
# Select reader-facing manuals explicitly. Repository maintenance documents
# stay outside the site, including its generated pages and search index.
MANUALS = {
    "CONTRIBUTOR-AGREEMENT.md": "contributor-agreement.md",
    "CONTRIBUTORS.md": "contributors.md",
    "LICENSE.md": "license.md",
    "licenses/ORIGINAL-CODE-GPL.md": "original-code-gpl.md",
    "LICENSING.md": "licensing.md",
    **{f"pocket/docs/{name}.md": f"pocket/{name}.md" for name in (
        "README", "apps-and-services", "connections", "external-node",
        "install", "local-owner-recovery", "messaging", "navigation",
        "nokia", "receive-history", "releases-0.1.0", "rnode-bluetooth",
        "service-publication", "service-transports", "touch-acquisition",
        "versioning",
    )},
    "pocket/shell/native/reticulum/README.md": "pocket/native-reticulum.md",
    "pocket/shell/vendor/README.md": "reference/bundled-source.md",
    "platform/README.md": "reference/platform-files.md",
    "platform/kernel/README.md": "reference/kernel-build-inputs.md",
    "hardware/htit/README.md": "reference/htit-inputs.md",
    "graphics/mbx/README.md": "reference/graphics-inputs.md",
    "graphics/mbx/checkpoints/30fps-20261104/README.md": "reference/gpu-30fps-inputs.md",
}
GPU_CHECKPOINT = ROOT / "graphics/mbx/checkpoints/30fps-20261104"
GPU_SOURCE_VIEWS = {
    "command-reuse.c.txt": "experiments/vgp-service-20261104/common/mbx_vgp_wire.c",
    "fifo-stream.c.txt": "experiments/vgp-service-20261104/common/mbx_vgp_stream.c",
    "render-service.h.txt": "experiments/vgp-service-20261104/kernel/mbx_render_service.h",
    "sampler-patch.py.txt": "mesa/prepare_sampler_scan.py",
    "test-command-reuse.c.txt": "experiments/vgp-service-20261104/test_wire_replay.c",
    "test-fifo.c.txt": "experiments/vgp-service-20261104/test_stream_batch.c",
    "test-samplers.py.txt": "tests/test_sampler_scan.py",
    "SOURCE.json": "SOURCE.json",
    "VERIFICATION.json": "VERIFICATION.json",
}
LINK = re.compile(r"(?P<lead>!?\[[^\]\n]*\]\()(?P<url>[^)\s]+)(?P<tail>\))")

def on_files(files, config):
    for source, destination in MANUALS.items():
        def rewrite(match):
            url = match['url']
            if url.startswith(("https://", "http://", "#", "mailto:")):
                return match[0]
            path, sep, anchor = url.partition('#')
            target = posixpath.normpath(posixpath.join(posixpath.dirname(source), path))
            if target in MANUALS:
                site_target = MANUALS[target]
            elif target.startswith('docs/'):
                site_target = target[5:]
            else:
                return match['lead'] + 'https://github.com/gordol/n810-revival/blob/main/' + target + sep + anchor + match['tail']
            relative = posixpath.relpath(site_target, posixpath.dirname(destination))
            return match['lead'] + relative + sep + anchor + match['tail']
        content = LINK.sub(rewrite, (ROOT / source).read_text())
        files.append(File.generated(config, destination, content=content))
    entries=json.loads((ROOT / "tools/journal-sources.json").read_text())["entries"]
    sources={item["path"] for row in entries for group in ("implementation", "tests", "inputs") for item in row[group]}
    for source in sorted(sources):
        files.append(File.generated(config, "assets/source/journal/" + source + ".txt", content=(ROOT / source).read_text()))
    for destination, source in GPU_SOURCE_VIEWS.items():
        files.append(File.generated(config, "assets/source/gpu-30fps/" + destination,
                                    content=(GPU_CHECKPOINT / source).read_text()))
    files.append(File.generated(config, "assets/patches/console-rgb.patch",
                                content=(ROOT / "platform/patches/console-rgb.patch").read_text()))
    for name in ("n810-5.15.224.patch", "n810.config", "source.lock.json", "verification.json"):
        files.append(File.generated(config, "assets/kernel/" + name,
                                    content=(ROOT / "platform/kernel" / name).read_text()))
    return files

def on_serve(server, config, builder):
    for source in MANUALS:
        server.watch(str(ROOT / source), builder)
    for source in GPU_SOURCE_VIEWS.values():
        server.watch(str(GPU_CHECKPOINT / source), builder)
    server.watch(str(ROOT / "platform/patches/console-rgb.patch"), builder)
    for name in ("n810-5.15.224.patch", "n810.config", "source.lock.json", "verification.json"):
        server.watch(str(ROOT / "platform/kernel" / name), builder)
    return server
