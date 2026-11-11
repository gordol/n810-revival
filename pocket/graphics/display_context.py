# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Select rendering from the owned display's capabilities."""
def create(platform):
    display=platform.display
    required=('pocket_scene_open','pocket_scene_map','pocket_scene_present')
    if display is None or all(hasattr(display.lib,name) for name in required):
        import os
        if os.environ.get("POCKET_NATIVE_PIXELS")=="1":
            from pixel_scene import Context
        else:
            from gpu_scene import Context
        context=Context(platform);context.report_key='gpu_scene'
        context.renderer_description='Native GPU scene renderer: '+context.backend
        return context
    from framebuffer_scene import Context
    return Context(platform)
