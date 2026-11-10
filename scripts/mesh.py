"""計算格子から連続境界面・断面を抽出し、表示用の細かい地形を作る。推定結果は変更しない。"""
import json
from pathlib import Path
import numpy as np
import shapely
from scipy import ndimage
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes, find_contours
from prepare import ROOT, FWD, INV, decode_dem, tile_sample
from rock_bodies import build as build_bodies

WEB=ROOT/'web/data'

class Pack:
    def __init__(self): self.parts=[];self.offset=0
    def put(self, values, dtype='<f4'):
        a=np.asarray(values,dtype=dtype).ravel(); entry={'offset':self.offset,'count':len(a),'type':dtype}
        self.parts.append(a.tobytes());self.offset+=a.nbytes;return entry
    def save(self,path): path.write_bytes(b''.join(self.parts))

def fault_aware_smooth(values,closed):
    q=values.astype(np.float32)
    masks=[]
    for axis in range(3):
        pads=[(1,1)]*3;masks.append(np.pad(closed[axis],pads,constant_values=False))
    for _ in range(3):
        result=q.copy()
        for axis,weight in enumerate((.05,.05,.01)):
            a=[slice(None)]*3;b=a.copy();a[axis]=slice(None,-1);b[axis]=slice(1,None);a=tuple(a);b=tuple(b)
            change=(q[b]-q[a])*weight;change[masks[axis]]=0
            result[a]+=change;result[b]-=change
        q=result
    return q

