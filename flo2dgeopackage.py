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


class Flo2dGeoPackage(object):
    """GeoPackage object class for storing FLO-2D model data"""

    def __init__(self, path, iface):
        self.path = path
        self.group = 'FLO-2D_{}'.format(os.path.basename(path).replace('.gpkg', ''))
        self.iface = iface
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.parser = None
        self.cell_size = None

    def set_parser(self, fname):
        self.parser = ParseDAT(fname)

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
        r = self.execute("SELECT rowid FROM {0};".format(table))
        if r.fetchone():
            return False
        else:
            return True

    def clear_tables(self, *tables):
        for tab in tables:
            if not self.is_table_empty(tab):
                sql = 'DELETE FROM "{0}";'.format(tab)
                self.execute(sql)
            else:
                pass

    def get_centroids(self, gids):
        cells = {}
        for i in set(gids):
            sql = '''SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM grid WHERE fid = {0};'''.format(i)
            geom = self.execute(sql).fetchone()[0]
            cells[i] = geom
        return cells

    def get_max(self, table, field='fid'):
        sql = '''SELECT MAX("{0}") FROM "{1}";'''.format(table, field)
        max_val = self.execute(sql).fetchone()[0]
        return max_val

    def import_fplain(self):
        self.cell_size, data = self.parser.parse_fplain_cadpts()
        if self.cell_size == 0:
            self.uc.bar_error("Cell size is 0 - something went wrong!")
        else:
            pass
        self.clear_tables('grid')
        # insert grid data into gpkg
        sql = """INSERT INTO grid (fid, cell_north, cell_east, cell_south, cell_west, n_value, elevation, geom) VALUES"""
        inp = []
        for d in data:
            g = square_from_center_and_size(d[-2], d[-1], self.cell_size)
            inp.append('({0}, {1})'.format(','.join(d[:7]), g))
        sql += '\n{0};'.format(',\n'.join(inp))
        self.execute(sql)

    def import_cont_toler(self):
        self.clear_tables('cont')
        sql = """INSERT INTO cont (fid, name, value, note) VALUES"""
        cont = self.parser.parse_cont()
        toler = self.parser.parse_toler()
        cont.update(toler)
        c = 1
        for option in cont:
            sql += "\n({0}, '{1}', '{2}', NULL),".format(c, option, cont[option])
            c += 1
#        self.uc.log_info(sql[:-1])
        self.execute(sql[:-1])

    def import_inflow(self):
        self.clear_tables('inflow', 'time_series', 'time_series_data', 'reservoirs')

        head, inf, res = self.parser.parse_inflow()
        gids = inf.keys() + res.keys()
        cells = self.get_centroids(gids)

        time_series_sql = """INSERT INTO time_series (fid, name, type, hourdaily) VALUES"""
        inflow_sql = """INSERT INTO inflow (fid, name, time_series_fid, type, inoutfc, geom, note) VALUES"""
        time_series_data_sql = """INSERT INTO time_series_data (fid, series_fid, time, value) VALUES"""
        reservoirs_sql = """INSERT INTO reservoirs (fid, name, grid_fid, wsel, geom, note) VALUES"""

        fid = 1
        nfid = 1
        buff = self.cell_size/4
        for gid in inf:
            row = inf[gid]['row']
            time_series_sql += "\n({0}, NULL, NULL, {1}),".format(fid, head['IHOURDAILY'])
            inflow_sql += "\n({0}, NULL, {0}, '{1}', {2}, AsGPB(ST_Buffer(ST_GeomFromText('{3}'), {4}, 3)), NULL),".format(fid, row[0], row[1], cells[gid], buff)
            for n in inf[gid]['nodes']:
                time_series_data_sql += "\n({0}, {1}, {2}, {3}),".format(nfid, fid, n[1], n[2])
                nfid += 1
            fid += 1
        fid = 1
        for gid in res:
            row = res[gid]['row']
            wsel = row[-1] if len(row) == 3 else 'NULL'
            reservoirs_sql += "\n({0}, NULL, {1}, {2}, AsGPB(ST_Buffer(ST_GeomFromText('{3}'), {4}, 3)), NULL),".format(fid, row[1], wsel, cells[gid], buff)
            fid += 1

        if len(inf) > 0:
            self.execute(time_series_sql[:-1])
            self.execute(inflow_sql[:-1])
            self.execute(time_series_data_sql[:-1])
        else:
            pass
        if len(res) > 0:
            self.execute(reservoirs_sql[:-1])
        else:
            pass

    def import_outflow(self):
        self.clear_tables('outflow', 'outflow_chan_elems', 'outflow_hydrographs')
        ch, ts, fp = self.parser.parse_outflow()
        gids = ch.keys() + ts.keys() + fp.keys()
        cells = self.get_centroids(gids)



    def import_topo(self):
        # in case FPLAIN is missing this require finding each grid cell neighbours
        pass
