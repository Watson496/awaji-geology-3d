"""公式の断層線の頂点を保持し、端点間の直線や地図の画素から線を作らない。

シームレス地質図の線と2つのGeomapNavi重ね合わせ図は、別々の出典として扱う。
構造補間に使うのは出典と対応づけた地質断層だけとする。
活断層の重ね合わせ図は広域の参照用とし、追加の障壁にはしない。
"""
import copy,gzip,hashlib,io,json,zipfile
import numpy as np
import shapefile,shapely
from shapely.geometry import shape,LineString
from pyproj import Transformer
from scipy.spatial import cKDTree
from prepare import ROOT,RAW,OUT,BOX,FWD,fetch


def decoded(data):return gzip.decompress(data) if data[:2]==b'\x1f\x8b' else data

def build(previous):
    region=shapely.box(*BOX);sources={};faults=[];groups={}
    previous_path=ROOT/'data/structure/official-faults.json'
    pinned=json.loads(previous_path.read_text())['sources'] if previous_path.exists() else {}
    def check_source(key,data):
        digest=hashlib.sha256(data).hexdigest()
        if key in pinned and pinned[key]['sha256']!=digest:raise ValueError(f'Official fault source changed: {key}; source review required')
        return digest
    hp=np.load(OUT/'surface.npz')['high_positions'];tree=cKDTree(hp[:,:2])
    # 5万分の1地質図の名称・姿勢は対応づけに使い、形状の置き換えには使わない。
    references=[(f,shapely.union_all([LineString(np.array(t)[:,:2]) for t in f['traces']])) for f in previous if f['trace_kind']=='mapped_50k' and f['name'] not in ('断層','推定断層')]
    def project(line,transform=FWD):
        points=np.array([transform.transform(*p[:2]) for p in line.coords]);distance,near=tree.query(points)
        return np.c_[points,np.where(distance<200,hp[near,2],0)].tolist()
    def parts(geometry):
        if geometry.is_empty:return []
        if geometry.geom_type=='LineString':return [geometry]
        return [p for g in geometry.geoms for p in parts(g)]
    for code in [5134,5135,5234,5235]:
        url=f'https://gsj-seamless.jp/seamless/download/shape/seamlessV2_shape_{code}.zip'
        data=fetch(url,RAW/f'seamless-{code}.zip');sources[str(code)]={'url':url,'sha256':check_source(str(code),data),'crs':'JGD2000 (EPSG:4612), from .prj','map_revision':'2025-07-18'}
        archive=zipfile.ZipFile(io.BytesIO(data));reader=shapefile.Reader(shp=io.BytesIO(archive.read(f'{code}_line.shp')),shx=io.BytesIO(archive.read(f'{code}_line.shx')),dbf=io.BytesIO(archive.read(f'{code}_line.dbf')),encoding='utf-8')
        transform=Transformer.from_crs(4612,32653,always_xy=True)
        for index,record in enumerate(reader.iterShapeRecords()):
            attr=record.record.as_dict();kind=attr['Major_Code']
            if kind not in ('2','4','6'):continue  # 撓曲を断層に含めない
            original=shape(record.shape.__geo_interface__)
            for part,line in enumerate(parts(original.intersection(region))):
                trace=project(line,transform);projected=LineString(np.array(trace)[:,:2]);sample=shapely.line_interpolate_point(projected,np.linspace(0,1,9),normalized=True)
                candidates=sorted([(float(np.max(shapely.distance(sample,g))),f['name'],f) for f,g in references],key=lambda x:x[0])
                match=candidates[0] if candidates and candidates[0][0]<250 else None
                key=f"seamless:{match[1]}:{kind}" if match else f'seamless:{code}:{index}:{part}'
                if key not in groups:
                    f=copy.deepcopy(match[2]) if match else {'profile_depth_dip':None,'dip_azimuth_deg':None,'supported_depth_m':0,'attitude_kind':'unresolved_orientation','angle_sensitivity_deg':0,'section_constraints':[],'notes':'地下姿勢は未拘束。後段の資料制約・姿勢推定で扱う。'}
                    f['attitude_source']=f.get('source')
                    f.update({'id':key,'name':match[1] if match else f"{attr['Legend_J']} {code}-{index}",'layer':'seamless','trace_kind':'official_seamless_vector','line_code':kind,'dashed':kind!='2','traces':[],'source_records':[],'source':'seamless','used_for_model':True,'horizontal_uncertainty_m':200})
                    if match:f['attitude_crosswalk']={'source':'GSJ 50k mapped faults','maximum_sample_distance_m':match[0],'status':'spatial correlation hypothesis; original trace geometry retained'}
                    groups[key]=f;faults.append(f)
                groups[key]['traces'].append(trace);groups[key]['source_records'].append({'sheet':code,'record':index,'part':part,'attributes':attr})
    for name,layer in [('af_segment','active'),('JPF_2024','major')]:
        url=f'https://gbank.gsj.jp/geonavi/docdata/db/{name}.json';data=fetch(url,RAW/f'{name}.json');sources[layer]={'url':url,'sha256':check_source(layer,data),'crs':'GeoJSON longitude/latitude WGS84','role':'same URL used by GeomapNavi; reference, not added interpolation barriers'}
        for index,feature in enumerate(json.loads(decoded(data))['features']):
            geom=shape(feature['geometry']);lines=parts(geom.intersection(region))
            if not lines:continue
            prop=feature['properties'];identifier=str(prop.get('id',prop.get('fault_segment_id',index)));label=prop.get('name',f'主要活断層帯 {identifier}')
            faults.append({'id':f'{layer}:{identifier}:{index}','name':label,'layer':layer,'trace_kind':'official_geonavi_geojson','source':layer,'source_properties':prop,'source_records':[{'feature':index}], 'traces':[project(g) for g in lines],'dashed':prop.get('_strokeDashstyle','solid')!='solid','color':prop.get('_color','#ed3346'),'used_for_model':False,'profile_depth_dip':None,'dip_azimuth_deg':None,'supported_depth_m':0,'angle_sensitivity_deg':0,'attitude_kind':'reference_trace_only','section_constraints':[],'notes':'Naviと同じ原データ。地域的な概略線。地下の面や地質境界との対応を意味しない。'})
    from gsi_fault_constraints import build as build_kinematics
    build_kinematics(faults)
    from fault_attitudes import constrain
    sections=json.loads((ROOT/'data/structure/sections.json').read_text())['sections']
    constrain(faults,sections)
    result={'sources':sources,'faults':faults,'layers':[{'id':'seamless','name':'シームレス地質図の断層','color':'#111111'},{'id':'active','name':'活断層データ','color':'#ed3346'},{'id':'major','name':'全国主要活断層帯','color':'#ed3346'}]}
    (ROOT/'data/structure/official-faults.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));return result