def main():
    meta=json.loads((WEB/'model.json').read_text());nx,ny=meta['shape'];nz=meta['nz'];body_catalog=build_bodies(meta);unit_ids=[b['id'] for b in body_catalog];nunits=max(unit_ids)+1;native={b['id']:b['source_unit'] for b in body_catalog}
    xmin,xmax,ymin,ymax=meta['extent_xy'];cx=(xmin+xmax)/2;cy=(ymin+ymax)/2
    dx=(xmax-xmin)/nx;dy=(ymax-ymin)/ny;dz=(meta['zmax']-meta['zmin'])/nz
    source=np.load(ROOT/'data/prepared/surface.npz')
    # 地形は地下の表示格子とは別に、約100m間隔で標高タイルから生成する。
    hx,hy=400,576
    xs=np.linspace(xmin+dx/2,xmax-dx/2,hx);ys=np.linspace(ymin+dy/2,ymax-dy/2,hy)
    xx,yy=np.meshgrid(xs,ys,indexing='ij');lon,lat=INV.transform(xx,yy)
    dem=decode_dem(tile_sample(lon,lat,12,'dem'))
    si=np.clip(((xx-xmin)/dx).astype(int),0,nx-1);sj=np.clip(((yy-ymin)/dy).astype(int),0,ny-1)
    land=np.isfinite(dem)
    nearest=ndimage.distance_transform_edt(~np.isfinite(dem),return_distances=False,return_indices=True)
    filled=dem[tuple(nearest)]
    def cap(v):
        ix=(v[:,0]-xs[0])/(xs[-1]-xs[0])*(hx-1);iy=(v[:,1]-ys[0])/(ys[-1]-ys[0])*(hy-1)
        top=ndimage.map_coordinates(filled,[ix,iy],order=1,mode='nearest')
        v[:,2]=np.minimum(v[:,2],top)
        return v
    def world(v): return np.c_[(v[:,0]-cx)/1000,v[:,2]/1000,-(v[:,1]-cy)/1000]
    positions=world(np.c_[xx.ravel(),yy.ravel(),np.nan_to_num(dem,nan=0).ravel()])
    # 海岸の階段状の輪郭も、細かい地質タイルの陸海境界で置き換える。
    rgba=tile_sample(lon,lat,12,'geology');sea=(rgba[...,3]==0)|(np.min(rgba[...,:3],axis=2)>250)
    land &= ~sea
    labels,_=ndimage.label(land)
    seed=FWD.transform(134.85,34.4)
    component=labels[np.argmin(abs(xs-seed[0])),np.argmin(abs(ys-seed[1]))]
    if component==0: raise ValueError('地形の淡路島シードが陸域にありません')
    land=labels==component
    faces=[]
    for i in range(hx-1):
        for j in range(hy-1):
            if land[i:i+2,j:j+2].all():
                a=i*hy+j;b=(i+1)*hy+j
                faces.extend([[a,a+1,b+1],[a,b+1,b]])
    faces=np.asarray(faces,dtype=np.uint32);used=np.unique(faces);lookup=np.zeros(hx*hy,np.uint32);lookup[used]=np.arange(len(used));faces=lookup[faces];positions=positions[used]
    legend=json.loads((ROOT/'data/raw/seamless-legend.json').read_text());palette=np.array([[d['r'],d['g'],d['b']] for d in legend]);distance,nearest=cKDTree(palette).query(rgba[...,:3].reshape(-1,3)[used])
    catalog={u['source_symbol']:u['id'] for u in meta['units'] if u['kind']=='geological'}
    vertex_units=np.array([catalog.get(legend[i]['symbol'],meta['unknown_id']) for i in nearest],np.uint32)
    if np.any(distance>1):raise ValueError('地表の原凡例を識別できません')
    terrain_pack=Pack();geom={'positions':terrain_pack.put(positions),'indices':terrain_pack.put(faces,'<u4'),'shape':[hx,hy],
                            'sourceIndex':terrain_pack.put((si*ny+sj).ravel()[used],'<u4'),'color':terrain_pack.put(rgba[...,:3].reshape(-1,3)[used]/255),'units':terrain_pack.put(vertex_units,'<u4')}
    terrain_pack.save(WEB/'terrain-mesh.bin');(WEB/'terrain-mesh.json').write_text(json.dumps(geom))
    def convert(v):
        return np.c_[xmin+(v[:,0]-.5)*dx,ymin+(v[:,1]-.5)*dy,meta['zmin']+(v[:,2]-.5)*dz]
    for scenario in meta['scenarios']:
        folder=WEB/scenario;volume=np.fromfile(folder/'body-volume.bin','<u2').reshape(nx,ny,nz)
        # 共通の多値場から界面を求め、隣接単元の界面に隙間を作らない。
        padded=np.pad(volume,1)
        barrier_data=np.load(ROOT/f'data/prepared/fault-barriers-{scenario}.npz')
        closed=[barrier_data[f'axis{i}'] for i in range(3)]
        probs=np.stack([fault_aware_smooth(padded==g,closed) for g in range(nunits)])
        top=probs.max(axis=0);winner=probs.argmax(axis=0);second=np.partition(probs,-2,axis=0)[-2]
        pack=Pack();meshes=[];fields={}
        for g in unit_ids:
            field=probs[g]-np.where(winner==g,second,top);fields[g]=field
            if field.max()<=0:continue
            v,f,_,_=marching_cubes(field,0,allow_degenerate=False)
            v=cap(convert(v));p=world(v)
            meshes.append({'unit':native[g],'body':g,'positions':pack.put(p),'indices':pack.put(f,'<u4')})
        pack.save(folder/'meshes.bin');(folder/'meshes.json').write_text(json.dumps(meshes))
        pack=Pack();sections=[[],[],[]]
        for axis,size in enumerate((nx,ny,nz)):
            for k in range(size):
                items=[]
                for g in unit_ids:
                    field=np.take(fields[g],k+1,axis=axis)
                    # 等値線の入れ子を対称差で処理し、空洞を埋めない。
                    shape=shapely.GeometryCollection()
                    for contour in find_contours(field,0,fully_connected='high'):
                        if len(contour)<4: continue
                        polygon=shapely.Polygon(contour)
                        if not polygon.is_valid: polygon=shapely.make_valid(polygon)
                        shape=shapely.symmetric_difference(shape,polygon)
                    if shape.is_empty:continue
                    triangles=shapely.get_parts(shapely.constrained_delaunay_triangles(shape))
                    vertices=[]
                    for triangle in triangles:
                        if triangle.area<1e-8:continue
                        coords=np.array(triangle.exterior.coords)[:3]
                        v=np.empty((3,3));v[:,axis]=k+1
                        other=[i for i in range(3) if i!=axis];v[:,other]=coords
                        vertices.extend(world(convert(v) if axis==2 else cap(convert(v))).tolist())
                    if vertices:items.append({'unit':native[g],'body':g,'positions':pack.put(vertices)})
                sections[axis].append(items)
        pack.save(folder/'sections.bin');(folder/'sections.json').write_text(json.dumps(sections))
        print(scenario, 'meshes',len(meshes),'sections',sum(map(len,sections)), 'bytes',pack.offset,flush=True)
    (WEB/'mesh-method.json').write_text(json.dumps({'method':'Shared categorical fields with fault-blocked diffusion; marching cubes and constrained contour triangulation',
        'display_smoothing':'3 symmetric diffusion steps, weights x/y=.05, z=.01; zero flux across fault barriers', 'terrain_spacing_m':[(xs[-1]-xs[0])/(hx-1),(ys[-1]-ys[0])/(hy-1)],
        'note':'表示用補間。元の推定結果・精度・カテゴリ格子は変更しない。断層を越える平滑化は遮断。'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
