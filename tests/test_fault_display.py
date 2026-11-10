import hashlib,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from fault_display import build,ROOT

def fault(id,layer,trace,name=None,**kw):
 return {'id':id,'layer':layer,'name':name or id,'traces':[trace],'dashed':False,'used_for_model':False,**kw}
class FaultDisplayTests(unittest.TestCase):
 def test_finer_trace_replaces_cross_source_duplicate(self):
  a=fault('fine','seamless',[[0,0,0],[500,0,1],[1000,0,2]])
  b=fault('coarse','active',[[0,50,0],[1000,50,0]])
  out=build({'faults':[a,b]})
  self.assertEqual(len(out['faults']),1)
  self.assertEqual(out['faults'][0]['traces'],a['traces'])
  self.assertIn('coarse',out['faults'][0]['source_ids'])
 def test_parallel_branches_from_same_source_are_kept(self):
  out=build({'faults':[fault('a','major',[[0,0,0],[1000,0,0]]),fault('b','major',[[0,100,0],[1000,100,0]])]})
  self.assertEqual(len(out['faults']),2)
 def test_crossing_fault_is_not_a_duplicate(self):
  out=build({'faults':[fault('a','seamless',[[-1000,0,0],[1000,0,0]]),fault('b','active',[[0,-1000,0],[0,1000,0]])]})
  self.assertEqual(len(out['faults']),2)
  self.assertTrue(all(x.get('suppressed_length_m',0)==0 for x in out['audit']))
 def test_overview_is_replaced_by_separate_strands(self):
  out=build({'faults':[fault('overview','active',[[0,0,0],[1000,0,0]],model_aliases=['a','b']),fault('a','major',[[0,0,0],[1000,0,0]]),fault('b','major',[[0,100,0],[1000,100,0]])]})
  self.assertEqual({x['id'] for x in out['faults']},{'a','b'})
 def test_published_display_matches_raw_catalog_and_retains_all_model_ids(self):
  raw=(ROOT/'web/data/faults.json').read_bytes();out=json.loads((ROOT/'web/data/fault-display.json').read_text())
  self.assertEqual(out['source_sha256'],hashlib.sha256(raw).hexdigest())
  covered={a for f in out['faults'] for a in f['model_aliases']}
  for f in json.loads(raw)['faults']:
   if f['used_for_model']:self.assertIn(f['id'],covered)
