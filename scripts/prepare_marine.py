"""Digitized acoustic-basement contours, not fabricated seamless lithology labels."""
import json,hashlib
import numpy as np
from pyproj import Transformer
from prepare import ROOT,RAW,fetch

URL='https://www1.kaiho.mlit.go.jp/faults/osakabay1.pdf'

def build():
 raw=fetch(URL,RAW/'osaka-basement-2000.pdf')
 previous=ROOT/'data/structure/marine.json'
 if previous.exists() and json.loads(previous.read_text())['source_sha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('Marine source changed; calibration must be reviewed')
 # Original PDF page 17 embedded image (2480 x 3507), Fig.22.
 # Map frame/ticks: lon 134°50' at x489, 135°30' at x2192;
 # lat 34°40' at y1881, 34°20' at y2909. Tokyo datum is an
 # explicit assumption for this pre-2002 map; horizontal sigma includes it.
 transform=Transformer.from_crs(4301,32653,always_xy=True)
 picks=[]
 for i,(x,y,depth) in enumerate([(772,2792,1500),(760,2710,1500),(760,2620,1500),(849,2800,1000),(844,2730,1000)]):
  lon=134+50/60+(x-489)/(2192-489)*(40/60);lat=34+40/60-(y-1881)/(2909-1881)*(20/60)
  east,north=transform.transform(lon,lat)
  picks.append({'id':f'osaka2000-fig22-{i+1}','pixel':[x,y],'xyz':[east,north,-depth],'horizontal_sigma_m':500,'depth_sigma_m':300,
   'kind':'interpreted_acoustic_basement_depth','native_symbol':None,'contour_depth_m':depth})
 out={'source_url':URL,'source_sha256':hashlib.sha256(raw).hexdigest(),'title':'岩淵ほか（2000）反射法音波探査に基づく大阪湾の基盤と活構造','figure':'Fig.22, PDF page 17','image_pixels':[2480,3507],
  'calibration':{'lon_pixels':[489,2192],'lon_degrees':[134+50/60,135.5],'lat_pixels':[1881,2909],'lat_degrees':[34+40/60,34+20/60],'source_datum':'Tokyo datum assumed; not confirmed in figure, included in 500m horizontal uncertainty'},
  'picks':picks,'correlation':'Acoustic basin/basement boundary is a structural constraint, not a unique granite/facies code. In this model it constrains the pre-Cenozoic assemblage (pre-Izumi + Izumi) versus younger cover; that correlation is explicitly a hypothesis.',
  'limitations':['Five correlated manual picks on two contours, not a complete digitization of the bay.', 'Depth conversion uncertainty and assumed source datum prevent sub-grid precision.', 'No seabed lithology is assigned from acoustic velocity alone.']}
 p=ROOT/'data/structure/marine.json';p.write_text(json.dumps(out,ensure_ascii=False,indent=2));(ROOT/'web/data/marine.json').write_text(p.read_text());return out
if __name__=='__main__':build()
