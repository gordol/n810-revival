"""Approximate georeferencing for our local, equirectangular DEM coordinates."""
import json
import math
from data_paths import data_root
from xml.sax.saxutils import escape


def reference(camera):
    metadata=json.loads(data_root().joinpath('tahoma-3dep.json').read_text())
    radius=6371000;latitude=metadata['latitude_first']+metadata['latitude_step']*(metadata['nz']-1)/2
    def ll(x,z):return (metadata['latitude_first']+math.degrees(z/radius),metadata['longitude_first']+metadata['longitude_step']*(metadata['nx']-1)/2+math.degrees(x/(radius*math.cos(math.radians(latitude)))))
    lat,lon=ll(camera.origin.x,camera.origin.z)
    _,_,forward=camera.axes();target=ll(camera.origin.x+forward.x*24000,camera.origin.z+forward.z*24000)
    heading=math.degrees(camera.yaw)%360
    def satellite(a,b):return f'https://www.google.com/maps/@?api=1&map_action=map&center={a:.7f}%2C{b:.7f}&zoom=12&basemap=satellite'
    return {'latitude':lat,'longitude':lon,'altitude_m':camera.origin.y,'heading_deg':heading,'downward_pitch_deg':math.degrees(camera.elevation),'vertical_fov_deg':math.degrees(2*math.atan(camera.span_y/(2*camera.focal))) if camera.focal else None,'camera_satellite':satellite(lat,lon),'forward_area_satellite':satellite(*target),'note':'Approximate inverse of the renderer projection, not a surveyed or ellipsoid-corrected camera. Forward area is 24km along heading, not a traced terrain intersection.'}


def kml(cameras):
    places=[]
    for name,camera in cameras.items():
        r=reference(camera)
        places.append(f'<Placemark><name>{escape(name)}</name><description>{escape(r["note"])}</description><Camera><longitude>{r["longitude"]}</longitude><latitude>{r["latitude"]}</latitude><altitude>{r["altitude_m"]}</altitude><heading>{r["heading_deg"]}</heading><tilt>{90-r["downward_pitch_deg"]}</tilt><roll>0</roll><altitudeMode>absolute</altitudeMode></Camera><Point><coordinates>{r["longitude"]},{r["latitude"]},{r["altitude_m"]}</coordinates><altitudeMode>absolute</altitudeMode></Point></Placemark>')
    return '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Scenery reference cameras</name>'+''.join(places)+'</Document></kml>'
