"""有限断層面を境界とする、現在の地質単元のスカラー場を補間する。

原地質単元ごとに反応項付きの離散Laplace方程式を解く。
有限断層面と交差する辺の伝導度は0とし、変位場や地震時のすべりは適用しない。
GemPy場を仮定に基づく弱い事前分布、現在の地表ラベルをDirichlet境界条件とする。
"""
import argparse
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import cg, LinearOperator
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
from prepare import ROOT,OUT
from prepare_faults import build
from prepare_sections import build as build_sections
from fault_attitudes import local_offset
from model_domain import native_prior,section_support,ZMIN,ZMAX,NZ
from structure import topology, ordered_packages, write_topology
from surficial_cover import constrain_packages,audit_volume,publish as publish_cover
from substrate_model import infer as infer_substrate,compose as compose_substrate
from marine_model import envelope as marine_envelope

WEB=ROOT/'web/data'
SCENARIOS=['reference','shallow','deep']

def offset_at(depth,profile,delta=0):
    """断層線からcot(dip)を積分する。節点間の傾斜は線形に変化させる。"""
    depth=np.maximum(np.asarray(depth,float),0)
    knots=np.array(profile,float);total=np.zeros_like(depth)
    # 格子より細かな精度を得るため、各区間を16分割して中点則で積分する。
    for (a,da),(b,db) in zip(knots[:-1],knots[1:]):
        length=np.clip(depth-a,0,b-a)
        for k in range(16):
            q=(k+.5)/16;angle=np.clip(da+(db-da)*length*q/(b-a)+delta,15,90)
            total+=length/16/np.tan(np.radians(angle))
    return total

def fault_triangles(fault,zmin,scenario='reference'):
    if not fault.get('used_for_model',True):return np.empty((0,3,3))
    profile=fault.get('profile_depth_dip')
    ensemble=fault.get('orientation_ensemble')
    if ensemble:
        orientation=ensemble[scenario];profile=[[0,orientation['dip_deg']],[4000,orientation['dip_deg']]];az=np.radians(orientation['dip_azimuth_deg']);delta=0
    else:
        # 直接拘束された曲線には、別の公表済み事前分布がない場合がある。
        if profile is None:profile=[[0,fault['section_attitudes'][0]['dip_deg']],[4000,fault['section_attitudes'][0]['dip_deg']]]
        az=np.radians(fault.get('dip_azimuth_deg',0));delta={'reference':0,'shallow':-1,'deep':1}[scenario]*fault.get('angle_sensitivity_deg',0)
    direction=np.array([np.sin(az),np.cos(az)]);triangles=[]
    for trace in fault['traces']:
        trace=np.asarray(trace,float)
        for a,b in zip(trace[:-1],trace[1:]):
            tangent=b[:2]-a[:2];length=np.linalg.norm(tangent)
            if length<1e-6:continue
            tangent/=length;normal=np.array([-tangent[1],tangent[0]])
            n=max(1,int(np.ceil(length/(250 if fault.get('section_attitudes') else 500))))
            for k in range(n):
                u=a+(b-a)*k/n;v=a+(b-a)*(k+1)/n
                maximum=max(u[2],v[2])-zmin
                levels=sorted(set([0.,maximum]+[float(d) for c in fault.get('section_attitudes',[]) for d in c['depth_m'] if 0<d<maximum]+[float(p[0]) for p in profile if 0<p[0]<maximum]))
                def vertex(p,d):
                    z=max(zmin,p[2]-d);depth=p[2]-z
                    prior=float(offset_at(depth,profile,delta))*(1 if np.dot(direction,normal)>=0 else -1)
                    offset=local_offset(fault,p,depth,normal,scenario,prior)
                    return np.r_[p[:2]+offset*normal,z]
                for d0,d1 in zip(levels[:-1],levels[1:]):
                    p,q,r,t=vertex(u,d0),vertex(v,d0),vertex(v,d1),vertex(u,d1)
                    triangles.extend([[p,q,r],[p,r,t]])
    return np.asarray(triangles)

