# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Flo2D
                                 A QGIS plugin
 FLO-2D tools for QGIS
                             -------------------
        begin                : 2016-08-28
        copyright            : (C) 2016 by Lutra Consulting for FLO-2D
        email                : info@lutraconsulting.co.uk
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 FLO-2D Preprocessor tools for QGIS.
"""
from collections import OrderedDict
from flo2dgeopackage import GeoPackageUtils


class CrossSection(GeoPackageUtils):
    columns = ['fid', 'seg_fid', 'nr_in_seg', 'rbankgrid', 'fcn', 'xlen', 'type', 'notes', 'geom']

    def __init__(self, fid, con, iface):
        super(CrossSection, self).__init__(con, iface)
        self.fid = fid
        self.row = None
        self.type = None
        self.chan = None
        self.chan_tab = None
        self.xsec = None

    def get_row(self):
        qry = 'SELECT * FROM chan_elems WHERE fid = ?;'
        values = [x if x is not None else '' for x in self.execute(qry, (self.fid,)).fetchone()]
        self.row = OrderedDict(zip(self.columns, values))
        self.type = self.row['type']
        return self.row

    def get_chan_segment(self):
        if self.row is not None:
            pass
        else:
            return
        seg_fid = self.row['seg_fid']
        args = self.table_info('chan', only_columns=True)
        qry = 'SELECT * FROM chan WHERE fid = ?;'
        values = [x if x is not None else '' for x in self.execute(qry, (seg_fid,)).fetchone()]
        self.chan = OrderedDict(zip(args, values))
        return self.chan

    def get_chan_table(self):
        if self.row is not None:
            pass
        else:
            return
        tables = {'N': 'chan_n', 'R': 'chan_r', 'T': 'chan_t', 'V': 'chan_v'}
        tab = tables[self.type]
        args = self.table_info(tab, only_columns=True)
        qry = 'SELECT * FROM {0} WHERE elem_fid = ?;'.format(tab)
        values = [x if x is not None else '' for x in self.execute(qry, (self.fid,)).fetchone()]
        self.chan_tab = OrderedDict(zip(args, values))
        return self.chan_tab

    def get_xsec_data(self):
        if self.row is not None and self.type == 'N':
            pass
        else:
            return None
        nxsecnum = self.chan_tab['nxsecnum']
        qry = 'SELECT xi, yi FROM xsec_n_data WHERE chan_n_nxsecnum = ? ORDER BY fid;'
        self.xsec = self.execute(qry, (nxsecnum,)).fetchall()
        return self.xsec


class Inflow(GeoPackageUtils):
    columns = ['fid', 'name', 'time_series_fid', 'ident', 'inoutfc', 'note', 'geom']

    def __init__(self, fid, con, iface):
        super(Inflow, self).__init__(con, iface)
        self.fid = fid
        self.series_fid = None
        self.row = None
        self.time_series_data = None

    def get_row(self):
        qry = 'SELECT * FROM inflow WHERE fid = ?;'
        values = [x if x is not None else '' for x in self.execute(qry, (self.fid,)).fetchone()]
        self.row = OrderedDict(zip(self.columns, values))
        self.series_fid = self.row['time_series_fid']
        return self.row

    def get_time_series_data(self):
        qry = 'SELECT time, value, value2 FROM inflow_time_series_data WHERE series_fid = ?;'
        self.time_series_data = self.execute(qry, (self.series_fid,)).fetchall()
        return self.time_series_data


class Outflow(GeoPackageUtils):
    columns = ['fid', 'name', 'chan_out', 'fp_out', 'hydro_out', 'chan_tser_fid', 'chan_qhpar_fid', 'chan_qhtab_fid',
               'fp_tser_fid', 'type', 'geom']

    def __init__(self, fid, con, iface):
        super(Outflow, self).__init__(con, iface)
        self.fid = fid
        self.row = None
        self.chan_out = None
        self.fp_out = None
        self.hydro_out = None
        self.chan_tser_fid = None
        self.chan_qhpar_fid = None
        self.chan_qhtab_fid = None
        self.fp_tser_fid = None
        self.time_series_data = None
        self.qh_params_data = None
        self.qh_table_data = None
        self.typ = None

    def get_row(self):
        qry = 'SELECT * FROM outflow WHERE fid = ?;'
        values = [x if x is not None else '' for x in self.execute(qry, (self.fid,)).fetchone()]
        self.row = OrderedDict(zip(self.columns, values))
        self.chan_out = self.row['chan_out']
        self.fp_out = self.row['fp_out']
        self.hydro_out = self.row['hydro_out']
        self.chan_tser_fid = self.row['chan_tser_fid']
        self.chan_qhpar_fid = self.row['chan_qhpar_fid']
        self.chan_qhtab_fid = self.row['chan_qhtab_fid']
        self.fp_tser_fid = self.row['fp_tser_fid']
        self.typ = self.row['type']
        return self.row

    def get_time_series(self):
        ts = self.execute('SELECT fid, name FROM outflow_time_series ORDER BY fid;').fetchall()
        return ts

    def get_qh_params(self):
        p = self.execute('SELECT fid, name FROM qh_params ORDER BY fid;').fetchall()
        return p

    def get_qh_tables(self):
        t = self.execute('SELECT fid, name FROM qh_table ORDER BY fid;').fetchall()
        return t

    def get_data_fid_name(self):
        if self.typ in [5, 6, 7, 8]:
            return self.get_time_series()
        elif self.typ in [9, 10]:
            return self.get_qh_params()
        elif self.typ == 11:
            return self.get_qh_tables()
        else:
            pass

    def clear_data_fids(self):
        self.chan_tser_fid = 0
        self.fp_tser_fid = 0
        self.chan_qhpar_fid = 0
        self.chan_qhtab_fid = 0

    def set_new_data_fid(self, fid):
        self.clear_data_fids()
        if self.typ in [5, 7]:
            self.fp_tser_fid = fid
        elif self.typ in [6, 8]:
            self.chan_tser_fid = fid
        elif self.typ in [9, 10]:
            self.chan_qhpar_fid = fid
        elif self.typ == 11:
            self.chan_qhtab_fid = fid
        else:
            pass

    def get_time_series_data(self):
        qry = 'SELECT time, value FROM outflow_time_series_data WHERE series_fid = ?;'
        if self.chan_tser_fid:
            self.time_series_data = self.execute(qry, (self.chan_tser_fid,)).fetchall()
        elif self.fp_tser_fid:
            self.time_series_data = self.execute(qry, (self.fp_tser_fid,)).fetchall()
        else:
            pass
        return self.time_series_data

    def get_qh_params_data(self):
        qry = 'SELECT hmax, coef, exponent FROM qh_params_data WHERE params_fid = ?;'
        self.qh_params_data = self.execute(qry, (self.chan_qhpar_fid,)).fetchall()
        return self.qh_params_data

    def get_qh_table_data(self):
        qry = 'SELECT depth, q FROM qh_table_data WHERE table_fid = ?;'
        self.qh_table_data = self.execute(qry, (self.chan_qhtab_fid,)).fetchall()
        return self.qh_table_data

    def get_data(self):
        if self.typ in [5, 6, 7, 8]:
            return self.get_time_series_data()
        elif self.typ in [9, 10]:
            return self.get_qh_params_data()
        elif self.typ == 11:
            return self.get_qh_table_data()
        else:
            pass


class Rain(GeoPackageUtils):
    columns = ['fid', 'name', 'irainreal', 'irainbuilding', 'time_series_fid', 'tot_rainfall', 'rainabs', 'irainarf', 'movingstrom', 'rainspeed', 'iraindir', 'notes']

    def __init__(self, con, iface):
        super(Rain, self).__init__(con, iface)
        self.row = None
        self.series_fid = None
        self.time_series = None
        self.time_series_data = None

    def get_row(self):
        qry = 'SELECT * FROM rain;'
        values = [x if x is not None else '' for x in self.execute(qry).fetchone()]
        self.row = OrderedDict(zip(self.columns, values))
        self.series_fid = self.row['time_series_fid']
        return self.row

    def get_time_series(self):
        qry = 'SELECT fid, name FROM rain_time_series WHERE fid = ?;'
        self.time_series = self.execute(qry, (self.series_fid,)).fetchall()
        return self.time_series

    def get_time_series_data(self):
        qry = 'SELECT time, value FROM rain_time_series_data WHERE series_fid = ?;'
        self.time_series_data = self.execute(qry, (self.series_fid,)).fetchall()
        return self.time_series_data


class Evaporation(GeoPackageUtils):
    columns = ['fid', 'ievapmonth', 'iday', 'clocktime']

    def __init__(self, con, iface):
        super(Evaporation, self).__init__(con, iface)
        self.row = None
        self.month = 'january'
        self.monthly = None
        self.hourly = None
        self.hourly_sum = 0

    def get_row(self):
        qry = 'SELECT * FROM evapor;'
        values = [x if x is not None else '' for x in self.execute(qry).fetchone()]
        self.row = OrderedDict(zip(self.columns, values))
        return self.row

    def get_monthly(self):
        qry = 'SELECT month, monthly_evap FROM evapor_monthly;'
        self.monthly = self.execute(qry).fetchall()
        return self.monthly

    def get_hourly(self):
        qry = 'SELECT hour, hourly_evap FROM evapor_hourly WHERE month = ? ORDER BY fid;'
        self.hourly = self.execute(qry, (self.month,)).fetchall()
        return self.hourly

    def get_hourly_sum(self):
        qry = 'SELECT ROUND(SUM(hourly_evap), 3) FROM evapor_hourly WHERE month = ? ORDER BY fid;'
        self.hourly_sum = self.execute(qry, (self.month,)).fetchone()[0]
        return self.hourly_sum
