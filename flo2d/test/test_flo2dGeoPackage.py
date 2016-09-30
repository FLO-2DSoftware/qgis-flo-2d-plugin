import os
import sys
import unittest
sys.path.append('..')
from flo2d.flo2dgeopackage import Flo2dGeoPackage

THIS_DIR = os.path.dirname(__file__)
IMPORT_DATA_DIR = os.path.join(THIS_DIR, 'data', 'import')
EXPORT_DATA_DIR = os.path.join(THIS_DIR, 'data', 'export')
GPKG_PATH = os.path.join(THIS_DIR, 'data', 'test.gpkg')
CONT = os.path.join(IMPORT_DATA_DIR, 'CONT.DAT')


class TestFlo2dGeoPackage(unittest.TestCase):
    f2g = Flo2dGeoPackage(GPKG_PATH, None)
    f2g.database_create()

    def setUp(self):
        self.f2g.set_parser(CONT)
        self.f2g.database_connect()

    def tearDown(self):
        self.f2g.database_disconnect()

    def test_set_parser(self):
        self.f2g.set_parser(CONT)
        self.assertIsNotNone(self.f2g.parser.dat_files['CONT.DAT'])
        self.assertIsNotNone(self.f2g.parser.dat_files['TOLER.DAT'])

    def test_import_cont_toler(self):
        self.f2g.import_cont_toler()
        self.assertFalse(self.f2g.is_table_empty('cont'))
        controls = self.f2g.execute('''SELECT name, value FROM cont;''').fetchall()
        self.assertDictContainsSubset({'build': 'Pro Model - Build No. 15.07.12'}, dict(controls))
        self.assertEqual(len(controls), 44)

    def test_import_mannings_n_topo(self):
        self.f2g.import_mannings_n_topo()
        cellsize = self.f2g.execute('''SELECT value FROM cont WHERE name = 'CELLSIZE';''').fetchone()[0]
        self.assertEqual(float(cellsize), 100)
        rows = self.f2g.execute('''SELECT COUNT(fid) FROM grid;''').fetchone()[0]
        self.assertEqual(float(rows), 9205)
        n_value = self.f2g.execute('''SELECT fid FROM grid WHERE n_value > 1;''').fetchone()
        self.assertIsNone(n_value)
        elevation = self.f2g.execute('''SELECT fid FROM grid WHERE elevation IS NULL;''').fetchone()
        self.assertIsNone(elevation)

    def test_import_inflow(self):
        self.f2g.import_mannings_n_topo()
        self.f2g.clear_tables('inflow')
        self.f2g.import_inflow()
        rows = self.f2g.execute('''SELECT time_series_fid FROM inflow;''').fetchall()
        self.assertEqual(len(rows), 4)
        self.assertListEqual([(1,), (2,), (3,), (4,)], rows)

    def test_import_outflow(self):
        self.f2g.import_mannings_n_topo()
        self.f2g.import_outflow()
        hydrographs = self.f2g.execute('''SELECT COUNT(fid) FROM outflow_hydrographs;''').fetchone()[0]
        self.assertEqual(float(hydrographs), 8)
        outflow = self.f2g.execute('''SELECT ident FROM outflow;''').fetchall()
        self.assertListEqual([('K',), ('K',), ('K',), ('N',)], outflow)
        qh_params = self.f2g.execute('''SELECT coef FROM qh_params;''').fetchone()[0]
        self.assertEqual(float(qh_params), 2.6)

    def test_import_rain(self):
        self.f2g.import_mannings_n_topo()
        self.f2g.import_rain()
        tot = self.f2g.execute('''SELECT tot_rainfall FROM rain;''').fetchone()[0]
        self.assertEqual(float(tot), 3.10)

    def test_import_infil(self):
        self.f2g.import_mannings_n_topo()
        self.f2g.import_infil()
        scsnall = self.f2g.execute('''SELECT scsnall FROM infil;''').fetchone()[0]
        self.assertEqual(float(scsnall), 99)
        areas = self.f2g.execute('''SELECT COUNT(fid) FROM infil_areas_green;''').fetchone()[0]
        cells = self.f2g.execute('''SELECT COUNT(fid) FROM infil_cells_green;''').fetchone()[0]
        self.assertEqual(int(areas), int(cells))

    def test_import_evapor(self):
        self.f2g.import_mannings_n_topo()
        self.f2g.import_evapor()
        months = self.f2g.execute('''SELECT month FROM evapor_monthly;''').fetchall()
        self.assertEqual(len(months), 12)
        mon = self.f2g.execute('''SELECT month FROM evapor_monthly WHERE monthly_evap = 5.57;''').fetchone()[0]
        self.assertEqual(mon, 'september')

    def test_import_chan(self):
        self.f2g.import_mannings_n_topo()
        self.f2g.import_chan()
        nelem = self.f2g.execute('''SELECT fcn FROM chan_elems WHERE fid = 7667;''').fetchone()[0]
        self.assertEqual(nelem, 0.055)
        nxsec = self.f2g.execute('''SELECT nxsecnum FROM chan_n WHERE elem_fid = 7667;''').fetchone()[0]
        self.assertEqual(nxsec, 107)

    def test_import_xsec(self):
        self.f2g.import_mannings_n_topo()
        self.f2g.import_chan()
        self.f2g.import_xsec()
        nxsec = self.f2g.execute('''SELECT COUNT(nxsecnum) FROM chan_n;''').fetchone()[0]
        xsec = self.f2g.execute('''SELECT COUNT(DISTINCT chan_n_nxsecnum) FROM xsec_n_data;''').fetchone()[0]
        self.assertEqual(nxsec, xsec)

    # def test_import_hystruc(self):
    #     self.fail()
    #
    # def test_import_street(self):
    #     self.fail()
    #
    # def test_import_arf(self):
    #     self.fail()
    #
    # def test_import_mult(self):
    #     self.fail()
    #
    # def test_import_sed(self):
    #     self.fail()
    #
    # def test_import_levee(self):
    #     self.fail()
    #
    # def test_import_fpxsec(self):
    #     self.fail()
    #
    # def test_import_breach(self):
    #     self.fail()
    #
    # def test_import_fpfroude(self):
    #     self.fail()
    #
    # def test_import_swmmflo(self):
    #     self.fail()
    #
    # def test_import_swmmflort(self):
    #     self.fail()
    #
    # def test_import_swmmoutf(self):
    #     self.fail()
    #
    # def test_import_tolspatial(self):
    #     self.fail()
    #
    # def test_import_wsurf(self):
    #     self.fail()
    #
    # def test_import_wstime(self):
    #     self.fail()
    #
    # def test_export_cont(self):
    #     self.fail()
    #
    # def test_export_mannings_n_topo(self):
    #     self.fail()
    #
    # def test_export_inflow(self):
    #     self.fail()
    #
    # def test_export_outflow(self):
    #     self.fail()
    #
    # def test_export_rain(self):
    #     self.fail()
    #
    # def test_export_infil(self):
    #     self.fail()
    #
    # def test_export_evapor(self):
    #     self.fail()
    #
    # def test_export_chan(self):
    #     self.fail()
    #
    # def test_export_xsec(self):
    #     self.fail()
    #
    # def test_export_hystruc(self):
    #     self.fail()
    #
    # def test_export_street(self):
    #     self.fail()
    #
    # def test_export_arf(self):
    #     self.fail()
    #
    # def test_export_mult(self):
    #     self.fail()
    #
    # def test_export_sed(self):
    #     self.fail()
    #
    # def test_export_levee(self):
    #     self.fail()
    #
    # def test_export_fpxsec(self):
    #     self.fail()
    #
    # def test_export_breach(self):
    #     self.fail()
    #
    # def test_export_fpfroude(self):
    #     self.fail()
    #
    # def test_export_swmmflo(self):
    #     self.fail()
    #
    # def test_export_swmmflort(self):
    #     self.fail()
    #
    # def test_export_swmmoutf(self):
    #     self.fail()
    #
    # def test_export_tolspatial(self):
    #     self.fail()
    #
    # def test_export_wsurf(self):
    #     self.fail()
    #
    # def test_export_wstime(self):
    #     self.fail()


# Running tests:
if __name__ == '__main__':
    cases = [TestFlo2dGeoPackage]
    suite = unittest.TestSuite()
    for t in cases:
        tests = unittest.TestLoader().loadTestsFromTestCase(t)
        suite.addTest(tests)
    unittest.TextTestRunner(verbosity=2).run(suite)
