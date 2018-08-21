# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import unittest
from collections import defaultdict
from qgis.core import QgsVectorLayer
from utilities import get_qgis_app
from flo2d.flo2d_tools.schematic_tools import get_intervals, interpolate_along_line, schematize_lines, populate_directions

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
            intervals = get_intervals(feat, point_layer.getFeatures(), 'elev', 500)
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
            intervals = get_intervals(feat, point_layer.getFeatures(), 'elev', 500)
            interpolated = interpolate_along_line(feat, levees_layer.getFeatures(), intervals)
            for row in interpolated:
                val = row[0]
                self.assertGreaterEqual(val, 50)
                self.assertLessEqual(val, 300)
                total_sum += 1
        self.assertEqual(total_sum, 88)

    def test_schematize_lines(self):
        user_lines = os.path.join(VECTOR_PATH, 'channels_streets.geojson')
        cell_size = 500
        offset_x, offset_y = (2.5, -8.94999999999709)
        line_layer = QgsVectorLayer(user_lines, 'lines', 'ogr')
        segments = tuple(schematize_lines(line_layer, cell_size, offset_x, offset_y))
        all_grids = 0
        unique_grids = 0
        for seg in segments:
            all_grids += len(seg)
            unique_grids += len(set(seg))
        self.assertEqual(all_grids - unique_grids, 5)

    def test_schematize_streets(self):
        user_lines = os.path.join(VECTOR_PATH, 'channels_streets.geojson')
        cell_size = 500
        offset_x, offset_y = (2.5, -8.94999999999709)
        line_layer = QgsVectorLayer(user_lines, 'lines', 'ogr')
        segments = schematize_lines(line_layer, cell_size, offset_x, offset_y)
        coords = defaultdict(set)
        for grids in segments:
            populate_directions(coords, grids)
        self.assertSetEqual(coords[(557497.5, 47508.95)], {1, 2, 3, 4})
        for s in coords.itervalues():
            directions = (True if 0 < d < 9 else False for d in s)
            self.assertTrue(all(directions))


# Running tests:
if __name__ == '__main__':
    cases = [TestSchematicTools]
    suite = unittest.TestSuite()
    for t in cases:
        tests = unittest.TestLoader().loadTestsFromTestCase(t)
        suite.addTest(tests)
    unittest.TextTestRunner(verbosity=2).run(suite)
