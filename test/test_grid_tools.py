# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import unittest

from flo2d.flo2d_ie.flo2dgeopackage import Flo2dGeoPackage
from .utilities import get_qgis_app

QGIS_APP = get_qgis_app()
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
VECTOR_PATH = os.path.join(THIS_DIR, "data", "vector")
EXPORT_DATA_DIR = os.path.join(THIS_DIR, "data")

from qgis.core import QgsVectorLayer

from flo2d.flo2d_tools.grid_tools import (build_grid, calculate_arfwrf,
                                          poly2grid)
from flo2d.geopackage_utils import database_create

IMPORT_DATA_DIR_1 = os.path.join(THIS_DIR, "data", "import_dat_1")
IMPORT_DATA_DIR_2 = os.path.join(THIS_DIR, "data", "import_dat_2")
CONT_1 = os.path.join(IMPORT_DATA_DIR_1, "CONT.DAT")
CONT_2 = os.path.join(IMPORT_DATA_DIR_2, "CONT.DAT")

class TestGridTools(unittest.TestCase):
    con = database_create(":memory:")
    con_2 = database_create(":memory:")

    @classmethod
    def setUpClass(cls):
        cls.f2g = Flo2dGeoPackage(cls.con, None)
        cls.f2g.disable_geom_triggers()
        cls.f2g.set_parser(CONT_1)

        cls.f2g_2 = Flo2dGeoPackage(cls.con_2, None)
        cls.f2g_2.disable_geom_triggers()
        cls.f2g_2.set_parser(CONT_2)

    @classmethod
    def tearDownClass(cls):
        for f in os.listdir(EXPORT_DATA_DIR):
            fpath = os.path.join(EXPORT_DATA_DIR, f)
            if os.path.isfile(fpath):
                os.remove(fpath)
            else:
                pass

    def test_build_grid(self):
        boundary = os.path.join(VECTOR_PATH, "boundary.geojson")
        vlayer = QgsVectorLayer(boundary, "bl", "ogr")
        self.assertIsInstance(vlayer, QgsVectorLayer)
        polygons = list(build_grid(vlayer, 500))
        self.assertEqual(len(polygons), 494)

    def test_poly2grid(self):
        self.f2g.import_cont_toler()
        cellsize = self.f2g.execute("""SELECT value FROM cont WHERE name = 'CELLSIZE';""").fetchone()[0]
        grid = os.path.join(VECTOR_PATH, "grid.geojson")
        roughness = os.path.join(VECTOR_PATH, "roughness.geojson")
        glayer = QgsVectorLayer(grid, "grid", "ogr")
        rlayer = QgsVectorLayer(roughness, "roughness", "ogr")
        n_values = []
        for n, gid in poly2grid(cellsize, glayer, rlayer, None, True, False, False, 1, "manning"):
            n_values.append(float(n))
        man_sum = sum(n_values)
        self.assertEqual(round(man_sum, 1), 16.5)
        expected = {0.5, 0.3, 0.1}
        self.assertSetEqual(set(n_values), expected)

    def test_calculate_arfwrf(self):
        grid = os.path.join(VECTOR_PATH, "grid.geojson")
        blockers = os.path.join(VECTOR_PATH, "blockers.geojson")
        glayer = QgsVectorLayer(grid, "grid", "ogr")
        blayer = QgsVectorLayer(blockers, "blockers", "ogr")
        row = tuple()
        for row in calculate_arfwrf(glayer, blayer):
            awrf = [True if i <= 1 else False for i in row[0][-9:]]
            self.assertTrue(all(awrf))
        self.assertTupleEqual(row[0][1:], (153, 4, 0.68, 1.0, 0.0, 0.27, 1.0, 0.56, 0.0, 1.0, 1.0))


# Running tests:
if __name__ == "__main__":
    cases = [TestGridTools]
    suite = unittest.TestSuite()
    for t in cases:
        tests = unittest.TestLoader().loadTestsFromTestCase(t)
        suite.addTest(tests)
    unittest.TextTestRunner(verbosity=2).run(suite)
