import os
import sys
import unittest
sys.path.append(os.path.join('..', 'flo2d'))
from shutil import copyfile
from qgis.core import *
from utilities import get_qgis_app
from flo2d.grid_tools import build_grid, roughness2grid, calculate_arfwrf

QGIS_APP = get_qgis_app()
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
VECTOR_PATH = os.path.join(THIS_DIR, 'data', 'vector')
EXPORT_DATA_DIR = os.path.join(THIS_DIR, 'data')


class TestGridTools(unittest.TestCase):

    @classmethod
    def tearDownClass(cls):
        for f in os.listdir(EXPORT_DATA_DIR):
            fpath = os.path.join(EXPORT_DATA_DIR, f)
            if os.path.isfile(fpath):
                os.remove(fpath)
            else:
                pass

    def test_build_grid(self):
        boundary = os.path.join(VECTOR_PATH, 'boundary.geojson')
        vlayer = QgsVectorLayer(boundary, 'bl', 'ogr')
        self.assertIsInstance(vlayer, QgsVectorLayer)
        polygons = list(build_grid(vlayer, 500))
        self.assertEqual(len(polygons), 494)

    def test_roughness2grid(self):
        grid_src = os.path.join(VECTOR_PATH, 'grid.geojson')
        grid = os.path.join(EXPORT_DATA_DIR, 'grid.geojson')
        roughness = os.path.join(VECTOR_PATH, 'roughness.geojson')
        copyfile(grid_src, grid)
        glayer = QgsVectorLayer(grid, 'grid', 'ogr')
        rlayer = QgsVectorLayer(roughness, 'roughness', 'ogr')
        roughness2grid(glayer, rlayer, 'manning')
        features = glayer.getFeatures()
        man_values = []
        for feat in features:
            man = feat.attribute('n_value')
            if man:
                man_values.append(float(man))
            else:
                pass
        man_sum = sum(man_values)
        self.assertEqual(round(man_sum, 1), 16.5)
        expected = {0.5, 0.3, 0.1}
        self.assertSetEqual(set(man_values), expected)

    def test_calculate_arfwrf(self):
        grid = os.path.join(VECTOR_PATH, 'grid.geojson')
        blockers = os.path.join(VECTOR_PATH, 'blockers.geojson')
        glayer = QgsVectorLayer(grid, 'grid', 'ogr')
        blayer = QgsVectorLayer(blockers, 'blockers', 'ogr')
        row = tuple()
        for row in calculate_arfwrf(glayer, blayer):
            awrf = [True if i <= 1 else False for i in row[-9:]]
            self.assertTrue(all(awrf))
        self.assertTupleEqual(row[1:], (153L, 0.68, 1.0, 0.0, 0.27, 1.0, 0.56, 0.0, 1.0, 1.0))


# Running tests:
if __name__ == '__main__':
    cases = [TestGridTools]
    suite = unittest.TestSuite()
    for t in cases:
        tests = unittest.TestLoader().loadTestsFromTestCase(t)
        suite.addTest(tests)
    unittest.TextTestRunner(verbosity=2).run(suite)
