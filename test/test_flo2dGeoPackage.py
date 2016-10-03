import os
import sys
import unittest
sys.path.append(os.path.join('..', 'flo2d'))
from flo2d.flo2dgeopackage import Flo2dGeoPackage

THIS_DIR = os.path.dirname(__file__)
IMPORT_DATA_DIR = os.path.join(THIS_DIR, 'data', 'import')
EXPORT_DATA_DIR = os.path.join(THIS_DIR, 'data', 'export')
GPKG_PATH = os.path.join(THIS_DIR, 'data', 'test.gpkg')
CONT = os.path.join(IMPORT_DATA_DIR, 'CONT.DAT')


class TestFlo2dGeoPackage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.f2g = Flo2dGeoPackage(GPKG_PATH, None)
        cls.f2g.database_create()
        cls.f2g.set_parser(CONT)
        cls.f2g.import_mannings_n_topo()

    @classmethod
    def tearDownClass(cls):
        os.remove(GPKG_PATH)

    def setUp(self):
        self.f2g.database_connect()

    def tearDown(self):
        self.f2g.database_disconnect()

    def test_set_parser(self):
        self.assertIsNotNone(self.f2g.parser.dat_files['CONT.DAT'])
        self.assertIsNotNone(self.f2g.parser.dat_files['TOLER.DAT'])

    def test_import_cont_toler(self):
        self.f2g.import_cont_toler()
        self.assertFalse(self.f2g.is_table_empty('cont'))
        controls = self.f2g.execute('''SELECT name, value FROM cont;''').fetchall()
        self.assertDictContainsSubset({'build': 'Pro Model - Build No. 15.07.12'}, dict(controls))
        self.assertEqual(len(controls), 44)

    def test_import_mannings_n_topo(self):
        cellsize = self.f2g.execute('''SELECT value FROM cont WHERE name = 'CELLSIZE';''').fetchone()[0]
        self.assertEqual(float(cellsize), 100)
        rows = self.f2g.execute('''SELECT COUNT(fid) FROM grid;''').fetchone()[0]
        self.assertEqual(float(rows), 9205)
        n_value = self.f2g.execute('''SELECT fid FROM grid WHERE n_value > 1;''').fetchone()
        self.assertIsNone(n_value)
        elevation = self.f2g.execute('''SELECT fid FROM grid WHERE elevation IS NULL;''').fetchone()
        self.assertIsNone(elevation)

    def test_import_inflow(self):
        self.f2g.clear_tables('inflow')
        self.f2g.import_inflow()
        rows = self.f2g.execute('''SELECT time_series_fid FROM inflow;''').fetchall()
        self.assertEqual(len(rows), 4)
        self.assertListEqual([(1,), (2,), (3,), (4,)], rows)

    def test_import_outflow(self):
        self.f2g.import_outflow()
        hydrographs = self.f2g.execute('''SELECT COUNT(fid) FROM outflow_hydrographs;''').fetchone()[0]
        self.assertEqual(float(hydrographs), 8)
        outflow = self.f2g.execute('''SELECT ident FROM outflow;''').fetchall()
        self.assertListEqual([('K',), ('K',), ('K',), ('N',)], outflow)
        qh_params = self.f2g.execute('''SELECT coef FROM qh_params;''').fetchone()[0]
        self.assertEqual(float(qh_params), 2.6)

    def test_import_rain(self):
        self.f2g.import_rain()
        tot = self.f2g.execute('''SELECT tot_rainfall FROM rain;''').fetchone()[0]
        self.assertEqual(float(tot), 3.10)

    def test_import_infil(self):
        self.f2g.import_infil()
        scsnall = self.f2g.execute('''SELECT scsnall FROM infil;''').fetchone()[0]
        self.assertEqual(float(scsnall), 99)
        areas = self.f2g.execute('''SELECT COUNT(fid) FROM infil_areas_green;''').fetchone()[0]
        cells = self.f2g.execute('''SELECT COUNT(fid) FROM infil_cells_green;''').fetchone()[0]
        self.assertEqual(int(areas), int(cells))

    def test_import_evapor(self):
        self.f2g.import_evapor()
        months = self.f2g.execute('''SELECT month FROM evapor_monthly;''').fetchall()
        self.assertEqual(len(months), 12)
        mon = self.f2g.execute('''SELECT month FROM evapor_monthly WHERE monthly_evap = 5.57;''').fetchone()[0]
        self.assertEqual(mon, 'september')

    def test_import_chan(self):
        self.f2g.import_chan()
        nelem = self.f2g.execute('''SELECT fcn FROM chan_elems WHERE fid = 7667;''').fetchone()[0]
        self.assertEqual(nelem, 0.055)
        nxsec = self.f2g.execute('''SELECT nxsecnum FROM chan_n WHERE elem_fid = 7667;''').fetchone()[0]
        self.assertEqual(nxsec, 107)

    def test_import_xsec(self):
        self.f2g.import_chan()
        self.f2g.import_xsec()
        nxsec = self.f2g.execute('''SELECT COUNT(nxsecnum) FROM chan_n;''').fetchone()[0]
        xsec = self.f2g.execute('''SELECT COUNT(DISTINCT chan_n_nxsecnum) FROM xsec_n_data;''').fetchone()[0]
        self.assertEqual(nxsec, xsec)

    def test_import_hystruc(self):
        self.f2g.import_hystruc()
        rrows = self.f2g.execute('''SELECT COUNT(fid) FROM repl_rat_curves;''').fetchone()[0]
        self.assertEqual(rrows, 1)
        frow = self.f2g.execute('''SELECT structname FROM struct WHERE type = 'F';''').fetchone()[0]
        self.assertEqual(frow, 'CulvertA')

    def test_import_street(self):
        self.f2g.import_street()
        seg = self.f2g.execute('''SELECT DISTINCT str_fid FROM street_seg;''').fetchall()
        streets = self.f2g.execute('''SELECT fid FROM streets;''').fetchall()
        self.assertEqual(len(seg), len(streets))

    def test_import_arf(self):
        self.f2g.import_arf()
        bt = self.f2g.execute('''SELECT COUNT(fid) FROM blocked_areas;''').fetchone()[0]
        b = self.f2g.execute('''SELECT COUNT(fid) FROM blocked_cells WHERE area_fid IS NULL;''').fetchone()[0]
        self.assertEqual(bt + b, 15)

    def test_import_mult(self):
        self.f2g.import_mult()
        areas = self.f2g.execute('''SELECT COUNT(fid) FROM mult_areas;''').fetchone()[0]
        self.assertEqual(areas, 17)
        cells = self.f2g.execute('''SELECT COUNT(fid) FROM mult_cells;''').fetchone()[0]
        self.assertEqual(areas, cells)

    def test_import_sed(self):
        self.f2g.import_sed()
        ndata = self.f2g.execute('''SELECT COUNT(fid) FROM sed_supply_frac_data;''').fetchone()[0]
        self.assertEqual(ndata, 9)
        nrow = self.f2g.execute('''SELECT COUNT(fid) FROM sed_supply_frac;''').fetchone()[0]
        self.assertEqual(ndata, nrow)

    def test_import_levee(self):
        self.f2g.import_levee()
        sides = self.f2g.execute('''SELECT COUNT(fid) FROM levee_data;''').fetchone()[0]
        self.assertEqual(sides, 12)
        levfragprob = self.f2g.execute('''SELECT SUM(levfragprob) FROM levee_fragility;''').fetchone()[0]
        self.assertEqual(round(levfragprob, 1), 4.9)
        gfragchar = self.f2g.execute('''SELECT gfragchar FROM levee_general;''').fetchone()[0]
        self.assertEqual(gfragchar, 'FS3')

    def test_import_fpxsec(self):
        self.f2g.import_fpxsec()
        fpxsec = self.f2g.execute('''SELECT COUNT(fid) FROM fpxsec;''').fetchone()[0]
        self.assertEqual(fpxsec, 10)

    def test_import_breach(self):
        self.f2g.import_breach()
        brbottomel = self.f2g.execute('''SELECT brbottomel FROM breach;''').fetchone()[0]
        self.assertEqual(brbottomel, 83.25)
        frag = self.f2g.execute('''SELECT COUNT(fid) FROM breach_fragility_curves;''').fetchone()[0]
        self.assertEqual(frag, 11)
        bglob = self.f2g.execute('''SELECT * FROM breach_global;''').fetchone()
        self.assertNotIn(None, bglob)
        gid = self.f2g.execute('''SELECT grid_fid FROM breach_cells;''').fetchone()
        self.assertTupleEqual(gid, (4015,))

    def test_import_fpfroude(self):
        self.f2g.import_fpfroude()
        count = self.f2g.execute('''SELECT COUNT(fid) FROM fpfroude;''').fetchone()[0]
        self.assertEqual(count, 8)

    def test_import_swmmflo(self):
        self.f2g.import_swmmflo()
        count = self.f2g.execute('''SELECT COUNT(fid) FROM swmmflo;''').fetchone()[0]
        self.assertEqual(count, 6)
        length = self.f2g.execute('''SELECT MAX(swmm_length) FROM swmmflo;''').fetchone()[0]
        self.assertEqual(length, 20)

    def test_import_swmmflort(self):
        self.f2g.import_swmmflort()
        fids = self.f2g.execute('''SELECT fid FROM swmmflort;''').fetchall()
        dist_fids = self.f2g.execute('''SELECT DISTINCT swmm_rt_fid FROM swmmflort_data;''').fetchall()
        self.assertListEqual(fids, dist_fids)

    def test_import_swmmoutf(self):
        self.f2g.import_swmmoutf()
        expected = [(1492, 'OUTFALL1', 1)]
        row = self.f2g.execute('''SELECT grid_fid, name, outf_flo FROM swmmoutf;''').fetchall()
        self.assertListEqual(row, expected)

    def test_import_tolspatial(self):
        self.f2g.import_tolspatial()
        count = self.f2g.execute('''SELECT COUNT(fid) FROM tolspatial;''').fetchone()[0]
        self.assertEqual(count, 4)

    def test_import_wsurf(self):
        self.f2g.import_wsurf()
        count = self.f2g.execute('''SELECT COUNT(fid) FROM wsurf;''').fetchone()[0]
        self.assertEqual(count, 10)
        with open(self.f2g.parser.dat_files['WSURF.DAT']) as w:
            head = w.readline()
            self.assertEqual(int(head), count)

    def test_import_wstime(self):
        self.f2g.import_wstime()
        count = self.f2g.execute('''SELECT COUNT(fid) FROM wstime;''').fetchone()[0]
        self.assertEqual(count, 10)
        with open(self.f2g.parser.dat_files['WSTIME.DAT']) as w:
            head = w.readline()
            self.assertEqual(int(head), count)

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
