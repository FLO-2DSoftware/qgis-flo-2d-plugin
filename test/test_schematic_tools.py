# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import sys
import unittest
sys.path.append(os.path.join('..', 'flo2d'))
from qgis.core import *
from utilities import get_qgis_app
from flo2d.schematic_tools import *

QGIS_APP = get_qgis_app()
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
VECTOR_PATH = os.path.join(THIS_DIR, 'data', 'vector')
EXPORT_DATA_DIR = os.path.join(THIS_DIR, 'data')


class TestSchematicTools(unittest.TestCase):

    @classmethod
    def tearDownClass(cls):
        for f in os.listdir(EXPORT_DATA_DIR):
            fpath = os.path.join(EXPORT_DATA_DIR, f)
            if os.path.isfile(fpath):
                os.remove(fpath)
            else:
                pass

    @unittest.skip("QGIS needs to be upgraded to version 2.18 on Jenkins machine")
    def test_get_intervals(self):
        user_lines = os.path.join(VECTOR_PATH, 'user_levee_lines.geojson')
        user_points = os.path.join(VECTOR_PATH, 'user_levee_points.geojson')
        line_layer = QgsVectorLayer(user_lines, 'lines', 'ogr')
        point_layer = QgsVectorLayer(user_points, 'points', 'ogr')
        inter_lens = [10, 7]
        for feat in line_layer.getFeatures():
            intervals = get_intervals(feat, point_layer, 'elev', 500)
            self.assertIn(len(intervals), inter_lens)

    @unittest.skip("QGIS needs to be upgraded to version 2.18 on Jenkins machine")
    def test_interpolate_along_line(self):
        user_lines = os.path.join(VECTOR_PATH, 'user_levee_lines.geojson')
        user_points = os.path.join(VECTOR_PATH, 'user_levee_points.geojson')
        levees = os.path.join(VECTOR_PATH, 'levees.geojson')

        line_layer = QgsVectorLayer(user_lines, 'lines', 'ogr')
        point_layer = QgsVectorLayer(user_points, 'points', 'ogr')
        levees_layer = QgsVectorLayer(levees, 'levees', 'ogr')

        total_sum = 0
        for feat in line_layer.getFeatures():
            intervals = get_intervals(feat, point_layer, 'elev', 500)
            interpolated = interpolate_along_line(feat, levees_layer, intervals)
            for row in interpolated:
                val = row[0]
                self.assertGreaterEqual(val, 50)
                self.assertLessEqual(val, 300)
                total_sum += 1
        self.assertEqual(total_sum, 88)

    @unittest.skip("QGIS needs to be upgraded to version 2.18 on Jenkins machine")
    def test_polys2levees(self):
        user_lines = os.path.join(VECTOR_PATH, 'user_levee_lines.geojson')
        user_polygons = os.path.join(VECTOR_PATH, 'user_levee_polygons.geojson')
        levees = os.path.join(VECTOR_PATH, 'levees.geojson')

        line_layer = QgsVectorLayer(user_lines, 'lines', 'ogr')
        polygon_layer = QgsVectorLayer(user_polygons, 'polygons', 'ogr')
        levees_layer = QgsVectorLayer(levees, 'levees', 'ogr')

        for feat in line_layer.getFeatures():
            poly_values = polys2levees(feat, polygon_layer, levees_layer, 'elev')
            vals = [77, 33.33]
            for row in poly_values:
                self.assertIn(row[0], vals)


# Running tests:
if __name__ == '__main__':
    cases = [TestSchematicTools]
    suite = unittest.TestSuite()
    for t in cases:
        tests = unittest.TestLoader().loadTestsFromTestCase(t)
        suite.addTest(tests)
    unittest.TextTestRunner(verbosity=2).run(suite)
