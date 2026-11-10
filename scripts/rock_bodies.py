"""地質図上の岩体の識別と、シームレス地質図の岩相区分を分ける。

既存の岩相推定に岩体を帰属させる処理であり、貫入境界や地層境界は再推定しない。
地表の起点には両地質図の一致を要求する。帰属の伝播は同じ原岩相内に限り、
閉じた断層辺を越えない。根拠のない岩体や競合する岩体は未割当のまま残す。
"""
import hashlib
import json
from pathlib import Path
import numpy as np
import shapely
from scipy import sparse
from scipy.sparse.csgraph import dijkstra
from pyproj import Transformer
from prepare import ROOT, read_layer

WEB = ROOT / 'web/data'
MAX_DISTANCE = 2000.  # 帰属のシナリオであり、観測された岩体の範囲ではない。
MIN_MARGIN = 200.  # 最寄りの起点間の二等分線に、根拠のない接触面を作らない。
MAP_FWD = Transformer.from_crs(4612,32653,always_xy=True)  # geo_A.prj: JGD2000

# 地図の重なりだけでは岩相の対応を確定できないため、対応関係を明示する。
# 2図幅にまたがる同名の地層は識別を共有し、岩相は原区分・色・出典IDを保持する。
MAPPED = {
    'akashi': {
        'Kt': ('kariya', '仮屋累層', ['Q1-21_sn']),
        'Kj': ('kariya', '仮屋累層', ['N3_sns','Q1-21_sn']),
        'Kk': ('kariya', '仮屋累層', ['N3_sns','Q1-21_sn']),
        'To': ('toshima', '富島累層', ['N3_snc','N3_sns','Q1-21_sn']),
        'Tf': ('toshima', '富島累層', ['N3_snc','N3_sns','Q1-21_sn']),
        'Ta': ('toshima', '富島累層', ['N3_snc','N3_sns','Q1-21_sn']),
        'A': ('atago', '愛宕累層', ['N3_snc','N3_sns','Q1-21_sn']),
        'Iu': ('iwaya', '岩屋累層', ['Pg2_sbs']),
        'Im': ('iwaya', '岩屋累層', ['Pg2_sbs']),
        'Il': ('iwaya', '岩屋累層', ['Pg2_sbs']),
        'NGd': ('nojima-gd', '野島花崗閃緑岩', ['K21_pim_a']),
        'TG': ('tosanji', '東山寺花崗岩', ['K21_pam_a']),
        'IG': ('iwaya-granite', '岩屋花崗岩', ['K22_pam_a']),
        'KG': ('kagaribayama', '篝場山花崗岩', ['K22_pam_a']),
        'ST': ('shizuki', '志筑トーナル岩', ['K21_pin_a']),
        'TS': ('tsushigawa', '都志川花崗岩', ['K21_pan_a']),
    },
    'sumoto': {
        'Go': ('goshikihama', '五色浜累層', ['N3_sns','Q1-21_sn']),
        **{k: ('atago', '愛宕累層', ['N3_snc','N3_sns','Q1-21_sn']) for k in ('At','Ag','As','Aa','Ai')},
        **{k: ('toshima', '富島累層', ['N3_snc','N3_sns','Q1-21_sn']) for k in ('To','Ta')},
        'Il': ('iwaya', '岩屋累層', ['Pg2_sbs']),
        **{k: ('kitaama', '北阿万累層', ['K22_som','K22_sosma','K22_soss']) for k in ('Ks','Ka')},
        **{k: ('seidan', '西淡累層', ['K22_soc','K22_som','K22_sosma','K22_soss']) for k in ('Sg','Sc')},
        'SG': ('senzan', '先山花崗岩', ['K22_pim_a']),
        'TG': ('tosanji', '東山寺花崗岩', ['K21_pam_a']),
        'SGd': ('sumoto-gd', '洲本花崗閃緑岩', ['K21_pim_a']),
        'W': ('sennan', '泉南流紋岩類', ['K21_vas_ap']),
        'EGd': ('ei', '江井花崗閃緑岩', ['K21_pan_a','K21_pin_a']),
        'ST': ('shizuki', '志筑トーナル岩', ['K21_pin_a']),
        'TS': ('tsushigawa', '都志川花崗岩', ['K21_pan_a']),
        'SO': ('shio', '塩尾花崗岩', ['K21_pan_a']),
        'Gb': ('gabbroids', '斑れい岩類', ['K21_pbg_a']),
    },
}


