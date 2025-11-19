import os
import unittest

from flo2d.flo2d_ie.flo2dgeopackage import Flo2dGeoPackage
from flo2d.geopackage_utils import database_create
from flo2d.gui.dlg_export_multidomain import ExportMultipleDomainsDialog
from flo2d.gui.dlg_import_multidomain import ImportMultipleDomainsDialog

from test.utilities import get_qgis_app

QGIS_APP = get_qgis_app()
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
GLOBAL_DATA_DIR = os.path.join(THIS_DIR, "CompletedProjects", "GlobalSelfHelpKit")
IMPORT_A_DATA_DIR = os.path.join(THIS_DIR, "CompletedProjects", "MultipleDomainSelfHelpKit", 'a')
IMPORT_B_DATA_DIR = os.path.join(THIS_DIR, "CompletedProjects", "MultipleDomainSelfHelpKit", 'b')
IMPORT_C_DATA_DIR = os.path.join(THIS_DIR, "CompletedProjects", "MultipleDomainSelfHelpKit", 'c')
IMPORT_D_DATA_DIR = os.path.join(THIS_DIR, "CompletedProjects", "MultipleDomainSelfHelpKit", 'd')
IMPORT_E_DATA_DIR = os.path.join(THIS_DIR, "CompletedProjects", "MultipleDomainSelfHelpKit", 'e')
EXPORT_GLOBAL_DATA_DIR = os.path.join(THIS_DIR, "CompletedProjects", "GlobalSelfHelpKit", "export")
# IMPORT_MD_DATA_DIR = os.path.join(THIS_DIR, "CompletedProjects", "MultipleDomainSelfHelpKit")
# EXPORT_MD_DATA_DIR = os.path.join(THIS_DIR, "CompletedProjects", "MultipleDomainSelfHelpKit", "export")
CONT_A = os.path.join(IMPORT_A_DATA_DIR, "CONT.DAT")
CONT_B = os.path.join(IMPORT_B_DATA_DIR, "CONT.DAT")
CONT_C = os.path.join(IMPORT_C_DATA_DIR, "CONT.DAT")
CONT_D = os.path.join(IMPORT_D_DATA_DIR, "CONT.DAT")
CONT_E = os.path.join(IMPORT_E_DATA_DIR, "CONT.DAT")
# CONT = os.path.join(IMPORT_MD_DATA_DIR, "CONT.DAT")


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

def file_len(fname):
    """Return number of lines in a text file."""
    count = 0
    with open(fname, "r") as f:
        for _ in f:
            count += 1
    return count


