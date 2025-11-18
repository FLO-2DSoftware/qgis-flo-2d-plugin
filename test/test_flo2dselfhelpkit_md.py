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

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        for f in os.listdir(EXPORT_GLOBAL_DATA_DIR):
            fpath = os.path.join(EXPORT_GLOBAL_DATA_DIR, f)
            if os.path.isfile(fpath):
                os.remove(fpath)
            else:
                pass
        os.rmdir(EXPORT_GLOBAL_DATA_DIR)

    def test_global_arf(self):
        self.f2g.export_arf(EXPORT_GLOBAL_DATA_DIR)
        infile = os.path.join(GLOBAL_DATA_DIR, "ARF.DAT")
        outfile = os.path.join(EXPORT_GLOBAL_DATA_DIR, "ARF.DAT")
        in_lines, out_lines = compare_files(infile, outfile)
        self.assertEqual(in_lines, out_lines)