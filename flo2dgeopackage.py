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
from .utils import *
from flo2d_parser import ParseDAT
from .user_communication import UserCommunication


class GeoPackageUtils(object):
    """GeoPackage utils for handling GPKG files"""
    def __init__(self, path):
        self.path = path
        self.conn = None
        self.msg = None

    def database_create(self):
        """Create geopackage with SpatiaLite functions"""
#        try:
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
#        except:
#            self.msg = "Couldn't create GeoPackage"
#            return False

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

    def get_centroids(self, gids, table='grid', field='fid'):
        cells = {}
        for i in set(gids):
            sql = '''SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = {2};'''.format(table, field, i)
            geom = self.execute(sql).fetchone()[0]
            cells[i] = geom
        return cells

    def build_linestring(self, gids, table='grid', field='fid'):
        line_sql = '''LINESTRING('''
        for i in gids:
            sql = '''SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = {2};'''.format(table, field, i)
            geom = self.execute(sql).fetchone()[0]
            points = geom.strip('POINT()') + ','
            line_sql += points
        line_sql = line_sql.strip(',') + ')'
        return line_sql

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
        self.buffer = None
        self.chunksize = float('inf')

    def set_parser(self, fpath):
        self.parser.scan_project_dir(fpath)
        self.cell_size = self.parser.calculate_cellsize()
        self.buffer = self.cell_size * 0.4

    def _import_fplain(self):
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
        data = self.parser.parse_fplain_cadpts()
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

    def _export_fplain(self, outdir):
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

    def import_cont_toler(self):
        self.clear_tables('cont')
        sql = '''INSERT INTO cont (name, value) VALUES'''
        sql_part = '''\n('{0}', '{1}'),'''
        cont = self.parser.parse_cont()
        toler = self.parser.parse_toler()
        cont.update(toler)
        for option in cont:
            sql += sql_part.format(option, cont[option])
        self.execute(sql.replace("'None'", 'NULL').rstrip(','))

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

    def import_inflow(self):
        self.clear_tables('inflow', 'time_series', 'time_series_data', 'reservoirs')

        head, inf, res = self.parser.parse_inflow()
        gids = inf.keys() + res.keys()
        cells = self.get_centroids(gids)

        inflow_sql = '''INSERT INTO inflow (time_series_fid, ident, inoutfc, geom) VALUES'''
        ts_sql = '''INSERT INTO time_series (hourdaily) VALUES'''
        tsd_sql = '''INSERT INTO time_series_data (series_fid, time, value, value2) VALUES'''
        reservoirs_sql = '''INSERT INTO reservoirs (grid_fid, wsel, geom) VALUES'''
        cont_sql = '''INSERT INTO cont (name, value) VALUES ('IDEPLT', '{0}');'''

        inflow_part = '''\n({0}, '{1}', {2}, AsGPB(ST_Buffer(ST_GeomFromText('{3}'), {4}, 3))),'''
        ts_part = '''\n({0}),'''
        tsd_part = '''\n({0}, {1}, {2}, {3}),'''
        reservoirs_part = '''\n({0}, {1}, AsGPB(ST_Buffer(ST_GeomFromText('{2}'), {3}, 3))),'''

        fid = 1
        for gid in inf:
            row = inf[gid]['row']
            inflow_sql += inflow_part.format(fid, row[0], row[1], cells[gid], self.buffer)
            ts_sql += ts_part.format(head['IHOURDAILY'])
            values = slice(1, None)
            for n in inf[gid]['time_series']:
                tsd_sql += tsd_part.format(fid, *n[values])
            fid += 1

        for gid in res:
            row = res[gid]['row']
            wsel = row[-1] if len(row) == 3 else 'NULL'
            reservoirs_sql += reservoirs_part.format(row[1], wsel, cells[gid], self.buffer)

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
        cells = self.get_centroids(gids)

        outflow_sql = '''INSERT INTO outflow (time_series_fid, ident, nostacfp, qh_params_fid, geom) VALUES'''
        qh_sql = '''INSERT INTO qh_params (hmax, coef, expontent) VALUES'''
        ts_sql = '''INSERT INTO time_series (fid) VALUES'''
        tsd_sql = '''INSERT INTO time_series_data (series_fid, time, value, value2) VALUES'''
        hydchar_sql = '''INSERT INTO outflow_hydrographs (hydro_fid, grid_fid) VALUES'''

        outflow_part = '''\n({0}, '{1}', {2}, {3}, AsGPB(ST_Buffer(ST_GeomFromText('{4}'), {5}, 3))),'''
        qh_part = '''\n({0}, {1}, {2}),'''
        ts_part = '''\n({0}),'''
        tsd_part = '''\n({0}, {1}, {2}, {3}),'''
        hydchar_part_sql = '''\n('{0}', {1}),'''

        fid = 1
        fid_qh = 1
        fid_ts = self.get_max('time_series') + 1
        tsd_val = slice(1, None)
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
            outflow_sql += outflow_part.format(tsfid, ident, nostacfp, qhfid, cells[gid], self.buffer)
            for n in time_series:
                tsd_sql += tsd_part.format(fid_ts, *n[tsd_val])
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

    def import_rain(self):
        self.clear_tables('rain', 'rain_arf_areas')
        options, time_series, rain_arf = self.parser.parse_rain()
        gids = [x[0] for x in rain_arf]
        cells = self.get_centroids(gids)
        rain_sql = '''INSERT INTO rain (time_series_fid, irainreal, ireainbuilding, tot_rainfall, rainabs, irainarf, movingstrom, rainspeed, iraindir) VALUES'''
        ts_sql = '''INSERT INTO time_series (fid) VALUES'''
        tsd_sql = '''INSERT INTO time_series_data (series_fid, time, value) VALUES'''
        rain_arf_sql = '''INSERT INTO rain_arf_areas (rain_fid, arf, geom) VALUES'''

        rain_part = '''\n({0}, {1}, {2}, {3}, {4}, {5}, {6}, {7}, {8}),'''
        ts_part = '''\n({0}),'''
        tsd_part = '''\n({0}, {1}, {2}),'''
        rain_arf_part = '''\n({0}, {1}, AsGPB(ST_Buffer(ST_GeomFromText('{2}'), {3}, 3))),'''

        fid = 1
        fid_ts = self.get_max('time_series') + 1

        rain_sql += rain_part.format(fid_ts, *options.values())
        ts_sql += ts_part.format(fid_ts)

        for row in time_series:
            char, time, value = row
            tsd_sql += tsd_part.format(fid_ts, time, value)

        for row in rain_arf:
            gid, val = row
            rain_arf_sql += rain_arf_part.format(fid, val, cells[gid], self.buffer)

        sql_list = [ts_sql, rain_sql, tsd_sql, rain_arf_sql]
        for sql in sql_list:
            if sql.endswith(','):
                self.execute(sql.rstrip(','))
            else:
                pass

    def import_infil(self):
        self.clear_tables('infil', 'infil_chan_seg', 'infil_areas_green', 'infil_areas_scs',  'infil_areas_horton ', 'infil_areas_chan')
        data = self.parser.parse_infil()
        infil_params = ['infmethod', 'abstr', 'sati', 'satf', 'poros', 'soild', 'infchan', 'hydcall', 'soilall', 'hydcadj', 'scsnall', 'abstr1', 'fhortoni', 'fhortonf', 'decaya']
        infil_sql = 'INSERT INTO infil (' + ', '.join(infil_params) + ') VALUES ('
        infil_sql += ', '.join([data[k.upper()] if k.upper() in data else 'NULL' for k in infil_params]) + '),'
        infil_seg_sql = '''INSERT INTO infil_chan_seg (chan_seg_fid, hydcx, hydcxfinal, soildepthcx) VALUES'''
        infil_green_sql = '''INSERT INTO infil_areas_green (geom, hydc, soils, dtheta, abstrinf, rtimpf, soil_depth) VALUES'''
        infil_scs_sql = '''INSERT INTO infil_areas_scs (geom, scscn) VALUES'''
        infil_chan_sql = '''INSERT INTO infil_areas_chan (geom, hydconch) VALUES'''
        infil_horton_sql = '''INSERT INTO infil_areas_horton (geom, fhorti, fhortf, deca) VALUES'''


        seg_part = '\n({0}, {1}, {2}, {3}),'
        green_part = '''\n(AsGPB(ST_Buffer(ST_GeomFromText('{0}'), {1}, 3)), {2}, {3}, {4}, {5}, {6}, {7}),'''
        scs_part = '''\n(AsGPB(ST_Buffer(ST_GeomFromText('{0}'), {1}, 3)), {2}),'''
        chan_part = '''\n(AsGPB(ST_Buffer(ST_GeomFromText('{0}'), {1}, 3)), {2}),'''
        horton_part = '''\n(AsGPB(ST_Buffer(ST_GeomFromText('{0}'), {1}, 3)), {2}, {3}, {4}),'''

        sqls = {
            'F': [infil_green_sql, green_part],
            'S': [infil_scs_sql, scs_part],
            'H': [infil_horton_sql, horton_part]
        }

        gids = [x[0] for x in chain(data['F'], data['S'], data['H'])]
        cells = self.get_centroids(gids)
        for i, row in enumerate(data['R']):
            infil_seg_sql += seg_part.format(i+1, *row)
        for i, row in enumerate(data['C']):
            pass
        for k in sqls:
            if len(data[k]) == 0:
                continue
            else:
                for row in data[k]:
                    self.uc.log_info(repr(row))
                    gid = row[0]
                    sqls[k][0] += sqls[k][1].format(cells[gid], self.cell_size, *row[1:])
        sql_list = [infil_sql, infil_seg_sql] + [x[0] for x in sqls.values()]
        for sql in sql_list:
            self.uc.log_info(sql)
            if sql.endswith(','):
                self.execute(sql.rstrip(','))
            else:
                pass

    def import_evapor(self):
        self.clear_tables('evapor', 'evapor_monthly', 'evapor_hourly')
        head, data = self.parser.parse_evapor()
        evapor_sql = '''INSERT INTO evapor (ievapmonth, iday, clocktime) VALUES'''
        evapor_mont_sql = '''INSERT INTO evapor_monthly (month, monthly_evap) VALUES'''
        evapor_hour_sql = '''INSERT INTO evapor_hourly (month, hour, hourly_evap) VALUES'''

        evapor_part = '''\n({0}, {1}, {2}),'''
        evapor_month_part = '''\n('{0}', {1}),'''
        evapor_hour_part = '''\n('{0}', {1}, {2}),'''

        evapor_sql += evapor_part.format(*head)
        for month in data:
            row = data[month]['row']
            time_series = data[month]['time_series']
            evapor_mont_sql += evapor_month_part.format(*row)
            for h, ts in enumerate(time_series):
                evapor_hour_sql += evapor_hour_part.format(month, h+1, ts)

        sql_list = [evapor_sql, evapor_mont_sql, evapor_hour_sql]
        for sql in sql_list:
            if sql.endswith(','):
                self.execute(sql.rstrip(','))
            else:
                pass

    def import_chan(self):
        self.clear_tables('chan', 'chan_r', 'chan_v', 'chan_t', 'chan_n', 'chan_confluences', 'noexchange_chan_areas', 'chan_wsel')
        segments, wsel, confluence, noexchange = self.parser.parse_chan()
        chan_sql = '''INSERT INTO chan (geom, depinitial, froudc, roughadj, isedn) VALUES'''
        chan_r_sql = '''INSERT INTO chan_r (seg_fid, nr_in_seg, ichangrid, bankell, bankelr, fcn, fcw, fcd, xlen, rbankgrid) VALUES'''
        chan_v_sql = '''INSERT INTO chan_v (seg_fid, nr_in_seg, ichangrid, bankell, bankelr, fcn, fcd, xlen, a1, a2, b1, b2, c1, c2, excdep, a11, a22, b11, b22, c11, c22, rbankgrid) VALUES'''
        chan_t_sql = '''INSERT INTO chan_t (seg_fid, nr_in_seg, ichangrid, bankell, bankelr, fcn, fcw, fcd, xlen, zl, zr, rbankgrid) VALUES'''
        chan_n_sql = '''INSERT INTO chan_n (seg_fid, nr_in_seg, ichangrid, fcn, xlen, nxecnum, rbankgrid) VALUES'''
        chan_wsel_sql = '''INSERT INTO chan_wsel (istart, wselstart, iend, wselend) VALUES'''
        chan_conf_sql = '''INSERT INTO chan_confluences (conf_fid, type, chan_elem_fid) VALUES'''
        chan_e_sql = '''INSERT INTO noexchange_chan_areas (geom) VALUES'''

        chan_part = '''\n(AsGPB(ST_GeomFromText('{0}')), {1}, {2}, {3}, {4}),'''
        chan_r_part = '\n(' + ','.join(['{} '] * 10) + '),'
        chan_v_part = '\n(' + ','.join(['{} '] * 22) + '),'
        chan_t_part = '\n(' + ','.join(['{} '] * 12) + '),'
        chan_n_part = '\n(' + ','.join(['{} '] * 7) + '),'
        chan_wsel_part = '\n(' + ','.join(['{} '] * 4) + '),'
        chan_conf_part = '\n(' + ','.join(['{} '] * 3) + '),'
        chan_e_part = '''\n(AsGPB(ST_Buffer(ST_GeomFromText('{0}'), {1}, 3))),'''

        sqls = {
            'R': [chan_r_sql, chan_r_part],
            'V': [chan_v_sql, chan_v_part],
            'T': [chan_t_sql, chan_t_part],
            'N': [chan_n_sql, chan_n_part]
        }

        for i, seg in enumerate(segments):
            xs = seg[-1]
            gids = []
            for ii, row in enumerate(xs):
                char = row[0]
                gid = row[1]
                params = row[1:]
                gids.append(gid)
                sqls[char][0] += sqls[char][1].format(i+1, ii+1, *params)
            options = seg[:-1]
            geom = self.build_linestring(gids)
            chan_sql += chan_part.format(geom, *options)

        for row in wsel:
            chan_wsel_sql += chan_wsel_part.format(*row)

        for i, row in enumerate(confluence):
            conf_fid = i + 1
            chan_conf_sql += chan_conf_part.format(conf_fid, 0, row[1])
            chan_conf_sql += chan_conf_part.format(conf_fid, 1, row[2])

        for row in noexchange:
            gid = row[-1]
            geom = self.get_centroids([gid])[0]
            chan_e_sql += chan_e_part.format(geom, self.buffer)

        sql_list = [x[0] for x in sqls.values()]
        sql_list.insert(0, chan_sql)
        sql_list.extend([chan_conf_sql, chan_e_sql, chan_wsel_sql])
        for sql in sql_list:
            if sql.endswith(','):
                self.execute(sql.rstrip(','))
            else:
                pass
        
        # create geometry for the newly added cross-sections
        for chtype in ['r', 'v', 't', 'n']:
            sql = "UPDATE chan_{0} SET notes='imported';"
            self.execute(sql.format(chtype))
            sql = """
            UPDATE "chan_{0}"
            SET geom = (
                SELECT
                    AsGPB(MakeLine((ST_Centroid(CastAutomagic(g1.geom))),
                    (ST_Centroid(CastAutomagic(g2.geom)))))
                FROM grid AS g1, grid AS g2
                WHERE g1.fid = ichangrid AND g2.fid = rbankgrid);
            """
            self.execute(sql.format(chtype))
            sql = "UPDATE chan_{0} SET notes=NULL;"
            self.execute(sql.format(chtype))
            
    def import_xsec(self):
        self.clear_tables('xsec_n_data')
        xsec_sql = '''INSERT INTO xsec_n_data (chan_n_nxsecnum, xi, yi) VALUES'''
        chan_n_sql = '''UPDATE chan_n SET xsecname = '{0}' WHERE nxecnum = {1};'''
        xsec_part = '''\n({0}, {1}, {2}),'''
        data = self.parser.parse_xsec()
        for xsec in data:
            nr, name, nodes = xsec
            self.execute(chan_n_sql.format(name, nr))
            for row in nodes:
                xsec_sql += xsec_part.format(nr, *row)
        if xsec_sql.endswith(','):
            self.execute(xsec_sql.rstrip(','))
        else:
            pass

    def export_cont(self, outdir):
        sql = '''SELECT name, value FROM cont;'''
        options = {o: v for o, v in self.execute(sql).fetchall()}
        cont = os.path.join(outdir, 'CONT.DAT')
        toler = os.path.join(outdir, 'TOLER.DAT')
        rline = ' {0}'
        with open(cont, 'w') as c:
            for row in self.parser.cont_rows:
                lst = ''
                for o in row:
                    val = options[o]
                    lst += rline.format(val)
                lst += '\n'
                c.write(lst.replace('None', ''))

        with open(toler, 'w') as t:
            for row in self.parser.toler_rows:
                lst = ''
                for o in row:
                    val = options[o]
                    lst += rline.format(val)
                lst += '\n'
                t.write(lst.replace('None', ''))

    def export_mannings_n_topo(self, outdir):
        sql = '''SELECT fid, n_value, elevation, ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM grid ORDER BY fid;'''
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

    def export_inflow(self, outdir):
        cont_sql = '''SELECT value FROM cont WHERE name = 'IDEPLT';'''
        inflow_sql = '''SELECT fid, time_series_fid, ident, inoutfc FROM inflow ORDER BY fid;'''
        inflow_cells_sql = '''SELECT inflow_fid, grid_fid FROM inflow_cells ORDER BY fid;'''
        ts_sql = '''SELECT hourdaily FROM time_series;'''
        ts_data_sql = '''SELECT time, value, value2 FROM time_series_data WHERE series_fid = {0} ORDER BY fid;'''
        reservoirs_sql = '''SELECT grid_fid, wsel FROM reservoirs ORDER BY fid;'''

        head_line = ' {0: <15} {1}'
        inf_line = '\n{0: <15} {1: <15} {2}'
        tsd_line = '\nH              {0: <15} {1: <15} {2}'
        res_line = '\nR              {0: <15} {1}'

        inf_rows = self.execute(inflow_sql)
        inf_cells = dict(self.execute(inflow_cells_sql).fetchall())
        hourdaily = self.execute(ts_sql).fetchone()[0]
        idplt = self.execute(cont_sql).fetchone()[0]

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
        outflow_sql = '''SELECT fid, time_series_fid, ident, nostacfp, qh_params_fid FROM outflow ORDER BY fid;'''
        outflow_cells_sql = '''SELECT outflow_fid, grid_fid FROM outflow_cells ORDER BY fid;'''
        outflow_chan_sql = '''SELECT outflow_fid, elem_fid FROM outflow_chan_elems ORDER BY fid;'''
        qh_sql = '''SELECT hmax, coef, expotent FROM qh_params WHERE fid = {0};'''
        ts_data_sql = '''SELECT time, value, value2 FROM time_series_data WHERE series_fid = {0} ORDER BY fid;'''
        hydchar_sql = '''SELECT hydro_fid, grid_fid FROM outflow_hydrographs ORDER BY fid;'''

        out_line = '{0: <15} {1: <15} {2}\n'
        qh_line = 'H {0: <15} {1: <15} {2}\n'
        tsd_line = '{0: <15} {1: <15} {2}\n'
        hyd_line = '{0: <15} {1}\n'

        out_rows = self.execute(outflow_sql)
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

    def export_rain(self, outdir):
        rain_sql = '''SELECT time_series_fid, irainreal, ireainbuilding, tot_rainfall, rainabs, irainarf, movingstrom, rainspeed, iraindir FROM rain;'''
        rain_cells_sql = '''SELECT grid_fid, arf FROM rain_arf_cells; ORDER BY fid'''
        ts_data_sql = '''SELECT time, value FROM time_series_data WHERE series_fid = {0} ORDER BY fid;'''

        rain_line1 = '{0}  {1}\n'
        rain_line2 = '{0}   {1}  {2}  {3}\n'
        rain_line4 = '{0}   {1}\n'
        tsd_line = 'R {0:.3f}   {1:.3f}\n'
        cell_line = '{0: <10} {1}\n'

        rain_row = self.execute(rain_sql).fetchone()
        rain = os.path.join(outdir, 'RAIN.DAT')
        with open(rain, 'w') as r:
            fid = rain_row[0]
            r.write(rain_line1.format(*rain_row[1:3]))
            r.write(rain_line2.format(*rain_row[3:7]))
            for row in self.execute(ts_data_sql.format(fid)):
                r.write(tsd_line.format(*row))
            if rain_row[-1] is not None:
                r.write(rain_line4.format(*rain_row[-2:]))
            else:
                pass
            for row in self.execute(rain_cells_sql):
                r.write(cell_line.format(*row))

    def export_infil(self, outdir):
        pass

    def export_evapor(self, outdir):
        evapor_sql = '''SELECT ievapmonth, iday, clocktime FROM evapor;'''
        evapor_month_sql = '''SELECT month, monthly_evap FROM evapor_monthly ORDER BY fid;'''
        evapor_hour_sql = '''SELECT hourly_evap FROM evapor_hourly WHERE month = '{0}' ORDER BY fid;'''

        head = '{0}   {1}   {2:.2f}\n'
        monthly = '  {0}  {1:.2f}\n'
        hourly = '    {0:.4f}\n'

        month_rows = self.execute(evapor_month_sql)
        evapor = os.path.join(outdir, 'EVAPOR.DAT')
        with open(evapor, 'w') as e:
            e.write(head.format(*self.execute(evapor_sql).fetchone()))
            for mrow in month_rows:
                month = mrow[0]
                e.write(monthly.format(*mrow))
                for hrow in self.execute(evapor_hour_sql.format(month)):
                    e.write(hourly.format(*hrow))

    def export_chan(self, outdir):
        chan_sql = '''SELECT fid, depinitial, froudc, roughadj, isedn FROM chan ORDER BY fid;'''

        chan_r_sql = '''SELECT * FROM chan_r WHERE seg_fid = {0} ORDER BY nr_in_seg DESC;'''
        chan_v_sql = '''SELECT * FROM chan_v WHERE seg_fid = {0} ORDER BY nr_in_seg DESC;'''
        chan_t_sql = '''SELECT * FROM chan_t WHERE seg_fid = {0} ORDER BY nr_in_seg DESC;'''
        chan_n_sql = '''SELECT * FROM chan_n WHERE seg_fid = {0} ORDER BY nr_in_seg DESC;'''

        chan_wsel_sql = '''SELECT istart, wselstart, iend, wselend FROM chan_wsel ORDER BY fid;'''
        chan_conf_sql = '''SELECT chan_elem_fid FROM chan_confluences ORDER BY fid;'''
        chan_e_sql = '''SELECT chan_elem_fid FROM noexchange_chan_elems ORDER BY fid;'''

        segment = '   {0:.2f}   {1:.2f}   {2:.2f}   {3}\n'
        xsec = '{} '
        chanbank = ' {0: <10} {1}\n'
        wsel = '{0} {1:.2f}\n'
        conf = ' C {0}  {1}\n'
        chan_e = ' E {0}\n'

        chan = os.path.join(outdir, 'CHAN.DAT')
        bank = os.path.join(outdir, 'CHANBANK.DAT')

        with open(chan, 'w') as c, open(bank, 'w') as b:
            for row in self.execute(chan_sql):
                fid = row[0]
                c.write(segment.format(*row[1:]).replace('None', ''))
                chan_r_rows = self.execute(chan_r_sql.format(fid))
                chan_v_rows = self.execute(chan_v_sql.format(fid))
                chan_t_rows = self.execute(chan_t_sql.format(fid))
                chan_n_rows = self.execute(chan_n_sql.format(fid))
                cross_sections = chain(chan_r_rows, chan_v_rows, chan_t_rows, chan_n_rows)
                for xs in cross_sections:
                    row_len = len(xs)
                    xsslice = slice(3, -3)
                    if row_len == 12:
                        char = 'R'
                    elif row_len == 25:
                        char = 'V'
                    elif row_len == 15:
                        char = 'T'
                    else:
                        char = 'N'
                        xsslice = slice(3, -4)
                    params = [char] + list(xs[xsslice])
                    params = [x for x in params if x is not None]
                    form = xsec * len(params) + '\n'
                    c.write(form.format(*params))
                    b.write(chanbank.format(xs[3], xs[-3]))

            for row in self.execute(chan_wsel_sql):
                c.write(wsel.format(*row[:2]))
                c.write(wsel.format(*row[2:]))

            pairs = []
            for row in self.execute(chan_conf_sql):
                chan_elem = row[0]
                if not pairs:
                    pairs.append(chan_elem)
                else:
                    pairs.append(chan_elem)
                    c.write(conf.format(*pairs))
                    del pairs[:]

            for row in self.execute(chan_e_sql):
                c.write(chan_e.format(row[0]))

    def export_xsec(self, outdir):
        chan_n_sql = '''SELECT nxecnum, xsecname FROM chan_n ORDER BY nxecnum;'''
        xsec_sql = '''SELECT xi, yi FROM xsec_n_data WHERE chan_n_nxsecnum = {0} ORDER BY fid;'''

        xsec_line = '''X     {0}  {1}\n'''
        pkt_line = ''' {0:<10} {1: >10}\n'''
        nr = '{0:.2f}'

        xsec = os.path.join(outdir, 'XSEC.DAT')
        with open(xsec, 'w') as x:
            for nxecnum, xsecname in self.execute(chan_n_sql):
                x.write(xsec_line.format(nxecnum, xsecname))
                for xi, yi in self.execute(xsec_sql.format(nxecnum)):
                    x.write(pkt_line.format(nr.format(xi), nr.format(yi)))
