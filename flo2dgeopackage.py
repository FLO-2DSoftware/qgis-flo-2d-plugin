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
 This script initializes the plugin, making it known to QGIS.
"""

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.gui import *
from qgis.core import *
import processing
import logging

from .utils import *
import pyspatialite.dbapi2 as db
from .user_communication import UserCommunication
from flo2d_parser import ParseDAT


class GeoPackageUtils(object):
    """GeoPackage utils for handling GPKG files"""
    def __init__(self, path):
        self.path = path
        self.conn = None
        self.msg = None

    def database_connect(self):
        """Connect database with sqlite3"""
        try:
            self.conn = db.connect(self.path)
            return True
        except:
            self.msg = "Couldn't connect to GeoPackage"
            return False

    def check_gpkg(self):
        """Check if file is GeoPackage """
        try:
            c = self.conn.cursor()
            c.execute('SELECT * FROM gpkg_contents;')
            c.fetchone()
            return True
        except:
            return False

    def execute(self, statement, inputs=None):
        """Execute a prepared SQL statement on this geopackage database."""
        with self.conn as db_con:
            cursor = db_con.cursor()
            if inputs is not None:
                result_cursor = cursor.execute(statement, inputs)
            else:
                result_cursor = cursor.execute(statement)
            return result_cursor

    def is_table_empty(self, table):
        r = self.execute('''SELECT rowid FROM {0};'''.format(table))
        if r.fetchone():
            return False
        else:
            return True

    def clear_tables(self, *tables):
        for tab in tables:
            if not self.is_table_empty(tab):
                sql = '''DELETE FROM "{0}";'''.format(tab)
                self.execute(sql)
            else:
                pass

    def get_centroids(self, gids, table, field='fid'):
        cells = {}
        for i in set(gids):
            sql = '''SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = {2};'''.format(table, field, i)
            geom = self.execute(sql).fetchone()[0]
            cells[i] = geom
        return cells

    def get_max(self, table, field='fid'):
        sql = '''SELECT MAX("{0}") FROM "{1}";'''.format(field, table)
        max_val = self.execute(sql).fetchone()[0]
        return max_val


class Flo2dGeoPackage(GeoPackageUtils):
    """GeoPackage object class for storing FLO-2D model data"""
    def __init__(self, path, iface):
        super(Flo2dGeoPackage, self).__init__(path)
        self.group = 'FLO-2D_{}'.format(os.path.basename(path).replace('.gpkg', ''))
        self.iface = iface
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.parser = None
        self.cell_size = None
        self.chunksize = float('inf')

    def set_parser(self, fname):
        self.parser = ParseDAT(fname)

    def import_fplain(self):
        self.cell_size, data = self.parser.parse_fplain_cadpts()
        if self.cell_size == 0:
            self.uc.bar_error("Cell size is 0 - something went wrong!")
        else:
            pass
        self.clear_tables('grid')
        # insert grid data into gpkg
        sql = '''INSERT INTO grid (fid, cell_north, cell_east, cell_south, cell_west, n_value, elevation, geom) VALUES'''
        inp = []
        c = 0
        sql_chunk = sql
        for d in data:
            if c < self.chunksize:
                g = square_from_center_and_size(d[-2], d[-1], self.cell_size)
                inp.append('({0}, {1})'.format(','.join(d[:7]), g))
                c += 1
            else:
                sql_chunk += '\n{0};'.format(',\n'.join(inp))
                self.execute(sql_chunk)
                sql_chunk = sql
                c = 0
                del inp[:]
        if len(inp) > 0:
            sql_chunk += '\n{0};'.format(',\n'.join(inp))
            self.execute(sql_chunk)
        else:
            pass

    def import_cont_toler(self):
        self.clear_tables('cont')
        sql = '''INSERT INTO cont (fid, name, value) VALUES'''
        sql_part = '''\n({0}, '{1}', '{2}'),'''
        cont = self.parser.parse_cont()
        toler = self.parser.parse_toler()
        cont.update(toler)
        c = 1
        for option in cont:
            sql += sql_part.format(c, option, cont[option])
            c += 1
        self.execute(sql[:-1])

    def import_inflow(self):
        self.clear_tables('inflow', 'time_series', 'time_series_data', 'reservoirs')

        head, inf, res = self.parser.parse_inflow()
        gids = inf.keys() + res.keys()
        cells = self.get_centroids(gids, 'grid')

        inflow_sql = '''INSERT INTO inflow (fid, time_series_fid, type, inoutfc, geom) VALUES'''
        ts_sql = '''INSERT INTO time_series (fid, hourdaily) VALUES'''
        tsd_sql = '''INSERT INTO time_series_data (fid, series_fid, time, value) VALUES'''
        reservoirs_sql = '''INSERT INTO reservoirs (fid, grid_fid, wsel, geom) VALUES'''

        inflow_part = '''\n({0}, {0}, '{1}', {2}, AsGPB(ST_Buffer(ST_GeomFromText('{3}'), {4}, 3))),'''
        ts_part = '''\n({0}, {1}),'''
        tsd_part = '''\n({0}, {1}, {2}, {3}),'''
        reservoirs_part = '''\n({0}, {1}, {2}, AsGPB(ST_Buffer(ST_GeomFromText('{3}'), {4}, 3))),'''

        fid = 1
        nfid = 1
        buff = self.cell_size * 0.25

        for gid in inf:
            row = inf[gid]['row']
            inflow_sql += inflow_part.format(fid, row[0], row[1], cells[gid], buff)
            ts_sql += ts_part.format(fid, head['IHOURDAILY'])
            for n in inf[gid]['nodes']:
                tsd_sql += tsd_part.format(nfid, fid, n[1], n[2])
                nfid += 1
            fid += 1

        fid = 1
        for gid in res:
            row = res[gid]['row']
            wsel = row[-1] if len(row) == 3 else 'NULL'
            reservoirs_sql += reservoirs_part.format(fid, row[1], wsel, cells[gid], buff)
            fid += 1

        if len(inf) > 0:
            self.execute(ts_sql[:-1])
            self.execute(inflow_sql[:-1])
            self.execute(tsd_sql[:-1])
        else:
            pass
        if len(res) > 0:
            self.execute(reservoirs_sql[:-1])
        else:
            pass

    def import_outflow(self):
        self.clear_tables('outflow', 'outflow_chan_elems', 'outflow_hydrographs')
        koutflow, noutflow, ooutflow = self.parser.parse_outflow()
        gids = koutflow.keys() + noutflow.keys() + ooutflow.keys()
        cells = self.get_centroids(gids, 'grid')

        outflow_sql = '''INSERT INTO outflow (fid, time_series_fid, ident, type, geom) VALUES'''
        ts_sql = '''INSERT INTO time_series (fid) VALUES'''
        tsd_sql = '''INSERT INTO time_series_data (fid, series_fid, time, value) VALUES'''

        outflow_part = '''\n({0}, {1}, NULL, '{2}', AsGPB(ST_Buffer(ST_GeomFromText('{3}'), {4}, 3))),'''
        ts_part = '''\n({0}),'''
        tsd_part = '''\n({0}, {1}, {2}, {3}),'''

        fid = 1
        fid_ts = self.get_max('time_series') + 1
        fid_tsd = self.get_max('time_series_data') + 1
        buff = self.cell_size * 0.25
        for gid in koutflow:
            row = koutflow[gid]['row']
            outflow_sql += outflow_part.format(fid, fid_ts, row[0], cells[gid], buff)
            ts_sql += ts_part.format(fid_ts)
            for n in koutflow[gid]['nodes']:
                tsd_sql += tsd_part.format(fid_tsd, fid_ts, n[1], n[2])
                fid_tsd += 1
            fid += 1
            fid_ts += 1

        if len(koutflow) > 0:
            self.execute(ts_sql[:-1])
            self.execute(outflow_sql[:-1])
            if tsd_sql.endswith(','):
                self.execute(tsd_sql[:-1])
            else:
                pass
        else:
            pass

    def import_topo(self):
        # in case FPLAIN is missing this require finding each grid cell neighbours
        pass

    def export_fplain(self, outdir):
        sql = 'SELECT fid, cell_north, cell_east, cell_south, cell_west, n_value, elevation, ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM grid;'
        records = self.execute(sql)
        fplain = os.path.join(outdir, 'FPLAIN.DAT')
        cadpts = os.path.join(outdir, 'CADPTS.DAT')

        fline = '{0: <10} {1: <10} {2: <10} {3: <10} {4: <10} {5: <10} {6: <10}\n'
        cline = '{0: <10} {1: <15} {2: <10}\n'
        with open(fplain, 'w') as f, open(cadpts, 'w') as c:

            for row in records:
                fid, n, e, s, w, man, elev, geom = row
                x, y = geom.strip('POINT()').split()
                f.write(fline.format(fid, n, e, s, w, '{0:.3f}'.format(man), '{0:.2f}'.format(elev)))
                c.write(cline.format(fid, '{0:.3f}'.format(float(x)), '{0:.3f}'.format(float(y))))

    def export_cont(self, outdir):
        lines = [
            ['SIMULT', 'TOUT', 'LGPLOT', 'METRIC', 'IBACKUPrescont'],
            ['ICHANNEL', 'MSTREET', 'LEVEE', 'IWRFS', 'IMULTC'],
            ['IRAIN', 'INFIL', 'IEVAP', 'MUD', 'ISED', 'IMODFLOW', 'SWMM'],
            ['IHYDRSTRUCT', 'IFLOODWAY', 'IDEBRV'],
            ['AMANN', 'DEPTHDUR', 'XCONC', 'XARF', 'FROUDL', 'SHALLOWN', 'ENCROACH'],
            ['NOPRTFP', 'SUPER'],
            ['NOPRTC'],
            ['ITIMTEP', 'TIMTEP'],
            ['GRAPTIM']
        ]
        tlines = [
            ['TOLGLOBAL', 'DEPTOL', 'WAVEMAX'],
            ['COURCHAR_C', 'COURANTFP', 'COURANTC', 'COURANTST'],
            ['COURCHAR_T', 'TIME_ACCEL']

        ]
        sql = 'SELECT name, value FROM cont;'
        options = {o: v for o, v in self.execute(sql).fetchall()}

        cont = os.path.join(outdir, 'CONT.DAT')
        toler = os.path.join(outdir, 'TOLER.DAT')
        rline = ' {0}'
        with open(cont, 'w') as c:
            nr = 1
            for row in lines:
                lst = ''
                for o in row:
                    val = options[o]
                    if val != 'None':
                        self.uc.log_info(val)
                        lst += rline.format(val)
                    else:
                        pass
                if nr == 1:
                    lst += ' Pro Model - Build No. 15.07.12'
                else:
                    pass
                lst += '\n'
                c.write(lst)
                nr += 1

        with open(toler, 'w') as t:
            for row in tlines:
                lst = ''
                for o in row:
                    val = options[o]
                    if val != 'None':
                        lst += rline.format(val)
                    else:
                        pass
                lst += '\n'
                t.write(lst)
