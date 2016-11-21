# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from collections import OrderedDict
from flo2dgeopackage import GeoPackageUtils


class CrossSection(GeoPackageUtils):
    """Cross section object representation."""
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
    """Inflow object representation."""
    columns = ['fid', 'name', 'time_series_fid', 'ident', 'inoutfc', 'note', 'geom_type', 'bc_fid']

    def __init__(self, fid, con, iface):
        super(Inflow, self).__init__(con, iface)
        self.row = None
        self.fid = fid
        self.name = None
        self.time_series_fid = None
        self.ident = None
        self.inoutfc = None
        self.geom_type = None
        self.bc_fid = None
        self.time_series_data = None

    def get_row(self):
        qry = 'SELECT * FROM inflow WHERE fid = ?;'
        values = [x if x is not None else '' for x in self.execute(qry, (self.fid,)).fetchone()]
        self.row = OrderedDict(zip(self.columns, values))
        self.name = self.row['name']
        self.time_series_fid = self.row['time_series_fid']
        self.ident = self.row['ident']
        self.inoutfc = self.row['inoutfc']
        self.geom_type = self.row['geom_type']
        self.bc_fid = self.row['bc_fid']
        # print 'inflow tser fid', self.time_series_fid
        return self.row

    def get_time_series(self):
        qry = 'SELECT fid, name FROM inflow_time_series ORDER BY fid;'
        self.time_series = self.execute(qry).fetchall()
        if not self.time_series:
            self.time_series = self.add_time_series(fetch=True)
        return self.time_series

    def add_time_series(self, name=None, fetch=False):
        qry = 'INSERT INTO inflow_time_series (name) VALUES (?);'
        rowid = self.execute(qry, (name,), get_rowid=True)
        qry = '''UPDATE inflow SET time_series_fid = ? WHERE fid = ?'''
        self.execute(qry, (rowid, self.fid))
        self.time_series_fid = rowid
        if fetch:
            return self.get_time_series()

    def get_time_series_data(self):
        # print 'in get_time_series_data for fid', self.time_series_fid
        if not self.time_series_fid:
            return
        qry = 'SELECT time, value, value2 FROM inflow_time_series_data WHERE series_fid = ? ORDER BY time;'
        self.time_series_data = self.execute(qry, (self.time_series_fid,)).fetchall()
        if not self.time_series_data:
            # add a new time series
            self.time_series_data = self.add_time_series_data(self.time_series_fid, fetch=True)
        return self.time_series_data

    def add_time_series_data(self, ts_fid, rows=5, fetch=False):
        """Add new rows to inflow_time_series_data for a given ts_fid"""
        qry = 'INSERT INTO inflow_time_series_data (series_fid, time, value) VALUES (?, NULL, NULL);'
        self.execute_many(qry, ([ts_fid],)*rows)
        if fetch:
            return self.get_time_series_data()

    def remove_time_series(self):
        qry = 'DELETE FROM inflow_time_series_data WHERE series_fid = ?;'
        self.execute(qry, (self.time_series_fid,))
        qry = 'DELETE FROM inflow_time_series WHERE fid = ?;'
        self.execute(qry, (self.time_series_fid,))

    def set_row(self):
        data = (
            self.name,
            self.time_series_fid,
            self.ident,
            self.inoutfc,
            self.fid
        )
        qry = 'UPDATE inflow SET name=?, time_series_fid=?, ident=?, inoutfc=? WHERE fid=?'
        self.execute(qry, data)

    def set_time_series_data(self, name, data):
        qry = 'UPDATE inflow_time_series SET name=? WHERE fid=?;'
        self.execute(qry, (name, self.time_series_fid,))
        qry = 'DELETE FROM inflow_time_series_data WHERE series_fid = ?;'
        self.execute(qry, (self.time_series_fid,))
        qry = 'INSERT INTO inflow_time_series_data (series_fid, time, value, value2) VALUES (?, ?, ?, ?);'
        self.execute_many(qry, data)


