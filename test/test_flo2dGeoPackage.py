import os
import sys
import unittest
sys.path.append(os.path.join('..', 'flo2d'))
from qgis.core import *
from utilities import get_qgis_app
from flo2d.flo2dgeopackage import *
from flo2d.grid_tools import build_grid

QGIS_APP = get_qgis_app()
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
IMPORT_DATA_DIR = os.path.join(THIS_DIR, 'data', 'import')
VECTOR_PATH = os.path.join(THIS_DIR, 'data', 'vector', 'boundary.shp')
EXPORT_DATA_DIR = os.path.join(THIS_DIR, 'data')
GPKG_PATH = os.path.join(THIS_DIR, 'data', 'test.gpkg')
CONT = os.path.join(IMPORT_DATA_DIR, 'CONT.DAT')


def file_len(fname):
    i = 0
    with open(fname) as f:
        for i, l in enumerate(f, 1):
            pass
    return i


def export_paths(*inpaths):
    paths = [os.path.join(EXPORT_DATA_DIR, os.path.basename(inpath)) for inpath in inpaths]
    if len(paths) == 1:
        paths = paths[0]
    else:
        pass
    return paths


class TestFlo2dGeoPackage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        con = database_create(GPKG_PATH)
        cls.f2g = Flo2dGeoPackage(con, None)
        cls.f2g.set_parser(CONT)
        cls.f2g.import_mannings_n_topo()
        con.close()

    @classmethod
    def tearDownClass(cls):
        for f in os.listdir(EXPORT_DATA_DIR):
            fpath = os.path.join(EXPORT_DATA_DIR, f)
            if os.path.isfile(fpath):
                os.remove(fpath)
            else:
                pass

    def setUp(self):
        self.f2g.con = database_connect(GPKG_PATH)

    def tearDown(self):
        database_disconnect(self.f2g.con)

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

    @unittest.skip('Skip outflow')
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

    def test_export_cont(self):
        self.f2g.import_cont_toler()
        self.f2g.export_cont_toler(EXPORT_DATA_DIR)
        infile1 = self.f2g.parser.dat_files['CONT.DAT']
        infile2 = self.f2g.parser.dat_files['TOLER.DAT']
        outfile1, outfile2 = export_paths(infile1, infile2)
        self.assertEqual(file_len(infile1), file_len(outfile1))
        self.assertEqual(file_len(infile2), file_len(outfile2))

    def test_export_mannings_n_topo(self):
        self.f2g.import_mannings_n_topo()
        self.f2g.export_mannings_n_topo(EXPORT_DATA_DIR)
        infile1 = self.f2g.parser.dat_files['MANNINGS_N.DAT']
        infile2 = self.f2g.parser.dat_files['TOPO.DAT']
        outfile1, outfile2 = export_paths(infile1, infile2)
        iman = file_len(infile1)
        itopo = file_len(infile2)
        eman = file_len(outfile1)
        etopo = file_len(outfile2)
        self.assertEqual(iman, itopo)
        self.assertEqual(iman, eman)
        self.assertEqual(itopo, etopo)
        self.assertEqual(eman, etopo)

    def test_export_inflow(self):
        self.f2g.import_inflow()
        self.f2g.export_inflow(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['INFLOW.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    @unittest.skip('Skip outflow')
    def test_export_outflow(self):
        self.f2g.import_outflow()
        self.f2g.export_outflow(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['OUTFLOW.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_rain(self):
        self.f2g.import_rain()
        self.f2g.export_rain(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['RAIN.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_infil(self):
        self.f2g.import_infil()
        self.f2g.export_infil(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['INFIL.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_evapor(self):
        self.f2g.import_evapor()
        self.f2g.export_evapor(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['EVAPOR.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_chan(self):
        self.f2g.import_chan()
        self.f2g.export_chan(EXPORT_DATA_DIR)
        infile1 = self.f2g.parser.dat_files['CHAN.DAT']
        infile2 = self.f2g.parser.dat_files['CHANBANK.DAT']
        outfile1, outfile2 = export_paths(infile1, infile2)
        in1 = file_len(infile1)
        in2 = file_len(infile2)
        out1 = file_len(outfile1)
        out2 = file_len(outfile2)
        self.assertEqual(in1, out1)
        self.assertEqual(in2, out2)

    def test_export_xsec(self):
        self.f2g.import_xsec()
        self.f2g.export_xsec(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['XSEC.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_hystruc(self):
        self.f2g.import_hystruc()
        self.f2g.export_hystruc(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['HYSTRUC.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_street(self):
        self.f2g.import_street()
        self.f2g.export_street(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['STREET.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_arf(self):
        self.f2g.import_arf()
        self.f2g.export_arf(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['ARF.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_mult(self):
        self.f2g.import_mult()
        self.f2g.export_mult(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['MULT.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_sed(self):
        self.f2g.import_sed()
        self.f2g.export_sed(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['SED.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_levee(self):
        self.f2g.import_levee()
        self.f2g.export_levee(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['LEVEE.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_fpxsec(self):
        self.f2g.import_fpxsec()
        self.f2g.export_fpxsec(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['FPXSEC.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_breach(self):
        self.f2g.import_breach()
        self.f2g.export_breach(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['BREACH.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_fpfroude(self):
        self.f2g.import_fpfroude()
        self.f2g.export_fpfroude(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['FPFROUDE.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_swmmflo(self):
        self.f2g.import_swmmflo()
        self.f2g.export_swmmflo(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['SWMMFLO.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_swmmflort(self):
        self.f2g.import_swmmflort()
        self.f2g.export_swmmflort(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['SWMMFLORT.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_swmmoutf(self):
        self.f2g.import_swmmoutf()
        self.f2g.export_swmmoutf(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['SWMMOUTF.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_tolspatial(self):
        self.f2g.import_tolspatial()
        self.f2g.export_tolspatial(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['TOLSPATIAL.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_wsurf(self):
        self.f2g.import_wsurf()
        self.f2g.export_wsurf(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['WSURF.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)

    def test_export_wstime(self):
        self.f2g.import_wstime()
        self.f2g.export_wstime(EXPORT_DATA_DIR)
        infile = self.f2g.parser.dat_files['WSTIME.DAT']
        outfile = export_paths(infile)
        in_len, out_len = file_len(infile), file_len(outfile)
        self.assertEqual(in_len, out_len)


class TestGridTools(unittest.TestCase):

    def test_build_grid(self):
        boundary = os.path.join(VECTOR_PATH)
        vlayer = QgsVectorLayer(boundary, 'bl', 'ogr')
        self.assertIsInstance(vlayer, QgsVectorLayer)
        polygons = list(build_grid(vlayer, 500))
        self.assertEqual(len(polygons), 494)


# Running tests:
if __name__ == '__main__':
    cases = [TestFlo2dGeoPackage, TestGridTools]
    suite = unittest.TestSuite()
    for t in cases:
        tests = unittest.TestLoader().loadTestsFromTestCase(t)
        suite.addTest(tests)
    unittest.TextTestRunner(verbosity=2).run(suite)

