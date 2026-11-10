"""Infer fault attitudes from georeferenced section curves, preserving map traces.

Signed dip polarities are a mixture, NOT vectors averaged to an artificial
vertical fault. Analogue weights are modelling weights, not probabilities.
"""
import numpy as np

def curve_value(depth,knots,values):
    x=np.asarray(knots,float);y=np.asarray(values,float);d=np.asarray(depth,float)
    order=np.argsort(x);x=x[order];y=y[order]
    value=np.interp(d,x,y)
    lo=(y[1]-y[0])/(x[1]-x[0]);hi=(y[-1]-y[-2])/(x[-1]-x[-2])
    return np.where(d<x[0],y[0]+(d-x[0])*lo,np.where(d>x[-1],y[-1]+(d-x[-1])*hi,value))

def nearest_foot(trace,point):
    trace=np.array(trace,float);best=None
    chain=np.r_[0,np.cumsum(np.linalg.norm(np.diff(trace[:,:2],axis=0),axis=1))]
    for i,(a,b) in enumerate(zip(trace[:-1],trace[1:])):
        v=b[:2]-a[:2];length=np.linalg.norm(v)
        if length<1e-6:continue
        t=np.clip((np.asarray(point[:2])-a[:2])@v/(length*length),0,1);foot=a+t*(b-a);distance=np.linalg.norm(np.asarray(point[:2])-foot[:2])
        if best is None or distance<best[0]:
            s=chain[i]+t*length
            # Smooth the local strike over 300m, without moving the original line.
            ab=np.array([[np.interp(np.clip(s+d,0,chain[-1]),chain,trace[:,axis]) for axis in range(2)] for d in [-150,150]])
            tangent=ab[1]-ab[0];tangent/=np.linalg.norm(tangent)
            best=(distance,foot,np.array([-tangent[1],tangent[0]]))
    return best

def weighted_quantile(values,weights,q):
    order=np.argsort(values);v=np.asarray(values)[order];w=np.asarray(weights)[order]
    return float(np.interp(q*np.sum(w),np.cumsum(w)-w*.5,v))

def analogue_ensemble(normal,anchor,seeds):
    eligible=[]
    for seed in seeds:
        dist=np.linalg.norm(np.asarray(seed['anchor_xyz'][:2])-anchor[:2]);alignment=abs(np.dot(normal,seed['normal_xy']))
        if dist>20000 or alignment<np.cos(np.radians(35)):continue
        weight=np.exp(-.5*(dist/8000)**2)*alignment**8*seed.get('weight',1)
        polarity=1 if np.dot(normal,seed['dip_direction_xy'])>=0 else -1
        eligible.append((seed,weight,polarity,dist))
    if not eligible:return None
    dip=[s['dip_deg'] for s,w,p,d in eligible];weights=np.array([w for s,w,p,d in eligible])
    plus=sum(w for s,w,p,d in eligible if p==1);minus=sum(w for s,w,p,d in eligible if p==-1);sign=1 if plus>=minus else -1
    ambiguous=min(plus,minus)/max(plus+minus,1e-10)>.25
    angle=weighted_quantile(dip,weights,.5)
    # Sensitivity margin, not a confidence interval or a measured angle.
    low=max(15.,weighted_quantile(dip,weights,.2)-10);high=min(89.,weighted_quantile(dip,weights,.8)+10)
    def case(di,sgn):
        direction=normal*sgn
        return {'dip_deg':di,'dip_azimuth_deg':float(np.degrees(np.arctan2(direction[0],direction[1]))%360)}
    return {'reference':case(angle,sign),'shallow':case(low,sign),'deep':case(high,-sign if ambiguous else sign),
      'direction_ambiguous':bool(ambiguous),'positive_side_weight':float(plus/(plus+minus)),
      'basis':[{'source':s['id'],'distance_m':round(d,1),'weight':float(w),'dip_deg':s['dip_deg']} for s,w,p,d in eligible],
      'method':'spatial/strike analogue mixture, weighted dip quantiles; 10deg sensitivity margin; polarity modes kept separate, not averaged',
      'limitations':'Analogue transfer is an assumption. Weights are not calibrated probabilities. Deep case reverses dip side when direction is ambiguous.'}