def intersection_mask(origins,direction,triangle):
    """Möller–Trumbore法で有限線分と三角形の交差をベクトル化して計算する。"""
    a,b,c=triangle;e1=b-a;e2=c-a;h=np.cross(direction,e2);det=e1@h
    if abs(det)<1e-10:return np.zeros(len(origins),bool)
    s=origins-a;u=(s@h)/det;q=np.cross(s,e1);v=(q@direction)/det;t=(q@e2)/det
    eps=1e-7
    return (u>=-eps)&(v>=-eps)&(u+v<=1+eps)&(t>=-eps)&(t<=1+eps)

def barriers(shape,origin,spacing,faults,zmin,scenario='reference',domain=None):
    closed=[np.zeros(tuple(n-(i==axis) for i,n in enumerate(shape)),bool) for axis in range(3)]
    counts={}
    for fault in faults:
        hit=0
        for tri in fault_triangles(fault,zmin,scenario):
            for axis in range(3):
                direction=np.eye(3)[axis]*spacing[axis]
                low=np.floor((tri.min(axis=0)-origin)/spacing).astype(int)-1
                high=np.ceil((tri.max(axis=0)-origin)/spacing).astype(int)+1
                low=np.maximum(low,0);high=np.minimum(high,np.array(closed[axis].shape)-1)
                if np.any(high<low):continue
                ijk=np.stack(np.meshgrid(*[np.arange(a,b+1) for a,b in zip(low,high)],indexing='ij'),-1).reshape(-1,3)
                pts=origin+ijk*spacing;cross=intersection_mask(pts,direction,tri)
                index=tuple(ijk[cross].T);new=~closed[axis][index]
                if domain is not None:
                    other=ijk[cross].copy();other[:,axis]+=1;new &= domain[index]&domain[tuple(other.T)]
                hit+=int(new.sum());closed[axis][index]=True
        counts[fault['id']]=hit
    members=[f['id'] for f in faults if f.get('zone_id')=='mtl-kitan-naruto']
    if members:counts['mtl-kitan-naruto']=sum(counts[k] for k in members)
    return closed,counts

def build_system(rock,closed,spacing,screen=.02):
    """岩石セル間だけに辺を持つ対称グラフ演算子。断層をまたぐ辺は持たない。"""
    count=int(rock.sum());index=np.full(rock.shape,-1,np.int32);index[rock]=np.arange(count)
    rows=[];cols=[];weights=[];degree=np.zeros(count,np.float32)
    scale=min(spacing[:2])
    for axis in range(3):
        a=[slice(None)]*3;b=a.copy();a[axis]=slice(None,-1);b[axis]=slice(1,None);a=tuple(a);b=tuple(b)
        valid=rock[a]&rock[b]&~closed[axis];i=index[a][valid];j=index[b][valid]
        w=np.float32((scale/spacing[axis])**2)
        rows.extend([i,j]);cols.extend([j,i]);weights.extend([np.full(len(i),-w,np.float32)]*2)
        np.add.at(degree,i,w);np.add.at(degree,j,w)
    matrix=sparse.coo_matrix((np.concatenate(weights),(np.concatenate(rows),np.concatenate(cols))),shape=(count,count)).tocsr()
    return matrix,degree,index

