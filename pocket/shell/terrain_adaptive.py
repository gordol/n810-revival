"""Conservative adaptive subdivision; bounds must include every underlying cell.

An average/coarse DEM is deliberately not accepted as a terrain upper bound.
"""
import math


def fractions(distance, start_height, end_height, frequency_mhz, k, location,
              upper_bound, *, max_depth=8, overview=32):
    from path_profile import EARTH_M, LIGHT_M_S
    selected={i/overview for i in range(overview+1)}
    stats=dict(cleared_intervals=0,refined_intervals=0,unresolved_intervals=0,bound_queries=0)
    wavelength=LIGHT_M_S/(frequency_mhz*1e6)
    def visit(a,b,depth):
        stats['bound_queries']+=1
        high=upper_bound(location(a),location(b))
        # The ray is linear. Curvature and Fresnel radius attain their maxima
        # at the interval point closest to the midpoint of the complete path.
        f=max(a,min(b,.5));product=distance*distance*f*(1-f)
        floor=min(start_height+(end_height-start_height)*a,
                  start_height+(end_height-start_height)*b)
        allowance=product/(2*k*EARTH_M)+.6*math.sqrt(wavelength*product/distance)
        if high is not None and high+allowance+1 < floor:
            stats['cleared_intervals']+=1
            return
        mid=(a+b)/2;selected.add(mid)
        if depth>=max_depth:
            stats['unresolved_intervals']+=1
            return
        stats['refined_intervals']+=1
        visit(a,mid,depth+1);visit(mid,b,depth+1)
    visit(0,1,0)
    return sorted(selected),stats
