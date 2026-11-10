"""Resolve duplicate cartographic traces without changing structural constraints.

Original vectors remain in faults.json. Matching uses direction and proximity,
not proximity alone. An active-segment overview with explicit model_aliases is
replaced by those separate strands, never by a single merged fault plane.
"""
import hashlib,json,math,re
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree

ROOT=Path(__file__).resolve().parents[1]

def named(f):
    return f['layer']=='seamless' and not re.search(r'\d{4}-\d+$',f['name'])

def build(catalog):
    groups={};samples=[];directions=[];owners=[];sample_layers=[];audit=[]
    faults=catalog['faults'];lookup={f['id']:f for f in faults}
    # Original geological mapping is the detailed trace; regional overlays fill gaps.
    ordered=sorted(faults,key=lambda f:({'seamless':0,'active':1,'major':2}[f['layer']],f['id']))
    # Explicit individual marine strands outrank their aggregate overview.
    strands={a for f in faults for a in f.get('model_aliases',[])}
    ordered.sort(key=lambda f:0 if f['layer']=='seamless' else 1 if f['id'] in strands else 2 if f['layer']=='active' else 3)
    tree=None
    for f in ordered:
        if f.get('model_aliases'):
            audit.append({'source_id':f['id'],'reason':'aggregate_replaced_by_individual_strands','replacements':f['model_aliases']});continue
        key={'active:191-01:381':'志筑断層','active:287-01:512':'先山断層'}.get(f['id'], f['name'] if named(f) else f['id'])
        group=groups.setdefault(key,{'id':f['id'],'name':('中央構造線（紀淡・鳴門海峡）・枝'+str(sorted(strands).index(f['id'])+1) if f['id'] in strands else f['name']),'layer':'unified','color':'#111111','traces':[],'trace_styles':[], 'model_aliases':[], 'source_ids':[], 'used_for_model':False})
        group['source_ids'].append(f['id']);group['model_aliases'].append(f['id']);group['used_for_model']|=f.get('used_for_model',False)
        additions=[]
        for ti,trace in enumerate(f['traces']):
            arr=np.array(trace,float);kept=[];run=[];matched={};removed=0;total=0
            for i,(a,b) in enumerate(zip(arr[:-1],arr[1:])):
                delta=b[:2]-a[:2];length=np.linalg.norm(delta)
                if length<1e-6:continue
                direction=delta/length
                # Subdivide only coarse overlapping segments; fine mapping vertices stay intact.
                count=max(1,math.ceil(length/100)) if f['layer']!='seamless' else 1
                for j in range(count):
                    p=a+(b-a)*(j/count);q=a+(b-a)*((j+1)/count);mid=(p[:2]+q[:2])/2
                    match=None
                    if tree is not None and f['layer']!='seamless':
                        inds=tree.query_ball_point(mid,400)
                        choices=[k for k in inds if sample_layers[k] != f["layer"] and abs(float(np.dot(direction,directions[k])))>=math.cos(math.radians(25))]
                        if choices:
                            k=min(choices,key=lambda k:np.linalg.norm(mid-samples[k]));match=owners[k]
                    total+=length/count
                    if match is not None:
                        removed+=length/count;matched[match]=matched.get(match,0)+length/count
                        if len(run)>1:kept.append(run)
                        run=[]
                    else:
                        if not run:run=[p.tolist()]
                        run.append(q.tolist())
            if len(run)>1:kept.append(run)
            if f['layer']=='seamless':kept=[trace]  # original high-detail vertices, no resampling
            for target,overlap in matched.items():
                g=groups[target]
                if f['id'] not in g['source_ids']:g['source_ids'].append(f['id'])
                # Selection aliases preserve underlying separate structural surfaces.
                if f['id'] not in g['model_aliases']:g['model_aliases'].append(f['id'])
            group['traces'].extend(kept)
            group['trace_styles'].extend([{'dashed':bool(f.get('dashed')),'source_id':f['id'],'source_trace':ti} for t in kept])
            audit.append({'source_id':f['id'],'trace':ti,'retained_length_m':round(total-removed,2),'suppressed_length_m':round(removed,2),'replaced_by':list(matched)})
            for t in kept:
                for a,b in zip(t[:-1],t[1:]):
                    a=np.array(a[:2]);b=np.array(b[:2]);d=b-a;length=np.linalg.norm(d)
                    if length<1e-6:continue
                    for v in np.linspace(0,1,max(2,math.ceil(length/100)+1)):
                        additions.append((a+v*d,d/length,key,f["layer"]))
        for p,d,k,layer in additions:samples.append(p);directions.append(d);owners.append(k);sample_layers.append(layer)
        if additions:tree=cKDTree(samples)
    result=[g for g in groups.values() if g['traces']]
    for g in result:
        g['model_aliases']=list(dict.fromkeys(g['model_aliases']))
        g['used_for_model']=any(lookup[a].get('used_for_model') for a in g['model_aliases'])
        g['dashed']=all(s['dashed'] for s in g['trace_styles'])
    return {'faults':result,'audit':audit,'policy':{'matching_distance_m':400,'maximum_angle_difference_deg':25,'coarse_segment_sampling_m':100,'meaning':'Cartographic duplicate suppression, not a geological correlation or a change to fault planes. Distinct original detailed branches remain separate.'}}

def main():
    source=ROOT/'web/data/faults.json';raw=source.read_bytes();out=build(json.loads(raw));out['source_sha256']=hashlib.sha256(raw).hexdigest()
    (ROOT/'web/data/fault-display.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')))
    print('unified faults',len(out['faults']),'suppressed km',round(sum(a.get('suppressed_length_m',0) for a in out['audit'])/1000,1))
if __name__=='__main__':main()
