# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from collections import OrderedDict
from flo2dgeopackage import GeoPackageUtils
from math import isnan


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


class UserCrossSection(GeoPackageUtils):
    """Cross section object representation."""
    columns = ['fid', 'fcn', 'type', 'name', 'notes']

    def __init__(self, fid, con, iface):
        super(UserCrossSection, self).__init__(con, iface)
        self.row = None
        self.fid = fid
        self.fcn = None
        self.type = None
        self.name = None
        self.chan_x_row = None
        self.xsec = None
        self.chan_x_tabs = {'N': 'user_chan_n', 'R': 'user_chan_r', 'T': 'user_chan_t', 'V': 'user_chan_v'}

    def get_row(self):
        qry = 'SELECT * FROM user_xsections WHERE fid = ?;'
        values = [x if x is not None else '' for x in self.execute(qry, (self.fid,)).fetchone()]
        self.row = OrderedDict(zip(self.columns, values))
        self.type = self.row['type']
        self.name = self.row['name']
        return self.row

    def get_chan_x_row(self):
        # print 'in get_chan_x_row'
        if self.row is not None:
            pass
        else:
            return
        tab = self.chan_x_tabs[self.type]
        qry = 'SELECT * FROM {0} WHERE user_xs_fid = ?;'.format(tab)
        chan_row = self.execute(qry, (self.fid,)).fetchone()
        if not chan_row:
            # create new row
            chan_row = self.add_chan_x_row(fetch=True)
        values = [x if x is not None else '' for x in chan_row]
        args = self.table_info(tab, only_columns=True)
        self.chan_x_row = OrderedDict(zip(args, values))
        return self.chan_x_row

    def add_chan_x_row(self, fetch=False):
        # add a new row in user_chan_(x) tables
        tab = self.chan_x_tabs[self.type]
        qry = 'INSERT INTO {0} (user_xs_fid) VALUES (?);'.format(tab)
        self.execute(qry, (self.fid,))
        if fetch:
            qry = 'SELECT * FROM {0} WHERE user_xs_fid = ?;'.format(tab)
            return self.execute(qry, (self.fid,)).fetchone()

    def get_chan_natural_data(self):
        if self.row is not None and self.type == 'N':
            pass
        else:
            return None
        qry = 'SELECT xi, yi FROM user_xsec_n_data WHERE chan_n_nxsecnum = ? ORDER BY xi;'
        self.xiyi = self.execute(qry, (self.fid,)).fetchall()
        if not self.xiyi:
            self.xiyi = self.add_chan_natural_data(fetch=True)
        return self.xiyi

    def add_chan_natural_data(self, fetch=False):
        qry = '''INSERT INTO user_xsec_n_data (chan_n_nxsecnum, xi, yi)
                VALUES ({0}, 0, 1), ({0}, 1, 0), ({0}, 2, 1)'''.format(self.fid)
        self.execute(qry)
        if fetch:
            qry = 'SELECT xi, yi FROM user_xsec_n_data WHERE chan_n_nxsecnum = ? ORDER BY xi;'
            self.xiyi = self.execute(qry, (self.fid,)).fetchall()
            return self.xiyi

    def set_chan_data(self, data):
        table = self.chan_x_tabs[self.type]
        # qry = '''DELETE FROM {0} WHERE user_xs_fid = ?'''.format(table)
        # self.execute(qry, (self.fid,))
        cols = list(self.table_info(table, only_columns=True))[1:]
        cols_t = ', '.join([c for c in cols])
        vals = []
        for v in data:
            if not isnan(v):
                vals.append(v)
            else:
                vals.append('NULL')
        vals_t = ', '.join([str(v) for v in vals])
        qry = '''INSERT INTO {0} ({1}) VALUES ({2}, {3});'''.format(table, cols_t, self.fid, vals_t)
        self.execute(qry)

    def set_chan_natural_data(self, data):
        qry = '''DELETE FROM user_xsec_n_data WHERE chan_n_nxsecnum = ?'''
        self.execute(qry, (self.fid, ))
        qry = '''INSERT INTO user_xsec_n_data (chan_n_nxsecnum, xi, yi) VALUES (?, ?, ?);'''
        self.execute_many(qry, data)

    def set_type(self, typ):
        qry = '''UPDATE user_xsections SET type = ? WHERE fid = ?;'''
        self.execute(qry, (typ, self.fid,))

    def set_n(self, n):
        qry = '''UPDATE user_xsections SET fcn = ? WHERE fid = ?;'''
        self.execute(qry, (n, self.fid,))

    def set_name(self, name=None):
        if not name:
            name = self.name
        qry = '''UPDATE user_xsections SET name = ? WHERE fid = ?;'''
        self.execute(qry, (name, self.fid,))


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

    def add_row(self):
        data = (
            self.name,
            self.time_series_fid,
            self.ident,
            self.inoutfc
        )
        qry = 'INSERT INTO inflow (name, time_series_fid, ident, inoutfc) VALUES (?, ?, ?, ?);'
        self.fid = self.execute(qry, data, get_rowid=True)

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
        return self.row

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

    def del_row(self):
        # first try to delete the bc from user layer
        if self.geom_type and self.bc_fid:
            qry = '''DELETE FROM user_bc_{}s WHERE fid=? AND type='inflow';'''.format(self.geom_type)
            self.execute(qry, (self.bc_fid,))
            # there is a trigger updating inflow table when the user bc layer is changed
            # this is for inflow rows without geometry
        qry = 'DELETE FROM inflow WHERE fid=?'
        self.execute(qry, (self.fid,))

    def add_time_series(self, name=None, fetch=False):
        qry = 'INSERT INTO inflow_time_series (name) VALUES (?);'
        rowid = self.execute(qry, (name,), get_rowid=True)
        qry = '''UPDATE inflow SET time_series_fid = ? WHERE fid = ?'''
        self.execute(qry, (rowid, self.fid))
        self.time_series_fid = rowid
        if fetch:
            return self.get_time_series()

    def get_time_series(self):
        qry = 'SELECT fid, name FROM inflow_time_series ORDER BY fid;'
        self.time_series = self.execute(qry).fetchall()
        if not self.time_series:
            self.time_series = self.add_time_series(fetch=True)
        return self.time_series

    def get_data_name(self, fid=None):
        qry = 'SELECT name FROM inflow_time_series WHERE fid = ?;'
        if not fid and self.time_series_fid:
            fid = self.time_series_fid
        elif fid:
            return self.execute(qry, (fid,))
        else:
            return None

    def add_time_series_data(self, ts_fid, rows=5, fetch=False):
        """Add new rows to inflow_time_series_data for a given ts_fid"""
        qry = 'INSERT INTO inflow_time_series_data (series_fid, time, value) VALUES (?, NULL, NULL);'
        self.execute_many(qry, ([ts_fid],)*rows)
        if fetch:
            return self.get_time_series_data()

    def get_time_series_data(self):
        if not self.time_series_fid:
            return
        qry = 'SELECT time, value, value2 FROM inflow_time_series_data WHERE series_fid = ? ORDER BY time;'
        self.time_series_data = self.execute(qry, (self.time_series_fid,)).fetchall()
        if not self.time_series_data:
            # add a new time series
            self.time_series_data = self.add_time_series_data(self.time_series_fid, fetch=True)
        return self.time_series_data

    def set_time_series_data_name(self, name):
        qry = 'UPDATE inflow_time_series SET name=? WHERE fid=?;'
        self.execute(qry, (name, self.time_series_fid,))

    def set_time_series_data(self, name, data):
        qry = 'UPDATE inflow_time_series SET name=? WHERE fid=?;'
        self.execute(qry, (name, self.time_series_fid,))
        qry = 'DELETE FROM inflow_time_series_data WHERE series_fid = ?;'
        self.execute(qry, (self.time_series_fid,))
        qry = 'INSERT INTO inflow_time_series_data (series_fid, time, value, value2) VALUES (?, ?, ?, ?);'
        self.execute_many(qry, data)

    def remove_time_series(self):
        qry = 'DELETE FROM inflow_time_series_data WHERE series_fid = ?;'
        self.execute(qry, (self.time_series_fid,))
        qry = 'DELETE FROM inflow_time_series WHERE fid = ?;'
        self.execute(qry, (self.time_series_fid,))


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

    def add_row(self):
        data = (
            self.name,
            self.chan_out,
            self.fp_out,
            self.hydro_out,
            self.chan_tser_fid,
            self.chan_qhpar_fid,
            self.chan_qhtab_fid,
            self.fp_tser_fid,
            self.typ
        )
        qry = '''INSERT INTO outflow (
            name,
            chan_out,
            fp_out,
            hydro_out,
            chan_tser_fid,
            chan_qhpar_fid,
            chan_qhtab_fid,
            fp_tser_fid,
            type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);'''
        self.fid = self.execute(qry, data, get_rowid=True)

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

    def del_row(self):
        # first try to delete the bc from user layer
        if self.geom_type and self.bc_fid:
            qry = '''DELETE FROM user_bc_{}s WHERE fid=? AND type='outflow';'''.format(self.geom_type)
            self.execute(qry, (self.bc_fid,))
        # there is a trigger updating outflow table when the user bc layer is changed
        # this is for outflow rows without geometry
        qry = 'DELETE FROM outflow WHERE fid=?'
        self.execute(qry, (self.fid,))

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

    def get_time_series(self, order_by='name'):
        if order_by == 'name':
            ts = self.execute('SELECT fid, name FROM outflow_time_series ORDER BY name COLLATE NOCASE;').fetchall()
        else:
            ts = self.execute('SELECT fid, name FROM outflow_time_series ORDER BY fid;').fetchall()
        if not ts:
            ts = self.add_time_series(fetch=True)
        return ts

    def add_time_series(self, name=None, fetch=False):
        qry = '''INSERT INTO outflow_time_series (name) VALUES (?);'''
        rowid = self.execute(qry, (name,), get_rowid=True)
        name_qry = '''UPDATE outflow_time_series SET name =  'Time series ' || cast(fid as text) WHERE fid = ?;'''
        self.execute(name_qry, (rowid,))
        self.set_new_data_fid(rowid)
        if not name:
            self.name = 'Time series {}'.format(rowid)
        if fetch:
            return self.get_time_series()

    def get_qh_params(self, order_by='name'):
        if order_by == 'name':
            p = self.execute('SELECT fid, name FROM qh_params ORDER BY name COLLATE NOCASE;').fetchall()
        else:
            p = self.execute('SELECT fid, name FROM qh_params ORDER BY fid;').fetchall()
        if not p:
            p = self.add_qh_params(fetch=True)
        return p

    def add_qh_params(self, name=None, fetch=False):
        qry = '''INSERT INTO qh_params (name) VALUES (?);'''
        rowid = self.execute(qry, (name,), get_rowid=True)
        name_qry = '''UPDATE qh_params SET name =  'Q(h) parameters ' || cast(fid as text) WHERE fid = ?;'''
        self.execute(name_qry, (rowid,))
        self.set_new_data_fid(rowid)
        if fetch:
            return self.get_qh_params()

    def get_qh_tables(self, order_by='name'):
        if order_by == 'name':
            t = self.execute('SELECT fid, name FROM qh_table ORDER BY name COLLATE NOCASE;').fetchall()
        else:
            t = self.execute('SELECT fid, name FROM qh_table ORDER BY fid;').fetchall()
        if not t:
            t = self.add_qh_table(fetch=True)
        return t

    def add_qh_table(self, name=None, fetch=False):
        qry = '''INSERT INTO qh_table (name) VALUES (?);'''
        rowid = self.execute(qry, (name,), get_rowid=True)
        name_qry = '''UPDATE qh_table SET name = 'Q(h) table ' || cast(fid as text) WHERE fid = ?;'''
        self.execute(name_qry, (rowid,))
        self.set_new_data_fid(rowid)
        if fetch:
            return self.get_qh_tables()

    def get_data_fid_name(self):
        """Return a list of [fid, name] pairs for each data set of a kind appropriate for the current outflow.
        This could be time series, Qh Table or Qh Parameters."""
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
        data = None
        if self.typ in [5, 6, 7, 8]:
            data = self.add_time_series(name)
        elif self.typ in [9, 10]:
            data = self.add_qh_params(name)
        elif self.typ == 11:
            data = self.add_qh_table(name)
        else:
            pass
        return data

    def set_data_name(self, name):
        """Save new data name"""
        self.data_fid = self.get_cur_data_fid()
        if self.typ in [5, 6, 7, 8]:
            self.set_time_series_data_name(name)
        elif self.typ in [9, 10]:
            self.set_qh_params_data_name(name)
        elif self.typ == 11:
            self.set_qh_table_data_name(name)
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

    def set_time_series_data_name(self, name):
        qry = 'UPDATE outflow_time_series SET name=? WHERE fid=?;'
        self.execute(qry, (name, self.data_fid,))

    def set_time_series_data(self, name, data):
        qry = 'UPDATE outflow_time_series SET name=? WHERE fid=?;'
        self.execute(qry, (name, self.data_fid,))
        qry = 'DELETE FROM outflow_time_series_data WHERE series_fid = ?;'
        self.execute(qry, (self.data_fid,))
        qry = 'INSERT INTO outflow_time_series_data (series_fid, time, value) VALUES ({}, ?, ?);'
        self.execute_many(qry.format(self.data_fid), data)

    def set_qh_params_data_name(self, name):
        qry = 'UPDATE qh_params SET name=? WHERE fid=?;'
        self.execute(qry, (name, self.data_fid,))

    def set_qh_params_data(self, name, data):
        qry = 'UPDATE qh_params SET name=? WHERE fid=?;'
        self.execute(qry, (name, self.data_fid,))
        qry = 'DELETE FROM qh_params_data WHERE params_fid = ?;'
        self.execute(qry, (self.data_fid,))
        qry = 'INSERT INTO qh_params_data (params_fid, hmax, coef, exponent) VALUES ({}, ?, ?, ?);'
        self.execute_many(qry.format(self.data_fid), data)

    def set_qh_table_data_name(self, name):
        qry = 'UPDATE qh_table SET name=? WHERE fid=?;'
        self.execute(qry, (name, self.data_fid,))

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
        if self.typ in [5, 6, 7, 8]:
            return self.get_time_series_data()
        elif self.typ in [9, 10]:
            return self.get_qh_params_data()
        elif self.typ == 11:
            return self.get_qh_table_data()
        else:
            pass

    def get_new_data_name(self, fid):
        if self.typ in [5, 6, 7, 8]:
            return 'Time series {}'.format(fid)
        elif self.typ in [9, 10]:
            return 'Q(h) parameters {}'.format(fid)
        elif self.typ == 11:
            return 'Q(h) table {}'.format(fid)
        else:
            return None


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
        data = self.execute(qry).fetchone()
        if not data:
            return
        values = [x if x is not None else '' for x in data]
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


