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
IMPORT_DATA_DIR = os.path.join(THIS_DIR, "CompletedProjects/SelfHelpKit")
EXPORT_DATA_DIR = os.path.join(THIS_DIR, "CompletedProjects/SelfHelpKit", "export")
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


class TestFlo2dSelfHelpKit(unittest.TestCase):
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
        file = IMPORT_DATA_DIR + r"\ARF.DAT"
        if os.path.isfile(file):
            self.f2g.import_arf()
            self.f2g.export_arf(EXPORT_DATA_DIR)
            infile = self.f2g.parser.dat_files["ARF.DAT"]
            outfile = os.path.join(EXPORT_DATA_DIR, "ARF.DAT")
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)
        else:
            self.skipTest("Project does not have ARF.DAT")

    @unittest.skip("Skipping test to fix the issue.")
    def test_chan(self):
        file1 = IMPORT_DATA_DIR + r"\CHAN.DAT"
        file2 = IMPORT_DATA_DIR + r"\CHANBANK.DAT"
        if os.path.isfile(file1) and os.path.isfile(file2):
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
        else:
            self.skipTest("Project does not have CHAN.DAT and CHANBANK.DAT")

    def test_cont_toler(self):
        file1 = IMPORT_DATA_DIR + r"\CONT.DAT"
        file2 = IMPORT_DATA_DIR + r"\TOLER.DAT"
        if os.path.isfile(file1) and os.path.isfile(file2):
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
        else:
            self.skipTest("Project does not have CONT.DAT and TOLER.DAT")

    def test_hystruct(self):
        file = IMPORT_DATA_DIR + r"\HYSTRUC.DAT"
        if os.path.isfile(file):
            self.f2g.import_hystruc()
            self.f2g.export_hystruc(EXPORT_DATA_DIR)
            infile = self.f2g.parser.dat_files["HYSTRUC.DAT"]
            outfile = os.path.join(EXPORT_DATA_DIR, "HYSTRUC.DAT")
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)
        else:
            self.skipTest("Project does not have HYSTRUC.DAT")

    def test_infil(self):
        file = IMPORT_DATA_DIR + r"\INFIL.DAT"
        if os.path.isfile(file):
            self.f2g.import_infil()
            self.f2g.export_infil(EXPORT_DATA_DIR)
            infile = self.f2g.parser.dat_files["INFIL.DAT"]
            outfile = os.path.join(EXPORT_DATA_DIR, "INFIL.DAT")
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)
        else:
            self.skipTest("Project does not have INFIL.DAT")

    def test_inflow(self):
        file = IMPORT_DATA_DIR + r"\INFLOW.DAT"
        if os.path.isfile(file):
            self.f2g.import_inflow()
            self.f2g.export_inflow(EXPORT_DATA_DIR)
            infile = self.f2g.parser.dat_files["INFLOW.DAT"]
            outfile = os.path.join(EXPORT_DATA_DIR, "INFLOW.DAT")
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)
        else:
            self.skipTest("Project does not have INFLOW.DAT")

    def test_levee(self):
        file = IMPORT_DATA_DIR + r"\LEVEE.DAT"
        if os.path.isfile(file):
            self.f2g.import_levee()
            self.f2g.export_levee(EXPORT_DATA_DIR)
            infile = self.f2g.parser.dat_files["LEVEE.DAT"]
            outfile = os.path.join(EXPORT_DATA_DIR, "LEVEE.DAT")
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)
        else:
            self.skipTest("Project does not have LEVEE.DAT")

    def test_manning_n_topo(self):
        file1 = IMPORT_DATA_DIR + r"\MANNINGS_N.DAT"
        file2 = IMPORT_DATA_DIR + r"\TOPO.DAT"
        if os.path.isfile(file1) and os.path.isfile(file2):
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
        else:
            self.skipTest("Project does not have MANNINGS_N.DAT and TOPO.DAT")

    def test_outflow(self):
        file = IMPORT_DATA_DIR + r"\OUTFLOW.DAT"
        if os.path.isfile(file):
            self.f2g.import_outflow()
            self.f2g.export_outflow(EXPORT_DATA_DIR)
            infile = self.f2g.parser.dat_files["OUTFLOW.DAT"]
            outfile = os.path.join(EXPORT_DATA_DIR, "OUTFLOW.DAT")
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)
        else:
            self.skipTest("Project does not have OUTFLOW.DAT")

    def test_rain(self):
        file = IMPORT_DATA_DIR + r"\RAIN.DAT"
        if os.path.isfile(file):
            self.f2g.import_rain()
            self.f2g.export_rain(EXPORT_DATA_DIR)
            infile = self.f2g.parser.dat_files["RAIN.DAT"]
            outfile = os.path.join(EXPORT_DATA_DIR, "RAIN.DAT")
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)
        else:
            self.skipTest("Project does not have RAIN.DAT")

    # def test_swmminp(self):
    #     """Testing the SWMMINP Import/Export"""
    #     file = IMPORT_DATA_DIR + r"\SWMM.INP"
    #     if os.path.isfile(file):
    #         f2d_plot = PlotWidget()
    #         f2g_table = TableEditorWidget(f2g.iface, f2d_plot, f2g.lyrs)
    #         sd = StormDrainEditorWidget(f2g.iface, f2d_plot, f2g_table, f2g.lyrs)
    #         StormDrainEditorWidget.import_storm_drain_INP_file(sd, mode=file, show_end_message=True)
    #         StormDrainEditorWidget.export_storm_drain_INP_file(specific_path=EXPORT_DATA_DIR)
    #         outfile = os.path.join(EXPORT_DATA_DIR, "SWMM.INP")
    #         in_lines, out_lines = compare_files(file, outfile)
    #         self.assertEqual(in_lines, out_lines)
    #     else:
    #         self.skipTest("Project does not have SWMM.INP")

    @unittest.skip("Storm Drain tests needs to be updated")
    def test_sdclogging(self):
        file = IMPORT_DATA_DIR + r"\SDCLOGGING.DAT"
        if os.path.isfile(file):
            self.f2g.import_sdclogging()
            self.f2g.export_sdclogging(EXPORT_DATA_DIR)
            infile = self.f2g.parser.dat_files["SDCLOGGING.DAT"]
            outfile = os.path.join(EXPORT_DATA_DIR, "SDCLOGGING.DAT")
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)
        else:
            self.skipTest("Project does not have SDCLOGGING.DAT")

    @unittest.skip("Storm Drain tests needs to be updated")
    def test_swmmflo(self):
        file = IMPORT_DATA_DIR + r"\SWMMFLO.DAT"
        if os.path.isfile(file):
            self.f2g.import_swmmflo()
            self.f2g.export_swmmflo(EXPORT_DATA_DIR)
            infile = self.f2g.parser.dat_files["SWMMFLO.DAT"]
            outfile = os.path.join(EXPORT_DATA_DIR, "SWMMFLO.DAT")
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)
        else:
            self.skipTest("Project does not have SWMMFLO.DAT")

    @unittest.skip("Storm Drain tests needs to be updated")
    def test_swmmflodropbox(self):
        file = IMPORT_DATA_DIR + r"\SWMMFLODROPBOX.DAT"
        if os.path.isfile(file):
            self.f2g.import_swmmflodropbox()
            self.f2g.export_swmmflodropbox(EXPORT_DATA_DIR)
            infile = self.f2g.parser.dat_files["SWMMFLODROPBOX.DAT"]
            outfile = os.path.join(EXPORT_DATA_DIR, "SWMMFLODROPBOX.DAT")
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)
        else:
            self.skipTest("Project does not have SWMMFLODROPBOX.DAT")

    @unittest.skip("Storm Drain tests needs to be updated")
    def test_swmmflort(self):
        file = IMPORT_DATA_DIR + r"\SWMMFLORT.DAT"
        if os.path.isfile(file):
            self.f2g.import_swmmflort()
            self.f2g.export_swmmflort(EXPORT_DATA_DIR)
            infile = self.f2g.parser.dat_files["SWMMFLORT.DAT"]
            outfile = os.path.join(EXPORT_DATA_DIR, "SWMMFLORT.DAT")
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)
        else:
            self.skipTest("Project does not have SWMMFLORT.DAT")

    @unittest.skip("Storm Drain tests needs to be updated")
    def test_swmmoutf(self):
        file = IMPORT_DATA_DIR + r"\SWMMOUTF.DAT"
        if os.path.isfile(file):
            self.f2g.import_swmmoutf()
            self.f2g.export_swmmoutf(EXPORT_DATA_DIR)
            infile = self.f2g.parser.dat_files["SWMMOUTF.DAT"]
            outfile = os.path.join(EXPORT_DATA_DIR, "SWMMOUTF.DAT")
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)
        else:
            self.skipTest("Project does not have SWMMOUTF.DAT")

    # @unittest.skip("Skipping to fix later.")
    def test_xsec(self):
        file = IMPORT_DATA_DIR + r"\XSEC.DAT"
        if os.path.isfile(file):
            self.f2g.import_xsec()
            self.f2g.export_xsec(EXPORT_DATA_DIR)
            infile = self.f2g.parser.dat_files["XSEC.DAT"]
            outfile = os.path.join(EXPORT_DATA_DIR, "XSEC.DAT")
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)
        else:
            self.skipTest("Project does not have XSEC.DAT")


if __name__ == "__main__":
    cases = [TestFlo2dSelfHelpKit]
    suite = unittest.TestSuite()
    for t in cases:
        tests = unittest.TestLoader().loadTestsFromTestCase(t)
        suite.addTest(tests)
    unittest.TextTestRunner(verbosity=2).run(suite)
