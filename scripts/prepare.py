"""Fetch official data, preserve originals, and prepare auditable GemPy constraints.

Coordinates: UTM zone 53N (metres); arrays are [east, north], north increasing.
No network fallbacks: an unsuccessful request stops the run.
"""
from pathlib import Path
import io
import json
import math
import hashlib
import zipfile
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import numpy as np
import requests
import shapefile
import shapely
from PIL import Image
from pyproj import Transformer
from scipy import ndimage
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw'
OUT = ROOT / 'data/prepared'
BOX = [134.62, 34.17, 135.05, 34.64]  # west,south,east,north
NX, NY = 200, 288
FWD = Transformer.from_crs(4326, 32653, always_xy=True)
INV = Transformer.from_crs(32653, 4326, always_xy=True)
SHEETS = {'sumoto': '13011_1992', 'akashi': '12083_1990'}


def fetch(url, path, allow_missing=False):
    path = Path(path)
    if path.exists():
        return path.read_bytes()
    response = subprocess.run(['curl', '--silent', '--show-error', '--location', '--max-time', '60',
                               '--write-out', '\n%{http_code}', url], capture_output=True, check=True)
    data, status = response.stdout.rsplit(b'\n', 1)
    if status == b'404' and allow_missing:
        return None  # no DEM tile, e.g. ocean; never substitute invented elevation
    if status != b'200':
        raise RuntimeError(f'HTTP {status.decode()} from {url}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def tile_xy(lon, lat, zoom):
    n = 2 ** zoom
    return (lon + 180) / 360 * n, (1 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2 * n


def tile_sample(lon, lat, zoom, service):
    tx, ty = tile_xy(lon, lat, zoom)
    tiles = sorted(set(zip(np.floor(tx).astype(int).ravel(), np.floor(ty).astype(int).ravel())))

    def load(tile):
        x, y = tile
        url = (f'https://cyberjapandata.gsi.go.jp/xyz/dem_png/{zoom}/{x}/{y}.png'
               if service == 'dem' else
               f'https://gbank.gsj.jp/seamless/v2/api/1.3.1/tiles/{zoom}/{y}/{x}.png?layer=g')
        data = fetch(url, RAW / 'tiles' / f'{service}-{zoom}-{x}-{y}.png', allow_missing=(service == 'dem'))
        if data is None:
            return tile, np.zeros((256, 256, 4), np.uint8)
        rgba = np.asarray(Image.open(io.BytesIO(data)).convert('RGBA'))
        return tile, rgba

    images = dict(ThreadPoolExecutor(max_workers=4).map(load, tiles))
    result = np.empty(lon.shape + (4,), np.uint8)
    for (x, y), image in images.items():
        mask = (np.floor(tx) == x) & (np.floor(ty) == y)
        result[mask] = image[np.minimum(255, ((ty[mask] - y) * 256).astype(int)),
                             np.minimum(255, ((tx[mask] - x) * 256).astype(int))]
    return result


def decode_dem(rgba):
    rgb = rgba[..., :3].astype(np.int32)
    packed = rgb[..., 0] * 65536 + rgb[..., 1] * 256 + rgb[..., 2]
    z = np.where(packed < 8388608, packed, packed - 16777216) * .01
    z[(packed == 8388608) | (rgba[..., 3] == 0)] = np.nan
    return z


def read_layer(sheet, layer):
    z = zipfile.ZipFile(RAW / f'{sheet}-vector.zip')
    n = next(n for n in z.namelist() if n.endswith(f'/{layer}.shp'))
    b = n[:-4]
    return shapefile.Reader(shp=io.BytesIO(z.read(n)), shx=io.BytesIO(z.read(b + '.shx')),
                            dbf=io.BytesIO(z.read(b + '.dbf')), encoding='cp932')


def normal_from_strike(strike, dip):
    """GSJ right hand rule: dip azimuth=strike+90, upward stratigraphic pole."""
    az, di = np.radians([strike + 90, dip])
    return np.array([np.sin(di) * np.sin(az), np.sin(di) * np.cos(az), np.cos(di)])


def spaced_indices(xy, spacing, limit):
    """Deterministic spatial thinning, never use global random state."""
    selected = []
    for i, point in enumerate(xy):
        if not selected or np.min(np.linalg.norm(xy[selected] - point, axis=1)) >= spacing:
            selected.append(i)
    if len(selected) > limit:
        selected = [selected[i] for i in np.linspace(0, len(selected) - 1, limit).astype(int)]
    return np.asarray(selected, dtype=int)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    legend=json.loads(fetch('https://gbank.gsj.jp/seamless/v2/api/1.3.1/legend.json?box=34.15,134.6,34.65,135.1',RAW/'seamless-legend.json'))
    for sheet,code in SHEETS.items():fetch(f'https://www.gsj.jp/data/50KGM/VCT/GSJ_MAP_G050_{code}_V01.zip',RAW/f'{sheet}-vector.zip')
    corners=np.array([FWD.transform(lo,la) for lo in BOX[::2] for la in BOX[1::2]])
    xmin,ymin=corners.min(axis=0);xmax,ymax=corners.max(axis=0);dx=(xmax-xmin)/NX;dy=(ymax-ymin)/NY
    xs=xmin+(np.arange(NX)+.5)*dx;ys=ymin+(np.arange(NY)+.5)*dy
    xx,yy=np.meshgrid(xs,ys,indexing='ij');lon,lat=INV.transform(xx,yy)
    rgba=tile_sample(lon,lat,12,'geology');dem=decode_dem(tile_sample(lon,lat,12,'dem'))
    palette=np.array([[d['r'],d['g'],d['b']] for d in legend]);tree=cKDTree(palette)
    distance,li=tree.query(rgba[...,:3].reshape(-1,3));li=li.reshape(xx.shape)
    valid=(distance.reshape(xx.shape)<1)&(rgba[...,3]>0)&np.isfinite(dem)
    label,_=ndimage.label(valid);seed=FWD.transform(134.85,34.4);component=label[np.argmin(abs(xs-seed[0])),np.argmin(abs(ys-seed[1]))]
    if component==0:raise ValueError('淡路島の陸域を識別できません')
    island=label==component
    # 約100mの地表メッシュに含まれる原凡例も検出し、小さな露出を落とさない。
    hx,hy=400,576
    hxs=np.linspace(xmin+dx/2,xmax-dx/2,hx);hys=np.linspace(ymin+dy/2,ymax-dy/2,hy)
    hxx,hyy=np.meshgrid(hxs,hys,indexing='ij');hlo,hla=INV.transform(hxx,hyy)
    hr=tile_sample(hlo,hla,12,'geology');hz=decode_dem(tile_sample(hlo,hla,12,'dem'));hdistance,hindices=tree.query(hr[...,:3].reshape(-1,3))
    hvalid=(hdistance.reshape(hxx.shape)<1)&(hr[...,3]>0)&np.isfinite(hz)
    hl,_=ndimage.label(hvalid);hc=hl[np.argmin(abs(hxs-seed[0])),np.argmin(abs(hys-seed[1]))]
    if hc==0:raise ValueError('細格子の淡路島陸域を識別できません')
    hland=hl==hc
    cell=hland[:-1,:-1]&hland[1:,:-1]&hland[:-1,1:]&hland[1:,1:]
    ii,jj=np.nonzero(cell);a0=ii*hy+jj;b0=(ii+1)*hy+jj
    faces=np.vstack([np.c_[a0,a0+1,b0+1],np.c_[a0,b0+1,b0]])
    used=np.unique(faces);lookup=np.zeros(hx*hy,np.uint32);lookup[used]=np.arange(len(used));faces=lookup[faces]
    high_edges=np.unique(np.sort(np.vstack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)
    hpos=np.c_[hxx.ravel()[used],hyy.ravel()[used],hz.ravel()[used]];hi=hindices[used]
    active=sorted(set(hi)|set(li[island]),key=lambda i:legend[i]['symbol'])
    remap={source:i+1 for i,source in enumerate(active)}
    units=[]
    for source in active:
        d=legend[source];units.append({'id':remap[source],'key':d['symbol'],'source_symbol':d['symbol'],'name':d['title'],'short_name':d['lithology_ja'],'color':'#'+d['value'],'kind':'geological','source_legend':d})
    unknown=len(units)+1
    units.append({'id':unknown,'key':'unconstrained','source_symbol':None,'name':'未拘束（地質単元ではない）','short_name':'未拘束','color':'#a9afb6','kind':'unknown'})
    surface=np.zeros((NX,NY),np.uint8)
    for source,g in remap.items():surface[island&(li==source)]=g
    highunits=np.array([remap[i] for i in hi],np.uint8)
    # 正順の堆積層の傾斜だけを、位置にある原単元に対応づける。
    attitudes=[]
    htree=cKDTree(hpos[:,:2])
    for sheet in SHEETS:
        for sr in read_layer(sheet,'strdip').iterShapeRecords():
            d=sr.record.as_dict()
            if d.get('LEGEND01')!='地層の走向及び傾斜' or d.get('Attribute')!=1:continue
            lo,la=sr.shape.points[0];x,y=FWD.transform(lo,la);dist,idx=htree.query([x,y])
            if dist>250:continue
            g=int(highunits[idx]);unit=units[g-1]
            if unit['source_legend']['group_ja']!='堆積岩':continue
            strike,dip=float(d['Strike_Val']),float(d['Dip_Value'])
            if not(0<=strike<360 and 0<=dip<=90):continue
            n=normal_from_strike(strike,dip);xn,yn=FWD.transform(lo,la+1e-5);north=np.array([xn-x,yn-y]);north/=np.linalg.norm(north);east=np.array([north[1],-north[0]]);h=n[0]*east+n[1]*north
            attitudes.append({'unit':g,'xyz':[x,y,float(hpos[idx,2])],'pole':[float(h[0]),float(h[1]),float(n[2])],'strike':strike,'dip':dip,'source':sheet,'status':'mapped_bedding_assigned_by_location_to_seamless_symbol'})
    constraints={'orientations':attitudes,'contacts':{},'fault_traces':[]}
    for sheet in SHEETS:
        for sr in read_layer(sheet,'geo_L').iterShapeRecords():
            d=sr.record.as_dict()
            if '断層' not in d.get('LEGEND01',''):continue
            pts=np.asarray(sr.shape.points);parts=list(sr.shape.parts)+[len(pts)]
            for a,b in zip(parts[:-1],parts[1:]):
                lo,la=pts[a:b].T;x,y=FWD.transform(lo,la);distance,nearest=htree.query(np.c_[x,y])
                if not np.any(distance<250):continue
                select=np.arange(0,len(x),max(1,len(x)//100));z=hpos[nearest,2]
                constraints['fault_traces'].append({'name':d.get('LEGEND02')or d['LEGEND01'],'source':sheet,'xyz':np.c_[x,y,z][select].round(2).tolist(),'status':'mapped_trace_only_not_inferred_plane'})
    np.savez_compressed(OUT/'surface.npz',dem=dem,surface=surface,island=island,xs=xs,ys=ys,
                        high_positions=hpos,high_units=highunits,high_edges=high_edges,provenance=np.where(island,200,0).astype(np.uint8))
    meta={'extent_xy':[xmin,xmax,ymin,ymax],'shape':[NX,NY],'spacing_m':[dx,dy],'crs':'EPSG:32653','units':units,'unknown_id':unknown,
          'source':'GSJ Seamless Geological Map V2 API 1.3.1, original legend symbols retained','land_cells':int(island.sum()),'mapped_orientation_count':len(attitudes),
          'source_legend_count':len(active),'fetched_at':datetime.now(timezone.utc).isoformat(),'raw_sha256':{'data/raw/seamless-legend.json':hashlib.sha256((RAW/'seamless-legend.json').read_bytes()).hexdigest()}}
    (OUT/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2));(OUT/'constraints.json').write_text(json.dumps(constraints,ensure_ascii=False,indent=2))
    # 元の地表データと同じ頂点順序の地形を同時に保存し、地下計算の接触グラフにも使う。
    web=ROOT/'web/data';web.mkdir(parents=True,exist_ok=True);parts=[];offset=0
    def pack(values,dtype='<f4'):
        nonlocal offset
        values=np.asarray(values,dtype=dtype).ravel();entry={'offset':offset,'count':len(values),'type':dtype};parts.append(values.tobytes());offset+=values.nbytes;return entry
    center=[(xmin+xmax)/2,(ymin+ymax)/2]
    terrain_positions=np.c_[(hpos[:,0]-center[0])/1000,hpos[:,2]/1000,-(hpos[:,1]-center[1])/1000]
    vi=np.clip(((hpos[:,0]-xmin)/dx).astype(int),0,NX-1);vj=np.clip(((hpos[:,1]-ymin)/dy).astype(int),0,NY-1)
    terrain={'positions':pack(terrain_positions),'indices':pack(faces,'<u4'),'shape':[hx,hy],'sourceIndex':pack(vi*NY+vj,'<u4'),'color':pack(hr[...,:3].reshape(-1,3)[used]/255),'units':pack(highunits,'<u4')}
    (web/'terrain-mesh.bin').write_bytes(b''.join(parts));(web/'terrain-mesh.json').write_text(json.dumps(terrain))

    print(json.dumps({'source_units':len(active),'land_cells':int(island.sum()),'attitudes':len(attitudes),'surface_counts':{u['key']:int((surface==u['id']).sum()) for u in units}},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
