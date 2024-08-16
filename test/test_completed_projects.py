# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import unittest

from .utilities import get_qgis_app

from flo2d.flo2d_ie.flo2dgeopackage import Flo2dGeoPackage
from flo2d.geopackage_utils import database_create

QGIS_APP = get_qgis_app()
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(THIS_DIR, "CompletedProjects")


def compare_files(file1, file2):
    def normalize(line):
        return ''.join(line.split())  # Remove all whitespace from the line

    with open(file1, 'r') as f1, open(file2, 'r') as f2:
        lines1 = [normalize(line) for line in f1]
        lines2 = [normalize(line) for line in f2]

    return lines1, lines2


def export_paths(export_folder, *inpaths):
    paths = [os.path.join(export_folder, os.path.basename(inpath)) for inpath in inpaths]
    if len(paths) == 1:
        paths = paths[0]
    else:
        pass
    return paths


class TestCompletedProjects(unittest.TestCase):

    con = database_create(":memory:")

    import_folder = os.path.join(PROJECTS_DIR, 'SelfHelpKit')
    export_folder = os.path.join(PROJECTS_DIR, 'SelfHelpKit', 'export')
    os.mkdir(export_folder)

    CONT = os.path.join(import_folder, "CONT.DAT")

    @classmethod
    def setUpClass(cls):

        cls.f2g = Flo2dGeoPackage(cls.con, None)
        cls.f2g.disable_geom_triggers()
        cls.f2g.set_parser(cls.CONT)
        cls.f2g.import_mannings_n_topo()

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        for f in os.listdir(cls.export_folder):
            fpath = os.path.join(cls.export_folder, f)
            if os.path.isfile(fpath):
                os.remove(fpath)
            else:
                pass
        os.rmdir(cls.export_folder)

    @unittest.skip("Skipping test to fix the issue.")
    def test_arf(self):
        file = self.import_folder + r"\ARF.DAT"
        if os.path.isfile(file):
            self.f2g.import_arf()
            self.f2g.export_arf(self.export_folder)
            infile = self.f2g.parser.dat_files["ARF.DAT"]
            outfile = export_paths(self.export_folder, infile)
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)

    def test_chan(self):
        file1 = self.import_folder + r"\CHAN.DAT"
        file2 = self.import_folder + r"\CHANBANK.DAT"
        if os.path.isfile(file1) and os.path.isfile(file2):
            self.f2g.import_chan()
            self.f2g.export_chan(self.export_folder)
            infile1 = self.f2g.parser.dat_files["CHAN.DAT"]
            infile2 = self.f2g.parser.dat_files["CHANBANK.DAT"]
            outfile1, outfile2 = export_paths(self.export_folder, infile1, infile2)
            in_lines1, out_lines1 = compare_files(infile1, outfile1)
            self.assertEqual(in_lines1, out_lines1)
            in_lines2, out_lines2 = compare_files(infile2, outfile2)
            self.assertEqual(in_lines2, out_lines2)

    def test_cont_toler(self):
        file1 = self.import_folder + r"\CONT.DAT"
        file2 = self.import_folder + r"\TOLER.DAT"
        if os.path.isfile(file1) and os.path.isfile(file2):
            self.f2g.import_cont_toler()
            self.f2g.export_cont_toler(self.export_folder)
            infile1 = self.f2g.parser.dat_files["CONT.DAT"]
            infile2 = self.f2g.parser.dat_files["TOLER.DAT"]
            outfile1, outfile2 = export_paths(self.export_folder, infile1, infile2)
            in_lines1, out_lines1 = compare_files(infile1, outfile1)
            self.assertEqual(in_lines1, out_lines1)
            in_lines2, out_lines2 = compare_files(infile2, outfile2)
            self.assertEqual(in_lines2, out_lines2)

    def test_hystruct(self):

        file = self.import_folder + r"\HYSTRUC.DAT"
        if os.path.isfile(file):
            self.f2g.import_hystruc()
            self.f2g.export_hystruc(self.export_folder)
            infile = self.f2g.parser.dat_files["HYSTRUC.DAT"]
            outfile = export_paths(self.export_folder, infile)
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)

    def test_infil(self):
        file = self.import_folder + r"\INFIL.DAT"
        if os.path.isfile(file):
            self.f2g.import_infil()
            self.f2g.export_infil(self.export_folder)
            infile = self.f2g.parser.dat_files["INFIL.DAT"]
            outfile = export_paths(self.export_folder, infile)
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)

    def test_inflow(self):
        file = self.import_folder + r"\INFLOW.DAT"
        if os.path.isfile(file):
            self.f2g.import_inflow()
            self.f2g.export_inflow(self.export_folder)
            infile = self.f2g.parser.dat_files["INFLOW.DAT"]
            outfile = export_paths(self.export_folder, infile)
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)

    def test_levee(self):
        file = self.import_folder + r"\LEVEE.DAT"
        if os.path.isfile(file):
            self.f2g.import_levee()
            self.f2g.export_levee(self.export_folder)
            infile = self.f2g.parser.dat_files["LEVEE.DAT"]
            outfile = export_paths(self.export_folder, infile)
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)

    def test_manning_n_topo(self):
        file1 = self.import_folder + r"\MANNINGS_N.DAT"
        file2 = self.import_folder + r"\TOPO.DAT"
        if os.path.isfile(file1) and os.path.isfile(file2):
            self.f2g.import_mannings_n_topo()
            self.f2g.export_mannings_n_topo(self.export_folder)
            infile1 = self.f2g.parser.dat_files["MANNINGS_N.DAT"]
            infile2 = self.f2g.parser.dat_files["TOPO.DAT"]
            outfile1, outfile2 = export_paths(self.export_folder, infile1, infile2)
            in_lines1, out_lines1 = compare_files(infile1, outfile1)
            self.assertEqual(in_lines1, out_lines1)
            in_lines2, out_lines2 = compare_files(infile2, outfile2)
            self.assertEqual(in_lines2, out_lines2)

    def test_outflow(self):
        file = self.import_folder + r"\OUTFLOW.DAT"
        if os.path.isfile(file):
            self.f2g.import_outflow()
            self.f2g.export_outflow(self.export_folder)
            infile = self.f2g.parser.dat_files["OUTFLOW.DAT"]
            outfile = export_paths(self.export_folder, infile)
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)

    def test_rain(self):
        file = self.import_folder + r"\RAIN.DAT"
        if os.path.isfile(file):
            self.f2g.import_rain()
            self.f2g.export_rain(self.export_folder)
            infile = self.f2g.parser.dat_files["RAIN.DAT"]
            outfile = export_paths(self.export_folder, infile)
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)

    @unittest.skip("Skipping test to fix the issue.")
    def test_sdclogging(self):
        file = self.import_folder + r"\SDCLOGGING.DAT"
        if os.path.isfile(file):
            self.f2g.import_sdclogging()
            self.f2g.export_sdclogging(self.export_folder)
            infile = self.f2g.parser.dat_files["SDCLOGGING.DAT"]
            outfile = export_paths(self.export_folder, infile)
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)

    def test_swmmflo(self):
        file = self.import_folder + r"\SWMMFLO.DAT"
        if os.path.isfile(file):
            self.f2g.import_swmmflo()
            self.f2g.export_swmmflo(self.export_folder)
            infile = self.f2g.parser.dat_files["SWMMFLO.DAT"]
            outfile = export_paths(self.export_folder, infile)
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)

    @unittest.skip("Skipping test to fix the issue.")
    def test_swmmflodropbox(self):
        file = self.import_folder + r"\SWMMFLODROPBOX.DAT"
        if os.path.isfile(file):
            self.f2g.import_swmmflodropbox()
            self.f2g.export_swmmflodropbox(self.export_folder)
            infile = self.f2g.parser.dat_files["SWMMFLODROPBOX.DAT"]
            outfile = export_paths(self.export_folder, infile)
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)

    @unittest.skip("Skipping test to fix the issue.")
    def test_swmmflort(self):
        file = self.import_folder + r"\SWMMFLORT.DAT"
        if os.path.isfile(file):
            self.f2g.import_swmmflort()
            self.f2g.export_swmmflort(self.export_folder)
            infile = self.f2g.parser.dat_files["SWMMFLORT.DAT"]
            outfile = export_paths(self.export_folder, infile)
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)

    @unittest.skip("Skipping test to fix the issue.")
    def test_swmmoutf(self):  # TODO IMPROVE THIS CODE FOR WHEN WE HAVE -9999
        file = self.import_folder + r"\SWMMOUTF.DAT"
        if os.path.isfile(file):
            self.f2g.import_swmmoutf()
            self.f2g.export_swmmoutf(self.export_folder)
            infile = self.f2g.parser.dat_files["SWMMOUTF.DAT"]
            outfile = export_paths(self.export_folder, infile)
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)

    def test_xsec(self):
        file = self.import_folder + r"\XSEC.DAT"
        if os.path.isfile(file):
            self.f2g.import_xsec()
            self.f2g.export_xsec(self.export_folder)
            infile = self.f2g.parser.dat_files["XSEC.DAT"]
            outfile = export_paths(self.export_folder, infile)
            in_lines, out_lines = compare_files(infile, outfile)
            self.assertEqual(in_lines, out_lines)


if __name__ == "__main__":
    cases = [TestCompletedProjects]
    suite = unittest.TestSuite()
    for t in cases:
        tests = unittest.TestLoader().loadTestsFromTestCase(t)
        suite.addTest(tests)
    unittest.TextTestRunner(verbosity=2).run(suite)



