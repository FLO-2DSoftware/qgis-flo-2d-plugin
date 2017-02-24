# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


import os
import traceback
from functools import wraps
from collections import defaultdict
from user_communication import UserCommunication


def connection_required(fn):
    """
    Checking for active connection object.
    """
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        if not self.con:
            self.uc.bar_warn("Define a database connections first!")
            return
        else:
            return fn(self, *args, **kwargs)
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
    """
    Create geopackage with SpatiaLite functions.
    """
    try:
        if os.path.exists(path):
            os.remove(path)
        else:
            pass
    except Exception as e:
        # Couldn't write on the existing GeoPackage file. Check if it is not opened by another process
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
    """
    Connect database with sqlite3.
    """
    try:
        con = spatialite_connect(path)
        return con
    except Exception as e:
        # Couldn't connect to GeoPackage
        return False


def database_disconnect(con):
    """
    Disconnect from database.
    """
    try:
        con.close()
    except Exception as e:
        # There is no active connection!
        pass


class GeoPackageUtils(object):
    """
    GeoPackage utils for handling data inside GeoPackage.
    """
    _descriptions = [
        ['AMANN',
         'Increments the floodplain Manning\'s n roughness coefficient at runtime. AMANN will uniformly increase or decrease the every floodplain grid element n-value (n-value + AMANN). Set AMANN to a negative value to decrease the n-value. Set AMANN= -99 to turn off depth integrated roughness. Set AMANN > 1.0 or <-1.0 to globally increase or decrease the n-value multiplicatively (n-value * AMANN).'],
        ['DEPRESSDEPTH',
         'DEPRESSDEPTH variable which replaces the ISUPER switch in CONT.DAT. A value of DEPRESSDEPTH = 3.0 ft is suggested. This depth will ignore minor small depression elements which can fill and overview.'],
        ['DEPTHDUR',
         'Flow depth (ft or m) for a depth-duration analysis. When a flow depth greater than DEPTHDUR is computed, the time duration of inundation for that grid element is tracked and reported in the DEPTHDUR.OUT file.'],
        ['ENCROACH',
         'The floodway encroachment increase in flow depth (ft or m). The IFLOODWAY switch must be set to 1 and a previous FLO-2D simulation must be completed for the project to generate the maximum water surface elevations.'],
        ['FROUDL',
         'Maximum Froude number for overland flow. When FROUDL is exceeded, the floodplain n-value is increased by 0.001 for that grid element for the next timestep. Set FROUDL = 0.0 for no Froude number limitations. The increased n-values are reported in the ROUGH.OUT and FPLAIN.RGH files.'],
        ['GRAPTIM',
         'Time interval in hours that the graphics display is updated (e.g. set GRAPTIM = 0.02 for a frequent update). GRAPHTIM is required when LGPLOT = 2. This variable will not affect the file output data time interval (TOUT). The graphics mode is limited to a 48-day inflow hydrograph.'],
        ['IBACKUP',
         'IBACKUP = 1 creates a backup file of all the data files with the *.BAC extension for data error troubleshooting. It also enables the model to be resumed following termination from the last output interval.\nIBACKUP = 2 enables elevation changes for outflow nodes made at runtime to be permanently written to the FPLAIN.RGH file.'],
        ['ICHANNEL',
         'If ICHANNEL = 1 channel component will be initiated. The CHAN.DAT must be created.'],
        ['IDEBRV', 'Set IDEBRV = 1 if a debris basin volume should be filled before routing the flow hydrograph.'],
        ['IEVAP', 'Set IEVAP = 1 if simulating free water surface evaporation from overland flow or channel flow.'],
        ['IFLOODWAY',
         'If FLOODWAY =1 a floodway analysis will be performed in the next FLO-2D simulation. An initial FLO-2D flood simulation must be completed prior to a floodway simulation.'],
        ['IHYDRSTRUCT',
         'Set IHYDRSTRUCT = 1 to simulate hydraulic structures either on the floodplain or in the channel. The HYSTRUC.DAT file must be created.'],
        ['IMULTC',
         'Set IMULTC = 1 to simulate multiple channel (rill and gully flow) rather than overland sheet flow between multiple channel elements. The MULT.DAT file must be created.'],
        ['IMODFLOW',
         'Set IMODFLOW = 1 to simulate surface-groundwater interaction. This switch initiate the MODFLOW groundwater model a during the FLO-2D simulation.'],
        ['INFIL',
         'INFIL = 1 initiates an infiltration subroutine using the Green-Ampt infiltration model for either channel or overland infiltration. The INFIL.DAT file must be created.'],
        ['IRAIN',
         'Set IRAIN = 1 to simulate rain on the grid system. The RAIN.DAT file must be created.'],
        ['ISED', 'If ISED = 1, the sediment transport routine will be used. The SED.DAT file must be created.'],
        ['ITIMTEP',
         '0 = No time series output is written at runtime.\n1 = TIMEDEP.OUT is written at runtime.\n2 = TIMEDEP.OUT and HDF5 files are written at runtime.\n3 = TIMEDEP.OUT and NETCDF4 files are written at runtime.\n4 = All time series output is written at runtime.\n5 = Extract a time series for specific cells. Requires TIMDEPCELL.DAT'],
        ['IWRFS',
         'IWRFS = 1 specifies that area and width reduction factors (ARFs and WRFs) will be assigned in the ARF.DAT file.'],
        ['LEVEE', 'Set LEVEE = 1 to simulate levees. The LEVEE.DAT file must be created.'],
        ['LGPLOT',
         'LGPLOT = 0 will display screen text scrolling the simulation time, minimum timestep and volume conservation.\nLGPLOT = 2 displays the graphical floodwave progression over the grid system (flow depth) and inflow hydrograph.'],
        ['METRIC', 'METRIC = 0 for English units and METRIC = 1 for the metric system of units.'],
        ['MSTREET',
         'MSTREET = 1 to initiate the street flow component. The STREET.DAT file must be created.'],
        ['MUD',
         'Set MUD = 0 for clear water and MUD = 1 for hyperconcentrated sediment flow. Setting MUD = 1 requires sediment concentration assignment to the inflow hydrograph. The sediment load (volume or concentration by volume) for either the floodplain hydrograph HP(I,J,3) or the channel hydrograph H(I,J,3) must be assigned to each inflow hydrograph pair. The SED.DAT file must be created.'],
        ['NOPRTC',
         'If NOPRTC = 0, all the BASE.OUT channel data is reported. . If NOPRTC = 1, the BASE.OUT channel outflow data is not reported.If NOPRTC = 2, none of the channel output data is reported.'],
        ['NOPRTFP',
         'If NOPRTFP = 0, all the BASE.OUT floodplain flow data is reported. If NOPRTFP = 1, the BASE.OUT floodplain outflow data is not reported. If NOPRTFP = 2, BASE.OUT is not written. This reduces the final print time for model output at the end of the simulaion.If NOPRTFP = 3, only floodplain outflow data is reported to the BASE.OUT file.'],
        ['SHALLOWN',
         'Flow roughness n-value for shallow overland flow (flow depth < 0.2 ft or 0.06 m). If SHALLOWN < 0.05, the model will default to SHALLOWN = 0.200.'],
        ['SIMUL', 'Simulation time (hours).'],
        ['SWMM', 'SWMM = 1 initiates the FLO-2D storm drain model.'],
        ['TIMTEP',
         'An output interval (hrs) that the flow depth, resolved velocity, x-velocity, y-velocity and water surface elevation datasets are reported to the TIMDEP.OUT file for a post-simulation flood animation TIMTEP should be a multiple of TOUT. The switch ITIMTEP = 1 is required.'],
        ['TOUT', 'Output interval (hrs) that hydraulic data is reported to the various output files *.OUT.'],
        ['XARF',
         'Global area reduction factor applied to all grid elements. This factor reduces the grid element surface area available for flood volume storage. XARF can be used to account irregular surface topography, dense vegetation or other features. Range: 0 < XARF < 1. A typical value for XARF might be 0.10 indicating that 10% of each grid element surface is not available for flood storage. The XARF value is overridden by the ARF variables specified for the individual grid elements in the ARF.DAT file. Assign XARF = 0 to flood the entire surface area of the grid elements.'],
        ['XCONC',
         'Volumetric concentration to bulk the inflow discharge hydrograph (channel or floodplain). For example, set XCONC = 0.20 for a concentration of 20% by volume. This will account for sediment bulking without initiating the hyperconcentrated sediment transport routine. If simulating clear water flooding, set XCONC = 0. Set MUD = 0, if XCONC is greater than zero.'],
        ['COURANTC',
         'Courant number for channels. Courant-Friedrich-Lewy numerical stability parameter that relates the floodwave movement to the discretized model in space and time.'],
        ['COURANTFP',
         'Courant number for floodplain. Courant number for floodplain. Numerical stability parameter that relates the floodwave movement to the discretized model in space and time.'],
        ['COURANTST',
         'Courant number for streets. Courant number for floodplain. Numerical stability parameter that relates the floodwave movement to the discretized model in space and time.'],
        ['COURCHAR', 'Character \'C\' that identifies Line 2 with the Courant stability parameter.'],
        ['DEPTOL',
         'Tolerance value for the percent change in the flow depth for a given timestep. When a given element DEPTOL is exceeded, the timestep will be reduced. If DEPTOL = 0, then the timestep is governed by the Courant numerical stability criteria. It is recommended that DEPTOL only be used for specific ponded flow conditions where the Courant number is ineffective.'],
        ['TIME_ACCEL',
         'Coefficent to increase the rate of incremental timestep change. Default value - 1. Higher value (+0.1) may result in a faster simulation time.'],
        ['TOLGLOBAL',
         'Surface detention. TOLGLOBAL is a minimum value of the flow depth for flood routing. A typical value is 0.10 ft. Use a small value for rainfall runoff (0.004 ft to 0.10 ft; 0.0012 m to 0.030m).'],
        ['WAVEMAX',
         'Obsolete stability parameter. Maximum value of the numerical stability coefficient for full dynamic wave flood routing. Default value for WAVEMAX = 0. Use Courant instead of this parameter.']
    ]

    PARAMETER_DESCRIPTION = defaultdict(str)
    for name, description in _descriptions:
        PARAMETER_DESCRIPTION[name] = description

    def __init__(self, con, iface):
        self.iface = iface
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = con

    def execute(self, statement, inputs=None, get_rowid=False):
        """
        Execute a prepared SQL statement on this geopackage database.
        """
        cursor = self.con.cursor()
        if inputs is not None:
            result_cursor = cursor.execute(statement, inputs)
        else:
            result_cursor = cursor.execute(statement)
        rowid = cursor.lastrowid
        self.con.commit()
        if get_rowid:
            return rowid
        else:
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
        """
        Check if file is GeoPackage.
        """
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
        """
        Get a parameter value from cont table.
        """
        try:
            sql = '''SELECT value FROM cont WHERE name = ?;'''
            r = self.execute(sql, (name,)).fetchone()[0]
            if r:
                return r
        except:
            return None

    def set_cont_par(self, name, value):
        """
        Set a parameter value in cont table.
        """
        description = self.PARAMETER_DESCRIPTION[name]
        sql = '''INSERT OR REPLACE INTO cont (name, value, note) VALUES (?,?,?);'''
        self.execute(sql, (name, value, description))

    def get_gpkg_path(self):
        """
        Return database attached to the current connection.
        """
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

    def single_centroid(self, gid, table='grid', field='fid', buffers=False):
        if buffers is False:
            sql = '''SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = ?;'''
        else:
            sql = '''SELECT AsGPB(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = ?;'''
        geom = self.execute(sql.format(table, field), (gid,)).fetchone()[0]
        return geom

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

    def count(self, table, field='fid'):
        sql = '''SELECT COUNT("{0}") FROM "{1}";'''.format(field, table)
        count = self.execute(sql).fetchone()[0]
        count = 0 if count is None else count
        return count

    def table_info(self, table, only_columns=False):
        qry = 'PRAGMA table_info("{0}")'.format(table)
        info = self.execute(qry)
        if only_columns is True:
            info = (col[1] for col in info)
        else:
            pass
        return info

    def delete_imported_reservoirs(self):
        qry = '''SELECT fid FROM reservoirs WHERE user_res_fid IS NULL;'''
        imported = self.execute(qry).fetchall()
        if imported:
            if self.uc.question('There are imported reservoirs in the database. Delete them?'):
                qry = 'DELETE FROM reservoirs WHERE user_res_fid IS NULL;'
                self.execute(qry)

    def update_layer_extents(self, table_name):
        sql = '''UPDATE gpkg_contents SET
            min_x = (SELECT MIN(MbrMinX(GeomFromGPB(geom))) FROM "{0}"),
            min_y = (SELECT MIN(MbrMinY(GeomFromGPB(geom))) FROM "{0}"),
            max_x = (SELECT MAX(MbrMaxX(GeomFromGPB(geom))) FROM "{0}"),
            max_y = (SELECT MAX(MbrMaxY(GeomFromGPB(geom))) FROM "{0}")
            WHERE table_name='{0}';'''.format(table_name)
        self.execute(sql)

    def delete_all_imported_inflows(self):
        qry = '''SELECT fid FROM inflow WHERE geom_type IS NULL;'''
        imported = self.execute(qry).fetchall()
        if imported:
            if self.uc.question('There are imported inflows in the database. Delete them?'):
                qry = 'DELETE FROM inflow WHERE geom_type IS NULL;'
                self.execute(qry)

    def delete_all_imported_outflows(self):
        qry = '''SELECT fid FROM outflow WHERE geom_type IS NULL;'''
        imported = self.execute(qry).fetchall()
        if imported:
            if self.uc.question('There are imported outflows in the database. Delete them?'):
                qry = 'DELETE FROM outflow WHERE geom_type IS NULL;'
                self.execute(qry)

    def delete_all_imported_bcs(self):
        self.delete_all_imported_inflows()
        self.delete_all_imported_outflows()

    def delete_all_imported_structs(self):
        qry = '''SELECT fid FROM struct WHERE notes = 'imported';'''
        imported = self.execute(qry).fetchall()
        if imported:
            if self.uc.question('There are imported structures in the database. If you proceed they will be deleted.\nProceed anyway?'):
                qry = '''DELETE FROM struct WHERE notes = 'imported';'''
                self.execute(qry)
            else:
                return False
        return True

    def copy_new_struct_from_user_lyr(self):
        qry = '''INSERT OR IGNORE INTO struct (fid) SELECT fid FROM user_struct;'''
        self.execute(qry)

    def fill_empty_reservoir_names(self):
        qry = '''UPDATE user_reservoirs SET name = 'Reservoir ' ||  cast(fid as text) WHERE name IS NULL;'''
        self.execute(qry)

    def fill_empty_inflow_names(self):
        qry = '''UPDATE inflow SET name = 'Inflow ' ||  cast(fid as text) WHERE name IS NULL;'''
        self.execute(qry)

    def fill_empty_outflow_names(self):
        qry = '''UPDATE outflow SET name = 'Outflow ' ||  cast(fid as text) WHERE name IS NULL;'''
        self.execute(qry)

    def fill_empty_user_xsec_names(self):
        qry = '''UPDATE user_xsections SET name = 'Cross-section ' ||  cast(fid as text) WHERE name IS NULL;'''
        self.execute(qry)

    def fill_empty_struct_names(self):
        qry = '''UPDATE struct SET structname = 'Structure_' ||  cast(fid as text) WHERE structname IS NULL;'''
        self.execute(qry)

    def set_def_n(self):
        def_n = self.get_cont_par('MANNING')
        if not def_n:
            def_n = 0.035
        qry = '''UPDATE user_xsections SET fcn = ? WHERE fcn IS NULL;'''
        self.execute(qry, (def_n,))

    def get_inflow_names(self):
        qry = '''SELECT name FROM inflow WHERE name IS NOT NULL;'''
        rows = self.execute(qry).fetchall()
        return [row[0] for row in rows]

    def get_outflow_names(self):
        qry = '''SELECT name FROM outflow WHERE name IS NOT NULL;'''
        rows = self.execute(qry).fetchall()
        return [row[0] for row in rows]

    def get_inflows_list(self):
        qry = 'SELECT fid, name, geom_type, time_series_fid FROM inflow ORDER BY LOWER(name);'
        return self.execute(qry).fetchall()

    def get_outflows_list(self):
        qry = 'SELECT fid, name, type, geom_type FROM outflow ORDER BY LOWER(name);'
        return self.execute(qry).fetchall()

    def get_structs_list(self):
        qry = 'SELECT fid, structname, type, notes FROM struct ORDER BY LOWER(structname);'
        return self.execute(qry).fetchall()

    def disable_geom_triggers(self):
        qry = 'UPDATE trigger_control set enabled = 0;'
        self.execute(qry)

    def enable_geom_triggers(self):
        qry = 'UPDATE trigger_control set enabled = 1;'
        self.execute(qry)

    def calculate_offset(self, cell_size):
        """
        Finding offset of grid squares centers which is formed after switching from float to integers.
        Rounding to integers is needed for Bresenham's Line Algorithm.
        """
        geom = self.single_centroid('1').strip('POINT()').split()
        x, y = float(geom[0]), float(geom[1])
        x_offset = round(x / cell_size) * cell_size - x
        y_offset = round(y / cell_size) * cell_size - y
        return x_offset, y_offset

    def grid_on_point(self, x, y):
        """
        Getting fid of grid which contains given point.
        """
        qry = '''
        SELECT g.fid
        FROM grid AS g
        WHERE g.ROWID IN (
            SELECT id FROM rtree_grid_geom
            WHERE
                {0} <= maxx AND
                {0} >= minx AND
                {1} <= maxy AND
                {1} >= miny)
        AND
            ST_Intersects(GeomFromGPB(g.geom), ST_GeomFromText('POINT({0} {1})'));
        '''
        qry = qry.format(x, y)
        gid = self.execute(qry).fetchone()[0]
        return gid

    def update_xs_type(self):
        """
        Updating parameters values specific for each cross section type.
        """
        self.clear_tables('chan_n', 'chan_r', 'chan_t', 'chan_v')
        chan_n = '''INSERT INTO chan_n (elem_fid) VALUES (?);'''
        chan_r = '''INSERT INTO chan_r (elem_fid) VALUES (?);'''
        chan_t = '''INSERT INTO chan_t (elem_fid) VALUES (?);'''
        chan_v = '''INSERT INTO chan_v (elem_fid) VALUES (?);'''
        xs_sql = '''SELECT fid, type FROM chan_elems;'''
        cross_sections = self.execute(xs_sql).fetchall()
        cur = self.con.cursor()
        for fid, typ in cross_sections:
            if typ == 'N':
                cur.execute(chan_n, (fid,))
            elif typ == 'R':
                cur.execute(chan_r, (fid,))
            elif typ == 'T':
                cur.execute(chan_t, (fid,))
            elif typ == 'V':
                cur.execute(chan_v, (fid,))
            else:
                pass
        self.con.commit()

    def update_rbank(self):
        """
        Create right bank lines.
        """
        self.clear_tables('rbank')
        qry = '''
        INSERT INTO rbank (chan_seg_fid, geom)
        SELECT c.fid, AsGPB(MakeLine(centroid(CastAutomagic(g.geom)))) as geom
        FROM
            chan as c,
            (SELECT * FROM  chan_elems ORDER BY seg_fid, nr_in_seg) as ce, -- sorting the chan elems post aggregation doesn't work so we need to sort the before
            grid as g
        WHERE
            c.fid = ce.seg_fid AND
            ce.seg_fid = c.fid AND
            g.fid = ce.rbankgrid
        GROUP BY c.fid;
        '''
        self.execute(qry)
