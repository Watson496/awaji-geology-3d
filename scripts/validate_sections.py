"""適合に使った原断面の再現を検査する。独立した地質精度の評価ではない。"""
import json
import numpy as np
from scipy.spatial import cKDTree
from prepare import ROOT,OUT
from fault_model import fault_triangles

def horizontal_distance(triangles,point):
    point=np.asarray(point);nearest=np.inf
    for tri in triangles:
        if point[2]<tri[:,2].min()-1e-6 or point[2]>tri[:,2].max()+1e-6:continue
        hits=[]
        for a,b in zip(tri,np.roll(tri,-1,axis=0)):
            da,db=a[2]-point[2],b[2]-point[2]
            if da*db>0 or abs(da-db)<1e-9:continue
            hits.append(a+(b-a)*da/(da-db))
        if len(hits)<2:continue
        a,b=np.array(hits[:2])[:,:2];v=b-a;t=np.clip((point[:2]-a)@v/max(v@v,1e-10),0,1)
        nearest=min(nearest,float(np.linalg.norm(point[:2]-a-t*v)))
    return None if not np.isfinite(nearest) else nearest

def main():
 web=ROOT/'web/data';m=json.loads((web/'model.json').read_text());s=np.load(OUT/'surface.npz');sections=json.loads((web/'sections.json').read_text())['sections'];faults=json.loads((web/'faults.json').read_text())['faults'];dz=(m['zmax']-m['zmin'])/m['nz'];spacing=np.r_[m['spacing_m'],dz];origin=np.r_[s['xs'][0],s['ys'][0],m['zmin']+dz/2]
 symbol={u['key']:u['id'] for u in m['units']}
 for case in m['scenarios']:
  volume=np.fromfile(web/case/'volume.bin',np.uint8).reshape(*m['shape'],m['nz']);report=[];mesh_cache={}
  for section in sections:
   boundaries=[]
   for p in section['picks']:
    if p['kind']!='interpreted_section_boundary':continue
    ids=[symbol[k] for k in p['allowed_symbols']];faces=[]
    for axis in range(3):
     a=[slice(None)]*3;b=a.copy();a[axis]=slice(None,-1);b[axis]=slice(1,None);a=tuple(a);b=tuple(b)
     hit=(volume[a]!=volume[b])&np.isin(volume[a],ids)&np.isin(volume[b],ids)
     ijk=np.argwhere(hit).astype(float);ijk[:,axis]+=.5;faces.extend((origin+ijk*spacing).tolist())
    distance=float(cKDTree(faces).query(p['xyz'])[0]) if faces else None
    boundaries.append({'id':p['id'],'distance_to_matching_model_interface_m':distance,'reading_sigma_m':p['sigma_m'],'tolerance_m':250,'within_tolerance':distance is not None and distance<=250})
   fault_fit=[]
   for p in section['fault_picks']:
    f=next(f for f in faults if f['name']==p['fault_name'])
    if f['id'] not in mesh_cache:mesh_cache[f['id']]=fault_triangles(f,m['zmin'],case)
    mesh=mesh_cache[f['id']];control=next(a for a in f['section_attitudes'] if a['id']==p['fault_line_id'])
    point=np.array(p['xyz']);registered=point.copy();registered[:2]-=np.array(control['map_registration_shift_xy_m'])
    valid=point[2]>=m['zmin'] and point[2]<=control['anchor_xyz'][2]+1e-6
    status='in_domain' if valid else ('below computational cap' if point[2]<m['zmin'] else 'above associated current DEM trace')
    fault_fit.append({'fault_name':p['fault_name'],'pixel':p['pixel'],'horizontal_distance_to_fault_surface_m':horizontal_distance(mesh,point),'map_registration_offset_m':control['map_registration_residual_m'],'registered_curve_distance_m':horizontal_distance(mesh,registered) if valid else None,'model_domain_status':status,'map_registration_distance_m':control['map_registration_distance_m'],'reading_sigma_m':p['sigma_m'],'source_dip_deg':control['dip_deg'],'usage':'source curve reproduction after registered trace offset, not independent accuracy','used_for_dip_fit':True})
   report.append({'section_id':section['id'],'usage':'constraint reproduction, not independent validation','boundary_fit':boundaries,'fault_intersections':fault_fit})
  (web/case/'section-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
  path=web/case/'metrics.json';metrics=json.loads(path.read_text());metrics['section_reproduction']=report;path.write_text(json.dumps(metrics,ensure_ascii=False,indent=2))
  errors=[p['registered_curve_distance_m'] for r in report for p in r['fault_intersections'] if p['registered_curve_distance_m'] is not None]
  print(case,'boundary distances',[round(p['distance_to_matching_model_interface_m'],1) if p['distance_to_matching_model_interface_m'] is not None else None for r in report for p in r['boundary_fit']],'registered fault curve median/max',round(float(np.median(errors)),1),round(max(errors),1),flush=True)
if __name__=='__main__':main()
