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
import os
import traceback
from user_communication import UserCommunication


def connection_required(method):
    """
    Checking for active connection object.
    """
    def wrapper(self):
        if not self.con:
            self.uc.bar_warn("Define a database connections first!")
            return
        else:
            return method(self)
    return wrapper


def spatialite_connect(*args, **kwargs):
    # copied from https://github.com/qgis/QGIS/blob/master/python/utils.py#L587
    try:
        from pyspatialite import dbapi2
    except ImportError:
        import sqlite3
        con = sqlite3.dbapi2.connect(*args, **kwargs)
        con.enable_load_extension(True)
        cur = con.cursor()
        libs = [
            # Spatialite >= 4.2 and Sqlite >= 3.7.17, should work on all platforms
            ("mod_spatialite", "sqlite3_modspatialite_init"),
            # Spatialite >= 4.2 and Sqlite < 3.7.17 (Travis)
            ("mod_spatialite.so", "sqlite3_modspatialite_init"),
            # Spatialite < 4.2 (linux)
            ("libspatialite.so", "sqlite3_extension_init")
        ]
        found = False
        for lib, entry_point in libs:
            try:
                cur.execute("select load_extension('{}', '{}')".format(lib, entry_point))
            except sqlite3.OperationalError:
                continue
            else:
                found = True
                break
        if not found:
            raise RuntimeError("Cannot find any suitable spatialite module")
        cur.close()
        con.enable_load_extension(False)
        return con
    return dbapi2.connect(*args, **kwargs)


def database_create(path):
    """Create geopackage with SpatiaLite functions"""
    try:
        if os.path.exists(path):
            os.remove(path)
        else:
            pass
    except Exception as e:
        print("Couldn't write on the existing GeoPackage file. Check if it is not opened by another process.")
        return False

    con = database_connect(path)
    plugin_dir = os.path.dirname(__file__)
    script = os.path.join(plugin_dir, 'db_structure.sql')
    qry = open(script, 'r').read()
    c = con.cursor()
    c.executescript(qry)
    con.commit()
    c.close()
    return con


def database_connect(path):
    """Connect database with sqlite3"""
    try:
        con = spatialite_connect(path)
        return con
    except Exception as e:
        print("Couldn't connect to GeoPackage")
        print(traceback.format_exc())
        return False


def database_disconnect(con):
    """Disconnect from database"""
    try:
        con.close()
    except Exception as e:
        print("There is no active connection!")
        print(traceback.format_exc())


