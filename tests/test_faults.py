import sys,unittest,json
from pathlib import Path
import numpy as np
from scipy.sparse.linalg import spsolve
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from fault_model import intersection_mask,offset_at,barriers,build_system
from structure import ordered_packages,topology

class FaultGeometry(unittest.TestCase):
 def test_finite_triangle_crossing_not_infinite_plane(self):
  tri=np.array([[.5,0,0],[.5,2,0],[.5,0,2]])
  np.testing.assert_array_equal(intersection_mask(np.array([[0,.25,.25],[0,2,2],[0,-1,0]]),np.array([1,0,0]),tri),[True,False,False])
 def test_dipping_profile_northwards_with_depth(self):
  self.assertAlmostEqual(float(offset_at(1000,[[0,30],[4000,30]])),1000*np.sqrt(3),places=6)
  self.assertLess(float(offset_at(500,[[0,80],[4000,80]])),100)
 def test_barrier_really_decouples_interpolation(self):
  rock=np.ones((6,3,3),bool);closed=[np.zeros((5,3,3),bool),np.zeros((6,2,3),bool),np.zeros((6,3,2),bool)]
  closed[0][2]=True
  off,degree,idx=build_system(rock,closed,np.ones(3))
  from scipy import sparse
  a=off+sparse.diags(degree+.1);rhs=np.zeros(rock.sum());rhs[idx[0,1,1]]=1
  result=spsolve(a,rhs).reshape(rock.shape)
  self.assertGreater(result[2,1,1],0);np.testing.assert_allclose(result[3:],0,atol=1e-10)
 def test_joint_order_can_jump_only_at_fault(self):
  rock=np.ones((1,1,5),bool);scores=np.zeros((1,1,5,3),np.float32)
  scores[0,0,:,0]=[0,0,10,0,0];scores[0,0,:,2]=[10,10,0,10,10]
  closed=np.zeros((1,1,4),bool)
  result=ordered_packages(scores,rock,closed,np.array([[2]]))
  self.assertTrue(np.all(np.diff(result[0,0].astype(int))>=0))
  closed[0,0,1]=True
  result=ordered_packages(scores,rock,closed,np.array([[2]]))
  self.assertGreater(result[0,0,1],result[0,0,2])
 def test_same_age_facies_are_not_stratigraphic_layers(self):
  meta=json.loads((Path(__file__).resolve().parents[1]/'web/data/model.json').read_text())
  packages,mapping=topology(meta)
  izumi=next(p for p in packages if p['id']=='izumi')
  self.assertEqual(len(izumi['unit_ids']),4)
  self.assertEqual(len(set(mapping[izumi['unit_ids']])),1)

