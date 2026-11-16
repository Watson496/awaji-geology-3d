"""科学的な前提とデータの契約を、ネットワーク接続なしで検査する。"""
import json
from pathlib import Path
import sys
import unittest

import numpy as np
import gempy as gp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare import decode_dem, normal_from_strike, spaced_indices


class InputConventions(unittest.TestCase):
    def test_gsi_signed_elevation_and_nodata(self):
        rgba = np.array([[[0, 0, 100, 255], [255, 255, 156, 255], [128, 0, 0, 255], [0, 0, 0, 0]]], np.uint8)
        z = decode_dem(rgba)
        self.assertEqual(z[0, 0], 1)
        self.assertEqual(z[0, 1], -1)
        self.assertTrue(np.isnan(z[0, 2:]).all())

    def test_right_hand_rule_and_unit_normal(self):
        # 東西走向90度は南傾斜に対応し、上向き法線の水平成分は南を向く。
        n = normal_from_strike(90, 30)
        np.testing.assert_allclose(n, [0, -.5, np.sqrt(3) / 2], atol=1e-12)
        np.testing.assert_allclose(normal_from_strike(0, 90), [1, 0, 0], atol=1e-12)
        self.assertAlmostEqual(np.linalg.norm(n), 1)

    def test_thinning_is_deterministic_and_spatial(self):
        xy = np.c_[np.arange(20) * 10, np.zeros(20)]
        np.testing.assert_equal(spaced_indices(xy, 50, 10), [0, 5, 10, 15])

    def test_gempy_above_below_and_layer_order(self):
        sp = gp.data.SurfacePointsTable.from_arrays(x=np.array([0., 1000., 0.]),
            y=np.array([0., 0., 1000.]), z=np.zeros(3), names='cover')
        ot = gp.data.OrientationsTable.from_arrays(x=np.array([500.]), y=np.array([500.]),
            z=np.zeros(1), G_x=np.zeros(1), G_y=np.zeros(1), G_z=np.ones(1), names='cover')
        element = gp.data.StructuralElement(name='cover', color='#dfcf91', surface_points=sp, orientations=ot)
        frame = gp.data.StructuralFrame([gp.data.StructuralGroup('young', [element], gp.data.StackRelationType.ERODE)],
                                        gp.data.ColorsGenerator())
        model = gp.create_geomodel(extent=[0, 1000, 0, 1000, -1000, 1000], refinement=1, structural_frame=frame)
        model.interpolation_options.evaluation_options.mesh_extraction = False
        result = gp.compute_model_at(model, np.array([[500., 500., -500.], [500., 500., 500.]]))
        np.testing.assert_equal(result, [2, 1])


@unittest.skipUnless((ROOT / 'web/data/model.json').exists(), 'Run the model first')
class GeneratedModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta = json.loads((ROOT / 'web/data/model.json').read_text())
        cls.source = np.load(ROOT / 'data/prepared/surface.npz')

    def test_volume_contract_and_original_symbols(self):
        nx,ny=self.meta['shape'];nz=self.meta['nz'];allowed={0,*[u['id'] for u in self.meta['units']]}
        for name in self.meta['scenarios']:
            v=np.fromfile(ROOT/f'web/data/{name}/volume.bin',np.uint8).reshape(nx,ny,nz)
            self.assertTrue(np.all(v[~self.source['island']]==0));self.assertTrue(set(np.unique(v)).issubset(allowed))
            zbottom=self.meta['zmin']+np.arange(nz)*(self.meta['zmax']-self.meta['zmin'])/nz
            self.assertTrue(np.all(v[zbottom[None,None,:]>=self.source['dem'][...,None]]==0))
    def test_source_catalog_is_not_aggregated(self):
        legend={d['symbol']:d for d in json.loads((ROOT/'data/raw/seamless-legend.json').read_text())}
        units=[u for u in self.meta['units'] if u['kind']=='geological']
        self.assertEqual(len(units),self.meta['source_legend_count']);self.assertEqual(len(set(u['key'] for u in units)),len(units))
        for u in units:
            self.assertEqual(u['key'],u['source_symbol']);self.assertEqual(u['color'],'#'+legend[u['key']]['value']);self.assertEqual(u['name'],legend[u['key']]['title'])
        self.assertEqual(set(np.unique(self.source['surface']))-{0},{u['id'] for u in units})
    def test_unknown_is_not_an_invented_geological_unit(self):
        unit=self.meta['units'][self.meta['unknown_id']-1];self.assertEqual(unit['kind'],'unknown');self.assertIsNone(unit['source_symbol'])
    def test_surface_metrics_match_boundary_condition(self):
        truth=self.source['surface'][self.source['island']]
        for name in self.meta['scenarios']:
            pred=np.fromfile(ROOT/f'web/data/{name}/surface.bin',np.uint8).reshape(self.meta['shape'])[self.source['island']]
            metrics=json.loads((ROOT/f'web/data/{name}/metrics.json').read_text())
            self.assertAlmostEqual(float(np.mean(pred==truth)),metrics['surface_agreement']);self.assertIn('boundary',metrics['surface_agreement_note'])
            self.assertEqual(np.array(metrics['surface_confusion_matrix_actual_rows']).sum(),len(truth))

if __name__=='__main__':unittest.main()
