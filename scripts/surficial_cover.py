"""地質群の推定に、有限の厚さを持つ表層被覆の仮説を適用する。

厚さは局所的なDEMからの深さで測り、絶対標高で区切らない。
公表断面は局所的な厚さの尺度に使い、島全体の上限とはしない。
地表の観測セルは固定する。50m格子では2〜10mの層を解像できない。
"""
import hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
POLICY=ROOT/'data/structure/surficial-cover.json'

def policy():return json.loads(POLICY.read_text())

def constrain_packages(scores,packages,z,dem,rock,scenario):
    rules=policy()['units'];depth=dem[...,None]-z[None,None,:]
    top=rock&~np.concatenate([rock[:,:,1:],np.zeros((*rock.shape[:2],1),bool)],axis=2)
    result=scores.copy();excluded={}
    for gi,package in enumerate(packages):
        symbols=[s for s in package['symbols'] if s in rules]
        if not symbols:continue
        limit=max(rules[s]['scenario_thickness_m'][scenario] for s in symbols)
        forbidden=rock&~top&(depth>limit)
        result[...,gi][forbidden]=-1e6
        excluded[package['id']]={'scenario_thickness_m':limit,'excluded_cells':int(forbidden.sum())}
    return result,{'kind':'finite surficial-cover thickness prior, not measured basal geometry','policy':'surficial-cover.json','packages':excluded,'top_cell_exception':'Original map label fixed; the top cell can represent unresolved thin cover. Grid thickness is not a field measurement.'}

def audit_volume(volume,meta,dem,scenario):
    z=meta['zmin']+(np.arange(meta['nz'])+.5)*(meta['zmax']-meta['zmin'])/meta['nz'];depth=dem[...,None]-z
    dz=(meta['zmax']-meta['zmin'])/meta['nz'];result={}
    for u in meta['units']:
        rule=policy()['units'].get(u['key'])
        if rule is None:continue
        m=volume==u['id'];limit=rule['scenario_thickness_m'][scenario]
        # 地表の観測は、未解像の1セル内に対応しうるが、深い列全体には対応させない。
        if np.any(m&(depth>max(limit,dz/2)+1e-5)):raise ValueError(f'Surficial unit escaped thickness prior: {scenario}/{u["key"]}')
        result[u['key']]={'prior_thickness_m':limit,'maximum_cell_center_depth_m':float(np.max(depth[m])) if m.any() else None,'cell_bottom_depth_upper_bound_m':float(np.max(depth[m])+dz/2) if m.any() else None,'cells':int(m.sum()),'cells_below_150m':int((m&(depth>150)).sum()),'note':'50m discretization; not a measured or sub-grid thickness'}
    return result

def publish():
    p=policy()
    for s in p['sources']:
        actual=hashlib.sha256((ROOT/s['file']).read_bytes()).hexdigest()
        if actual!=s['sha256']:raise ValueError(f'Surficial-cover source changed: {s["id"]}')
    (ROOT/'web/data/surficial-cover.json').write_text(json.dumps(p,ensure_ascii=False,indent=2))
