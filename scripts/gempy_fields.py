"""シームレス地質図V2の原単元ごとにGemPyの暗黙場を計算する。5区分への統合は行わない。"""
from pathlib import Path
import argparse
import contextlib
import hashlib
import io
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import gempy as gp
import numpy as np
from scipy.spatial import cKDTree
from scipy import ndimage
from prepare import ROOT, OUT, spaced_indices

WEB=ROOT/'web/data'
NZ,ZMIN,ZMAX=52,-3000.,700.
SCENARIOS={'reference':(1.,0),'shallow':(.65,-5),'deep':(1.4,5)}
# 観測値ではない。原単元ごとに独立した有限深度の構造仮説を記録する。
DEPTHS={'H2_or':8,'H_sad':35,'H_ssd':25,'Q32-33_std':35,'Q31_std':60,'Q22_std':80,'Q1-21_sn':350,
'N3_sns':450,'N3_snc':450,'Pg2_sbs':180,'Pg3_sns':250,'K22_soss':2200,'K22_som':2200,'K22_soc':1800,'K22_sosma':2200,
'K21_vas_ap':600,'K21_pbg_a':1600,'K2-Pg12_mgmpe_lks':2500,'K12_pbd_a':3500,'K21_pam_a':3500,'K21_pan_a':3500,
'K21_pim_a':3500,'K21_pin_a':3500,'K22_pam_a':3500,'K22_pim_a':3500}
_CONTEXT=None

