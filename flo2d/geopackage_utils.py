# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os
import traceback
from collections import defaultdict
from functools import wraps

from PyQt5.QtWidgets import QProgressDialog, QApplication
from osgeo import ogr, gdal
from qgis._core import QgsMessageLog, QgsVectorLayer, QgsProject, QgsRasterLayer, QgsMapLayer
from qgis.core import QgsGeometry, QgsVectorFileWriter
from .user_communication import UserCommunication

import sqlite3

import processing

def connection_required(fn):
    """
    Checking for active connection object.
    """
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        if not self.con:
            self.uc.bar_warn("Define a database connection first!")             
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
            ("libspatialite.so", "sqlite3_extension_init"),
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
    script = os.path.join(plugin_dir, "db_structure.sql")
    with open(script, "r") as file:
        qry = file.read()
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


# Generate list of QgsPoints from input geometry ( can be point, line, or polygon )
def extractPoints(geom):
    multi_geom = QgsGeometry()
    temp_geom = []
    if geom.type() == 0:  # it's a point
        if geom.isMultipart():
            temp_geom = geom.asMultiPoint()
        else:
            temp_geom.append(geom.asPoint())
    elif geom.type() == 1:  # it's a line
        if geom.isMultipart():
            multi_geom = geom.asMultiPolyline()  # multi_geog is a multiline
            for i in multi_geom:  # i is a line
                temp_geom.extend(i)
        else:
            temp_geom = geom.asPolyline()
    elif geom.type() == 2:  # it's a polygon
        if geom.isMultipart():
            multi_geom = geom.asMultiPolygon()  # multi_geom is a multipolygon
            for i in multi_geom:  # i is a polygon
                for j in i:  # j is a line
                    temp_geom.extend(j)
        else:
            multi_geom = geom.asPolygon()  # multi_geom is a polygon
            for i in multi_geom:  # i is a line
                temp_geom.extend(i)
    # FIXME - if there is none of know geoms (point, line, polygon) show an warning message
    return temp_geom


