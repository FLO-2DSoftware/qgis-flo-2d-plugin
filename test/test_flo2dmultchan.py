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
from flo2d.geopackage_utils import database_create

from test.utilities import get_qgis_app

QGIS_APP = get_qgis_app()
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
IMPORT_DATA_DIR = os.path.join(THIS_DIR, "CompletedProjects", "MultChan")
EXPORT_DATA_DIR = os.path.join(THIS_DIR, "CompletedProjects", "MultChan", "export")
CONT = os.path.join(IMPORT_DATA_DIR, "CONT.DAT")


def compare_files(file1, file2):
    """
    Function to compare two files without considering the zeros
    """

    def normalize(line):
        return ''.join(line.split())

    with open(file1, 'r') as f1, open(file2, 'r') as f2:
        lines1 = [normalize(line) for line in f1]
        lines2 = [normalize(line) for line in f2]

    return lines1, lines2


class TestFlo2dMultChan(unittest.TestCase):
    con = database_create(":memory:")

    @classmethod
    def setUpClass(cls):
        os.makedirs(EXPORT_DATA_DIR)
        cls.f2g = Flo2dGeoPackage(cls.con, None)
        cls.f2g.disable_geom_triggers()
        cls.f2g.set_parser(CONT)
        cls.f2g.import_mannings_n_topo()

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        for f in os.listdir(EXPORT_DATA_DIR):
            fpath = os.path.join(EXPORT_DATA_DIR, f)
            if os.path.isfile(fpath):
                os.remove(fpath)
            else:
                pass
        os.rmdir(EXPORT_DATA_DIR)

    def test_arf(self):
        self.f2g.import_arf()
        self.f2g.export_arf(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files["ARF.DAT"]
        outfile = os.path.join(EXPORT_DATA_DIR, "ARF.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_cont_toler(self):
        self.f2g.import_cont_toler()
        self.f2g.export_cont_toler(EXPORT_DATA_DIR)
        infile1 = self.f2g.parser.dat_files["CONT.DAT"]
        infile2 = self.f2g.parser.dat_files["TOLER.DAT"]
        outfile1 = os.path.join(EXPORT_DATA_DIR, "CONT.DAT")
        outfile2 = os.path.join(EXPORT_DATA_DIR, "TOLER.DAT")
        in_lines1, out_lines1 = compare_files(infile1, outfile1)
        self.assertEqual(in_lines1, out_lines1)
        in_lines2, out_lines2 = compare_files(infile2, outfile2)
        self.assertEqual(in_lines2, out_lines2)

    def test_fpfroude(self):
        self.f2g.import_fpfroude()
        self.f2g.export_fpfroude(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files["FPFROUDE.DAT"]
        outfile = os.path.join(EXPORT_DATA_DIR, "FPFROUDE.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_fpxsec(self):
        self.f2g.import_fpxsec()
        self.f2g.export_fpxsec(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files["FPXSEC.DAT"]
        outfile = os.path.join(EXPORT_DATA_DIR, "FPXSEC.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_manning_n_topo(self):
        self.f2g.import_mannings_n_topo()
        self.f2g.export_mannings_n_topo(EXPORT_DATA_DIR)
        infile1 = self.f2g.parser.dat_files["MANNINGS_N.DAT"]
        infile2 = self.f2g.parser.dat_files["TOPO.DAT"]
        outfile1 = os.path.join(EXPORT_DATA_DIR, "MANNINGS_N.DAT")
        outfile2 = os.path.join(EXPORT_DATA_DIR, "TOPO.DAT")
        in_lines1, out_lines1 = compare_files(infile1, outfile1)
        self.assertEqual(in_lines1, out_lines1)
        in_lines2, out_lines2 = compare_files(infile2, outfile2)
        self.assertEqual(in_lines2, out_lines2)

    def test_mult(self):
        self.f2g.import_mult()
        self.f2g.export_mult(EXPORT_DATA_DIR)
        infile1 = self.f2g.parser.dat_files["MULT.DAT"]
        infile2 = self.f2g.parser.dat_files["SIMPLE_MULT.DAT"]
        outfile1 = os.path.join(EXPORT_DATA_DIR, "MULT.DAT")
        outfile2 = os.path.join(EXPORT_DATA_DIR, "SIMPLE_MULT.DAT")
        in_lines1, out_lines1 = compare_files(infile1, outfile1)
        self.assertEqual(in_lines1, out_lines1)
        in_lines2, out_lines2 = compare_files(infile2, outfile2)
        self.assertEqual(in_lines2, out_lines2)

    def test_outflow(self):
        self.f2g.import_outflow()
        self.f2g.export_outflow(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files["OUTFLOW.DAT"]
        outfile = os.path.join(EXPORT_DATA_DIR, "OUTFLOW.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_rain(self):
        self.f2g.import_rain()
        self.f2g.export_rain(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files["RAIN.DAT"]
        outfile = os.path.join(EXPORT_DATA_DIR, "RAIN.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    @unittest.skip("Need to build this test")
    def test_tolspatial(self):
        self.f2g.import_tolspatial()
        self.f2g.export_tolspatial(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files["TOLSPATIAL.DAT"]
        outfile = os.path.join(EXPORT_DATA_DIR, "TOLSPATIAL.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)


if __name__ == "__main__":
    cases = [TestFlo2dMultChan]
    suite = unittest.TestSuite()
    for t in cases:
        tests = unittest.TestLoader().loadTestsFromTestCase(t)
        suite.addTest(tests)
    unittest.TextTestRunner(verbosity=2).run(suite)
