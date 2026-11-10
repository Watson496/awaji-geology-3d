"""陸域の岩相推定領域と、深部の音響堆積盆の計算領域を分ける。"""
import numpy as np
from scipy.ndimage import map_coordinates

# 計算範囲であり、島全体が観測済みであることを示すものではない。
# 5万分の1地質図の両図幅で、印刷断面の標高軸は-500〜+500mである。
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
 """画像全体ではなく、実際に読み取った解釈点への近さを記録する。

平面上500m、鉛直方向100mの読み取り余裕を、影響範囲の仮定として明示する。
校正済みの信頼領域ではなく、範囲外の予測は外挿である。
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
