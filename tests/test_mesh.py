"""表示メッシュの座標・三角形・断面の平面性を検査する。"""
import json
import unittest
from pathlib import Path
import numpy as np

WEB=Path(__file__).resolve().parents[1]/'web/data'

def values(raw,entry):
    return np.frombuffer(raw,dtype=entry['type'],count=entry['count'],offset=entry['offset'])

@unittest.skipUnless((WEB/'terrain-mesh.json').exists(),'npm run mesh が必要')
class DisplayMeshes(unittest.TestCase):
    def test_terrain_indices_and_vertex_colors(self):
        data=json.loads((WEB/'terrain-mesh.json').read_text());raw=(WEB/'terrain-mesh.bin').read_bytes()
        p=values(raw,data['positions']).reshape(-1,3);c=values(raw,data['color']).reshape(-1,3);index=values(raw,data['indices'])
        self.assertTrue(np.isfinite(p).all());self.assertEqual(p.shape,c.shape);self.assertTrue(((c>=0)&(c<=1)).all())
        self.assertLess(index.max(),len(p));self.assertEqual(len(index)%3,0);self.assertGreater(len(p),20000)
        units=values(raw,data['units']);self.assertEqual(len(units),len(p));meta=json.loads((WEB/'model.json').read_text());self.assertTrue(set(np.unique(units)).issubset({u['id'] for u in meta['units'] if u['kind']=='geological'}))

    def test_rock_meshes_have_valid_triangles(self):
        for name in ['reference','shallow','deep']:
            folder=WEB/name;raw=(folder/'meshes.bin').read_bytes();meshes=json.loads((folder/'meshes.json').read_text())
            meta=json.loads((WEB/'model.json').read_text());self.assertTrue({m['unit'] for m in meshes}.issubset({u['id'] for u in meta['units']}))
            for m in meshes:
                p=values(raw,m['positions']).reshape(-1,3);f=values(raw,m['indices'])
                self.assertTrue(np.isfinite(p).all());self.assertEqual(len(f)%3,0);self.assertLess(f.max(),len(p))

    def test_fence_triangles_are_in_their_section_plane(self):
        for name in ['reference','shallow','deep']:
            folder=WEB/name;raw=(folder/'sections.bin').read_bytes();sections=json.loads((folder/'sections.json').read_text())
            meta=json.loads((WEB/'model.json').read_text());self.assertEqual(list(map(len,sections)),[*meta['shape'],meta['nz']])
            for axis,planes in enumerate(sections):
                coordinate=[0,2,1][axis]
                for items in planes:
                    for item in items:
                        p=values(raw,item['positions']).reshape(-1,3)
                        self.assertEqual(len(p)%3,0);self.assertTrue(np.isfinite(p).all())
                        self.assertLess(float(np.ptp(p[:,coordinate])),2e-6)
