"""Perspective grab for the Rainier camera. Pitch increases looking down."""
from math import asin,atan,atan2,cos,hypot,remainder,sin,tau

HALF_FOV_TANGENT=.5543


def screen_ray(u,v,aspect,yaw,pitch):
    side=(2*u-1)*aspect*HALF_FOV_TANGENT
    up=(1-2*v)*HALF_FOV_TANGENT
    ahead=cos(pitch)+up*sin(pitch)
    return (side*cos(yaw)+ahead*sin(yaw),up*cos(pitch)-sin(pitch),
            ahead*cos(yaw)-side*sin(yaw))


class ViewGrab:
    def __init__(self,u,v,aspect,yaw,pitch):
        self.start=(u,v)
        self.cursor=None
        self.direction=screen_ray(u,v,aspect,yaw,pitch)

    def aim(self,aspect,yaw):
        dx,dy,dz=self.direction
        length=hypot(dx,dy,dz)
        if length<1e-6:return None
        u,v=self.cursor
        side=(2*u-1)*aspect*HALF_FOV_TANGENT
        up=(1-2*v)*HALF_FOV_TANGENT
        # Invert the rendered ray: match its elevation, then its compass bearing.
        elevation=dy/length*hypot(1.,side,up)/hypot(1.,up)
        pitch=max(-1.,min(1.,atan(up)-asin(max(-1.,min(1.,elevation)))))
        ahead=cos(pitch)+up*sin(pitch)
        heading=atan2(dx,dz)-atan2(side,ahead)
        return yaw+remainder(heading-yaw,tau),pitch
