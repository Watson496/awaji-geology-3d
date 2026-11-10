"""Auxiliary basin/basement envelope on land AND the surrounding marine domain.

Marine facies stay unclassified. This envelope constrains onshore package choice
through the same finite-fault barrier operator. Sea-level is the computational
ceiling offshore, NOT a fabricated measured seabed.
"""
import json
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import cg,LinearOperator
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes
from prepare import ROOT,OUT
from prepare_marine import build
from structure import topology

def _envelope(meta,s,scenario,catalog):
 from fault_model import barriers,build_system
 marine=build();nx,ny=meta['shape'];nz=meta['nz'];dz=(meta['zmax']-meta['zmin'])/nz
 z=meta['zmin']+(np.arange(nz)+.5)*dz;spacing=np.r_[meta['spacing_m'],dz];origin=np.r_[s['xs'][0],s['ys'][0],z[0]]
 ceiling=np.where(s['island'],s['dem'],0.)
 domain=z[None,None,:]-dz/2<ceiling[...,None]
 closed,counts=barriers(domain.shape,origin,spacing,catalog['faults'],meta['zmin'],scenario,domain)
 off,degree,index=build_system(domain,closed,spacing);size=int(domain.sum());coords=np.stack(np.meshgrid(s['xs'],s['ys'],z,indexing='ij'),-1)[domain]
 fixed=np.zeros(size,bool);target=np.zeros(size,np.float32)
 ii,jj=np.nonzero(s['island']);kk=domain.sum(axis=2)[ii,jj]-1;ids=index[ii,jj,kk];fixed[ids]=True
 _,packages=topology(meta);target[ids]=np.where(packages[s['surface'][ii,jj]]<2,1.,-1.)
 tree=cKDTree(coords);fit=[];shift={'reference':0,'shallow':300,'deep':-300}[scenario]
 # Points on a contour are correlated; all carry the same positional/depth
 # uncertainty and are shifted together, not treated as independent precision.
 for pick in marine['picks']:
  p=np.array(pick['xyz']);p[2]+=shift
  for dzpick,value in [(500,-1),(0,0),(-500,1)]:
   q=p+[0,0,dzpick];distance,j=tree.query(q)
   if distance>350:raise ValueError('Marine constraint outside computational domain')
   if fixed[j] and target[j]!=value:raise ValueError('Conflicting marine constraints')
   fixed[j]=True;target[j]=value
  fit.append({'id':pick['id'],'xyz':p.tolist(),'kind':pick['kind'],'usage':'fitting constraint, not independent validation'})
 free=np.flatnonzero(~fixed);known=np.flatnonzero(fixed);full=off+sparse.diags(degree+.005);a=full[free][:,free].tocsr();rhs=-full[free][:,known]@target[known]
 inv=1/a.diagonal();m=LinearOperator(a.shape,matvec=lambda v:inv*v,dtype=np.float32)
 x,status=cg(a,rhs,M=m,rtol=3e-4,atol=1e-5,maxiter=1000)
 if status:raise RuntimeError(f'{scenario}: marine basement envelope failed to converge')
 values=target.copy();values[free]=x;grid=np.zeros(domain.shape,np.float32);grid[domain]=values
 folder=ROOT/'web/data'/scenario;grid.tofile(folder/'basin-envelope.bin')
 # Display the inferred roof only near the digitized contours. This is a
 # structural surface, not a new geological legend unit.
 xx,yy=np.meshgrid(s['xs'],s['ys'],indexing='ij');dist=cKDTree(np.array([p['xyz'][:2] for p in marine['picks']])).query(np.c_[xx.ravel(),yy.ravel()])[0].reshape(nx,ny)
 display=domain&(~s['island'])[...,None]&(dist<4000)[...,None]
 if np.any(grid[display]<0) and np.any(grid[display]>0):
  v,f,_,_=marching_cubes(grid,0,mask=display,allow_degenerate=False);world=origin+v*spacing
  (folder/'marine-basement.json').write_text(json.dumps({'positions':world.round(2).tolist(),'indices':f.tolist(),'status':'Interpolated acoustic basement roof, limited to 4km from digitized evidence; not a lithology map'},separators=(',',':')))
 return grid,{'domain':'land plus surrounding sea down to -3000m; offshore computational ceiling 0m, seabed not measured','fit':fit,'native_marine_lithology':'unclassified','correlation':marine['correlation'],'relative_residual':float(np.linalg.norm(a@x-rhs)/np.linalg.norm(rhs))}


def envelope(meta,s,scenario,catalog):
 from scipy.ndimage import map_coordinates
 deep=dict(meta,zmin=-3000.,zmax=700.,nz=52)
 grid,audit=_envelope(deep,s,scenario,catalog)
 nx,ny=meta['shape'];z=meta['zmin']+(np.arange(meta['nz'])+.5)*(meta['zmax']-meta['zmin'])/meta['nz']
 i,j,k=np.meshgrid(np.arange(nx),np.arange(ny),np.arange(meta['nz']),indexing='ij');q=(z[k]+3000)/(3700/52)-.5
 shallow=map_coordinates(grid,[i,j,q],order=1,mode='nearest',prefilter=False).astype(np.float32)
 shallow.tofile(ROOT/'web/data'/scenario/'basin-envelope.bin')
 audit['land_lithology_domain']='separate -500m computational cap; deep marine acoustic boundary does not justify deeper land lithology'
 return shallow,audit