class Street(GeoPackageUtils):
    """Street data implementation."""
    columns = ['fid', 'str_fid', 'igridn', 'depex', 'stman', 'elstr', 'geom']

    def __init__(self, fid, con, iface):
        super(Street, self).__init__(con, iface)
        self.fid = fid
        self.row = None
        self.general = None
        self.elems = None
        self.name = None
        self.notes = None
        self.curb_height = None
        self.n_value = None
        self.elevation = None

    def get_row(self):
        qry = 'SELECT * FROM street_elems WHERE fid = ?;'
        values = [x if x is not None else '' for x in self.execute(qry, (self.fid,)).fetchone()]
        self.row = OrderedDict(zip(self.columns, values))
        self.name = self.row['name']
        self.curb_height = self.row['depex']
        self.n_value = self.row['stman']
        self.elevation = self.row['elstr']
        return self.row

    def get_name_notes(self):
        qry = 'SELECT stname, notes FROM streets WHERE fid = ?;'
        values = [x if x is not None else '' for x in self.execute(qry, (self.fid,)).fetchone()]
        self.name, self.notes = values
        return self.name, self.notes

    def get_elems(self):
        qry = 'SELECT istdir, widr FROM street_elems WHERE str_fid = ?;'
        self.elems = self.execute(qry, (self.fid,)).fetchall()


