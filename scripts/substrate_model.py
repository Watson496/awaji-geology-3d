"""Infer substrate independently of the younger surficial-cover observations.

Covered ground is NOT a negative observation of every older unit. Its substrate
boundary is free. Outcrop labels and registered interpreted sections anchor
nonnegative fields on the same finite-fault graph as the structural model.
Normalized evidence scores are heuristics, never calibrated probabilities.
"""
import json
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import cg,LinearOperator
from scipy.sparse.csgraph import dijkstra
from prepare import ROOT,OUT
from model_domain import native_prior
from structure import ordered_packages
from surficial_cover import policy

CONFIG=ROOT/'data/structure/substrate-policy.json'

def infer_fields(offdiag,degree,fixed,truth,unit_ids,priors,picks,screen=.02):
    """One-hot outcrop evidence; no artificial negative boundary on covered ground."""
    n=len(degree);free=~fixed
    penalty=np.zeros(n,np.float32)
    for pick,j,weight in picks:penalty[j]+=weight
    full=offdiag+sparse.diags(degree+screen+penalty)
    free_ids=np.flatnonzero(free);fixed_ids=np.flatnonzero(fixed)
    system=full[free_ids][:,free_ids].tocsr();coupling=full[free_ids][:,fixed_ids].tocsr()
    inverse_diagonal=1/system.diagonal()
    pre=LinearOperator(system.shape,matvec=lambda x:x*inverse_diagonal,dtype=np.float32)
    fields={};audit=[]
    for uid in unit_ids:
        boundary=(truth[fixed_ids]==uid).astype(np.float32)
        evidence=np.zeros(n,np.float32)
        for allowed,j,weight in picks:
            if uid in allowed:evidence[j]+=weight/len(allowed)
        prior=priors[uid];rhs=(screen*prior+evidence)[free]-coupling@boundary;iterations=[0]
        def tick(_):iterations[0]+=1
        solution,status=cg(system,rhs,x0=prior[free],M=pre,rtol=2e-4,atol=1e-6,maxiter=900,callback=tick)
        if status:raise RuntimeError(f'Substrate field {uid} did not converge ({status})')
        score=np.empty(n,np.float32);score[free]=np.clip(solution,0,1);score[fixed_ids]=boundary
        fields[uid]=score
        residual=float(np.linalg.norm(system@solution-rhs)/max(np.linalg.norm(rhs),1e-9))
        audit.append({'unit_id':uid,'iterations':iterations[0],'relative_residual':residual})
    return fields,audit

def source_distances(offdiag,fixed,picks,scale):
    """Shortest physical path to actual constraints; cannot cross closed faults."""
    sources=fixed.copy()
    for _,j,_ in picks:sources[j]=True
    if not sources.any():return np.full(len(fixed),np.inf)
    graph=offdiag.copy();graph.data=scale/np.sqrt(-graph.data)
    return dijkstra(graph,directed=False,indices=np.flatnonzero(sources),min_only=True)

def gate_native_fields(fields,offdiag,fixed,truth,picks,scale,limit):
    """A source of some OTHER unit cannot license a facies introduced by a prior."""
    distances={}
    for uid in fields:
        matching=[p for p in picks if uid in p[0]]
        d=source_distances(offdiag,fixed&(truth==uid),matching,scale).astype(np.float32)
        fields[uid]=np.where(d<=limit,fields[uid],0)
        distances[uid]=d
    return fields,distances

