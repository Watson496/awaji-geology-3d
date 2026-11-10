"""Separate the land lithology domain from deeper acoustic-basin calculations."""
import numpy as np
from scipy.ndimage import map_coordinates

# These are COMPUTATIONAL limits, not a claim that the whole island is observed.
# Both 50k map sheets' printed section axes span -500..+500 m elevation.
ZMIN=-500.;ZMAX=700.;NZ=24

def native_prior(cache,rock,z,s):
 from gempy_fields import context,ZMIN as old_min,ZMAX as old_max,NZ as old_nz
 _,_,_,_,old_count,old_rock,_,signature=context()
 if str(cache['signature'])!=signature:raise ValueError('GemPy prior source signature does not match')
 index=cache['indices'];sel=index<old_count
 scores=np.full(old_count,-1,np.float32);scores[index[sel]]=np.clip(cache['score'][sel],-1,1)
 dense=np.full(old_rock.shape,-1,np.float32);dense[old_rock]=scores
 i,j,k=np.nonzero(rock);q=(z[k]-old_min)/((old_max-old_min)/old_nz)-.5
 return map_coordinates(dense,np.array([i,j,q]),order=1,mode='nearest',prefilter=False)

def section_support(meta,s,sections):
 """Mark proximity to ACTUAL picked interpretations, not the entire image frame.

A 500m plan-view corridor and 100m vertical reading margin are explicit influence
windows, not a calibrated confidence region. Elsewhere predictions are extrapolation.
"""
 from shapely.geometry import LineString
 import shapely
 xx,yy=np.meshgrid(s['xs'],s['ys'],indexing='ij');points=shapely.points(xx,yy)
 z=meta['zmin']+(np.arange(meta['nz'])+.5)*(meta['zmax']-meta['zmin'])/meta['nz'];support=np.zeros((*xx.shape,len(z)),np.uint8)
 for section in sections:
  picks=section['picks']
  if not section['used_for_model'] or not picks:continue
  low=min(p['xyz'][2]-p['sigma_m'] for p in picks);high=max(p['xyz'][2]+p['sigma_m'] for p in picks)
  near=shapely.distance(points,LineString(section['route_xy']))<=500
  support[near[...,None]&(z[None,None,:]>=low)&(z[None,None,:]<=high)]=2
 return support
