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
import os
import pyspatialite.dbapi2 as db
from .utils import *
from itertools import chain
from .user_communication import UserCommunication
from flo2d_parser import ParseDAT


class GeoPackageUtils(object):
    """GeoPackage utils for handling GPKG files"""
    def __init__(self, path):
        self.path = path
        self.conn = None
        self.msg = None

    def database_create(self):
        """Create geopackage with SpatiaLite functions"""
        try:
            # delete db file if exists
            if os.path.exists(self.path):
                try:
                    os.remove(self.path)
                except:
                    self.msg = "Couldn't write on the existing GeoPackage file. Check if it is not opened by another process."
                    return False
            self.conn = db.connect(self.path)
            plugin_dir = os.path.dirname(__file__)
            script = os.path.join(plugin_dir, 'db_structure.sql')
            qry = open(script, 'r').read()
            c = self.conn.cursor()
            c.executescript(qry)
            self.conn.commit()
            c.close()
            return True
        except:
            self.msg = "Couldn't create GeoPackage"
            return False
        
    
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
        self.parser = ParseDAT()
        self.cell_size = None
        self.chunksize = float('inf')

    def set_parser(self, fpath):
        self.parser.scan_project_dir(fpath)

    def import_mannings_n_topo(self):
        if self.cell_size == 0:
            self.uc.bar_error("Cell size is 0 - something went wrong!")
        else:
            pass

        self.clear_tables('grid')
        # insert grid data into gpkg
        sql = '''INSERT INTO grid (fid, n_value, elevation, geom) VALUES'''
        inp = []
        c = 0
        sql_chunk = sql
        data = self.parser.parse_mannings_n_topo()
        for d in data:
            man = slice(0, 2)
            coords = slice(2, 4)
            elev = slice(4, None)
            if c < self.chunksize:
                g = square_from_center_and_size(self.cell_size, *d[coords])
                inp.append('({0}, {1})'.format(','.join(d[man] + d[elev]), g))
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
            coords = slice(8, 10)
            fplain = slice(0, 7)
            if c < self.chunksize:
                g = square_from_center_and_size(self.cell_size, *d[coords])
                inp.append('({0}, {1})'.format(','.join(d[fplain]), g))
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
        sql = '''INSERT INTO cont (name, value) VALUES'''
        sql_part = '''\n('{0}', '{1}'),'''
        cont = self.parser.parse_cont()
        toler = self.parser.parse_toler()
        cont.update(toler)
        for option in cont:
            sql += sql_part.format(option, cont[option])
        self.execute(sql.rstrip(','))

    def import_inflow(self):
        self.clear_tables('inflow', 'time_series', 'time_series_data', 'reservoirs')

        head, inf, res = self.parser.parse_inflow()
        gids = inf.keys() + res.keys()
        cells = self.get_centroids(gids, 'grid')

        inflow_sql = '''INSERT INTO inflow (fid, time_series_fid, ident, inoutfc, geom) VALUES'''
        ts_sql = '''INSERT INTO time_series (fid, hourdaily) VALUES'''
        tsd_sql = '''INSERT INTO time_series_data (fid, series_fid, time, value, value2) VALUES'''
        reservoirs_sql = '''INSERT INTO reservoirs (fid, grid_fid, wsel, geom) VALUES'''
        cont_sql = '''INSERT INTO cont (name, value) VALUES ('IDEPLT', '{0}');'''

        inflow_part = '''\n({0}, {0}, '{1}', {2}, AsGPB(ST_Buffer(ST_GeomFromText('{3}'), {4}, 3))),'''
        ts_part = '''\n({0}, {1}),'''
        tsd_part = '''\n({0}, {1}, {2}, {3}, {4}),'''
        reservoirs_part = '''\n({0}, {1}, {2}, AsGPB(ST_Buffer(ST_GeomFromText('{3}'), {4}, 3))),'''

        fid = 1
        nfid = 1
        buff = self.cell_size * 0.4

        for gid in inf:
            row = inf[gid]['row']
            inflow_sql += inflow_part.format(fid, row[0], row[1], cells[gid], buff)
            ts_sql += ts_part.format(fid, head['IHOURDAILY'])
            values = slice(1, None)
            for n in inf[gid]['time_series']:
                tsd_sql += tsd_part.format(nfid, fid, *n[values])
                nfid += 1
            fid += 1

        fid = 1
        for gid in res:
            row = res[gid]['row']
            wsel = row[-1] if len(row) == 3 else 'NULL'
            reservoirs_sql += reservoirs_part.format(fid, row[1], wsel, cells[gid], buff)
            fid += 1

        self.execute(cont_sql.format(head['IDEPLT']))
        sql_list = [ts_sql, inflow_sql, tsd_sql, reservoirs_sql]
        for sql in sql_list:
            if sql.endswith(','):
                self.execute(sql.rstrip(','))
            else:
                pass

    def import_outflow(self):
        self.clear_tables('outflow', 'outflow_hydrographs', 'qh_params')
        koutflow, noutflow, ooutflow = self.parser.parse_outflow()
        gids = koutflow.keys() + noutflow.keys() + ooutflow.keys()
        cells = self.get_centroids(gids, 'grid')

        outflow_sql = '''INSERT INTO outflow (fid, time_series_fid, ident, nostacfp, qh_params_fid, geom) VALUES'''
        qh_sql = '''INSERT INTO qh_params (hmax, coef, expontent) VALUES'''
        ts_sql = '''INSERT INTO time_series (fid) VALUES'''
        tsd_sql = '''INSERT INTO time_series_data (fid, series_fid, time, value, value2) VALUES'''
        hydchar_sql = '''INSERT INTO outflow_hydrographs (hydro_fid, grid_fid) VALUES'''

        outflow_part = '''\n({0}, {1}, '{2}', {3}, {4}, AsGPB(ST_Buffer(ST_GeomFromText('{5}'), {6}, 3))),'''
        qh_part = '''\n({0}, {1}, {2}),'''
        ts_part = '''\n({0}),'''
        tsd_part = '''\n({0}, {1}, {2}, {3}, {4}),'''
        hydchar_part_sql = '''\n('{0}', {1}),'''

        fid = 1
        fid_qh = 1
        fid_ts = self.get_max('time_series') + 1
        fid_tsd = self.get_max('time_series_data') + 1
        buff = self.cell_size * 0.4
        outflow = chain(koutflow.iteritems(), noutflow.iteritems())

        for gid, val in outflow:
            row, time_series, qh = val['row'], val['time_series'], val['qh']
            if qh:
                qhfid = fid_qh
                fid_qh += 1
                qh_sql += qh_part.format(*qh[0])
            else:
                qhfid = 'NULL'
            if time_series:
                tsfid = fid_ts
                fid_ts += 1
                ts_sql += ts_part.format(tsfid)
            else:
                tsfid = 'NULL'
            ident = row[0]
            nostacfp = row[-1] if ident == 'N' else 'NULL'
            outflow_sql += outflow_part.format(fid, tsfid, ident, nostacfp, qhfid, cells[gid], buff)
            values = slice(1, None)
            for n in time_series:
                tsd_sql += tsd_part.format(fid_tsd, fid_ts, *n[values])
                fid_tsd += 1
            fid += 1

        for gid, val in ooutflow.iteritems():
            row = val['row']
            hydchar_sql += hydchar_part_sql.format(*row)

        sql_list = [ts_sql, qh_sql, outflow_sql, tsd_sql, hydchar_sql]
        for sql in sql_list:
            if sql.endswith(','):
                self.execute(sql.rstrip(','))
            else:
                pass

    def export_mannings_n_topo(self, outdir):
        sql = '''SELECT fid, n_value, elevation, ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM grid;'''
        records = self.execute(sql)
        mannings = os.path.join(outdir, 'MANNINGS_N.DAT')
        topo = os.path.join(outdir, 'TOPO.DAT')

        mline = '{0: >10} {1: >10}\n'
        tline = '{0: >15} {1: >15} {2: >10}\n'

        with open(mannings, 'w') as m, open(topo, 'w') as t:
            for row in records:
                fid, man, elev, geom = row
                x, y = geom.strip('POINT()').split()
                m.write(mline.format(fid, '{0:.3f}'.format(man)))
                t.write(tline.format('{0:.3f}'.format(float(x)), '{0:.3f}'.format(float(y)), '{0:.2f}'.format(elev)))

    def export_fplain(self, outdir):
        sql = '''SELECT fid, cell_north, cell_east, cell_south, cell_west, n_value, elevation, ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM grid;'''
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
        sql = '''SELECT name, value FROM cont;'''
        options = {o: v for o, v in self.execute(sql).fetchall()}
        cont = os.path.join(outdir, 'CONT.DAT')
        toler = os.path.join(outdir, 'TOLER.DAT')
        rline = ' {0}'
        with open(cont, 'w') as c:
            nr = 1
            for row in self.parser.cont_rows:
                lst = ''
                for o in row:
                    val = options[o]
                    if val != 'None':
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
            for row in self.parser.toler_rows:
                lst = ''
                for o in row:
                    val = options[o]
                    if val != 'None':
                        lst += rline.format(val)
                    else:
                        pass
                lst += '\n'
                t.write(lst)

    def export_inflow(self, outdir):
        cont_sql = '''SELECT value FROM cont WHERE name = 'IDEPLT';'''
        inflow_sql = '''SELECT fid, time_series_fid, ident, inoutfc FROM inflow;'''
        inflow_cells_sql = '''SELECT inflow_fid, grid_fid FROM inflow_cells;'''
        ts_sql = '''SELECT hourdaily FROM time_series;'''
        ts_data_sql = '''SELECT time, value, value2 FROM time_series_data WHERE series_fid = {0};'''
        reservoirs_sql = '''SELECT grid_fid, wsel FROM reservoirs;'''

        head_line = ' {0: <15} {1}'
        inf_line = '\n{0: <15} {1: <15} {2}'
        tsd_line = '\nH              {0: <15} {1: <15} {2}'
        res_line = '\nR              {0: <15} {1}'

        inf_rows = self.execute(inflow_sql).fetchall()
        inf_cells = dict(self.execute(inflow_cells_sql).fetchall())
        hourdaily = self.execute(ts_sql).fetchone()[0]
        idplt = self.execute(cont_sql).fetchall()[0][0]

        inflow = os.path.join(outdir, 'INFLOW.DAT')
        with open(inflow, 'w') as i:
            i.write(head_line.format(hourdaily, idplt))
            for row in inf_rows:
                fid, ts_fid, ident, inoutfc = row
                gid = inf_cells[fid]
                i.write(inf_line.format(ident, inoutfc, gid))
                series = self.execute(ts_data_sql.format(ts_fid))
                for tsd_row in series:
                    i.write(tsd_line.format(*tsd_row).replace('None', '').rstrip())
            for res in self.execute(reservoirs_sql):
                i.write(res_line.format(*res).replace('None', '').rstrip())

    def export_outflow(self, outdir):
        outflow_sql = '''SELECT fid, time_series_fid, ident, nostacfp, qh_params_fid FROM outflow;'''
        outflow_cells_sql = '''SELECT outflow_fid, grid_fid FROM outflow_cells;'''
        outflow_chan_sql = '''SELECT outflow_fid, elem_fid FROM outflow_chan_elems;'''
        qh_sql = '''SELECT hmax, coef, expotent FROM qh_params WHERE fid = {0};'''
        ts_data_sql = '''SELECT time, value, value2 FROM time_series_data WHERE series_fid = {0};'''
        hydchar_sql = '''SELECT hydro_fid, grid_fid FROM outflow_hydrographs;'''

        out_line = '{0: <15} {1: <15} {2}\n'
        qh_line = 'H {0: <15} {1: <15} {2}\n'
        tsd_line = '{0: <15} {1: <15} {2}\n'
        hyd_line = '{0: <15} {1}\n'

        out_rows = self.execute(outflow_sql).fetchall()
        out_cells = dict(self.execute(outflow_cells_sql).fetchall())
        out_chan = dict(self.execute(outflow_chan_sql).fetchall())

        outflow = os.path.join(outdir, 'OUTFLOW.DAT')
        with open(outflow, 'w') as o:
            for row in out_rows:
                fid, ts_fid, ident, nostacfp, qh_fid = row
                gid = out_chan[fid] if ident == 'K' else out_cells[fid]
                o.write(out_line.format(ident, gid, nostacfp).replace('None', ''))
                if qh_fid is not None:
                    qh_params = self.execute(qh_sql.format(qh_fid)).fetchone()
                    o.write(qh_line.format(*qh_params[0]))
                else:
                    pass
                if ts_fid is not None:
                    series = self.execute(ts_data_sql.format(ts_fid))
                    for tsd_row in series:
                        o.write(tsd_line.format(*tsd_row).replace('None', ''))
                else:
                    pass
            for hyd in self.execute(hydchar_sql):
                o.write(hyd_line.format(*hyd))
