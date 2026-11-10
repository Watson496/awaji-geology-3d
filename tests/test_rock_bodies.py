"""Identity attribution must not silently become a new lithology estimate."""
import sys
import json
import hashlib
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from rock_bodies import attribute


class RockBodyTests(unittest.TestCase):
    def test_generated_identity_volumes_preserve_native_classes(self):
        web=Path(__file__).resolve().parents[1]/'web/data'
        catalog=json.loads((web/'rock-bodies.json').read_text())
        implementation=Path(__file__).resolve().parents[1]/'scripts/rock_bodies.py'
        self.assertEqual(catalog['implementation_sha256'],hashlib.sha256(implementation.read_bytes()).hexdigest())
        bodies=catalog['bodies'];lookup=np.zeros(len(bodies)+1,np.uint8)
        for body in bodies: lookup[body['id']]=body['source_unit']
        for scenario in ('reference','shallow','deep'):
            self.assertEqual(catalog['native_volume_sha256'][scenario],hashlib.sha256((web/scenario/'volume.bin').read_bytes()).hexdigest())
            native=np.fromfile(web/scenario/'volume.bin',np.uint8)
            attributed=np.fromfile(web/scenario/'body-volume.bin','<u2')
            np.testing.assert_array_equal(lookup[attributed],native)
            entries=json.loads((web/scenario/'meshes.json').read_text())
            for entry in entries: self.assertEqual(lookup[entry['body']],entry['unit'])

    def fixture(self):
        volume=np.ones((7,1,2),np.uint8)
        closed=[np.zeros((6,1,2),bool),np.zeros((7,0,2),bool),np.zeros((7,1,1),bool)]
        a=np.zeros((7,1),bool);a[0]=True
        b=np.zeros_like(a);b[-1]=True
        bodies=[{'id':2,'source_unit':1,'identity':'a','attribution':'interpreted'},
                {'id':3,'source_unit':1,'identity':'b','attribution':'interpreted'}]
        return volume,bodies,{('a',1):a,('b',1):b},closed

    def test_same_legend_distinct_bodies_and_ambiguous_middle(self):
        v,b,s,c=self.fixture();result=attribute(v,b,s,c,[100,100,50],1000,1)
        self.assertEqual(result[0,0,0],2)
        self.assertEqual(result[-1,0,0],3)
        self.assertEqual(result[3,0,0],1)  # equal-distance identity stays unresolved
        self.assertTrue(np.all(v==1))  # inference input unchanged

    def test_fault_blocks_identity_even_if_nearby(self):
        v,b,s,c=self.fixture();c[0][2]=True
        result=attribute(v,b[:1],s,c,[100,100,50],1000,1)
        self.assertEqual(result[2,0,0],2)
        self.assertTrue(np.all(result[3:]==1))

    def test_other_lithology_is_not_an_identity_bridge(self):
        v,b,s,c=self.fixture();v[2]=4
        result=attribute(v,b[:1],s,c,[100,100,50],1000,1)
        self.assertTrue(np.all(result[2]==4))
        self.assertTrue(np.all(result[3:]==1))

    def test_distance_limit_is_not_a_vertical_extrusion(self):
        v,b,s,c=self.fixture()
        result=attribute(v,b[:1],s,c,[100,100,50],120,1)
        self.assertEqual(result[0,0,0],2)
        self.assertEqual(result[1,0,0],1)  # path 100 horizontal + 50 vertical
        self.assertEqual(result[1,0,1],2)


if __name__=='__main__': unittest.main()
