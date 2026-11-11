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

@dataclass(frozen=True)
class MapComposite:
    """Clipped map textures positioned over one map-window rectangle."""
    layers:tuple
    clip_width:int=0
    clip_height:int=0

@dataclass(eq=False,frozen=True)
class RasterScene:
    source:MapScene
    pixels:object
    @property
    def marks(self):return self.source.marks

@dataclass(frozen=True)
class RoomScene:
    """Room geometry/camera commands; no CPU pixel buffer or device handle."""
    age:float
    x:float
    z:float
    yaw:float
    pitch:float
    eye_height:float
    width:int
    height:int
