# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native drawing inputs. Geometry and text remain separate until rasterization."""
from dataclasses import dataclass

@dataclass(eq=False,frozen=True)
class MapScene:
    width:int
    height:int
    terrain:object
    sample_width:int
    sample_height:int
    lines:tuple
    marks:object
    insets:tuple=()
    base:object=None
    overlay_marks:object=None
    overlay_lines:tuple=()
    forest_overlay:object=None
    forest_visible:bool=False
    drag_labels:object=None
    content_width:int=0
    surround:object=None
    smooth:bool=False