class GeoPackageUtils(object):
    """
    GeoPackage utils for handling data inside GeoPackage.
    """

    _metadata = [
        ["PROJ_NAME", "Project Name"],
        ["CONTACT", "Contact Engineer Name"],
        ["EMAIL", "Email Address"],
        ["COMPANY", "Company Name"],
        ["PHONE", "Phone Number"],
        ["PLUGIN_V", "FLO-2D-Plugin Version"],
        ["QGIS_V", "QGIS Version"],
        ["FLO-2D_V", "FLO-2D Build Version"],
        ["CRS", "Coordinate Reference System"],
    ]

    _descriptions = [
        ["TIME_ACCEL", "Timestep Sensitivity"],
        ["DEPTOL", "Percent Change in Depth"],
        ["NOPRTC", "Detailed Channel Output Options"],
        ["MUD", "Mudflow Switch"],
        ["COURANTFP", "Courant Stability FP"],
        ["SWMM", "Storm Drain Switch"],
        ["GRAPTIM", "Graphical Update Interval"],
        ["AMANN", "Increment n Value at runtime"],
        ["IMULTC", "Multiple Channel Switch"],
        ["FROUDL", "Global Limiting Froude"],
        ["LGPLOT", "Graphic Mode"],
        ["MSTREET", "Street Switch"],
        ["NOPRTFP", "Detailed Floodplain Output Options"],
        ["IDEBRV", "Debris Switch"],
        ["build", "Executable Build"],
        ["ITIMTEP", "Time Series Selection Switch"],
        ["STARTIMTEP", "Start time for time series output"],
        ["ENDTIMTEP", "End time for time series output"],
        ["XCONC", "Global Sediment Concentration"],
        ["ICHANNEL", "Channel Switch"],
        ["TIMTEP", "Time Series Output Interval"],
        ["SHALLOWN", "Shallow n Value"],
        ["TOLGLOBAL", "Low flow exchange limit"],
        ["COURCHAR_T", "Stability Line 3 Character"],
        ["IFLOODWAY", "Floodway Analysis Switch"],
        ["METRIC", "Metric Switch"],
        ["SIMUL", "Simulation Time"],
        ["COURANTC", "Courant Stability C"],
        ["LEVEE", "Levee Switch"],
        ["IHYDRSTRUCT", "Hydraulic Structure Switch"],
        ["ISED", "Sediment Transport Switch"],
        ["DEPTHDUR", "Depth Duration"],
        ["XARF", "Global Area Reduction"],
        ["IARFBLOCKMOD", "Global ARF=1 revision"],
        ["IWRFS", "Building Switch"],
        ["IRAIN", "Rain Switch"],
        ["COURCHAR_C", "Stability Line 2 Character ID"],
        ["COURANTST", "Courant Stability St"],
        ["IBACKUP", "Backup Switch"],
        ["INFIL", "Infiltration Switch"],
        ["TOUT", "Output Data Interval"],
        ["ENCROACH", "Encroachment Analysis Depth"],
        ["IEVAP", "Evaporation Switch"],
        ["IMODFLOW", "Modflow Switch"],
        ["DEPRESSDEPTH", "Depress Depth"],
        ["CELLSIZE", "Cellsize"],
        ["MANNING", "Global n Value Adjustment"],
        ["IDEPLT", "Plot Hydrograph"],
        ["IHOURDAILY", "Basetime Switch Hourly / Daily"],
        ["NXPRT", "Detailed FP cross section output."],
        ["PROJ", "Projection"],
    ]

    PARAMETER_DESCRIPTION = defaultdict(str)
    for name, description in _descriptions:
        PARAMETER_DESCRIPTION[name] = description

    METADATA_DESCRIPTION = defaultdict(str)
    for name, metadata in _metadata:
        METADATA_DESCRIPTION[name] = metadata

    # Current geopackage tables -> add/modify/delete when gpkg is modified
    current_gpkg_tables = [
        'metadata', 'cont', 'trigger_control', 'grid', 'inflow', 'inflow_cells',
        'reservoirs', 'inflow_time_series', 'inflow_time_series_data', 'outflow_time_series',
        'outflow_time_series_data', 'rain_time_series', 'rain_time_series_data', 'outflow',
        'outflow_cells', 'qh_params', 'qh_params_data', 'qh_table', 'qh_table_data',
        'out_hydrographs', 'out_hydrographs_cells', 'rain', 'rain_arf_cells', 'chan',
        'chan_elems', 'rbank', 'chan_r', 'chan_v', 'chan_t', 'chan_n', 'chan_confluences',
        'user_noexchange_chan_areas', 'noexchange_chan_cells', 'chan_wsel', 'xsec_n_data',
        'evapor', 'evapor_monthly', 'evapor_hourly', 'infil', 'infil_chan_seg',
        'infil_cells_green', 'infil_cells_scs', 'infil_cells_horton', 'infil_chan_elems',
        'struct', 'user_struct', 'rat_curves', 'repl_rat_curves', 'rat_table',
        'culvert_equations', 'bridge_xs', 'storm_drains', 'bridge_variables',
        'street_general', 'streets', 'street_seg', 'street_elems', 'user_blocked_areas',
        'blocked_cells', 'mult', 'mult_cells', 'mult_areas', 'mult_lines',
        'simple_mult_lines', 'simple_mult_cells', 'levee_general', 'levee_data',
        'levee_failure', 'levee_fragility', 'fpxsec', 'fpxsec_cells', 'fpfroude',
        'fpfroude_cells', 'swmm_inflows', 'swmm_inflow_patterns',
        'swmm_time_series', 'swmm_time_series_data', 'swmm_tidal_curve',
        'swmm_tidal_curve_data', 'user_swmm_storage_units', 'user_swmm_conduits', 'user_swmm_pumps',
        'swmm_pumps_curve_data', 'user_swmm_orifices', 'user_swmm_weirs', 'swmmflo',
        'swmm_other_curves',
        'swmmflort', 'swmmflort_data', 'swmmflo_culvert', 'swmmoutf', 'swmm_export',
        'spatialshallow', 'spatialshallow_cells', 'gutter_globals', 'gutter_areas',
        'gutter_lines', 'gutter_cells', 'tailing_cells', 'tolspatial', 'tolspatial_cells',
        'wsurf', 'wstime', 'breach_global', 'breach', 'breach_cells',
        'breach_fragility_curves', 'mud', 'mud_areas', 'mud_cells', 'sed_group_areas',
        'sed_groups', 'sed_group_frac', 'sed_group_frac_data', 'sed_group_cells', 'sed',
        'sed_rigid_areas', 'sed_rigid_cells', 'sed_supply_areas', 'sed_supply_cells',
        'sed_supply_frac', 'sed_supply_frac_data', 'user_fpxsec', 'user_model_boundary',
        'user_1d_domain', 'user_left_bank', 'user_right_bank', 'user_xsections',
        'chan_elems_interp', 'user_chan_r', 'user_chan_v', 'user_chan_t', 'user_chan_n',
        'user_xsec_n_data', 'user_elevation_points', 'user_levee_lines', 'user_streets',
        'user_roughness', 'user_spatial_tolerance', 'user_spatial_froude',
        'user_spatial_shallow_n', 'user_elevation_polygons', 'user_bc_points',
        'user_bc_lines', 'user_bc_polygons', 'all_schem_bc', 'user_reservoirs',
        'user_infiltration', 'user_effective_impervious_area', 'raincell',
        'raincell_data', 'buildings_areas', 'buildings_stats', 'sd_fields', 'outrc', 'swmm_control',
        'user_tailings', 'user_tailing_reservoirs', 'tailing_reservoirs', 'tailing_cells', 'external_layers',
        'user_swmm_inlets_junctions', 'user_swmm_outlets'
    ]

    def __init__(self, con, iface):
        self.iface = iface
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = con

    def copy_from_other(self, other_gpkg):
        """
        Function to copy an old geopackage into the newest version
        """
        new_gpkg_conn = self.con
        new_gpkg_cur = new_gpkg_conn.cursor()
        other_gpkg_conn = sqlite3.connect(other_gpkg)
        other_gpkg_cur = other_gpkg_conn.cursor()

        tab_sql = """SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'gpkg_%' AND name NOT LIKE 'rtree_%';"""
        tabs = [row[0] for row in self.execute(tab_sql)]
        self.execute("ATTACH ? AS other;", (other_gpkg,))
        other_tab_sql = """SELECT name FROM other.sqlite_master WHERE type='table' AND name NOT LIKE 'gpkg_%' AND name NOT LIKE 'rtree_%';"""
        other_tabs = [row[0] for row in self.execute(other_tab_sql)]

        tables_in_both = set(tabs) & set(other_tabs)
        tables_only_in_db1 = set(tabs) - set(other_tabs)
        tables_only_in_other_gpkg = set(other_tabs) - set(tabs)

        self.clear_tables(*tabs)

        # Update old tables
        update_tables_sql = []
        is_not_vector = []
        is_not_raster = []
        for table in tables_only_in_other_gpkg:
            if table == "infil_areas_green":
                sql = """
                        INSERT INTO infil_cells_green (fid, grid_fid, hydc, soils, dtheta, abstrinf, rtimpf, soil_depth)
                        SELECT infil_cells_green.fid, infil_cells_green.grid_fid, infil_areas_green.hydc, infil_areas_green.soils,
                               infil_areas_green.dtheta, infil_areas_green.abstrinf, infil_areas_green.rtimpf, infil_areas_green.soil_depth
                        FROM other.infil_cells_green
                        JOIN other.infil_areas_green ON other.infil_cells_green.infil_area_fid = other.infil_areas_green.fid;
                      """
                update_tables_sql.append(sql)
            if table == "infil_areas_scs":
                sql = """
                        INSERT INTO infil_cells_scs (fid, grid_fid, scsn)
                        SELECT infil_cells_scs.fid, infil_cells_scs.grid_fid, infil_areas_scs.scsn
                        FROM other.infil_cells_scs
                        JOIN other.infil_areas_scs ON other.infil_cells_scs.infil_area_fid = other.infil_areas_scs.fid;
                      """
                update_tables_sql.append(sql)
            if table == "infil_areas_horton":
                sql = """
                        INSERT INTO infil_cells_horton (fid, grid_fid, fhorti, fhortf, deca)
                        SELECT infil_cells_horton.fid, infil_cells_horton.grid_fid, infil_areas_horton.fhorti, 
                            infil_areas_horton.fhortf, infil_areas_horton.deca
                        FROM other.infil_cells_horton
                        JOIN other.infil_areas_horton ON other.infil_cells_horton.infil_area_fid = other.infil_areas_horton.fid;
                      """
                update_tables_sql.append(sql)
            if table == "infil_areas_chan":
                sql = """
                        INSERT INTO infil_chan_elems (fid, grid_fid, hydconch)
                        SELECT infil_chan_elems.fid, infil_chan_elems.grid_fid, infil_areas_chan.hydconch
                        FROM other.infil_chan_elems
                        JOIN other.infil_areas_chan ON other.infil_chan_elems.infil_area_fid = other.infil_areas_chan.fid;
                      """
                update_tables_sql.append(sql)

            if table == 'user_swmm_nodes':

                # add data to the user_swmm_inlets_junctions
                columns = self.execute(f"PRAGMA table_info('user_swmm_nodes');").fetchall()
                column_exists = any(column[1] == 'drboxarea' for column in columns)
                if column_exists:
                    sql = """
                            INSERT INTO user_swmm_inlets_junctions (
                                fid,
                                grid,
                                name,
                                sd_type,
                                external_inflow,
                                junction_invert_elev,
                                max_depth,
                                init_depth,
                                surcharge_depth,
                                intype,
                                swmm_length,
                                swmm_width,
                                swmm_height,
                                swmm_coeff,
                                swmm_feature,
                                curbheight,
                                swmm_clogging_factor,
                                swmm_time_for_clogging,
                                drboxarea,
                                geom
                            )
                            SELECT
                                user_swmm_nodes.fid,
                                user_swmm_nodes.grid,
                                user_swmm_nodes.name,
                                user_swmm_nodes.sd_type,
                                user_swmm_nodes.external_inflow,
                                user_swmm_nodes.junction_invert_elev,
                                user_swmm_nodes.max_depth,
                                user_swmm_nodes.init_depth,
                                user_swmm_nodes.surcharge_depth,
                                user_swmm_nodes.intype,
                                user_swmm_nodes.swmm_length,
                                user_swmm_nodes.swmm_width,
                                user_swmm_nodes.swmm_height,
                                user_swmm_nodes.swmm_coeff,
                                user_swmm_nodes.swmm_feature,
                                user_swmm_nodes.curbheight,
                                user_swmm_nodes.swmm_clogging_factor,
                                user_swmm_nodes.swmm_time_for_clogging,
                                user_swmm_nodes.drboxarea,
                                user_swmm_nodes.geom
                            FROM user_swmm_nodes WHERE user_swmm_nodes.sd_type <> 'O'
                          """
                    update_tables_sql.append(sql)
                else:
                    sql = """
                            INSERT INTO user_swmm_inlets_junctions (
                                fid,
                                grid,
                                name,
                                sd_type,
                                external_inflow,
                                junction_invert_elev,
                                max_depth,
                                init_depth,
                                surcharge_depth,
                                intype,
                                swmm_length,
                                swmm_width,
                                swmm_height,
                                swmm_coeff,
                                swmm_feature,
                                curbheight,
                                swmm_clogging_factor,
                                swmm_time_for_clogging,
                                geom
                            )
                            SELECT
                                user_swmm_nodes.fid,
                                user_swmm_nodes.grid,
                                user_swmm_nodes.name,
                                user_swmm_nodes.sd_type,
                                user_swmm_nodes.external_inflow,
                                user_swmm_nodes.junction_invert_elev,
                                user_swmm_nodes.max_depth,
                                user_swmm_nodes.init_depth,
                                user_swmm_nodes.surcharge_depth,
                                user_swmm_nodes.intype,
                                user_swmm_nodes.swmm_length,
                                user_swmm_nodes.swmm_width,
                                user_swmm_nodes.swmm_height,
                                user_swmm_nodes.swmm_coeff,
                                user_swmm_nodes.swmm_feature,
                                user_swmm_nodes.curbheight,
                                user_swmm_nodes.swmm_clogging_factor,
                                user_swmm_nodes.swmm_time_for_clogging,
                                user_swmm_nodes.geom
                            FROM user_swmm_nodes WHERE user_swmm_nodes.sd_type <> 'O'
                          """
                    update_tables_sql.append(sql)

                # add data to the user_swmm_outlets
                sql = """
                        INSERT INTO user_swmm_outlets (
                            grid,
                            name,
                            outfall_invert_elev,
                            flapgate, 
                            swmm_allow_discharge,
                            outfall_type,
                            tidal_curve,
                            time_series,  
                            geom
                        )
                        SELECT
                            user_swmm_nodes.grid,
                            user_swmm_nodes.name,
                            user_swmm_nodes.outfall_invert_elev,
                            user_swmm_nodes.flapgate, 
                            user_swmm_nodes.swmm_allow_discharge,
                            user_swmm_nodes.outfall_type,
                            user_swmm_nodes.tidal_curve,
                            user_swmm_nodes.time_series,  
                            user_swmm_nodes.geom
                        FROM user_swmm_nodes WHERE user_swmm_nodes.sd_type = 'O'
                      """
                update_tables_sql.append(sql)

            if table == 'sqlite_sequence' or table == 'qgis_projects' or table == 'rain_arf_areas' or table == 'user_swmm_nodes':
                continue

            # check if it is a vector layer
            try:
                ds = ogr.Open(other_gpkg)
                layer = ds.GetLayerByName(table)
                # Vector
                if layer.GetGeomType() != ogr.wkbNone:
                    source_layer = QgsVectorLayer(other_gpkg + "|layername=" + table, table, "ogr")
                    options = QgsVectorFileWriter.SaveVectorOptions()
                    options.driverName = "GPKG"
                    options.includeZ = True
                    options.overrideGeometryType = source_layer.wkbType()
                    options.layerName = source_layer.name()
                    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
                    QgsVectorFileWriter.writeAsVectorFormatV3(
                        source_layer,
                        self.get_gpkg_path(),
                        QgsProject.instance().transformContext(),
                        options)
                    is_not_vector.append(table)
                    continue
            except Exception as e:
                pass

            try:
                raster_ds = gdal.Open(f"GPKG:{other_gpkg}:{table}", gdal.OF_READONLY)
                if raster_ds:
                    source_layer = QgsRasterLayer(f"GPKG:{other_gpkg}:" + table, table, "gdal")
                    layer_name = source_layer.name().replace(" ", "_")
                    params = {'INPUT': f'{source_layer.dataProvider().dataSourceUri()}',
                              'TARGET_CRS': None,
                              'NODATA': None,
                              'COPY_SUBDATASETS': False,
                              'OPTIONS': '',
                              'EXTRA': f'-co APPEND_SUBDATASET=YES -co RASTER_TABLE={layer_name} -ot Float32',
                              'DATA_TYPE': 0,
                              'OUTPUT': f'{self.get_gpkg_path()}'}

                    processing.run("gdal:translate", params)
                    is_not_raster.append(table)

            except Exception as e:
                pass

            if table in is_not_raster and table in is_not_vector:
                self.uc.log_info("Error while porting {table} to the new Geopackage! Please, add it manually.")
                self.uc.bar_error("Error while porting {table} to the new Geopackage! Please, add it manually.")

        if len(update_tables_sql) != 0:
            for sql in update_tables_sql:
                try:
                    self.execute(sql)
                except Exception as e:
                    self.uc.log_info(traceback.format_exc())

        tables_manually_updated = ['infil_cells_green']

        pd = QProgressDialog("Updating tables...", None, 0, 157)
        pd.setWindowTitle("Update GeoPackage")
        pd.setModal(True)
        pd.forceShow()
        pd.setValue(0)
        i = 0

        for tab in tabs:
            if tab in tables_manually_updated:
                continue
            pd.setLabelText(f"Updating {tab}...")
            names_new = self.table_info(tab, only_columns=True)
            names_old = set(self.table_info(tab, only_columns=True, attached_db="other"))
            import_names = (name for name in names_new if name in names_old)
            columns = ", ".join(import_names)
            try:
                # If there are values on columns, the table exists. Otherwise, just create the table.
                if columns:
                    qry = f"""INSERT OR IGNORE INTO {tab} ({columns}) SELECT {columns} FROM other.{tab};"""
                    self.execute(qry)
            except Exception as e:
                self.uc.log_info(traceback.format_exc())
            i += 1
            QApplication.processEvents()
            pd.setValue(i)

        # Compare schema differences
        update_schema_sql = []
        for table in tables_in_both:
            new_gpkg_cur.execute(f"PRAGMA table_info({table})")
            columns_new_gpkg = set(column[1] for column in new_gpkg_cur.fetchall())

            other_gpkg_cur.execute(f"PRAGMA table_info({table})")
            columns_other_gpkg = set(column[1] for column in other_gpkg_cur.fetchall())

            # locate tables with different schemas
            if columns_new_gpkg != columns_other_gpkg:
                if table == "grid":
                    sql = f'''
                                    UPDATE grid
                                    SET col = ST_X(ST_Centroid(geom)),
                                        row = ST_Y(ST_Centroid(geom))
                               '''
                    update_schema_sql.append(sql)
                if table == "outflow_cells":
                    sql = f'''
                                    UPDATE outflow_cells
                                    SET geom_type = CASE 
                                        WHEN EXISTS (SELECT 1 FROM user_bc_points WHERE user_bc_points.fid = outflow_cells.outflow_fid) THEN 'point'
                                        WHEN EXISTS (SELECT 1 FROM user_bc_lines WHERE user_bc_lines.fid = outflow_cells.outflow_fid) THEN 'line'
                                        WHEN EXISTS (SELECT 1 FROM user_bc_polygons WHERE user_bc_polygons.fid = outflow_cells.outflow_fid) THEN 'polygon'
                                        ELSE 'Unknown'
                                    END
                               '''
                    update_schema_sql.append(sql)
        if len(update_schema_sql) != 0:
            for sql in update_schema_sql:
                try:
                    self.execute(sql)
                except Exception as e:
                    self.uc.log_info(traceback.format_exc())

        self.execute("DETACH other;")

    def execute(self, statement, inputs=None, get_rowid=False):
        """
        Execute a prepared SQL statement on this geopackage database.
        """
        try:
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

        except Exception as e:
            self.con.rollback()
            raise

    def execute_many(self, sql, data):
        try:
            cursor = self.con.cursor()
            if sql is not None:
                cursor.executemany(sql, data)
            else:
                return
            self.con.commit()
        except Exception as e:
            self.con.rollback()
            raise

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
                qry_part = " (" + ",".join(["?"] * row_len) + ")"
                qry_all = qry + qry_part
                cur = self.con.cursor()
                cur.executemany(qry_all, sql)
                self.con.commit()
                del sql[:]
                sql += [qry, row_len]
            except Exception as e:
                self.con.rollback()
                self.uc.log_info(qry)
                self.uc.log_info(traceback.format_exc())

    def check_gpkg(self):
        """
        Check if file is GeoPackage.
        """
        try:
            c = self.con.cursor()
            c.execute("SELECT * FROM gpkg_contents;")
            c.fetchone()
            return True
        except Exception as e:
            return False

    def check_gpkg_version(self):
        """
        Check GeoPackage version.
        """
        try:
            c = self.con.cursor()
            # Check if all expected tables exist
            for table in self.current_gpkg_tables:
                c.execute(f"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='{table}';")
                table_exists = c.fetchone()[0]
                if not table_exists:
                    return False
            # If all checks pass, return True
            return True
        except Exception as e:
            return False

    def get_grid_crs(self):
        """
        Function to retrieve the grid crs
        """
        try:
            qry = f"""SELECT crs.organization, crs.srs_id
                       FROM gpkg_contents AS content
                       JOIN gpkg_spatial_ref_sys AS crs ON content.srs_id = crs.srs_id
                       WHERE content.table_name = 'grid';
                   """
            crs_data = self.execute(qry).fetchone()
            if crs_data:
                organization, srs_id = crs_data
                projectCrs = f"{organization}:{srs_id}"
                return projectCrs
        except Exception as e:
            return False

    def is_table_empty(self, table):
        r = self.execute("""SELECT rowid FROM {0};""".format(table))
        if r.fetchone():
            return False
        else:
            return True

    def clear_tables(self, *tables):
        for tab in tables:
            if not self.is_table_empty(tab):
                sql = """DELETE FROM "{0}";""".format(tab)
                self.execute(sql)
            else:
                pass

    def get_cont_par(self, name):
        """
        Get a parameter value from cont table.
        """
        try:
            sql = """SELECT value FROM cont WHERE name = ?;"""
            r = self.execute(sql, (name,)).fetchone()[0]
            if r:
                return r
        except Exception as e:
            return None

    def get_metadata_par(self, name):
        """
        Get a parameter value from metadata table.
        """
        try:
            sql = """SELECT value FROM metadata WHERE name = ?;"""
            r = self.execute(sql, (name,)).fetchone()[0]
            if r:
                return r
        except Exception as e:
            return None

    def set_metadata_par(self, name, value):
        """
        Set a parameter value in metadata table.
        """
        metadata = self.METADATA_DESCRIPTION[name]
        sql = """INSERT OR REPLACE INTO metadata (name, value, note) VALUES (?,?,?);"""
        self.execute(sql, (name, value, metadata))

    def set_cont_par(self, name, value):
        """
        Set a parameter value in cont table.
        """
        description = self.PARAMETER_DESCRIPTION[name]
        sql = """INSERT OR REPLACE INTO cont (name, value, note) VALUES (?,?,?);"""
        self.execute(sql, (name, value, description))

    def get_gpkg_path(self):
        """
        Return database attached to the current connection.
        """
        try:
            sql = """PRAGMA database_list;"""
            r = self.execute(sql).fetchone()[2]
            return r
        except Exception as e:
            return None

    def get_views_list(self):
        qry = "SELECT name FROM sqlite_master WHERE type='view';"
        res = self.execute(qry).fetchall()
        return res

    def wkt_to_gpb(self, wkt_geom):
        gpb = """SELECT AsGPB(ST_GeomFromText('{}'))""".format(wkt_geom)
        gpb_buff = self.execute(gpb).fetchone()[0]
        return gpb_buff

    def grid_geom(self, gid, table="grid", field="fid"):
        sql = """SELECT geom FROM "{0}" WHERE "{1}" = ?;"""
        geom = self.execute(sql.format(table, field), (gid,)).fetchone()[0]
        return geom

    def grid_centroids(self, gids, table="grid", field="fid", buffers=False):
        cells = {}
        if buffers is False:
            sql = """SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = ?;"""
        else:
            sql = """SELECT AsGPB(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = ?;"""
        for g in gids:
            geom = self.execute(sql.format(table, field), (g,)).fetchone()[0]
            cells[g] = geom
        return cells

    def grid_centroids_all(self, table="grid", buffers=False):
        cells = []
        if buffers is False:
            sql = """SELECT fid, ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM "{0}";"""
        else:
            sql = """SELECT fid, AsGPB(ST_Centroid(GeomFromGPB(geom))) FROM "{0}";"""

        for g in self.execute(sql.format(table)).fetchall():
            cells.append(
                (
                    g[0],
                    [float(item) for item in g[1].replace("POINT(", "").replace(")", "").split(" ")],
                )
            )
        return cells

    def single_centroid(self, gid, table="grid", field="fid", buffers=False):
        if buffers is False:
            sql = """SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = ?;"""
        else:
            sql = """SELECT AsGPB(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = ?;"""
        geom = self.execute(sql.format(table, field), (gid,)).fetchone()[0]
        return geom

    def build_linestring(self, gids, table="grid", field="fid"):
        gpb = """SELECT AsGPB(ST_GeomFromText('LINESTRING("""
        points = []
        for g in gids:
            qry = """SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = ?;""".format(
                table, field
            )
            wkt_geom = self.execute(qry, (g,)).fetchone()[0]
            points.append(wkt_geom.strip("POINT()"))
        gpb = gpb + ",".join(points) + ")'))"
        gpb_buff = self.execute(gpb).fetchone()[0]
        return gpb_buff

    def build_multilinestring(self, gid, directions, cellsize, table="grid", field="fid"):
        functions = {
            "1": (lambda x, y, shift: (x, y + shift)),
            "2": (lambda x, y, shift: (x + shift, y)),
            "3": (lambda x, y, shift: (x, y - shift)),
            "4": (lambda x, y, shift: (x - shift, y)),
            "5": (lambda x, y, shift: (x + shift, y + shift)),
            "6": (lambda x, y, shift: (x + shift, y - shift)),
            "7": (lambda x, y, shift: (x - shift, y - shift)),
            "8": (lambda x, y, shift: (x - shift, y + shift)),
        }
        gpb = """SELECT AsGPB(ST_GeomFromText('MULTILINESTRING("""
        gpb_part = """({0} {1}, {2} {3})"""
        qry = """SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = ?;""".format(table, field)
        wkt_geom = self.execute(qry, (gid,)).fetchone()[0]  # "wkt_geom" is POINT. Centroid of cell "gid"
        x1, y1 = [float(i) for i in wkt_geom.strip("POINT()").split()]  # Coordinates x1, y1 of centriod of cell "gid".
        half_cell = cellsize * 0.5
        parts = []
        for d in directions:
            x2, y2 = functions[d](
                x1, y1, half_cell
            )  # Coords x2,y2 of end point of subline,  half_cell apart from x1,y1, in direction.
            parts.append(gpb_part.format(x1, y1, x2, y2))
        gpb = gpb + ",".join(parts) + ")'))"
        gpb_buff = self.execute(gpb).fetchone()[0]
        return gpb_buff

    def build_levee(self, gid, direction, cellsize, table="grid", field="fid"):
        """
        Builds a single line in cell "gid" according to "direction" (1 to 8)
        """
        functions = {
            "1": (lambda x, y, s: (x - s / 2.414, y + s, x + s / 2.414, y + s)),
            "2": (lambda x, y, s: (x + s, y + s / 2.414, x + s, y - s / 2.414)),
            "3": (lambda x, y, s: (x + s / 2.414, y - s, x - s / 2.414, y - s)),
            "4": (lambda x, y, s: (x - s, y - s / 2.414, x - s, y + s / 2.414)),
            "5": (lambda x, y, s: (x + s / 2.414, y + s, x + s, y + s / 2.414)),
            "6": (lambda x, y, s: (x + s, y - s / 2.414, x + s / 2.414, y - s)),
            "7": (lambda x, y, s: (x - s / 2.414, y - s, x - s, y - s / 2.414)),
            "8": (lambda x, y, s: (x - s, y + s / 2.414, x - s / 2.414, y + s)),
        }

        qry = """SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM "{0}" WHERE "{1}" = ?;""".format(table, field)
        # "qry" ends up as '''SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM "grid" WHERE "fid" = ?;'''

        wkt_geom = self.execute(qry, (gid,)).fetchone()[0]  # Centriod POINT (x,y) of cell "gid".

        xc, yc = [float(i) for i in wkt_geom.strip("POINT()").split()]
        x1, y1, x2, y2 = functions[direction](
            xc, yc, cellsize * 0.45
        )  # Get 2 points of a line from "functions" dictionary.

        gpb = """SELECT AsGPB(ST_GeomFromText('LINESTRING({0} {1}, {2} {3})'))""".format(x1, y1, x2, y2)
        # "gpb" gets a value with actual points, e.g.
        # SELECT AsGPB(ST_GeomFromText('LINESTRING(366961.647995 1185707.0, 366981.532005 1185707.0)'))
        gpb_buff = self.execute(gpb).fetchone()[0]
        return gpb_buff

    def build_buffer(self, wkt_geom, distance, quadrantsegments=3):
        gpb = """SELECT AsGPB(ST_Buffer(ST_GeomFromText('{0}'), {1}, {2}))"""
        gpb = gpb.format(wkt_geom, distance, quadrantsegments)
        gpb_buff = self.execute(gpb).fetchone()[0]
        return gpb_buff

    def build_square_xy(self, x, y, size):
        half_size = size * 0.5
        gpb = """SELECT AsGPB(ST_GeomFromText('POLYGON(({} {}, {} {}, {} {}, {} {}, {} {}))'))""".format(
            x - half_size,
            y - half_size,
            x + half_size,
            y - half_size,
            x + half_size,
            y + half_size,
            x - half_size,
            y + half_size,
            x - half_size,
            y - half_size,
        )
        gpb_buff = self.execute(gpb).fetchone()[0]
        return gpb_buff

    def build_square(self, wkt_geom, size):
        x, y = [float(x) for x in wkt_geom.strip("POINT()").split()]
        half_size = float(size) * 0.5
        gpb = """SELECT AsGPB(ST_GeomFromText('POLYGON(({} {}, {} {}, {} {}, {} {}, {} {}))'))""".format(
            x - half_size,
            y - half_size,
            x + half_size,
            y - half_size,
            x + half_size,
            y + half_size,
            x - half_size,
            y + half_size,
            x - half_size,
            y - half_size,
        )
        gpb_buff = self.execute(gpb).fetchone()[0]
        return gpb_buff

    def build_square_from_polygon(self, polygon_coordinates):
        gpb = """SELECT AsGPB(ST_GeomFromText('POLYGON(({} {}, {} {}, {} {}, {} {}, {} {}))'))""".format(
            *polygon_coordinates
        )
        gpb_buff = self.execute(gpb).fetchone()[0]
        return gpb_buff

    def build_square_from_polygon2(self, polyColRow):
        gpb = """SELECT AsGPB(ST_GeomFromText('POLYGON(({} {}, {} {}, {} {}, {} {}, {} {}))'))""".format(*polyColRow[0])
        gpb_buff = self.execute(gpb).fetchone()[0]
        return (gpb_buff, polyColRow[1], polyColRow[2])

    def get_max(self, table, field="fid"):
        sql = """SELECT MAX("{0}") FROM "{1}";""".format(field, table)
        max_val = self.execute(sql).fetchone()[0]
        max_val = 0 if max_val is None else max_val
        return max_val

    def count(self, table, field="fid"):
        sql = """SELECT COUNT("{0}") FROM "{1}";""".format(field, table)
        count = self.execute(sql).fetchone()[0]
        count = 0 if count is None else count
        return count

    def table_info(self, table, only_columns=False, attached_db=None):
        if attached_db is None:
            qry = 'PRAGMA table_info("{0}")'.format(table)
        else:
            qry = 'PRAGMA {0}.table_info("{1}")'.format(attached_db, table)
        info = self.execute(qry)
        if only_columns is True:
            info = (col[1] for col in info)
        else:
            pass
        return info

    def delete_imported_reservoirs(self):
        qry = """SELECT fid FROM reservoirs WHERE user_res_fid IS NULL;"""
        imported = self.execute(qry).fetchall()
        if imported:
            if self.uc.question("There are imported reservoirs in the database. Delete them?"):
                qry = "DELETE FROM reservoirs WHERE user_res_fid IS NULL;"
                self.execute(qry)

    def update_layer_extents(self, table_name):
        sql = """UPDATE gpkg_contents SET
            min_x = (SELECT MIN(MbrMinX(GeomFromGPB(geom))) FROM "{0}"),
            min_y = (SELECT MIN(MbrMinY(GeomFromGPB(geom))) FROM "{0}"),
            max_x = (SELECT MAX(MbrMaxX(GeomFromGPB(geom))) FROM "{0}"),
            max_y = (SELECT MAX(MbrMaxY(GeomFromGPB(geom))) FROM "{0}")
            WHERE table_name='{0}';""".format(
            table_name
        )
        self.execute(sql)

    def delete_all_imported_inflows(self):
        qry = """SELECT fid FROM inflow WHERE geom_type IS NULL;"""
        imported = self.execute(qry).fetchall()
        if imported:
            if self.uc.question("There are imported inflows in the database. Delete them?"):
                qry = "DELETE FROM inflow WHERE geom_type IS NULL;"
                self.execute(qry)

    def delete_all_imported_outflows(self):
        qry = """SELECT fid FROM outflow WHERE geom_type IS NULL;"""
        imported = self.execute(qry).fetchall()
        if imported:
            if self.uc.question("There are imported outflows in the database. Delete them?"):
                qry = "DELETE FROM outflow WHERE geom_type IS NULL;"
                self.execute(qry)

    def delete_all_imported_bcs(self):
        self.delete_all_imported_inflows()
        self.delete_all_imported_outflows()

    def delete_all_imported_structs(self):
        qry = """SELECT fid FROM struct WHERE notes = 'imported';"""
        imported = self.execute(qry).fetchall()
        if imported:
            if self.uc.question(
                "There are imported structures in the database. If you proceed they will be deleted.\nProceed anyway?"
            ):
                qry = """DELETE FROM struct WHERE notes = 'imported';"""
                self.execute(qry)
            else:
                return False
        return True

    def copy_new_struct_from_user_lyr(self):
        qry = """INSERT OR IGNORE INTO struct (fid) SELECT fid FROM user_struct;"""
        self.execute(qry)

    def fill_empty_reservoir_names(self):
        qry = """UPDATE user_reservoirs SET name = 'Reservoir ' ||  cast(fid as text) WHERE name IS NULL;"""
        self.execute(qry)
        qry = """UPDATE user_reservoirs SET wsel = 0.0 WHERE wsel IS NULL;"""
        self.execute(qry)

    def fill_empty_tailings_names(self):
        qry = """UPDATE user_tailings SET name = 'Tailings ' ||  cast(fid as text) WHERE name IS NULL;"""
        self.execute(qry)
        qry = """UPDATE user_tailings SET tailings_surf_elev = 0.0 WHERE tailings_surf_elev IS NULL;"""
        self.execute(qry)

    def fill_empty_point_tailings_names(self):
        qry = """UPDATE user_tailing_reservoirs SET name = 'Tailings ' ||  cast(fid as text) WHERE name IS NULL;"""
        self.execute(qry)
        qry = """UPDATE user_tailing_reservoirs SET tailings = 0.0 WHERE tailings IS NULL;"""
        self.execute(qry)

    def fill_empty_inflow_names(self):
        qry = """UPDATE inflow SET name = 'Inflow ' ||  cast(fid as text) WHERE name IS NULL;"""
        self.execute(qry)

    def fill_empty_outflow_names(self):
        qry = """UPDATE outflow SET name = 'Outflow ' ||  cast(fid as text) WHERE name IS NULL;"""
        self.execute(qry)

    def fill_empty_user_xsec_names(self):
        qry = """UPDATE user_xsections SET name = 'Cross-section-' ||  cast(fid as text) WHERE name IS NULL;"""
        self.execute(qry)

    def fill_empty_struct_names(self):
        qry = """UPDATE struct SET structname = 'Structure_' ||  cast(fid as text) WHERE structname IS NULL;"""
        self.execute(qry)

    def fill_empty_mult_globals(self):
        self.clear_tables("mult")
        sql_mult_defaults = [
            """INSERT INTO mult (wmc, wdrall, dmall, nodchansall,
                                     xnmultall, sslopemin, sslopemax, avuld50, simple_n) VALUES""",
            9,
        ]
        if self.get_cont_par("METRIC") == "1":
            sql_mult_defaults += [(0.0, 1.0, 0.3, 1, 0.04, 0.0, 0.0, 0.0, 0.04)]
        else:
            sql_mult_defaults += [(0.0, 3.0, 1.0, 1, 0.04, 0.0, 0.0, 0.0, 0.04)]
        self.batch_execute(sql_mult_defaults)

    def set_def_n(self):
        def_n = self.get_cont_par("MANNING")
        if not def_n:
            def_n = 0.04
        qry = """UPDATE user_xsections SET fcn = ? WHERE fcn IS NULL;"""
        self.execute(qry, (def_n,))

    def get_inflow_names(self):
        qry = """SELECT name FROM inflow WHERE name IS NOT NULL;"""
        rows = self.execute(qry).fetchall()
        return [row[0] for row in rows]

    def get_outflow_names(self):
        qry = """SELECT name FROM outflow WHERE name IS NOT NULL;"""
        rows = self.execute(qry).fetchall()
        return [row[0] for row in rows]

    def get_inflows_list(self):
        qry = "SELECT fid, name, geom_type, time_series_fid FROM inflow ORDER BY LOWER(fid);"
        return self.execute(qry).fetchall()

    def get_outflows_list(self):
        qry = "SELECT fid, name, type, geom_type FROM outflow ORDER BY LOWER(fid);"
        return self.execute(qry).fetchall()

    def get_structs_list(self):
        qry = "SELECT fid, structname, type, notes FROM struct ORDER BY LOWER(structname);"
        return self.execute(qry).fetchall()

    def disable_geom_triggers(self):
        qry = "UPDATE trigger_control SET enabled = 0;"
        self.execute(qry)

    def enable_geom_triggers(self):
        qry = "UPDATE trigger_control SET enabled = 1;"
        self.execute(qry)

    def calculate_offset(self, cell_size):
        """
        Finding offset of grid squares centers which is formed after switching from float to integers.
        Rounding to integers is needed for Bresenham's Line Algorithm.
        """
        geom = self.single_centroid("1").strip("POINT()").split()
        x, y = float(geom[0]), float(geom[1])
        x_offset = round(x / cell_size) * cell_size - x
        y_offset = round(y / cell_size) * cell_size - y
        return x_offset, y_offset

    def grid_on_point(self, x, y):
        """
        Getting fid of grid which contains given point.
        """
        qry = """
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
        """
        qry = qry.format(x, y)
        data = self.execute(qry).fetchone()
        if data is not None:
            gid = data[0]
        else:
            gid = None
        return gid

    def grid_elevation_on_point(self, x, y):
        """
        Getting elevation of grid which contains given point.
        """
        qry = """
        SELECT g.elevation
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
        """
        qry = qry.format(x, y)
        data = self.execute(qry).fetchone()
        if data is not None:
            elev = data[0]
        else:
            elev = None
        return elev

    def grid_value(self, gid, field):
        qry = 'SELECT "{}" FROM grid WHERE fid=?;'.format(field)
        value = self.execute(qry, (gid,)).fetchone()[0]
        return value

    def create_xs_type_n_r_t_v_tables(self):
        """
        Creates parameters values specific for each cross section type.
        """
        self.clear_tables("chan_r", "chan_v", "chan_t", "chan_n")
        chan_r = """INSERT INTO chan_r (elem_fid) VALUES (?);"""
        chan_v = """INSERT INTO chan_v (elem_fid) VALUES (?);"""
        chan_t = """INSERT INTO chan_t (elem_fid) VALUES (?);"""
        chan_n = """INSERT INTO chan_n (elem_fid) VALUES (?);"""

        xs_sql = """SELECT fid, type FROM chan_elems;"""
        cross_sections = self.execute(xs_sql).fetchall()
        cur = self.con.cursor()
        for fid, typ in cross_sections:
            if typ == "R":
                cur.execute(chan_r, (fid,))
            elif typ == "V":
                cur.execute(chan_v, (fid,))
            elif typ == "T":
                cur.execute(chan_t, (fid,))
            elif typ == "N":
                cur.execute(chan_n, (fid,))
            else:
                pass
        self.con.commit()

    def create_schematized_rbank_lines_from_xs_tips(self):
        """
        Create right bank lines.
        """
        self.clear_tables("rbank")
        qry = """
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
        """
        self.execute(qry)