class Outflow(GeoPackageUtils):
    """Outflow object representation."""
    columns = ['fid', 'name', 'chan_out', 'fp_out', 'hydro_out', 'chan_tser_fid', 'chan_qhpar_fid', 'chan_qhtab_fid',
               'fp_tser_fid', 'type', 'geom_type', 'bc_fid']

    def __init__(self, fid, con, iface):
        super(Outflow, self).__init__(con, iface)
        self.fid = fid
        self.name = None
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
        self.name = self.row['name']
        self.chan_out = self.row['chan_out']
        self.fp_out = self.row['fp_out']
        self.hydro_out = self.row['hydro_out']
        self.chan_tser_fid = self.row['chan_tser_fid']
        self.chan_qhpar_fid = self.row['chan_qhpar_fid']
        self.chan_qhtab_fid = self.row['chan_qhtab_fid']
        self.fp_tser_fid = self.row['fp_tser_fid']
        self.typ = self.row['type']
        self.geom_type = self.row['geom_type']
        self.bc_fid = self.row['bc_fid']
        return self.row

    def clear_type_data(self):
        self.typ = None
        self.chan_out = None
        self.fp_out = None
        self.hydro_out = None

    def set_type_data(self, typ):
        if typ == 4:
            # keep nr of outflow hydrograph to set it later
            old_hydro_out = self.hydro_out
        else:
            old_hydro_out = None
        self.clear_type_data()
        self.typ = typ
        if typ in (2, 8):
            self.chan_out = 1
        elif typ in (1, 7):
            self.fp_out = 1
        elif typ == 3:
            self.chan_out = 1
            self.fp_out = 1
        elif typ == 4:
            self.clear_data_fids()
            self.hydro_out = old_hydro_out
        else:
            pass

    def set_row(self):
        data = (
            self.name,
            self.chan_out,
            self.fp_out,
            self.hydro_out,
            self.chan_tser_fid,
            self.chan_qhpar_fid,
            self.chan_qhtab_fid,
            self.fp_tser_fid,
            self.typ,
            self.fid
        )
        qry = '''UPDATE outflow
                    SET name=?,
                    chan_out=?,
                    fp_out=?,
                    hydro_out=?,
                    chan_tser_fid=?,
                    chan_qhpar_fid=?,
                    chan_qhtab_fid=?,
                    fp_tser_fid=?,
                    type=?
                WHERE fid=?;'''
        self.execute(qry, data)

    def get_time_series(self):
        ts = self.execute('SELECT fid, name FROM outflow_time_series ORDER BY fid;').fetchall()
        if not ts:
            ts = self.add_time_series(fetch=True)
        return ts

    def add_time_series(self, name=None, fetch=False):
        if not name:
            name = 'New time series'
        qry = '''INSERT INTO outflow_time_series (name) VALUES (?);'''
        rowid = self.execute(qry, (name,), get_rowid=True)
        self.set_new_data_fid(rowid)
        if fetch:
            return self.get_time_series()

    def get_qh_params(self):
        p = self.execute('SELECT fid, name FROM qh_params ORDER BY fid;').fetchall()
        if not p:
            p = self.add_qh_params()
        return p

    def add_qh_params(self, name=None, fetch=False):
        if not name:
            name = 'New QH Parameters'
        qry = '''INSERT INTO qh_params (name) VALUES (?);'''
        rowid = self.execute(qry, (name,), get_rowid=True)
        self.set_new_data_fid(rowid)
        if fetch:
            return self.get_qh_params()

    def get_qh_tables(self):
        t = self.execute('SELECT fid, name FROM qh_table ORDER BY fid;').fetchall()
        if not t:
            t = self.add_qh_table()
        return t

    def add_qh_table(self, name=None, fetch=False):
        if not name:
            name = 'New QH Table'
        qry = '''INSERT INTO qh_table (name) VALUES (?);'''
        rowid = self.execute(qry, (name,), get_rowid=True)
        self.set_new_data_fid(rowid)
        if fetch:
            return self.get_qh_tables()

    def get_data_fid_name(self):
        # print 'in get_data_fid_name for typ', self.typ
        if self.typ in [5, 6, 7, 8]:
            return self.get_time_series()
        elif self.typ in [9, 10]:
            return self.get_qh_params()
        elif self.typ == 11:
            return self.get_qh_tables()
        else:
            pass

    def add_data(self, name=None):
        """Add a new data to current outflow type data table (time series, qh params or qh table)"""
        if self.typ in [5, 6, 7, 8]:
            self.add_time_series(name)
        elif self.typ in [9, 10]:
            self.add_qh_params(name)
        elif self.typ == 11:
            self.add_qh_table(name)
        else:
            pass

    def set_data(self, name, data):
        """Save current model data to the right outflow data table"""
        self.data_fid = self.get_cur_data_fid()
        if self.typ in [5, 6, 7, 8]:
            self.set_time_series_data(name, data)
        elif self.typ in [9, 10]:
            self.set_qh_params_data(name, data)
        elif self.typ == 11:
            self.set_qh_table_data(name, data)
        else:
            pass

    def set_time_series_data(self, name, data):
        qry = 'UPDATE outflow_time_series SET name=? WHERE fid=?;'
        self.execute(qry, (name, self.data_fid,))
        qry = 'DELETE FROM outflow_time_series_data WHERE series_fid = ?;'
        self.execute(qry, (self.data_fid,))
        qry = 'INSERT INTO outflow_time_series_data (series_fid, time, value) VALUES ({}, ?, ?);'
        self.execute_many(qry.format(self.data_fid), data)

    def set_qh_params_data(self, name, data):
        qry = 'UPDATE qh_params SET name=? WHERE fid=?;'
        self.execute(qry, (name, self.data_fid,))
        qry = 'DELETE FROM qh_params_data WHERE params_fid = ?;'
        self.execute(qry, (self.data_fid,))
        qry = 'INSERT INTO qh_params_data (params_fid, hmax, coef, exponent) VALUES ({}, ?, ?, ?);'
        self.execute_many(qry.format(self.data_fid), data)

    def set_qh_table_data(self, name, data):
        qry = 'UPDATE qh_table SET name=? WHERE fid=?;'
        self.execute(qry, (name, self.data_fid,))
        qry = 'DELETE FROM qh_table_data WHERE table_fid = ?;'
        self.execute(qry, (self.data_fid,))
        qry = 'INSERT INTO qh_table_data (table_fid, depth, q) VALUES ({}, ?, ?);'
        self.execute_many(qry.format(self.data_fid), data)

    def get_cur_data_fid(self):
        """Get first non-zero outflow data fid (i.e. ch_tser_fid, fp_tser_fid, chan_qhpar_fid or ch_qhtab_fid)"""
        data_fid_vals = [self.chan_tser_fid, self.chan_qhpar_fid, self.chan_qhtab_fid, self.fp_tser_fid]
        return next((val for val in data_fid_vals if val), None)

    def clear_data_fids(self):
        self.chan_tser_fid = None
        self.fp_tser_fid = None
        self.chan_qhpar_fid = None
        self.chan_qhtab_fid = None

    def set_new_data_fid(self, fid):
        """Set new data fid for current outflow type"""
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
        """Get time, value pairs for the current outflow"""
        qry = 'SELECT time, value FROM outflow_time_series_data WHERE series_fid = ? ORDER BY time;'
        data_fid = self.get_cur_data_fid()
        if not data_fid:
            self.uc.bar_warn('No time series fid for current outflow is defined.')
            return
        self.time_series_data = self.execute(qry, (data_fid,)).fetchall()
        if not self.time_series_data:
            # add a new time series
            self.time_series_data = self.add_time_series_data(data_fid, fetch=True)
        return self.time_series_data

    def add_time_series_data(self, ts_fid, rows=5, fetch=False):
        """Add new rows to outflow_time_series_data for a given ts_fid"""
        # print 'in add_time_series_data'
        qry = 'INSERT INTO outflow_time_series_data (series_fid, time, value) VALUES (?, NULL, NULL);'
        self.execute_many(qry, ([ts_fid],)*rows)
        if fetch:
            return self.get_time_series_data()

    def get_qh_params_data(self):
        qry = 'SELECT hmax, coef, exponent FROM qh_params_data WHERE params_fid = ?;'
        params_fid = self.get_cur_data_fid()
        self.qh_params_data = self.execute(qry, (params_fid,)).fetchall()
        if not self.qh_params_data:
            self.qh_params_data = self.add_qh_params_data(params_fid, fetch=True)
        return self.qh_params_data

    def add_qh_params_data(self, params_fid, rows=1, fetch=False):
        """Add new rows to qh_params_data for a given params_fid"""
        qry = 'INSERT INTO qh_params_data (params_fid, hmax, coef, exponent) VALUES (?, NULL, NULL, NULL);'
        self.execute_many(qry, ([params_fid],)*rows)
        if fetch:
            return self.get_qh_params_data()

    def get_qh_table_data(self):
        qry = 'SELECT depth, q FROM qh_table_data WHERE table_fid = ? ORDER BY depth;'
        table_fid = self.get_cur_data_fid()
        self.qh_table_data = self.execute(qry, (table_fid,)).fetchall()
        if not self.qh_table_data:
            self.qh_table_data = self.add_qh_table_data(table_fid, fetch=True)
        return self.qh_table_data

    def add_qh_table_data(self, table_fid, rows=5, fetch=False):
        """Add new rows to qh_table_data for a given table_fid"""
        qry = 'INSERT INTO qh_table_data (table_fid, depth, q) VALUES (?, NULL, NULL);'
        self.execute_many(qry, ([table_fid],)*rows)
        if fetch:
            return self.get_qh_table_data()

    def get_data(self):
        """Get data for current type and data_fid of the outflow"""
        # print 'in get_data, typ=', self.typ
        if self.typ in [5, 6, 7, 8]:
            # print 'getting time series...'
            return self.get_time_series_data()
        elif self.typ in [9, 10]:
            return self.get_qh_params_data()
        elif self.typ == 11:
            return self.get_qh_table_data()
        else:
            pass


class Rain(GeoPackageUtils):
    """Rain data representation."""
    columns = ['fid', 'name', 'irainreal', 'irainbuilding', 'time_series_fid', 'tot_rainfall',
               'rainabs', 'irainarf', 'movingstrom', 'rainspeed', 'iraindir', 'notes']

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
    """Evaporation data representation."""
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