def context():
    global _CONTEXT
    if _CONTEXT is not None:return _CONTEXT
    meta=json.loads((OUT/'metadata.json').read_text());s=dict(np.load(OUT/'surface.npz'));c=json.loads((OUT/'constraints.json').read_text())
    nx,ny=meta['shape'];xmin,xmax,ymin,ymax=meta['extent_xy'];dz=(ZMAX-ZMIN)/NZ
    x,y,z=np.meshgrid(s['xs'],s['ys'],ZMIN+(np.arange(NZ)+.5)*dz,indexing='ij')
    rock=s['island'][...,None]&(z-dz/2<s['dem'][...,None]);ez=np.minimum(z,s['dem'][...,None]-.5)
    points=np.c_[x[rock],y[rock],ez[rock]]
    xx,yy=np.meshgrid(s['xs'],s['ys'],indexing='ij');ground=np.c_[xx[s['island']],yy[s['island']],s['dem'][s['island']]-1]
    points=np.vstack([points,ground]);nrock=int(rock.sum())
    tm=json.loads((WEB/'terrain-mesh.json').read_text());raw=(WEB/'terrain-mesh.bin').read_bytes();e=tm['indices'];f=np.frombuffer(raw,dtype=e['type'],offset=e['offset'],count=e['count']).reshape(-1,3)
    edges=np.unique(np.sort(np.vstack([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1),axis=0)
    signature=hashlib.sha256(Path(__file__).read_bytes()+(OUT/'metadata.json').read_bytes()+(OUT/'surface.npz').read_bytes()+(OUT/'constraints.json').read_bytes()).hexdigest()
    _CONTEXT=(meta,s,c,points,nrock,rock,edges,signature);return _CONTEXT

def thin(points,spacing,limit,minimum=3):
    if not len(points):return np.empty(0,int)
    ids=spaced_indices(points[:,:2],spacing,limit)
    if len(ids)<min(minimum,len(points)):ids=np.unique(np.linspace(0,len(points)-1,min(minimum,len(points))).astype(int))
    return ids

def age(symbol):
    if symbol.startswith('K2-Pg'):return None
    for i,prefix in enumerate(['H','Q32','Q31','Q22','Q1','N3','Pg3','Pg2','K22','K21','K12']):
        if symbol.startswith(prefix):return i
    return None

def task(args):
    scenario,g,surface_only=args;t=time.monotonic();meta,s,c,points,nrock,rock,edges,signature=context();unit=meta['units'][g-1];key=unit['key'];depth=DEPTHS[key]*SCENARIOS[scenario][0]
    target=OUT/'fields'/scenario/f'{key}{"-surface" if surface_only else ""}.npz';target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        cache=np.load(target)
        if str(cache['signature'])==signature:return scenario,g,str(target),0.
    hp=s['high_positions'];hu=s['high_units'];inside=hp[hu==g]
    # 地表の実測ラベルを持つ格子中心も校正点に含める。
    ground=points[nrock:];truth=s['surface'][s['island']];inside=np.vstack([inside,ground[truth==g]+[0,0,1]])
    itree=cKDTree(inside[:,:2]);margin=max(1200.,depth*.8)
    distances=itree.query(points[:,:2])[0]
    candidate=(distances<margin)&(points[:,2]>inside[:,2].min()-depth*1.35)
    if surface_only:candidate[:nrock]=False
    query_ids=np.flatnonzero(candidate)
    ii=thin(inside,400,220);inside=inside[ii];
    outside=hp[hu!=g];outside=outside[itree.query(outside[:,:2])[0]<margin+1200]
    outside=outside[thin(outside,550,260)]
    mask=((hu[edges[:,0]]==g)^(hu[edges[:,1]]==g));edge=edges[mask]
    contact=(hp[edge[:,0]]+hp[edge[:,1]])*.5
    inward=np.where((hu[edge[:,0]]==g)[:,None],hp[edge[:,0]]-hp[edge[:,1]],hp[edge[:,1]]-hp[edge[:,0]])
    inward[:,2]=0;inward/=np.linalg.norm(inward,axis=1)[:,None]
    neighbors=np.where(hu[edge[:,0]]==g,hu[edge[:,1]],hu[edge[:,0]])
    ci=thin(contact,500,150);contact=contact[ci];normals=inward[ci];neighbors=neighbors[ci]
    obs=[o for o in c['orientations'] if o['unit']==g]
    delta=SCENARIOS[scenario][1]
    def pole(o):
        p=np.array(o['pole'],float);a=np.arctan2(p[0],p[1]);d=np.clip(np.arccos(p[2])+np.radians(delta),.001,np.radians(85))
        return np.array([np.sin(d)*np.sin(a),np.sin(d)*np.cos(a),np.cos(d)])
    # 同年代の異なる岩相は側方境界のまま扱い、層序へ並べない。
    rank=age(key)
    for i,other in enumerate(neighbors):
        neighbor=meta['units'][int(other)-1];nr=age(neighbor['key'])
        if rank is None or nr is None or rank==nr:continue
        if rank<nr and unit['source_legend']['group_ja']=='堆積岩':
            o=min(obs,key=lambda o:np.linalg.norm(np.array(o['xyz'][:2])-contact[i,:2])) if obs else None
            normals[i]=pole(o) if o else [0,0,1]
        elif rank>nr and neighbor['source_legend']['group_ja']=='堆積岩':
            otherobs=[o for o in c['orientations'] if o['unit']==int(other)]
            o=min(otherobs,key=lambda o:np.linalg.norm(np.array(o['xyz'][:2])-contact[i,:2])) if otherobs else None
            normals[i]=-pole(o) if o else [0,0,-1]
    basal=inside[thin(inside,1500,65)].copy();basal[:,2]-=depth
    deep_inside=inside[thin(inside,900,80)].copy();deep_inside[:,2]-=.4*depth
    below=basal.copy();below[:,2]-=.35*depth
    # inside/outsideは地質単元ではなく、原単元の暗黙場を校正する補助等値面。
    anchors=[np.vstack([inside,deep_inside]),np.vstack([contact,basal]),np.vstack([outside,below])]
    orientation_positions=np.vstack([contact[::max(1,len(contact)//45)],basal[::max(1,len(basal)//20)]])
    orientation_poles=np.vstack([normals[::max(1,len(contact)//45)],np.tile([0,0,1],(len(basal[::max(1,len(basal)//20)]),1))])
    elements=[]
    for name,coords in zip(['inside_anchor','contact','outside_anchor'],anchors):
        sp=gp.data.SurfacePointsTable.from_arrays(x=coords[:,0],y=coords[:,1],z=coords[:,2],names=name,nugget=np.full(len(coords),1e-12))
        if name=='contact':ot=gp.data.OrientationsTable.from_arrays(x=orientation_positions[:,0],y=orientation_positions[:,1],z=orientation_positions[:,2],G_x=orientation_poles[:,0],G_y=orientation_poles[:,1],G_z=orientation_poles[:,2],names=name,nugget=np.full(len(orientation_positions),.02))
        else:ot=gp.data.OrientationsTable.initialize_empty()
        elements.append(gp.data.StructuralElement(name=name,color=unit['color'],surface_points=sp,orientations=ot))
    frame=gp.data.StructuralFrame([gp.data.StructuralGroup('body',elements,gp.data.StackRelationType.ERODE)],gp.data.ColorsGenerator())
    xmin,xmax,ymin,ymax=meta['extent_xy'];model=gp.create_geomodel(project_name=key,extent=[xmin,xmax,ymin,ymax,ZMIN,ZMAX],refinement=1,structural_frame=frame)
    model.interpolation_options.evaluation_options.mesh_extraction=False;model.interpolation_options.evaluation_options.evaluation_chunk_size=1000000
    calibration=np.array([anchors[0][0],anchors[1][0],anchors[2][0]])
    with contextlib.redirect_stdout(io.StringIO()):gp.compute_model_at(model,np.vstack([points[query_ids],calibration]))
    output=model.solutions.root_output.outputs[0]
    result=output.scalar_fields.exported_fields.scalar_field[output.grid.custom_grid_slice]
    result=np.asarray(result).ravel();
    if len(result)!=len(query_ids)+3:raise ValueError('GemPyのカスタム格子と出力点数が一致しません')
    a,b,d=result[-3:]
    if abs(a-b)<1e-10:raise ValueError(f'{key}: 暗黙場の内外を校正できません')
    scores=((result[:-3]-b)/(a-b)).astype(np.float32)
    # 地表を既知の境界条件として与える。地表のカテゴリIDを地下へ押し出す処理ではない。
    # GemPy場の地表残差を連続な場として補正し、深度とともに減衰させる。
    nx,ny=meta['shape'];xmin,xmax,ymin,ymax=meta['extent_xy'];dx=(xmax-xmin)/nx;dy=(ymax-ymin)/ny
    unit_mask=s['surface']==g
    surface_target=np.clip((ndimage.distance_transform_edt(unit_mask,sampling=(dx,dy))-ndimage.distance_transform_edt(~unit_mask,sampling=(dx,dy)))/500,-1,1)
    raw_ground=np.zeros((nx,ny),np.float32)
    qi=np.clip(((points[query_ids,0]-xmin)/dx).astype(int),0,nx-1);qj=np.clip(((points[query_ids,1]-ymin)/dy).astype(int),0,ny-1)
    isground=query_ids>=nrock;raw_ground[qi[isground],qj[isground]]=scores[isground]
    residual=surface_target-raw_ground
    length=min(depth*.5,750.)
    depth_below=np.maximum(0,s['dem'][qi,qj]-points[query_ids,2]-1)
    scores+=residual[qi,qj]*np.exp(-depth_below/length)

    if not np.isfinite(scores).all():raise ValueError(f'{key}: 暗黙場に非有限値')
    audit={'source_symbol':key,'source_unit_id':g,'depth_prior_m':depth,'contact_count':len(contact),'inside_anchors':len(anchors[0]),'outside_anchors':len(anchors[2]),
           'bedding_count':len(obs),'side_boundary_attitude':'vertical prior unless an older/younger sediment contact provides a bedding proxy',
           'basal_points':basal.tolist(),'calibration':[float(a),float(b),float(d)],'outside_calibrated_score':float((d-b)/(a-b)),
           'surface_condition':'Signed-distance boundary condition from observed source symbols; residual from GemPy surface field decays exponentially with depth', 'surface_decay_length_m':length,'computed_points':len(query_ids),'elapsed_seconds':round(time.monotonic()-t,2),'status':'source-symbol-preserving structural hypothesis; finite-depth and side-attitude priors, not measured subsurface boundaries'}
    np.savez_compressed(target,indices=query_ids.astype(np.int32),score=scores,audit=json.dumps(audit),signature=signature)
    return scenario,g,str(target),audit['elapsed_seconds']

def combine(scenario):
    meta,s,c,points,nrock,rock,edges,signature=context();units=meta['units'];best=np.zeros(len(points),np.float32);second=np.zeros(len(points),np.float32);ids=np.full(len(points),meta['unknown_id'],np.uint8);audits=[]
    for unit in units:
        if unit['kind']=='unknown':continue
        cache=np.load(OUT/'fields'/scenario/f"{unit['key']}.npz");idx=cache['indices'];score=cache['score'];audit=json.loads(str(cache['audit']));audits.append(audit)
        if str(cache['signature'])!=signature:raise ValueError('計算場の入力バージョンが一致しません')
        win=score>best[idx];second[idx]=np.maximum(second[idx],np.minimum(score,best[idx]));best[idx[win]]=score[win];ids[idx[win]]=unit['id']
    volume=np.zeros(rock.shape,np.uint8);volume[rock]=ids[:nrock];surface=np.zeros(meta['shape'],np.uint8);surface[s['island']]=ids[nrock:]
    truth=s['surface'][s['island']];conf=np.zeros((len(units),len(units)),int)
    np.add.at(conf,(truth-1,ids[nrock:]-1),1)
    folder=WEB/scenario;folder.mkdir(parents=True,exist_ok=True);volume.tofile(folder/'volume.bin');surface.tofile(folder/'surface.bin')
    ambiguity=np.zeros(rock.shape,np.uint8);ambiguity[rock]=((best[:nrock]>0)&((best[:nrock]-second[:nrock])<.05)).astype(np.uint8);ambiguity.tofile(folder/'ambiguous.bin')
    report={'scenario':scenario,'gempy_version':gp.__version__,'source_legend_count':len(units)-1,'surface_agreement':float(np.mean(truth==ids[nrock:])),
            'surface_agreement_note':'Surface labels are imposed as boundary conditions; agreement is not an independent validation of subsurface structure.','surface_confusion_matrix_actual_rows':conf.tolist(),'voxel_counts':{u['key']:int((volume==u['id']).sum()) for u in units},
            'unknown_fraction':float(np.mean(ids[:nrock]==meta['unknown_id'])),'ambiguous_fraction':float(ambiguity.sum()/nrock),'audit':audits,
            'interpretation':'Each original source symbol has its own GemPy potential field. Positive calibrated fields compete by maximum normalized potential; nonpositive locations remain explicitly unconstrained. Same-age units are not assigned an invented stratigraphic order.'}
    (folder/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:report[k] for k in ['scenario','surface_agreement','unknown_fraction','voxel_counts']},ensure_ascii=False),flush=True)

def export_common():
    meta,s,c,points,nrock,rock,edges,signature=context();WEB.mkdir(parents=True,exist_ok=True)
    s['surface'].tofile(WEB/'observed.bin');np.nan_to_num(s['dem'],nan=-9999).astype('<f4').tofile(WEB/'terrain.bin');s['provenance'].tofile(WEB/'provenance.bin');rock.astype(np.uint8).tofile(WEB/'domain.bin')
    (WEB/'constraints.json').write_text(json.dumps(c,ensure_ascii=False,separators=(',',':')))
    meta.update({'nz':NZ,'zmin':ZMIN,'zmax':ZMAX,'order':'C [x,y,z]; z increases upward','scenarios':list(SCENARIOS),
                 'status':'Original seamless symbols retained; independent GemPy body hypotheses with explicit unconstrained domain',
                 'faults':'Mapped traces only; fault displacement not included','priors':{'depth_m':DEPTHS,'scenario_factors':SCENARIOS},'input_signature':signature})
    (WEB/'model.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    a=[np.fromfile(WEB/name/'volume.bin',np.uint8) for name in SCENARIOS];((a[0]!=a[1])|(a[0]!=a[2])).astype(np.uint8).tofile(WEB/'disagreement.bin')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scenario',choices=[*SCENARIOS,'all'],default='all');parser.add_argument('--unit');parser.add_argument('--surface-only',action='store_true');parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    meta=json.loads((OUT/'metadata.json').read_text());names=list(SCENARIOS) if args.scenario=='all' else [args.scenario]
    jobs=[(name,u['id'],args.surface_only) for name in names for u in meta['units'] if u['kind']!='unknown' and (args.unit is None or u['key']==args.unit)]
    if not jobs:raise ValueError('計算対象の原単元がありません')
    if args.workers==1:
        for job in jobs:print(task(job),flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures={pool.submit(task,job):job for job in jobs}
            for future in as_completed(futures):print(future.result(),flush=True)
    if args.surface_only and not args.unit:
        meta,s,c,points,nrock,rock,edges,signature=context();truth=s['surface'][s['island']];best=np.zeros(len(truth));pred=np.full(len(truth),meta['unknown_id'],np.uint8)
        for u in meta['units']:
            if u['kind']=='unknown':continue
            a=np.load(OUT/'fields'/names[0]/f"{u['key']}-surface.npz");idx=a['indices']-nrock;score=a['score'];win=score>best[idx];best[idx[win]]=score[win];pred[idx[win]]=u['id']
        print('SURFACE AGREEMENT',float(np.mean(pred==truth)),'UNKNOWN',float(np.mean(pred==meta['unknown_id'])),flush=True)
        for u in meta['units']:
            if u['kind']=='unknown':continue
            mask=truth==u['id'];print(u['key'],int(mask.sum()),float(np.mean(pred[mask]==u['id'])),flush=True)
    if args.unit or args.surface_only:return
    for name in names:combine(name)
    if all((WEB/name/'metrics.json').exists() and json.loads((WEB/name/'metrics.json').read_text()).get('source_legend_count')==meta['source_legend_count'] for name in SCENARIOS):export_common()

if __name__=='__main__':main()