def group(key):
    if key in ('K22_soc','K22_som','K22_sosma','K22_soss'): return '和泉層群'
    if key in ('N3_snc','N3_sns','Q1-21_sn'): return '大阪層群'
    if key == 'Pg2_sbs': return '古第三系'
    if key in ('K12_pbd_a','K21_pam_a','K21_pan_a','K21_pbg_a','K21_pim_a','K21_pin_a','K22_pam_a','K22_pim_a'): return '深成岩類'
    if key == 'K21_vas_ap': return '火山岩類'
    if key == 'K2-Pg12_mgmpe_lks': return '変成岩類'
    if key in ('Q31_std','Q32-33_std'): return '段丘堆積物'
    if key in ('H2_or','H_sad'): return '沖積層・人工地盤'
    return '未拘束'


def seed_catalog(meta, surface):
    xx,yy=np.meshgrid(surface['xs'],surface['ys'],indexing='ij')
    points=shapely.points(xx,yy);seeds={};provenance={};names={}
    by_key={u['key']:u['id'] for u in meta['units']}
    for sheet, mapping in MAPPED.items():
        for feature in read_layer(sheet,'geo_A').iterShapeRecords():
            symbol=feature.record.as_dict()['Symbol'].strip()
            if symbol not in mapping: continue
            key,name,allowed=mapping[symbol]
            polygon=shapely.geometry.shape(feature.shape.__geo_interface__)
            polygon=shapely.transform(polygon,MAP_FWD.transform,interleaved=False)
            inside=shapely.contains(polygon,points)
            for native_key in allowed:
                uid=by_key[native_key]
                mask=inside & (surface['surface']==uid) & surface['island']
                # 地図境界が食い違う付近の単一セルの一致だけでは、
                # 図幅をまたぐ岩相の対応を確定しない。
                if mask.sum()<3: continue
                identity=(key,uid);names[identity]=name
                seeds[identity]=seeds.get(identity,np.zeros(xx.shape,bool))|mask
                provenance.setdefault(identity,[]).append({'sheet':sheet,'symbol':symbol,'surface_cells':int(mask.sum())})
    bodies=[]
    for u in meta['units']:
        bodies.append({**u,'source_unit':u['id'],'identity':f'unassigned:{u["key"]}',
                       'group':group(u['key']),'attribution':'unassigned',
                       'short_name':u['short_name'], 'name':u['name']})
    for identity in sorted(seeds):
        key,uid=identity;u=meta['units'][uid-1]
        bodies.append({**u,'id':len(bodies)+1,'source_unit':uid,'identity':key,
                       'key':f'{key}:{u["key"]}','name':f'{names[identity]} / {u["source_symbol"]}',
                       'short_name':names[identity], 'group':group(u['key']),'attribution':'interpreted',
                       'sources':provenance[identity]})
    return bodies,seeds


