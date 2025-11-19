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
IMPORT_DATA_DIR = os.path.join(THIS_DIR, "CompletedProjects", "Coastal")
EXPORT_DATA_DIR = os.path.join(THIS_DIR, "CompletedProjects", "Coastal", "export")
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


class TestFlo2dCoastal(unittest.TestCase):
    
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

    def test_chan(self):
        self.f2g.import_chan()
        self.f2g.export_chan(EXPORT_DATA_DIR)
        infile1 = self.f2g.parser.dat_files["CHAN.DAT"]
        infile2 = self.f2g.parser.dat_files["CHANBANK.DAT"]
        outfile1 = os.path.join(EXPORT_DATA_DIR, "CHAN.DAT")
        outfile2 = os.path.join(EXPORT_DATA_DIR, "CHANBANK.DAT")
        in_lines1, out_lines1 = compare_files(infile1, outfile1)
        self.assertEqual(in_lines1, out_lines1)
        in_lines2, out_lines2 = compare_files(infile2, outfile2)
        self.assertEqual(in_lines2, out_lines2)

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

    def test_hystruct(self):
        self.f2g.import_hystruc()
        self.f2g.export_hystruc(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files["HYSTRUC.DAT"]
        outfile = os.path.join(EXPORT_DATA_DIR, "HYSTRUC.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_infil(self):
        self.f2g.import_infil()
        self.f2g.export_infil(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files["INFIL.DAT"]
        outfile = os.path.join(EXPORT_DATA_DIR, "INFIL.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_inflow(self):
        self.f2g.import_inflow()
        self.f2g.export_inflow(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files["INFLOW.DAT"]
        outfile = os.path.join(EXPORT_DATA_DIR, "INFLOW.DAT")
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

    def test_swmminp(self):
        self.f2g.import_swmminp()
        # Number of inlets
        n_inlets = self.f2g.execute("""SELECT COUNT(fid) FROM chan_elems WHERE fid = 'I';""").fetchone()[0]
        self.assertEqual(n_inlets, 283)
        # Number of junctions
        n_junctions = self.f2g.execute("""SELECT COUNT(fid) FROM user_swmm_inlets_junctions WHERE sd_type = 'J';""").fetchone()[0]
        self.assertEqual(n_junctions, 1)
        # Number of junctions & inlets
        n_inlets_junctions = self.f2g.execute("""SELECT COUNT(fid) FROM user_swmm_inlets_junctions;""").fetchone()[0]
        self.assertEqual(n_inlets_junctions, 284)
        # Number of outfalls:
        n_outfalls = self.f2g.execute("""SELECT COUNT(fid) FROM user_swmm_outlets;""").fetchone()[0]
        self.assertEqual(n_outfalls, 10)
        # Number of conduits
        n_conduits = self.f2g.execute("""SELECT COUNT(fid) FROM user_swmm_conduits;""").fetchone()[0]
        self.assertEqual(n_conduits, 284)
        # Number of RT
        n_rt = self.f2g.execute("""SELECT COUNT(fid) FROM swmmflort;""").fetchone()[0]
        self.assertEqual(n_rt, 59)
        # Number of RT data
        n_rt_data = self.f2g.execute("""SELECT COUNT(fid) FROM swmmflort_data;""").fetchone()[0]
        self.assertEqual(n_rt_data, 437)
        # Number of SD CONTROL
        n_control = self.f2g.execute("""SELECT COUNT(fid) FROM swmm_control;""").fetchone()[0]
        self.assertEqual(n_control, 32)

    def test_swmmflo(self):
        self.f2g.import_swmmflo()
        self.f2g.export_swmmflo(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files["SWMMFLO.DAT"]
        outfile = os.path.join(EXPORT_DATA_DIR, "SWMMFLO.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_swmmflort(self):
        self.f2g.import_swmminp()
        self.f2g.import_swmmflort()
        self.f2g.export_swmmflort(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files["SWMMFLORT.DAT"]
        outfile = os.path.join(EXPORT_DATA_DIR, "SWMMFLORT.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_swmmoutf(self):
        self.f2g.import_swmmoutf()
        self.f2g.export_swmmoutf(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files["SWMMOUTF.DAT"]
        outfile = os.path.join(EXPORT_DATA_DIR, "SWMMOUTF.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_xsec(self):
        self.f2g.import_xsec()
        self.f2g.export_xsec(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files["XSEC.DAT"]
        outfile = os.path.join(EXPORT_DATA_DIR, "XSEC.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)
            
            
if __name__ == "__main__":
    cases = [TestFlo2dCoastal]
    suite = unittest.TestSuite()
    for t in cases:
        tests = unittest.TestLoader().loadTestsFromTestCase(t)
        suite.addTest(tests)
    unittest.TextTestRunner(verbosity=2).run(suite)
