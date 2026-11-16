"""現在の断層形状を整理し、地震時のすべりモデルは適用しない。

GSJの5万分の1地質図の断層線は、分離した各部分をそのまま保持する。
地震調査研究推進本部の端点を結ぶ線は、広域の近似として扱う。
"""
import json
import hashlib
from pathlib import Path
import numpy as np
from prepare import ROOT, OUT, FWD, fetch
from scipy.spatial import cKDTree
from official_faults import build as build_official

DEST = ROOT / 'data/structure/faults.json'

def build():
    sources = json.loads((DEST.parent/'sources.json').read_text())
    for source in sources.values():
        data=fetch(source['url'],ROOT/source['file'])
        if hashlib.sha256(data).hexdigest()!=source['sha256']:raise ValueError(f'Official source changed: {source["url"]}')
    constraints = json.loads((OUT/'constraints.json').read_text())
    grouped = {}
    for i,t in enumerate(constraints['fault_traces']):
        name = t['name']
        # 名称のない断層線を、単一の架空の断層に結合しない。
        key = name if name not in ('断層','推定断層') else f'{t["source"]}-{name}-{i+1}'
        grouped.setdefault(key,[]).append(t)
    profiles = {
        '野島断層': ('rokko',135,[[0,80],[600,80],[4000,80]],'約80°南東傾斜は約600m以浅。深部への延長は仮定。',600),
        '浅野断層': ('rokko',135,[[0,80],[600,80],[4000,80]],'西岸区間の代表傾斜を適用する仮定。',600),
        '楠本断層': ('rokko',315,[[0,80],[2000,80],[4000,80]],'高角度北西傾斜。80°という数値は仮定。',2000),
        '東浦断層': ('rokko',315,[[0,80],[2000,80],[4000,80]],'高角度北西傾斜。80°という数値は仮定。',2000),
        '野田尾断層': ('rokko',315,[[0,80],[2000,80],[4000,80]],'東岸区間の代表傾斜を適用する仮定。',2000),
        '志筑断層': ('shizuki',76,[[0,70],[4000,70]],'北東傾斜。角度70°と深部形状は仮定。',0),
    }
    for n in ['先山断層','安乎断層','奥畑断層','鮎原南断層']:
        profiles[n]=('senzan',305,[[0,60],[4000,60]],'地表付近の北西傾斜。角度60°と深部形状は仮定。',0)
    faults=[]
    for key,traces in grouped.items():
        name=traces[0]['name']; known=name in profiles
        source,az,profile,note,depth=profiles.get(name,('gsj50k',0,[[0,90],[4000,90]],'傾斜不明のため鉛直面を仮定。断層面全体は未拘束。',0))
        faults.append({'id':key,'name':name,'traces':[t['xyz'] for t in traces],
            'trace_kind':'mapped_50k','trace_sources':sorted(set(t['source'] for t in traces)),
            'dip_azimuth_deg':az,'profile_depth_dip':profile,'supported_depth_m':depth,
            'attitude_kind':'published_direction_with_explicit_angle_or_extrapolation_prior' if known else 'unknown_vertical_prior',
            'notes':note,'source':source,'horizontal_uncertainty_m':100,
            'angle_sensitivity_deg':5 if name in ['野島断層','浅野断層'] else (10 if known else 20)})
    # 中持断層の傾斜は、A-B断面の解釈済み断層点に適合させる。
    sections=json.loads((DEST.parent/'sections.json').read_text())['sections']
    for section in sections:sources[section['id']]={'url':section['source_url'],'sha256':section['source_sha256'],'figure':section['name']}
    for fault in faults:
        picks=[p for sec in sections for p in sec['fault_picks'] if p['fault_name']==fault['name']]
        fault['section_constraints']=picks
        if fault['name']!='中持断層' or not picks:continue
        vectors=[];depths=[]
        for pick in picks:
            xyz=np.array(pick['xyz']);nearest=None
            for trace in fault['traces']:
                for a,b in zip(np.array(trace)[:-1],np.array(trace)[1:]):
                    v=b[:2]-a[:2];f=np.clip((xyz[:2]-a[:2])@v/max(v@v,1e-9),0,1);foot=a+(b-a)*f
                    distance=np.linalg.norm(xyz[:2]-foot[:2])
                    if nearest is None or distance<nearest[0]:nearest=(distance,foot)
            distance,foot=nearest
            if foot[2]>xyz[2]:vectors.append(xyz[:2]-foot[:2]);depths.append(foot[2]-xyz[2])
        vec=np.mean(vectors,axis=0);az=float(np.degrees(np.arctan2(vec[0],vec[1]))%360);direction=vec/np.linalg.norm(vec)
        horizontal=np.array(vectors)@direction;depths=np.array(depths);cot=float(horizontal@depths/(depths@depths));dip=float(np.degrees(np.arctan2(1,cot)))
        fault.update({'dip_azimuth_deg':az,'profile_depth_dip':[[0,dip],[4000,dip]],'source':'akashi-ab',
            'attitude_kind':'fitted_to_interpreted_section','supported_depth_m':float(max(depths)),
            'notes':'明石1990 A-B断面の中持断層2点と地表断層線から傾斜を最小二乗推定。読み取り誤差120m。浅部から断層全体・深部への延長は仮定。'})
    official=build_official(faults);faults=official['faults']
    sources.update(official['sources'])
    out={'target':'present-day geological structure; no coseismic or cumulative slip is applied',
        'sources':sources,'faults':faults,'fault_zones':[],'layers':official['layers'],'map_connections':[],
        'limitations':['Endpoint chords and hand-digitized regional traces are excluded; only original official vectors are published.',
        'Unknown fault dips and depths are priors, not measurements.',
        'No temporal restoration, earthquake slip, slip-rate multiplication, or arbitrary fault throw.',
        'Borehole logs and seismic velocities are not assigned to seamless lithology codes without georeferencing and correlation.']}
    DEST.write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print('faults',len(faults),'trace parts',sum(len(f['traces']) for f in faults))
    return out

if __name__=='__main__':build()
