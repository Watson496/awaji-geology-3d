import json,sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from surficial_cover import constrain_packages,audit_volume,policy,ROOT
from structure import ordered_packages
class SurficialCoverTests(unittest.TestCase):
 def test_thickness_is_relative_to_local_dem_not_sea_level(self):
  z=np.arange(-475,526,50);dem=np.array([[0.],[300.]])
  rock=z[None,None,:]-25<dem[...,None]
  scores=np.zeros((*rock.shape,2),np.float32);scores[...,1]=100
  packages=[{'id':'older','symbols':['K22_soss']},{'id':'alluvial','symbols':['H_sad']}]
  constrained,_=constrain_packages(scores,packages,z,dem,rock,'reference')
  out=ordered_packages(constrained,rock,np.zeros((*rock.shape[:2],rock.shape[2]-1),bool),np.ones((2,1),int))
  depth=dem[...,None]-z
  self.assertFalse(np.any((out==1)&rock&(depth>30)))
  self.assertTrue(np.any((out==1)&rock&(z[None,None,:]>200)))
 def test_fault_reset_does_not_allow_deep_young_cover(self):
  z=np.arange(-475,26,50);rock=np.ones((1,1,len(z)),bool)
  scores=np.zeros((*rock.shape,2),np.float32);scores[...,1]=1000
  c,_=constrain_packages(scores,[{'id':'older','symbols':['K22_soss']},{'id':'terrace','symbols':['Q32-33_std']}],z,np.zeros((1,1)),rock,'reference')
  out=ordered_packages(c,rock,np.ones((1,1,len(z)-1),bool),np.ones((1,1),int))
  self.assertFalse(np.any((out==1)&(-z[None,None,:]>35)))
 def test_thin_ground_label_is_preserved_with_explicit_grid_limitation(self):
  z=np.array([-25.]);rock=np.ones((1,1,1),bool)
  scores=np.zeros((1,1,1,2),np.float32)
  out,audit=constrain_packages(scores,[{'id':'older','symbols':['K22_soss']},{'id':'fill','symbols':['H2_or']}],z,np.zeros((1,1)),rock,'shallow')
  self.assertEqual(out[0,0,0,1],0)
  self.assertIn('unresolved',audit['top_cell_exception'])
 def test_generated_scenarios_have_no_deep_surficial_units(self):
  meta=json.loads((ROOT/'web/data/model.json').read_text());dem=np.load(ROOT/'data/prepared/surface.npz')['dem']
  for case in meta['scenarios']:
   volume=np.fromfile(ROOT/f'web/data/{case}/volume.bin',np.uint8).reshape(*meta['shape'],meta['nz'])
   report=audit_volume(volume,meta,dem,case)
   self.assertTrue(all(r['cells_below_150m']==0 for r in report.values()))