def constrain(faults,sections):
    seeds=[]
    for fault in faults:
        if fault.get('layer')!='seamless' and not fault.get('structural_candidate'):continue
        controls=[]
        for section in sections:
            for line in section.get('fault_lines',[]):
                if line['fault_name']!=fault['name']:continue
                points=np.array([p['xyz'] for p in line['points']]);top=points[np.argmax(points[:,2])]
                feet=[nearest_foot(t,top) for t in fault['traces']];distance,anchor,normal=min(feet,key=lambda x:x[0])
                if distance>600:raise ValueError(f"Section fault/map association too far: {line['id']} ({distance:.0f}m)")
                depth=anchor[2]-points[:,2];offset=(points[:,:2]-anchor[:2])@normal
                delta_depth=np.diff(depth);delta_offset=np.diff(offset)
                slope=float(delta_depth@delta_offset/(delta_depth@delta_depth))
                di=float(np.degrees(np.arctan2(1,abs(slope))));direction=normal*(1 if slope>=0 else -1)
                control={'id':line['id'],'section_id':section['id'],'source_sha256':section['source_sha256'],'points':line['points'],'anchor_xyz':anchor.tolist(),'normal_xy':normal.tolist(),
                 'depth_m':depth.tolist(),'normal_offset_m':offset.tolist(),'dip_deg':di,'dip_direction_xy':direction.tolist(),
                 'map_registration_residual_m':float(curve_value(0,depth,offset)),'sigma_m':line['sigma_m'],
                 'method':'section curve projected onto local map-trace normal; map trace fixed; normal offsets registered at depth zero; local along-strike transfer'}
                surface_xy=np.array([float(curve_value(0,depth,points[:,axis])) for axis in range(2)])
                shift=surface_xy-anchor[:2]
                control['map_registration_shift_xy_m']=shift.tolist();control['map_registration_distance_m']=float(np.linalg.norm(shift))
                control['registration_note']='Whole horizontal source-curve/200k-map tie, including along-strike offset at a mapped trace endpoint. No map vertices are moved. Raw and registered errors are separate.'
                controls.append(control);seeds.append(control)
        fault['section_attitudes']=controls
        if controls:
            representative=controls[0];direction=np.array(representative['dip_direction_xy']);dip=representative['dip_deg']
            fault.update({'attitude_kind':'interpreted_section_curve','supported_depth_m':float(max(max(c['depth_m']) for c in controls)),'profile_depth_dip':[[0,dip],[4000,dip]],'dip_azimuth_deg':float(np.degrees(np.arctan2(direction[0],direction[1]))%360)})
        else:
            profile=fault.get('profile_depth_dip');kind=fault['attitude_kind']
            if profile and kind.startswith('published'):
                # These records encode a published DIRECTION with a numerical
                # placeholder, not a measured numerical dip. Do not seed other
                # faults with that placeholder as if it were an observation.
                fault['published_direction_constraint']={'azimuth_deg':fault['dip_azimuth_deg'],'source':fault.get('attitude_source'),'notes':fault['notes']}
                fault['legacy_angle_prior_deg']=profile[0][1]
                fault['attitude_kind']='unresolved_orientation'
    # A REGIONAL high-angle prior, not a fabricated measured point. Its centre
    # is just the weighting kernel centre of the Kitan-Naruto coverage region.
    # 75deg is the midpoint of a 60..90 high-angle sensitivity range. It is not
    # the measured dip of every strand. Individual mapped strands stay separate.
    from prepare import FWD
    centre=[*FWD.transform(134.835,34.205),0.]
    seeds.append({'id':'HERP2017-MTL-shallow-regional-prior','anchor_xyz':centre,'normal_xy':[0.,1.],'dip_direction_xy':[0.,1.],'dip_deg':75.,'weight':.25,'scope':'regional prior coverage centre, NOT an observation location','source':'HERP 2017 MTL evaluation: high angle near seabed; deep 30deg not transferred to shallow branches'})
    for fault in faults:
        if fault.get('layer')!='seamless' and not fault.get('structural_candidate'):continue
        # Every formerly-unknown attitude is inferred from eligible evidence or
        # remains unresolved WITHOUT constructing a vertical plane.
        if fault['attitude_kind'] not in ('unknown_vertical_prior','unresolved_orientation'):continue
        trace=max(fault['traces'],key=len);anchor=np.array(trace[len(trace)//2]);_,_,normal=nearest_foot(trace,anchor)
        ensemble=analogue_ensemble(normal,anchor,seeds)
        if ensemble and fault.get('published_direction_constraint'):
            az=np.radians(fault['published_direction_constraint']['azimuth_deg']);expected=np.array([np.sin(az),np.cos(az)])
            direction=normal*(1 if normal@expected>=0 else -1)
            for case in ['reference','shallow','deep']:ensemble[case]['dip_azimuth_deg']=float(np.degrees(np.arctan2(direction[0],direction[1]))%360)
            ensemble['direction_ambiguous']=False;ensemble['direction_basis']='published direction; numerical angle inferred from section evidence'
        # Resolve dip side only where kinematics + fault type permit it.
        for obs in fault.get('gsi_kinematic_constraints',[]):
            if ensemble is None:continue
            if 'dip_side_azimuth_deg' in obs:
                az=np.radians(obs['dip_side_azimuth_deg']);expected=np.array([np.sin(az),np.cos(az)])
                sg=1 if normal@expected>=0 else -1;direction=normal*sg
                for case in ['reference','shallow','deep']:ensemble[case]['dip_azimuth_deg']=float(np.degrees(np.arctan2(direction[0],direction[1]))%360)
                ensemble['direction_ambiguous']=False;ensemble['gsi_direction_basis']=obs['id']
            else:
                # A downthrow side alone permits normal AND reverse solutions.
                ensemble['direction_ambiguous']=True
                ensemble['deep']['dip_azimuth_deg']=(ensemble['reference']['dip_azimuth_deg']+180)%360
                ensemble['gsi_motion_basis']=obs['id'];ensemble['kinematic_alternatives']=obs['dip_sense_alternatives']
        fault['orientation_ensemble']=ensemble;fault['profile_depth_dip']=None
        if ensemble:
            fault['attitude_kind']='spatial_strike_analogue';fault['used_for_model']=True
            fault['notes']='近隣の断面姿勢・公表姿勢と走向から推定した傾斜アンサンブル。実測値ではない。方向が曖昧な場合は両側の傾斜を別シナリオに保持。'
        else:
            fault['attitude_kind']='unresolved_orientation';fault['used_for_model']=False
            fault['notes']='適用可能な姿勢制約がないため地下の単一面を作らない。地表トレースは保持。鉛直とは仮定しない。'
    return faults

def local_offset(fault,point,depth,normal,scenario,prior):
    controls=fault.get('section_attitudes',[])
    if not controls:return prior
    distances=np.array([np.linalg.norm(np.asarray(c['anchor_xyz'][:2])-point[:2]) for c in controls]);weights=1/(distances**2+1)
    values=[]
    for c in controls:
        value=curve_value(depth,c['depth_m'],c['normal_offset_m'])-curve_value(0,c['depth_m'],c['normal_offset_m'])
        values.append(float(value)*np.dot(c['normal_xy'],normal))
    fitted=float(np.dot(weights,values)/weights.sum());influence=float(np.exp(-(distances.min()/3000)**2))
    return (1-influence)*prior+influence*fitted