class GeneratedFaultModel(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.root=Path(__file__).resolve().parents[1];cls.meta=json.loads((cls.root/'web/data/model.json').read_text())
 def test_present_day_discontinuities_and_mtl_member_accounting(self):
  self.assertEqual(self.meta['fault_model']['target_epoch'],'present-day')
  for case in self.meta['scenarios']:
   report=json.loads((self.root/f'web/data/{case}/metrics.json').read_text())['fault_conditioning']
   self.assertFalse(report['coseismic_displacement_applied']);self.assertFalse(report['cumulative_displacement_applied'])
   faults=json.loads((self.root/'web/data/faults.json').read_text())['faults']
   members=[f['id'] for f in faults if f.get('zone_id')=='mtl-kitan-naruto']
   self.assertTrue(report['blocked_edges'])
   self.assertGreater(sum(report['blocked_edges'].values()),0)
   self.assertFalse(any(f['trace_kind']=='regional_endpoint_chord' for f in faults))
   self.assertTrue(report['topology']['shared_envelopes'])
 def test_parent_topology_is_ordered_except_at_fault_crossings(self):
  _,mapping=topology(self.meta);shape=(*self.meta['shape'],self.meta['nz'])
  for case in self.meta['scenarios']:
   packages=np.fromfile(self.root/f'web/data/{case}/structural-packages.bin',np.uint8).reshape(shape)
   volume=np.fromfile(self.root/f'web/data/{case}/volume.bin',np.uint8).reshape(shape)
   barriers=np.load(self.root/f'data/prepared/fault-barriers-{case}.npz')['axis2']
   connected=(packages[:,:,:-1]>0)&(packages[:,:,1:]>0)&~barriers
   self.assertTrue(np.all(packages[:,:,1:][connected]>=packages[:,:,:-1][connected]))
   known=(volume>0)&(volume!=self.meta['unknown_id'])
   np.testing.assert_array_equal(mapping[volume[known]],packages[known]-1)
 def test_interpreted_contact_reproduction_with_declared_resolution(self):
  for case in self.meta['scenarios']:
   reports=json.loads((self.root/f'web/data/{case}/section-validation.json').read_text())
   for report in reports:
    self.assertIn('not independent',report['usage'])
    for p in report['boundary_fit']:self.assertLessEqual(p['distance_to_matching_model_interface_m'],p['tolerance_m'])
 def test_marine_evidence_is_not_assigned_invented_lithology(self):
  marine=json.loads((self.root/'web/data/marine.json').read_text())
  self.assertEqual(len(marine['picks']),5)
  self.assertTrue(all(p['native_symbol'] is None for p in marine['picks']))
  for case in self.meta['scenarios']:
   m=json.loads((self.root/f'web/data/{case}/metrics.json').read_text())['fault_conditioning']['marine_structure']
   self.assertEqual(m['native_marine_lithology'],'unclassified');self.assertLess(m['relative_residual'],.001)

class OfficialFaultSources(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.root=Path(__file__).resolve().parents[1]
  cls.catalog=json.loads((cls.root/'web/data/faults.json').read_text())
 def test_only_original_source_geometry_is_published(self):
  faults=self.catalog['faults']
  self.assertEqual({f['layer'] for f in faults},{'seamless','active','major'})
  self.assertTrue(all(f['trace_kind'] in ('official_seamless_vector','official_geonavi_geojson') for f in faults))
  self.assertTrue(all(not f['used_for_model'] for f in faults if f['layer']=='active'))
  self.assertEqual(sum(f.get('structural_candidate',False) for f in faults),10)
  self.assertTrue(all(f['line_code'] in ('2','4','6') for f in faults if f['layer']=='seamless'))
 def test_seamless_vertices_match_original_shapefile(self):
  import io,zipfile,shapefile,shapely
  from shapely.geometry import shape
  from pyproj import Transformer
  from prepare import BOX
  readers={};transform=Transformer.from_crs(4612,32653,always_xy=True)
  for f in self.catalog['faults']:
   if f['layer']!='seamless':continue
   for trace,source in zip(f['traces'],f['source_records']):
    code=source['sheet']
    if code not in readers:
     z=zipfile.ZipFile(self.root/f'data/raw/seamless-{code}.zip')
     readers[code]=shapefile.Reader(shp=io.BytesIO(z.read(f'{code}_line.shp')),shx=io.BytesIO(z.read(f'{code}_line.shx')),dbf=io.BytesIO(z.read(f'{code}_line.dbf')),encoding='utf-8')
    geom=shape(readers[code].shape(source['record']).__geo_interface__).intersection(shapely.box(*BOX))
    parts=[geom] if geom.geom_type=='LineString' else list(geom.geoms)
    expected=np.array([transform.transform(*p) for p in parts[source['part']].coords])
    np.testing.assert_allclose(np.array(trace)[:,:2],expected,atol=1e-6,rtol=0)
 def test_land_cap_and_source_support_do_not_excise_inferred_bodies(self):
  from prepare import OUT
  meta=json.loads((self.root/'web/data/model.json').read_text());self.assertEqual(meta['zmin'],-500)
  source=np.load(OUT/'surface.npz');shape=(*meta['shape'],meta['nz'])
  support=np.fromfile(self.root/'web/data/section-support.bin',np.uint8).reshape(shape)
  z=meta['zmin']+(np.arange(meta['nz'])+.5)*(meta['zmax']-meta['zmin'])/meta['nz']
  rock=source['island'][...,None]&(z[None,None,:]-(meta['zmax']-meta['zmin'])/meta['nz']/2<source['dem'][...,None])
  top=np.zeros(shape,bool);i,j=np.nonzero(source['island']);top[i,j,rock.sum(axis=2)[i,j]-1]=True
  for case in meta['scenarios']:
   volume=np.fromfile(self.root/f'web/data/{case}/volume.bin',np.uint8).reshape(shape)
   extrapolated=rock&~top&(support==0)
   self.assertGreater(np.mean((volume[extrapolated]>0)&(volume[extrapolated]!=meta['unknown_id'])),.5)
   k=int(np.argmin(abs(z+300)))
   self.assertGreater(np.mean(volume[:,:,k][source['island']]!=meta['unknown_id']),.5)
  sections=json.loads((self.root/'web/data/sections.json').read_text())['sections']
  self.assertEqual(len(sections),6)
 def test_geonavi_vertices_match_the_original_geojson(self):
  import gzip,shapely
  from shapely.geometry import shape
  from prepare import BOX,FWD
  source={}
  for layer,name in [('active','af_segment'),('major','JPF_2024')]:
   raw=(self.root/f'data/raw/{name}.json').read_bytes()
   source[layer]=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)['features']
  for fault in self.catalog['faults']:
   if fault['layer'] not in source:continue
   original=source[fault['layer']][fault['source_records'][0]['feature']]
   geom=shape(original['geometry']).intersection(shapely.box(*BOX))
   lines=[geom] if geom.geom_type=='LineString' else list(geom.geoms)
   self.assertEqual(len(lines),len(fault['traces']))
   for line,trace in zip(lines,fault['traces']):
    expected=np.array([FWD.transform(*p[:2]) for p in line.coords]);np.testing.assert_allclose(np.array(trace)[:,:2],expected,atol=1e-6,rtol=0)
 def test_gsi_reference_covers_the_island(self):
  from PIL import Image
  m=json.loads((self.root/'web/data/model.json').read_text());s=np.load(self.root/'data/prepared/surface.npz');im=np.asarray(Image.open(self.root/'web/data/gsi-active-fault-map.png'))
  xmin,xmax,ymin,ymax=m['extent_xy'];xx,yy=np.meshgrid(s['xs'],s['ys'],indexing='ij')
  x=np.clip(((xx-xmin)/(xmax-xmin)*(im.shape[1]-1)).astype(int),0,im.shape[1]-1)
  y=np.clip(((ymax-yy)/(ymax-ymin)*(im.shape[0]-1)).astype(int),0,im.shape[0]-1)
  self.assertTrue(np.all(im[y,x,3][s['island']]>0))
 def test_body_meshes_do_not_extend_below_the_land_cap(self):
  for case in ['reference','shallow','deep']:
   entries=json.loads((self.root/f'web/data/{case}/meshes.json').read_text());data=(self.root/f'web/data/{case}/meshes.bin').read_bytes()
   for entry in entries:
    p=entry['positions'];xyz=np.frombuffer(data,dtype=p['type'],count=p['count'],offset=p['offset']).reshape(-1,3)
    self.assertGreaterEqual(xyz[:,1].min(),-.50001)

class AttitudeInference(unittest.TestCase):
 def test_opposite_dip_modes_do_not_average_to_vertical(self):
  from fault_attitudes import analogue_ensemble
  seeds=[{'id':str(s),'anchor_xyz':[s*100,0,0],'normal_xy':[0,1],'dip_direction_xy':[0,s],'dip_deg':60} for s in [-1,1]]
  result=analogue_ensemble(np.array([0,1]),np.zeros(3),seeds)
  self.assertAlmostEqual(result['reference']['dip_deg'],60);self.assertTrue(result['direction_ambiguous'])
  self.assertAlmostEqual((result['deep']['dip_azimuth_deg']-result['reference']['dip_azimuth_deg'])%360,180)
 def test_no_evidence_does_not_construct_a_vertical_face(self):
  from fault_attitudes import analogue_ensemble
  self.assertIsNone(analogue_ensemble(np.array([0,1]),np.zeros(3),[]))
 def test_direct_curves_retain_their_depth_offsets(self):
  from fault_attitudes import local_offset,curve_value
  fs=json.loads((Path(__file__).resolve().parents[1]/'web/data/faults.json').read_text())['faults']
  self.assertFalse(any(f['attitude_kind']=='unknown_vertical_prior' for f in fs))
  for f in fs:
   for c in f.get('section_attitudes',[]):
    for d,q in zip(c['depth_m'],c['normal_offset_m']):
     result=local_offset(f,np.array(c['anchor_xyz']),d,np.array(c['normal_xy']),'reference',0)
     expected=q-float(curve_value(0,c['depth_m'],c['normal_offset_m']))
     self.assertLess(abs(result-expected),1)
 def test_kunono_is_sloping_in_both_original_sections(self):
  fs=json.loads((Path(__file__).resolve().parents[1]/'web/data/faults.json').read_text())['faults'];f=next(x for x in fs if x['name']=='久野々断層')
  self.assertEqual({c['section_id'] for c in f['section_attitudes']},{'akashi-cde','akashi-fg'})
  self.assertTrue(all(50<c['dip_deg']<85 for c in f['section_attitudes']))
 def test_downthrow_is_not_automatically_dip_direction(self):
  data=json.loads((Path(__file__).resolve().parents[1]/'data/structure/gsi-fault-kinematics.json').read_text())
  for o in data['observations']:
   self.assertIsNone(o['dip_angle_deg'])
   if o['sense']=='reverse':self.assertAlmostEqual((o['dip_side_azimuth_deg']-o['downthrow_azimuth_deg'])%360,180)
   else:self.assertEqual(len(o['dip_sense_alternatives']),2)

 def test_visible_source_curves_match_registered_3d_geometry(self):
  root=Path(__file__).resolve().parents[1]
  for case in ['reference','shallow','deep']:
   reports=json.loads((root/f'web/data/{case}/section-validation.json').read_text())
   for r in reports:
    for p in r['fault_intersections']:
     if p['model_domain_status']!='in_domain':continue
     self.assertIsNotNone(p['registered_curve_distance_m'])
     self.assertLess(p['registered_curve_distance_m'],50)