class TestFlo2dGlobalSelfHelpKit(unittest.TestCase):
    con = database_create(":memory:")

    @classmethod
    def setUpClass(cls):
        os.makedirs(EXPORT_GLOBAL_DATA_DIR)
        cls.f2g = Flo2dGeoPackage(cls.con, None)
        cls.import_md = ImportMultipleDomainsDialog(cls.con, None, None)
        subdomains_path = [
            IMPORT_A_DATA_DIR,
            IMPORT_B_DATA_DIR,
            IMPORT_C_DATA_DIR,
            IMPORT_D_DATA_DIR,
            IMPORT_E_DATA_DIR,
        ]
        total_subdomains = len(subdomains_path)
        cls.import_md.import_global_domain(subdomains_path)

        # cls.f2g.disable_geom_triggers()
        # cls.f2g.set_parser(CONT)
        # cls.f2g.import_mannings_n_topo()
        # cls.f2g.import_swmminp()

    # @classmethod
    # def tearDownClass(cls):
    #     cls.con.close()
    #     for f in os.listdir(EXPORT_GLOBAL_DATA_DIR):
    #         fpath = os.path.join(EXPORT_GLOBAL_DATA_DIR, f)
    #         if os.path.isfile(fpath):
    #             os.remove(fpath)
    #         else:
    #             pass
    #     os.rmdir(EXPORT_GLOBAL_DATA_DIR)

    def test_global_arf(self):                                                        # Passed
        self.f2g.export_arf(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "ARF.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "ARF.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_global_chan(self):
        xs1 = self.f2g.execute("""SELECT fid, fcn, xlen FROM chan_elems WHERE fid = 42054;""").fetchone()
        self.assertEqual(xs1, (42054, 0.04, 30))
        xs2 = self.f2g.execute("""SELECT fid, fcn, xlen FROM chan_elems WHERE fid = 33446;""").fetchone()
        self.assertEqual(xs2, (33446, 0.04, 36.21))
        xs3 = self.f2g.execute("""SELECT fid, fcn, xlen FROM chan_elems WHERE fid = 26404;""").fetchone()
        self.assertEqual(xs3, (26404, 0.04, 42.43))
        xs4 = self.f2g.execute("""SELECT fid, fcn, xlen FROM chan_elems WHERE fid = 19838;""").fetchone()
        self.assertEqual(xs4, (19838, 0.04, 36.21))
        xs5 = self.f2g.execute("""SELECT fid, fcn, xlen FROM chan_elems WHERE fid = 156;""").fetchone()
        self.assertEqual(xs5, (156, 0.04, 30))

    def test_global_cont(self):                                                     # Failed (toler passes on its own)
        self.f2g.export_cont_toler(EXPORT_GLOBAL_DATA_DIR)
        infile1 = os.path.join(GLOBAL_DATA_DIR, "CONT.DAT")
        infile2 = os.path.join(GLOBAL_DATA_DIR, "TOLER.DAT")
        outfile1 = os.path.join(EXPORT_GLOBAL_DATA_DIR, "CONT.DAT")
        outfile2 = os.path.join(EXPORT_GLOBAL_DATA_DIR, "TOLER.DAT")
        in_cont, out_cont = compare_files(infile1, outfile1)
        in_toler, out_toler = compare_files(infile2, outfile2)
        self.assertEqual(in_cont, out_cont)
        self.assertEqual(in_toler, out_toler)

    def test_global_fpfroude(self):                                                  # Failed
        self.f2g.export_fpfroude(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "FPFROUDE.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "FPFROUDE.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_global_hystruc(self):                                                    # Passed
        self.f2g.export_hystruc(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "HYSTRUC.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "HYSTRUC.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_global_infil(self):                                                       # Passed
        self.f2g.export_infil(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "INFIL.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "INFIL.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_global_inlfow(self):                                                       # Failed (Not written)
        self.f2g.export_inflow(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "INFLOW.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "INFLOW.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_global_levee(self):                                                         # Failed
        self.f2g.export_levee(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "LEVEE.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "LEVEE.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_global_lid_volume(self):                                                     # Passed
        self.f2g.export_lid_volume(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "LID_VOLUME.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "LID_VOLUME.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_global_mannings_n_topo(self):                                                # passed
        self.f2g.export_mannings_n_topo(EXPORT_GLOBAL_DATA_DIR)
        infile1 = os.path.join(GLOBAL_DATA_DIR, "MANNINGS_N.DAT")
        infile2 = os.path.join(GLOBAL_DATA_DIR, "TOPO.DAT")
        outfile1 = os.path.join(EXPORT_GLOBAL_DATA_DIR, "MANNINGS_N.DAT")
        outfile2 = os.path.join(EXPORT_GLOBAL_DATA_DIR, "TOPO.DAT")
        in_man, out_man = compare_files(infile1, outfile1)
        in_topo, out_topo = compare_files(infile2, outfile2)
        self.assertEqual(in_man, out_man)
        self.assertEqual(in_topo, out_topo)

    def test_global_rain(self):
        ok = self.f2g.export_rain(EXPORT_GLOBAL_DATA_DIR)
        print("export_rain returned:", ok)

        rain_path = os.path.join(EXPORT_GLOBAL_DATA_DIR, "RAIN.DAT")
        print("RAIN exists:", os.path.exists(rain_path))

        infile = os.path.join(GLOBAL_DATA_DIR, "RAIN.DAT")
        outfile = rain_path
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_global_sdclogging(self):                                                    # Failed (Lines interchanged)
        self.f2g.export_sdclogging(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "SDCLOGGING.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "SDCLOGGING.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_global_shallown(self):                                                       # Passed
        self.f2g.export_shallowNSpatial(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "SHALLOWN_SPATIAL.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "SHALLOWN_SPATIAL.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_global_swmmflo(self):                                                        # Passed
        self.f2g.export_swmmflo(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "SWMMFLO.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "SWMMFLO.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_global_swmmflodropbox(self):                                                 # Failed
        self.f2g.export_swmmflodropbox(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "SWMMFLODROPBOX.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "SWMMFLODROPBOX.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_global_swmmflort(self):                                                     # Failed
        self.f2g.export_swmmflort(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "SWMMFLORT.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "SWMMFLORT.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_global_swmmoutf(self):                                                      # Failed
        self.f2g.export_swmmoutf(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "SWMMOUTF.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "SWMMOUTF.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_global_tolspatial(self):                                                    # Failed
        self.f2g.export_tolspatial(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "TOLSPATIAL.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "TOLSPATIAL.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    def test_global_xsec(self):                                                          # Passed
        self.f2g.export_xsec(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "XSEC.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "XSEC.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)

    @unittest.skip("takes too long")
    def test_global_rain(self):                                                          # Failed (Hangs)
        self.f2g.export_rain(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "RAIN.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "RAIN.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)