def attribute(volume, bodies, seeds, closed, spacing, max_distance=MAX_DISTANCE, margin=MIN_MARGIN):
    """原岩相IDを変えずに、別の岩体IDを返す。"""
    result=volume.astype(np.uint16);shape=volume.shape
    top=volume.shape[2]-1-np.argmax((volume!=0)[...,::-1],axis=2)
    for uid in sorted({b['source_unit'] for b in bodies if b['attribution']=='interpreted'}):
        candidates=[b for b in bodies if b['source_unit']==uid and b['attribution']=='interpreted']
        mask=volume==uid;ids=np.full(shape,-1,np.int32);ids[mask]=np.arange(mask.sum())
        rows=[];cols=[];weights=[]
        for axis,step in enumerate(spacing):
            a=[slice(None)]*3;b=a.copy();a[axis]=slice(None,-1);b[axis]=slice(1,None);a=tuple(a);b=tuple(b)
            connected=mask[a]&mask[b]&~closed[axis]
            rows.append(ids[a][connected]);cols.append(ids[b][connected]);weights.append(np.full(connected.sum(),step))
        rows=np.concatenate(rows);cols=np.concatenate(cols);weights=np.concatenate(weights)
        graph=sparse.coo_matrix((weights,(rows,cols)),shape=(mask.sum(),mask.sum())).tocsr()
        graph=graph+graph.T
        best=np.full(mask.sum(),np.inf);second=best.copy();winner=np.zeros(mask.sum(),np.uint16)
        for body in candidates:
            observed=seeds[(body['identity'],uid)]
            i,j=np.nonzero(observed);k=top[i,j]
            source=ids[i,j,k];source=np.unique(source[source>=0])
            if not len(source): continue
            dist=dijkstra(graph,directed=False,indices=source,min_only=True,limit=max_distance)
            better=dist<best;second=np.where(better,best,np.minimum(second,dist))
            best=np.minimum(best,dist);winner[better]=body['id']
        # 第2候補が無限大なら、範囲内に競合する岩体はない。
        gap=np.full_like(best,np.inf)
        np.subtract(second,best,out=gap,where=np.isfinite(best))
        supported=np.isfinite(best)&(gap>margin)
        values=result[mask];values[supported]=winner[supported];result[mask]=values
    return result


def build(meta):
    surface=np.load(ROOT/'data/prepared/surface.npz');bodies,seeds=seed_catalog(meta,surface)
    nx,ny=meta['shape'];nz=meta['nz'];spacing=[*meta['spacing_m'],(meta['zmax']-meta['zmin'])/nz]
    counts={}
    for scenario in meta['scenarios']:
        folder=WEB/scenario;volume=np.fromfile(folder/'volume.bin',np.uint8).reshape(nx,ny,nz)
        barriers=np.load(ROOT/f'data/prepared/fault-barriers-{scenario}.npz')
        attributed=attribute(volume,bodies,seeds,[barriers[f'axis{i}'] for i in range(3)],spacing)
        attributed.astype('<u2').tofile(folder/'body-volume.bin')
        counts[scenario]={str(int(i)):int(n) for i,n in zip(*np.unique(attributed,return_counts=True))}
        print(scenario,'body attribution',len(counts[scenario])-1,flush=True)
    for body in bodies:
        body['cell_counts']={s:counts[s].get(str(body['id']),0) for s in meta['scenarios']}
    catalog={'schema_version':1,'body_volume_dtype':'<u2','bodies':bodies,'method':'Same-native-class, finite-fault-blocked shortest paths from concordant 50k / seamless outcrops',
             'maximum_transfer_m':MAX_DISTANCE,'minimum_winner_margin_m':MIN_MARGIN,
             'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'native_volume_sha256':{s:hashlib.sha256((WEB/s/'volume.bin').read_bytes()).hexdigest() for s in meta['scenarios']},
             'limitations':['Body attribution is an interpretation of the existing volume, not an independently fitted 3D contact.',
                            'No vertical polygon extrusion. No splitting by disconnected pixels alone.',
                            'Unassigned means geological identity is unresolved; it does not mean unknown native lithology.',
                            '1990/1992 Iwaya map symbols identify the area only; obsolete Miocene age / Kobe assignment is not adopted.'],
             'sources':[{'sheet':s,'crs':'EPSG:4612','url':f'https://www.gsj.jp/data/50KGM/VCT/GSJ_MAP_G050_{c}_V01.zip',
                         'sha256':hashlib.sha256((ROOT/f'data/raw/{s}-vector.zip').read_bytes()).hexdigest()}
                        for s,c in [('akashi','12083_1990'),('sumoto','13011_1992')]]}
    (WEB/'rock-bodies.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2))
    return bodies


if __name__=='__main__':
    build(json.loads((WEB/'model.json').read_text()))