def solve_fields(meta,s,catalog,scenario,closed,counts):
    start=time.monotonic();marine_grid,marine_audit=marine_envelope(meta,s,scenario,catalog)
    nx,ny=meta['shape'];nz=meta['nz'];dz=(meta['zmax']-meta['zmin'])/nz
    z=meta['zmin']+(np.arange(nz)+.5)*dz
    rock=s['island'][...,None]&(z[None,None,:]-dz/2<s['dem'][...,None])
    offdiag,degree,index=build_system(rock,closed,np.array([*meta['spacing_m'],dz]))
    # 陸域の各列の最上部の岩石セルをDirichlet境界とする。
    top=np.zeros_like(rock);ii,jj=np.nonzero(s['island']);kk=rock.sum(axis=2)[ii,jj]-1;top[ii,jj,kk]=True
    fixed=top[rock];free=~fixed;free_ids=np.flatnonzero(free)
    lam=np.float32(.02)
    full=offdiag+sparse.diags(degree+lam)
    system=full[free_ids][:,free_ids].tocsr();coupling=full[free_ids][:,np.flatnonzero(fixed)].tocsr()
    invdiag=1/system.diagonal();pre=LinearOperator(system.shape,matvec=lambda x:invdiag*x,dtype=np.float32)
    best=np.zeros(int(rock.sum()),np.float32);second=best.copy();chosen=np.full(len(best),meta['unknown_id'],np.uint8)
    package_defs,package_map=topology(meta)
    native_scores={};package_priors=[np.full(len(best),-1,np.float32) for _ in package_defs]
    section_data=json.loads((ROOT/'data/structure/sections.json').read_text())
    section_picks=[p for sec in section_data['sections'] if sec['used_for_model'] for p in sec['picks']]
    rock_xyz=np.stack(np.meshgrid(s['xs'],s['ys'],z,indexing='ij'),-1)[rock]
    tree=cKDTree(rock_xyz)
    pick_penalty=np.zeros(len(best),np.float32);mapped_picks=[]
    for pick in section_picks:
        distance,j=tree.query(pick['xyz'])
        if distance>200:raise ValueError(f'Section pick outside model: {pick["id"]}')
        weight=(min(meta['spacing_m'])/pick['sigma_m'])**2
        pick_penalty[j]+=weight;mapped_picks.append((pick,int(j),float(weight),float(distance)))
    full=full+sparse.diags(pick_penalty)
    system=full[free_ids][:,free_ids].tocsr();invdiag=1/system.diagonal()
    pre=LinearOperator(system.shape,matvec=lambda x:invdiag*x,dtype=np.float32)
    nrock=len(best);truth=s['surface'][ii,jj];audits=[]
    for unit in meta['units']:
        if unit['kind']=='unknown':continue
        cache=np.load(OUT/'fields'/scenario/f'{unit["key"]}.npz')
        prior=native_prior(cache,rock,z,s)
        package_priors[package_map[unit['id']]]=np.maximum(package_priors[package_map[unit['id']]],prior)
        boundary=np.where(truth==unit['id'],1.,-1.).astype(np.float32)
        evidence=np.zeros(nrock,np.float32)
        for pick,j,weight,_ in mapped_picks:evidence[j]+=weight*((0 if pick['kind']=='interpreted_section_boundary' else 1) if unit['key'] in pick['allowed_symbols'] else -1)
        rhs=(lam*prior+evidence)[free]-coupling@boundary;iterations=[0]
        def tick(_):iterations[0]+=1
        solution,status=cg(system,rhs,x0=prior[free],M=pre,rtol=2e-4,atol=1e-5,maxiter=700,callback=tick)
        if status!=0:raise RuntimeError(f'{scenario}/{unit["key"]}: fault-constrained solver failed to converge ({status})')
        residual=float(np.linalg.norm(system@solution-rhs)/max(np.linalg.norm(rhs),1e-9))
        score=np.empty(nrock,np.float32);score[free]=solution;score[fixed]=boundary
        native_scores[unit['id']]=score
        win=score>best;second=np.maximum(second,np.minimum(score,best));best[win]=score[win];chosen[win]=unit['id']
        audits.append({'source_symbol':unit['key'],'iterations':iterations[0],'relative_residual':residual,'prior_signature':str(cache['signature'])})
        print(scenario,unit['key'],'iterations',iterations[0],'residual',round(residual,6),flush=True)
    # 共通の包絡面は地質群ごとに推定し、22岩相のポテンシャルの大域的な競争で選ばない。
    package_scores=np.zeros((*rock.shape,len(package_defs)),np.float32)
    for gi,package in enumerate(package_defs):
        boundary=np.where(np.isin(truth,package['unit_ids']),1.,-1.).astype(np.float32)
        evidence=np.zeros(nrock,np.float32)
        for pick,j,weight,_ in mapped_picks:
            allowed=[u['id'] for u in meta['units'] if u['key'] in pick['allowed_symbols']]
            evidence[j]+=weight*((0 if pick['kind']=='interpreted_section_boundary' else 1) if any(a in package['unit_ids'] for a in allowed) else -1)
        rhs=(lam*package_priors[gi]+evidence)[free]-coupling@boundary
        solution,status=cg(system,rhs,x0=package_priors[gi][free],M=pre,rtol=2e-4,atol=1e-5,maxiter=700)
        if status:raise RuntimeError(f'{scenario}/{package["id"]}: shared envelope did not converge')
        values=np.empty(nrock,np.float32);values[free]=solution;values[fixed]=boundary
        field=np.zeros(rock.shape,np.float32);field[rock]=values;package_scores[...,gi]=field
    # 海域の音響基盤は新生代以前の共通包絡面を制約するが、
    # 特定の花崗岩や海域の岩相の識別には使わない。
    for gi in range(len(package_defs)):package_scores[...,gi]+=.35*marine_grid*(1 if gi<2 else -1)
    surface_package=package_map[s['surface']]
    package_scores,cover_audit=constrain_packages(package_scores,package_defs,z,s["dem"],rock,scenario)
    package_grid=ordered_packages(package_scores,rock,closed[2],surface_package)
    chosen=np.full(nrock,meta['unknown_id'],np.uint8);best=np.zeros(nrock,np.float32);second=best.copy()
    for gi,package in enumerate(package_defs):
        mask=package_grid[rock]==gi
        for uid in package['unit_ids']:
            score=native_scores[uid];win=mask&(score>best)
            second[mask]=np.maximum(second[mask],np.minimum(score[mask],best[mask]));best[win]=score[win];chosen[win]=uid
    # 貫入岩の重複は、根拠のある局所的な岩相関係に従って解消する。
    # 片状岩相と塊状岩相に堆積層としての順序を与えない。
    symbols={u['key']:u['id'] for u in meta['units']}
    intrusion_changes=0
    for younger,older in [('K21_pim_a',['K21_pan_a','K21_pin_a']),('K21_pam_a',['K21_pan_a','K21_pin_a','K21_pim_a'])]:
        uid=symbols[younger];mask=(package_grid[rock]==0)&np.isin(chosen,[symbols[k] for k in older])&(native_scores[uid]>.25)&~fixed
        intrusion_changes+=int(mask.sum());chosen[mask]=uid
    # 現在の地表の原ラベルは、厳密な境界条件として保持する。
    support=section_support(meta,s,json.loads((ROOT/'data/structure/sections.json').read_text())['sections'])[rock]
    extrapolated=chosen.copy()
    # 根拠の強さは出典・不確実性を表し、岩体を切り捨てる条件にはしない。
    chosen[fixed]=truth
    volume=np.zeros(rock.shape,np.uint8);volume[rock]=chosen
    substrate,substrate_packages,substrate_audit,substrate_status=infer_substrate(meta,s,scenario,rock,top,offdiag,degree,mapped_picks,closed,marine_grid,z)
    previous_classification=volume.copy()
    volume,package_grid,substrate_region=compose_substrate(volume,package_grid,substrate,substrate_packages,s['surface'],meta)
    chosen=volume[rock];extrapolated=chosen.copy()
    substrate_audit['under_cover']={}
    for unit in meta['units']:
        if unit['key'] not in json.loads((ROOT/'data/structure/surficial-cover.json').read_text())['units']:continue
        region=substrate_region&(s['surface']==unit['id'])[...,None]
        n=int(region.sum())
        substrate_audit['under_cover'][unit['key']]={'cells':n,'cover_only_unknown_fraction':float(np.mean(previous_classification[region]==meta['unknown_id'])) if n else None,'unknown_fraction':float(np.mean(volume[region]==meta['unknown_id'])) if n else None,'changed_cells':int((volume[region]!=previous_classification[region]).sum())}
    cover_audit["result"]=audit_volume(volume,meta,s["dem"],scenario)
    section_validation=[]
    for pick,j,weight,distance in mapped_picks:
        predicted=meta['units'][int(chosen[j])-1]['key']
        section_validation.append({'id':pick['id'],'predicted_symbol':predicted,'allowed_symbols':pick['allowed_symbols'],'matches':predicted in pick['allowed_symbols'],'snap_distance_m':distance,'sigma_m':pick['sigma_m'],'usage':'fitting constraint; not independent validation'})
    packages_out=np.zeros(rock.shape,np.uint8);packages_out[rock]=package_grid[rock]+1;packages_out.tofile((WEB/scenario)/'structural-packages.bin')
    folder=WEB/scenario;previous=json.loads((folder/'metrics.json').read_text());old_raw=np.fromfile(folder/'volume.bin',np.uint8);old=old_raw.reshape(rock.shape) if old_raw.size==rock.size else np.full(rock.shape,meta['unknown_id'],np.uint8)
    raw_extrapolation=np.zeros(rock.shape,np.uint8);raw_extrapolation[rock]=extrapolated;raw_extrapolation.tofile(folder/'extrapolated-volume.bin')
    volume.tofile(folder/'volume.bin');s['surface'].tofile(folder/'surface.bin')
    ambiguous=np.zeros_like(volume);ambiguous[rock]=((best>0)&(best-second<.05)).astype(np.uint8);ambiguous[substrate_region]=(substrate_status[substrate_region]==2).astype(np.uint8);ambiguous.tofile(folder/'ambiguous.bin')
    block_count,labels=connected_components(offdiag,directed=False)
    np.savez_compressed(OUT/f'fault-barriers-{scenario}.npz',**{f'axis{i}':x for i,x in enumerate(closed)})
    component_grid=np.zeros(rock.shape,np.uint32);component_grid[rock]=labels+1;component_grid.tofile(folder/'fault-blocks.bin')
    previous.update({'surface_agreement':1.,'surface_agreement_note':'Present-day surface labels are Dirichlet boundary conditions, not independent subsurface validation.',
        'surface_confusion_matrix_actual_rows':np.diag(np.bincount(truth,minlength=len(meta['units'])+1)[1:]).tolist(),
        'unknown_fraction':float(np.mean(chosen==meta['unknown_id'])),'section_extrapolation_fraction':float(np.mean(support==0)),'ambiguous_fraction':float(ambiguous.sum()/nrock),
        'voxel_counts':{u['key']:int((volume==u['id']).sum()) for u in meta['units']},
        'fault_conditioning':{'method':'screened graph Laplace interpolation, zero conductance on finite fault crossings, Dirichlet present-day source labels, clipped GemPy potentials as weak priors',
        'screening_weight':float(lam),'fault_count':len(catalog['faults']),'blocked_edges':{k:int(v) for k,v in counts.items()},
        'graph_components':int(block_count),'changed_from_previous_snapshot_cells':int(np.sum((old!=volume)&rock)),
        'substrate':substrate_audit,'surficial_cover':cover_audit,'marine_structure':marine_audit,'topology':{'package_count':len(package_defs),'shared_envelopes':True,'ordered_unfaulted_segments':True,'intrusive_overlap_cells':intrusion_changes},'section_fit':section_validation,'coseismic_displacement_applied':False,'cumulative_displacement_applied':False,'solver_audit':audits,
        'elapsed_seconds':round(time.monotonic()-start,2)},
        'interpretation':'Present-day fault-bounded structural hypothesis. Faults block the interpolation operator; neither event slip nor invented cumulative throw is applied. Surface traces, reported dips, extrapolation priors and regional chords are distinguished in faults.json. Georeferenced interpreted section lithology/contact picks are fitted; these are not independent validation. Borehole logs are not fitted.'})
    (folder/'metrics.json').write_text(json.dumps(previous,ensure_ascii=False,indent=2))
    print(scenario,'changed',previous['fault_conditioning']['changed_from_previous_snapshot_cells'],'unknown',previous['unknown_fraction'],flush=True)

