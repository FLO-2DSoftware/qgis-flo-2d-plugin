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

    def test_get_intervals(self):
        user_lines = os.path.join(VECTOR_PATH, 'user_levee_lines.geojson')
        user_points = os.path.join(VECTOR_PATH, 'user_levee_points.geojson')
        line_layer = QgsVectorLayer(user_lines, 'lines', 'ogr')
        point_layer = QgsVectorLayer(user_points, 'points', 'ogr')
        for feat in line_layer.getFeatures():
            intervals = get_intervals(feat, point_layer, 'elev', 500)
            for i in intervals:
                print(i)

    def test_interpolate_along_line(self):
        user_lines = os.path.join(VECTOR_PATH, 'user_levee_lines.geojson')
        user_points = os.path.join(VECTOR_PATH, 'user_levee_points.geojson')
        levees = os.path.join(VECTOR_PATH, 'levees.geojson')

        line_layer = QgsVectorLayer(user_lines, 'lines', 'ogr')
        point_layer = QgsVectorLayer(user_points, 'points', 'ogr')
        levees_layer = QgsVectorLayer(levees, 'levees', 'ogr')

        for feat in line_layer.getFeatures():
            intervals = get_intervals(feat, point_layer, 'elev', 500)
            interpolated = interpolate_along_line(feat, levees_layer, intervals)
            for row in interpolated:
                print(row)


# Running tests:
if __name__ == '__main__':
    cases = [TestSchematicTools]
    suite = unittest.TestSuite()
    for t in cases:
        tests = unittest.TestLoader().loadTestsFromTestCase(t)
        suite.addTest(tests)
    unittest.TextTestRunner(verbosity=2).run(suite)
