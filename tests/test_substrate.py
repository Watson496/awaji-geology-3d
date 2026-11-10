import json,sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from fault_model import build_system
from substrate_model import infer_fields,source_distances,gate_native_fields,compose,ROOT
from structure import ordered_packages

class SubstrateInferenceTests(unittest.TestCase):
 def test_exposed_units_continue_beneath_unobserved_cover(self):
  rock=np.ones((9,1,4),bool);closed=[np.zeros((8,1,4),bool),np.zeros((9,0,4),bool),np.zeros((9,1,3),bool)]
  off,degree,index=build_system(rock,closed,np.ones(3))
  fixed=np.zeros_like(rock);fixed[:2,:,3]=True;fixed[-2:,:,3]=True
  truth=np.zeros(rock.shape,np.uint8);truth[:2]=1;truth[-2:]=2;truth[2:7]=3
  fields,_=infer_fields(off,degree,fixed[rock],truth[rock],[1,2],{1:np.zeros(rock.sum(),np.float32),2:np.zeros(rock.sum(),np.float32)},[],.02)
  one=fields[1].reshape(rock.shape);two=fields[2].reshape(rock.shape)
  self.assertGreater(one[2,0,1],two[2,0,1]);self.assertGreater(two[6,0,1],one[6,0,1])
  self.assertGreater(one[4,0,1]+two[4,0,1],.2)
  # A true substrate outcrop is still an exact one-hot constraint.
  self.assertEqual(one[0,0,3],1);self.assertEqual(two[0,0,3],0)
 def test_closed_fault_is_not_a_shortcut_to_an_outcrop(self):
  rock=np.ones((6,1,3),bool);closed=[np.zeros((5,1,3),bool),np.zeros((6,0,3),bool),np.zeros((6,1,2),bool)];closed[0][2]=True
  off,degree,index=build_system(rock,closed,np.array([100.,100.,50.]))
  fixed=np.zeros(rock.shape,bool);fixed[0,0,2]=True
  distances=source_distances(off,fixed[rock],[],100).reshape(rock.shape)
  self.assertAlmostEqual(distances[1,0,1],150)
  self.assertTrue(np.all(np.isinf(distances[3:])))
 def test_a_prior_without_matching_native_evidence_cannot_fill_a_fault_block(self):
  rock=np.ones((4,1,2),bool);closed=[np.zeros((3,1,2),bool),np.zeros((4,0,2),bool),np.zeros((4,1,1),bool)];closed[0][1]=True
  off,_,_=build_system(rock,closed,np.ones(3))
  fixed=np.zeros(rock.shape,bool);fixed[0,0,1]=True;fixed[3,0,1]=True
  truth=np.zeros(rock.shape,np.uint8);truth[0]=1;truth[3]=2
  fields={1:np.ones(rock.sum(),np.float32),2:np.ones(rock.sum(),np.float32)}
  gated,dist=gate_native_fields(fields,off,fixed[rock],truth[rock],[],1,10)
  self.assertTrue(np.all(gated[1].reshape(rock.shape)[2:]==0))
  self.assertTrue(np.all(gated[2].reshape(rock.shape)[:2]==0))
 def test_cover_overlay_preserves_cover_and_exposed_structure(self):
  meta={'units':[{'id':1,'key':'K22_soss'},{'id':2,'key':'K21_pim_a'},{'id':3,'key':'H_sad'}]}
  old=np.array([[[9,9,3]],[[1,1,1]]],np.uint8);old_package=np.array([[[0,0,7]],[[1,1,1]]],np.uint8)
  base=np.full(old.shape,2,np.uint8);parents=np.zeros(old.shape,np.uint8)
  result,p,region=compose(old,old_package,base,parents,np.array([[3],[1]]),meta)
  np.testing.assert_array_equal(result[0,0],[2,2,3]);np.testing.assert_array_equal(result[1,0],[1,1,1])
  self.assertEqual(p[0,0,2],7);self.assertEqual(region.sum(),2)
 def test_unobserved_surface_does_not_force_a_substrate_age(self):
  rock=np.ones((1,1,3),bool);scores=np.zeros((1,1,3,3),np.float32);scores[...,1]=10
  result=ordered_packages(scores,rock,np.zeros((1,1,2),bool),np.array([[-1]]))
  np.testing.assert_array_equal(result,1)

class GeneratedSubstrate(unittest.TestCase):
 def test_cover_is_not_used_as_negative_substrate_boundary(self):
  m=json.loads((ROOT/'web/data/model.json').read_text())
  for case in m['scenarios']:
   report=json.loads((ROOT/f'web/data/{case}/metrics.json').read_text())['fault_conditioning']['substrate']
   self.assertFalse(report['covered_surface_is_negative_evidence']);self.assertFalse(report['normalized_scores_are_probabilities'])
   self.assertGreater(report['outcrop_constraint_cells'],0)
   self.assertGreater(report['interpreted_section_constraint_count'],0)
 def test_accepted_substrate_requires_a_nearby_connected_constraint(self):
  m=json.loads((ROOT/'web/data/model.json').read_text());shape=(*m['shape'],m['nz'])
  s=np.load(ROOT/'data/prepared/surface.npz');cover=json.loads((ROOT/'data/structure/surficial-cover.json').read_text())['units'];ids=[u['id'] for u in m['units'] if u['key'] in cover]
  for case in m['scenarios']:
   base=np.fromfile(ROOT/f'web/data/{case}/substrate-volume.bin',np.uint8).reshape(shape)
   dist=np.fromfile(ROOT/f'web/data/{case}/substrate-distance.bin',np.float32).reshape(shape)
   status=np.fromfile(ROOT/f'web/data/{case}/substrate-status.bin',np.uint8).reshape(shape)
   report=json.loads((ROOT/f'web/data/{case}/metrics.json').read_text())['fault_conditioning']['substrate']
   accepted=(base>0)&(base!=m['unknown_id'])
   self.assertFalse(np.isin(base[accepted],ids).any())
   self.assertTrue(np.isfinite(dist[accepted]).all())
   self.assertLessEqual(float(dist[accepted].max()),report['maximum_transfer_distance_m']+1e-3)
   self.assertTrue((status[accepted]>=3).all())
   self.assertTrue(np.all(base[(status==0)&(base>0)]==m['unknown_id']))
   v=np.fromfile(ROOT/f'web/data/{case}/volume.bin',np.uint8).reshape(shape)
   region=np.isin(s['surface'],ids)[...,None]&(v>0)&~np.isin(v,ids)
   np.testing.assert_array_equal(v[region],base[region])
   self.assertTrue(np.any(v[region]==m['unknown_id']))