def infer(meta,s,scenario,rock,top,offdiag,degree,mapped_picks,closed,marine_grid,z):
    from structure import topology
    settings=json.loads(CONFIG.read_text());cover_symbols=set(policy()['units'])
    packages,mapping=topology(meta);base_packages=[p for p in packages if not any(k in cover_symbols for k in p['symbols'])]
    units=[u for u in meta['units'] if u['kind']!='unknown' and u['key'] not in cover_symbols]
    unit_ids=[u['id'] for u in units];by_symbol={u['key']:u['id'] for u in units}
    truth_grid=np.broadcast_to(s['surface'][...,None],rock.shape);truth=truth_grid[rock]
    fixed=(top&~np.isin(s['surface'],[u['id'] for u in meta['units'] if u['key'] in cover_symbols])[...,None])[rock]
    picks=[]
    for p,j,weight,_ in mapped_picks:
        allowed=[by_symbol[k] for k in p['allowed_symbols'] if k in by_symbol]
        if allowed:picks.append((allowed,j,weight))
    priors={}
    for u in units:
        cache=np.load(OUT/'fields'/scenario/f'{u["key"]}.npz')
        priors[u['id']]=np.maximum(native_prior(cache,rock,z,s),0)
    total=sum(priors.values());positive=total>0
    for uid in priors:priors[uid]=np.divide(priors[uid],total,out=np.zeros_like(total),where=positive)
    fields,solver_audit=infer_fields(offdiag,degree,fixed,truth,unit_ids,priors,picks,settings['screening_weight'])
    max_distance=settings['maximum_transfer_distance_m'][scenario]
    fields,native_distances=gate_native_fields(fields,offdiag,fixed,truth,picks,min(meta['spacing_m']),max_distance)
    distances=np.min(np.stack(list(native_distances.values())),axis=0)
    selected_distances=distances.copy()
    reachable=np.isfinite(distances)&(distances<=max_distance)
    package_scores=np.zeros((*rock.shape,len(base_packages)),np.float32);masses=[]
    for gi,p in enumerate(base_packages):
        mass=sum(fields[uid] for uid in p['unit_ids'])
        # Same regional acoustic hypothesis; does not identify a granite facies.
        mass=mass*np.exp(.35*marine_grid[rock]*(1 if gi<2 else -1))
        masses.append(mass);package_scores[...,gi][rock]=mass
    # Surface age is constrained ONLY where the older substrate is exposed.
    surface_package=mapping[s['surface']].copy()
    surface_package[np.isin(s['surface'],[u['id'] for u in meta['units'] if u['key'] in cover_symbols])]=-1
    parent=ordered_packages(package_scores,rock,closed[2],surface_package)
    total_mass=sum(masses);chosen=np.full(len(truth),meta['unknown_id'],np.uint8)
    margin=np.zeros(len(truth),np.float32);strength=np.zeros(len(truth),np.float32)
    for gi,p in enumerate(base_packages):
        ids=p['unit_ids'];a=np.stack([fields[uid] for uid in ids]);order=np.argsort(a,axis=0)
        best=np.take_along_axis(a,order[-1:,:],axis=0)[0]
        second=np.take_along_axis(a,order[-2:-1,:],axis=0)[0] if len(ids)>1 else np.zeros_like(best)
        raw_mass=a.sum(axis=0)
        native_strength=np.divide(best,raw_mass,out=np.zeros_like(best),where=raw_mass>1e-12)
        native_margin=np.divide(best-second,raw_mass,out=np.zeros_like(best),where=raw_mass>1e-12)
        package_strength=np.divide(masses[gi],total_mass,out=np.zeros_like(best),where=total_mass>1e-12)
        candidate=(parent[rock]==gi)
        accepted=candidate&reachable&(total_mass>1e-8)&(package_strength>=settings['minimum_package_share'])&(native_strength>=settings['minimum_native_share'])&(native_margin>=settings['minimum_native_margin'])
        chosen[accepted]=np.array(ids,np.uint8)[order[-1,accepted]]
        native_distance=np.stack([native_distances[uid] for uid in ids])
        selected_distances[accepted]=np.take_along_axis(native_distance,order[-1:,:],axis=0)[0,accepted]
        margin[candidate]=native_margin[candidate];strength[candidate]=package_strength[candidate]
    chosen[fixed]=truth[fixed]
    status=np.zeros(len(truth),np.uint8);status[np.isfinite(distances)]=1;status[reachable]=2
    status[chosen!=meta['unknown_id']]=3;status[fixed]=4
    base=np.zeros(rock.shape,np.uint8);base[rock]=chosen
    distance_grid=np.full(rock.shape,np.inf,np.float32);distance_grid[rock]=selected_distances
    status_grid=np.zeros(rock.shape,np.uint8);status_grid[rock]=status
    folder=ROOT/'web/data'/scenario
    base.tofile(folder/'substrate-volume.bin');distance_grid.tofile(folder/'substrate-distance.bin');status_grid.tofile(folder/'substrate-status.bin')
    report={'method':'Separate substrate on the finite-fault graph: covered ground is unobserved, one-hot older outcrops and interpreted section constraints, positive normalized weak GemPy priors, ordered older packages, then surficial-cover overlay.',
        'policy':'substrate-policy.json','covered_surface_is_negative_evidence':False,'maximum_transfer_distance_m':max_distance,'normalized_scores_are_probabilities':False,'distance_basis':'Matched native unit outcrops and interpreted section constraints; unrelated units do not license a label','outcrop_constraint_cells':int(fixed.sum()),'interpreted_section_constraint_count':len(picks),'cells_in_constraint_free_components':int((~np.isfinite(distances)).sum()),'accepted_cells':int((chosen!=meta['unknown_id']).sum()),'rejected_for_distance_or_connectivity':int((~reachable).sum()),'solver_audit':solver_audit,
        'status_codes':{'0':'outside domain or no constraint in connected fault block','1':'beyond assumed transfer distance','2':'within range but competing or weak evidence','3':'accepted structural extrapolation, not observation','4':'mapped substrate outcrop'},
        'limitations':['Transfer ranges and score thresholds are modeling assumptions, not calibrated confidence.','A covered location has no direct substrate observation. No boreholes have been added.','No crossing a closed fault edge; paths around finite fault tips remain possible.']}
    return base,parent,report,status_grid

def compose(existing,existing_packages,substrate,substrate_packages,surface,meta):
    """Retain the finite cover; replace its entire underlying column coherently."""
    ids=[u['id'] for u in meta['units'] if u['key'] in policy()['units']]
    columns=np.isin(surface,ids);cover=np.isin(existing,ids)
    region=columns[...,None]&(existing>0)&~cover
    volume=existing.copy();parents=existing_packages.copy()
    volume[region]=substrate[region];parents[region]=substrate_packages[region]
    return volume,parents,region
