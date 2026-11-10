"""比較用の国土地理院都市圏活断層図に位置を付与する。RGBから断層を推定しない。"""
import io,json,hashlib
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image
from prepare import ROOT,RAW,OUT,INV,tile_xy,fetch

def build():
 meta=json.loads((OUT/'metadata.json').read_text());xmin,xmax,ymin,ymax=meta['extent_xy'];nx,ny=2400,3200
 x,y=np.meshgrid(np.linspace(xmin,xmax,nx),np.linspace(ymax,ymin,ny));lon,lat=INV.transform(x,y);tx,ty=tile_xy(lon,lat,13)
 tiles=sorted(set(zip(np.floor(tx).astype(int).ravel(),np.floor(ty).astype(int).ravel())))
 def tile(pair):
  a,b=pair;url=f'https://cyberjapandata.gsi.go.jp/xyz/afm/13/{a}/{b}.png';data=fetch(url,RAW/'afm'/f'13-{a}-{b}.png',allow_missing=True)
  return pair,None if data is None else np.asarray(Image.open(io.BytesIO(data)).convert('RGBA'))
 result=np.zeros((ny,nx,4),np.uint8);present=[]
 for (a,b),image in ThreadPoolExecutor(max_workers=4).map(tile,tiles):
  if image is None:continue
  mask=(np.floor(tx)==a)&(np.floor(ty)==b);result[mask]=image[((ty[mask]-b)*256).astype(int),((tx[mask]-a)*256).astype(int)];present.append([int(a),int(b)])
 if not present:raise ValueError('No GSI active-fault map tiles were available')
 target=ROOT/'web/data';Image.fromarray(result).save(target/'gsi-active-fault-map.png')
 data={'id':'gsi-afm','name':'国土地理院 都市圏活断層図','template':'https://cyberjapandata.gsi.go.jp/xyz/afm/{z}/{x}/{y}.png','extent_xy':meta['extent_xy'],'image':'gsi-active-fault-map.png','zoom':13,'available_tiles':present,'missing_tiles':[[int(t[0]),int(t[1])] for t in tiles if list(t) not in present],'role':'georeferenced reference map; red labels/arrows are not automatically interpreted as fault lines','guidebook':'https://www.gsi.go.jp/common/000096723.pdf','attribution':'国土地理院 活断層図（都市圏活断層図）','sha256':hashlib.sha256((target/'gsi-active-fault-map.png').read_bytes()).hexdigest()}
 (ROOT/'data/structure/gsi-active-fault-map.json').write_text(json.dumps(data,ensure_ascii=False,indent=2));(target/'gsi-active-fault-map.json').write_text(json.dumps(data,ensure_ascii=False));print('GSI urban active-fault map',len(present),'tiles; transparent pixels',float(np.mean(result[...,3]==0)))
 return data
if __name__=='__main__':build()
