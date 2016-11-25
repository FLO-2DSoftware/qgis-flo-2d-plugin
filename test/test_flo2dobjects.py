# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import sys
import unittest
from itertools import chain
sys.path.append(os.path.join('..', 'flo2d'))
from flo2d.geopackage_utils import *
from flo2d.flo2dobjects import *
from flo2d.flo2dgeopackage import Flo2dGeoPackage

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
IMPORT_DATA_DIR = os.path.join(THIS_DIR, 'data', 'import')
CONT = os.path.join(IMPORT_DATA_DIR, 'CONT.DAT')


class TestCrossSection(unittest.TestCase):
    con = database_create(":memory:")

    @classmethod
    def setUpClass(cls):
        cls.f2g = Flo2dGeoPackage(cls.con, None)
        cls.f2g.set_parser(CONT)
        cls.f2g.import_mannings_n_topo()
        cls.f2g.import_chan()
        cls.f2g.import_xsec()

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def setUp(self):
        self.cross_section = CrossSection(374, self.con, None)

    def test_get_row(self):
        row = self.cross_section.get_row()
        self.assertEqual(row['fcn'], 0.04)
        self.assertEqual(row['xlen'], 110)
        self.assertEqual(row['type'], 'N')

    def test_get_chan_segment(self):
        self.cross_section.get_row()
        chan = self.cross_section.get_chan_segment()
        self.assertEqual(chan['froudc'], 0.5)

    def test_get_chan_table(self):
        self.cross_section.get_row()
        chan_tab = self.cross_section.get_chan_table()
        self.assertEqual(chan_tab['xsecname'], 'AW735.2X')

    def test_get_xsec_data(self):
        self.cross_section.get_row()
        self.cross_section.get_chan_table()
        xsec = self.cross_section.get_xsec_data()
        self.assertEqual(len(xsec), 27)


class TestInflow(unittest.TestCase):
    con = database_create(":memory:")

    @classmethod
    def setUpClass(cls):
        cls.f2g = Flo2dGeoPackage(cls.con, None)
        cls.f2g.set_parser(CONT)
        cls.f2g.import_mannings_n_topo()
        cls.f2g.import_inflow()

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def setUp(self):
        self.inflow = Inflow(1, self.con, None)

    def test_get_row(self):
        row = self.inflow.get_row()
        self.assertEqual(row['ident'], 'C')

    def test_get_time_series(self):
        self.inflow.get_row()
        ts = self.inflow.get_time_series()
        self.assertEqual(len(ts), 4)

    def test_get_time_series_data(self):
        self.inflow.get_row()
        tsd = self.inflow.get_time_series_data()
        self.assertEqual(len(tsd), 601)


class TestOutflow(unittest.TestCase):
    con = database_create(":memory:")

    @classmethod
    def setUpClass(cls):
        cls.f2g = Flo2dGeoPackage(cls.con, None)
        cls.f2g.set_parser(CONT)
        cls.f2g.import_mannings_n_topo()
        cls.f2g.import_outflow()

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def setUp(self):
        self.outflow = Outflow(3, self.con, None)

    def test_get_row(self):
        row = self.outflow.get_row()
        self.assertEqual(row['chan_out'], 0)
        self.assertEqual(row['fp_out'], 1)
        self.assertEqual(row['type'], 7)

    def test_get_time_series(self):
        self.outflow.get_row()
        ts = self.outflow.get_time_series()
        self.assertEqual(len(ts), 3)

    def test_get_qh_params(self):
        self.outflow.get_row()
        qhp = self.outflow.get_qh_params()
        self.assertEqual(len(qhp), 1)

    def test_get_qh_tables(self):
        self.outflow.get_row()
        qht = self.outflow.get_qh_tables()
        self.assertListEqual(qht, [(1, None)])

    def test_get_data_fid_name(self):
        self.outflow.get_row()
        self.assertEqual(self.outflow.get_data_fid_name(), self.outflow.get_time_series())

    def test_clear_data_fids(self):
        self.outflow.get_row()
        self.outflow.clear_data_fids()
        fids = (
            self.outflow.chan_tser_fid,
            self.outflow.fp_tser_fid,
            self.outflow.chan_qhpar_fid,
            self.outflow.chan_qhtab_fid
        )
        self.assertTupleEqual(fids, (None, None, None, None))

    def test_set_new_data_fid(self):
        self.outflow.get_row()
        self.outflow.set_new_data_fid(123)
        self.assertEqual(self.outflow.fp_tser_fid, 123)

    def test_get_time_series_data(self):
        self.outflow.get_row()
        self.outflow.get_time_series()
        data = self.outflow.get_time_series_data()
        self.assertEqual(len(data), 5)

    def test_get_qh_params_data(self):
        self.outflow.get_row()
        self.outflow.get_qh_params()
        data = self.outflow.get_qh_params_data()
        self.assertListEqual(data, [(5.0, 1.0, 6.0), (10.0, 2.0, 7.0), (20.0, 3.0, 8.0)])

    def test_get_qh_table_data(self):
        self.outflow.get_row()
        self.outflow.get_qh_tables()
        data = self.outflow.get_qh_table_data()
        self.assertFalse(all(chain.from_iterable(data)))

    def test_get_data(self):
        self.outflow.get_row()
        self.outflow.get_data_fid_name()
        data = self.outflow.get_data()
        self.assertEqual(len(data), 5)


class TestRain(unittest.TestCase):
    con = database_create(":memory:")

    @classmethod
    def setUpClass(cls):
        cls.f2g = Flo2dGeoPackage(cls.con, None)
        cls.f2g.set_parser(CONT)
        cls.f2g.import_mannings_n_topo()
        cls.f2g.import_rain()

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def setUp(self):
        self.rain = Rain(self.con, None)

    def test_get_row(self):
        row = self.rain.get_row()
        self.assertEqual(row['tot_rainfall'], 3.1)

    def test_get_time_series(self):
        self.rain.get_row()
        ts = self.rain.get_time_series()
        self.assertEqual(len(ts), 1)

    def test_get_time_series_data(self):
        self.rain.get_row()
        tsd = self.rain.get_time_series_data()
        self.assertEqual(len(tsd), 5)


class TestEvaporation(unittest.TestCase):
    con = database_create(":memory:")

    @classmethod
    def setUpClass(cls):
        cls.f2g = Flo2dGeoPackage(cls.con, None)
        cls.f2g.set_parser(CONT)
        cls.f2g.import_evapor()

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def setUp(self):
        self.evaporation = Evaporation(self.con, None)

    def test_get_row(self):
        row = self.evaporation.get_row()
        self.assertEqual(row['ievapmonth'], 5)

    def test_get_monthly(self):
        monthly = self.evaporation.get_monthly()
        self.assertEqual(len(monthly), 12)

    def test_get_hourly(self):
        hourly = self.evaporation.get_hourly()
        self.assertEqual(len(hourly), 24)

    def test_get_hourly_sum(self):
        self.assertEqual(self.evaporation.get_hourly_sum(), 1)


# Running tests:
if __name__ == '__main__':
    cases = [
        TestCrossSection,
        TestInflow,
        TestOutflow,
        TestRain,
        TestEvaporation
    ]
    suite = unittest.TestSuite()
    for t in cases:
        tests = unittest.TestLoader().loadTestsFromTestCase(t)
        suite.addTest(tests)
    unittest.TextTestRunner(verbosity=2).run(suite)