class Reservoir(GeoPackageUtils):
    """Reservoir data representation."""
    columns = ['fid', 'name', 'wsel', 'notes']

    def __init__(self, fid, con, iface):
        super(Reservoir, self).__init__(con, iface)
        self.fid = fid
        self.row = None
        self.name = None
        self.wsel = None

    def get_row(self):
        qry = 'SELECT * FROM user_reservoirs WHERE fid = ?;'
        data = self.execute(qry, (self.fid, )).fetchone()
        if not data:
            return
        values = [x if x is not None else '' for x in data]
        self.row = OrderedDict(zip(self.columns, values))
        self.name = self.row['name']
        self.wsel = self.row['wsel']
        return self.row

    def set_row(self):
        qry = '''UPDATE user_reservoirs SET
            name = '{0}',
            wsel = {1}
        WHERE fid = {2};'''.format(self.name, self.wsel, self.fid)
        self.execute(qry)

    def del_row(self):
        qry = 'DELETE FROM user_reservoirs WHERE fid=?'
        self.execute(qry, (self.fid,))


class Structure(GeoPackageUtils):
    """Outflow object representation."""
    columns = ['fid', 'type', 'structname', 'ifporchan', 'icurvtable', 'inflonod', 'outflonod', 'inoutcont', 'headrefel',
               'clength', 'cdiameter', 'notes']

    def __init__(self, fid, con, iface):
        super(Structure, self).__init__(con, iface)
        self.fid = fid
        self.type = None
        self.name = None
        self.ifporchan = None
        self.icurvtable = None
        self.inflonod = None
        self.chan_tser_fid = None
        self.chan_qhpar_fid = None
        self.chan_qhtab_fid = None
        self.fp_tser_fid = None
        self.time_series_data = None
        self.qh_params_data = None
        self.qh_table_data = None
        self.typ = None

    def add_row(self):
        data = (
            self.name,
            self.chan_out,
            self.fp_out,
            self.hydro_out,
            self.chan_tser_fid,
            self.chan_qhpar_fid,
            self.chan_qhtab_fid,
            self.fp_tser_fid,
            self.typ
        )
        qry = '''INSERT INTO outflow (
            name,
            chan_out,
            fp_out,
            hydro_out,
            chan_tser_fid,
            chan_qhpar_fid,
            chan_qhtab_fid,
            fp_tser_fid,
            type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);'''
        self.fid = self.execute(qry, data, get_rowid=True)

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

    def del_row(self):
        # first try to delete the bc from user layer
        if self.geom_type and self.bc_fid:
            qry = '''DELETE FROM user_bc_{}s WHERE fid=? AND type='outflow';'''.format(self.geom_type)
            self.execute(qry, (self.bc_fid,))
        # there is a trigger updating outflow table when the user bc layer is changed
        # this is for outflow rows without geometry
        qry = 'DELETE FROM outflow WHERE fid=?'
        self.execute(qry, (self.fid,))

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

    def get_time_series(self, order_by='name'):
        if order_by == 'name':
            ts = self.execute('SELECT fid, name FROM outflow_time_series ORDER BY name COLLATE NOCASE;').fetchall()
        else:
            ts = self.execute('SELECT fid, name FROM outflow_time_series ORDER BY fid;').fetchall()
        if not ts:
            ts = self.add_time_series(fetch=True)
        return ts

    def add_time_series(self, name=None, fetch=False):
        qry = '''INSERT INTO outflow_time_series (name) VALUES (?);'''
        rowid = self.execute(qry, (name,), get_rowid=True)
        name_qry = '''UPDATE outflow_time_series SET name =  'Time series ' || cast(fid as text) WHERE fid = ?;'''
        self.execute(name_qry, (rowid,))
        self.set_new_data_fid(rowid)
        if not name:
            self.name = 'Time series {}'.format(rowid)
        if fetch:
            return self.get_time_series()

    def get_qh_params(self, order_by='name'):
        if order_by == 'name':
            p = self.execute('SELECT fid, name FROM qh_params ORDER BY name COLLATE NOCASE;').fetchall()
        else:
            p = self.execute('SELECT fid, name FROM qh_params ORDER BY fid;').fetchall()
        if not p:
            p = self.add_qh_params(fetch=True)
        return p

    def add_qh_params(self, name=None, fetch=False):
        qry = '''INSERT INTO qh_params (name) VALUES (?);'''
        rowid = self.execute(qry, (name,), get_rowid=True)
        name_qry = '''UPDATE qh_params SET name =  'Q(h) parameters ' || cast(fid as text) WHERE fid = ?;'''
        self.execute(name_qry, (rowid,))
        self.set_new_data_fid(rowid)
        if fetch:
            return self.get_qh_params()

    def get_qh_tables(self, order_by='name'):
        if order_by == 'name':
            t = self.execute('SELECT fid, name FROM qh_table ORDER BY name COLLATE NOCASE;').fetchall()
        else:
            t = self.execute('SELECT fid, name FROM qh_table ORDER BY fid;').fetchall()
        if not t:
            t = self.add_qh_table(fetch=True)
        return t

    def add_qh_table(self, name=None, fetch=False):
        qry = '''INSERT INTO qh_table (name) VALUES (?);'''
        rowid = self.execute(qry, (name,), get_rowid=True)
        name_qry = '''UPDATE qh_table SET name = 'Q(h) table ' || cast(fid as text) WHERE fid = ?;'''
        self.execute(name_qry, (rowid,))
        self.set_new_data_fid(rowid)
        if fetch:
            return self.get_qh_tables()

    def get_data_fid_name(self):
        """Return a list of [fid, name] pairs for each data set of a kind appropriate for the current outflow.
        This could be time series, Qh Table or Qh Parameters."""
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
        data = None
        if self.typ in [5, 6, 7, 8]:
            data = self.add_time_series(name)
        elif self.typ in [9, 10]:
            data = self.add_qh_params(name)
        elif self.typ == 11:
            data = self.add_qh_table(name)
        else:
            pass
        return data

    def set_data_name(self, name):
        """Save new data name"""
        self.data_fid = self.get_cur_data_fid()
        if self.typ in [5, 6, 7, 8]:
            self.set_time_series_data_name(name)
        elif self.typ in [9, 10]:
            self.set_qh_params_data_name(name)
        elif self.typ == 11:
            self.set_qh_table_data_name(name)
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

    def set_time_series_data_name(self, name):
        qry = 'UPDATE outflow_time_series SET name=? WHERE fid=?;'
        self.execute(qry, (name, self.data_fid,))

    def set_time_series_data(self, name, data):
        qry = 'UPDATE outflow_time_series SET name=? WHERE fid=?;'
        self.execute(qry, (name, self.data_fid,))
        qry = 'DELETE FROM outflow_time_series_data WHERE series_fid = ?;'
        self.execute(qry, (self.data_fid,))
        qry = 'INSERT INTO outflow_time_series_data (series_fid, time, value) VALUES ({}, ?, ?);'
        self.execute_many(qry.format(self.data_fid), data)

    def set_qh_params_data_name(self, name):
        qry = 'UPDATE qh_params SET name=? WHERE fid=?;'
        self.execute(qry, (name, self.data_fid,))

    def set_qh_params_data(self, name, data):
        qry = 'UPDATE qh_params SET name=? WHERE fid=?;'
        self.execute(qry, (name, self.data_fid,))
        qry = 'DELETE FROM qh_params_data WHERE params_fid = ?;'
        self.execute(qry, (self.data_fid,))
        qry = 'INSERT INTO qh_params_data (params_fid, hmax, coef, exponent) VALUES ({}, ?, ?, ?);'
        self.execute_many(qry.format(self.data_fid), data)

    def set_qh_table_data_name(self, name):
        qry = 'UPDATE qh_table SET name=? WHERE fid=?;'
        self.execute(qry, (name, self.data_fid,))

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
        if self.typ in [5, 6, 7, 8]:
            return self.get_time_series_data()
        elif self.typ in [9, 10]:
            return self.get_qh_params_data()
        elif self.typ == 11:
            return self.get_qh_table_data()
        else:
            pass

    def get_new_data_name(self, fid):
        if self.typ in [5, 6, 7, 8]:
            return 'Time series {}'.format(fid)
        elif self.typ in [9, 10]:
            return 'Q(h) parameters {}'.format(fid)
        elif self.typ == 11:
            return 'Q(h) table {}'.format(fid)
        else:
            return None