def structural_signature():
    paths=[ROOT/'data/structure'/name for name in ['sources.json','faults.json','sections.json','marine.json','topology.json','official-faults.json','gsi-fault-kinematics.json','surficial-cover.json','substrate-policy.json']]
    paths += [ROOT/'scripts'/name for name in ['fault_model.py','marine_model.py','structure.py','prepare_sections.py','prepare_faults.py','prepare_marine.py','official_faults.py','model_domain.py','fault_attitudes.py','gsi_fault_constraints.py','surficial_cover.py','substrate_model.py']]
    return hashlib.sha256(b''.join(p.read_bytes() for p in paths)).hexdigest()

def main():
    publish_cover();(WEB/"substrate-policy.json").write_bytes((ROOT/"data/structure/substrate-policy.json").read_bytes());build_sections();catalog=build();meta=json.loads((WEB/'model.json').read_text());s=dict(np.load(OUT/'surface.npz'))
    meta.update({'zmin':ZMIN,'zmax':ZMAX,'nz':NZ,'depth_policy':{'land_lithology_elevation_m':[ZMIN,ZMAX],'basis':'Printed -500m lower section axes of Akashi 1990 and Sumoto 1992. Computational cap only; NOT evidence of island-wide support to -500m.','section_influence_window_m':500,'outside_section_support':'continuous structural extrapolation with weak priors; support is recorded separately and does not excise bodies','deep_marine_model':'separate acoustic basement envelope, not native lithology'}})
    write_topology(meta)
    nx,ny=meta['shape'];nz=meta['nz'];dz=(meta['zmax']-meta['zmin'])/nz
    spacing=np.array([*meta['spacing_m'],dz]);origin=np.array([s['xs'][0],s['ys'][0],meta['zmin']+dz/2])
    zz=meta['zmin']+np.arange(nz)*dz
    domain=s['island'][...,None]&(zz[None,None,:]<s['dem'][...,None])
    domain.astype(np.uint8).tofile(WEB/'domain.bin')
    sections=json.loads((ROOT/'data/structure/sections.json').read_text())['sections']
    support=section_support(meta,s,sections);support[~domain]=0
    support.tofile(WEB/'section-support.bin')
    for name in SCENARIOS:
        closed,counts=barriers((nx,ny,nz),origin,spacing,catalog['faults'],meta['zmin'],name,domain)
        print(name,'barriers',sum(int(v.sum()) for v in closed),flush=True)
        surface_data=[{'id':f['id'],'name':f['name'],'trace_kind':f['trace_kind'],'attitude_kind':f['attitude_kind'],'triangles':fault_triangles(f,meta['zmin'],name).round(3).tolist()} for f in catalog['faults']]
        (WEB/f'fault-surfaces-{name}.json').write_text(json.dumps(surface_data,ensure_ascii=False,separators=(',',':')))
        solve_fields(meta,s,catalog,name,closed,counts)
    (WEB/'faults.json').write_text(json.dumps(catalog,ensure_ascii=False,separators=(',',':')))
    meta.update({'status':'Present-day fault-bounded hierarchical geological packages and original-unit facies hypothesis',
        'substrate_model':{'policy':'substrate-policy.json','volume':'{scenario}/substrate-volume.bin','distance':'{scenario}/substrate-distance.bin','status':'{scenario}/substrate-status.bin','distance_dtype':'little-endian float32 meters; infinity for constraint-free components','labels':'original native unit IDs; no surficial-cover classes'},
        'faults':'Finite fault surfaces block interpolation; present-day surface labels; no coseismic or cumulative slip applied',
        'fault_model':{'count':len(catalog['faults']),'catalog':'faults.json','target_epoch':'present-day',
        'topology':'topology.json','section_constraints':'sections.json','signature':structural_signature()}})
    (WEB/'model.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    a=[np.fromfile(WEB/name/'volume.bin',np.uint8) for name in SCENARIOS]
    ((a[0]!=a[1])|(a[0]!=a[2])).astype(np.uint8).tofile(WEB/'disagreement.bin')

if __name__=='__main__':main()