class GeoPackageUtils(object):
    """GeoPackage utils for handling GPKG files"""
    def __init__(self, con, iface):
        self.iface = iface
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = con

    def execute(self, statement, inputs=None):
        """Execute a prepared SQL statement on this geopackage database."""
        cursor = self.con.cursor()
        if inputs is not None:
            result_cursor = cursor.execute(statement, inputs)
        else:
            result_cursor = cursor.execute(statement)
        self.con.commit()
        return result_cursor

    def execute_many(self, sql, data):
        cursor = self.con.cursor()
        if sql is not None:
            cursor.executemany(sql, data)
        else:
            return
        self.con.commit()

    def batch_execute(self, *sqls):
        for sql in sqls:
            qry = None
            if len(sql) <= 2:
                continue
            else:
                pass
            try:
                qry = sql.pop(0)
                row_len = sql.pop(0)
                qry_part = ' (' + ','.join(['?'] * row_len) + ')'
                qry_all = qry + qry_part
                cur = self.con.cursor()
                cur.executemany(qry_all, sql)
                self.con.commit()
                del sql[:]
                sql += [qry, row_len]
            except Exception as e:
                self.uc.log_info(qry)
                self.uc.log_info(traceback.format_exc())

    def check_gpkg(self):
        """Check if file is GeoPackage """
        try:
            c = self.con.cursor()
            c.execute('SELECT * FROM gpkg_contents;')
            c.fetchone()
            return True
        except Exception as e:
            return False

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

    def get_cont_par(self, name):
        """Get a parameter value from cont table"""
        try:
            sql = '''SELECT value FROM cont WHERE name = ?;'''
            r = self.execute(sql, (name,)).fetchone()[0]
            if r:
                return r
        except:
            return None

    def set_cont_par(self, name, value):
        """Set a parameter value in cont table"""
        try:
            sql = '''SELECT fid FROM cont WHERE name = ?;'''
            r = self.execute(sql, (name,)).fetchone()[0]
            if r:
                sql = '''UPDATE cont SET value = ? WHERE name = ?;'''
                self.execute(sql, (value, name,))
            else:
                sql = '''INSERT INTO cont (name, value) VALUES (?, ?);'''
                self.execute(sql, (name, value,))
            return True
        except:
            return None

    def get_gpkg_path(self):
        """Return database attached to the current connection"""
        try:
            sql = '''PRAGMA database_list;'''
            r = self.execute(sql).fetchone()[2]
            return r
        except:
            return None

    def get_views_list(self):
        qry = "SELECT name FROM sqlite_master WHERE type='view';"
        res = self.execute(qry).fetchall()
        return res

    def grid_centroids(self, gids, table='grid', field='fid', buffers=False):
        cells = {}
        if buffers is False:
            sql = '''SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = ?;'''
        else:
            sql = '''SELECT AsGPB(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = ?;'''
        for g in gids:
            geom = self.execute(sql.format(table, field), (g,)).fetchone()[0]
            cells[g] = geom
        return cells

    def single_centroid(self, gid, table='grid', field='fid'):
        sql = '''SELECT AsGPB(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = ?;'''
        gpb_buff = self.execute(sql.format(table, field), (gid,)).fetchone()[0]
        return gpb_buff

    def build_linestring(self, gids, table='grid', field='fid'):
        gpb = '''SELECT AsGPB(ST_GeomFromText('LINESTRING('''
        points = []
        for g in gids:
            qry = '''SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = ?;'''.format(table, field)
            wkt_geom = self.execute(qry, (g,)).fetchone()[0]
            points.append(wkt_geom.strip('POINT()'))
        gpb = gpb + ','.join(points) + ')\'))'
        gpb_buff = self.execute(gpb).fetchone()[0]
        return gpb_buff

    def build_multilinestring(self, gid, directions, cellsize, table='grid', field='fid'):
        functions = {
            '1': (lambda x, y, shift: (x, y + shift)),
            '2': (lambda x, y, shift: (x + shift, y)),
            '3': (lambda x, y, shift: (x, y - shift)),
            '4': (lambda x, y, shift: (x - shift, y)),
            '5': (lambda x, y, shift: (x + shift, y + shift)),
            '6': (lambda x, y, shift: (x + shift, y - shift)),
            '7': (lambda x, y, shift: (x - shift, y - shift)),
            '8': (lambda x, y, shift: (x - shift, y + shift))
        }
        gpb = '''SELECT AsGPB(ST_GeomFromText('MULTILINESTRING('''
        gpb_part = '''({0} {1}, {2} {3})'''
        qry = '''SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = ?;'''.format(table, field)
        wkt_geom = self.execute(qry, (gid,)).fetchone()[0]
        x1, y1 = [float(i) for i in wkt_geom.strip('POINT()').split()]
        half_cell = cellsize * 0.5
        parts = []
        for d in directions:
            x2, y2 = functions[d](x1, y1, half_cell)
            parts.append(gpb_part.format(x1, y1, x2, y2))
        gpb = gpb + ','.join(parts) + ')\'))'
        gpb_buff = self.execute(gpb).fetchone()[0]
        return gpb_buff

    def build_levee(self, gid, direction, cellsize, table='grid', field='fid'):
        functions = {
            '1': (lambda x, y, s: (x - s/2.414, y + s, x + s/2.414, y + s)),
            '2': (lambda x, y, s: (x + s, y + s/2.414, x + s, y - s/2.414)),
            '3': (lambda x, y, s: (x + s/2.414, y - s, x - s/2.414, y - s)),
            '4': (lambda x, y, s: (x - s, y - s/2.414, x - s, y + s/2.414)),
            '5': (lambda x, y, s: (x + s/2.414, y + s, x + s, y + s/2.414)),
            '6': (lambda x, y, s: (x + s, y - s/2.414, x + s/2.414, y - s)),
            '7': (lambda x, y, s: (x - s/2.414, y - s, x - s, y - s/2.414)),
            '8': (lambda x, y, s: (x - s, y + s/2.414, x - s/2.414, y + s))
        }
        qry = '''SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = ?;'''.format(table, field)
        wkt_geom = self.execute(qry, (gid,)).fetchone()[0]
        xc, yc = [float(i) for i in wkt_geom.strip('POINT()').split()]
        x1, y1, x2, y2 = functions[direction](xc, yc, cellsize*0.48)
        gpb = '''SELECT AsGPB(ST_GeomFromText('LINESTRING({0} {1}, {2} {3})'))'''.format(x1, y1, x2, y2)
        gpb_buff = self.execute(gpb).fetchone()[0]
        return gpb_buff

    def build_buffer(self, wkt_geom, distance, quadrantsegments=3):
        gpb = '''SELECT AsGPB(ST_Buffer(ST_GeomFromText('{0}'), {1}, {2}))'''
        gpb = gpb.format(wkt_geom, distance, quadrantsegments)
        gpb_buff = self.execute(gpb).fetchone()[0]
        return gpb_buff

    def build_square(self, wkt_geom, size):
        x, y = [float(x) for x in wkt_geom.strip('POINT()').split()]
        half_size = float(size) * 0.5
        gpb = '''SELECT AsGPB(ST_GeomFromText('POLYGON(({} {}, {} {}, {} {}, {} {}, {} {}))'))'''.format(
            x - half_size, y - half_size,
            x + half_size, y - half_size,
            x + half_size, y + half_size,
            x - half_size, y + half_size,
            x - half_size, y - half_size
        )
        gpb_buff = self.execute(gpb).fetchone()[0]
        return gpb_buff

    def get_max(self, table, field='fid'):
        sql = '''SELECT MAX("{0}") FROM "{1}";'''.format(field, table)
        max_val = self.execute(sql).fetchone()[0]
        max_val = 0 if max_val is None else max_val
        return max_val

    def table_info(self, table, only_columns=False):
        qry = 'PRAGMA table_info("{0}")'.format(table)
        info = self.execute(qry)
        if only_columns is True:
            info = (col[1] for col in info)
        else:
            pass
        return info
