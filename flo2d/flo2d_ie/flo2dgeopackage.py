# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os
import shutil
import traceback
from collections import OrderedDict
from datetime import datetime
from itertools import chain, groupby
from operator import itemgetter

from qgis._core import QgsFeatureRequest, QgsGeometry
from qgis.core import QgsWkbTypes

from .rainfall_io import HDFProcessor

try:
    import h5py
except ImportError:
    pass
import numpy as np
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QMessageBox
from qgis.core import NULL
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QApplication, QProgressDialog

from ..flo2d_tools.grid_tools import grid_compas_neighbors, number_of_elements, cell_centroid
from ..geopackage_utils import GeoPackageUtils
from ..gui.dlg_settings import SettingsDialog
from ..layers import Layers
from ..utils import float_or_zero, get_BC_Border, get_flo2dpro_release_date
from .flo2d_parser import ParseDAT, ParseHDF5


def create_array(line_format, max_columns, array_type, *args):
    if len(args) == 1 and isinstance(args[0], tuple):
        values = line_format.format(*args[0]).split()
    else:
        values = line_format.format(*args).split()
    array = np.array(values[:max_columns] + [""] * (max_columns - len(values)), dtype=array_type)
    return array


def check_outflow_condition(variables):
    return all(val == 0 for val in variables)


class Flo2dGeoPackage(GeoPackageUtils):
    """
    Class for proper import and export FLO-2D data.
    """

    FORMAT_DAT = "DAT"
    FORMAT_HDF5 = "HDF5"

    def __init__(self, con, iface, parsed_format=FORMAT_DAT):
        super(Flo2dGeoPackage, self).__init__(con, iface)
        self.parsed_format = parsed_format
        self.parser = None
        self.cell_size = None
        self.buffer = None
        self.shrink = None
        self.chunksize = float("inf")
        self.gutils = GeoPackageUtils(con, iface)
        self.lyrs = Layers(iface)
        self.export_messages = ""

    def set_parser(self, fpath, get_cell_size=True):
        if self.parsed_format == self.FORMAT_DAT:
            self.parser = ParseDAT()
            self.parser.scan_project_dir(fpath)
            self.cell_size = int(round(self.parser.calculate_cellsize()))
        elif self.parsed_format == self.FORMAT_HDF5:
            self.parser = ParseHDF5()
            self.parser.hdf5_filepath = fpath
            self.cell_size = int(round(self.parser.calculate_cellsize()))
        else:
            raise NotImplementedError("Unsupported extension type.")
        if not get_cell_size:
            return True
        if self.cell_size == 0:
            self.uc.show_info(
                "ERROR 060319.1604: Cell size is 0 - something went wrong!\nDoes TOPO.DAT file exist or is empty?"
            )
            return False
        else:
            pass
        self.buffer = self.cell_size * 0.4
        self.shrink = self.cell_size * 0.95
        return True

    def import_cont_toler(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_cont_toler_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_cont_toler_hdf5()

    def import_cont_toler_dat(self):
        sql = ["""INSERT OR REPLACE INTO cont (name, value, note) VALUES""", 3]
        mann = self.get_cont_par("MANNING")
        if not mann:
            mann = "0.05"
        else:
            pass
        self.clear_tables("cont")
        cont = self.parser.parse_cont()
        if len(cont["ITIMTEP"]) > 1:
            cont["ITIMTEP"] = cont["ITIMTEP"][0]
        toler = self.parser.parse_toler()
        cont.update(toler)
        for option in cont:
            sql += [(option, cont[option], self.PARAMETER_DESCRIPTION[option])]
        sql += [("CELLSIZE", self.cell_size, self.PARAMETER_DESCRIPTION["CELLSIZE"])]
        sql += [("MANNING", mann, self.PARAMETER_DESCRIPTION["MANNING"])]
        self.batch_execute(sql)

    def import_cont_toler_hdf5(self):

        # Define variable names
        cont_variables = [
            "SIMUL", "TOUT", "LGPLOT", "METRIC", "IBACKUP", "ICHANNEL", "MSTREET", "LEVEE",
            "IWRFS", "IMULTC", "IRAIN", "INFIL", "IEVAP", "MUD", "ISED", "IMODFLOW", "SWMM",
            "IHYDRSTRUCT", "IFLOODWAY", "IDEBRV", "AMANN", "DEPTHDUR", "XCONC", "XARF",
            "FROUDL", "SHALLOWN", "ENCROACH", "NOPRTFP", "DEPRESSDEPTH", "NOPRTC", "ITIMTEP",
            "TIMTEP", "STARTIMTEP", "ENDTIMTEP", "GRAPTIM"
        ]

        tol_variables = [
            "TOLGLOBAL", "DEPTOL", "COURANTFP", "COURANTC", "COURANTST", "TIME_ACCEL"
        ]

        sql = ["""INSERT OR REPLACE INTO cont (name, value, note) VALUES""", 3]

        control_group = self.parser.read_groups("Input/Control Parameters")
        if control_group:
            control_group = control_group[0]

            cont_dataset = control_group.datasets["CONT"].data
            toler_dataset = control_group.datasets["TOLER"].data

            # Insert CONT variables
            for i, var in enumerate(cont_variables):
                value = cont_dataset[i] if i < len(cont_dataset) else -9999
                sql += [(var, value, self.PARAMETER_DESCRIPTION.get(var, ""))]

            # Insert TOLER variables
            for i, var in enumerate(tol_variables):
                value = toler_dataset[i] if i < len(toler_dataset) else -9999
                sql += [(var, value, self.PARAMETER_DESCRIPTION.get(var, ""))]

            mann = self.get_cont_par("MANNING")
            if not mann:
                mann = "0.05"
            else:
                pass
            sql += [("CELLSIZE", self.cell_size, self.PARAMETER_DESCRIPTION["CELLSIZE"])]
            sql += [("MANNING", mann, self.PARAMETER_DESCRIPTION["MANNING"])]

            self.batch_execute(sql)
        else:
            mann = self.get_cont_par("MANNING")
            if not mann:
                mann = "0.05"
            else:
                pass
            sql += [("CELLSIZE", self.cell_size, self.PARAMETER_DESCRIPTION["CELLSIZE"])]
            sql += [("MANNING", mann, self.PARAMETER_DESCRIPTION["MANNING"])]
            self.batch_execute(sql)
            dlg_settings = SettingsDialog(self.con, self.iface, self.lyrs, self.gutils)
            dlg_settings.set_default_controls(self.con)

    def import_mannings_n_topo(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_mannings_n_topo_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_mannings_n_topo_hdf5()

    def import_topo(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_topo_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            pass  # TODO implement this on the hdf5 project
            # return self.import_topo_dat_hdf5()

    def import_topo_dat(self):
        """
        Function to import only the TOPO.DAT file (single component)
        """
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:

            qry = "UPDATE grid SET elevation = ? WHERE fid = ?;"

            # Clear the elevation
            self.execute("UPDATE grid SET elevation = '-9999';")

            data = self.parser.parse_topo()
            fid = 1
            cell_elev = []
            for row in data:
                cell_elev.append((row[2], fid))
                fid += 1
            self.gutils.execute_many(qry, cell_elev)

            QApplication.restoreOverrideCursor()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 040521.1154: importing TOPO.DAT!.\n", e)

    def import_mannings_n(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_manning_n_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            pass  # TODO implement this on the hdf5 project
            # return self.import_topo_dat_hdf5()

    def import_manning_n_dat(self):
        """
        Function to import only the MANNINGS_N.DAT file (single component)
        """
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:

            qry = "UPDATE grid SET n_value = ? WHERE fid = ?;"

            # Clear the elevation
            self.execute("UPDATE grid SET n_value = '0.04';")

            data = self.parser.parse_mannings_n()
            cell_mannings_n = []
            for row in data:
                cell_mannings_n.append((row[1], row[0]))
            self.gutils.execute_many(qry, cell_mannings_n)

            QApplication.restoreOverrideCursor()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 040521.1154: importing MANNINGS_N.DAT!.\n", e)

    def import_mannings_n_topo_dat(self):
        try:
            sql = ["""INSERT INTO grid (fid, n_value, elevation, geom) VALUES""", 4]

            self.clear_tables("grid")
            data = self.parser.parse_mannings_n_topo()

            c = 0
            man = slice(0, 2)
            coords = slice(2, 4)
            elev = slice(4, None)
            for row in data:
                if c < self.chunksize:
                    geom = " ".join(row[coords])
                    g = self.build_square(geom, self.cell_size)
                    sql += [tuple(row[man] + row[elev] + [g])]
                    c += 1
                else:
                    self.batch_execute(sql)
                    c = 0
            if len(sql) > 2:
                self.batch_execute(sql)
            else:
                pass

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 040521.1154: importing TOPO.DAT!.\n", e)

    def import_mannings_n_topo_hdf5(self):
        try:
            sql = ["""INSERT INTO grid (fid, n_value, elevation, geom) VALUES""", 4]

            self.clear_tables("grid")
            grid_group = self.parser.read_groups("Input/Grid")[0]

            c = 0
            grid_code_list = grid_group.datasets["GRIDCODE"].data
            manning_list = grid_group.datasets["MANNING"].data
            elevation_list = grid_group.datasets["ELEVATION"].data
            x_list = grid_group.datasets["COORDINATES"].data[:, 0]
            y_list = grid_group.datasets["COORDINATES"].data[:, 1]
            for grid_code, manning, z, x, y in zip(grid_code_list, manning_list, elevation_list, x_list, y_list):
                if c < self.chunksize:
                    g = self.build_square_xy(x, y, self.cell_size)
                    row_value = (
                        str(grid_code),
                        str(manning),
                        str(z),
                        g,
                    )
                    sql.append(row_value)
                    c += 1
                else:
                    self.batch_execute(sql)
                    c = 0
            if len(sql) > 2:
                self.batch_execute(sql)
            else:
                pass

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 040521.1154: importing Grid data from HDF5 file!\n", e)

    def import_inflow(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_inflow_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_inflow_hdf5()

    def import_inflow_dat(self):
        cont_sql = ["""INSERT INTO cont (name, value, note) VALUES""", 3]
        inflow_sql = [
            """INSERT INTO inflow (time_series_fid, ident, inoutfc, bc_fid) VALUES""",
            4,
        ]
        cells_sql = ["""INSERT INTO inflow_cells (inflow_fid, grid_fid) VALUES""", 2]
        ts_sql = ["""INSERT INTO inflow_time_series (fid, name) VALUES""", 2]
        tsd_sql = [
            """INSERT INTO inflow_time_series_data (series_fid, time, value, value2) VALUES""",
            4,
        ]

        # Reservoirs
        schematic_reservoirs_sql = [
            """INSERT INTO reservoirs (grid_fid, wsel, n_value, geom) VALUES""",
            4,
        ]
        user_reservoirs_sql = [
            """INSERT INTO user_reservoirs (wsel, n_value, geom) VALUES""",
            3,
        ]

        # Tailings Reservoirs
        schematic_tailings_reservoirs_sql = [
            """INSERT INTO tailing_reservoirs (grid_fid, wsel, n_value, tailings, geom) VALUES""",
            5,
        ]
        user_tailing_reservoirs = [
            """INSERT INTO user_tailing_reservoirs (wsel, n_value, tailings, geom) VALUES""",
            4,
        ]

        try:
            self.clear_tables(
                "inflow",
                "inflow_cells",
                "reservoirs",
                "tailing_reservoirs",
                "user_reservoirs",
                "user_tailing_reservoirs",
                "inflow_time_series",
                "inflow_time_series_data",
            )
            head, inf, res = self.parser.parse_inflow()
            if not head == None:
                cont_sql += [
                    ("IDEPLT", head["IDEPLT"], self.PARAMETER_DESCRIPTION["IDEPLT"]),
                    (
                        "IHOURDAILY",
                        head["IHOURDAILY"],
                        self.PARAMETER_DESCRIPTION["IHOURDAILY"],
                    ),
                ]

                for i, gid in enumerate(inf, 1):
                    row = inf[gid]["row"]
                    inflow_sql += [(i, row[0], row[1], i)]
                    cells_sql += [(i, gid)]
                    if inf[gid]["time_series"]:
                        ts_sql += [(i, "Time series " + str(i))]
                        for n in inf[gid]["time_series"]:
                            tsd_sql += [(i,) + tuple(n[1:])]

                self.batch_execute(cont_sql, ts_sql, inflow_sql, cells_sql, tsd_sql)
                qry = """UPDATE inflow SET name = 'Inflow ' ||  cast(fid as text);"""
                self.execute(qry)

            gids = list(res.keys())
            cells = self.grid_centroids(gids)
            for gid in res:
                row = res[gid]["row"]
                square = self.build_square(cells[gid], self.shrink)
                centroid = self.single_centroid(gid, buffers=True)
                # one-phase simulation
                if len(row) == 4:
                    grid = row[1]
                    wsel = row[2]
                    n_value = row[3]
                    user_value = (wsel, n_value)
                    schema_value = (grid, wsel, n_value)
                    schematic_reservoirs_sql += [(*schema_value, square)]
                    user_reservoirs_sql += [(*user_value, centroid)]
                # two-phase simulation
                if len(row) == 5:
                    grid = row[1]
                    wsel = row[2]
                    tail = row[3]
                    n_value = row[4]
                    user_value = (wsel, n_value, tail)
                    schema_value = (grid, wsel, n_value, tail)
                    schematic_tailings_reservoirs_sql += [(*schema_value, square)]
                    user_tailing_reservoirs += [(*user_value, centroid)]

            if user_reservoirs_sql and schematic_reservoirs_sql:
                self.batch_execute(user_reservoirs_sql)
                self.batch_execute(schematic_reservoirs_sql)
                qry = """UPDATE user_reservoirs SET name = 'Reservoir ' ||  cast(fid as text);"""
                self.execute(qry)
                qry = """UPDATE reservoirs SET user_res_fid = fid, name = 'Reservoir ' ||  cast(fid as text);"""
                self.execute(qry)
            if user_tailing_reservoirs and schematic_tailings_reservoirs_sql:
                self.batch_execute(user_tailing_reservoirs)
                self.batch_execute(schematic_tailings_reservoirs_sql)
                qry = """UPDATE user_tailing_reservoirs SET name = 'Tal Reservoir ' ||  cast(fid as text);"""
                self.execute(qry)
                qry = """UPDATE tailing_reservoirs SET user_tal_res_fid = fid, name = 'Tal Reservoir ' ||  cast(fid as text);"""
                self.execute(qry)

        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error("ERROR 070719.1051: Import inflows failed!.", e)

    def import_inflow_hdf5(self):
        try:

            inflow_group = self.parser.read_groups("Input/Boundary Conditions/Inflow")
            if inflow_group:
                inflow_group = inflow_group[0]

                self.clear_tables(
                    "inflow",
                    "inflow_cells",
                    "reservoirs",
                    "tailing_reservoirs",
                    "user_reservoirs",
                    "user_tailing_reservoirs",
                    "inflow_time_series",
                    "inflow_time_series_data",
                )

                inflow_sql = ["""INSERT INTO inflow (time_series_fid, ident, inoutfc, geom_type, bc_fid) VALUES""", 5]
                cells_sql = ["""INSERT INTO inflow_cells (inflow_fid, grid_fid) VALUES""", 2]
                ts_sql = ["""INSERT OR REPLACE INTO inflow_time_series (fid, name) VALUES""", 2]
                tsd_sql = ["""INSERT INTO inflow_time_series_data (series_fid, time, value, value2) VALUES""", 4,]

                # Reservoirs
                schematic_reservoirs_sql = ["""INSERT INTO reservoirs (grid_fid, wsel, n_value, geom) VALUES""", 4]
                user_reservoirs_sql = ["""INSERT INTO user_reservoirs (wsel, n_value, geom) VALUES""", 3]

                # Tailings Reservoirs
                schematic_tailings_reservoirs_sql = ["""INSERT INTO tailing_reservoirs (grid_fid, wsel, n_value, tailings, geom) VALUES""", 5]
                user_tailing_reservoirs = ["""INSERT INTO user_tailing_reservoirs (wsel, n_value, tailings, geom) VALUES""", 4]

                # Import inflow global parameters if present
                if "INF_GLOBAL" in inflow_group.datasets:
                    inflow_global = inflow_group.datasets["INF_GLOBAL"].data
                    self.execute("INSERT INTO cont (name, value, note) VALUES (?, ?, ?)", ("IHOURDAILY", int(inflow_global[0]), GeoPackageUtils.PARAMETER_DESCRIPTION["IHOURDAILY"]))
                    self.execute("INSERT INTO cont (name, value, note) VALUES (?, ?, ?)", ("IDEPLT", int(inflow_global[1]), GeoPackageUtils.PARAMETER_DESCRIPTION["IDEPLT"]))

                # Import inflow time series
                if "INF_GRID" in inflow_group.datasets:
                    for i, inflow_grid in enumerate(inflow_group.datasets["INF_GRID"].data, start=1):
                        ifc, inoutfc, khiin, ts_id = inflow_grid
                        if ifc == 0:
                            ident = 'F'
                        else:
                            ident = 'C'
                        inflow_sql += [(int(ts_id), ident, int(inoutfc), 'point', i)]
                        cells_sql += [(i, int(khiin))]
                        ts_sql += [(int(ts_id), "Time series " + str(ts_id))]

                # Import inflow time series data
                if "TS_INF_DATA" in inflow_group.datasets:
                    for tsd in inflow_group.datasets["TS_INF_DATA"].data:
                        ts_id, hpj1, hpj2, hpj3 = tsd
                        if hpj3 == -9999:
                            tsd_sql += [(ts_id, hpj1, hpj2, None)]
                        else:
                            tsd_sql += [(ts_id, hpj1, hpj2, hpj3)]

                # Import reservoir
                if "RESERVOIRS" in inflow_group.datasets:
                    grid_group = self.parser.read_groups("Input/Grid")[0]
                    x_list = grid_group.datasets["COORDINATES"].data[:, 0]
                    y_list = grid_group.datasets["COORDINATES"].data[:, 1]
                    for reservoir in inflow_group.datasets["RESERVOIRS"].data:
                        grid_fid, wsel, n_value, tailings = reservoir
                        user_geom = self.build_point_xy(x_list[int(grid_fid) - 1], y_list[int(grid_fid) - 1])
                        schema_geom = self.build_square_xy(x_list[int(grid_fid) - 1], y_list[int(grid_fid) - 1], self.cell_size)
                        # Water
                        if int(tailings) == -9999:
                            schematic_reservoirs_sql += [(grid_fid, wsel, n_value, schema_geom)]
                            user_reservoirs_sql += [(wsel, n_value, user_geom)]
                        # Tailings
                        else:
                            schematic_tailings_reservoirs_sql += [(grid_fid, wsel, n_value, tailings, schema_geom)]
                            user_tailing_reservoirs += [(wsel, n_value, tailings, user_geom)]

                if inflow_sql:
                    self.batch_execute(inflow_sql)

                if cells_sql:
                    self.batch_execute(cells_sql)

                if ts_sql:
                    self.batch_execute(ts_sql)

                if tsd_sql:
                    self.batch_execute(tsd_sql)

                if schematic_reservoirs_sql:
                    self.batch_execute(schematic_reservoirs_sql)

                if user_reservoirs_sql:
                    self.batch_execute(user_reservoirs_sql)

                if schematic_tailings_reservoirs_sql:
                    self.batch_execute(schematic_tailings_reservoirs_sql)

                if user_tailing_reservoirs:
                    self.batch_execute(user_tailing_reservoirs)

                return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR: importing INFLOW from HDF5 failed!\n", e)
            self.uc.log_info("ERROR: importing INFLOW from HDF5 failed!")
            return False

    def import_outrc(self):
        """
        Function to import the OUTRC.DAT file into the project
        """
        outrc_sql = [
            """INSERT INTO outrc (grid_fid, depthrt, volrt) VALUES""",
            3,
        ]

        self.clear_tables("outrc")

        # OUTRC.DAT
        data = self.parser.parse_outrc()
        if data:
            for row in data:
                if len(row) == 2:
                    grid_fid = row[1]
                    continue
                if len(row) == 3:
                    depthrt = row[1]
                    volrt = row[2]
                outrc_sql += [(grid_fid, depthrt, volrt)]
            self.batch_execute(outrc_sql)

    def import_tailings(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_tailings_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_tailings_hdf5()

    def import_tailings_dat(self):
        tailings_sql = [
            """INSERT INTO tailing_cells (grid, tailings_surf_elev, water_surf_elev, concentration, geom) VALUES""",
            5,
        ]
        tailings_cv_sql = [
            """INSERT INTO tailing_cells (grid, tailings_surf_elev, water_surf_elev, concentration, geom) VALUES""",
            5,
        ]
        tailings_sd_sql = [
            """INSERT INTO tailing_cells (grid, tailings_surf_elev, water_surf_elev, concentration, geom) VALUES""",
            5,
        ]

        self.clear_tables("tailing_cells")

        # TAILINGS.DAT
        data = self.parser.parse_tailings()
        if data:
            for row in data:
                grid_fid, tailings_surf_elev = row
                square = self.build_square(self.grid_centroids([grid_fid])[grid_fid], self.shrink)
                tailings_sql += [(grid_fid, tailings_surf_elev, 0, 0, square)]
            self.batch_execute(tailings_sql)
            qry = """UPDATE tailing_cells SET name = 'Tailings ' ||  cast(fid as text);"""
            self.execute(qry)

        # TAILINGS_CV.DAT
        data = self.parser.parse_tailings_cv()
        if data:
            for row in data:
                grid_fid, tailings_surf_elev, concentration = row
                square = self.build_square(self.grid_centroids([grid_fid])[grid_fid], self.shrink)
                tailings_cv_sql += [(grid_fid, tailings_surf_elev, 0, concentration, square)]
            self.batch_execute(tailings_cv_sql)
            qry = """UPDATE tailing_cells SET name = 'Tailings ' ||  cast(fid as text);"""
            self.execute(qry)

        # TAILINGS_STACK_DEPTH.DAT
        data = self.parser.parse_tailings_sd()
        if data:
            for row in data:
                grid_fid, water_surf_elev, tailings_surf_elev = row
                square = self.build_square(self.grid_centroids([grid_fid])[grid_fid], self.shrink)
                tailings_sd_sql += [(grid_fid, water_surf_elev, tailings_surf_elev, 0, square)]
            self.batch_execute(tailings_sd_sql)
            qry = """UPDATE tailing_cells SET name = 'Tailings ' ||  cast(fid as text);"""
            self.execute(qry)

    def import_tailings_hdf5(self):
        try:
            # Access the tailings group
            tailings_group = self.parser.read_groups("Input/Tailings")
            if tailings_group:
                tailings_group = tailings_group[0]

                self.clear_tables("tailing_cells")

                tailings_sql = [
                    """INSERT INTO tailing_cells (grid, tailings_surf_elev, water_surf_elev, concentration, geom) VALUES""",
                    5,
                ]
                tailings_cv_sql = [
                    """INSERT INTO tailing_cells (grid, tailings_surf_elev, water_surf_elev, concentration, geom) VALUES""",
                    5,
                ]
                tailings_sd_sql = [
                    """INSERT INTO tailing_cells (grid, tailings_surf_elev, water_surf_elev, concentration, geom) VALUES""",
                    5,
                ]

                # Import TAILINGS dataset
                if "TAILINGS" in tailings_group.datasets:
                    data = tailings_group.datasets["TAILINGS"].data
                    for row in data:
                        grid_fid, tailings_surf_elev = row
                        square = self.build_square(self.grid_centroids([grid_fid])[grid_fid], self.cell_size)
                        tailings_sql += [(grid_fid, tailings_surf_elev, 0, 0, square)]
                    self.batch_execute(tailings_sql)
                    qry = """UPDATE tailing_cells SET name = 'Tailings ' ||  cast(fid as text);"""
                    self.execute(qry)

                # Import TAILINGS_CV if present
                if "TAILINGS_CV" in tailings_group.datasets:
                    data = tailings_group.datasets["TAILINGS_CV"].data
                    for row in data:
                        grid_fid, tailings_surf_elev, concentration = row
                        square = self.build_square(self.grid_centroids([grid_fid])[grid_fid], self.cell_size)
                        tailings_cv_sql += [(grid_fid, tailings_surf_elev, 0, concentration, square)]
                    self.batch_execute(tailings_cv_sql)
                    qry = """UPDATE tailing_cells SET name = 'Tailings ' ||  cast(fid as text);"""
                    self.execute(qry)

                # Import TAILINGS_STACK_DEPTH if present
                if "TAILINGS_STACK_DEPTH" in tailings_group.datasets:
                    data = tailings_group.datasets["TAILINGS_STACK_DEPTH"].data
                    for row in data:
                        grid_fid, tailings_surf_elev, water_surf_elev = row
                        square = self.build_square(self.grid_centroids([grid_fid])[grid_fid], self.cell_size)
                        tailings_sd_sql += [(grid_fid, tailings_surf_elev, water_surf_elev, 0, square)]
                    self.batch_execute(tailings_sd_sql)
                    qry = """UPDATE tailing_cells SET name = 'Tailings ' ||  cast(fid as text);"""
                    self.execute(qry)

                return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR: importing TAILINGS from HDF5 failed!\n", e)
            self.uc.log_info("ERROR: importing TAILINGS from HDF5 failed!")
            return False

    def import_outflow(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_outflow_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_outflow_hdf5()

    def import_outflow_dat(self):
        outflow_sql = [
            """INSERT INTO outflow (chan_out, fp_out, hydro_out, chan_tser_fid, chan_qhpar_fid,
                                            chan_qhtab_fid, fp_tser_fid, bc_fid) VALUES""",
            8,
        ]
        cells_sql = ["""INSERT INTO outflow_cells (outflow_fid, grid_fid) VALUES""", 2]
        qh_params_sql = ["""INSERT INTO qh_params (fid) VALUES""", 1]
        qh_params_data_sql = [
            """INSERT INTO qh_params_data (params_fid, hmax, coef, exponent) VALUES""",
            4,
        ]
        qh_tab_sql = ["""INSERT INTO qh_table (fid) VALUES""", 1]
        qh_tab_data_sql = [
            """INSERT INTO qh_table_data (table_fid, depth, q) VALUES""",
            3,
        ]
        ts_sql = ["""INSERT INTO outflow_time_series (fid) VALUES""", 1]
        ts_data_sql = [
            """INSERT INTO outflow_time_series_data (series_fid, time, value) VALUES""",
            3,
        ]

        self.clear_tables(
            "outflow",
            "outflow_cells",
            "qh_params",
            "qh_params_data",
            "qh_table",
            "qh_table_data",
            "outflow_time_series",
            "outflow_time_series_data",
        )
        data = self.parser.parse_outflow()

        qh_params_fid = 0
        qh_tab_fid = 0
        ts_fid = 0
        fid = 1
        for gid, values in data.items():
            chan_out = values["K"]
            fp_out = values["O"]
            hydro_out = values["hydro_out"]
            chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid = [0] * 4
            if values["qh_params"]:
                qh_params_fid += 1
                chan_qhpar_fid = qh_params_fid
                qh_params_sql += [(qh_params_fid,)]
                for row in values["qh_params"]:
                    qh_params_data_sql += [(qh_params_fid,) + tuple(row)]
            else:
                pass
            if values["qh_data"]:
                qh_tab_fid += 1
                chan_qhtab_fid = qh_tab_fid
                qh_tab_sql += [(qh_tab_fid,)]
                for row in values["qh_data"]:
                    qh_tab_data_sql += [(qh_tab_fid,) + tuple(row)]
            else:
                pass
            if values["time_series"]:
                ts_fid += 1
                if values["N"] == 1:
                    fp_tser_fid = ts_fid
                elif values["N"] == 2:
                    chan_tser_fid = ts_fid
                else:
                    pass
                ts_sql += [(ts_fid,)]
                for row in values["time_series"]:
                    ts_data_sql += [(ts_fid,) + tuple(row)]
            else:
                pass
            outflow_sql += [
                (
                    chan_out,
                    fp_out,
                    hydro_out,
                    chan_tser_fid,
                    chan_qhpar_fid,
                    chan_qhtab_fid,
                    fp_tser_fid,
                    fid,
                )
            ]
            cells_sql += [(fid, gid)]
            fid += 1

        self.batch_execute(
            qh_params_sql,
            qh_params_data_sql,
            qh_tab_sql,
            qh_tab_data_sql,
            ts_sql,
            ts_data_sql,
            outflow_sql,
            cells_sql,
        )
        type_qry = """UPDATE outflow SET type = (CASE
                    WHEN (fp_out > 0 AND chan_out = 0 AND fp_tser_fid = 0) THEN 1
                    WHEN (fp_out = 0 AND chan_out > 0 AND chan_tser_fid = 0 AND
                          chan_qhpar_fid = 0 AND chan_qhtab_fid = 0) THEN 2
                    WHEN (fp_out > 0 AND chan_out > 0) THEN 3
                    WHEN (hydro_out > 0) THEN 4
                    WHEN (fp_out = 0 AND fp_tser_fid > 0) THEN 5
                    WHEN (chan_out = 0 AND chan_tser_fid > 0) THEN 6
                    WHEN (fp_out > 0 AND fp_tser_fid > 0) THEN 7
                    WHEN (chan_out > 0 AND chan_tser_fid > 0) THEN 8
                    -- WHEN (chan_qhpar_fid > 0) THEN 9 -- stage-disscharge qhpar
                    WHEN (chan_qhpar_fid > 0) THEN 10 -- depth-discharge qhpar
                    WHEN (chan_qhtab_fid > 0) THEN 11
                    ELSE 0
                END),
                name = 'Outflow ' ||  cast(fid as text);"""
        self.execute(type_qry)
        # update series and tables names
        ts_name_qry = """UPDATE outflow_time_series SET name = 'Time series ' ||  cast(fid as text);"""
        self.execute(ts_name_qry)
        qhpar_name_qry = """UPDATE qh_params SET name = 'Q(h) parameters ' ||  cast(fid as text);"""
        self.execute(qhpar_name_qry)
        qhtab_name_qry = """UPDATE qh_table SET name = 'Q(h) table ' ||  cast(fid as text);"""
        self.execute(qhtab_name_qry)

    def import_outflow_hdf5(self):
        try:
            outflow_group = self.parser.read_groups("Input/Boundary Conditions/Outflow")
            if outflow_group:
                outflow_group = outflow_group[0]

                self.clear_tables(
                    "outflow",
                    "outflow_cells",
                    "qh_params",
                    "qh_params_data",
                    "qh_table",
                    "qh_table_data",
                    "outflow_time_series",
                    "outflow_time_series_data",
                )

                floodplain_outflow_sql = [
                    """INSERT INTO outflow (fid, fp_out, hydro_out, chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid, bc_fid) VALUES""",
                    8,
                ]

                channel_outflow_sql = [
                    """INSERT INTO outflow (fid, chan_out, hydro_out, chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid, bc_fid) VALUES""",
                    8,
                ]

                cells_sql = ["""INSERT OR REPLACE INTO outflow_cells (outflow_fid, grid_fid, geom_type) VALUES""", 3]
                qh_params_sql = ["""INSERT OR REPLACE INTO qh_params (fid, name) VALUES""", 2]
                qh_params_data_sql = ["""INSERT INTO qh_params_data (params_fid, hmax, coef, exponent) VALUES""", 4]
                qh_tab_sql = ["""INSERT INTO qh_table (fid, name) VALUES""", 2]
                qh_tab_data_sql = ["""INSERT INTO qh_table_data (table_fid, depth, q) VALUES""", 3]
                ts_sql = ["""INSERT OR REPLACE INTO outflow_time_series (fid, name) VALUES""", 2]
                ts_data_sql = ["""INSERT INTO outflow_time_series_data (series_fid, time, value) VALUES""", 3]

                update_sql = []
                parsed_grid = {}
                fid = 1
                bc_fid = self.execute("SELECT MAX(fid) FROM all_schem_bc;").fetchone()
                if bc_fid and bc_fid[0] is not None:
                    bc_fid = bc_fid[0] + 1
                else:
                    bc_fid = 1

                # Read datasets
                if "FP_OUT_GRID" in outflow_group.datasets:
                    data = outflow_group.datasets["FP_OUT_GRID"].data
                    for grid in data:
                        if grid not in parsed_grid.keys():
                            parsed_grid[grid] = fid
                            floodplain_outflow_sql += [
                                (
                                    fid,
                                    1,
                                    0,
                                    0,
                                    0,
                                    0,
                                    0,
                                    bc_fid,
                                )
                            ]
                            cells_sql += [
                                (
                                    fid,
                                    int(grid),
                                    'point'
                                )
                            ]
                            fid += 1
                            bc_fid += 1
                        else:
                            existing_fid = parsed_grid[grid]
                            update_sql.append(f"UPDATE outflow SET fp_out = 1 WHERE fid = {existing_fid};")

                if "CH_OUT_GRID" in outflow_group.datasets:
                    data = outflow_group.datasets["CH_OUT_GRID"].data
                    for grid in data:
                        if grid not in parsed_grid.keys():
                            parsed_grid[grid] = fid
                            channel_outflow_sql += [
                                (
                                    fid,
                                    1,
                                    0,
                                    0,
                                    0,
                                    0,
                                    0,
                                    bc_fid,
                                )
                            ]
                            cells_sql += [
                                (
                                    fid,
                                    int(grid),
                                    'point'
                                )
                            ]
                            fid += 1
                            bc_fid += 1
                        else:
                            existing_fid = parsed_grid[grid]
                            update_sql.append(f"UPDATE outflow SET chan_out = 1 WHERE fid = {existing_fid};")

                if "HYD_OUT_GRID" in outflow_group.datasets:
                    data = outflow_group.datasets["HYD_OUT_GRID"].data
                    for row in data:
                        hydro_out, grid = row
                        floodplain_outflow_sql += [
                            (
                                fid,
                                0,
                                int(hydro_out),
                                0,
                                0,
                                0,
                                0,
                                bc_fid,
                            )
                        ]
                        cells_sql += [
                            (
                                fid,
                                int(grid),
                                'point'
                            )
                        ]
                        fid += 1
                        bc_fid += 1

                if "TS_OUT_GRID" in outflow_group.datasets:
                    data = outflow_group.datasets["TS_OUT_GRID"].data
                    for row in data:
                        grid, cell_type, ts_id = row
                        if grid not in parsed_grid.keys():
                            if int(cell_type) == 0:  # floodplain
                                floodplain_outflow_sql += [
                                    (
                                        fid,
                                        0,
                                        0,
                                        0,
                                        0,
                                        0,
                                        int(ts_id),
                                        bc_fid,
                                    )
                                ]
                                cells_sql += [
                                    (
                                        fid,
                                        int(grid),
                                        'point'
                                    )
                                ]
                                ts_sql += [(int(ts_id), "Time series " + str(ts_id))]
                                fid += 1
                                bc_fid += 1

                            if int(cell_type) == 1:  # channel
                                channel_outflow_sql += [
                                    (
                                        fid,
                                        0,
                                        0,
                                        int(ts_id),
                                        0,
                                        0,
                                        0,
                                        bc_fid,
                                    )
                                ]
                                cells_sql += [
                                    (
                                        fid,
                                        int(grid),
                                        'point'
                                    )
                                ]
                                ts_sql += [(int(ts_id), "Time series " + str(ts_id))]
                                fid += 1
                                bc_fid += 1
                        else:
                            if int(cell_type) == 0:  # floodplain
                                existing_fid = parsed_grid[grid]
                                update_sql.append(f"UPDATE outflow SET fp_tser_fid = {int(ts_id)} WHERE fid = {existing_fid};")
                                ts_sql += [(int(ts_id), "Time series " + str(ts_id))]

                            if int(cell_type) == 1:  # channel
                                existing_fid = parsed_grid[grid]
                                update_sql.append(f"UPDATE outflow SET chan_tser_fid = {int(ts_id)} WHERE fid = {existing_fid};")
                                ts_sql += [(int(ts_id), "Time series " + str(ts_id))]

                if "TS_OUT_DATA" in outflow_group.datasets:
                    data = outflow_group.datasets["TS_OUT_DATA"].data
                    for row in data:
                        ts_id, time, value = row
                        ts_data_sql += [(int(ts_id), time, value)]

                if "QH_PARAMS_GRID" in outflow_group.datasets:
                    data = outflow_group.datasets["QH_PARAMS_GRID"].data
                    for row in data:
                        grid, qh_params_id = row
                        if grid not in parsed_grid.keys():
                            channel_outflow_sql += [
                                (
                                    fid,
                                    1,
                                    0,
                                    0,
                                    qh_params_id,
                                    0,
                                    0,
                                    bc_fid,
                                )
                            ]
                            cells_sql += [
                                (
                                    fid,
                                    int(grid),
                                    'point'
                                )
                            ]
                            qh_params_sql += [(int(qh_params_id), "Q(h) parameters " + str(qh_params_id))]
                            fid += 1
                            bc_fid += 1
                        else:
                            existing_fid = parsed_grid[grid]
                            update_sql.append(
                                f"UPDATE outflow SET chan_qhpar_fid = {int(qh_params_id)} WHERE fid = {existing_fid};")
                            qh_params_sql += [(int(qh_params_id), "Q(h) parameters " + str(qh_params_id))]

                if "QH_PARAMS" in outflow_group.datasets:
                    data = outflow_group.datasets["QH_PARAMS"].data
                    for row in data:
                        qh_params_id, param1, param2, param3 = row
                        qh_params_data_sql += [(int(qh_params_id), param1, param2, param3)]

                if "QH_TABLE_GRID" in outflow_group.datasets:
                    data = outflow_group.datasets["QH_TABLE_GRID"].data
                    for row in data:
                        grid, qh_table_id = row
                        if grid not in parsed_grid.keys():
                            channel_outflow_sql += [
                                (
                                    fid,
                                    1,
                                    0,
                                    0,
                                    0,
                                    qh_table_id,
                                    0,
                                    bc_fid,
                                )
                            ]
                            cells_sql += [
                                (
                                    fid,
                                    int(grid),
                                    'point'
                                )
                            ]
                            qh_tab_sql += [(int(qh_table_id), "Q(h) table " + str(qh_table_id))]
                            fid += 1
                            bc_fid += 1
                        else:
                            existing_fid = parsed_grid[grid]
                            update_sql.append(
                                f"UPDATE outflow SET chan_qhtab_fid = {int(qh_table_id)} WHERE fid = {existing_fid};")
                            qh_tab_data_sql += [(int(qh_table_id), "Q(h) parameters " + str(qh_table_id))]

                if "QH_TABLE" in outflow_group.datasets:
                    data = outflow_group.datasets["QH_TABLE"].data
                    for row in data:
                        qh_table_id, param1, param2 = row
                        qh_tab_data_sql += [(int(qh_table_id), param1, param2)]

                if floodplain_outflow_sql:
                    self.batch_execute(floodplain_outflow_sql)

                if channel_outflow_sql:
                    self.batch_execute(channel_outflow_sql)

                if ts_sql:
                    self.batch_execute(ts_sql)

                if ts_data_sql:
                    self.batch_execute(ts_data_sql)

                if qh_params_sql:
                    self.batch_execute(qh_params_sql)

                if qh_params_data_sql:
                    self.batch_execute(qh_params_data_sql)

                if qh_tab_sql:
                    self.batch_execute(qh_tab_sql)

                if qh_tab_data_sql:
                    self.batch_execute(qh_tab_data_sql)

                if update_sql:
                    for qry in update_sql:
                        self.execute(qry)

                if cells_sql:
                    self.batch_execute(cells_sql)

                type_qry = """UPDATE outflow SET type = (CASE
                                    WHEN (fp_out > 0 AND chan_out = 0 AND fp_tser_fid = 0) THEN 1
                                    WHEN (fp_out = 0 AND chan_out > 0 AND chan_tser_fid = 0 AND
                                          chan_qhpar_fid = 0 AND chan_qhtab_fid = 0) THEN 2
                                    WHEN (fp_out > 0 AND chan_out > 0) THEN 3
                                    WHEN (hydro_out > 0) THEN 4
                                    WHEN (fp_out = 0 AND fp_tser_fid > 0) THEN 5
                                    WHEN (chan_out = 0 AND chan_tser_fid > 0) THEN 6
                                    WHEN (fp_out > 0 AND fp_tser_fid > 0) THEN 7
                                    WHEN (chan_out > 0 AND chan_tser_fid > 0) THEN 8
                                    WHEN (chan_qhpar_fid > 0) THEN 9 -- depth-discharge qhpar
                                    WHEN (chan_qhtab_fid > 0) THEN 10
                                    ELSE 0
                                END),
                                name = 'Outflow ' ||  cast(fid as text);"""
                self.execute(type_qry)
                return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR: importing OUTFLOW from HDF5 failed!\n", e)
            self.uc.log_info("ERROR: importing OUTFLOW from HDF5 failed!")
            return False

    def import_rain(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_rain_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_rain_hdf5()

    def import_rain_dat(self):
        rain_sql = [
            """INSERT INTO rain (time_series_fid, irainreal, irainbuilding, tot_rainfall,
                                         rainabs, irainarf, movingstorm, rainspeed, iraindir) VALUES""",
            9,
        ]
        ts_sql = ["""INSERT INTO rain_time_series (fid) VALUES""", 1]
        tsd_sql = [
            """INSERT INTO rain_time_series_data (series_fid, time, value) VALUES""",
            3,
        ]
        cells_sql = [
            """INSERT INTO rain_arf_cells (rain_arf_area_fid, grid_fid, arf) VALUES""",
            3,
        ]

        self.clear_tables(
            "rain",
            "rain_arf_cells",
            "rain_time_series",
            "rain_time_series_data",
        )
        options, time_series, rain_arf = self.parser.parse_rain()
        gids = (x[0] for x in rain_arf)
        cells = self.grid_centroids(gids)

        fid = 1
        fid_ts = 1

        # If the RAIN.DAT does not contain IRAINDIR and RAINSPEED, add it as a default of 0
        if len(options.values()) == 6:
            options["RAINSPEED"] = 0
            options["IRAINDIR"] = 0

        rain_sql += [(fid_ts,) + tuple(options.values())]
        ts_sql += [(fid_ts,)]

        for row in time_series:
            dummy, time, value = row
            tsd_sql += [(fid_ts, time, value)]

        for i, row in enumerate(rain_arf, 1):
            gid, val = row
            # rain_arf_sql += [(fid, val, self.build_buffer(cells[gid], self.buffer))]
            cells_sql += [(i, gid, val)]

        self.batch_execute(ts_sql, rain_sql, tsd_sql, cells_sql)  # rain_arf_sql
        name_qry = """UPDATE rain_time_series SET name = 'Time series ' || cast (fid as text) """
        self.execute(name_qry)

    def import_rain_hdf5(self):
        try:
            rain_group = self.parser.read_groups("Input/Rainfall")
            if rain_group:
                rain_group = rain_group[0]

                rain_sql = [
                    """INSERT INTO rain (time_series_fid, irainreal, irainbuilding, tot_rainfall,
                                         rainabs, irainarf, movingstorm, rainspeed, iraindir) VALUES""",
                    9,
                ]
                ts_sql = ["""INSERT INTO rain_time_series (fid) VALUES""", 1]
                tsd_sql = [
                    """INSERT INTO rain_time_series_data (series_fid, time, value) VALUES""",
                    3,
                ]
                cells_sql = [
                    """INSERT INTO rain_arf_cells (rain_arf_area_fid, grid_fid, arf) VALUES""",
                    3,
                ]

                self.clear_tables(
                    "rain",
                    "rain_arf_cells",
                    "rain_time_series",
                    "rain_time_series_data",
                )

                # Read RAIN_GLOBAL dataset
                rain_global = rain_group.datasets["RAIN_GLOBAL"].data
                if len(rain_global) < 8:
                    raise ValueError("RAIN_GLOBAL dataset is incomplete.")
                rain_sql += [(1,) + tuple(rain_global[:8])]

                # Insert time series data
                ts_sql += [(1,)]
                rain_data = rain_group.datasets["RAIN_DATA"].data
                for row in rain_data:
                    time, value = row
                    tsd_sql += [(1, time, value)]

                # Insert ARF data if available
                if "RAIN_ARF" in rain_group.datasets:
                    rain_arf = rain_group.datasets["RAIN_ARF"].data
                    for i, row in enumerate(rain_arf, 1):
                        grid_fid, arf = row
                        cells_sql += [(i, int(grid_fid), float(arf))]

                # Execute batch inserts
                self.batch_execute(ts_sql, rain_sql, tsd_sql, cells_sql)

                # Update time series name
                name_qry = """UPDATE rain_time_series SET name = 'Time series ' || cast(fid as text);"""
                self.execute(name_qry)

                return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR: Importing RAIN data from HDF5 failed!", e)
            return False

    def import_raincell(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_raincell_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_raincell_hdf5()

    def import_raincell_dat(self):
        head_sql = [
            """INSERT INTO raincell (rainintime, irinters, timestamp) VALUES""",
            3,
        ]
        data_sql = [
            """INSERT INTO raincell_data (time_interval, rrgrid, iraindum) VALUES""",
            3,
        ]

        self.clear_tables("raincell", "raincell_data")

        header, data = self.parser.parse_raincell()
        head_sql += [tuple(header)]

        time_step = float(header[0])
        irinters = int(header[1])
        data_len = len(data)
        grid_count = data_len // irinters
        data_gen = (data[i: i + grid_count] for i in range(0, data_len, grid_count))
        time_interval = 0
        for data_series in data_gen:
            for row in data_series:
                data_sql += [(time_interval,) + tuple(row)]
            time_interval += time_step
        self.batch_execute(head_sql, data_sql)

    def import_raincell_hdf5(self):
        try:

            s = QSettings()
            project_dir = s.value("FLO-2D/lastGdsDir")

            raincell = os.path.join(project_dir, "RAINCELL.HDF5")
            if os.path.exists(raincell):

                head_sql = [
                    """INSERT INTO raincell (rainintime, irinters, timestamp) VALUES""",
                    3,
                ]

                data_sql = [
                    """INSERT INTO raincell_data (time_interval, rrgrid, iraindum) VALUES""",
                    3,
                ]

                self.clear_tables("raincell", "raincell_data", "raincellraw", "flo2d_raincell")

                with h5py.File(raincell, "r") as f:
                    grp  = f["raincell"]

                    # Read header scalars
                    rainintime = int(grp["RAININTIME"][()])  # scalar int
                    irinters = int(grp["IRINTERS"][()])  # scalar int

                    # TIMESTAMP is a 1-element array of bytes
                    ts0 = grp["TIMESTAMP"][0]
                    if isinstance(ts0, (bytes, bytearray)):
                        timestamp = ts0.decode("utf-8", errors="ignore")
                    else:
                        timestamp = str(ts0)

                    head_sql += [(rainintime, int(irinters), timestamp)]

                    # Bulk insert raincell_data in chunks
                    dts = grp["IRAINDUM"]  # shape (n_cells, irinters)
                    n_cells, n_intervals = dts.shape

                    # Iterate column-wise to keep locality by time_interval
                    for i in range(n_intervals):
                        col = dts[:, i]  # length n_cells
                        # Append rows to chunk
                        # rrgrid is 1..n_cells to match your exported order
                        for rrgrid in range(1, n_cells + 1):
                            # Ensure native Python float for DB drivers
                            val = float(col[rrgrid - 1])
                            data_sql += [(int(i), int(rrgrid), val)]

                    if head_sql:
                        self.batch_execute(head_sql)

                    if data_sql:
                        self.batch_execute(data_sql)

                return True
            else:
                return False

        except Exception as e:
            self.uc.show_error("Error while importing RAINCELL data from HDF5!", e)
            self.uc.log_info("Error while importing RAINCELL data from HDF5!")
            return False

    def import_raincellraw(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_raincellraw_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_raincellraw_hdf5()

    def import_raincellraw_dat(self):
        try:
            head_sql = [
                """INSERT INTO raincell (rainintime, irinters) VALUES""",
                2,
            ]
            raincellraw_data_sql = [
                """INSERT INTO raincellraw (nxrdgd, r_time, rrgrid) VALUES""",
                3,
            ]

            flo2draincell_data_sql = [
                """INSERT INTO flo2d_raincell (iraindum, nxrdgd) VALUES""",
                2,
            ]

            self.clear_tables("raincell", "raincell_data", "raincellraw", "flo2d_raincell")

            rainintime, irinters, data = self.parser.parse_raincellraw()
            head_sql += [(rainintime, irinters)]

            nxrdgd = None
            for row in data:
                if row[0] == 'N':
                    nxrdgd = row[1]
                if row[0] == 'R':
                    r_time = row[1]
                    rrgrid = row[2]
                    raincellraw_data_sql += [(nxrdgd, r_time, rrgrid)]

            data = self.parser.parse_flo2draincell()
            for row in data:
                iraindum, nxrdgd = row
                flo2draincell_data_sql += [(iraindum, nxrdgd)]

            self.batch_execute(head_sql, raincellraw_data_sql, flo2draincell_data_sql)

        except Exception as e:
            self.uc.show_error("Error while importing RAINCELLRAW.DAT and FLO2DRAINCELL.DAT!", e)
            self.uc.log_info("Error while importing RAINCELLRAW.DAT and FLO2DRAINCELL.DAT!")

    def import_raincellraw_hdf5(self):
        try:

            s = QSettings()
            project_dir = s.value("FLO-2D/lastGdsDir")

            raincellraw = os.path.join(project_dir, "RAINCELLRAW.HDF5")
            if os.path.exists(raincellraw):

                head_sql = [
                    """INSERT INTO raincell (rainintime, irinters) VALUES""",
                    2,
                ]

                raincellraw_sql = [
                    """INSERT INTO raincellraw (nxrdgd, r_time, rrgrid) VALUES""",
                    3,
                ]

                flo2draincell_sql = [
                    """INSERT INTO flo2d_raincell (iraindum, nxrdgd) VALUES""",
                    2,
                ]

                self.clear_tables("raincell", "raincell_data", "raincellraw", "flo2d_raincell")

                with h5py.File(raincellraw, "r") as f:
                    grp = f["raincellraw"]

                    # Read header scalars
                    rainintime = int(grp["RAININTIME"][()])  # scalar int
                    irinters = int(grp["IRINTERS"][()])  # scalar int

                    head_sql += [(rainintime, int(irinters))]

                    flo2draincell_dts = grp["FLO2DRAINCELL"]
                    for row in flo2draincell_dts:
                        flo2draincell_sql += [(int(row[0]), int(row[1]))]

                    raincellraw_dts = grp["RAINCELLRAW"]
                    for row in raincellraw_dts:
                        raincellraw_sql += [(int(row[0]), float(row[1]), float(row[2]))]

                    if head_sql:
                        self.batch_execute(head_sql)

                    if flo2draincell_sql:
                        self.batch_execute(flo2draincell_sql)

                    if raincellraw_sql:
                        self.batch_execute(raincellraw_sql)

                return True
            else:
                return False

        except Exception as e:
            self.uc.show_error("Error while importing RAINCELL data from HDF5!", e)
            self.uc.log_info("Error while importing RAINCELL data from HDF5!")
            return False

    def import_infil(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_infil_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_infil_hdf5()

    def import_infil_dat(self):
        infil_params = [
            "infmethod",
            "abstr",
            "sati",
            "satf",
            "poros",
            "soild",
            "infchan",
            "hydcall",
            "soilall",
            "hydcadj",
            "hydcxx",
            "scsnall",
            "abstr1",
            "fhortoni",
            "fhortonf",
            "decaya",
            "fhortonia"
        ]
        infil_sql = ["INSERT INTO infil (" + ", ".join(infil_params) + ") VALUES", 17]
        infil_seg_sql = [
            """INSERT INTO infil_chan_seg (chan_seg_fid, hydcx, hydcxfinal, soildepthcx) VALUES""",
            4,
        ]
        infil_green_sql = [
            """INSERT INTO infil_cells_green (grid_fid, hydc, soils, dtheta,
                                                             abstrinf, rtimpf, soil_depth) VALUES""",
            7,
        ]
        infil_scs_sql = ["""INSERT INTO infil_cells_scs (grid_fid, scsn) VALUES""", 2]
        infil_horton_sql = [
            """INSERT INTO infil_cells_horton (grid_fid, fhorti, fhortf, deca) VALUES""",
            4,
        ]
        infil_chan_sql = [
            """INSERT INTO infil_chan_elems (grid_fid, hydconch) VALUES""",
            2,
        ]

        sqls = {
            "F": infil_green_sql,
            "S": infil_scs_sql,
            "H": infil_horton_sql,
            "C": infil_chan_sql,
        }

        self.clear_tables(
            "infil",
            "infil_chan_seg",
            "infil_cells_green",
            "infil_cells_scs",
            "infil_cells_horton",
            "infil_chan_elems",
        )
        data = self.parser.parse_infil()

        infil_sql += [tuple([data[k.upper()] if k.upper() in data else None for k in infil_params])]

        for i, row in enumerate(data["R"], 1):
            infil_seg_sql += [(i,) + tuple(row)]

        for k in sqls:
            if len(data[k]) > 0:
                for i, row in enumerate(data[k], 1):
                    gid = row[0]
                    sqls[k] += [(gid,) + tuple(row[1:])]
            else:
                pass

        self.batch_execute(
            infil_sql,
            infil_seg_sql,
            infil_green_sql,
            infil_scs_sql,
            infil_horton_sql,
            infil_chan_sql,
        )

    def import_infil_hdf5(self):
        # Access the infiltration group
        infil_group = self.parser.read_groups("Input/Infiltration")
        if infil_group:
            infil_group = infil_group[0]

            infil_params = [
                "infmethod",
                "abstr",
                "sati",
                "satf",
                "poros",
                "soild",
                "infchan",
                "hydcall",
                "soilall",
                "hydcadj",
                "hydcxx",
                "scsnall",
                "abstr1",
                "fhortoni",
                "fhortonf",
                "decaya",
                "fhortonia"
            ]
            infil_sql = ["INSERT INTO infil (" + ", ".join(infil_params) + ") VALUES", 17]
            infil_seg_sql = [
                """INSERT INTO infil_chan_seg (chan_seg_fid, hydcx, hydcxfinal, soildepthcx) VALUES""",
                4,
            ]
            infil_green_sql = [
                """INSERT INTO infil_cells_green (grid_fid, hydc, soils, dtheta,
                                                                     abstrinf, rtimpf, soil_depth) VALUES""",
                7,
            ]
            infil_scs_sql = ["""INSERT INTO infil_cells_scs (grid_fid, scsn) VALUES""", 2]
            infil_horton_sql = [
                """INSERT INTO infil_cells_horton (grid_fid, fhorti, fhortf, deca) VALUES""",
                4,
            ]
            infil_chan_sql = [
                """INSERT INTO infil_chan_elems (grid_fid, hydconch) VALUES""",
                2,
            ]

            sqls = {
                "F": infil_green_sql,
                "S": infil_scs_sql,
                "H": infil_horton_sql,
                "C": infil_chan_sql,
            }

            self.clear_tables(
                "infil",
                "infil_chan_seg",
                "infil_cells_green",
                "infil_cells_scs",
                "infil_cells_horton",
                "infil_chan_elems",
            )

            try:

                # Read INFIL_METHOD dataset
                infil_method = int(infil_group.datasets["INFIL_METHOD"].data[0])
                infil_data = [infil_method] + [None] * (len(infil_params) - 1)

                # Populate infil_sql with global infiltration parameters
                if infil_method == 1 or infil_method == 3:  # Green-Ampt
                    infil_ga_global = infil_group.datasets["INFIL_GA_GLOBAL"].data
                    infil_data[1:7] = infil_ga_global[:6]  # ABSTR, SATI, SATF, POROS, SOILD, INFCHAN
                    infil_data[7:10] = infil_ga_global[6:9]  # HYDCALL, SOILALL, HYDCADJ

                if infil_method == 2 or infil_method == 3:  # SCS
                    infil_scs_global = infil_group.datasets["INFIL_SCS_GLOBAL"].data
                    infil_data[11:13] = infil_scs_global[:2]  # SCSNALL, ABSTR1

                if infil_method == 4:  # Horton
                    infil_horton_global = infil_group.datasets["INFIL_HORTON_GLOBAL"].data
                    infil_data[13:17] = infil_horton_global[:4]  # FHORTONI, FHORTONF, DECAYA, FHORTONIA

                infil_sql += [tuple(infil_data)]

                # Populate infil_chan_seg
                if "INFIL_CHAN_SEG" in infil_group.datasets:
                    infil_chan_seg_data = infil_group.datasets["INFIL_CHAN_SEG"].data
                    for i, row in enumerate(infil_chan_seg_data, 1):
                        infil_seg_sql += [(i,) + tuple(row)]

                # Populate infil_cells_green
                if "INFIL_GA_CELLS" in infil_group.datasets:
                    infil_ga_cells = infil_group.datasets["INFIL_GA_CELLS"].data
                    for row in infil_ga_cells:
                        sqls["F"] += [tuple(row)]

                # Populate infil_cells_scs
                if "INFIL_SCS_CELLS" in infil_group.datasets:
                    infil_scs_cells = infil_group.datasets["INFIL_SCS_CELLS"].data
                    for row in infil_scs_cells:
                        sqls["S"] += [tuple(row)]

                # Populate infil_cells_horton
                if "INFIL_HORTON_CELLS" in infil_group.datasets:
                    infil_horton_cells = infil_group.datasets["INFIL_HORTON_CELLS"].data
                    for row in infil_horton_cells:
                        sqls["H"] += [tuple(row)]

                # Populate infil_chan_elems
                if "INFIL_CHAN_ELEMS" in infil_group.datasets:
                    infil_chan_elems = infil_group.datasets["INFIL_CHAN_ELEMS"].data
                    for row in infil_chan_elems:
                        sqls["C"] += [tuple(row)]

                # Execute batch inserts
                self.batch_execute(
                    infil_sql,
                    infil_seg_sql,
                    infil_green_sql,
                    infil_scs_sql,
                    infil_horton_sql,
                    infil_chan_sql,
                )

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error("ERROR: Importing INFIL data from HDF5 failed!", e)
                self.uc.log_info("ERROR: Importing INFIL data from HDF5 failed!")

    def import_evapor(self):
        evapor_sql = ["""INSERT INTO evapor (ievapmonth, iday, clocktime) VALUES""", 3]
        evapor_month_sql = [
            """INSERT INTO evapor_monthly (month, monthly_evap) VALUES""",
            2,
        ]
        evapor_hour_sql = [
            """INSERT INTO evapor_hourly (month, hour, hourly_evap) VALUES""",
            3,
        ]

        self.clear_tables("evapor", "evapor_monthly", "evapor_hourly")
        head, data = self.parser.parse_evapor()
        evapor_sql += [tuple(head)]
        for month in data:
            row = data[month]["row"]
            time_series = data[month]["time_series"]
            evapor_month_sql += [tuple(row)]
            for i, ts in enumerate(time_series, 1):
                evapor_hour_sql += [(month, i, ts)]

        self.batch_execute(evapor_sql, evapor_month_sql, evapor_hour_sql)

    def import_chan(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_chan_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_chan_hdf5()

    def import_chan_dat(self):

        QApplication.setOverrideCursor(Qt.WaitCursor)

        chan_sql = [
            """INSERT INTO chan (geom, depinitial, froudc, roughadj, isedn, ibaseflow) VALUES""",
            6,
        ]
        chan_elems_sql = [
            """INSERT INTO chan_elems (geom, fid, seg_fid, nr_in_seg, rbankgrid, fcn, xlen, type) VALUES""",
            8,
        ]
        chan_r_sql = [
            """INSERT INTO chan_r (elem_fid, bankell, bankelr, fcw, fcd) VALUES""",
            5,
        ]
        chan_v_sql = [
            """INSERT INTO chan_v (elem_fid, bankell, bankelr, fcd, a1, a2, b1, b2, c1, c2,
                                                 excdep, a11, a22, b11, b22, c11, c22) VALUES""",
            17,
        ]
        chan_t_sql = [
            """INSERT INTO chan_t (elem_fid, bankell, bankelr, fcw, fcd, zl, zr) VALUES""",
            7,
        ]
        chan_n_sql = ["""INSERT INTO chan_n (elem_fid, nxsecnum, xsecname) VALUES""", 3]
        chan_wsel_sql = [
            """INSERT INTO chan_wsel (istart, wselstart, iend, wselend) VALUES""",
            4,
        ]
        chan_conf_sql = [
            """INSERT INTO chan_confluences (geom, conf_fid, type, chan_elem_fid) VALUES""",
            4,
        ]
        chan_e_sql = ["""INSERT INTO user_noexchange_chan_areas (geom) VALUES""", 1]
        elems_e_sql = [
            """INSERT INTO noexchange_chan_cells (area_fid, grid_fid) VALUES""",
            2,
        ]

        sqls = {
            "R": [chan_r_sql, 4, 7],
            "V": [chan_v_sql, 4, 6],
            "T": [chan_t_sql, 4, 7],
            "N": [chan_n_sql, 2, 3],
        }

        try:
            self.clear_tables(
                "chan",
                "chan_elems",
                "chan_r",
                "chan_v",
                "chan_t",
                "chan_n",
                "chan_confluences",
                "user_noexchange_chan_areas",
                "noexchange_chan_cells",
                "chan_wsel",
            )

            segments, wsel, confluence, noexchange = self.parser.parse_chan()
            for i, seg in enumerate(segments, 1):
                bLine = "0.0"
                if seg[-1][0] == "B":
                    bLine = seg[-1][1] 
                    seg.pop()  
                    
                xs = seg[-1]  # Last element from segment. [-1] means count from right, last from right.
                gids = []
                for ii, row in enumerate(xs, 1):  # Adds counter ii to iterable.
                    char = row[0]  # " R", "V", "T", or "N"
                    gid = row[1]  # Grid element number (no matter what 'char' is).
                    rbank = row[-1]
                    geom = self.build_linestring([gid, rbank]) if int(rbank) > 0 else self.build_linestring([gid, gid])
                    sql, fcn_idx, xlen_idx = sqls[char]
                    xlen = row.pop(xlen_idx)
                    fcn = row.pop(fcn_idx)
                    params = row[1:-1]
                    gids.append(gid)
                    chan_elems_sql += [(geom, gid, i, ii, rbank, fcn, xlen, char)]
                    sql += [tuple(params)]
                options = seg[:-1]
                geom = self.build_linestring(gids)
                chan_sql += [(geom,) + tuple(options + [bLine])]
                

            for row in wsel:
                chan_wsel_sql += [tuple(row)]

            for i, row in enumerate(confluence, 1):
                gid1, gid2 = row[1], row[2]
                cells = self.grid_centroids([gid1, gid2], buffers=True)

                geom1, geom2 = cells[gid1], cells[gid2]
                chan_conf_sql += [(geom1, i, 0, gid1)]
                chan_conf_sql += [(geom2, i, 1, gid2)]
            for i, row in enumerate(noexchange, 1):
                gid = row[-1]
                geom = self.grid_centroids([gid])[gid]
                chan_e_sql += [(self.build_buffer(geom, self.buffer),)]
                elems_e_sql += [(i, gid)]

            self.batch_execute(
                chan_sql,
                chan_elems_sql,
                chan_r_sql,
                chan_v_sql,
                chan_t_sql,
                chan_n_sql,
                chan_conf_sql,
                chan_e_sql,
                elems_e_sql,
                chan_wsel_sql,
            )
            qry = """UPDATE chan SET name = 'Channel ' ||  cast(fid as text);"""
            self.execute(qry)
            QApplication.restoreOverrideCursor()

        except Exception:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn(
                "WARNING 010219.0742: Import channels failed!. Check CHAN.DAT and CHANBANK.DAT files."
            )
            self.uc.log_info(
                "WARNING 010219.0742: Import channels failed!. Check CHAN.DAT and CHANBANK.DAT files."
            )

    def import_chan_hdf5(self):
        channel_group = self.parser.read_groups("Input/Channels")
        if channel_group:
            channel_group = channel_group[0]

            chan_sql = [
                """INSERT INTO chan (geom, depinitial, froudc, roughadj, isedn, ibaseflow) VALUES""",
                6,
            ]
            chan_elems_sql = [
                """INSERT INTO chan_elems (geom, fid, seg_fid, nr_in_seg, rbankgrid, fcn, xlen, type) VALUES""",
                8,
            ]
            chan_r_sql = [
                """INSERT INTO chan_r (elem_fid, bankell, bankelr, fcw, fcd) VALUES""",
                5,
            ]
            # chan_v_sql = [
            #     """INSERT INTO chan_v (elem_fid, bankell, bankelr, fcd, a1, a2, b1, b2, c1, c2,
            #                                          excdep, a11, a22, b11, b22, c11, c22) VALUES""",
            #     17,
            # ]
            chan_t_sql = [
                """INSERT INTO chan_t (elem_fid, bankell, bankelr, fcw, fcd, zl, zr) VALUES""",
                7,
            ]
            chan_n_sql = [
                """INSERT INTO chan_n (elem_fid, nxsecnum, xsecname) VALUES""",
                3
            ]
            chan_wsel_sql = [
                """INSERT INTO chan_wsel (seg_fid, istart, wselstart, iend, wselend) VALUES""",
                5,
            ]
            chan_conf_sql = [
                """INSERT INTO chan_confluences (geom, conf_fid, type, chan_elem_fid) VALUES""",
                4,
            ]
            chan_e_sql = [
                """INSERT INTO user_noexchange_chan_areas (geom) VALUES""",
                1
            ]
            elems_e_sql = [
                """INSERT INTO noexchange_chan_cells (area_fid, grid_fid) VALUES""",
                2,
            ]

            # try:
            self.clear_tables(
                "chan",
                "chan_elems",
                "chan_r",
                "chan_v",
                "chan_t",
                "chan_n",
                "chan_confluences",
                "user_noexchange_chan_areas",
                "noexchange_chan_cells",
                "chan_wsel",
            )

            xs_geom = {}
            left_bank_geom = {}
            left_bank_grids = []
            prev_chan_id = None
            i = 1

            # Read CHANBANK dataset (maps left to right bank grids)
            if "CHANBANK" in channel_group.datasets:
                data = channel_group.datasets["CHANBANK"].data
                for row in data:
                    left_bank_grid, right_bank_grid = row
                    xs_geom[int(left_bank_grid)] = int(right_bank_grid)

            # Helper function to flush geometry per channel
            def flush_channel_geometry():
                if left_bank_grids and prev_chan_id is not None:
                    left_bank_geom[prev_chan_id] = self.build_linestring(left_bank_grids)

            # Process CHAN_NATURAL
            if "CHAN_NATURAL" in channel_group.datasets:
                data = channel_group.datasets["CHAN_NATURAL"].data
                for row in data:
                    chan_id, grid, fcn, xlen, nxecnum = row
                    chan_id = int(chan_id)
                    grid = int(grid)

                    if prev_chan_id is not None and chan_id != prev_chan_id:
                        flush_channel_geometry()
                        left_bank_grids = []
                        i = 1

                    chan_n_sql += [(grid, nxecnum, f"XS {int(nxecnum)}")]
                    if xs_geom[grid] not in [0, "0"]:
                        geom = self.build_linestring([grid, xs_geom[grid]])
                    else:
                        geom = None
                    chan_elems_sql += [(geom, grid, chan_id, i, xs_geom[grid], fcn, xlen, "N")]
                    left_bank_grids.append(grid)
                    prev_chan_id = chan_id
                    i += 1

            # Process CHAN_RECTANGULAR
            if "CHAN_RECTANGULAR" in channel_group.datasets:
                data = channel_group.datasets["CHAN_RECTANGULAR"].data
                for row in data:
                    chan_id, grid, bankell, bankelr, fcn, fcw, fcd, xlen = row
                    chan_id = int(chan_id)
                    grid = int(grid)

                    if prev_chan_id is not None and chan_id != prev_chan_id:
                        flush_channel_geometry()
                        left_bank_grids = []
                        i = 1

                    chan_r_sql += [(grid, bankell, bankelr, fcw, fcd)]
                    if xs_geom[grid] not in [0, "0"]:
                        geom = self.build_linestring([grid, xs_geom[grid]])
                    else:
                        geom = None
                    chan_elems_sql += [(geom, grid, chan_id, i, xs_geom[grid], fcn, xlen, "R")]
                    left_bank_grids.append(grid)
                    prev_chan_id = chan_id
                    i += 1

            # Process CHAN_TRAPEZOIDAL
            if "CHAN_TRAPEZOIDAL" in channel_group.datasets:
                data = channel_group.datasets["CHAN_TRAPEZOIDAL"].data
                for row in data:
                    chan_id, grid, bankell, bankelr, fcn, fcw, fcd, xlen, zl, zr = row
                    chan_id = int(chan_id)
                    grid = int(grid)

                    if prev_chan_id is not None and chan_id != prev_chan_id:
                        flush_channel_geometry()
                        left_bank_grids = []
                        i = 1

                    chan_t_sql += [(grid, bankell, bankelr, fcw, fcd, zl, zr)]
                    if xs_geom[grid] not in [0, "0"]:
                        geom = self.build_linestring([grid, xs_geom[grid]])
                    else:
                        geom = None
                    chan_elems_sql += [(geom, grid, chan_id, i, xs_geom[grid], fcn, xlen, "T")]
                    left_bank_grids.append(grid)
                    prev_chan_id = chan_id
                    i += 1

            # Finalize last channel after all groups
            flush_channel_geometry()

            # Process CHAN_GLOBAL for main channel table
            if "CHAN_GLOBAL" in channel_group.datasets:
                data = channel_group.datasets["CHAN_GLOBAL"].data
                for row in data:
                    # This is done because some hdf5 do not have the ibaseflow on it
                    if len(row) < 6:
                        chan_id, depinitial, froudc, roughadj, isedn = row
                        ibaseflow = 0
                    else:
                        chan_id, depinitial, froudc, roughadj, ibaseflow, isedn = row
                    chan_id = int(chan_id)
                    geom = left_bank_geom.get(chan_id)
                    if float(isedn) == -9999:
                        isedn = None  # Default value for isedn if not provided
                    chan_sql += [(geom, depinitial, froudc, roughadj, isedn, ibaseflow)]

            # Process CONFLUENCES
            if "CONFLUENCES" in channel_group.datasets:
                grid_group = self.parser.read_groups("Input/Grid")[0]
                x_list = grid_group.datasets["COORDINATES"].data[:, 0]
                y_list = grid_group.datasets["COORDINATES"].data[:, 1]
                data = channel_group.datasets["CONFLUENCES"].data
                for row in data:
                    con_id, river_type, grid = row
                    geom = self.build_point_xy(x_list[int(grid) - 1], y_list[int(grid) - 1])
                    chan_conf_sql += [(geom, int(con_id), int(river_type), int(grid))]

            # Process noexchange areas and cells
            if "NOEXCHANGE" in channel_group.datasets:
                data = channel_group.datasets["NOEXCHANGE"].data
                for i, grid in enumerate(data, start=1):
                    geom = self.build_square(self.grid_centroids([int(grid)])[int(grid)], self.cell_size)
                    chan_e_sql += [(geom,)]
                    elems_e_sql += [(i, int(grid))]

            # Process CHAN_WSEL
            if "CHAN_WSE" in channel_group.datasets:
                data = channel_group.datasets["CHAN_WSE"].data
                for row in data:
                    seg_fid, istart, wselstart, iend, wselend = row
                    chan_wsel_sql += [(int(seg_fid), int(istart), wselstart, int(iend), wselend)]

            if chan_n_sql:
                self.batch_execute(chan_n_sql)

            if chan_r_sql:
                self.batch_execute(chan_r_sql)

            if chan_t_sql:
                self.batch_execute(chan_t_sql)

            if chan_sql:
                self.batch_execute(chan_sql)

            if chan_elems_sql:
                self.batch_execute(chan_elems_sql)

            if chan_conf_sql:
                self.batch_execute(chan_conf_sql)

            if chan_e_sql:
                self.batch_execute(chan_e_sql)

            if elems_e_sql:
                self.batch_execute(elems_e_sql)

            if chan_wsel_sql:
                self.batch_execute(chan_wsel_sql)

            qry = """UPDATE chan SET name = 'Channel ' ||  cast(fid as text);"""
            self.execute(qry)

            self.set_cont_par("ICHANNEL" , 1)  # Set ICHANNEL to 1 after import

            QApplication.restoreOverrideCursor()

    def import_xsec(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_xsec_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_xsec_hdf5()

    def import_xsec_dat(self):
        xsec_sql = ["""INSERT INTO xsec_n_data (chan_n_nxsecnum, xi, yi) VALUES""", 3]
        self.clear_tables("xsec_n_data")
        data = self.parser.parse_xsec()
        for key in list(data.keys()):
            xsec_no, xsec_name = key
            nodes = data[key]
            for row in nodes:
                xsec_sql += [(xsec_no,) + tuple(row)]

        self.batch_execute(xsec_sql)

    def import_xsec_hdf5(self):
        channel_group = self.parser.read_groups("Input/Channels")
        if channel_group:
            channel_group = channel_group[0]
            xsec_sql = ["""INSERT INTO xsec_n_data (chan_n_nxsecnum, xi, yi) VALUES""", 3]
            self.clear_tables("xsec_n_data")

            # Process XSEC_DATA
            if "XSEC_DATA" in channel_group.datasets:
                data = channel_group.datasets["XSEC_DATA"].data
                for row in data:
                    chan_n_nxsecnum, xi, yi = row
                    xsec_sql += [(chan_n_nxsecnum, xi, yi)]

            # Process XSEC_NAME
            if "XSEC_NAME" in channel_group.datasets:
                data = channel_group.datasets["XSEC_NAME"].data
                for row in data:
                    nsecum, xsecname = row
                    if isinstance(xsecname, bytes):
                        xsecname = xsecname.decode("utf-8")
                    self.execute(
                        "UPDATE chan_n SET xsecname = ? WHERE nxsecnum = ?;",
                        (xsecname, int(nsecum))
                    )

            if xsec_sql:
                self.batch_execute(xsec_sql)

    def import_hystruc(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_hystruc_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_hystruc_hdf5()

    def import_hystruc_dat(self):
        try:
            hystruc_params = [
                "geom",
                "type",
                "structname",
                "ifporchan",
                "icurvtable",
                "inflonod",
                "outflonod",
                "inoutcont",
                "headrefel",
                "clength",
                "cdiameter",
            ]
            hystruc_sql = [
                "INSERT INTO struct (" + ", ".join(hystruc_params) + ") VALUES",
                11,
            ]
            ratc_sql = [
                """INSERT INTO rat_curves (struct_fid, hdepexc, coefq, expq, coefa, expa) VALUES""",
                6,
            ]
            repl_ratc_sql = [
                """INSERT INTO repl_rat_curves (struct_fid, repdep, rqcoef, rqexp, racoef, raexp) VALUES""",
                6,
            ]
            ratt_sql = [
                """INSERT INTO rat_table (struct_fid, hdepth, qtable, atable) VALUES""",
                4,
            ]
            culvert_sql = [
                """INSERT INTO culvert_equations (struct_fid, typec, typeen, culvertn, ke, cubase, multibarrels) VALUES""",
                7,
            ]
            storm_sql = [
                """INSERT INTO storm_drains (struct_fid, istormdout, stormdmax) VALUES""",
                3,
            ]
            bridge_sql = [
                """INSERT INTO bridge_variables (struct_fid, IBTYPE, COEFF, C_PRIME_USER, KF_COEF, KWW_COEF, KPHI_COEF, KY_COEF, KX_COEF, KJ_COEF, BOPENING, BLENGTH, BN_VALUE, UPLENGTH12, LOWCHORD, DECKHT, DECKLENGTH, PIERWIDTH, SLUICECOEFADJ, ORIFICECOEFADJ, COEFFWEIRB, WINGWALL_ANGLE, PHI_ANGLE, LBTOEABUT, RBTOEABUT) VALUES""",
                25,
            ]

            sqls = {
                "C": ratc_sql,
                "R": repl_ratc_sql,
                "T": ratt_sql,
                "F": culvert_sql,
                "D": storm_sql,
                "B": bridge_sql,
            }

            n_cells = next(self.execute("SELECT COUNT(*) FROM grid;"))[0]
            data = self.parser.parse_hystruct()
            nodes = slice(3, 5)
            cells_outside = ""
            for i, hs in enumerate(data, 1):
                params = hs[:-1]  # Line 'S' (first line of next structure)

                cell_1 = int(params[nodes][0])
                cell_2 = int(params[nodes][1])
                if cell_1 > n_cells or cell_1 < 0 or cell_2 > n_cells or cell_2 < 0:
                    cells_outside += " (" + str(cell_1) + ", " + str(cell_2) + ")\n"
                    continue
                elems = hs[-1]  # Lines 'C', 'R', 'I', 'F', 'D' and/or 'B'(rest of lines of next structure)
                if "B" in elems:
                    elems = {"B": [elems.get("B")[0] + elems.get("B")[1]]}
                geom = self.build_linestring(params[nodes])
                typ = list(elems.keys())[0] if len(elems) == 1 else "C"
                hystruc_sql += [(geom, typ) + tuple(params)]
                for char in list(elems.keys()):
                    for row in elems[char]:
                        sqls[char] += [(i,) + tuple(row)]

            self.clear_tables(
                "struct",
                "rat_curves",
                "repl_rat_curves",
                "rat_table",
                "culvert_equations",
                "storm_drains",
                "bridge_variables",
            )
            self.batch_execute(
                hystruc_sql,
                ratc_sql,
                repl_ratc_sql,
                ratt_sql,
                culvert_sql,
                storm_sql,
                bridge_sql,
            )
            qry = """UPDATE struct SET notes = 'imported';"""
            self.execute(qry)

            if cells_outside != "":
                self.uc.show_warn(
                    "WARNING 120121.1913: Hydraulic structures cells in HYSTRUC.DAT outside the computational domain:\n\n"
                    + cells_outside
                )
                self.uc.log_info(
                    "WARNING 120121.1913: Hydraulic structures cells in HYSTRUC.DAT outside the computational domain:\n\n"
                    + cells_outside
                )

        except Exception:
            QApplication.restoreOverrideCursor()
            self.uc.show_warn(
                "ERROR 040220.0742: Importing hydraulic structures failed!\nPlease check HYSTRUC.DAT data format and values."
            )
            self.uc.log_info(
                "ERROR 040220.0742: Importing hydraulic structures failed!\nPlease check HYSTRUC.DAT data format and values."
            )

    def import_hystruc_hdf5(self):
        try:
            hydrostruct_group = self.parser.read_groups("Input/Hydraulic Structures")
            if hydrostruct_group:
                hydrostruct_group = hydrostruct_group[0]

                self.clear_tables(
                    "struct",
                    "rat_curves",
                    "repl_rat_curves",
                    "rat_table",
                    "culvert_equations",
                    "storm_drains",
                    "bridge_variables",
                )

                hystruc_params = [
                    "fid",
                    "geom",
                    "ifporchan",
                    "icurvtable",
                    "inflonod",
                    "outflonod",
                    "inoutcont",
                    "headrefel",
                    "clength",
                    "cdiameter",
                ]

                hystruc_sql = [
                    "INSERT INTO struct (" + ", ".join(hystruc_params) + ") VALUES",
                    10,
                ]
                ratc_sql = [
                    """INSERT INTO rat_curves (struct_fid, hdepexc, coefq, expq, coefa, expa) VALUES""",
                    6,
                ]
                repl_ratc_sql = [
                    """INSERT INTO repl_rat_curves (struct_fid, repdep, rqcoef, rqexp, racoef, raexp) VALUES""",
                    6,
                ]
                ratt_sql = [
                    """INSERT INTO rat_table (struct_fid, hdepth, qtable, atable) VALUES""",
                    4,
                ]
                culvert_sql = [
                    """INSERT INTO culvert_equations (struct_fid, typec, typeen, culvertn, ke, cubase, multibarrels) VALUES""",
                    7,
                ]
                storm_sql = [
                    """INSERT INTO storm_drains (struct_fid, istormdout, stormdmax) VALUES""",
                    3,
                ]
                bridge_sql = [
                    """INSERT INTO bridge_variables (struct_fid, IBTYPE, COEFF, C_PRIME_USER, KF_COEF, KWW_COEF, KPHI_COEF, KY_COEF, KX_COEF, KJ_COEF, BOPENING, BLENGTH, BN_VALUE, UPLENGTH12, LOWCHORD, DECKHT, DECKLENGTH, PIERWIDTH, SLUICECOEFADJ, ORIFICECOEFADJ, COEFFWEIRB, WINGWALL_ANGLE, PHI_ANGLE, LBTOEABUT, RBTOEABUT) VALUES""",
                    25,
                ]

                # Process STR_CONTROL
                if "STR_CONTROL" in hydrostruct_group.datasets:
                    data = hydrostruct_group.datasets["STR_CONTROL"].data
                    for row in data:
                        struct_fid, ifporchan, icurvtable, inflonod, outflonod, inoutcont, headrefel, clength, cdiameter = row
                        geom = self.build_linestring([int(inflonod), int(outflonod)])
                        hystruc_sql += [(int(struct_fid), geom, int(ifporchan), int(icurvtable), int(inflonod), int(outflonod), int(inoutcont), headrefel, clength, cdiameter)]

                # Process RAT_CURVES
                if "RATING_CURVE" in hydrostruct_group.datasets:
                    data = hydrostruct_group.datasets["RATING_CURVE"].data
                    for row in data:
                        struct_fid, hdepexc, coefq, expq, coefa, expa, repdep, rqcoef, rqexp, racoef, raexp = row
                        ratc_sql += [(int(struct_fid), hdepexc, coefq, expq, coefa, expa)]
                        repl_ratc_sql += [(int(struct_fid), repdep, rqcoef, rqexp, racoef, raexp)]

                # Process RAT_TABLE
                if "RATING_TABLE" in hydrostruct_group.datasets:
                    data = hydrostruct_group.datasets["RATING_TABLE"].data
                    for row in data:
                        rt_fid, hdepth, qtable, atable = row
                        ratt_sql += [(int(rt_fid), hdepth, qtable, atable)]

                # Process CULVERT EQUATIONS
                if "CULVERT_EQUATIONS" in hydrostruct_group.datasets:
                    data = hydrostruct_group.datasets["CULVERT_EQUATIONS"].data
                    for row in data:
                        struct_fid, typec, typeen, culvertn, ke, cubase, multibarrels = row
                        culvert_sql += [(int(struct_fid), typec, typeen, culvertn, ke, cubase, int(multibarrels))]

                # Process STORM_DRAIN
                if "STORM_DRAIN" in hydrostruct_group.datasets:
                    data = hydrostruct_group.datasets["STORM_DRAIN"].data
                    for row in data:
                        struct_fid, istormdout, stormdmax = row
                        storm_sql += [(int(struct_fid), int(istormdout), stormdmax)]

                # Process BRIDGE VARIABLES
                if "BRIDGE_VARIABLES" in hydrostruct_group.datasets:
                    data = hydrostruct_group.datasets["BRIDGE_VARIABLES"].data
                    values = [row[0] for row in data]
                    bridge_sql += [tuple(values)]

                if hystruc_sql:
                    self.batch_execute(hystruc_sql)

                if ratc_sql:
                    self.batch_execute(ratc_sql)

                if repl_ratc_sql:
                    self.batch_execute(repl_ratc_sql)

                if ratt_sql:
                    self.batch_execute(ratt_sql)

                if culvert_sql:
                    self.batch_execute(culvert_sql)

                if storm_sql:
                    self.batch_execute(storm_sql)

                if bridge_sql:
                    self.batch_execute(bridge_sql)

                # Process STR_NAME
                if "STR_NAME" in hydrostruct_group.datasets:
                    data = hydrostruct_group.datasets["STR_NAME"].data
                    for row in data:
                        struct_fid, structname = row
                        if isinstance(structname, bytes):
                            structname = structname.decode("utf-8")
                        self.execute(
                            "UPDATE struct SET structname = ? WHERE fid = ?;",
                            (structname, int(struct_fid))
                        )

        except Exception:
            QApplication.restoreOverrideCursor()
            self.uc.show_warn("ERROR 040220.0742: Importing HDF5 hydraulic structures failed!")
            self.uc.log_info("ERROR 040220.0742: Importing HDF5 hydraulic structures failed!")

    def import_hystruc_bridge_xs(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_hystruc_bridge_xs_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_hystruc_bridge_xs_hdf5()

    def import_hystruc_bridge_xs_dat(self):
        try:
            bridge_xs_sql = [
                """INSERT INTO bridge_xs (struct_fid, xup, yup, yb) VALUES""",
                4,
            ]
            no_struct = ""
            value_missing = False
            data = self.parser.parse_hystruct_bridge_xs()
            for key, values in data.items():
                fid = self.gutils.execute("SELECT fid FROM struct WHERE inflonod = ?;", (key,)).fetchone()
                if fid:
                    for val in values:
                        if len(val) != 3:
                            value_missing = True
                        bridge_xs_sql += [(fid[0],) + tuple(val)]
                else:
                    if key:
                        no_struct += key + "\n"
                    else:
                        no_struct += "Null\n"
            self.clear_tables("bridge_xs")
            self.batch_execute(bridge_xs_sql)

            warnng = ""
            if no_struct != "":
                warnng += (
                        "WARNING 111122.0446:\nThese cells in BRIDGE_XSEC.DAT have no hydraulic structure defined in HYSTRUC.DAT:\n\n"
                        + no_struct
                )
            if value_missing:
                warnng += "\n\nThere are values missing in BRIDGE_XSEC.DAT"
            if warnng != "":
                QApplication.restoreOverrideCursor()
                self.uc.show_info(warnng)
                QApplication.setOverrideCursor(Qt.WaitCursor)

        except Exception:
            QApplication.restoreOverrideCursor()
            self.uc.show_warn(
                "ERROR 101122.1107: Importing hydraulic structures bridge xsecs from BRIDGE_XSEC.DAT failed!"
            )
            self.uc.log_info(
                "ERROR 101122.1107: Importing hydraulic structures bridge xsecs from BRIDGE_XSEC.DAT failed!"
            )
            QApplication.setOverrideCursor(Qt.WaitCursor)

    def import_hystruc_bridge_xs_hdf5(self):
        try:
            hydrostruct_group = self.parser.read_groups("Input/Hydraulic Structures")
            if hydrostruct_group:
                hydrostruct_group = hydrostruct_group[0]
                bridge_xs_sql = [
                    """INSERT INTO bridge_xs (struct_fid, xup, yup, yb) VALUES""",
                    4,
                ]

                self.clear_tables("bridge_xs")

                # Process RAT_TABLE
                if "BRIDGE_XSEC" in hydrostruct_group.datasets:
                    data = hydrostruct_group.datasets["BRIDGE_XSEC"].data
                    for row in data:
                        struct_fid, xup, yup, yb = row
                        bridge_xs_sql += [(int(struct_fid), xup, yup, yb)]

                if bridge_xs_sql:
                    self.batch_execute(bridge_xs_sql)

        except Exception:
            QApplication.restoreOverrideCursor()
            self.uc.show_warn("Importing HDF5 bridge xsecs failed!")
            self.uc.log_info("Importing HDF5 bridge xsecs failed!")
            QApplication.setOverrideCursor(Qt.WaitCursor)

    def import_street(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_street_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_street_hdf5()

    def import_street_dat(self):
        general_sql = [
            """INSERT INTO street_general (strman, istrflo, strfno, depx, widst) VALUES""",
            5,
        ]
        streets_sql = ["""INSERT INTO streets (stname) VALUES""", 1]
        seg_sql = [
            """INSERT INTO street_seg (geom, str_fid, igridn, depex, stman, elstr) VALUES""",
            6,
        ]
        elem_sql = ["""INSERT INTO street_elems (seg_fid, istdir, widr) VALUES""", 3]

        sqls = {"N": streets_sql, "S": seg_sql, "W": elem_sql}

        self.clear_tables("street_general", "streets", "street_seg", "street_elems")
        head, data = self.parser.parse_street()
        general_sql += [tuple(head)]
        seg_fid = 1
        for i, n in enumerate(data, 1):
            name = n[0]
            sqls["N"] += [(name,)]
            for s in n[-1]:
                gid = s[0]
                directions = []
                s_params = s[:-1]
                for w in s[-1]:
                    d = w[0]
                    directions.append(d)
                    sqls["W"] += [(seg_fid,) + tuple(w)]
                """
                "build_multilinestring" builds a line inside cell "gid".
                Parameter "directions" has 1 or 2 values. The beginning-cell and end-cell of the street segment,
                has only one direction. All other cells have 2 directions. All lines include the centroid of cell.
                """
                geom = self.build_multilinestring(gid, directions, self.cell_size)
                sqls["S"] += [(geom, i) + tuple(s_params)]  # Add
                seg_fid += 1

        self.batch_execute(general_sql, streets_sql, seg_sql, elem_sql)

    def import_street_hdf5(self):
        try:
            street_group = self.parser.read_groups("Input/Street")
            if street_group:
                street_group = street_group[0]
                general_sql = [
                    """INSERT INTO street_general (strman, istrflo, strfno, depx, widst) VALUES""",
                    5,
                ]
                streets_sql = ["""INSERT INTO streets (stname) VALUES""", 1]
                seg_sql = [
                    """INSERT INTO street_seg (geom, str_fid, igridn, depex, stman, elstr) VALUES""",
                    6,
                ]
                elem_sql = ["""INSERT INTO street_elems (seg_fid, istdir, widr) VALUES""", 3]

                self.clear_tables("street_general", "streets", "street_seg", "street_elems")

                dir_dict = {}

                # Process STREET_GLOBAL dataset
                if "STREET_GLOBAL" in street_group.datasets:
                    data = street_group.datasets["STREET_GLOBAL"].data
                    for row in data:
                        strman, istrflo, strfno, depx, widst = row
                        general_sql += [(strman, int(istrflo), strfno, depx, widst)]

                # Process STREET_NAME dataset
                if "STREET_NAMES" in street_group.datasets:
                    data = street_group.datasets["STREET_NAMES"].data
                    for name in data:
                        if isinstance(name, (list, np.ndarray)) and len(name) > 0:
                            name_val = name[0]
                        else:
                            name_val = name
                        if isinstance(name_val, bytes):
                            name_val = name_val.decode("utf-8")
                        streets_sql += [(name_val,)]

                # Process STREET_ELEM dataset
                if "STREET_ELEMS" in street_group.datasets:
                    data = street_group.datasets["STREET_ELEMS"].data
                    for row in data:
                        seg_fid, istdir, widr = row
                        dir_dict.setdefault(seg_fid, []).append(str(int(istdir)))
                        elem_sql += [(int(seg_fid), int(istdir), widr)]

                # Process STREET_SEG dataset
                if "STREET_SEG" in street_group.datasets:
                    data = street_group.datasets["STREET_SEG"].data
                    for row in data:
                        seg_fid, igridn, depex, stman, elstr = row
                        directions = dir_dict.get(seg_fid, [])
                        geom = self.build_multilinestring(int(igridn), directions, self.cell_size)
                        seg_sql += [(geom, int(seg_fid), int(igridn), depex, stman, elstr)]

                if general_sql:
                    self.batch_execute(general_sql)

                if streets_sql:
                    self.batch_execute(streets_sql)

                if elem_sql:
                    self.batch_execute(elem_sql)

                if seg_sql:
                    self.batch_execute(seg_sql)

                return True
        except Exception:
            QApplication.restoreOverrideCursor()
            self.uc.show_warn("Importing HDF5 street data failed!")
            self.uc.log_info("Importing HDF5 street data failed!")

    def import_arf(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_arf_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_arf_hdf5()

    def import_arf_dat(self):
        try:
            cont_sql = ["""INSERT INTO cont (name, value) VALUES""", 2]
            cells_sql = [
                """INSERT INTO blocked_cells (geom, area_fid, grid_fid, arf,
                                                       wrf1, wrf2, wrf3, wrf4, wrf5, wrf6, wrf7, wrf8) VALUES""",
                12,
            ]

            self.clear_tables("blocked_cells")
            head, data = self.parser.parse_arf()
            cont_sql += [("IARFBLOCKMOD",) + tuple(head)]
            gids = (str(abs(int(x[0]))) for x in chain(data["T"], data["PB"]))
            cells = self.grid_centroids(gids, buffers=True)

            for i, row in enumerate(chain(data["T"], data["PB"]), 1):
                gid = str(abs(int(row[0])))
                centroid = cells[gid]
                cells_sql += [(centroid, i) + tuple(row)]

            self.batch_execute(cont_sql, cells_sql)

        except Exception as e:
            self.uc.show_error(
                "ERROR 050420.1720.0701: couldn't import ARF.DAT file!"
                + "\n__________________________________________________",
                e,
            )

    def import_arf_hdf5(self):
        try:
            arfwrf_group = self.parser.read_groups("Input/Reduction Factors")
            if arfwrf_group:
                arfwrf_group = arfwrf_group[0]

                cont_sql = ["""INSERT INTO cont (name, value) VALUES""", 2]
                cells_sql = [
                    """INSERT INTO blocked_cells (geom, area_fid, grid_fid, arf,
                                                           wrf1, wrf2, wrf3, wrf4, wrf5, wrf6, wrf7, wrf8) VALUES""",
                    12,
                ]
                # collapse_sql = ["""INSERT INTO user_blocked_areas (geom, collapse, calc_arf, calc_wrf) VALUES""", 4]

                self.clear_tables("blocked_cells", "user_blocked_areas")

                i = 1

                grid_group = self.parser.read_groups("Input/Grid")[0]

                # Read ARF_GLOBAL dataset
                if "ARF_GLOBAL" in arfwrf_group.datasets:
                    arf_global = arfwrf_group.datasets["ARF_GLOBAL"].data
                    if arf_global.size > 0:
                        cont_sql += [("IARFBLOCKMOD", arf_global[0])]

                # Read ARF_TOTALLY_BLOCKED dataset
                if "ARF_TOTALLY_BLOCKED" in arfwrf_group.datasets:
                    totally_blocked = arfwrf_group.datasets["ARF_TOTALLY_BLOCKED"].data
                    x_list = grid_group.datasets["COORDINATES"].data[:, 0]
                    y_list = grid_group.datasets["COORDINATES"].data[:, 1]
                    for i, cell in enumerate(totally_blocked, 1):
                        cell = int(cell)
                        geom = self.build_point_xy(x_list[abs(cell) - 1], y_list[abs(cell) - 1])
                        arf = 1
                        wrf = 1
                        cells_sql += [(geom, i, cell, arf) + (wrf,) * 8]  # Remaining WRF values are 0

                # Read ARF_PARTIALLY_BLOCKED dataset
                if "ARF_PARTIALLY_BLOCKED" in arfwrf_group.datasets:
                    partially_blocked = arfwrf_group.datasets["ARF_PARTIALLY_BLOCKED"].data
                    x_list = grid_group.datasets["COORDINATES"].data[:, 0]
                    y_list = grid_group.datasets["COORDINATES"].data[:, 1]
                    for row in partially_blocked:
                        i += 1
                        grid_fid = int(row[0])
                        geom = self.build_point_xy(x_list[grid_fid - 1], y_list[grid_fid - 1])
                        arf = float(row[1])
                        wrf_values = row[2:]
                        cells_sql += [(geom, i, grid_fid, arf) + tuple(wrf_values)]

                # Execute batch inserts
                self.batch_execute(cont_sql, cells_sql)

        except Exception as e:
            self.uc.show_error(
                "ERROR: Importing ARF data from HDF5 failed!"
                + "\n__________________________________________________",
                e,
            )
            self.uc.log_info("ERROR: Importing ARF data from HDF5 failed!")

    def import_mult(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_mult_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_mult_hdf5()

    def import_mult_dat(self):
        try:
            self.clear_tables("mult", "mult_areas", "mult_lines", "mult_cells")
            head, data = self.parser.parse_mult()
            if head:
                mult_sql = [
                    """INSERT INTO mult (wmc, wdrall, dmall, nodchansall,
                                                 xnmultall, sslopemin, sslopemax, avuld50, simple_n) VALUES""",
                    9,
                ]
                mult_area_sql = [
                    """INSERT INTO mult_areas (geom, wdr, dm, nodchns, xnmult) VALUES""",
                    5,
                ]
                mult_cells_sql = [
                    """INSERT INTO mult_cells (area_fid, grid_fid, wdr, dm, nodchns, xnmult) VALUES""",
                    6,
                ]
                head.append("0.04")
                mult_sql += [tuple(head)]
                gids = (x[0] for x in data)
                cells = self.grid_centroids(gids)
                for i, row in enumerate(data, 1):
                    gid = row[0]
                    geom = self.build_square(cells[gid], self.shrink)
                    mult_area_sql += [(geom,) + tuple(row[1:])]
                    mult_cells_sql += [
                        (
                            i,
                            gid,
                        )
                        + tuple(row[1:])
                    ]
                self.gutils.disable_geom_triggers()
                self.batch_execute(mult_sql, mult_area_sql, mult_cells_sql)
                self.gutils.enable_geom_triggers()

        except Exception as e:
            self.uc.show_error(
                "ERROR 280122.1920.: couldn't import MULT.DAT file!"
                + "\n__________________________________________________",
                e,
            )

        # Import Simplified Multiple Channels:
        try:
            self.clear_tables("simple_mult_lines", "simple_mult_cells")
            head, data = self.parser.parse_simple_mult()
            if head:
                if self.is_table_empty("mult"):
                    self.gutils.fill_empty_mult_globals()
                simple_mult_sql = """UPDATE mult SET simple_n = ?; """
                simple_mult_cells_sql = [
                    """INSERT INTO simple_mult_cells (grid_fid) VALUES""",
                    1,
                ]
                gids = (x[0] for x in data)
                cells = self.grid_centroids(gids)
                for row in data:
                    gid = row[0]
                    geom = self.build_square(cells[gid], self.shrink)
                    simple_mult_cells_sql += [(gid,) + tuple(row[1:])]
                self.gutils.disable_geom_triggers()
                self.gutils.execute(simple_mult_sql, (head))
                self.batch_execute(simple_mult_cells_sql)
                self.gutils.enable_geom_triggers()

        except Exception as e:
            self.uc.show_error(
                "ERROR 280122.1938: couldn't import SIMPLE_MULT.DAT file!"
                + "\n__________________________________________________",
                e,
            )

    def import_mult_hdf5(self):
        mult_group = self.parser.read_groups("Input/Multiple Channels")
        if mult_group:
            mult_group = mult_group[0]
            try:
                mult_sql = [
                    """INSERT INTO mult (wmc, wdrall, dmall, nodchansall,
                                                 xnmultall, sslopemin, sslopemax, avuld50, simple_n) VALUES""",
                    9,
                ]
                mult_area_sql = [
                    """INSERT INTO mult_areas (geom, wdr, dm, nodchns, xnmult) VALUES""",
                    5,
                ]
                mult_cells_sql = [
                    """INSERT INTO mult_cells (area_fid, grid_fid, wdr, dm, nodchns, xnmult) VALUES""",
                    6,
                ]

                self.clear_tables("mult", "mult_areas", "mult_lines", "mult_cells")

                # Process MULT_GLOBAL dataset
                if "MULT_GLOBAL" in mult_group.datasets:
                    data = mult_group.datasets["MULT_GLOBAL"].data
                    for row in data:
                        wmc, wdrall, dmall, nodchansall, xnmultall, sslopemin, sslopemax, avuld50, simple_n = row
                        mult_sql += [(wmc, wdrall, dmall, nodchansall, xnmultall, sslopemin, sslopemax, avuld50, simple_n)]

                # Process MULT dataset
                if "MULT" in mult_group.datasets:
                    data = mult_group.datasets["MULT"].data
                    for i, row in enumerate(data, start=1):
                        gid, wdr, dm, nodchns, xnmult = row
                        geom = self.build_square(self.grid_centroids([int(gid)])[int(gid)], self.shrink)
                        mult_area_sql += [(geom, wdr, dm, int(nodchns), xnmult)]
                        mult_cells_sql += [(i, int(gid), wdr, dm, int(nodchns), xnmult)]

                self.gutils.disable_geom_triggers()
                if mult_sql:
                    self.batch_execute(mult_sql)

                if mult_area_sql:
                    self.batch_execute(mult_area_sql)

                if mult_cells_sql:
                    self.batch_execute(mult_cells_sql)
                self.gutils.enable_geom_triggers()

                self.set_cont_par("IMULTC", 1)

            except Exception as e:
                self.uc.show_error(
                    "Error while importing MULT data from hdf5 file!"
                    + "\n__________________________________________________",
                    e,
                )
                self.uc.log_info("Error while importing MULT data from hdf5 file!")

            # Import Simplified Multiple Channels:
            try:
                simple_mult_cells_sql = [
                    """INSERT INTO simple_mult_cells (grid_fid) VALUES""",
                    1,
                ]

                self.clear_tables("simple_mult_lines", "simple_mult_cells")

                self.gutils.disable_geom_triggers()
                # Process SIMPLE_MULT_GLOBAL dataset
                if "SIMPLE_MULT_GLOBAL" in mult_group.datasets:
                    data = mult_group.datasets["SIMPLE_MULT_GLOBAL"].data
                    n_value = data[0]
                    self.gutils.execute(f"""UPDATE mult SET simple_n = '{n_value[0]}'; """)

                # Process SIMPLE_MULT dataset
                if "SIMPLE_MULT" in mult_group.datasets:
                    data = mult_group.datasets["SIMPLE_MULT"].data
                    for grid in data:
                        gid = int(grid[0])
                        simple_mult_cells_sql += [(gid,)]

                if simple_mult_cells_sql:
                    self.batch_execute(simple_mult_cells_sql)
                self.gutils.enable_geom_triggers()

                self.set_cont_par("IMULTC", 1)

            except Exception as e:
                self.uc.show_error(
                    "Error while importing SIMPLE_MULT data from hdf5 file!"
                    + "\n__________________________________________________",
                    e,
                )
                self.uc.log_info("Error while importing SIMPLE_MULT data from hdf5 file!")

    def import_sed(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_sed_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_sed_hdf5()

    def import_sed_dat(self):
        sed_m_sql = ["""INSERT INTO mud (va, vb, ysa, ysb, sgsm, xkx) VALUES""", 6]
        sed_c_sql = [
            """INSERT INTO sed (isedeqg, isedsizefrac, dfifty, sgrad, sgst, dryspwt,
                                         cvfg, isedsupply, isedisplay, scourdep) VALUES""",
            10,
        ]
        sgf_sql = ["""INSERT INTO sed_group_frac (fid) VALUES""", 1]
        sed_z_sql = [
            """INSERT INTO sed_groups (dist_fid, isedeqi, bedthick, cvfi) VALUES""",
            4,
        ]
        sed_p_sql = [
            """INSERT INTO sed_group_frac_data (dist_fid, sediam, sedpercent) VALUES""",
            3,
        ]
        areas_d_sql = ["""INSERT INTO mud_areas (geom, debrisv) VALUES""", 2]
        cells_d_sql = ["""INSERT INTO mud_cells (area_fid, grid_fid) VALUES""", 2]
        areas_g_sql = ["""INSERT INTO sed_group_areas (geom, group_fid) VALUES""", 2]
        cells_g_sql = ["""INSERT INTO sed_group_cells (area_fid, grid_fid) VALUES""", 2]
        areas_r_sql = ["""INSERT INTO sed_rigid_areas (geom) VALUES""", 1]
        cells_r_sql = ["""INSERT INTO sed_rigid_cells (area_fid, grid_fid) VALUES""", 2]
        areas_s_sql = [
            """INSERT INTO sed_supply_areas (geom, dist_fid, isedcfp, ased, bsed) VALUES""",
            5,
        ]
        cells_s_sql = [
            """INSERT INTO sed_supply_cells (area_fid, grid_fid) VALUES""",
            2,
        ]
        sed_n_sql = ["""INSERT INTO sed_supply_frac (fid) VALUES""", 1]
        data_n_sql = [
            """INSERT INTO sed_supply_frac_data (dist_fid, ssediam, ssedpercent) VALUES""",
            3,
        ]

        parts = [
            ["D", areas_d_sql, cells_d_sql],
            ["G", areas_g_sql, cells_g_sql],
            ["R", areas_r_sql, cells_r_sql],
        ]

        new_dict = {
            "M": [],
            "C": [],
            "Z": [],
            "P": [],
            "D": [],
            "E": [],
            "R": [],
            "S": [],
            "N": [],
            "G": [],
        }  # Create a new empty dictionary
        error = ""

        self.clear_tables(
            "mud",
            "mud_areas",
            "mud_cells",
            "sed",
            "sed_groups",
            "sed_group_areas",
            "sed_group_cells",
            "sed_group_frac",
            "sed_group_frac_data",
            "sed_rigid_areas",
            "sed_rigid_cells",
            "sed_supply_areas",
            "sed_supply_cells",
            "sed_supply_frac",
            "sed_supply_frac_data",
        )

        try:
            n_cells = self.gutils.execute("SELECT COUNT(fid) FROM grid;").fetchone()[0]
            data = self.parser.parse_sed()
            for key, value in data.items():
                # If value satisfies the condition, then store it in new_dict
                if key == "S":
                    for v in value:
                        if int(v[0]) <= n_cells:
                            new_dict["S"].append(v)
                        else:
                            error += v[0] + "\n"
                else:
                    for v in value:
                        new_dict[key].append(v)

            data = new_dict
            gids = (x[0] for x in chain(data["D"], data["G"], data["R"], data["S"]))
            cells = self.grid_centroids(gids)
            for row in data["M"]:
                sed_m_sql += [tuple(row)]
            for row in data["C"]:
                erow = ["10.0"]
                if data["E"]:
                    erow = data["E"][0]
                if erow:
                    row += erow
                else:
                    row.append(None)
                sed_c_sql += [tuple(row)]
            for i, row in enumerate(data["Z"], 1):
                sgf_sql += [(i,)]
                sed_z_sql += [(i,) + tuple(row[:-1])]
                for prow in row[-1]:
                    sed_p_sql += [(i,) + tuple(prow)]
            for char, asql, csql in parts:
                for i, row in enumerate(data[char], 1):
                    gid = row[0]
                    vals = row[1:]
                    geom = self.build_square(cells[gid], self.shrink)
                    asql += [(geom,) + tuple(vals)]
                    csql += [(i, gid)]

            for i, row in enumerate(data["S"], 1):
                gid = row[0]
                vals = row[1:-1]
                nrows = row[-1]
                geom = self.build_square(cells[gid], self.shrink)
                areas_s_sql += [(geom, i) + tuple(vals)]
                cells_s_sql += [(i, gid)]
                for ii, nrow in enumerate(nrows, 1):
                    sed_n_sql += [(ii,)]
                    data_n_sql += [(i,) + tuple(nrow)]
            triggers = self.execute("SELECT name, enabled FROM trigger_control").fetchall()
            self.batch_execute(
                sed_m_sql,
                areas_d_sql,
                cells_d_sql,
                sed_c_sql,
                sgf_sql,
                sed_z_sql,
                areas_g_sql,
                cells_g_sql,
                sed_p_sql,
                areas_r_sql,
                # cells_r_sql,
                areas_s_sql,
                cells_s_sql,
                sed_n_sql,
                data_n_sql,
            )

            if self.is_table_empty("mud_cells"):
                self.set_cont_par("IDEBRV", 0)

            if data["M"] == [] and data["C"] == []:
                self.set_cont_par("MUD", 0)
                self.set_cont_par("ISED", 0)

            elif data["M"] == [] and data["C"] != []:
                self.set_cont_par("MUD", 0)
                self.set_cont_par("ISED", 1)

            elif data["M"] != [] and data["C"] == []:
                self.set_cont_par("MUD", 1)
                self.set_cont_par("ISED", 0)

            elif data["M"] != [] and data["C"] != []:
                self.set_cont_par("MUD", 2)
                self.set_cont_par("ISED", 0)

            # Also triggers the creation of rigid cells (rigid_cells table):
            # self.batch_execute(areas_r_sql)
            if error != "":
                QApplication.restoreOverrideCursor()
                self.uc.show_info(
                    "WARNING 190523.0432: some cells are outside the domain in file SED.DAT.\n"
                    + "They were omitted:\n\n"
                    + error,
                )
                QApplication.setOverrideCursor(Qt.WaitCursor)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 180523.0453: couldn't import SED.DAT file!"
                + "\n__________________________________________________",
                e,
            )
            QApplication.setOverrideCursor(Qt.WaitCursor)

    def import_sed_hdf5(self):
        # try:
        sed_group = self.parser.read_groups("Input/Mudflow and Sediment Transport")
        if sed_group:
            sed_group = sed_group[0]

            sed_m_sql = [
                """INSERT INTO mud (va, vb, ysa, ysb, sgsm, xkx) VALUES""",
                6,
            ]
            sed_c_sql = [
                """INSERT INTO sed (isedeqg, isedsizefrac, dfifty, sgrad, sgst, dryspwt,
                                             cvfg, isedsupply, isedisplay, scourdep) VALUES""",
                10,
            ]
            # sgf_sql = [
            #     """INSERT INTO sed_group_frac (fid) VALUES""",
            #     1,
            # ]
            sed_z_sql = [
                """INSERT INTO sed_groups (dist_fid, isedeqi, bedthick, cvfi) VALUES""",
                4,
            ]
            sed_p_sql = [
                """INSERT INTO sed_group_frac_data (dist_fid, sediam, sedpercent) VALUES""",
                3,
            ]
            areas_d_sql = ["""INSERT INTO mud_areas (geom, debrisv) VALUES""", 2]
            cells_d_sql = ["""INSERT INTO mud_cells (area_fid, grid_fid) VALUES""", 2]
            areas_g_sql = ["""INSERT INTO sed_group_areas (geom, group_fid) VALUES""", 2]
            cells_g_sql = ["""INSERT INTO sed_group_cells (area_fid, grid_fid) VALUES""", 2]
            areas_r_sql = ["""INSERT INTO sed_rigid_areas (geom) VALUES""", 1]
            areas_s_sql = [
                """INSERT INTO sed_supply_areas (geom, dist_fid, isedcfp, ased, bsed) VALUES""",
                5,
            ]
            cells_s_sql = [
                """INSERT INTO sed_supply_cells (area_fid, grid_fid) VALUES""",
                2,
            ]
            sed_n_sql = ["""INSERT INTO sed_supply_frac (fid) VALUES""", 1]
            data_n_sql = [
                """INSERT INTO sed_supply_frac_data (dist_fid, ssediam, ssedpercent) VALUES""",
                3,
            ]

            self.clear_tables(
                "mud",
                "mud_areas",
                "mud_cells",
                "sed",
                "sed_groups",
                "sed_group_areas",
                "sed_group_cells",
                "sed_group_frac",
                "sed_group_frac_data",
                "sed_rigid_areas",
                "sed_rigid_cells",
                "sed_supply_areas",
                "sed_supply_cells",
                "sed_supply_frac",
                "sed_supply_frac_data",
            )

            # Process MUDFLOW_PARAMS
            if "MUDFLOW_PARAMS" in sed_group.datasets:
                data = sed_group.datasets["MUDFLOW_PARAMS"].data
                for row in data:
                    va, vb, ysa, ysb, sgsm, xkx = row
                    sed_m_sql += [(va, vb, ysa, ysb, sgsm, xkx)]

            # Process SED_PARAMS
            if "SED_PARAMS" in sed_group.datasets:
                data = sed_group.datasets["SED_PARAMS"].data
                for row in data:
                    isedeqg, isedsizefrac, dfifty, sgrad, sgst, dryspwt, cvfg, isedsupply, isedisplay, scourdep = row
                    sed_c_sql += [(int(isedeqg), int(isedsizefrac), dfifty, sgrad, sgst, dryspwt, cvfg, int(isedsupply), int(isedisplay), scourdep)]

            if "SED_GROUPS" in sed_group.datasets:
                data = sed_group.datasets["SED_GROUPS"].data
                for row in data:
                    dist_fid, isedeqi, bedthick, cvfi = row
                    sed_z_sql += [(int(dist_fid), int(isedeqi), bedthick, cvfi)]

            if "SED_GROUPS_FRAC_DATA" in sed_group.datasets:
                data = sed_group.datasets["SED_GROUPS_FRAC_DATA"].data
                for row in data:
                    dist_fid, sediam, sedpercent = row
                    sed_p_sql += [(int(dist_fid), sediam, sedpercent)]

            if "MUDFLOW_AREAS" in sed_group.datasets:
                data = sed_group.datasets["MUDFLOW_AREAS"].data
                for i, row in enumerate(data, start=1):
                    grid, debrisv = row
                    geom = self.build_square(self.grid_centroids([int(grid)])[int(grid)], self.cell_size)
                    areas_d_sql += [(geom, debrisv)]
                    cells_d_sql += [(i, int(grid))]

            if "SED_GROUPS_AREAS" in sed_group.datasets:
                data = sed_group.datasets["SED_GROUPS_AREAS"].data
                for i, row in enumerate(data, start=1):
                    group_id, grid = row
                    geom = self.build_square(self.grid_centroids([int(grid)])[int(grid)], self.cell_size)
                    areas_g_sql += [(geom, int(group_id))]
                    cells_g_sql += [(int(group_id), int(grid))]

            if "SED_RIGID_CELLS" in sed_group.datasets:
                data = sed_group.datasets["SED_RIGID_CELLS"].data
                for grid in data:
                    grid = grid[0]
                    geom = self.build_square(self.grid_centroids([int(grid)])[int(grid)], self.shrink)
                    areas_r_sql += [(geom,)]

            if "SED_SUPPLY_AREAS" in sed_group.datasets:
                data = sed_group.datasets["SED_SUPPLY_AREAS"].data
                for row in data:
                    dist_fid, isedgrid, isedcfp, ased, bsed = row
                    geom = self.build_square(self.grid_centroids([int(isedgrid)])[int(isedgrid)], self.cell_size)
                    areas_s_sql += [(geom, int(dist_fid), int(isedcfp), ased, bsed)]
                    cells_s_sql += [(int(dist_fid), int(isedgrid))]

            if "SED_SUPPLY_FRAC_DATA" in sed_group.datasets:
                data = sed_group.datasets["SED_SUPPLY_FRAC_DATA"].data
                for i, row in enumerate(data, start=1):
                    dist_fid, ssediam, ssedpercent = row
                    sed_n_sql += [(i,)]
                    data_n_sql += [(int(dist_fid), ssediam, ssedpercent)]

            if sed_m_sql:
                self.batch_execute(sed_m_sql)

            if sed_c_sql:
                self.batch_execute(sed_c_sql)

            if sed_z_sql:
                self.batch_execute(sed_z_sql)

            if sed_p_sql:
                self.batch_execute(sed_p_sql)

            if areas_d_sql:
                self.batch_execute(areas_d_sql)

            if cells_d_sql:
                self.batch_execute(cells_d_sql)

            if areas_g_sql:
                self.batch_execute(areas_g_sql)

            if cells_g_sql:
                self.batch_execute(cells_g_sql)

            if areas_r_sql:
                self.batch_execute(areas_r_sql)

            if areas_s_sql:
                self.batch_execute(areas_s_sql)

            if cells_s_sql:
                self.batch_execute(cells_s_sql)

            if sed_n_sql:
                self.batch_execute(sed_n_sql)

            if data_n_sql:
                self.batch_execute(data_n_sql)

            if self.is_table_empty("mud_cells"):
                self.set_cont_par("IDEBRV", 0)

            if self.is_table_empty("mud") and self.is_table_empty("sed"):
                self.set_cont_par("MUD", 0)
                self.set_cont_par("ISED", 0)

            elif self.is_table_empty("mud") and not self.is_table_empty("sed"):
                self.set_cont_par("MUD", 0)
                self.set_cont_par("ISED", 1)

            elif not self.is_table_empty("mud") and self.is_table_empty("sed"):
                self.set_cont_par("MUD", 1)
                self.set_cont_par("ISED", 0)

            elif not self.is_table_empty("mud") and not self.is_table_empty("sed"):
                self.set_cont_par("MUD", 2)
                self.set_cont_par("ISED", 0)

            return True

        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error(
        #         "Error while importing Mudflow and Sediment Transport from hdf5 file!"
        #         + "\n__________________________________________________",
        #         e,
        #     )
        #     self.uc.log_info("Error while importing Mudflow and Sediment Transport from hdf5 file!")
        #     QApplication.setOverrideCursor(Qt.WaitCursor)

    def import_levee(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_levee_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_levee_hdf5()

    def import_levee_dat(self):
        lgeneral_sql = [
            """INSERT INTO levee_general (raiselev, ilevfail, gfragchar, gfragprob) VALUES""",
            4,
        ]
        ldata_sql = [
            """INSERT INTO levee_data (geom, grid_fid, ldir, levcrest) VALUES""",
            4,
        ]
        lfailure_sql = [
            """INSERT INTO levee_failure (grid_fid, lfaildir, failevel, failtime,
                                                      levbase, failwidthmax, failrate, failwidrate) VALUES""",
            8,
        ]
        lfragility_sql = [
            """INSERT INTO levee_fragility (grid_fid, levfragchar, levfragprob) VALUES""",
            3,
        ]

        self.clear_tables("levee_general", "levee_data", "levee_failure", "levee_fragility")
        head, data = self.parser.parse_levee()

        lgeneral_sql += [tuple(head)]

        for gid, directions in data["L"]:
            for row in directions:
                ldir, levcrest = row
                geom = self.build_levee(gid, ldir, self.cell_size)
                ldata_sql += [(geom, gid, ldir, levcrest)]

        for gid, directions in data["F"]:
            for row in directions:
                lfailure_sql += [(gid,) + tuple(row)]

        for row in data["P"]:
            lfragility_sql += [tuple(row)]

        self.batch_execute(lgeneral_sql, ldata_sql, lfailure_sql, lfragility_sql)

    def import_levee_hdf5(self):
        try:
            levee_group = self.parser.read_groups("Input/Levee")
            if levee_group:
                levee_group = levee_group[0]

                lgeneral_sql = [
                    """INSERT INTO levee_general (raiselev, ilevfail) VALUES""",
                    2,
                ]
                ldata_sql = [
                    """INSERT INTO levee_data (geom, grid_fid, ldir, levcrest) VALUES""",
                    4,
                ]
                lfailure_sql = [
                    """INSERT INTO levee_failure (grid_fid, lfaildir, failevel, failtime,
                                                              levbase, failwidthmax, failrate, failwidrate) VALUES""",
                    8,
                ]

                self.clear_tables("levee_general", "levee_data", "levee_failure", "levee_fragility")

                # Process LEVEE_GLOBAL dataset
                if "LEVEE_GLOBAL" in levee_group.datasets:
                    data = levee_group.datasets["LEVEE_GLOBAL"].data
                    for row in data:
                        raiselev, ilevfail = row
                        lgeneral_sql += [(raiselev, int(ilevfail))]

                if "LEVEE_DATA" in levee_group.datasets:
                    data = levee_group.datasets["LEVEE_DATA"].data
                    for row in data:
                        lgridno, ldir, levcrest = row
                        geom = self.build_levee(int(lgridno), str(int(ldir)), self.cell_size)
                        ldata_sql += [(geom, int(lgridno), int(ldir), levcrest)]

                if "LEVEE_FAILURE" in levee_group.datasets:
                    data = levee_group.datasets["LEVEE_FAILURE"].data
                    for row in data:
                        lfailgrid, lfaildir, failevel, failtime, levbase, failwidthmax, failrate, failwidrate = row
                        lfailure_sql += [(int(lfailgrid), lfaildir, failevel, failtime, levbase, failwidthmax, failrate, failwidrate)]

                if lgeneral_sql:
                    self.batch_execute(lgeneral_sql)

                if ldata_sql:
                    self.batch_execute(ldata_sql)

                if lfailure_sql:
                    self.batch_execute(lfailure_sql)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR: Importing LEVEE data from HDF5 failed!", e)
            self.uc.log_info("ERROR: Importing LEVEE data from HDF5 failed!")

    def import_fpxsec(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_fpxsec_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_fpxsec_hdf5()

    def import_fpxsec_dat(self):
        cont_sql = ["""INSERT INTO cont (name, value) VALUES""", 2]
        fpxsec_sql = ["""INSERT INTO fpxsec (geom, iflo, nnxsec) VALUES""", 3]
        cells_sql = [
            """INSERT INTO fpxsec_cells (geom, fpxsec_fid, grid_fid) VALUES""",
            3,
        ]

        self.clear_tables("fpxsec", "fpxsec_cells")
        head, data = self.parser.parse_fpxsec()
        cont_sql += [("NXPRT", head)]
        for i, xs in enumerate(data, 1):
            params, gids = xs
            geom = self.build_linestring(gids)
            fpxsec_sql += [(geom,) + tuple(params)]
            for gid in gids:
                grid_geom = self.single_centroid(gid, buffers=True)
                cells_sql += [(grid_geom, i, gid)]

        self.batch_execute(cont_sql, fpxsec_sql, cells_sql)

    def import_fpxsec_hdf5(self):
        try:
            fpxsec_group = self.parser.read_groups("Input/Floodplain")
            if fpxsec_group:
                fpxsec_group = fpxsec_group[0]

                cont_sql = ["""INSERT INTO cont (name, value) VALUES""", 2]
                fpxsec_sql = ["""INSERT INTO fpxsec (geom, iflo, nnxsec) VALUES""", 3]
                cells_sql = ["""INSERT INTO fpxsec_cells (geom, fpxsec_fid, grid_fid) VALUES""", 3]

                self.clear_tables("fpxsec", "fpxsec_cells")

                # Read FPXSEC_GLOBAL dataset
                if "FPXSEC_GLOBAL" in fpxsec_group.datasets:
                    nxprt = fpxsec_group.datasets["FPXSEC_GLOBAL"].data[0]
                    cont_sql += [("NXPRT", str(nxprt))]

                # Read FPXSEC_DATA dataset
                if "FPXSEC_DATA" in fpxsec_group.datasets:
                    data = fpxsec_group.datasets["FPXSEC_DATA"].data
                    grid_group = self.parser.read_groups("Input/Grid")[0]
                    x_list = grid_group.datasets["COORDINATES"].data[:, 0]
                    y_list = grid_group.datasets["COORDINATES"].data[:, 1]
                    for i, row in enumerate(data, start=1):
                        iflo, nnxsec = row[:2]
                        gids = [int(g) for g in row[2:] if int(g) != -9999]
                        line_geom = self.build_linestring(gids)
                        fpxsec_sql += [(line_geom, int(iflo), int(nnxsec))]
                        for gid in gids:
                            point_geom = self.build_point_xy(x_list[int(gid) - 1], y_list[int(gid) - 1])
                            cells_sql += [(point_geom, i, int(gid))]

                if cont_sql:
                    self.batch_execute(cont_sql)

                if fpxsec_sql:
                    self.batch_execute(fpxsec_sql)

                if cells_sql:
                    self.batch_execute(cells_sql)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR: Importing FPXSEC data from HDF5 failed!", e)
            self.uc.log_info("ERROR: Importing FPXSEC data from HDF5 failed!")

    def import_breach(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_breach_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_breach_hdf5()

    def import_breach_dat(self):
        glob = [
            "ibreachsedeqn",
            "gbratio",
            "gweircoef",
            "gbreachtime",
            "gzu",
            "gzd",
            "gzc",
            "gcrestwidth",
            "gcrestlength",
            "gbrbotwidmax",
            "gbrtopwidmax",
            "gbrbottomel",
            "gd50c",
            "gporc",
            "guwc",
            "gcnc",
            "gafrc",
            "gcohc",
            "gunfcc",
            "gd50s",
            "gpors",
            "guws",
            "gcns",
            "gafrs",
            "gcohs",
            "gunfcs",
            "ggrasslength",
            "ggrasscond",
            "ggrassvmaxp",
            "gsedconmax",
            "gd50df",
            "gunfcdf",
        ]

        local = [
            "geom",
            "ibreachdir",
            "zu",
            "zd",
            "zc",
            "crestwidth",
            "crestlength",
            "brbotwidmax",
            "brtopwidmax",
            "brbottomel",
            "weircoef",
            "d50c",
            "porc",
            "uwc",
            "cnc",
            "afrc",
            "cohc",
            "unfcc",
            "d50s",
            "pors",
            "uws",
            "cns",
            "afrs",
            "cohs",
            "unfcs",
            "bratio",
            "grasslength",
            "grasscond",
            "grassvmaxp",
            "sedconmax",
            "d50df",
            "unfcdf",
            "breachtime",
        ]
        use_global_data = 0
        global_sql = ["INSERT INTO breach_global (" + ", ".join(glob) + ") VALUES", 32]
        local_sql = ["INSERT INTO breach (" + ", ".join(local) + ") VALUES", 33]
        cells_sql = ["""INSERT INTO breach_cells (breach_fid, grid_fid) VALUES""", 2]
        frag_sql = [
            """INSERT INTO breach_fragility_curves (fragchar, prfail, prdepth) VALUES""",
            3,
        ]

        data = self.parser.parse_breach()
        gids = (x[0] for x in data["D"])
        cells = self.grid_centroids(gids, buffers=True)
        for row in data["G"]:
            use_global_data = 1
            global_sql += [tuple(row)]
        for i, row in enumerate(data["D"], 1):
            gid = row[0]
            geom = cells[gid]
            local_sql += [(geom,) + tuple(row[1:])]
            cells_sql += [(i, gid)]
        for row in data["F"]:
            frag_sql += [tuple(row)]

        self.clear_tables("breach_global", "breach", "breach_cells", "breach_fragility_curves")
        # NOTE: 'cells_sql' was removed in next self.batch_execute since there is a trigger for ´breach' table that inserts them.
        # self.batch_execute(global_sql, local_sql, cells_sql, frag_sql)
        self.batch_execute(global_sql, local_sql, frag_sql)

        # Set 'useglobaldata' to 1 if there are 'G' lines, 0 otherwise:
        self.gutils.execute("UPDATE breach_global SET useglobaldata = ?;", (use_global_data,))

    def import_breach_hdf5(self):
        try:
            levee_group = self.parser.read_groups("Input/Levee")
            if levee_group:
                levee_group = levee_group[0]
                glob = [
                    "ibreachsedeqn",
                    "gbratio",
                    "gweircoef",
                    "gbreachtime",
                    "useglobaldata",
                    "gzu",
                    "gzd",
                    "gzc",
                    "gcrestwidth",
                    "gcrestlength",
                    "gbrbotwidmax",
                    "gbrtopwidmax",
                    "gbrbottomel",
                    "gd50c",
                    "gporc",
                    "guwc",
                    "gcnc",
                    "gafrc",
                    "gcohc",
                    "gunfcc",
                    "gd50s",
                    "gpors",
                    "guws",
                    "gcns",
                    "gafrs",
                    "gcohs",
                    "gunfcs",
                    "ggrasslength",
                    "ggrasscond",
                    "ggrassvmaxp",
                    "gsedconmax",
                    "gd50df",
                    "gunfcdf",
                ]

                local = [
                    "geom",
                    "ibreachdir",
                    "zu",
                    "zd",
                    "zc",
                    "crestwidth",
                    "crestlength",
                    "brbotwidmax",
                    "brtopwidmax",
                    "brbottomel",
                    "weircoef",
                    "d50c",
                    "porc",
                    "uwc",
                    "cnc",
                    "afrc",
                    "cohc",
                    "unfcc",
                    "d50s",
                    "pors",
                    "uws",
                    "cns",
                    "afrs",
                    "cohs",
                    "unfcs",
                    "bratio",
                    "grasslength",
                    "grasscond",
                    "grassvmaxp",
                    "sedconmax",
                    "d50df",
                    "unfcdf",
                    "breachtime",
                ]

                global_sql = ["INSERT INTO breach_global (" + ", ".join(glob) + ") VALUES", 33]
                local_sql = ["INSERT INTO breach (" + ", ".join(local) + ") VALUES", 33]
                cells_sql = ["""INSERT INTO breach_cells (breach_fid, grid_fid) VALUES""", 2]
                frag_sql = [
                    """INSERT INTO breach_fragility_curves (fragchar, prfail, prdepth) VALUES""",
                    3,
                ]

                # Read BREACH_GLOBAL dataset
                if "BREACH_GLOBAL" in levee_group.datasets:
                    data = levee_group.datasets["BREACH_GLOBAL"].data
                    data = data.T
                    for row in data:
                        row[4] = int(row[4])
                        global_sql += [tuple(row)]

                if "BREACH_INDIVIDUAL" in levee_group.datasets:
                    data = levee_group.datasets["BREACH_INDIVIDUAL"].data
                    data = data.T
                    grid_group = self.parser.read_groups("Input/Grid")[0]
                    x_list = grid_group.datasets["COORDINATES"].data[:, 0]
                    y_list = grid_group.datasets["COORDINATES"].data[:, 1]
                    for i, row in enumerate(data, start=1):
                        grid = int(row[0])
                        geom = self.build_point_xy(x_list[grid - 1], y_list[grid - 1])
                        local_sql += [(geom,) + tuple(row[1:])]
                        cells_sql += [(i, grid)]

                if "FRAGILITY_CURVES" in levee_group.datasets:
                    data = levee_group.datasets["FRAGILITY_CURVES"].data
                    for row in data:
                        frag_sql += [tuple(row)]

                if global_sql:
                    self.batch_execute(global_sql)

                if local_sql:
                    self.batch_execute(local_sql)

                if cells_sql:
                    self.batch_execute(cells_sql)

                if frag_sql:
                    self.batch_execute(frag_sql)

                return True
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("Error while importing BREACH data from HDF5!", e)
            self.uc.log_info("Error while importing FPXSEC data from HDF5!")

    def import_fpfroude(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_fpfroude_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_fpfroude_hdf5()

    def import_fpfroude_dat(self):
        fpfroude_sql = ["""INSERT INTO fpfroude (geom, froudefp) VALUES""", 2]
        cells_sql = ["""INSERT INTO fpfroude_cells (area_fid, grid_fid) VALUES""", 2]

        self.clear_tables("fpfroude", "fpfroude_cells")
        data = self.parser.parse_fpfroude()
        gids = (x[0] for x in data)
        cells = self.grid_centroids(gids)
        for i, row in enumerate(data, 1):
            gid, froudefp = row
            geom = self.build_square(cells[gid], self.shrink)
            fpfroude_sql += [(geom, froudefp)]
            cells_sql += [(i, gid)]

        self.batch_execute(fpfroude_sql, cells_sql)

    def import_fpfroude_hdf5(self):
        try:
            fpfroude_group = self.parser.read_groups("Input/Spatially Variable")
            if fpfroude_group:
                fpfroude_group = fpfroude_group[0]

                fpfroude_sql = ["""INSERT INTO fpfroude (geom, froudefp) VALUES""", 2]
                cells_sql = ["""INSERT INTO fpfroude_cells (area_fid, grid_fid) VALUES""", 2]

                self.clear_tables("fpfroude", "fpfroude_cells")

                # Process FPFROUDE dataset
                if "FPFROUDE" in fpfroude_group.datasets:
                    data = fpfroude_group.datasets["FPFROUDE"].data
                    for i, row in enumerate(data, start=1):
                        grid, froudefp = row
                        geom = self.build_square(self.grid_centroids([int(grid)])[int(grid)], self.cell_size)
                        fpfroude_sql += [(geom, froudefp)]
                        cells_sql += [(i, int(grid))]

                if fpfroude_sql:
                    self.batch_execute(fpfroude_sql)

                if cells_sql:
                    self.batch_execute(cells_sql)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR: Importing FPFROUDE data from HDF5 failed!", e)
            self.uc.log_info("ERROR: Importing FPFROUDE data from HDF5 failed!")

    def import_steep_slopen(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_steep_slopen_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_steep_slopen_hdf5()

    def import_steep_slopen_dat(self):
        cells_sql = ["""INSERT INTO steep_slope_n_cells (global, grid_fid) VALUES""", 2]

        self.clear_tables("steep_slope_n_cells")

        data = self.parser.parse_steep_slopen()

        first_value = int(data[0][0])  # Get the first value from the first line

        if first_value == 0:
            return
        elif first_value == 1:
            cells_sql += [(1, 0)]
        elif first_value == 2:
            grid_ids = [int(row[0]) for row in data[1:]]
            for grid_id in grid_ids:
                cells_sql += [(0, grid_id)]

        self.batch_execute(cells_sql)

    def import_steep_slopen_hdf5(self):
        try:
            steep_slopen_group = self.parser.read_groups("Input/Spatially Variable")
            if steep_slopen_group:
                steep_slopen_group = steep_slopen_group[0]

                user_steep_slopen_sql = ["""INSERT INTO user_steep_slope_n_areas (geom, global) VALUES""", 2]
                cells_sql = ["""INSERT INTO steep_slope_n_cells (global, area_fid, grid_fid) VALUES""", 3]

                self.clear_tables("steep_slope_n_cells", "user_steep_slope_n_areas")

                # Process STEEP_SLOPEN_GLOBAL dataset
                if "STEEP_SLOPEN_GLOBAL" in steep_slopen_group.datasets:
                    data = steep_slopen_group.datasets["STEEP_SLOPEN_GLOBAL"].data
                    isteepn_global = int(data[0])
                    if isteepn_global == 0:
                        return
                    elif isteepn_global == 1:
                        self.execute("INSERT INTO steep_slope_n_cells (global) VALUES (1);")
                        return
                    elif isteepn_global == 2:
                        if "STEEP_SLOPEN" in steep_slopen_group.datasets:
                            grid_elems = steep_slopen_group.datasets["STEEP_SLOPEN"].data
                            for i, grid in enumerate(grid_elems, start=1):
                                geom = self.build_square(self.grid_centroids([int(grid)])[int(grid)], self.cell_size)
                                cells_sql += [(0, i, int(grid))]
                                user_steep_slopen_sql += [(geom, 0)]

                if cells_sql:
                    self.batch_execute(cells_sql)

                if user_steep_slopen_sql:
                    self.batch_execute(user_steep_slopen_sql)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR: Importing STEEP_SLOPEN data from HDF5 failed!", e)
            self.uc.log_info("ERROR: Importing STEEP_SLOPEN data from HDF5 failed!")

    def import_lid_volume(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_lid_volume_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_lid_volume_hdf5()

    def import_lid_volume_dat(self):
        cells_sql = ["""INSERT INTO lid_volume_cells (grid_fid, volume) VALUES""", 2]

        self.clear_tables("lid_volume_cells")

        data = self.parser.parse_lid_volume()

        for i, row in enumerate(data, 1):
            gid, volume = row
            cells_sql += [(gid, volume)]

        self.batch_execute(cells_sql)

    def import_lid_volume_hdf5(self):
        try:
            lid_volume_group = self.parser.read_groups("Input/Spatially Variable")
            if lid_volume_group:
                lid_volume_group = lid_volume_group[0]

                user_lid_volume_sql = ["""INSERT INTO user_lid_volume_areas (geom, volume) VALUES""", 2]
                cells_sql = ["""INSERT INTO lid_volume_cells (grid_fid, area_fid, volume) VALUES""", 3]

                self.clear_tables("lid_volume_cells")

                # Process LID_VOLUME dataset
                if "LID_VOLUME" in lid_volume_group.datasets:
                    data = lid_volume_group.datasets["LID_VOLUME"].data
                    for i, row in enumerate(data, start=1):
                        grid, lid_volume = row
                        geom = self.build_square(self.grid_centroids([int(grid)])[int(grid)], self.cell_size)
                        user_lid_volume_sql += [(geom, lid_volume)]
                        cells_sql += [(int(grid), i, lid_volume)]

                if cells_sql:
                    self.batch_execute(cells_sql)

                if user_lid_volume_sql:
                    self.batch_execute(user_lid_volume_sql)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR: Importing LID_VOLUME data from HDF5 failed!", e)
            self.uc.log_info("ERROR: Importing LID_VOLUME data from HDF5 failed!")

    def import_gutter(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_gutter_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_gutter_hdf5()

    def import_gutter_dat(self):
        gutter_globals_sql = [
            """INSERT INTO gutter_globals (width, height, n_value) VALUES""",
            3,
        ]
        gutter_areas_sql = [
            """INSERT INTO gutter_areas (geom, width, height, n_value, direction) VALUES""",
            5,
        ]
        cells_sql = [
            """INSERT INTO gutter_cells (geom, area_fid, grid_fid) VALUES""",
            3,
        ]

        self.clear_tables("gutter_globals", "gutter_areas", "gutter_lines", "gutter_cells")
        head, data = self.parser.parse_gutter()
        gutter_globals_sql += [tuple(head)]

        gids = (x[1] for x in data)
        cells = self.grid_centroids(gids)
        for i, row in enumerate(data, 1):
            gid = row[1]
            geom = self.build_square(cells[gid], self.shrink)
            gutter_areas_sql += [(geom,) + tuple(row[2:])]
            cells_sql += [(geom, i, gid)]

        self.batch_execute(gutter_globals_sql, gutter_areas_sql, cells_sql)

    def import_gutter_hdf5(self):
        try:
            gutter_group = self.parser.read_groups("Input/Gutter")
            if gutter_group:
                gutter_group = gutter_group[0]

                gutter_globals_sql = [
                    """INSERT INTO gutter_globals (width, height, n_value) VALUES""",
                    3,
                ]
                gutter_areas_sql = [
                    """INSERT INTO gutter_areas (geom, width, height, n_value, direction) VALUES""",
                    5,
                ]
                cells_sql = [
                    """INSERT INTO gutter_cells (geom, area_fid, grid_fid) VALUES""",
                    3,
                ]

                self.clear_tables("gutter_globals", "gutter_areas", "gutter_lines", "gutter_cells")

                # Process GUTTER_GLOBAL dataset
                if "GUTTER_GLOBAL" in gutter_group.datasets:
                    data = gutter_group.datasets["GUTTER_GLOBAL"].data
                    for row in data:
                        strwidth, curbheight, n_value = row
                        gutter_globals_sql += [(strwidth, curbheight, n_value)]

                # Process GUTTER_DATA dataset
                if "GUTTER_DATA" in gutter_group.datasets:
                    data = gutter_group.datasets["GUTTER_DATA"].data
                    for i, row in enumerate(data, start=1):
                        igrid, widstr, curbht, xnstr, icurbdir = row
                        geom = self.build_square(self.grid_centroids([int(igrid)])[int(igrid)], self.cell_size)
                        gutter_areas_sql += [(geom, widstr, curbht, xnstr, int(icurbdir))]
                        cells_sql += [(geom, i, int(igrid))]

                if gutter_globals_sql:
                    self.batch_execute(gutter_globals_sql)

                if gutter_areas_sql:
                    self.batch_execute(gutter_areas_sql)

                if cells_sql:
                    self.batch_execute(cells_sql)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR: Importing GUTTER data from HDF5 failed!", e)
            self.uc.log_info("ERROR: Importing GUTTER data from HDF5 failed!")

    def import_swmminp(self, swmm_file="SWMM.INP", delete_existing=True):
        """
        Function to import the SWMM.INP -> refactored from the old method on the storm drain editor widget
        """
        if self.parsed_format == self.FORMAT_HDF5:
            dat_parser = ParseDAT()
            dat_parser.scan_project_dir(self.parser.hdf5_filepath)
            swmminp_dict = dat_parser.parse_swmminp(swmm_file)
        else:
            swmminp_dict = self.parser.parse_swmminp(swmm_file)

        if swmminp_dict:

            coordinates_data = swmminp_dict.get('COORDINATES', [])
            if len(coordinates_data) == 0:
                self.uc.show_warn(
                    "WARNING 060319.1729: SWMM input file has no coordinates defined!"
                )
                self.uc.log_info(
                    "WARNING 060319.1729: SWMM input file has no coordinates defined!"
                )
                return

            self.import_swmminp_control(swmminp_dict)
            self.import_swmminp_inflows(swmminp_dict, delete_existing)
            self.import_swmminp_patterns(swmminp_dict, delete_existing)
            self.import_swmminp_ts(swmminp_dict, delete_existing)
            self.import_swmminp_curves(swmminp_dict, delete_existing)
            self.import_swmminp_inlets_junctions(swmminp_dict, delete_existing)
            self.import_swmminp_outfalls(swmminp_dict, delete_existing)
            self.import_swmminp_storage_units(swmminp_dict, delete_existing)
            self.import_swmminp_conduits(swmminp_dict, delete_existing)
            self.import_swmminp_pumps(swmminp_dict, delete_existing)
            self.import_swmminp_orifices(swmminp_dict, delete_existing)
            self.import_swmminp_weirs(swmminp_dict, delete_existing)

            self.remove_outside_junctions()

    def remove_outside_junctions(self):
        """
        Function to remove outside junctions
        """
        try:
            # SELECT all the nodes connected to a conduit
            inside_inlets_qry = self.execute("""
                SELECT DISTINCT conduit_inlet FROM user_swmm_conduits
                UNION
                SELECT DISTINCT pump_inlet FROM user_swmm_pumps
                UNION
                SELECT DISTINCT orifice_inlet FROM user_swmm_orifices
                UNION
                SELECT DISTINCT weir_inlet FROM user_swmm_weirs
            ;""").fetchall()
            inside_inlets = [inside_inlet[0] for inside_inlet in inside_inlets_qry]
            inside_outlets_qry = self.execute("""            
                SELECT DISTINCT conduit_outlet FROM user_swmm_conduits
                UNION
                SELECT DISTINCT pump_outlet FROM user_swmm_pumps
                UNION
                SELECT DISTINCT orifice_outlet FROM user_swmm_orifices
                UNION
                SELECT DISTINCT weir_outlet FROM user_swmm_weirs
            ;""").fetchall()
            inside_outlets = [inside_outlet[0] for inside_outlet in inside_outlets_qry]
            inside_nodes = list(set(inside_inlets) | set(inside_outlets))

            # Convert list to a SQL list
            placeholders = ', '.join(['?'] * len(inside_nodes))

            # Remove all the nodes that are not inside nodes.
            inlet_junctions_delete_query = f"""
                DELETE FROM user_swmm_inlets_junctions
                WHERE name NOT IN ({placeholders});
            """
            inlet_junctions_delete = self.execute(inlet_junctions_delete_query, inside_nodes)
            inlet_junctions_deleted_count = inlet_junctions_delete.rowcount
            if inlet_junctions_deleted_count > 0:
                self.uc.log_info(f"JUNCTIONS: {inlet_junctions_deleted_count} are outside the domain and not added to the project")
            outfalls_delete_query = f"""
                DELETE FROM user_swmm_outlets
                WHERE name NOT IN ({placeholders});
            """
            outfalls_delete = self.execute(outfalls_delete_query, inside_nodes)
            outfalls_deleted_count = outfalls_delete.rowcount
            if outfalls_deleted_count > 0:
                self.uc.log_info(f"OUTFALLS: {outfalls_deleted_count} are outside the domain and not added to the project")
            storage_delete_query = f"""
                DELETE FROM user_swmm_storage_units
                WHERE name NOT IN ({placeholders});
            """
            storage_delete = self.execute(storage_delete_query, inside_nodes)
            storage_deleted_count = storage_delete.rowcount
            if storage_deleted_count > 0:
                self.uc.log_info(f"STORAGES: {storage_deleted_count} are outside the domain and not added to the project")

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            msg = "ERROR 08282024.0505: Removing outside nodes failed!\n\n" \
                  f"{e}"
            self.uc.show_error(msg, e)
            self.uc.log_info(msg)
            QApplication.restoreOverrideCursor()

    def import_swmminp_control(self, swmminp_dict):
        """
        Function to import swmm inp control data
        """
        try:
            self.gutils.clear_tables('swmm_control')
            insert_controls_sql = """INSERT INTO swmm_control (
                                           name,
                                           value
                                           )
                                           VALUES (?, ?);"""

            controls_data = swmminp_dict.get('OPTIONS', [])

            for control in controls_data:
                self.gutils.execute(insert_controls_sql, (
                    control[0],
                    control[1]
                    )
                )

            report_data = swmminp_dict.get('REPORT', [])

            for report in report_data:
                self.gutils.execute(insert_controls_sql, (
                    report[0],
                    report[1]
                    )
                )

            # Adjust the TITLE
            title_sql = self.gutils.execute("SELECT name, value FROM swmm_control WHERE name = 'TITLE';").fetchone()
            if not title_sql:
                self.gutils.execute("""INSERT INTO swmm_control (name, value)
                                       VALUES 
                                       ('TITLE', 'INP file created by FLO-2D')
                                    """)

            self.uc.log_info("Storm Drain control variables set")

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            msg = "ERROR 08272024.0849: creation of Storm Drain control variables failed!\n\n" \
                  "Please check your SWMM input data.\n" \
                  f"{e}"
            self.uc.show_error(msg, e)
            self.uc.log_info(msg)
            QApplication.restoreOverrideCursor()

    def import_swmminp_weirs(self, swmminp_dict, delete_existing):
        """
        Function to import swmm inp weirs
        """
        try:
            existing_weirs = []
            not_added = []
            if delete_existing:
                self.gutils.clear_tables('user_swmm_weirs')
            else:
                existing_weirs_qry = self.gutils.execute("SELECT weir_name FROM user_swmm_weirs;").fetchall()
                existing_weirs = [weir[0] for weir in existing_weirs_qry]

            insert_weirs_sql = """INSERT INTO user_swmm_weirs (
                                    weir_name,
                                    weir_inlet,
                                    weir_outlet,
                                    weir_type,
                                    weir_crest_height,
                                    weir_disch_coeff,
                                    weir_flap_gate,
                                    weir_end_contrac,
                                    weir_end_coeff,
                                    weir_shape, 
                                    weir_height, 
                                    weir_length,
                                    weir_side_slope,
                                    geom
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);"""

            replace_user_swmm_weirs_sql = """UPDATE user_swmm_weirs
                             SET   weir_inlet  = ?,
                                   weir_outlet  = ?,
                                   weir_type = ?,
                                   weir_crest_height = ?,
                                   weir_disch_coeff = ?,
                                   weir_flap_gate = ?,
                                   weir_end_contrac = ?,
                                   weir_end_coeff = ?,
                                   weir_shape = ?,
                                   weir_height = ?,
                                   weir_length = ?,
                                   weir_side_slope = ?
                             WHERE weir_name = ?;"""

            weirs_data = swmminp_dict.get('WEIRS', [])
            coordinates_data = swmminp_dict.get('COORDINATES', [])
            coordinates_dict = {item[0]: item[1:] for item in coordinates_data}
            xsections_data = swmminp_dict.get('XSECTIONS', [])
            xsections_dict = {item[0]: item[1:] for item in xsections_data}
            vertices_data = swmminp_dict.get('VERTICES', [])

            if len(weirs_data) > 0:
                added_weirs = 0
                updated_weirs = 0
                for weir in weirs_data:
                    """
                    [WEIRS]
                    ;;               Inlet            Outlet           Weir         Crest      Disch.     Flap End      End       
                    ;;Name           Node             Node             Type         Height     Coeff.     Gate Con.     Coeff.    
                    ;;-------------- ---------------- ---------------- ------------ ---------- ---------- ---- -------- ----------
                    weir1            Cistern3         Ocistern         V-NOTCH      4.50       3.30       NO   0        0.00      
                    """

                    # SWMM Variables
                    weir_name = weir[0]
                    weir_inlet = weir[1]
                    weir_outlet = weir[2]
                    weir_type = weir[3]
                    weir_crest_height = weir[4]
                    weir_disch_coeff = weir[5]
                    weir_flap_gate = weir[6]
                    weir_end_contrac = weir[7]
                    weir_end_coeff = weir[8]

                    weir_shape = xsections_dict[weir_name][0]
                    weir_height = xsections_dict[weir_name][1]
                    weir_length = xsections_dict[weir_name][2]
                    weir_side_slope = xsections_dict[weir_name][3]

                    # QGIS Variables
                    linestring_list = []
                    inlet_x = coordinates_dict[weir_inlet][0]
                    inlet_y = coordinates_dict[weir_inlet][1]
                    inlet_grid = self.grid_on_point(inlet_x, inlet_y)

                    linestring_list.append((inlet_x, inlet_y))

                    for vertice in vertices_data:
                        if vertice[0] == weir_name:
                            linestring_list.append((vertice[1], vertice[2]))

                    outlet_x = coordinates_dict[weir_outlet][0]
                    outlet_y = coordinates_dict[weir_outlet][1]
                    outlet_grid = self.grid_on_point(outlet_x, outlet_y)

                    linestring_list.append((outlet_x, outlet_y))

                    # Both ends of the orifice is outside the grid
                    if not inlet_grid and not outlet_grid:
                        not_added.append(weir_name)
                        continue

                    # Orifice inlet is outside the grid, and it is an Inlet
                    if not inlet_grid and weir_inlet.lower().startswith("i"):
                        not_added.append(weir_name)
                        continue

                    geom = "LINESTRING({})".format(", ".join("{0} {1}".format(x, y) for x, y in linestring_list))
                    geom = self.gutils.wkt_to_gpb(geom)

                    if weir_name in existing_weirs:
                        updated_weirs += 1
                        self.gutils.execute(
                            replace_user_swmm_weirs_sql,
                            (
                                weir_inlet,
                                weir_outlet,
                                weir_type,
                                weir_crest_height,
                                weir_disch_coeff,
                                weir_flap_gate,
                                weir_end_contrac,
                                weir_end_coeff,
                                weir_shape,
                                weir_height,
                                weir_length,
                                weir_side_slope,
                                weir_name,
                            ),
                        )
                    else:
                        added_weirs += 1
                        self.gutils.execute(insert_weirs_sql, (
                                            weir_name,
                                            weir_inlet,
                                            weir_outlet,
                                            weir_type,
                                            weir_crest_height,
                                            weir_disch_coeff,
                                            weir_flap_gate,
                                            weir_end_contrac,
                                            weir_end_coeff,
                                            weir_shape,
                                            weir_height,
                                            weir_length,
                                            weir_side_slope,
                                            geom
                                            )
                                            )
                self.uc.log_info(f"WEIRS: {added_weirs} added and {updated_weirs} updated from imported SWMM INP file")

                if len(not_added) > 0:
                    self.uc.log_info(
                        f"WEIRS: {len(not_added)} are outside the domain and not added to the project")

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            msg = "ERROR 080422.1115: creation of Storm Drain Weirs layer failed!\n\n" \
                  "Please check your SWMM input data.\n" \
                  f"{e}"
            self.uc.show_error(msg, e)
            self.uc.log_info(msg)
            QApplication.restoreOverrideCursor()

    def import_swmminp_orifices(self, swmminp_dict, delete_existing):
        """
        Function to import swmm inp orifices
        """
        try:
            not_added = []
            existing_orifices = []
            if delete_existing:
                self.gutils.clear_tables('user_swmm_orifices')
            else:
                existing_orifices_qry = self.gutils.execute("SELECT orifice_name FROM user_swmm_orifices;").fetchall()
                existing_orifices = [orifice[0] for orifice in existing_orifices_qry]

            insert_orifices_sql = """INSERT INTO user_swmm_orifices (
                                    orifice_name,
                                    orifice_inlet,
                                    orifice_outlet,
                                    orifice_type,
                                    orifice_crest_height,
                                    orifice_disch_coeff,
                                    orifice_flap_gate,
                                    orifice_open_close_time,
                                    orifice_shape,
                                    orifice_height,
                                    orifice_width,
                                    geom
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);"""

            replace_user_swmm_orificies_sql = """UPDATE user_swmm_orifices
                             SET   orifice_inlet  = ?,
                                   orifice_outlet  = ?,
                                   orifice_type  = ?,
                                   orifice_crest_height  = ?,
                                   orifice_disch_coeff  = ?,
                                   orifice_flap_gate  = ?,
                                   orifice_open_close_time  = ?,
                                   orifice_shape  = ?,
                                   orifice_height  = ?,
                                   orifice_width  = ?
                             WHERE orifice_name = ?;"""

            orifices_data = swmminp_dict.get('ORIFICES', [])
            coordinates_data = swmminp_dict.get('COORDINATES', [])
            coordinates_dict = {item[0]: item[1:] for item in coordinates_data}
            xsections_data = swmminp_dict.get('XSECTIONS', [])
            xsections_dict = {item[0]: item[1:] for item in xsections_data}
            vertices_data = swmminp_dict.get('VERTICES', [])

            if len(orifices_data) > 0:
                added_orifices = 0
                updated_orifices = 0
                for orifice in orifices_data:
                    """
                    [ORIFICES]
                    ;;               Inlet            Outlet           Orifice      Crest      Disch.     Flap Open/Close
                    ;;Name           Node             Node             Type         Height     Coeff.     Gate Time      
                    ;;-------------- ---------------- ---------------- ------------ ---------- ---------- ---- ----------
                    orifice1         Cistern1         Cistern2         SIDE         0.50       0.65       NO   0.00      
                    """

                    # SWMM Variables
                    orifice_name = orifice[0]
                    orifice_inlet = orifice[1]
                    orifice_outlet = orifice[2]
                    orifice_type = orifice[3]
                    orifice_crest_height = orifice[4]
                    orifice_disch_coeff = orifice[5]
                    orifice_flap_gate = orifice[6]
                    orifice_open_close_time = orifice[7]

                    orifice_shape = xsections_dict[orifice_name][0]
                    orifice_height = xsections_dict[orifice_name][1]
                    orifice_width = xsections_dict[orifice_name][2]

                    # QGIS Variables
                    linestring_list = []
                    inlet_x = coordinates_dict[orifice_inlet][0]
                    inlet_y = coordinates_dict[orifice_inlet][1]
                    inlet_grid = self.gutils.grid_on_point(inlet_x, inlet_y)

                    linestring_list.append((inlet_x, inlet_y))

                    for vertice in vertices_data:
                        if vertice[0] == orifice_name:
                            linestring_list.append((vertice[1], vertice[2]))

                    outlet_x = coordinates_dict[orifice_outlet][0]
                    outlet_y = coordinates_dict[orifice_outlet][1]
                    outlet_grid = self.gutils.grid_on_point(outlet_x, outlet_y)

                    linestring_list.append((outlet_x, outlet_y))

                    # Both ends of the orifice is outside the grid
                    if not inlet_grid and not outlet_grid:
                        not_added.append(orifice_name)
                        continue

                    # Orifice inlet is outside the grid, and it is an Inlet
                    if not inlet_grid and orifice_inlet.lower().startswith("i"):
                        not_added.append(orifice_name)
                        continue

                    geom = "LINESTRING({})".format(", ".join("{0} {1}".format(x, y) for x, y in linestring_list))
                    geom = self.gutils.wkt_to_gpb(geom)

                    if orifice_name in existing_orifices:
                        updated_orifices += 1
                        self.gutils.execute(
                            replace_user_swmm_orificies_sql,
                            (
                                orifice_inlet,
                                orifice_outlet,
                                orifice_type,
                                orifice_crest_height,
                                orifice_disch_coeff,
                                orifice_flap_gate,
                                orifice_open_close_time,
                                orifice_shape,
                                orifice_height,
                                orifice_width,
                                orifice_name,
                            )
                        )
                    else:
                        added_orifices += 1
                        self.gutils.execute(insert_orifices_sql, (
                            orifice_name,
                            orifice_inlet,
                            orifice_outlet,
                            orifice_type,
                            orifice_crest_height,
                            orifice_disch_coeff,
                            orifice_flap_gate,
                            orifice_open_close_time,
                            orifice_shape,
                            orifice_height,
                            orifice_width,
                            geom
                            )
                        )
                self.uc.log_info(f"ORIFICES: {added_orifices} added and {updated_orifices} updated from imported SWMM INP file")

                if len(not_added) > 0:
                    self.uc.log_info(
                        f"ORIFICES: {len(not_added)} are outside the domain and not added to the project")

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            msg = "ERROR 310322.0853: creation of Storm Drain Orifices layer failed!\n\n" \
                  "Please check your SWMM input data.\n" \
                  f"{e}"
            self.uc.show_error(msg, e)
            self.uc.log_info(msg)
            QApplication.restoreOverrideCursor()

    def import_swmminp_pumps(self, swmminp_dict, delete_existing):
        """
        Function to import swmm inp pumps
        """
        try:
            not_added = []
            existing_pumps = []
            if delete_existing:
                self.gutils.clear_tables('user_swmm_pumps')
            else:
                existing_pumps_qry = self.gutils.execute("SELECT pump_name FROM user_swmm_pumps;").fetchall()
                existing_pumps = [pump[0] for pump in existing_pumps_qry]
            insert_pumps_sql = """INSERT INTO user_swmm_pumps (
                                    pump_name,
                                    pump_inlet, 
                                    pump_outlet, 
                                    pump_curve, 
                                    pump_init_status, 
                                    pump_startup_depth, 
                                    pump_shutoff_depth,
                                    geom
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);"""

            replace_user_swmm_pumps_sql = """UPDATE user_swmm_pumps
                             SET   pump_inlet  = ?,
                                   pump_outlet  = ?,
                                   pump_curve  = ?,
                                   pump_init_status  = ?,
                                   pump_startup_depth  = ?,
                                   pump_shutoff_depth  = ?
                             WHERE pump_name = ?;"""

            pumps_data = swmminp_dict.get('PUMPS', [])
            coordinates_data = swmminp_dict.get('COORDINATES', [])
            coordinates_dict = {item[0]: item[1:] for item in coordinates_data}
            vertices_data = swmminp_dict.get('VERTICES', [])

            if len(pumps_data) > 0:
                added_pumps = 0
                updated_pumps = 0
                for pump in pumps_data:
                    """
                    [PUMPS]
                    ;;               Inlet            Outlet           Pump             Init.  Startup  Shutoff 
                    ;;Name           Node             Node             Curve            Status Depth    Depth   
                    ;;-------------- ---------------- ---------------- ---------------- ------ -------- --------
                    CPump            Ids1             Cistern1         P1               OFF    3.00     40.00   
                    """

                    # SWMM Variables
                    pump_name = pump[0]
                    pump_inlet = pump[1]
                    pump_outlet = pump[2]
                    pump_curve = pump[3]
                    pump_init_status = pump[4]
                    pump_startup_depth = pump[5]
                    pump_shutoff_depth = pump[6]

                    # QGIS Variables
                    linestring_list = []
                    inlet_x = coordinates_dict[pump_inlet][0]
                    inlet_y = coordinates_dict[pump_inlet][1]
                    inlet_grid = self.grid_on_point(inlet_x, inlet_y)

                    linestring_list.append((inlet_x, inlet_y))

                    for vertice in vertices_data:
                        if vertice[0] == pump_name:
                            linestring_list.append((vertice[1], vertice[2]))

                    outlet_x = coordinates_dict[pump_outlet][0]
                    outlet_y = coordinates_dict[pump_outlet][1]
                    outlet_grid = self.grid_on_point(outlet_x, outlet_y)

                    linestring_list.append((outlet_x, outlet_y))

                    # Both ends of the pump is outside the grid
                    if not inlet_grid and not outlet_grid:
                        not_added.append(pump_name)
                        continue

                    # Pump inlet is outside the grid, and it is an Inlet
                    if not inlet_grid and pump_inlet.lower().startswith("i"):
                        not_added.append(pump_name)
                        continue

                    geom = "LINESTRING({})".format(", ".join("{0} {1}".format(x, y) for x, y in linestring_list))
                    geom = self.gutils.wkt_to_gpb(geom)

                    if pump_name in existing_pumps:
                        updated_pumps += 1
                        self.gutils.execute(
                            replace_user_swmm_pumps_sql,
                            (
                                pump_inlet,
                                pump_outlet,
                                pump_curve,
                                pump_init_status,
                                pump_startup_depth,
                                pump_shutoff_depth,
                                pump_name,
                            ),
                        )
                    else:
                        added_pumps += 1
                        self.gutils.execute(insert_pumps_sql, (
                            pump_name,
                            pump_inlet,
                            pump_outlet,
                            pump_curve,
                            pump_init_status,
                            pump_startup_depth,
                            pump_shutoff_depth,
                            geom
                        )
                        )
                self.uc.log_info(f"PUMPS: {added_pumps} added and {updated_pumps} updated from imported SWMM INP file")

                if len(not_added) > 0:
                    self.uc.log_info(
                        f"PUMPS: {len(not_added)} are outside the domain and not added to the project")

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            msg = "ERROR 050618.1805: creation of Storm Drain Pumps layer failed!\n\n" \
                  "Please check your SWMM input data.\n" \
                  f"{e}"
            self.uc.show_error(msg, e)
            self.uc.log_info(msg)
            QApplication.restoreOverrideCursor()

    def import_swmminp_conduits(self, swmminp_dict, delete_existing):
        """
        Function to import swmm inp conduits
        """
        try:
            existing_conduits = []
            not_added = []
            if delete_existing:
                self.gutils.clear_tables('user_swmm_conduits')
            else:
                existing_conduits_qry = self.gutils.execute("SELECT conduit_name FROM user_swmm_conduits;").fetchall()
                existing_conduits = [conduit[0] for conduit in existing_conduits_qry]

            insert_conduits_sql = """INSERT INTO user_swmm_conduits (
                                       conduit_name,
                                       conduit_inlet,
                                       conduit_outlet,
                                       conduit_length,
                                       conduit_manning,
                                       conduit_inlet_offset,
                                       conduit_outlet_offset,
                                       conduit_init_flow,
                                       conduit_max_flow,
                                       losses_inlet,
                                       losses_outlet,
                                       losses_average,
                                       losses_flapgate,
                                       xsections_shape,
                                       xsections_barrels,
                                       xsections_max_depth,
                                       xsections_geom2,
                                       xsections_geom3,
                                       xsections_geom4,
                                       geom
                                       )
                                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);"""

            replace_user_swmm_conduits_sql = """UPDATE user_swmm_conduits
                             SET   conduit_inlet  = ?,
                                   conduit_outlet  = ?,
                                   conduit_length  = ?,
                                   conduit_manning  = ?,
                                   conduit_inlet_offset  = ?,
                                   conduit_outlet_offset  = ?,
                                   conduit_init_flow  = ?,
                                   conduit_max_flow  = ?,
                                   losses_inlet  = ?,
                                   losses_outlet  = ?,
                                   losses_average  = ?,
                                   losses_flapgate  = ?,
                                   xsections_shape  = ?,
                                   xsections_barrels  = ?,
                                   xsections_max_depth  = ?,
                                   xsections_geom2  = ?,
                                   xsections_geom3  = ?,
                                   xsections_geom4  = ?
                             WHERE conduit_name = ?;"""

            conduits_data = swmminp_dict.get('CONDUITS', [])
            losses_data = swmminp_dict.get('LOSSES', [])
            losses_dict = {item[0]: item[1:] for item in losses_data}
            xsections_data = swmminp_dict.get('XSECTIONS', [])
            xsections_dict = {item[0]: item[1:] for item in xsections_data}
            coordinates_data = swmminp_dict.get('COORDINATES', [])
            coordinates_dict = {item[0]: item[1:] for item in coordinates_data}
            vertices_data = swmminp_dict.get('VERTICES', [])

            if len(conduits_data) > 0:
                updated_conduits = 0
                added_conduits = 0
                for conduit in conduits_data:
                    """
                    ;;               Inlet            Outlet                      Manning    Inlet      Outlet     Init.      Max.      
                    ;;Name           Node             Node             Length     N          Offset     Offset     Flow       Flow      
                    ;;-------------- ---------------- ---------------- ---------- ---------- ---------- ---------- ---------- ----------
                    """
                    # SWMM Variables
                    conduit_name = conduit[0]
                    conduit_inlet = conduit[1]
                    conduit_outlet = conduit[2]
                    conduit_length = conduit[3]
                    conduit_manning = conduit[4]
                    conduit_inlet_offset = conduit[5]
                    conduit_outlet_offset = conduit[6]
                    conduit_init_flow = conduit[7]
                    conduit_max_flow = conduit[8]

                    """
                    [LOSSES]
                    ;;Link           Inlet      Outlet     Average    Flap Gate 
                    ;;-------------- ---------- ---------- ---------- ----------
                    DS2-1            0.0        0.0        0.00       NO
                    """
                    losses_inlet = losses_dict[conduit_name][0]
                    losses_outlet = losses_dict[conduit_name][1]
                    losses_average = losses_dict[conduit_name][2]
                    losses_flapgate = 'True' if losses_dict[conduit_name][3] == 'YES' else 'False'

                    """
                    [XSECTIONS]
                    ;;Link           Shape        Geom1            Geom2      Geom3      Geom4      Barrels   
                    ;;-------------- ------------ ---------------- ---------- ---------- ---------- ----------
                    DS2-1            CIRCULAR     1.00             0.00       0.000      0.00       1             
                    """
                    xsections_shape = xsections_dict[conduit_name][0]
                    xsections_barrels = xsections_dict[conduit_name][5]
                    xsections_max_depth = xsections_dict[conduit_name][1]
                    xsections_geom2 = xsections_dict[conduit_name][2]
                    xsections_geom3 = xsections_dict[conduit_name][3]
                    xsections_geom4 = xsections_dict[conduit_name][4]

                    # QGIS Variables
                    linestring_list = []
                    inlet_x = coordinates_dict[conduit_inlet][0]
                    inlet_y = coordinates_dict[conduit_inlet][1]
                    inlet_grid = self.gutils.grid_on_point(inlet_x, inlet_y)

                    linestring_list.append((inlet_x, inlet_y))

                    for vertice in vertices_data:
                        if vertice[0] == conduit_name:
                            linestring_list.append((vertice[1], vertice[2]))

                    outlet_x = coordinates_dict[conduit_outlet][0]
                    outlet_y = coordinates_dict[conduit_outlet][1]
                    outlet_grid = self.gutils.grid_on_point(outlet_x, outlet_y)

                    linestring_list.append((outlet_x, outlet_y))

                    # Both ends of the conduit is outside the grid
                    if not inlet_grid and not outlet_grid:
                        not_added.append(conduit_name)
                        continue

                    # Conduit inlet is outside the grid, and it is an Inlet
                    if not inlet_grid and conduit_inlet.lower().startswith("i"):
                        not_added.append(conduit_name)
                        continue

                    geom = "LINESTRING({})".format(", ".join("{0} {1}".format(x, y) for x, y in linestring_list))
                    geom = self.gutils.wkt_to_gpb(geom)

                    if conduit_name in existing_conduits:
                        updated_conduits += 1
                        self.gutils.execute(
                            replace_user_swmm_conduits_sql,
                            (
                                conduit_inlet,
                                conduit_outlet,
                                conduit_length,
                                conduit_manning,
                                conduit_inlet_offset,
                                conduit_outlet_offset,
                                conduit_init_flow,
                                conduit_max_flow,
                                losses_inlet,
                                losses_outlet,
                                losses_average,
                                losses_flapgate,
                                xsections_shape,
                                xsections_barrels,
                                xsections_max_depth,
                                xsections_geom2,
                                xsections_geom3,
                                xsections_geom4,
                                conduit_name,
                            ),
                        )

                    else:
                        added_conduits += 1
                        self.gutils.execute(insert_conduits_sql, (
                            conduit_name,
                            conduit_inlet,
                            conduit_outlet,
                            conduit_length,
                            conduit_manning,
                            conduit_inlet_offset,
                            conduit_outlet_offset,
                            conduit_init_flow,
                            conduit_max_flow,
                            losses_inlet,
                            losses_outlet,
                            losses_average,
                            losses_flapgate,
                            xsections_shape,
                            xsections_barrels,
                            xsections_max_depth,
                            xsections_geom2,
                            xsections_geom3,
                            xsections_geom4,
                            geom
                        )
                        )
                self.uc.log_info(f"CONDUITS: {added_conduits} added and {updated_conduits} updated from imported SWMM INP file")

                if len(not_added) > 0:
                    self.uc.log_info(
                        f"CONDUITS: {len(not_added)} are outside the domain and not added to the project")

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            msg = "ERROR 050618.1804: creation of Storm Drain Conduits layer failed!\n\n" \
                  "Please check your SWMM input data.\n" \
                  f"{e}"
            self.uc.show_error(msg, e)
            self.uc.log_info(msg)
            QApplication.restoreOverrideCursor()

    def import_swmminp_storage_units(self, swmminp_dict, delete_existing):
        """
        Function to import swmm inp storage units
        """
        try:
            existing_storages = []
            if delete_existing:
                self.gutils.clear_tables('user_swmm_storage_units')
            else:
                existing_storages_qry = self.gutils.execute("SELECT name FROM user_swmm_storage_units;").fetchall()
                existing_storages = [storage[0] for storage in existing_storages_qry]

            insert_storage_units_sql = """
                                    INSERT INTO user_swmm_storage_units (
                                        name, 
                                        grid,
                                        invert_elev,
                                        max_depth,
                                        init_depth,
                                        external_inflow,
                                        treatment,
                                        ponded_area,
                                        evap_factor,
                                        infiltration,
                                        infil_method,
                                        suction_head,
                                        conductivity,
                                        initial_deficit,
                                        storage_curve,
                                        coefficient,
                                        exponent,
                                        constant,
                                        curve_name,
                                        geom
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);"""

            replace_user_swmm_storage_sql = """UPDATE user_swmm_storage_units
                                         SET    geom = ?,
                                                "invert_elev" = ?,
                                                "max_depth" = ?,
                                                "init_depth" = ?,
                                                "external_inflow" = ?,
                                                "treatment" = ?,
                                                "ponded_area" = ?,
                                                "evap_factor" = ?,
                                                "infiltration" = ?,
                                                "infil_method" = ?,
                                                "suction_head" = ?,
                                                "conductivity" = ?,
                                                "initial_deficit" = ?,
                                                "storage_curve" = ?,
                                                "coefficient" = ?,
                                                "exponent" = ?,
                                                "constant" = ?,
                                                "curve_name" = ?                             
                                         WHERE name = ?;"""

            storage_units_data = swmminp_dict.get('STORAGE', [])
            coordinates_data = swmminp_dict.get('COORDINATES', [])
            coordinates_dict = {item[0]: item[1:] for item in coordinates_data}
            inflows_data = swmminp_dict.get('INFLOWS', [])
            external_inflows = [external_inflow_name[0] for external_inflow_name in inflows_data]

            if len(storage_units_data) > 0:
                added_storages = 0
                updated_storages = 0
                for storage_unit in storage_units_data:
                    """
                    [STORAGE]
                    ;;               Invert   Max.     Init.    Storage    Curve                      Ponded   Evap.   
                    ;;Name           Elev.    Depth    Depth    Curve      Params                     Area     Frac.    Infiltration Parameters
                    ;;-------------- -------- -------- -------- ---------- -------- -------- -------- -------- -------- -----------------------
                    Cistern1         1385     9        0        TABULAR    Storage1                   0        0       
                    Cistern2         1385     9        0        TABULAR    Storage1                   0        0        50       60       70      
                    Cistern3         1385     9        0        FUNCTIONAL 1000     100      10       0        0       
                    """

                    # SWMM VARIABLES
                    name = storage_unit[0]
                    invert_elev = storage_unit[1]
                    max_depth = storage_unit[2]
                    init_depth = storage_unit[3]
                    storage_curve = storage_unit[4]
                    if storage_curve == 'FUNCTIONAL':
                        coefficient = storage_unit[5]
                        exponent = storage_unit[6]
                        constant = storage_unit[7]
                        evap_factor = storage_unit[9]
                        curve_name = '*'
                    else:
                        coefficient = 1000
                        exponent = 0
                        constant = 0
                        curve_name = storage_unit[5]
                        evap_factor = storage_unit[7]
                    infiltration = 'YES' if len(storage_unit) == 13 or len(storage_unit) == 11 else 'NO'
                    infil_method = 'GREEN_AMPT'
                    if len(storage_unit) == 13:
                        suction_head = storage_unit[10]
                        conductivity = storage_unit[11]
                        initial_deficit = storage_unit[12]
                    elif len(storage_unit) == 11:
                        suction_head = storage_unit[8]
                        conductivity = storage_unit[9]
                        initial_deficit = storage_unit[10]
                    else:
                        suction_head = 0
                        conductivity = 0
                        initial_deficit = 0
                    external_inflow = 'YES' if name in external_inflows else 'NO'
                    treatment = 'NO'
                    ponded_area = 0

                    # QGIS VARIABLES
                    x = float(coordinates_dict[name][0])
                    y = float(coordinates_dict[name][1])

                    grid_n = self.gutils.grid_on_point(x, y)
                    grid = -9999 if grid_n is None else grid_n
                    geom = "POINT({0} {1})".format(x, y)
                    geom = self.gutils.wkt_to_gpb(geom)

                    if name in existing_storages:
                        updated_storages += 1
                        self.gutils.execute(
                            replace_user_swmm_storage_sql,
                            (
                                geom,
                                invert_elev,
                                max_depth,
                                init_depth,
                                external_inflow,
                                treatment,
                                ponded_area,
                                evap_factor,
                                infiltration,
                                infil_method,
                                suction_head,
                                conductivity,
                                initial_deficit,
                                storage_curve,
                                coefficient,
                                exponent,
                                constant,
                                curve_name,
                                name,
                            ),
                        )
                    else:
                        added_storages += 1
                        self.gutils.execute(insert_storage_units_sql, (
                            name,
                            grid,
                            invert_elev,
                            max_depth,
                            init_depth,
                            external_inflow,
                            treatment,
                            ponded_area,
                            evap_factor,
                            infiltration,
                            infil_method,
                            suction_head,
                            conductivity,
                            initial_deficit,
                            storage_curve,
                            coefficient,
                            exponent,
                            constant,
                            curve_name,
                            geom
                        )
                        )

                self.uc.log_info(f"STORAGES: {added_storages} added and {updated_storages} updated from imported SWMM INP file")

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            msg = "ERROR 300124.1109: Creating Storm Drain Storage Units layer failed!\n\n" \
                  "Please check your SWMM input data.\nAre the nodes coordinates inside the computational domain?\n" \
                  f"{e}"
            self.uc.show_error(msg, e)
            self.uc.log_info(msg)
            QApplication.restoreOverrideCursor()

    def import_swmminp_outfalls(self, swmminp_dict, delete_existing):
        """
        Function to import swmm inp outfalls
        """
        try:
            existing_outfalls = []
            if delete_existing:
                self.gutils.clear_tables('user_swmm_outlets')
            else:
                existing_outfalls_qry = self.gutils.execute("SELECT name FROM user_swmm_outlets;").fetchall()
                existing_outfalls = [outfall[0] for outfall in existing_outfalls_qry]

            insert_outfalls_sql = """
                        INSERT INTO user_swmm_outlets (
                            grid,
                            name,
                            outfall_invert_elev,
                            flapgate, 
                            swmm_allow_discharge,
                            outfall_type,
                            tidal_curve,
                            time_series,  
                            fixed_stage,
                            geom
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);"""

            replace_user_swmm_outlets_sql = """UPDATE user_swmm_outlets
                                     SET    geom = ?,
                                            outfall_type = ?, 
                                            outfall_invert_elev = ?, 
                                            swmm_allow_discharge = ?,
                                            tidal_curve = ?, 
                                            time_series = ?,
                                            fixed_stage = ?,
                                            flapgate = ?
                                     WHERE name = ?;"""

            outfalls_data = swmminp_dict.get('OUTFALLS', [])
            coordinates_data = swmminp_dict.get('COORDINATES', [])
            coordinates_dict = {item[0]: item[1:] for item in coordinates_data}

            if len(outfalls_data) > 0:
                added_outfalls = 0
                updated_outfalls = 0
                for outfall in outfalls_data:
                    """
                    [OUTFALLS]
                    ;;               Invert     Outfall    Stage/Table      Tide
                    ;;Name           Elev.      Type       Time Series      Gate
                    ;;-------------- ---------- ---------- ---------------- ----
                    O-35-31-23       1397.16    FREE                        NO
                    """

                    # SWMM VARIABLES
                    name = outfall[0]
                    outfall_invert_elev = outfall[1]
                    outfall_type = outfall[2]
                    if len(outfall) == 5:
                        flapgate = "True" if outfall[4] == "YES" else "False"
                        tidal_curve = outfall[3] if outfall_type == "TIDAL" else '*'
                        time_series = outfall[3] if outfall_type == "TIMESERIES" else '*'
                        fixed_stage = outfall[3] if outfall_type == "FIXED" else '*'
                    else:
                        flapgate = "True" if outfall[3] == "YES" else "False"
                        tidal_curve = '*'
                        time_series = '*'
                        fixed_stage = '*'

                    # QGIS VARIABLES
                    x = coordinates_dict[name][0]
                    y = coordinates_dict[name][1]
                    grid_n = self.gutils.grid_on_point(x, y)
                    grid = -9999 if grid_n is None else grid_n
                    geom = "POINT({0} {1})".format(x, y)
                    geom = self.gutils.wkt_to_gpb(geom)

                    # FLO-2D VARIABLES
                    swmm_allow_discharge = 0

                    if name in existing_outfalls:
                        updated_outfalls += 1
                        self.gutils.execute(
                            replace_user_swmm_outlets_sql,
                            (
                                geom,
                                outfall_type,
                                outfall_invert_elev,
                                swmm_allow_discharge,
                                tidal_curve,
                                time_series,
                                fixed_stage,
                                flapgate,
                                name,
                            ),
                        )
                    else:
                        added_outfalls += 1
                        self.gutils.execute(insert_outfalls_sql, (
                            grid,
                            name,
                            outfall_invert_elev,
                            flapgate,
                            swmm_allow_discharge,
                            outfall_type,
                            tidal_curve,
                            time_series,
                            fixed_stage,
                            geom
                        )
                        )

                self.uc.log_info(f"OUTFALLS: {added_outfalls} added and {updated_outfalls} updated from imported SWMM INP file")

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            msg = "ERROR 060319.1610: Creating Storm Drain Outfalls layer failed!\n\n" \
                  "Please check your SWMM input data.\nAre the nodes coordinates inside the computational domain?\n" \
                  f"{e}"
            self.uc.show_error(msg, e)
            self.uc.log_info(msg)
            QApplication.restoreOverrideCursor()

    def import_swmminp_inlets_junctions(self, swmminp_dict, delete_existing):
        """
        Function to import swmm inp inlets junctions
        """
        try:
            existing_inlets_junctions = []
            if delete_existing:
                self.gutils.clear_tables('user_swmm_inlets_junctions')
            else:
                existing_inlets_junctions_qry = self.gutils.execute("SELECT name FROM user_swmm_inlets_junctions;").fetchall()
                existing_inlets_junctions = [inlet_junction[0] for inlet_junction in existing_inlets_junctions_qry]

            insert_inlets_junctions_sql = """
                                        INSERT INTO user_swmm_inlets_junctions (
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
                                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);"""

            replace_user_swmm_inlets_junctions_sql = """UPDATE user_swmm_inlets_junctions
                                     SET    geom = ?,
                                            sd_type = ?,
                                            external_inflow = ?,
                                            junction_invert_elev = ?,
                                            max_depth = ?,
                                            init_depth = ?,
                                            surcharge_depth = ?,
                                            intype = ?,
                                            swmm_length = ?,
                                            swmm_width = ?,
                                            swmm_height = ?,
                                            swmm_coeff = ?,
                                            swmm_feature = ?,
                                            curbheight = ?,
                                            swmm_clogging_factor = ?,
                                            swmm_time_for_clogging = ?,
                                            drboxarea = ?
                                     WHERE name = ?;"""

            inlets_junctions_data = swmminp_dict.get('JUNCTIONS', [])
            coordinates_data = swmminp_dict.get('COORDINATES', [])
            coordinates_dict = {item[0]: item[1:] for item in coordinates_data}
            inflows_data = swmminp_dict.get('INFLOWS', [])
            external_inflows_inlet_junctions = [external_inflow_name[0] for external_inflow_name in inflows_data]

            if len(inlets_junctions_data) > 0:
                added_inlets_junctions = 0
                updated_inlets_junctions = 0
                for inlet_junction in inlets_junctions_data:
                    """
                    ;;               Invert     Max.       Init.      Surcharge  Ponded
                    ;;Name           Elev.      Depth      Depth      Depth      Area
                    ;;-------------- ---------- ---------- ---------- ---------- ----------
                    I1-35-31-18      1399.43    15.00      0.00       0.00       0.00
                    I1-35-32-54      1399.43    15.00      0.00       0.00       0.00
                    """

                    # SWMM VARIABLES
                    name = inlet_junction[0]
                    junction_invert_elev = float(inlet_junction[1])
                    max_depth = float(inlet_junction[2])
                    init_depth = float(inlet_junction[3])
                    surcharge_depth = float(inlet_junction[4])
                    external_inflow = 1 if name in external_inflows_inlet_junctions else 0

                    # QGIS VARIABLES
                    x = coordinates_dict[name][0]
                    y = coordinates_dict[name][1]
                    grid_n = self.gutils.grid_on_point(x, y)
                    grid = -9999 if grid_n is None else grid_n
                    geom = "POINT({0} {1})".format(x, y)
                    geom = self.gutils.wkt_to_gpb(geom)

                    # FLO-2D VARIABLES -> Updated later when other files are imported
                    sd_type = 'I' if name.lower().startswith("i") else 'J'
                    intype = 0
                    swmm_length = 0
                    swmm_width = 0
                    swmm_height = 0
                    swmm_coeff = 0
                    swmm_feature = 0
                    curbheight = 0
                    swmm_clogging_factor = 0
                    swmm_time_for_clogging = 0
                    drboxarea = 0

                    if name in existing_inlets_junctions:
                        updated_inlets_junctions += 1
                        self.gutils.execute(replace_user_swmm_inlets_junctions_sql, (
                            geom,
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
                            name
                        )
                        )

                    else:
                        added_inlets_junctions += 1
                        self.gutils.execute(insert_inlets_junctions_sql, (
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
                        )

                self.uc.log_info(f"JUNCTIONS: {added_inlets_junctions} added and {updated_inlets_junctions} updated from imported SWMM INP file")

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            msg = "ERROR 060319.1610: Creating Storm Drain Inlets/Junctions layer failed!\n\n" \
                  "Please check your SWMM input data.\nAre the nodes coordinates inside the computational domain?\n" \
                  f"{e}"
            self.uc.show_error(msg, e)
            self.uc.log_info(msg)
            QApplication.restoreOverrideCursor()

    def import_swmminp_curves(self, swmminp_dict, delete_existing):
        """
        Function to import swmm inp curves (pump, tidal, and other)
        """
        try:
            existing_curves = []
            if delete_existing:
                self.gutils.clear_tables('swmm_pumps_curve_data')
                self.gutils.clear_tables('swmm_tidal_curve')
                self.gutils.clear_tables('swmm_tidal_curve_data')
                self.gutils.clear_tables('swmm_other_curves')
            else:
                existing_pump_curves_qry = self.gutils.execute("SELECT DISTINCT pump_curve_name FROM swmm_pumps_curve_data;").fetchall()
                existing_pump_curves = [pump_curve[0] for pump_curve in existing_pump_curves_qry]
                existing_tidal_curves_qry = self.gutils.execute("SELECT DISTINCT tidal_curve_name FROM swmm_tidal_curve;").fetchall()
                existing_tidal_curves = [tidal_curve[0] for tidal_curve in existing_tidal_curves_qry]
                existing_other_curves_qry = self.gutils.execute("SELECT DISTINCT name FROM swmm_other_curves;").fetchall()
                existing_other_curves = [other_curve[0] for other_curve in existing_other_curves_qry]
                existing_curves = existing_pump_curves + existing_tidal_curves + existing_other_curves

            insert_pump_curves_sql = """INSERT INTO swmm_pumps_curve_data
                                                        (   pump_curve_name, 
                                                            pump_curve_type, 
                                                            x_value,
                                                            y_value,
                                                            description
                                                        ) 
                                                        VALUES (?, ?, ?, ?, ?);"""

            replace_pump_curves_sql = """UPDATE swmm_pumps_curve_data
                                                        SET pump_curve_type = ?,
                                                            x_value = ?,
                                                            y_value = ?
                                                        WHERE
                                                            pump_curve_name = ?;"""

            insert_tidal_curves_sql = """INSERT OR REPLACE INTO swmm_tidal_curve
                                                        (   tidal_curve_name, 
                                                            tidal_curve_description
                                                        ) 
                                                        VALUES (?, ?);"""

            insert_tidal_curves_data_sql = """INSERT INTO swmm_tidal_curve_data
                                                        (   tidal_curve_name, 
                                                            hour, 
                                                            stage
                                                        ) 
                                                        VALUES (?, ?, ?);"""

            replace_tidal_curves_data_sql = """UPDATE swmm_tidal_curve_data
                                                        SET hour = ?, 
                                                            stage = ?
                                                        WHERE
                                                            tidal_curve_name = ?;"""

            insert_other_curves_sql = """INSERT INTO swmm_other_curves
                                                        (   name, 
                                                            type, 
                                                            description,
                                                            x_value,
                                                            y_value
                                                        ) 
                                                        VALUES (?, ?, ?, ?, ?);"""

            replace_other_curves_sql = """UPDATE swmm_other_curves
                                                        SET type = ?,
                                                            x_value = ?,
                                                            y_value = ?
                                                        WHERE
                                                            name = ?;"""

            curves_data = swmminp_dict.get('CURVES', [])

            # Initialize the dictionaries for each group
            groups = {
                'Pump': {},
                'Tidal': {},
                'Other': {}
            }

            current_key = None
            current_group_type = None
            extra_column = None
            data_added = False  # Flag to track if data was added to the current group
            current_group_data = []  # Initialize before entering the loop

            if len(curves_data) > 0:
                for curve in curves_data:
                    if len(curve) == 4:  # New set (defining the type and the key)
                        # Only store the current group if data was added
                        if current_key is not None and data_added:
                            groups[current_group_type][current_key] = current_group_data

                        # Now, handle the new group definition
                        current_key = curve[0]
                        if 'Pump' in curve[1]:  # Pump group
                            current_group_type = 'Pump'
                            extra_column = curve[1]  # Use the entire Pump name (e.g., 'Pump4')
                        elif 'Tidal' in curve[1]:  # Tidal group
                            current_group_type = 'Tidal'
                            extra_column = curve[1]  # Use the entire Tidal name (e.g., 'Tidal')
                        else:  # Other group
                            current_group_type = 'Other'
                            extra_column = curve[1]  # Use the entire name (e.g., 'Storage')

                        # Start a new group
                        current_group_data = [[curve[0], curve[2], curve[3], extra_column]]  # Reset the list for the new group
                        data_added = False  # Reset the flag for the new group
                    else:
                        # Add subsequent rows to the current group data
                        if extra_column is not None:
                            # Append the suffix (Pump name, Tidal name, or Storage name) as a new column
                            curve.append(extra_column)

                        current_group_data.append(curve)
                        data_added = True  # Mark that data has been added

                # After the loop, ensure the last group is stored if it has data
                if current_key is not None and data_added:
                    groups[current_group_type][current_key] = current_group_data

                added_pumps_curves = 0
                updated_pumps_curves = 0
                for key, values in groups['Pump'].items():
                    if key in existing_curves:
                        updated_pumps_curves += 1
                        for value in values:
                            self.gutils.execute(replace_pump_curves_sql,
                                                (value[3][-1], value[1], value[2], value[0]))
                    else:
                        added_pumps_curves += 1
                        for value in values:
                            self.gutils.execute(insert_pump_curves_sql, (value[0], value[3][-1], value[1], value[2], ''))
                self.uc.log_info(f"CURVES (pumps): {added_pumps_curves} added and {updated_pumps_curves} updated from imported SWMM INP file")

                added_tidal_curves = 0
                updated_tidal_curves = 0
                for key, values in groups['Tidal'].items():
                    if key in existing_curves:
                        updated_tidal_curves += 1
                        for value in values:
                            self.gutils.execute(replace_tidal_curves_data_sql, (value[1], value[2], value[0]))
                    else:
                        added_tidal_curves += 1
                        for value in values:
                            self.gutils.execute(insert_tidal_curves_sql, (value[0], ''))
                            self.gutils.execute(insert_tidal_curves_data_sql, (value[0], value[1], value[2]))
                self.uc.log_info(f"CURVES (tidal): {added_tidal_curves} added and {updated_tidal_curves} updated from imported SWMM INP file")

                added_other_curves = 0
                updated_other_curves = 0
                for key, values in groups['Other'].items():
                    if key in existing_curves:
                        updated_other_curves += 1
                        for value in values:
                            self.gutils.execute(replace_other_curves_sql, (value[3], value[1], value[2], value[0]))
                    else:
                        added_other_curves += 1
                        for value in values:
                            self.gutils.execute(insert_other_curves_sql, (value[0], value[3], '', value[1], value[2]))
                self.uc.log_info(f"CURVES (other): {added_other_curves} added and {updated_other_curves} updated from imported SWMM INP file")

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            msg = "ERROR 241121.0547: Reading storm drain curve data from SWMM input data failed!\n" \
                  "__________________________________________________\n" \
                  f"{e}"
            self.uc.show_error(msg, e)
            self.uc.log_info(msg)
            QApplication.restoreOverrideCursor()

    def import_swmminp_ts(self, swmminp_dict, delete_existing):
        """
        Function to import swmm inp time series
        """
        try:
            existing_time_series = []
            if delete_existing:
                self.gutils.clear_tables('swmm_time_series')
                self.gutils.clear_tables('swmm_time_series_data')
            else:
                existing_time_series_qry = self.gutils.execute("SELECT DISTINCT time_series_name FROM swmm_time_series;").fetchall()
                existing_time_series = [time_series[0] for time_series in existing_time_series_qry]
            insert_times_from_file_sql = """INSERT INTO swmm_time_series 
                                    (   time_series_name, 
                                        time_series_description, 
                                        time_series_file,
                                        time_series_data
                                    ) 
                                    VALUES (?, ?, ?, ?);"""

            replace_times_from_file_sql = """UPDATE swmm_time_series 
                                                SET                                        
                                                    time_series_file = ?,
                                                    time_series_data = ?
                                                WHERE 
                                                    time_series_name = ?;"""

            insert_times_from_data_sql = """INSERT INTO swmm_time_series_data
                                    (   time_series_name, 
                                        date, 
                                        time,
                                        value
                                    ) 
                                    VALUES (?, ?, ?, ?);"""

            replace_times_from_data_sql = """UPDATE swmm_time_series_data 
                                                SET                                        
                                                    date = ?,
                                                    time = ?,
                                                    value = ?
                                                WHERE 
                                                    time_series_name = ?;"""

            time_series_data_data = swmminp_dict.get('TIMESERIES', [])
            if len(time_series_data_data) > 0:
                updated_time_series = 0
                added_time_series = 0

                time_series_names = self.gutils.execute("SELECT DISTINCT time_series_name FROM swmm_time_series;").fetchall()
                for time_series_name in time_series_names:
                    if time_series_name[0] in existing_time_series:
                        updated_time_series += 1

                for time_series in time_series_data_data:
                    if time_series[1] == "FILE":
                        name = time_series[0]
                        description = ""
                        file = time_series[2]
                        file2 = file.replace('"', "")
                        if name in existing_time_series:
                            self.gutils.execute(replace_times_from_file_sql, (file2.strip(), "False", name))
                        else:
                            added_time_series += 1
                            self.gutils.execute(insert_times_from_file_sql, (name, description, file2.strip(), "False"))
                    else:
                        # See if time series data reference is already in table:
                        row = self.gutils.execute(
                            "SELECT * FROM swmm_time_series WHERE time_series_name = ?;", (time_series[0],)
                        ).fetchone()
                        if not row:
                            name = time_series[0]
                            description = ""
                            file = ""
                            file2 = file.replace('"', "")
                            if name in existing_time_series:
                                self.gutils.execute(replace_times_from_file_sql, (file2.strip(), "True", name))
                            else:
                                added_time_series += 1
                                self.gutils.execute(insert_times_from_file_sql, (name, description, file2.strip(), "True"))

                        name = time_series[0]
                        date = time_series[1]
                        tme = time_series[2]
                        value = float_or_zero(time_series[3])

                        if name in existing_time_series:
                            self.gutils.execute(replace_times_from_data_sql, (date, tme, value, name))
                        else:
                            self.gutils.execute(insert_times_from_data_sql, (name, date, tme, value))

                self.uc.log_info(
                    f"TIMESERIES: {added_time_series} added and {updated_time_series} updated from imported SWMM INP file")

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            msg = "ERROR 020219.0812:  Reading storm drain time series from SWMM input data failed!\n" \
                  "__________________________________________________\n" \
                  f"{e}"
            self.uc.show_error(msg, e)
            self.uc.log_info(msg)
            QApplication.restoreOverrideCursor()

    def import_swmminp_inflows(self, swmminp_dict, delete_existing):
        """
        Function to import swmm inp inflows
        """
        try:
            existing_inflows = []
            if delete_existing:
                self.gutils.clear_tables('swmm_inflows')
            else:
                existing_inflows_qry = self.gutils.execute("SELECT DISTINCT node_name FROM swmm_inflows;").fetchall()
                existing_inflows = [inflow[0] for inflow in existing_inflows_qry]

            insert_inflows_sql = """INSERT INTO swmm_inflows 
                                            (   node_name, 
                                                constituent, 
                                                baseline, 
                                                pattern_name, 
                                                time_series_name, 
                                                scale_factor
                                            ) 
                                            VALUES (?, ?, ?, ?, ?, ?);"""

            replace_inflows_sql = """UPDATE swmm_inflows 
                                            SET 
                                                constituent = ?,
                                                baseline = ?,
                                                pattern_name = ?,
                                                time_series_name = ?,
                                                scale_factor = ?
                                            WHERE node_name = ?;"""

            inflows_data = swmminp_dict.get('INFLOWS', [])

            if len(inflows_data) > 0:
                added_inflows = 0
                update_inflows = 0
                for inflow in inflows_data:
                    """
                    ;;                                                 Param    Units    Scale    Baseline Baseline
                    ;;Node           Parameter        Time Series      Type     Factor   Factor   Value    Pattern
                    ;;-------------- ---------------- ---------------- -------- -------- -------- -------- --------
                    J3-38-32-2       FLOW             ts_test          FLOW     1.0      3.5      12       pattern_test
                    """

                    name = inflow[0] if len(inflow) > 0 else ""
                    constituent = inflow[1] if len(inflow) > 1 else ""
                    time_series_name = inflow[2] if len(inflow) > 2 else ""
                    scale_factor = inflow[5] if len(inflow) > 5 else ""
                    baseline = inflow[6] if len(inflow) > 6 and inflow[6] is not None else ""
                    pattern_name = inflow[7] if len(inflow) > 7 and inflow[7] is not None else ""

                    if name in existing_inflows:
                        update_inflows += 1
                        self.gutils.execute(
                            replace_inflows_sql,
                            (constituent, baseline, pattern_name, time_series_name, scale_factor, name),
                        )
                    else:
                        added_inflows += 1
                        self.gutils.execute(
                            insert_inflows_sql,
                            (name, constituent, baseline, pattern_name, time_series_name, scale_factor),
                        )

                self.uc.log_info(
                    f"INFLOWS: {added_inflows} added and {update_inflows} updated from imported SWMM INP file")

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            msg = "ERROR 020219.0812: Reading storm drain inflows from SWMM input data failed!\n" \
                  "__________________________________________________\n" \
                  f"{e}"
            self.uc.show_error(msg, e)
            self.uc.log_info(msg)
            QApplication.restoreOverrideCursor()

    def import_swmminp_patterns(self, swmminp_dict, delete_existing):
        """
        Function to import swmm inp patterns
        """
        try:
            """
            [PATTERNS]
            ;;Name           Type       Multipliers
            ;;-------------- ---------- -----------
            ;description
            pattern_test     HOURLY     1.0   2     3     4     5     6    
            pattern_test                7     8     9     10    11    12   
            """
            existing_patterns = []
            if delete_existing:
                self.gutils.clear_tables('swmm_inflow_patterns')
            else:
                existing_patterns_qry = self.gutils.execute("SELECT DISTINCT pattern_name FROM swmm_inflow_patterns;").fetchall()
                existing_patterns = [pattern[0] for pattern in existing_patterns_qry]

            insert_patterns_sql = """INSERT INTO swmm_inflow_patterns
                                                                (   pattern_name, 
                                                                    pattern_description, 
                                                                    hour, 
                                                                    multiplier
                                                                ) 
                                                                VALUES (?, ?, ?, ?);"""

            replace_patterns_sql = """UPDATE swmm_inflow_patterns 
                                        SET
                                            hour = ?,
                                            multiplier = ?
                                        WHERE 
                                            pattern_name = ?;"""

            patterns_data = swmminp_dict.get('PATTERNS', [])

            if len(patterns_data) > 0:
                # Adjust the patterns by adding them into their own list
                merged_patterns = {}
                updated_patterns = 0
                added_patterns = 0
                # Step 1: Merge the patterns while skipping the element at index 1 only in the first occurrence
                for pattern in patterns_data:
                    name = pattern[0]

                    if name not in merged_patterns:
                        # For the first occurrence, skip the element at index 1
                        merged_patterns[name] = pattern[2:]
                    else:
                        # For subsequent occurrences, don't skip
                        merged_patterns[name].extend(pattern[1:])

                # Step 2: Convert to individual lists with a counter, resetting after 24
                add_results = []
                added_patterns = 0
                update_results = []
                updated_patterns = 0

                for name, data in merged_patterns.items():
                    if name in existing_patterns:
                        updated_patterns += 1
                        counter = 0  # Start the counter at 0
                        for value in data:
                            update_results.append([name, counter, value])
                            counter += 1
                            if counter > 24:  # Reset counter if greater than 24
                                counter = 0
                    else:
                        added_patterns += 1
                        counter = 0  # Start the counter at 0
                        for value in data:
                            add_results.append([name, counter, value])
                            counter += 1
                            if counter > 24:  # Reset counter if greater than 24
                                counter = 0

                for r in add_results:
                    self.gutils.execute(insert_patterns_sql, (r[0], "", r[1], r[2]))

                for r in update_results:
                    self.gutils.execute(replace_patterns_sql, (r[1], r[2], r[0]))

                self.uc.log_info(
                    f"PATTERNS: {added_patterns} added and {updated_patterns} updated from imported SWMM INP file")

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            msg = "ERROR 020219.0812: Reading storm drain patterns from SWMM input data failed!\n" \
                  "__________________________________________________\n" \
                  f"{e}"
            self.uc.show_error(msg, e)
            self.uc.log_info(msg)
            QApplication.restoreOverrideCursor()

    def import_swmmflo(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_swmmflo_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_swmmflo_hdf5()

    def import_swmmflo_dat(self):

        swmmflo_sql = [
            """INSERT INTO swmmflo (geom, swmmchar, swmm_jt, swmm_iden, intype, swmm_length,
                                               swmm_width, swmm_height, swmm_coeff, flapgate, curbheight, swmm_feature) VALUES""",
            12,
        ]

        self.clear_tables("swmmflo")
        data = self.parser.parse_swmmflo()
        gids = (x[1] for x in data)
        cells = self.grid_centroids(gids, buffers=True)
        for row in data:
            gid = row[1]
            geom = cells[gid]
            row.append(row[8])
            # Update the user_swmm_inlets_junctions if existing
            if not self.is_table_empty('user_swmm_inlets_junctions'):
                update_qry = (f"""UPDATE user_swmm_inlets_junctions
                                SET
                                intype = '{row[3]}',
                                swmm_length = '{row[4]}',
                                swmm_width = '{row[5]}',
                                swmm_height = '{row[6]}',
                                swmm_coeff = '{row[7]}',
                                curbheight = '{row[9]}',
                                swmm_feature = '{row[10]}'
                                WHERE name = '{row[2]}' AND grid = '{row[1]}';""")
                self.execute(update_qry)

            swmmflo_sql += [(geom,) + tuple(row)]

        self.batch_execute(swmmflo_sql)

    def import_swmmflo_hdf5(self):
        try:
            stormdrain_group = self.parser.read_groups("Input/Storm Drain")
            if stormdrain_group:
                stormdrain_group = stormdrain_group[0]

                swmmflo_sql = [
                    """INSERT INTO swmmflo (geom, fid, swmmchar, swmm_jt, swmm_iden, intype, swmm_length,
                                                       swmm_width, swmm_height, swmm_coeff, flapgate, curbheight, swmm_feature) VALUES""",
                    13,
                ]

                self.clear_tables("swmmflo")

                # Process SWMMFLO_DATA dataset
                if "SWMMFLO_DATA" in stormdrain_group.datasets:
                    data = stormdrain_group.datasets["SWMMFLO_DATA"].data
                    name = stormdrain_group.datasets["SWMMFLO_NAME"].data
                    node_id_to_name = {int(row[0]): row[1] for row in name}
                    grid_group = self.parser.read_groups("Input/Grid")[0]
                    x_list = grid_group.datasets["COORDINATES"].data[:, 0]
                    y_list = grid_group.datasets["COORDINATES"].data[:, 1]
                    for row in data:
                        node_id, swmm_jt, intype, swmm_length, swmm_width, swmm_height, swmm_coeff, feature, curbheight = row
                        swmm_ident = node_id_to_name.get(int(node_id), None)
                        if isinstance(swmm_ident, bytes):
                            swmm_ident = swmm_ident.decode("utf-8")
                        geom = self.build_point_xy(x_list[int(swmm_jt) - 1], y_list[int(swmm_jt) - 1])
                        swmm_char = "D"
                        swmmflo_sql += [(geom, int(node_id), swmm_char, int(swmm_jt), swmm_ident, intype, swmm_length, swmm_width, swmm_height, swmm_coeff, 0, curbheight, feature)]

                if swmmflo_sql:
                    self.batch_execute(swmmflo_sql)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR: Importing SWMMFLO data from HDF5 failed!", e)
            self.uc.log_info("ERROR: Importing SWMMFLO data from HDF5 failed!")

    def import_swmmflodropbox(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_swmmflodropbox_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_swmmflodropbox_hdf5()

    def import_swmmflodropbox_dat(self):
        """
        Function to import the SWMMFLODROPBOX.DAT
        """
        data = self.parser.parse_swmmflodropbox()
        for row in data:
            name = row[0]
            area = row[2]
            self.execute(f"UPDATE user_swmm_inlets_junctions SET drboxarea = '{area}' WHERE name = '{name}'")

    def import_swmmflodropbox_hdf5(self):
        """
        Function to import the SWMMFLODROPBOX.DAT
        """
        try:
            stormdrain_group = self.parser.read_groups("Input/Storm Drain")
            if stormdrain_group:
                stormdrain_group = stormdrain_group[0]

                # Process SWMMFLODROPBOX dataset
                if "SWMMFLODROPBOX" in stormdrain_group.datasets:
                    data = stormdrain_group.datasets["SWMMFLODROPBOX"].data
                    name = stormdrain_group.datasets["SWMMFLO_NAME"].data
                    node_id_to_name = {int(row[0]): row[1] for row in name}
                    for row in data:
                        node_id, swmmdropbox = row
                        name = node_id_to_name.get(int(node_id), None)
                        if isinstance(name, bytes):
                            name = name.decode("utf-8")
                        self.execute(f"UPDATE user_swmm_inlets_junctions SET drboxarea = '{swmmdropbox}' WHERE name = '{name}'")

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("Importing SWMMFLODROPBOX data from HDF5 failed!", e)
            self.uc.log_info("Importing SWMMFLODROPBOX data from HDF5 failed!")

    def import_sdclogging(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_sdclogging_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_sdclogging_hdf5()

    def import_sdclogging_dat(self):
        """
        Function to import the SDCLOGGING.DAT
        """
        data = self.parser.parse_sdclogging()
        for row in data:
            name = row[2]
            clog_fact = row[3]
            clog_time = row[4]
            self.execute(f"""UPDATE user_swmm_inlets_junctions
                                   SET swmm_clogging_factor = '{clog_fact}', swmm_time_for_clogging = '{clog_time}'
                                   WHERE name = '{name}'""")

    def import_sdclogging_hdf5(self):
        """
        Function to import the SDCLOGGING from hdf5 file
        """
        try:
            stormdrain_group = self.parser.read_groups("Input/Storm Drain")
            if stormdrain_group:
                stormdrain_group = stormdrain_group[0]

                # Process SDCLOGGING dataset
                if "SDCLOGGING" in stormdrain_group.datasets:
                    data = stormdrain_group.datasets["SDCLOGGING"].data
                    name = stormdrain_group.datasets["SWMMFLO_NAME"].data
                    node_id_to_name = {int(row[0]): row[1] for row in name}
                    for row in data:
                        node_id, swmm_clogfac, clogtime = row
                        name = node_id_to_name.get(int(node_id), None)
                        if isinstance(name, bytes):
                            name = name.decode("utf-8")
                        self.execute(f"""UPDATE user_swmm_inlets_junctions
                                               SET swmm_clogging_factor = '{swmm_clogfac}', swmm_time_for_clogging = '{clogtime}'
                                               WHERE name = '{name}'""")

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("Importing SDCLOGGING data from HDF5 failed!", e)
            self.uc.log_info("Importing SDCLOGGING data from HDF5 failed!")

    def import_swmmflort(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_swmmflort_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_swmmflort_hdf5()

    def import_swmmflort_dat(self):
        """
        Reads SWMMFLORT.DAT (Rating Tables).

        Reads rating tables from SWMMFLORT.DAT and fills data of QGIS tables swmmflort and swmmflort_data.

        """
        try:
            # swmmflort_sql = ["""INSERT INTO swmmflort (grid_fid, name) VALUES""", 2]

            swmmflort_rows = []
            rt_data_rows = []
            culvert_rows = []

            data = self.parser.parse_swmmflort()  # Reads SWMMFLORT.DAT.
            for i, row in enumerate(data, 1):
                if row[0] == "D" and len(row) == 3:  # old D line for Rating Table: D  7545
                    gid, params = row[1:]
                    name = "RatingTable{}".format(i)
                elif row[0] == "D" and len(row) == 4:  # D line for Rating Table: D  7545  I4-38
                    gid, inlet_name, params = row[1:]
                    name = inlet_name
                elif row[0] == "S":
                    try:
                        gid, inlet_name, cdiameter, params = row[1:]
                    except ValueError as e:
                        raise ValueError("Wrong Culvert Eq. definition in line 'S' of SWMMFLORT.DAT")
                        continue

                if row[0] == "D":  # Rating Table
                    swmmflort_rows.append((gid, name))

                    for j in range(1, len(params)):
                        rt_data_rows.append(((i,) + tuple(params[j])))

                elif row[0] == "S":  # Culvert Eq.
                    if gid in (None, "", 'None'):
                        pass
                    elif int(gid) < 1:
                        pass
                    else:
                        culvert_rows.append(
                            (
                                gid,
                                inlet_name,
                                cdiameter,
                                row[4][0][0],
                                row[4][0][1],
                                row[4][0][2],
                                row[4][0][3],
                            )
                        )

            if swmmflort_rows:
                self.clear_tables("swmmflort")
                self.con.executemany(
                    "INSERT INTO swmmflort (grid_fid, name) VALUES (?,?);",
                    swmmflort_rows,
                )
                # self.batch_execute(swmmflort_sql)

            if rt_data_rows:
                self.clear_tables("swmmflort_data")
                self.con.executemany(
                    "INSERT INTO swmmflort_data (swmm_rt_fid, depth, q) VALUES (?, ?, ?);",
                    rt_data_rows,
                )

            if culvert_rows:
                self.clear_tables("swmmflo_culvert")
                qry = """INSERT INTO swmmflo_culvert 
                        (grid_fid, name, cdiameter, typec, typeen, cubase, multbarrels) 
                        VALUES (?, ?, ?, ?, ?, ?, ?);"""
                self.con.executemany(qry, culvert_rows)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 150221.1535: importing SWMMFLORT.DAT failed!.\n", e)

    def import_swmmflort_hdf5(self):
        """
        Reads SWMMFLORT.DAT (Rating Tables).

        Reads rating tables from SWMMFLORT.DAT and fills data of QGIS tables swmmflort and swmmflort_data.

        """
        # try:
        stormdrain_group = self.parser.read_groups("Input/Storm Drain")
        if stormdrain_group:
            stormdrain_group = stormdrain_group[0]

            swmmflort_sql = [
                """INSERT OR REPLACE INTO swmmflort (fid, grid_fid, name) VALUES""",
                3,
            ]

            swmmflort_data_sql = [
                """INSERT INTO swmmflort_data (swmm_rt_fid, depth, q) VALUES""",
                3,
            ]

            swmmflo_culvert_sql = [
                """INSERT INTO swmmflo_culvert (grid_fid, name, cdiameter, typec, typeen, cubase, multbarrels) VALUES""",
                7,
            ]

            self.clear_tables("swmmflort", "swmmflort_data", "swmmflo_culvert")

            # Process RATING_TABLE dataset
            if "RATING_TABLE" in stormdrain_group.datasets:
                data = stormdrain_group.datasets["RATING_TABLE"].data
                grid = stormdrain_group.datasets["SWMMFLO_DATA"].data
                node_id_to_grid = {int(row[0]): row[1] for row in grid}
                name = stormdrain_group.datasets["SWMMFLO_NAME"].data
                node_id_to_name = {int(row[0]): row[1] for row in name}
                for i, row in enumerate(data, start=1):
                    node_id, depth, q = row
                    grid_fid = node_id_to_grid.get(int(node_id), None)
                    rt_name = node_id_to_name.get(int(node_id), None)
                    if isinstance(rt_name, bytes):
                        rt_name = rt_name.decode("utf-8")
                    swmmflort_sql += [(int(node_id), int(grid_fid), rt_name)]
                    swmmflort_data_sql += [(int(node_id), depth, q)]

            if "CULVERT_EQUATIONS" in stormdrain_group.datasets:
                data = stormdrain_group.datasets["CULVERT_EQUATIONS"].data
                grid = stormdrain_group.datasets["SWMMFLO_DATA"].data
                node_id_to_grid = {int(row[0]): row[1] for row in grid}
                name = stormdrain_group.datasets["SWMMFLO_NAME"].data
                node_id_to_name = {int(row[0]): row[1] for row in name}
                for row in data:
                    node_id, cdiameter, typec, typeen, cubase, multbarrels = row
                    grid_fid = node_id_to_grid.get(int(node_id), None)
                    culvert_name = node_id_to_name.get(int(node_id), None)
                    if isinstance(culvert_name, bytes):
                        culvert_name = culvert_name.decode("utf-8")
                    swmmflo_culvert_sql += [(int(grid_fid), culvert_name, cdiameter, int(typec), int(typeen), cubase, int(multbarrels))]

            if swmmflort_sql:
                self.batch_execute(swmmflort_sql)

            if swmmflort_data_sql:
                self.batch_execute(swmmflort_data_sql)

            if swmmflo_culvert_sql:
                self.batch_execute(swmmflo_culvert_sql)

        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error("Importing SWMMFLORT from hdf5 failed!.\n", e)
        #     self.uc.show_error("Importing SWMMFLORT from hdf5 failed!")

    def import_swmmoutf(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_swmmoutf_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_swmmoutf_hdf5()

    def import_swmmoutf_dat(self):
        swmmoutf_sql = [
            """INSERT INTO swmmoutf (geom, name, grid_fid, outf_flo) VALUES""",
            4,
        ]

        self.clear_tables("swmmoutf")
        data = self.parser.parse_swmmoutf()
        gids = []
        # Outfall outside the grid -> Don't look for the grid centroid
        for x in data:
            if x[1] != '-9999':
                gids.append(x[1])
        cells = self.grid_centroids(gids, buffers=True)
        have_outside = False
        for row in data:
            outfall_name = row[0]
            gid = row[1]
            allow_q = row[2]
            # Update the swmm_allow_discharge on the user_swmm_outlets
            self.execute(f"UPDATE user_swmm_outlets SET swmm_allow_discharge = {allow_q} WHERE name = '{outfall_name}';")
            # Outfall outside the grid -> Add exactly over the Storm Drain Outfalls
            if gid == '-9999':
                have_outside = True
                geom_qry = self.execute(f"SELECT geom FROM user_swmm_outlets WHERE name = '{outfall_name}'").fetchone()
                if geom_qry:
                    geom = geom_qry[0]
                else:  # When there is no SWMM.INP
                    self.uc.log_info(f"{outfall_name} outside the grid!")
                    continue
            else:
                geom = cells[gid]
            swmmoutf_sql += [(geom,) + tuple(row)]

        self.batch_execute(swmmoutf_sql)

        if have_outside:
            self.uc.bar_warn(f"Some Outfalls are outside the grid! Check log messages for more information.")

    def import_swmmoutf_hdf5(self):
        try:
            stormdrain_group = self.parser.read_groups("Input/Storm Drain")
            if stormdrain_group:
                stormdrain_group = stormdrain_group[0]

                swmmoutf_sql = [
                    """INSERT INTO swmmoutf (geom, fid, name, grid_fid, outf_flo) VALUES""",
                    5,
                ]

                self.clear_tables("swmmoutf")

                if "SWMMOUTF_DATA" in stormdrain_group.datasets:
                    data = stormdrain_group.datasets["SWMMOUTF_DATA"].data
                    name = stormdrain_group.datasets["SWMMOUTF_NAME"].data
                    node_id_to_name = {int(row[0]): row[1] for row in name}
                    grid_group = self.parser.read_groups("Input/Grid")[0]
                    x_list = grid_group.datasets["COORDINATES"].data[:, 0]
                    y_list = grid_group.datasets["COORDINATES"].data[:, 1]
                    for row in data:
                        outfall_id, outf_grid, outf_flo2dvol = row
                        outf_name = node_id_to_name.get(int(outfall_id), None)
                        if isinstance(outf_name, bytes):
                            outf_name = outf_name.decode("utf-8")
                        geom = self.build_point_xy(x_list[int(outf_grid) - 1], y_list[int(outf_grid) - 1])
                        swmmoutf_sql += [(geom, int(outfall_id), outf_name, int(outf_grid), int(outf_flo2dvol))]

                if swmmoutf_sql:
                    self.batch_execute(swmmoutf_sql)


                # data = self.parser.parse_swmmoutf()
                # gids = []
                # # Outfall outside the grid -> Don't look for the grid centroid
                # for x in data:
                #     if x[1] != '-9999':
                #         gids.append(x[1])
                # cells = self.grid_centroids(gids, buffers=True)
                # have_outside = False
                # for row in data:
                #     outfall_name = row[0]
                #     gid = row[1]
                #     allow_q = row[2]
                #     # Update the swmm_allow_discharge on the user_swmm_outlets
                #     self.execute(f"UPDATE user_swmm_outlets SET swmm_allow_discharge = {allow_q} WHERE name = '{outfall_name}';")
                #     # Outfall outside the grid -> Add exactly over the Storm Drain Outfalls
                #     if gid == '-9999':
                #         have_outside = True
                #         geom_qry = self.execute(f"SELECT geom FROM user_swmm_outlets WHERE name = '{outfall_name}'").fetchone()
                #         if geom_qry:
                #             geom = geom_qry[0]
                #         else:  # When there is no SWMM.INP
                #             self.uc.log_info(f"{outfall_name} outside the grid!")
                #             continue
                #     else:
                #         geom = cells[gid]
                #     swmmoutf_sql += [(geom,) + tuple(row)]
                #
                # self.batch_execute(swmmoutf_sql)
                #
                # if have_outside:
                #     self.uc.bar_warn(f"Some Outfalls are outside the grid! Check log messages for more information.")

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR: Importing SWMMOUTF data from HDF5 failed!", e)
            self.uc.log_info("ERROR: Importing SWMMOUTF data from HDF5 failed!")

    def import_tolspatial(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_tolspatial_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_tolspatial_hdf5()

    def import_tolspatial_dat(self):
        tolspatial_sql = ["""INSERT INTO tolspatial (geom, tol) VALUES""", 2]
        cells_sql = ["""INSERT INTO tolspatial_cells (area_fid, grid_fid) VALUES""", 2]

        self.clear_tables("tolspatial", "tolspatial_cells")
        data = self.parser.parse_tolspatial()
        gids = (x[0] for x in data)
        cells = self.grid_centroids(gids)
        for i, row in enumerate(data, 1):
            gid, tol = row
            geom = self.build_square(cells[gid], self.shrink)
            tolspatial_sql += [(geom, tol)]
            cells_sql += [(i, gid)]

        self.batch_execute(tolspatial_sql, cells_sql)

    def import_tolspatial_hdf5(self):
        tolspatial_sql = ["""INSERT INTO tolspatial (geom, tol) VALUES""", 2]
        cells_sql = ["""INSERT INTO tolspatial_cells (area_fid, grid_fid) VALUES""", 2]

        self.clear_tables("tolspatial", "tolspatial_cells")

        try:
            # Access the TOLSPATIAL dataset
            spatially_variable_group = self.parser.read_groups("Input/Spatially Variable")
            if spatially_variable_group:
                spatially_variable_group = spatially_variable_group[0]
                if "TOLSPATIAL" in spatially_variable_group.datasets:
                    tolspatial_data = spatially_variable_group.datasets["TOLSPATIAL"].data

                    # Process each row in the dataset
                    gids = set()
                    for i, row in enumerate(tolspatial_data, 1):
                        gid, tol = row
                        gids.add(gid)
                        geom = self.build_square(self.grid_centroids([gid])[gid], self.cell_size)
                        tolspatial_sql += [(geom, tol)]
                        cells_sql += [(i, gid)]

                    self.batch_execute(tolspatial_sql, cells_sql)
                    return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info("ERROR: Importing TOLSPATIAL from HDF5 failed!")
            self.uc.show_error("ERROR: Importing TOLSPATIAL from HDF5 failed!", e)
            return False

    def import_shallowNSpatial(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_shallowNSpatial_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_shallowNSpatial_hdf5()

    def import_shallowNSpatial_dat(self):
        shallowNSpatial_sql = ["""INSERT INTO spatialshallow (geom, shallow_n) VALUES""", 2]
        cells_sql = ["""INSERT INTO spatialshallow_cells (area_fid, grid_fid) VALUES""", 2]

        self.clear_tables("spatialshallow", "spatialshallow_cells")
        data = self.parser.parse_shallowNSpatial()
        gids = (x[0] for x in data)
        cells = self.grid_centroids(gids)
        for i, row in enumerate(data, 1):
            gid, shallow_n = row
            geom = self.build_square(cells[gid], self.shrink)
            shallowNSpatial_sql += [(geom, shallow_n)]
            cells_sql += [(i, gid)]

        self.batch_execute(shallowNSpatial_sql, cells_sql)

    def import_shallowNSpatial_hdf5(self):
        try:
            shallowNSpatial_group = self.parser.read_groups("Input/Spatially Variable")
            if shallowNSpatial_group:
                shallowNSpatial_group = shallowNSpatial_group[0]

                shallowNSpatial_sql = ["""INSERT INTO spatialshallow (geom, shallow_n) VALUES""", 2]
                cells_sql = ["""INSERT INTO spatialshallow_cells (area_fid, grid_fid) VALUES""", 2]

                self.clear_tables("spatialshallow", "spatialshallow_cells")

                # Process SHALLOWN_SPATIAL dataset
                if "SHALLOWN_SPATIAL" in shallowNSpatial_group.datasets:
                    data = shallowNSpatial_group.datasets["SHALLOWN_SPATIAL"].data
                    for i, row in enumerate(data, start=1):
                        grid, shallowNSpatial = row
                        geom = self.build_square(self.grid_centroids([int(grid)])[int(grid)], self.cell_size)
                        shallowNSpatial_sql += [(geom, shallowNSpatial)]
                        cells_sql += [(i, int(grid))]

                if shallowNSpatial_sql:
                    self.batch_execute(shallowNSpatial_sql)

                if cells_sql:
                    self.batch_execute(cells_sql)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR: Importing SHALLOWN_SPATIAL data from HDF5 failed!", e)
            self.uc.log_info("ERROR: Importing SHALLOWN_SPATIAL data from HDF5 failed!")

    def import_wsurf(self):
        wsurf_sql = ["""INSERT INTO wsurf (geom, grid_fid, wselev) VALUES""", 3]

        self.clear_tables("wsurf")
        dummy, data = self.parser.parse_wsurf()
        gids = (x[0] for x in data)
        cells = self.grid_centroids(gids, buffers=True)
        for row in data:
            gid = row[0]
            geom = cells[gid]
            wsurf_sql += [(geom,) + tuple(row)]

        self.batch_execute(wsurf_sql)

    def import_wstime(self):
        wstime_sql = [
            """INSERT INTO wstime (geom, grid_fid, wselev, wstime) VALUES""",
            4,
        ]

        self.clear_tables("wstime")
        dummy, data = self.parser.parse_wstime()
        gids = (x[0] for x in data)
        cells = self.grid_centroids(gids, buffers=True)
        for row in data:
            gid = row[0]
            geom = cells[gid]
            wstime_sql += [(geom,) + tuple(row)]

        self.batch_execute(wstime_sql)

    def export_cont_toler(self, output=None, subdomain=None):
        """subdomain: Placeholder parameter for compatibility with other code logic."""
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_cont_toler_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_cont_toler_hdf5()

    def export_cont_toler_hdf5(self):
        try:
            cont_group = self.parser.control_group
            qgis_group = self.parser.qgis_group

            cont_variables = [
                "SIMUL",
                "TOUT",
                "LGPLOT",
                "METRIC",
                "IBACKUP",
                "ICHANNEL",
                "MSTREET",
                "LEVEE",
                "IWRFS",
                "IMULTC",
                "IRAIN",
                "INFIL",
                "IEVAP",
                "MUD",
                "ISED",
                "IMODFLOW",
                "SWMM",
                "IHYDRSTRUCT",
                "IFLOODWAY",
                "IDEBRV",
                "AMANN",
                "DEPTHDUR",
                "XCONC",
                "XARF",
                "FROUDL",
                "SHALLOWN",
                "ENCROACH",
                "NOPRTFP",
                "DEPRESSDEPTH",
                "NOPRTC",
                "ITIMTEP",
                "TIMTEP",
                "STARTIMTEP",
                "ENDTIMTEP",
                "GRAPTIM",
            ]

            tol_variables = [
                "TOLGLOBAL",
                "DEPTOL",
                "COURANTFP",
                "COURANTC",
                "COURANTST",
                "TIME_ACCEL"
            ]

            cont_group.create_dataset('CONT', [])
            for var in cont_variables:
                sql = f"""SELECT value FROM cont WHERE name = '{var}';"""
                value = self.execute(sql).fetchone()
                if value and value[0] is not None:
                    cont_group.datasets["CONT"].data.append(float(value[0]))
                else:
                    cont_group.datasets["CONT"].data.append(-9999)

            cont_group.create_dataset('TOLER', [])
            for var in tol_variables:
                sql = f"""SELECT value FROM cont WHERE name = '{var}';"""
                value = self.execute(sql).fetchone()
                if value and value[0] is not None:
                    cont_group.datasets["TOLER"].data.append(float(value[0]))
                else:
                    cont_group.datasets["TOLER"].data.append(-9999)

            qgis_group.create_dataset('INFO', [])

            info_data = [
                ["CONTACT", self.gutils.get_metadata_par("CONTACT") or ""],
                ["EMAIL", self.gutils.get_metadata_par("EMAIL") or ""],
                ["COMPANY", self.gutils.get_metadata_par("COMPANY") or ""],
                ["PHONE", self.gutils.get_metadata_par("PHONE") or ""],
                ["PROJ_NAME", self.gutils.get_metadata_par("PROJ_NAME") or ""],
                ["PLUGIN_V", self.gutils.get_metadata_par("PLUGIN_V") or ""],
                ["QGIS_V", self.gutils.get_metadata_par("QGIS_V") or ""],
                ["FLO-2D_V", self.gutils.get_metadata_par("FLO-2D_V") or ""],
                ["CRS", self.gutils.get_metadata_par("CRS") or ""],
            ]

            for data in info_data:
                qgis_group.datasets["INFO"].data.append([data[0], data[1]])

            self.parser.write_groups(cont_group, qgis_group)
            return True
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("Exporting Control data to HDF5 file failed!.\n", e)
            self.uc.log_info("Exporting Control data to HDF5 file failed!.\n")
            return False

    def export_cont_toler_dat(self, outdir):
        try:
            parser = ParseDAT()
            sql = """SELECT name, value FROM cont;"""
            options = {o: v if v is not None else "" for o, v in self.execute(sql).fetchall()}
            if options["IFLOODWAY"] == "0":
                del options["ENCROACH"]
            if options["ICHANNEL"] == "0":
                del options["NOPRTC"]
                del options["COURANTC"]
            if options["LGPLOT"] != "2":
                del options["GRAPTIM"]
            if options["LGPLOT"] == "2":
                options["IDEPLT"] = "0"
            if options["MSTREET"] == "0":
                del options["COURANTST"]
            if "IDEPLT" not in options:
                options["IDEPLT"] = "0"

            first_gid = self.execute("""SELECT grid_fid FROM inflow_cells ORDER BY fid LIMIT 1;""").fetchone()
            first_gid = first_gid[0] if first_gid is not None else 0

            if options["LGPLOT"] == "0":
                options["IDEPLT"] = "0"
                self.set_cont_par("IDEPLT", 0)
            elif options["IDEPLT"] == "0" and first_gid > 0:
                options["IDEPLT"] = first_gid
                self.set_cont_par("IDEPLT", first_gid)
            # elif options["IRAIN"] != "0":
            #     # Levee LGPLOT and IDEPLT
            #     pass
            # else:
            #     options["LGPLOT"] = 0
            #     options["IDEPLT"] = 0
            #     self.set_cont_par("LGPLOT", 0)
            #     self.set_cont_par("IDEPLT", 0)

            cont = os.path.join(outdir, "CONT.DAT")
            toler = os.path.join(outdir, "TOLER.DAT")
            rline = " {0}"
            with open(cont, "w") as c:
                for row in parser.cont_rows:
                    lst = ""
                    for o in row:
                        if o not in options:
                            continue
                        val = options[o]
                        lst += rline.format(val)
                    lst += "\n"
                    if lst.isspace() is False:
                        if row[0] == "ITIMTEP":
                            # See if CONT table has ENDTIMTEP and STARTIMTEP:
                            endtimtep = self.get_cont_par("ENDTIMTEP")
                            if not endtimtep:
                                self.set_cont_par("ENDTIMTEP", 0.0)

                            starttimtep = self.get_cont_par("STARTIMTEP")
                            if not starttimtep:
                                self.set_cont_par("STARTIMTEP", 0.0)

                            # options = {o: v if v is not None else "" for o, v in self.execute(sql).fetchall()}

                            if options["ITIMTEP"] != "0" and float_or_zero(options["ENDTIMTEP"]) > 0.0:
                                _itimtep = ("11", "21", "31", "41", "51")[int(float(options["ITIMTEP"])) - 1]
                                if (
                                        float_or_zero(options["STARTIMTEP"]) == 0.0
                                        and float_or_zero(options["ENDTIMTEP"]) == 0.0
                                ):
                                    lst = " " + _itimtep + " " + options["TIMTEP"]
                                else:
                                    lst = (
                                            " "
                                            + _itimtep
                                            + " "
                                            + options["TIMTEP"]
                                            + " "
                                            + options["STARTIMTEP"]
                                            + " "
                                            + options["ENDTIMTEP"]
                                    )
                            else:
                                lst = " " + options["ITIMTEP"] + " " + options["TIMTEP"]
                            lst += "\n"
                        c.write(lst)
                    else:
                        pass

            with open(toler, "w") as t:
                for row in parser.toler_rows:
                    lst = ""
                    for o in row:
                        if o not in options:
                            continue
                        val = options[o]
                        lst += rline.format(val)  # Second line 'C' (Courant values) writes 1, 2, or 3 values depending
                        # if channels and/or streets are simulated
                    lst += "\n"
                    if lst.isspace() is False:
                        t.write(lst)
                    else:
                        pass
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1535: exporting CONT.DAT or TOLER.DAT failed!.\n", e)
            return False

    def export_steep_slopen(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_steep_slopen_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_steep_slopen_hdf5(subdomain)

    def export_steep_slopen_dat(self, outdir, subdomain):
        try:

            if self.is_table_empty("steep_slope_n_cells"):
                return False

            steep_slopen = os.path.join(outdir, "STEEP_SLOPEN.DAT")

            # Check if there are global steep slope areas
            qry = """SELECT COUNT(*) FROM steep_slope_n_cells WHERE global = 1;"""
            result = self.gutils.execute(qry).fetchone()

            with open(steep_slopen, "w") as s:
                if result and result[0] > 0:
                    # Write global steep slope value
                    s.write("1\n")
                else:
                    # Write individual steep slope grid IDs
                    if not subdomain:
                        sql = """SELECT grid_fid FROM steep_slope_n_cells ORDER BY fid;"""
                    else:
                        # Write individual steep slope grid IDs
                        sql = f"""SELECT 
                                    md.domain_cell
                                FROM 
                                    steep_slope_n_cells AS ss
                                JOIN 
                                    schema_md_cells md ON ss.grid_fid = md.grid_fid
                                WHERE 
                                    md.domain_fid =  {subdomain}
                                ;"""
                    records = self.gutils.execute(sql).fetchall()
                    if records:
                        s.write("2\n")
                        for row in records:
                            grid_fid = row[0]  # Unpack the first value
                            s.write(f"{grid_fid}\n")

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.bar_error("ERROR: exporting STEEP_SLOPEN.DAT failed!")
            self.uc.log_info("ERROR: exporting STEEP_SLOPEN.DAT failed!\n")
            QApplication.setOverrideCursor(Qt.WaitCursor)
            return False

    def export_steep_slopen_hdf5(self, subdomain):
        try:

            if self.is_table_empty("steep_slope_n_cells"):
                return False

            spatially_variable_group = self.parser.spatially_variable_group

            # Check if there are global steep slope areas
            qry = """SELECT COUNT(*) FROM steep_slope_n_cells WHERE global = 1;"""
            result = self.gutils.execute(qry).fetchone()

            if result and result[0] > 0:
                # Write global steep slope value
                try:
                    spatially_variable_group.datasets["STEEP_SLOPEN_GLOBAL"].data.append(1)
                except:
                    spatially_variable_group.create_dataset('STEEP_SLOPEN_GLOBAL', [])
                    spatially_variable_group.datasets["STEEP_SLOPEN_GLOBAL"].data.append(1)
            else:
                # Write individual steep slope grid IDs
                try:
                    spatially_variable_group.datasets["STEEP_SLOPEN_GLOBAL"].data.append(2)
                except:
                    spatially_variable_group.create_dataset('STEEP_SLOPEN_GLOBAL', [])
                    spatially_variable_group.datasets["STEEP_SLOPEN_GLOBAL"].data.append(2)
                if not subdomain:
                    sql = """SELECT grid_fid FROM steep_slope_n_cells ORDER BY fid;"""
                else:
                    # Write individual steep slope grid IDs
                    sql = f"""SELECT 
                                md.domain_cell
                            FROM 
                                steep_slope_n_cells AS ss
                            JOIN 
                                schema_md_cells md ON ss.grid_fid = md.grid_fid
                            WHERE 
                                md.domain_fid =  {subdomain}
                            ;"""
                records = self.gutils.execute(sql).fetchall()
                if records:
                    for row in records:
                        grid_fid = row[0]  # Unpack the first value
                        try:
                            spatially_variable_group.datasets["STEEP_SLOPEN"].data.append(grid_fid)
                        except:
                            spatially_variable_group.create_dataset('STEEP_SLOPEN', [])
                            spatially_variable_group.datasets["STEEP_SLOPEN"].data.append(grid_fid)

            self.parser.write_groups(spatially_variable_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.bar_error("ERROR: exporting STEEP_SLOPEN to hdf5 failed!")
            self.uc.log_info("ERROR: exporting STEEP_SLOPEN to hdf5 failed!\n")
            QApplication.setOverrideCursor(Qt.WaitCursor)
            return False

    def export_lid_volume(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_lid_volume_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_lid_volume_hdf5(subdomain)

    def export_lid_volume_dat(self, outdir, subdomain):
        try:
            if self.is_table_empty("lid_volume_cells"):
                return False

            lid_volume = os.path.join(outdir, "LID_VOLUME.DAT")

            with open(lid_volume, "w") as lid:
                # Write individual lid volume grid IDs
                if not subdomain:
                    sql = """SELECT grid_fid, volume FROM lid_volume_cells ORDER BY fid;"""
                else:
                    sql = f"""SELECT 
                                md.domain_cell, 
                                volume 
                            FROM 
                                lid_volume_cells AS lv
                            JOIN 
                                schema_md_cells md ON lv.grid_fid = md.grid_fid
                            WHERE 
                                md.domain_fid = {subdomain};"""
                records = self.execute(sql)
                for row in records:
                    grid_fid = row[0]
                    volume = row[1]
                    lid.write(f"{grid_fid} {volume}\n")

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.bar_error("ERROR: exporting LID_VOLUME.DAT failed!")
            self.uc.log_info("ERROR: exporting LID_VOLUME.DAT failed!\n", e)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            return False

    def export_lid_volume_hdf5(self, subdomain):
        try:
            if self.is_table_empty("lid_volume_cells"):
                return False

            spatially_variable_group = self.parser.spatially_variable_group

            if not subdomain:
                sql = """SELECT grid_fid, volume FROM lid_volume_cells ORDER BY fid;"""
            else:
                sql = f"""SELECT 
                            md.domain_cell, 
                            volume 
                        FROM 
                            lid_volume_cells AS lv
                        JOIN 
                            schema_md_cells md ON lv.grid_fid = md.grid_fid
                        WHERE 
                            md.domain_fid = {subdomain};"""
            records = self.execute(sql)
            for row in records:
                grid_fid = row[0]
                volume = row[1]
                try:
                    spatially_variable_group.datasets["LID_VOLUME"].data.append([grid_fid, volume])
                except:
                    spatially_variable_group.create_dataset('LID_VOLUME', [])
                    spatially_variable_group.datasets["LID_VOLUME"].data.append([grid_fid, volume])

            self.parser.write_groups(spatially_variable_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.bar_error("ERROR: exporting LID_VOLUME to hdf5 failed!")
            self.uc.log_info("ERROR: exporting LID_VOLUME to hdf5 failed!\n", e)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            return False

    def export_mannings_n_topo(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_mannings_n_topo_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_mannings_n_topo_hdf5(subdomain)

    def export_mannings_n_topo_hdf5(self, subdomain):
        try:
            if not subdomain:
                sql = (
                    """SELECT fid, n_value, elevation, ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM grid ORDER BY fid;"""
                )
                records = self.execute(sql)
            else:
                sub_grid_cells = self.gutils.execute(f"""SELECT DISTINCT 
                                                            md.domain_cell, 
                                                            g.n_value, 
                                                            g.elevation,
                                                            ST_AsText(ST_Centroid(GeomFromGPB(g.geom)))
                                                         FROM 
                                                            grid g
                                                         JOIN 
                                                            schema_md_cells md ON g.fid = md.grid_fid
                                                         WHERE 
                                                             md.domain_fid = {subdomain};""").fetchall()

                records = sorted(sub_grid_cells, key=lambda x: x[0])

            nulls = 0
            grid_group = self.parser.grid_group
            coordinates_line = "{0} {1}"
            for row in records:
                fid, man, elev, geom = row
                if man is None or elev is None:
                    nulls += 1
                    if man is None:
                        man = 0.04
                    if elev is None:
                        elev = -9999
                x, y = [float(coord) for coord in geom.strip("POINT()").split()]
                grid_group.datasets["GRIDCODE"].data.append(fid)
                grid_group.datasets["MANNING"].data.append(man)
                grid_group.datasets["ELEVATION"].data.append(elev)
                grid_group.datasets["COORDINATES"].data.append(
                    create_array(coordinates_line, 2, np.float64, tuple([x, y])))
                # grid_group.datasets["X"].data.append(x)
                # grid_group.datasets["Y"].data.append(y)
            neighbors_line = "{0} {1} {2} {3} {4} {5} {6} {7}"
            for row in grid_compas_neighbors(self.gutils):
                grid_group.datasets["NEIGHBORS"].data.append(create_array(neighbors_line, 8, np.int_, tuple(row)))
            self.parser.write_groups(grid_group)
            if nulls > 0:
                QApplication.restoreOverrideCursor()
                self.uc.show_warn(
                    "WARNING 281122.0541: there are "
                    + str(nulls)
                    + " NULL values in the Grid layer's elevation or n_value fields.\n\n"
                    + "Default values where written to the exported files.\n\n"
                    + "Please check the source layer coverage or use Fill Nodata."
                )
                self.uc.log_info(
                    "WARNING 281122.0541: there are "
                    + str(nulls)
                    + " NULL values in the Grid layer's elevation or n_value fields.\n\n"
                    + "Default values where written to the exported files.\n\n"
                    + "Please check the source layer coverage or use Fill Nodata."
                )
                QApplication.setOverrideCursor(Qt.WaitCursor)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1541: exporting Grid data failed!.\n", e)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            return False

    def export_mannings_n_topo_dat(self, outdir, subdomain):
        try:
            if not subdomain:
                sql = (
                    """SELECT fid, n_value, elevation, ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM grid ORDER BY fid;"""
                )
                records = self.execute(sql)
            else:
                sub_grid_cells = self.gutils.execute(f"""SELECT DISTINCT 
                                                            md.domain_cell, 
                                                            g.n_value, 
                                                            g.elevation,
                                                            ST_AsText(ST_Centroid(GeomFromGPB(g.geom)))
                                                         FROM 
                                                            grid g
                                                         JOIN 
                                                            schema_md_cells md ON g.fid = md.grid_fid
                                                         WHERE 
                                                             md.domain_fid = {subdomain};""").fetchall()

                records = sorted(sub_grid_cells, key=lambda x: x[0])

            mannings = os.path.join(outdir, "MANNINGS_N.DAT")
            topo = os.path.join(outdir, "TOPO.DAT")

            mline = "{0: >10} {1: >10}\n"
            tline = "{0: >15} {1: >15} {2: >10}\n"

            nulls = 0

            with open(mannings, "w") as m, open(topo, "w") as t:
                for row in records:
                    fid, man, elev, geom = row
                    if man == None or elev == None:
                        nulls += 1
                        if man == None:
                            man = 0.04
                        if elev == None:
                            elev = -9999
                    x, y = geom.strip("POINT()").split()
                    m.write(mline.format(fid, "{0:.3f}".format(man)))
                    t.write(
                        tline.format(
                            "{0:.4f}".format(float(x)),
                            "{0:.4f}".format(float(y)),
                            "{0:.4f}".format(elev),
                        )
                    )

            if nulls > 0:
                QApplication.restoreOverrideCursor()
                self.uc.show_warn(
                    "WARNING 281122.0541: there are "
                    + str(nulls)
                    + " NULL values in the Grid layer's elevation or n_value fields.\n\n"
                    + "Default values where written to the exported files.\n\n"
                    + "Please check the source layer coverage or use Fill Nodata."
                )
                QApplication.setOverrideCursor(Qt.WaitCursor)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1541: exporting MANNINGS_N.DAT or TOPO.DAT failed!.\n", e)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            return False

    # def export_neighbours(self):
    #     if self.parsed_format == self.FORMAT_DAT:
    #         raise NotImplementedError("Exporting NEIGHBOURS.DAT is not supported!")
    #     elif self.parsed_format == self.FORMAT_HDF5:
    #         return self.export_neighbours_hdf5()
    #
    # def export_neighbours_hdf5(self):
    #     # try:
    #     grid_group = self.parser.grid_group
    #     neighbors_line = "{0} {1} {2} {3} {4} {5} {6} {7}"
    #     for row in grid_compas_neighbors(self.gutils):
    #         # self.uc.log_info(str(row))
    #         grid_group.datasets["NEIGHBORS"].data.append(create_array(neighbors_line, 8, np.float64, tuple(row)))
    #         # directions = ["N", "E", "S", "W", "NE", "SE", "SW", "NW"]
    #         # for direction, neighbor_gid in zip(directions, row):
    #         #     grid_group.datasets[direction].data.append(neighbor_gid)
    #     #self.parser.write_groups(grid_group)
    #     return True
    #     # except Exception as e:
    #     #     QApplication.restoreOverrideCursor()
    #     #     self.uc.show_error("ERROR: exporting grid neighbors data failed!.\n", e)
    #     #     QApplication.setOverrideCursor(Qt.WaitCursor)
    #     #     return False

    def export_inflow(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_inflow_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_inflow_hdf5(subdomain)

    def export_inflow_hdf5(self, subdomain):
        """
        Function to export inflow data to hdf5
        """
        if self.is_table_empty("inflow") and self.is_table_empty("reservoirs") and self.is_table_empty("tailing_reservoirs"):
            return False

        # Create the SQL queries
        cont_sql = """SELECT value FROM cont WHERE name = ?;"""
        inflow_sql = """SELECT fid, time_series_fid, ident, inoutfc FROM inflow WHERE fid = ?;"""
        ts_data_sql = (
            """SELECT series_fid, time, value, value2 FROM inflow_time_series_data WHERE series_fid = ? ORDER BY fid;"""
        )

        if not subdomain:
            inflow_cells_sql = """SELECT inflow_fid, grid_fid FROM inflow_cells ORDER BY inflow_fid, grid_fid;"""
        else:
            inflow_cells_sql = f"""
                                SELECT 
                                    ic.inflow_fid, 
                                    md.domain_cell 
                                FROM 
                                    inflow_cells AS ic
                                JOIN
                                    schema_md_cells md ON ic.grid_fid = md.grid_fid
                                WHERE 
                                    md.domain_fid = {subdomain}
                                ORDER BY ic.inflow_fid, md.domain_cell;
                                """

        four_values = "{0}  {1}  {2}  {3}"
        ts_series_fid = []

        # Create the INF_GLOBAL dataset
        ideplt = self.execute(cont_sql, ("IDEPLT",)).fetchone()
        # Adjust the ideplt grid number to the multi domain cell
        if subdomain:
            ideplt = self.execute(f"""
                                    SELECT
                                        md.domain_cell 
                                    FROM 
                                        schema_md_cells AS md
                                    JOIN 
                                        grid g ON g.fid = md.grid_fid
                                    WHERE 
                                        g.fid = {ideplt[0]} AND md.domain_fid = {subdomain}
                                    """).fetchone()
        if ideplt is None:
            if not subdomain:
                first_gid = self.execute("""SELECT grid_fid FROM inflow_cells ORDER BY fid LIMIT 1;""").fetchone()
            else:
                first_gid = self.execute(f"""SELECT 
                                                md.domain_cell 
                                            FROM 
                                                inflow_cells AS ic
                                            JOIN
                                                schema_md_cells md ON ic.grid_fid = md.grid_fid
                                            WHERE 
                                                md.domain_fid = {subdomain}
                                            ORDER BY ic.fid LIMIT 1;""").fetchone()
            ideplt = first_gid if first_gid is not None else (0,)

        if ideplt:
            ideplt = ideplt[0]

        ihourdaily = self.execute(cont_sql, ("IHOURDAILY",)).fetchone()
        if ihourdaily:
            ihourdaily = ihourdaily[0]
        else:
            ihourdaily = 0

        inflow_global = [float(ihourdaily), float(ideplt)]

        bc_group = self.parser.bc_group
        bc_group.create_dataset('Inflow/INF_GLOBAL', [])
        for data in inflow_global:
            bc_group.datasets["Inflow/INF_GLOBAL"].data.append(data)

        # Create the TS_INF_DATA dataset
        ts_fids = self.execute("SELECT DISTINCT time_series_fid FROM inflow;").fetchall()
        for (ts_fid,) in ts_fids:
            try:
                for tsd_row in self.execute(ts_data_sql, (ts_fid,)):
                    tsd_row = [x if (x is not None and x != "") else -9999 for x in tsd_row]
                    bc_group.datasets["Inflow/TS_INF_DATA"].data.append(
                        create_array(four_values, 4, np.float64, tuple(tsd_row)))
            except:
                bc_group.create_dataset('Inflow/TS_INF_DATA', [])
                for tsd_row in self.execute(ts_data_sql, (ts_fid,)):
                    tsd_row = [x if (x is not None and x != "") else -9999 for x in tsd_row]
                    bc_group.datasets["Inflow/TS_INF_DATA"].data.append(
                        create_array(four_values, 4, np.float64, tuple(tsd_row)))

            #     ts_series_fid.append(ts_fid)
            # ts_series_fid.append(ts_fid)

        max_ts_series_fid = self.execute("""SELECT MAX(series_fid) FROM inflow_time_series_data;""").fetchone()
        if max_ts_series_fid:
            max_ts_series_fid = max_ts_series_fid[0]

        # Divide inflow line hydrograph between grid elements
        has_line_hyd = self.execute("SELECT fid, time_series_fid FROM inflow WHERE geom_type = 'line';").fetchall()
        split_ts = {}
        if has_line_hyd:
            for (line_hyd, time_series_fid) in has_line_hyd:
                line_cells = self.execute(f"SELECT grid_fid FROM inflow_cells WHERE inflow_fid = '{line_hyd}';").fetchall()
                if subdomain:
                    subdomain_line_cells = self.execute(f"""
                    SELECT 
                        md.domain_cell 
                    FROM 
                        inflow_cells AS ic
                    JOIN
                        schema_md_cells md ON ic.grid_fid = md.grid_fid
                    WHERE 
                        inflow_fid = '{line_hyd}' AND md.domain_fid = {subdomain};
                    """).fetchall()
                    if len(subdomain_line_cells) == 0:
                        continue
                max_ts_series_fid += 1
                split_ts[line_hyd] = max_ts_series_fid
                for tsd_row in self.execute(ts_data_sql, (time_series_fid,)):
                    tsd_row = [x if (x is not None and x != "") else -9999 for x in tsd_row]
                    _, time, value, value2 = tsd_row
                    bc_group.datasets["Inflow/TS_INF_DATA"].data.append(
                        create_array(four_values, 4, np.float64, (split_ts[line_hyd] , time, round(value/len(line_cells), 2), value2)))

        previous_iid = -1
        row = None

        warning = ""

        if not self.is_table_empty("inflow"):
            for iid, gid in self.execute(inflow_cells_sql):
                if previous_iid != iid:
                    row = self.execute(inflow_sql, (iid,)).fetchone()
                    if row:
                        row = [x if x is not None and x != "" else 0 for x in row]
                        previous_iid = iid
                    else:
                        warning += (
                                "Data for inflow in cell "
                                + str(gid)
                                + " not found in 'Inflow' table (wrong inflow 'id' "
                                + str(iid)
                                + " in 'Inflow Cells' table).\n\n"
                        )
                        continue
                else:
                    pass

                fid, ts_fid, ident, inoutfc = row
                if ident == 'F':
                    try:
                        if fid in split_ts.keys():
                            ts_fid = split_ts[fid]
                        bc_group.datasets["Inflow/INF_GRID"].data.append(
                            create_array(four_values, 4, np.int_, (0, inoutfc, gid, ts_fid)))
                    except:
                        bc_group.create_dataset('Inflow/INF_GRID', [])
                        if fid in split_ts.keys():
                            ts_fid = split_ts[fid]
                        bc_group.datasets["Inflow/INF_GRID"].data.append(
                            create_array(four_values, 4, np.int_, (0, inoutfc, gid, ts_fid)))

                if ident == 'C':
                    try:
                        bc_group.datasets["Inflow/INF_GRID"].data.append(
                            create_array(four_values, 4, np.int_, (1, inoutfc, gid, ts_fid)))
                    except:
                        bc_group.create_dataset('Inflow/INF_GRID', [])
                        bc_group.datasets["Inflow/INF_GRID"].data.append(
                            create_array(four_values, 4, np.int_, (1, inoutfc, gid, ts_fid)))

        if not self.is_table_empty("tailing_reservoirs"):

            if not subdomain:
                schematic_tailings_reservoirs_sql = (
                    """SELECT grid_fid, wsel, n_value, tailings FROM tailing_reservoirs ORDER BY fid;"""
                )
            else:
                schematic_tailings_reservoirs_sql = f"""
                                        SELECT 
                                            md.domain_cell, 
                                            tr.wsel, 
                                            tr.n_value,
                                            tr.tailings
                                        FROM 
                                            tailing_reservoirs AS tr
                                        JOIN
                                            schema_md_cells md ON tr.grid_fid = md.grid_fid
                                        WHERE 
                                            md.domain_fid = {subdomain}
                                        ORDER BY tr.fid;"""

            for res in self.execute(schematic_tailings_reservoirs_sql):
                res = [x if (x is not None and x != "") else -9999 for x in res]
                try:
                    bc_group.datasets["Inflow/RESERVOIRS"].data.append(
                        create_array(four_values, 4, np.float64, tuple(res)))
                except:
                    bc_group.create_dataset('Inflow/RESERVOIRS', [])
                    bc_group.datasets["Inflow/RESERVOIRS"].data.append(
                        create_array(four_values, 4, np.float64, tuple(res)))

        if not self.is_table_empty("reservoirs"):

            if not subdomain:
                schematic_reservoirs_sql = (
                    """SELECT grid_fid, wsel, n_value, -9999 FROM reservoirs ORDER BY fid;"""
                )
            else:
                schematic_reservoirs_sql = f"""SELECT 
                                                    md.domain_cell, 
                                                    r.wsel, 
                                                    r.n_value,
                                                    -9999 AS tailings 
                                                FROM 
                                                    reservoirs AS r
                                                JOIN
                                                    schema_md_cells md ON r.grid_fid = md.grid_fid
                                                WHERE 
                                                    md.domain_fid = {subdomain}
                                                ORDER BY r.fid;"""

            for res in self.execute(schematic_reservoirs_sql):
                res = [x if (x is not None and x != "") else -9999 for x in res]
                try:
                    bc_group.datasets["Inflow/RESERVOIRS"].data.append(
                        create_array(four_values, 4, np.float64, tuple(res)))
                except:
                    bc_group.create_dataset('Inflow/RESERVOIRS', [])
                    bc_group.datasets["Inflow/RESERVOIRS"].data.append(
                        create_array(four_values, 4, np.float64, tuple(res)))

        self.parser.write_groups(bc_group)

        return True

    def export_inflow_dat(self, outdir, subdomain):
        # check if there are any inflows defined
        # try:
        if self.is_table_empty("inflow") and self.is_table_empty("reservoirs") and self.is_table_empty(
                "tailing_reservoirs"):
            return False
        cont_sql = """SELECT value FROM cont WHERE name = ?;"""
        inflow_sql = """SELECT fid, time_series_fid, ident, inoutfc FROM inflow WHERE fid = ?;"""
        ts_data_sql = (
            """SELECT time, value, value2 FROM inflow_time_series_data WHERE series_fid = ? ORDER BY fid;"""
        )

        if not subdomain:
            inflow_cells_sql = """SELECT inflow_fid, grid_fid FROM inflow_cells ORDER BY inflow_fid, grid_fid;"""
        else:
            inflow_cells_sql = f"""
                                SELECT 
                                    ic.inflow_fid, 
                                    md.domain_cell 
                                FROM 
                                    inflow_cells AS ic
                                JOIN
                                    schema_md_cells md ON ic.grid_fid = md.grid_fid
                                WHERE 
                                    md.domain_fid = {subdomain}
                                ORDER BY ic.inflow_fid, md.domain_cell;
                                """

        # Divide inflow line hydrograph between grid elements
        has_line_hyd = self.execute("SELECT fid FROM inflow WHERE geom_type = 'line';").fetchall()
        line_cells_dict = {}
        if has_line_hyd:
            for line_hyd in has_line_hyd:
                line_cells = self.execute(f"SELECT grid_fid FROM inflow_cells WHERE inflow_fid = '{line_hyd[0]}';").fetchall()
                n_cells = len(line_cells)
                if subdomain:
                    line_cells = self.execute(
                        f"""SELECT 
                                md.domain_cell 
                            FROM 
                                inflow_cells AS ic
                            JOIN
                                schema_md_cells md ON ic.grid_fid = md.grid_fid
                            WHERE 
                                ic.inflow_fid = '{line_hyd[0]}' AND md.domain_fid = {subdomain};
                            """).fetchall()
                for cell in line_cells:
                    line_cells_dict[cell[0]] = n_cells

        head_line = " {0: <15} {1}"
        inf_line = "{0: <15} {1: <15} {2}"
        tsd_line = "H   {0: <15} {1: <15} {2}"

        ideplt = self.execute(cont_sql, ("IDEPLT",)).fetchone()
        # Adjust the ideplt grid number to the multi domain cell
        if subdomain:
            ideplt = self.execute(f"""
                                    SELECT
                                        md.domain_cell 
                                    FROM 
                                        schema_md_cells AS md
                                    JOIN 
                                        grid g ON g.fid = md.grid_fid
                                    WHERE 
                                        g.fid = {ideplt[0]} AND md.domain_fid = {subdomain}
                                    """).fetchone()

        ihourdaily = self.execute(cont_sql, ("IHOURDAILY",)).fetchone()

        if ihourdaily is None:
            ihourdaily = (0,)

        if ideplt is None:
            if not subdomain:
                first_gid = self.execute("""SELECT grid_fid FROM inflow_cells ORDER BY fid LIMIT 1;""").fetchone()
            else:
                first_gid = self.execute(f"""SELECT 
                                                md.domain_cell 
                                            FROM 
                                                inflow_cells AS ic
                                            JOIN
                                                schema_md_cells md ON ic.grid_fid = md.grid_fid
                                            WHERE 
                                                md.domain_fid = {subdomain}
                                            ORDER BY ic.fid LIMIT 1;""").fetchone()
            ideplt = first_gid if first_gid is not None else (0,)

        inflow = os.path.join(outdir, "INFLOW.DAT")
        previous_iid = -1
        row = None

        warning = ""
        inflow_lines = []

        if not self.is_table_empty("inflow"):
            for iid, gid in self.execute(inflow_cells_sql):
                if previous_iid != iid:
                    row = self.execute(inflow_sql, (iid,)).fetchone()
                    if row:
                        row = [x if x is not None and x != "" else 0 for x in row]
                        if previous_iid == -1:
                            inflow_lines.append(head_line.format(ihourdaily[0], ideplt[0]))
                        previous_iid = iid
                    else:
                        warning += (
                                "Data for inflow in cell "
                                + str(gid)
                                + " not found in 'Inflow' table (wrong inflow 'id' "
                                + str(iid)
                                + " in 'Inflow Cells' table).\n\n"
                        )
                        continue
                else:
                    pass

                fid, ts_fid, ident, inoutfc = row  # ident is 'F' or 'C'
                inflow_lines.append(inf_line.format(ident, inoutfc, gid))
                series = self.execute(ts_data_sql, (ts_fid,))
                for tsd_row in series:
                    tsd_row = [x if x is not None and x not in [-9999] else "" for x in tsd_row]
                    if gid in line_cells_dict.keys():
                        inflow_lines.append(tsd_line.format(tsd_row[0], round(tsd_row[1]/line_cells_dict.get(gid), 2), tsd_row[2]).rstrip())
                    else:
                        inflow_lines.append(tsd_line.format(tsd_row[0], round(tsd_row[1], 2), tsd_row[2]).rstrip())

        mud = self.gutils.get_cont_par("MUD")
        ised = self.gutils.get_cont_par("ISED")

        if not self.is_table_empty("reservoirs"):
            if mud == '0':
                if not subdomain:
                    schematic_reservoirs_sql = (
                        """SELECT grid_fid, wsel, n_value FROM reservoirs ORDER BY fid;"""
                    )
                else:
                    schematic_reservoirs_sql = f"""
                                                SELECT 
                                                    md.domain_cell,
                                                    r.wsel, 
                                                    r.n_value 
                                                FROM 
                                                    reservoirs AS r
                                                JOIN
                                                    schema_md_cells md ON r.grid_fid = md.grid_fid
                                                WHERE 
                                                    md.domain_fid = {subdomain}
                                                ORDER BY r.fid;"""

                res_line1a = "R   {0: <15} {1:<10.2f} {2:<10.2f}"

                for res in self.execute(schematic_reservoirs_sql):
                    res = [x if x is not None else "" for x in res]
                    inflow_lines.append(res_line1a.format(*res))
            if mud == '2':
                if not subdomain:
                    schematic_reservoirs_sql = (
                        """SELECT grid_fid, wsel, 0 AS tailings, n_value FROM reservoirs ORDER BY fid;"""
                    )
                else:
                    schematic_reservoirs_sql = f"""SELECT 
                                                    md.domain_cell, 
                                                    r.wsel, 
                                                    0 AS tailings, 
                                                    r.n_value 
                                                FROM 
                                                    reservoirs AS r
                                                JOIN
                                                    schema_md_cells md ON r.grid_fid = md.grid_fid
                                                WHERE 
                                                    md.domain_fid = {subdomain}
                                                ORDER BY r.fid;"""

                res_line1a = "R   {0: <15} {1:<10.2f} {2:<10.2f} {3:<10.2f}"

                for res in self.execute(schematic_reservoirs_sql):
                    res = [x if x is not None else "" for x in res]
                    inflow_lines.append(res_line1a.format(*res))

        if not self.is_table_empty("tailing_reservoirs"):
            if mud == '2':
                if not subdomain:
                    schematic_tailing_reservoirs_sql = (
                        """SELECT grid_fid, wsel, tailings, n_value FROM tailing_reservoirs ORDER BY fid;"""
                    )
                else:
                    schematic_tailing_reservoirs_sql = f"""
                        SELECT 
                            md.domain_cell, 
                            tr.wsel, 
                            tr.tailings, 
                            tr.n_value 
                        FROM 
                            tailing_reservoirs AS tr
                        JOIN
                            schema_md_cells md ON tr.grid_fid = md.grid_fid
                        WHERE 
                            md.domain_fid = {subdomain}
                        ORDER BY tr.fid;"""


                res_line1at = "R   {0: <15} {1:<10.2f} {2:<10.2f} {3:<10.2f}"

                for res in self.execute(schematic_tailing_reservoirs_sql):
                    res = [x if x is not None else "" for x in res]
                    inflow_lines.append(res_line1at.format(*res))
            if mud == '1':
                if not subdomain:
                    schematic_tailing_reservoirs_sql = (
                        """SELECT grid_fid, tailings, n_value FROM tailing_reservoirs ORDER BY fid;"""
                    )
                else:
                    schematic_tailing_reservoirs_sql = f"""
                        SELECT 
                            md.domain_cell, 
                            tr.tailings, 
                            tr.n_value 
                        FROM 
                            tailing_reservoirs AS tr
                        JOIN
                            schema_md_cells md ON tr.grid_fid = md.grid_fid
                        WHERE 
                            md.domain_fid = {subdomain}
                        ORDER BY tr.fid;"""

                res_line1at = "R   {0: <15} {1:<10.2f} {2:<10.2f}"

                for res in self.execute(schematic_tailing_reservoirs_sql):
                    res = [x if x is not None else "" for x in res]
                    inflow_lines.append(res_line1at.format(*res))

            if mud == '0' and ised == '1':
                if not subdomain:
                    schematic_tailing_reservoirs_sql = (
                        """SELECT grid_fid, tailings, n_value FROM tailing_reservoirs ORDER BY fid;"""
                    )
                else:
                    schematic_tailing_reservoirs_sql = f"""
                        SELECT 
                            md.domain_cell, 
                            tr.tailings, 
                            tr.n_value 
                        FROM 
                            tailing_reservoirs AS tr
                        JOIN
                            schema_md_cells md ON tr.grid_fid = md.grid_fid
                        WHERE 
                            md.domain_fid = {subdomain}
                        ORDER BY tr.fid;"""

                res_line1at = "R   {0: <15} {1:<10.2f} {2:<10.2f}"

                for res in self.execute(schematic_tailing_reservoirs_sql):
                    res = [x if x is not None else "" for x in res]
                    inflow_lines.append(res_line1at.format(*res))

        if inflow_lines:
            with open(inflow, "w") as inf:
                for line in inflow_lines:
                    if line:
                        inf.write(line + "\n")

        QApplication.restoreOverrideCursor()
        if warning != "":
            self.uc.show_warn(
                "ERROR 180319.1020: error while exporting INFLOW.DAT!\n\n"
                + warning
                + "\n\nWere the Boundary Conditions schematized? "
            )

        return True
        #
        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error("ERROR 101218.1542: exporting INFLOW.DAT failed!.\n", e)
        #     return False

    def export_outrc(self, output=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_outrc_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            pass

    def export_outrc_dat(self, outdir):
        """
        Function to export the outrc to the DAT file
        """
        try:
            if self.is_table_empty("outrc"):
                return False

            outrc_sql = """SELECT DISTINCT grid_fid FROM outrc ORDER BY grid_fid"""

            rows = self.execute(outrc_sql).fetchall()
            if not rows:
                return False

            one_value = "N  {0}\n"
            two_values = "P  {0}  {1}\n"

            outrc = os.path.join(outdir, "OUTRC.DAT")
            with open(outrc, "w") as t:
                for row in rows:
                    t.write(one_value.format(row[0]))
                    outrc_data_sql = f"""SELECT depthrt, volrt FROM outrc WHERE grid_fid = {row[0]} ORDER BY depthrt;"""
                    outrc_data = self.execute(outrc_data_sql).fetchall()
                    for data in outrc_data:
                        t.write(two_values.format(*[round(data[0], 2), round(data[1], 2)]))
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 040822.0442: exporting OUTRC.DAT failed!.\n", e)
            return False

    def export_tailings(self, output=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_tailings_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_tailings_hdf5()

    def export_tailings_hdf5(self):
        """
        Function to export tailings to a hdf5 file
        """
        try:
            if self.is_table_empty("tailing_cells"):
                return False

            tailings_sql = """
            SELECT grid, tailings_surf_elev, water_surf_elev, concentration FROM tailing_cells ORDER BY grid;
            """
            concentration_sql = """SELECT 
                                CASE WHEN COUNT(*) > 0 THEN True
                                     ELSE False
                                END AS result
                                FROM 
                                    tailing_cells
                                WHERE 
                                    concentration <> 0 OR concentration IS NULL;"""
            line1 = "{0}  {1}  {2}  {3}\n"

            rows = self.execute(tailings_sql).fetchall()
            if not rows:
                return False
            else:
                pass

            tailings_group = self.parser.tailings_group

            cv = self.execute(concentration_sql).fetchone()[0]
            MUD = int(float(self.gutils.get_cont_par("MUD")))
            ISED = int(float(self.gutils.get_cont_par("ISED")))

            # Don't export any tailings
            if MUD == 0 and ISED == 0:
                return False

            # TAILINGS and TAILINGS_CV
            elif MUD == 1 or ISED == 1:
                # Export TAILINGS_CV
                if cv == 1:
                    for row in rows:
                        try:
                            tailings_group.datasets["TAILINGS_CV"].data.append([row[0], row[1], row[3]])
                        except:
                            tailings_group.create_dataset('TAILINGS_CV', [])
                            tailings_group.datasets["TAILINGS_CV"].data.append([row[0], row[1], row[3]])

                # Export TAILINGS.DAT
                else:
                    for row in rows:
                        try:
                            tailings_group.datasets["TAILINGS"].data.append([row[0], row[1]])
                        except:
                            tailings_group.create_dataset('TAILINGS', [])
                            tailings_group.datasets["TAILINGS"].data.append([row[0], row[1]])

            # TAILINGS_STACK_DEPTH.DAT
            elif MUD == 2:
                for row in rows:
                    try:
                        tailings_group.datasets["TAILINGS_STACK_DEPTH"].data.append([row[0], row[2], row[1]])
                    except:
                        tailings_group.create_dataset('TAILINGS_STACK_DEPTH', [])
                        tailings_group.datasets["TAILINGS_STACK_DEPTH"].data.append([row[0], row[2], row[1]])
            else:
                return False

            self.parser.write_groups(tailings_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 040822.0442: exporting TAILINGS.HDF5 failed!.\n", e)
            return False

    def export_tailings_dat(self, outdir):
        try:
            if self.is_table_empty("tailing_cells"):
                return False

            tailings_sql = """SELECT grid, tailings_surf_elev, water_surf_elev, concentration FROM tailing_cells ORDER BY grid;"""
            concentration_sql = """SELECT 
                                CASE WHEN COUNT(*) > 0 THEN True
                                     ELSE False
                                END AS result
                                FROM 
                                    tailing_cells
                                WHERE 
                                    concentration <> 0 OR concentration IS NULL;"""

            rows = self.execute(tailings_sql).fetchall()
            if not rows:
                return False

            cv = self.execute(concentration_sql).fetchone()[0]
            MUD = self.gutils.get_cont_par("MUD")
            ISED = self.gutils.get_cont_par("ISED")

            two_values = "{0}  {1}\n"
            three_values = "{0}  {1}  {2}\n"

            # Don't export any tailings related file
            if MUD == '0' and ISED == '0':
                return False
            # TAILINGS.DAT and TAILINGS_CV.DAT
            elif MUD == '1' or ISED == '1':
                # Export TAILINGS_CV.DAT
                if cv == 1:
                    tailings_cv = os.path.join(outdir, "TAILINGS_CV.DAT")
                    with open(tailings_cv, "w") as t:
                        for row in rows:
                            t.write(three_values.format(*[row[0], row[1], row[3]]))
                # Export TAILINGS.DAT
                else:
                    tailings = os.path.join(outdir, "TAILINGS.DAT")
                    with open(tailings, "w") as t:
                        for row in rows:
                            t.write(two_values.format(*[row[0], row[1]]))
            # TAILINGS_STACK_DEPTH.DAT
            elif MUD == '2':
                stack = os.path.join(outdir, "TAILINGS_STACK_DEPTH.DAT")
                with open(stack, "w") as t:
                    for row in rows:
                        t.write(three_values.format(*[row[0], row[2], row[1]]))
            else:
                return False

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 040822.0442: exporting TAILINGS.DAT failed!.\n", e)
            return False

    def export_outflow(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_outflow_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_outflow_hdf5(subdomain)

    def export_outflow_dat(self, outdir, subdomain):
        # check if there are any outflows defined.
        try:
            if self.is_table_empty("outflow") and self.is_table_empty("outflow_cells"):
                return False

            outflow_sql = """
            SELECT fid, fp_out, chan_out, hydro_out, chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid
            FROM outflow WHERE fid = ?;"""
            if not subdomain:
                outflow_cells_sql = """SELECT outflow_fid, grid_fid FROM outflow_cells ORDER BY outflow_fid, grid_fid;"""
            else:
                outflow_cells_sql = f"""SELECT 
                                            outflow_fid, 
                                            md.domain_cell 
                                        FROM 
                                            outflow_cells AS oc
                                        JOIN 
                                            schema_md_cells md ON oc.grid_fid = md.grid_fid
                                        WHERE 
                                            md.domain_fid = {subdomain};"""
            qh_params_data_sql = """SELECT hmax, coef, exponent FROM qh_params_data WHERE params_fid = ?;"""
            qh_table_data_sql = """SELECT depth, q FROM qh_table_data WHERE table_fid = ? ORDER BY fid;"""
            ts_data_sql = """SELECT time, value FROM outflow_time_series_data WHERE series_fid = ? ORDER BY fid;"""

            k_line = "K  {0}\n"
            qh_params_line = "H  {0}  {1}  {2}\n"
            qh_table_line = "T  {0}  {1}\n"
            n_line = "N     {0}  {1}\n"
            ts_line = "S  {0}  {1}\n"
            o_line = "{0}  {1}\n"

            out_cells = self.execute(outflow_cells_sql).fetchall()
            outflow = os.path.join(outdir, "OUTFLOW.DAT")
            floodplains = {}
            previous_oid = -1
            row = None
            border = get_BC_Border()

            data_written = False

            warning = ""
            with open(outflow, "w") as o:
                if out_cells:
                    for oid, gid in out_cells:
                        if previous_oid != oid:
                            row = self.execute(outflow_sql, (oid,)).fetchone()
                            if row is not None:
                                row = [x if x is not None and x != "" else 0 for x in row]
                                previous_oid = oid
                            else:
                                warning += (
                                        "<br>* Cell " + str(
                                    gid) + " in 'outflow_cells' table points to 'outflow' table with"
                                )
                                warning += "<br> 'outflow_fid' = " + str(oid) + ".<br>"
                                continue
                        else:
                            pass

                        if row is not None:
                            (
                                fid,
                                fp_out,
                                chan_out,
                                hydro_out,
                                chan_tser_fid,
                                chan_qhpar_fid,
                                chan_qhtab_fid,
                                fp_tser_fid,
                            ) = row
                            if gid not in floodplains and (fp_out == 1 or hydro_out > 0):
                                floodplains[gid] = hydro_out
                            if chan_out == 1:
                                o.write(k_line.format(gid))
                                data_written = True
                                for values in self.execute(qh_params_data_sql, (chan_qhpar_fid,)):
                                    o.write(qh_params_line.format(*values))
                                    data_written = True
                                for values in self.execute(qh_table_data_sql, (chan_qhtab_fid,)):
                                    o.write(qh_table_line.format(*values))
                                    data_written = True
                            else:
                                pass

                            if chan_tser_fid > 0 or fp_tser_fid > 0:
                                if border is not None:
                                    if gid in border:
                                        continue
                                nostacfp = 1 if chan_tser_fid == 1 else 0
                                o.write(n_line.format(gid, nostacfp))
                                data_written = True
                                series_fid = chan_tser_fid if chan_tser_fid > 0 else fp_tser_fid
                                for values in self.execute(ts_data_sql, (series_fid,)):
                                    o.write(ts_line.format(*values))
                                    data_written = True
                            else:
                                pass

                # Write the subdomains O lines
                subdomain_hydrograph_grid_elements = []
                if subdomain:
                    if any(hydro_out > 0 for _, hydro_out in floodplains.items()):
                        self.uc.bar_warn(
                            "During multiple domain export, the outflow hydrograph boundary condition is automatically replaced by the connections between the domains.")
                        self.uc.log_info(
                            "During multiple domain export, the outflow hydrograph boundary condition is automatically replaced by the connections between the domains.")

                    outflow_md_connections_sql = f"""SELECT
                                                       fid_subdomain_1,
                                                       fid_subdomain_2,
                                                       fid_subdomain_3,
                                                       fid_subdomain_4,
                                                       fid_subdomain_5,
                                                       fid_subdomain_6,
                                                       fid_subdomain_7,
                                                       fid_subdomain_8,
                                                       fid_subdomain_9
                                                   FROM
                                                       mult_domains_con AS im
                                                   WHERE 
                                                        fid = {subdomain};"""

                    result = self.gutils.execute(outflow_md_connections_sql).fetchone()

                    # Initialize fid_subdomains
                    fid_subdomains = [fid for fid in result if fid not in (0, None, 'NULL')] if result else []

                    # Find fids greater than 9
                    fids_greater_than_9 = [fid for fid in fid_subdomains if int(fid) > 9]

                    # Find available fids between 1 and 9
                    used_fids = set(fid_subdomains)  # Already used fids
                    available_fids = [i for i in range(1, 10) if i not in used_fids]

                    # Create a dictionary to map fids greater than 9 to the lowest available fid
                    fid_mapping = {}
                    for fid in fids_greater_than_9:
                        if available_fids:
                            new_fid = available_fids.pop(0)  # Get the lowest available fid
                            fid_mapping[fid] = new_fid

                    # Proceed only if fid_subdomains is not empty
                    if fid_subdomains:
                        placeholders = ", ".join("?" for _ in fid_subdomains)  # Create placeholders for the IN clause
                        outflow_md_cells_sql = f"""
                                            SELECT 
                                                domain_cell, 
                                                down_domain_fid 
                                            FROM 
                                                schema_md_cells AS md
                                            JOIN 
                                                mult_domains_con mdc ON mdc.fid = md.domain_fid
                                            WHERE 
                                                domain_fid = ? AND down_domain_fid IS NOT NULL AND down_domain_fid IN ({placeholders})
                                            ORDER BY 
                                                down_domain_fid, domain_cell;
                                        """
                        outflow_md_cells = self.execute(outflow_md_cells_sql, (subdomain, *fid_subdomains)).fetchall()
                        for cell in outflow_md_cells:
                            gid = cell[0]
                            subdomain_hydrograph_grid_elements.append(gid)
                            hydro_out = cell[1]
                            if hydro_out > 9:
                                # Check if the hydro_out value is in the mapping
                                if hydro_out in fid_mapping:
                                    # Replace the hydro_out value with the mapped value
                                    hydro_out = fid_mapping[hydro_out]
                            ident = "O{0}".format(hydro_out)
                            o.write(o_line.format(ident, gid))
                            data_written = True
                            if border is not None and gid in border:
                                border.remove(gid)

                # Write O1, O2, ... lines:
                for gid, hydro_out in sorted(iter(floodplains.items()), key=lambda items: (items[1], items[0])):
                    if gid not in subdomain_hydrograph_grid_elements:
                        if not subdomain:
                            ident = "O{0}".format(hydro_out) if hydro_out > 0 else "O"
                        else:
                            ident = "O"
                        o.write(o_line.format(ident, gid))
                        data_written = True
                        if border is not None:
                            if gid in border:
                                border.remove(gid)

                # Write lines 'O cell_id":
                if border is not None:
                    for b in border:
                        o.write(o_line.format("O", b))
                        data_written = True

            if not data_written:
                os.remove(outflow)

            if warning != "":
                QApplication.setOverrideCursor(Qt.ArrowCursor)
                msg = "ERROR 170319.2018: error while exporting OUTFLOW.DAT!<br><br>" + warning
                msg += "<br><br><FONT COLOR=red>Did you schematize the Boundary Conditions?</FONT>"
                self.uc.show_warn(msg)
                QApplication.restoreOverrideCursor()
            return True

        except Exception as e:
            self.uc.show_error("ERROR 101218.1543: exporting OUTFLOW.DAT failed!\n", e)
            self.uc.log_info("ERROR 101218.1543: exporting OUTFLOW.DAT failed!")
            return False

    def export_outflow_hdf5(self, subdomain):
        """
        Function to export outflow data to HDF5 file
        """

        # check if there are any outflows defined.
        if self.is_table_empty("outflow") and self.is_table_empty("outflow_cells"):
            return False

        outflow_sql = """
        SELECT fid, fp_out, chan_out, hydro_out, chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid
        FROM outflow WHERE fid = ?;"""
        if not subdomain:
            outflow_cells_sql = """SELECT outflow_fid, grid_fid FROM outflow_cells ORDER BY outflow_fid, grid_fid;"""
        else:
            outflow_cells_sql = f"""SELECT 
                                        outflow_fid, 
                                        md.domain_cell 
                                    FROM 
                                        outflow_cells AS oc
                                    JOIN 
                                        schema_md_cells md ON oc.grid_fid = md.grid_fid
                                    WHERE 
                                        md.domain_fid = {subdomain};"""
        qh_params_data_sql = """SELECT params_fid, hmax, coef, exponent FROM qh_params_data WHERE params_fid = ?;"""
        qh_table_data_sql = """SELECT table_fid, depth, q FROM qh_table_data WHERE table_fid = ? ORDER BY fid;"""
        ts_data_sql = """SELECT series_fid, time, value FROM outflow_time_series_data WHERE series_fid = ? ORDER BY fid;"""

        two_values = "{0}  {1}\n"
        three_values = "{0}  {1}  {2}\n"
        four_values = "{0}  {1}  {2}  {3}\n"

        out_cells = self.execute(outflow_cells_sql).fetchall()
        bc_group = self.parser.bc_group

        previous_oid = -1
        row = None
        ts_series_fid = []
        qh_params_fid = []
        qh_table_fid = []

        warning = ""

        border = get_BC_Border()
        data_written = False

        subdomain_hydrograph_grid_elements = []
        if subdomain:

            outflow_md_connections_sql = f"""SELECT
                                               fid_subdomain_1,
                                               fid_subdomain_2,
                                               fid_subdomain_3,
                                               fid_subdomain_4,
                                               fid_subdomain_5,
                                               fid_subdomain_6,
                                               fid_subdomain_7,
                                               fid_subdomain_8,
                                               fid_subdomain_9
                                           FROM
                                               mult_domains_con AS im
                                           WHERE 
                                                fid = {subdomain};"""

            result = self.gutils.execute(outflow_md_connections_sql).fetchone()

            # Initialize fid_subdomains
            fid_subdomains = [fid for fid in result if fid not in (0, None, 'NULL')] if result else []

            # Find fids greater than 9
            fids_greater_than_9 = [fid for fid in fid_subdomains if int(fid) > 9]

            # Find available fids between 1 and 9
            used_fids = set(fid_subdomains)  # Already used fids
            available_fids = [i for i in range(1, 10) if i not in used_fids]

            # Create a dictionary to map fids greater than 9 to the lowest available fid
            fid_mapping = {}
            for fid in fids_greater_than_9:
                if available_fids:
                    new_fid = available_fids.pop(0)  # Get the lowest available fid
                    fid_mapping[fid] = new_fid

            # Proceed only if fid_subdomains is not empty
            if fid_subdomains:
                placeholders = ", ".join(
                    "?" for _ in fid_subdomains)  # Create placeholders for the IN clause
                outflow_md_cells_sql = f"""
                                        SELECT 
                                            domain_cell, 
                                            down_domain_fid 
                                        FROM 
                                            schema_md_cells AS md
                                        JOIN 
                                            mult_domains_con mdc ON mdc.fid = md.domain_fid
                                        WHERE 
                                            domain_fid = ? AND down_domain_fid IS NOT NULL AND down_domain_fid IN ({placeholders})
                                        ORDER BY 
                                            down_domain_fid, domain_cell;
                                        """
                outflow_md_cells = self.execute(outflow_md_cells_sql,
                                                (subdomain, *fid_subdomains)).fetchall()

                for cell in outflow_md_cells:
                    gid = cell[0]
                    subdomain_hydrograph_grid_elements.append(gid)
                    hydro_out = cell[1]
                    if hydro_out > 9:
                        # Check if the hydro_out value is in the mapping
                        if hydro_out in fid_mapping:
                            # Replace the hydro_out value with the mapped value
                            hydro_out = fid_mapping[hydro_out]
                    try:
                        bc_group.datasets["Outflow/HYD_OUT_GRID"].data.append(
                            create_array(two_values, 2, np.int_, (hydro_out, gid)))
                    except:
                        bc_group.create_dataset('Outflow/HYD_OUT_GRID', [])
                        bc_group.datasets["Outflow/HYD_OUT_GRID"].data.append(
                            create_array(two_values, 2, np.int_, (hydro_out, gid)))
                    data_written = True

                    # ident = "O{0}".format(hydro_out)
                    #
                    # o.write(o_line.format(ident, gid))

                    if border is not None and gid in border:
                        border.remove(gid)

        for oid, gid in out_cells:
            if previous_oid != oid:
                row = self.execute(outflow_sql, (oid,)).fetchone()
                if row is not None:
                    row = [x if x is not None and x != "" else 0 for x in row]
                    previous_oid = oid
                else:
                    warning += (
                            "<br>* Cell " + str(gid) + " in 'outflow_cells' table points to 'outflow' table with"
                    )
                    warning += "<br> 'outflow_fid' = " + str(oid) + ".<br>"
                    continue
            else:
                pass

            if row is not None:

                def to_int(val):
                    if isinstance(val, bytes):
                        return int.from_bytes(val, byteorder='little')
                    return int(val)

                (
                    fid,
                    fp_out,
                    chan_out,
                    hydro_out,
                    chan_tser_fid,
                    chan_qhpar_fid,
                    chan_qhtab_fid,
                    fp_tser_fid,
                ) = (to_int(x) for x in row)

                if gid in subdomain_hydrograph_grid_elements:
                    continue

                # 1. Floodplain outflow (no hydrograph)
                variables = (chan_out, hydro_out, chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid)
                if fp_out == 1 and check_outflow_condition(variables):
                    try:
                        bc_group.datasets["Outflow/FP_OUT_GRID"].data.append(gid)
                    except:
                        bc_group.create_dataset('Outflow/FP_OUT_GRID', [])
                        bc_group.datasets["Outflow/FP_OUT_GRID"].data.append(gid)
                    data_written = True
                    continue

                # 2. Channel outflow (no hydrograph)
                variables = (fp_out, hydro_out, chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid)
                if chan_out == 1 and check_outflow_condition(variables):
                    try:
                        bc_group.datasets["Outflow/CH_OUT_GRID"].data.append(gid)
                    except:
                        bc_group.create_dataset('Outflow/CH_OUT_GRID', [])
                        bc_group.datasets["Outflow/CH_OUT_GRID"].data.append(gid)
                    data_written = True
                    continue

                # 3. Floodplain and channel outflow (no hydrograph)
                variables = (hydro_out, chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid)
                if fp_out == 1 and chan_out == 1 and check_outflow_condition(variables):
                    try:
                        bc_group.datasets["Outflow/FP_OUT_GRID"].data.append(gid)
                    except:
                        bc_group.create_dataset('Outflow/FP_OUT_GRID', [])
                        bc_group.datasets["Outflow/FP_OUT_GRID"].data.append(gid)
                    try:
                        bc_group.datasets["Outflow/CH_OUT_GRID"].data.append(gid)
                    except:
                        bc_group.create_dataset('Outflow/CH_OUT_GRID', [])
                        bc_group.datasets["Outflow/CH_OUT_GRID"].data.append(gid)
                    data_written = True
                    continue

                # 4. Outflow with hydrograph
                if not subdomain:
                    variables = (fp_out, chan_out, chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid)
                    if hydro_out != 0 and check_outflow_condition(variables):
                        try:
                            bc_group.datasets["Outflow/HYD_OUT_GRID"].data.append(
                                create_array(two_values, 2, np.int_, (hydro_out, gid)))
                        except:
                            bc_group.create_dataset('Outflow/HYD_OUT_GRID', [])
                            bc_group.datasets["Outflow/HYD_OUT_GRID"].data.append(
                                create_array(two_values, 2, np.int_, (hydro_out, gid)))
                        data_written = True
                        continue
                else:
                    if hydro_out != 0 and check_outflow_condition(variables):
                        self.uc.bar_warn(
                            "During multiple domain export, the outflow hydrograph boundary condition is automatically replaced by the connections between the domains.")
                        self.uc.log_info(
                            "During multiple domain export, the outflow hydrograph boundary condition is automatically replaced by the connections between the domains.")

                # Time-stage BCs
                variables = (hydro_out, chan_qhpar_fid, chan_qhtab_fid)
                if check_outflow_condition(variables):
                    # 5. Time-stage for floodplain
                    if fp_tser_fid != 0:
                        try:
                            bc_group.datasets["Outflow/TS_OUT_GRID"].data.append(
                                create_array(three_values, 3, np.int_, (gid, 0, fp_tser_fid)))
                            if fp_tser_fid not in ts_series_fid:
                                for ts_line_values in self.execute(ts_data_sql, (fp_tser_fid,)):
                                    bc_group.datasets["Outflow/TS_OUT_DATA"].data.append(
                                        create_array(three_values, 3, np.float64, ts_line_values))
                                ts_series_fid.append(fp_tser_fid)
                        except:
                            bc_group.create_dataset('Outflow/TS_OUT_GRID', [])
                            bc_group.datasets["Outflow/TS_OUT_GRID"].data.append(
                                create_array(three_values, 3, np.int_, (gid, 0, fp_tser_fid)))
                            bc_group.create_dataset('Outflow/TS_OUT_DATA', [])
                            for ts_line_values in self.execute(ts_data_sql, (fp_tser_fid,)):
                                bc_group.datasets["Outflow/TS_OUT_DATA"].data.append(
                                    create_array(three_values, 3, np.float64, ts_line_values))
                            ts_series_fid.append(fp_tser_fid)
                        data_written = True
                    # 6. Time-stage for channel
                    if chan_tser_fid != 0:
                        try:
                            bc_group.datasets["Outflow/TS_OUT_GRID"].data.append(
                                create_array(three_values, 3, np.int_, (gid, 1, chan_tser_fid)))
                            if chan_tser_fid not in ts_series_fid:
                                for ts_line_values in self.execute(ts_data_sql, (chan_tser_fid,)):
                                    bc_group.datasets["Outflow/TS_OUT_DATA"].data.append(
                                        create_array(three_values, 3, np.float64, ts_line_values))
                                ts_series_fid.append(chan_tser_fid)
                        except:
                            bc_group.create_dataset('Outflow/TS_OUT_GRID', [])
                            bc_group.datasets["Outflow/TS_OUT_GRID"].data.append(
                                create_array(three_values, 3, np.int_, (gid, 1, chan_tser_fid)))
                            bc_group.create_dataset('Outflow/TS_OUT_DATA', [])
                            for ts_line_values in self.execute(ts_data_sql, (chan_tser_fid,)):
                                bc_group.datasets["Outflow/TS_OUT_DATA"].data.append(
                                    create_array(three_values, 3, np.float64, ts_line_values))
                            ts_series_fid.append(chan_tser_fid)
                        data_written = True
                    # Free floodplain
                    if fp_out == 1 and check_outflow_condition(variables):
                        try:
                            bc_group.datasets["Outflow/FP_OUT_GRID"].data.append(gid)
                        except:
                            bc_group.create_dataset('Outflow/FP_OUT_GRID', [])
                            bc_group.datasets["Outflow/FP_OUT_GRID"].data.append(gid)
                        data_written = True
                    # Free channel
                    if chan_out == 1:
                        try:
                            bc_group.datasets["Outflow/CH_OUT_GRID"].data.append(gid)
                        except:
                            bc_group.create_dataset('Outflow/CH_OUT_GRID', [])
                            bc_group.datasets["Outflow/CH_OUT_GRID"].data.append(gid)
                        data_written = True
                    continue

                # 9. Channel Depth-Discharge Power Regression (qh-params)
                variables = (fp_out, hydro_out, chan_tser_fid, chan_qhtab_fid, fp_tser_fid)
                if chan_out == 1 and chan_qhpar_fid != 0 and check_outflow_condition(variables):
                    try:
                        bc_group.datasets["Outflow/QH_PARAMS_GRID"].data.append(
                            create_array(two_values, 2, np.int_, (gid, chan_qhpar_fid)))
                        if chan_qhpar_fid not in qh_params_fid:
                            for qh_params_values in self.execute(qh_params_data_sql, (chan_qhpar_fid,)):
                                bc_group.datasets["Outflow/QH_PARAMS"].data.append(
                                    create_array(four_values, 4, np.float64, qh_params_values))
                            qh_params_fid.append(chan_qhpar_fid)
                    except:
                        bc_group.create_dataset('Outflow/QH_PARAMS_GRID', [])
                        bc_group.datasets["Outflow/QH_PARAMS_GRID"].data.append(
                            create_array(two_values, 2, np.int_, (gid, chan_qhpar_fid))
                        )
                        bc_group.create_dataset('Outflow/QH_PARAMS', [])
                        for qh_params_values in self.execute(qh_params_data_sql, (chan_qhpar_fid,)):
                            bc_group.datasets["Outflow/QH_PARAMS"].data.append(
                                create_array(four_values, 4, np.float64, qh_params_values))
                        qh_params_fid.append(chan_qhpar_fid)
                    data_written = True
                    continue

                # 10. Channel Depth-Discharge (qh-table)
                variables = (fp_out, hydro_out, chan_tser_fid, chan_qhpar_fid, fp_tser_fid)
                if chan_out == 1 and chan_qhtab_fid != 0 and check_outflow_condition(variables):
                    try:
                        bc_group.datasets["Outflow/QH_TABLE_GRID"].data.append(
                            create_array(two_values, 2, np.int_, (gid, chan_qhtab_fid)))
                        if chan_qhtab_fid not in qh_table_fid:
                            for qh_table_values in self.execute(qh_table_data_sql, (chan_qhtab_fid,)):
                                bc_group.datasets["Outflow/QH_TABLE"].data.append(
                                    create_array(three_values, 3, np.float64, qh_table_values))
                            qh_table_fid.append(chan_qhtab_fid)
                    except:
                        bc_group.create_dataset('Outflow/QH_TABLE_GRID', [])
                        bc_group.datasets["Outflow/QH_TABLE_GRID"].data.append(
                            create_array(two_values, 2, np.int_, (gid, chan_qhtab_fid)))
                        bc_group.create_dataset('Outflow/QH_TABLE', [])
                        for qh_table_values in self.execute(qh_table_data_sql, (chan_qhtab_fid,)):
                            bc_group.datasets["Outflow/QH_TABLE"].data.append(
                                create_array(three_values, 3, np.float64, qh_table_values))
                        qh_table_fid.append(chan_qhtab_fid)
                    data_written = True
                    continue

        if data_written:
            self.parser.write_groups(bc_group)
        QApplication.restoreOverrideCursor()
        if warning != "":
            msg = "ERROR 170319.2018: error while exporting OUTFLOW.DAT!<br><br>" + warning
            msg += "<br><br><FONT COLOR=red>Did you schematize the Boundary Conditions?</FONT>"
            self.uc.show_warn(msg)
        return True

    # def export_outflow_md(self, outdir, subdomain):
    #     # check if there are any outflows defined.
    #     try:
    #
    #         outflow_sql = """
    #            SELECT fid, fp_out, chan_out, hydro_out, chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid
    #            FROM outflow WHERE fid = ?;"""
    #
    #         outflow_cells_sql = f"""SELECT
    #                                 outflow_fid,
    #                                 md.domain_cell
    #                             FROM
    #                                 outflow_cells AS oc
    #                             JOIN
    #                                 schema_md_cells md ON oc.grid_fid = md.grid_fid
    #                             WHERE
	# 							    md.domain_fid = {subdomain};"""
    #
    #         qh_params_data_sql = """SELECT hmax, coef, exponent FROM qh_params_data WHERE params_fid = ?;"""
    #         qh_table_data_sql = """SELECT depth, q FROM qh_table_data WHERE table_fid = ? ORDER BY fid;"""
    #         ts_data_sql = """SELECT time, value FROM outflow_time_series_data WHERE series_fid = ? ORDER BY fid;"""
    #
    #         k_line = "K  {0}\n"
    #         qh_params_line = "H  {0}  {1}  {2}\n"
    #         qh_table_line = "T  {0}  {1}\n"
    #         n_line = "N     {0}  {1}\n"
    #         ts_line = "S  {0}  {1}\n"
    #         o_line = "{0}  {1}\n"
    #
    #         out_cells = self.execute(outflow_cells_sql).fetchall()
    #
    #         outflow = os.path.join(outdir, "OUTFLOW.DAT")
    #         floodplains = {}
    #         previous_oid = -1
    #         row = None
    #         border = get_BC_Border()
    #
    #         warning = ""
    #         with open(outflow, "w") as o:
    #             if out_cells:
    #                 for oid, gid in out_cells:
    #                     if previous_oid != oid:
    #                         row = self.execute(outflow_sql, (oid,)).fetchone()
    #                         if row is not None:
    #                             row = [x if x is not None and x != "" else 0 for x in row]
    #                             previous_oid = oid
    #                         else:
    #                             warning += (
    #                                     "<br>* Cell " + str(
    #                                 gid) + " in 'outflow_cells' table points to 'outflow' table with"
    #                             )
    #                             warning += "<br> 'outflow_fid' = " + str(oid) + ".<br>"
    #                             continue
    #                     else:
    #                         pass
    #
    #                     if row is not None:
    #                         (
    #                             fid,
    #                             fp_out,
    #                             chan_out,
    #                             hydro_out,
    #                             chan_tser_fid,
    #                             chan_qhpar_fid,
    #                             chan_qhtab_fid,
    #                             fp_tser_fid,
    #                         ) = row
    #                         if gid not in floodplains and (fp_out == 1 or hydro_out > 0):
    #                             floodplains[gid] = hydro_out
    #                         if chan_out == 1:
    #                             o.write(k_line.format(gid))
    #                             for values in self.execute(qh_params_data_sql, (chan_qhpar_fid,)):
    #                                 o.write(qh_params_line.format(*values))
    #                             for values in self.execute(qh_table_data_sql, (chan_qhtab_fid,)):
    #                                 o.write(qh_table_line.format(*values))
    #                         else:
    #                             pass
    #
    #                         if chan_tser_fid > 0 or fp_tser_fid > 0:
    #                             if border is not None:
    #                                 if gid in border:
    #                                     continue
    #                             nostacfp = 1 if chan_tser_fid == 1 else 0
    #                             o.write(n_line.format(gid, nostacfp))
    #                             series_fid = chan_tser_fid if chan_tser_fid > 0 else fp_tser_fid
    #                             for values in self.execute(ts_data_sql, (series_fid,)):
    #                                 o.write(ts_line.format(*values))
    #                         else:
    #                             pass
    #
    #             # Write O1, O2, ... lines with the multi domain logic, don't allow for user hydro_out
    #             if any(hydro_out > 0 for _, hydro_out in floodplains.items()):
    #                 self.uc.bar_warn("During multiple domain export, the outflow hydrograph boundary condition is automatically replaced by the connections between the domains.")
    #                 self.uc.log_info("During multiple domain export, the outflow hydrograph boundary condition is automatically replaced by the connections between the domains.")
    #
    #             outflow_md_connections_sql = f"""SELECT
    #                                                    fid_subdomain_1,
    #                                                    fid_subdomain_2,
    #                                                    fid_subdomain_3,
    #                                                    fid_subdomain_4,
    #                                                    fid_subdomain_5,
    #                                                    fid_subdomain_6,
    #                                                    fid_subdomain_7,
    #                                                    fid_subdomain_8,
    #                                                    fid_subdomain_9
    #                                                FROM
    #                                                    mult_domains_con AS im
    #                                                WHERE
    #                                                     fid = {subdomain};"""
    #
    #             result = self.gutils.execute(outflow_md_connections_sql).fetchone()
    #
    #             # Initialize fid_subdomains
    #             fid_subdomains = [fid for fid in result if fid not in (0, None, 'NULL')] if result else []
    #
    #             # Find fids greater than 9
    #             fids_greater_than_9 = [fid for fid in fid_subdomains if int(fid) > 9]
    #
    #             # Find available fids between 1 and 9
    #             used_fids = set(fid_subdomains)  # Already used fids
    #             available_fids = [i for i in range(1, 10) if i not in used_fids]
    #
    #             # Create a dictionary to map fids greater than 9 to the lowest available fid
    #             fid_mapping = {}
    #             for fid in fids_greater_than_9:
    #                 if available_fids:
    #                     new_fid = available_fids.pop(0)  # Get the lowest available fid
    #                     fid_mapping[fid] = new_fid
    #
    #             # Proceed only if fid_subdomains is not empty
    #             if fid_subdomains:
    #                 placeholders = ", ".join("?" for _ in fid_subdomains)  # Create placeholders for the IN clause
    #                 outflow_md_cells_sql = f"""
    #                     SELECT
    #                         domain_cell,
    #                         down_domain_fid
    #                     FROM
    #                         schema_md_cells AS md
    #                     JOIN
    #                         mult_domains_con mdc ON mdc.fid = md.domain_fid
    #                     WHERE
    #                         domain_fid = ? AND down_domain_fid IS NOT NULL AND down_domain_fid IN ({placeholders})
    #                     ORDER BY
    #                         down_domain_fid, domain_cell;
    #                 """
    #                 outflow_md_cells = self.execute(outflow_md_cells_sql, (subdomain, *fid_subdomains)).fetchall()
    #
    #                 for cell in outflow_md_cells:
    #                     gid = cell[0]
    #                     hydro_out = cell[1]
    #                     if hydro_out > 9:
    #                         # Check if the hydro_out value is in the mapping
    #                         if hydro_out in fid_mapping:
    #                             # Replace the hydro_out value with the mapped value
    #                             hydro_out = fid_mapping[hydro_out]
    #                     ident = "O{0}".format(hydro_out)
    #                     o.write(o_line.format(ident, gid))
    #                     if border is not None and gid in border:
    #                         border.remove(gid)
    #
    #             # Write lines 'O cell_id":
    #             if border is not None:
    #                 for b in border:
    #                     o.write(o_line.format("O", b))
    #
    #         QApplication.restoreOverrideCursor()
    #         if warning != "":
    #             msg = "ERROR 170319.2018: error while exporting OUTFLOW.DAT!<br><br>" + warning
    #             msg += "<br><br><FONT COLOR=red>Did you schematize the Boundary Conditions?</FONT>"
    #             self.uc.show_warn(msg)
    #         return True
    #
    #     except Exception as e:
    #         QApplication.restoreOverrideCursor()
    #         self.uc.show_error("ERROR 101218.1543: exporting OUTFLOW.DAT failed!.\n", e)
    #         return False

    def export_rain(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_rain_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_rain_hdf5(subdomain)

    def export_rain_hdf5(self, subdomain):
        """
        Function to export rain data to the HDF5 file
        """
        # check if there is any rain defined.
        # try:
        if self.is_table_empty("rain"):
            return False
        rain_sql = """SELECT time_series_fid, irainreal, irainbuilding, tot_rainfall,
                             rainabs, irainarf, movingstorm, rainspeed, iraindir
                      FROM rain;"""

        ts_data_sql = """SELECT time, value FROM rain_time_series_data WHERE series_fid = ? ORDER BY fid;"""
        if not subdomain:
            rain_cells_sql = """SELECT grid_fid, arf FROM rain_arf_cells ORDER BY fid;"""
        else:
            rain_cells_sql = f"""SELECT 
                                    md.domain_cell, 
                                    arf 
                                FROM 
                                    rain_arf_cells AS ra
                                JOIN 
                                    schema_md_cells md ON ra.grid_fid = md.grid_fid
                                 WHERE 
                                    md.domain_fid = {subdomain};"""

        rain_global = "{0}  {1}   {2}   {3}   {4}   {5}\n"
        tsd_line = "{0}   {1}\n"  # Rainfall Time series distribution

        cell_line = "{0: <10} {1}\n"

        rain_row = self.execute(
            rain_sql
        ).fetchone()  # Returns a single feature with all the singlevalues of the rain table:
        # time_series_fid, irainreal, irainbuilding, tot_rainfall, rainabs,
        # irainarf, movingstorm, rainspeed, iraindir.
        if rain_row is None:
            return False
        else:
            pass

        rain_group = self.parser.rain_group
        rain_group.create_dataset('RAIN_GLOBAL', [])

        for global_data in rain_row[1:9]:
            if global_data == "":
                global_data = 0
            rain_group.datasets["RAIN_GLOBAL"].data.append(global_data)
        # rain_group.datasets["RAIN"].data.append(create_array(rain_line2, 4, rain_row[3:7]))

        fid = rain_row[
            0
        ]  # time_series_fid (pointer to the 'rain_time_series_data' table where the pairs (time , distribution) are.
        rain_group.create_dataset('RAIN_DATA', [])
        for row in self.execute(ts_data_sql, (fid,)):
            if None not in row:  # Writes 3rd. lines if rain_time_series_data exists (Rainfall distribution).
                rain_group.datasets["RAIN_DATA"].data.append(create_array(tsd_line, 2, np.float64, row))
                # This is a time series created from the Rainfall Distribution tool in the Rain Editor,
                # selected from a list

        # if rain_row[6] == 1:  # if movingstorm from rain = 0, omit this line.
        #     if (
        #         rain_row[-1] is not None
        #     ):  # row[-1] is the last value of tuple (time_series_fid, irainreal, irainbuilding, tot_rainfall,
        #         # rainabs, irainarf, movingstorm, rainspeed, iraindir).
        #         rain_group.datasets["RAIN"].data.append(create_array(rain_line4, 4, rain_row[-2:]))
        #     else:
        #         pass
        # else:
        #     pass

        if rain_row[5] == 1:  # if irainarf from rain = 0, omit this line.
            rain_group.create_dataset('RAIN_ARF', [])
            for row in self.execute(rain_cells_sql):
                rain_group.datasets["RAIN_ARF"].data.append(create_array(
                    cell_line,
                    2,
                    np.float64,
                    row[0],
                    "{0:.3f}".format(row[1])
                ))

        self.parser.write_groups(rain_group)
        return True

        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error("ERROR 101218.1543: exporting RAIN.DAT failed!.\n", e)
        #     return False

    def export_rain_dat(self, outdir, subdomain):
        # check if there is any rain defined.
        try:

            # Check if rain table is empty and return False if true
            if self.is_table_empty("rain"):
                self.uc.log_info("Rain table is empty!")
                self.uc.bar_info("Rain table is empty!")
                return False

            rain_sql = """SELECT time_series_fid, irainreal, irainbuilding, tot_rainfall,
                                 rainabs, irainarf, movingstorm, rainspeed, iraindir
                          FROM rain;"""

            ts_data_sql = """SELECT time, value FROM rain_time_series_data WHERE series_fid = ? ORDER BY fid;"""

            if not subdomain:
                rain_cells_sql = """SELECT grid_fid, arf FROM rain_arf_cells ORDER BY fid;"""
            else:
                rain_cells_sql = f"""SELECT 
                                        md.domain_cell, 
                                        arf 
                                    FROM 
                                        rain_arf_cells AS ra
                                    JOIN 
                                        schema_md_cells md ON ra.grid_fid = md.grid_fid
                                     WHERE 
                                        md.domain_fid = {subdomain};"""

            rain_line1 = "{0}  {1}\n"
            rain_line2 = "{0}   {1}  {2}  {3}\n"
            tsd_line3 = "R {0}   {1}\n"  # Rainfall Time series distribution
            rain_line4 = "{0}   {1}\n"

            cell_line5 = "{0: <10} {1}\n"

            rain_row = self.execute(
                rain_sql
            ).fetchone()  # Returns a single feature with all the singlevalues of the rain table:
            # time_series_fid, irainreal, irainbuilding, tot_rainfall, rainabs,
            # irainarf, movingstorm, rainspeed, iraindir.

            # If no data was found on the rain table, return False
            if rain_row is None:
                return False

            # If tot_rainfall is zero, return False
            if rain_row[1] == 0 and rain_row[3] == 0:
                self.uc.log_info("Total Storm Rainfall is not defined!")
                self.uc.bar_warn("Total Storm Rainfall is not defined!")
                return False

            rain = os.path.join(outdir, "RAIN.DAT")
            with open(rain, "w") as r:
                r.write(rain_line1.format(*rain_row[1:3]))  # irainreal, irainbuilding
                r.write(rain_line2.format(*rain_row[3:7]))  # tot_rainfall (RTT), rainabs, irainarf, movingstorm

                fid = rain_row[
                    0
                ]  # time_series_fid (pointer to the 'rain_time_series_data' table where the pairs (time , distribution) are.
                for row in self.execute(ts_data_sql, (fid,)):
                    if None not in row:  # Writes 3rd. lines if rain_time_series_data exists (Rainfall distribution).
                        r.write(
                            tsd_line3.format(*row)
                        )  # Writes 'R time value (i.e. distribution)' (i.e. 'R  R_TIME R_DISTR' in FLO-2D jargon).
                        # This is a time series created from the Rainfall Distribution tool in the Rain Editor,
                        # selected from a list

                if rain_row[6] == 1:  # if movingstorm from rain = 0, omit this line.
                    if (
                            rain_row[-1] is not None
                    ):  # row[-1] is the last value of tuple (time_series_fid, irainreal, irainbuilding, tot_rainfall,
                        # rainabs, irainarf, movingstorm, rainspeed, iraindir).
                        r.write(
                            rain_line4.format(*rain_row[-2:])
                        )  # Write the last 2 values (-2 means 2 from last): rainspeed and iraindir.
                    else:
                        pass
                else:
                    pass

                if rain_row[5] == 1:  # if irainarf from rain = 0, omit this line.
                    for row in self.execute(rain_cells_sql):
                        r.write(cell_line5.format(row[0], "{0:.3f}".format(row[1])))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1543: exporting RAIN.DAT failed!.\n", e)
            self.uc.log_info("ERROR 101218.1543: exporting RAIN.DAT failed!.\n")
            return False

    def export_raincell(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_raincell_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_raincell_hdf5(subdomain)

    def export_raincell_dat(self, outdir, subdomain):
        try:
            if self.is_table_empty("raincell_data"):
                return False

            s = QSettings()

            # Check for existing RAINCELL.DAT file
            raincell = os.path.join(outdir, "RAINCELL.DAT")
            if os.path.exists(raincell):
                msg = f"There is an existing RAINCELL.DAT file at: \n\n{outdir}\n\n"
                msg += "Would you like to overwrite it?"
                QApplication.setOverrideCursor(Qt.ArrowCursor)
                answer = self.uc.customized_question("FLO-2D", msg)
                if answer == QMessageBox.No:
                    QApplication.restoreOverrideCursor()
                    return
                else:
                    QApplication.restoreOverrideCursor()

            # Check FLOPRO.exe version to determine RAINCELL.DAT format
            flopro_dir = s.value("FLO-2D/last_flopro")
            flo2d_release_date = False
            if flopro_dir is not None:
                if os.path.isfile(flopro_dir + "/FLOPRO.exe"):
                    flo2d_release_date = get_flo2dpro_release_date(flopro_dir + "/FLOPRO.exe")
                elif os.path.isfile(flopro_dir + "/FLOPRO_Demo.exe"):
                    flo2d_release_date = get_flo2dpro_release_date(flopro_dir + "/FLOPRO_Demo.exe")
            else:
                return False

            new_raincell_format = False
            new_raincell_format_release_date = "2024-08-01"
            target_date = datetime.strptime(new_raincell_format_release_date, "%Y-%m-%d")
            flo2d_release_date = datetime.strptime(flo2d_release_date, "%Y-%m-%d")
            if flo2d_release_date >= target_date:
                new_raincell_format = True

            title = "Select RAINCELL format to export"

            msg = "Select the desired RAINCELL.DAT format. \n\n" \
                  "New RAINCELL.DAT: Suggested for a smaller file size. \n" \
                  "Old RAINCELL.DAT: Use this format if your FLOPRO.exe build is earlier than 23.10.25.\n"

            if not new_raincell_format:
                msg += "\nYour current version of FLOPRO.exe does not support the new RAINCELL.DAT format. Please " \
                       "contact the FLO-2D team to update your FLOPRO.exe build."

            msg_box = QMessageBox()

            # Set the title for the message box
            msg_box.setWindowTitle(title)

            # Set the text for the message box
            msg_box.setText(msg)

            # Add buttons to the message box
            button2 = msg_box.addButton("New RAINCELL.DAT", QMessageBox.ActionRole)
            button3 = msg_box.addButton("Old RAINCELL.DAT", QMessageBox.ActionRole)
            if not new_raincell_format:
                button2.setEnabled(False)
            button4 = msg_box.addButton("Cancel", QMessageBox.ActionRole)

            # Set the icon for the message box
            msg_box.setIcon(QMessageBox.Information)

            # Display the message box and wait for the user to click a button
            QApplication.restoreOverrideCursor()
            msg_box.exec_()

            # New RAINCELL.DAT
            if msg_box.clickedButton() == button2:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                head_sql = """SELECT rainintime, irinters, timestamp FROM raincell LIMIT 1;"""
                if not subdomain:
                    data_sql = """SELECT rrgrid, iraindum FROM raincell_data ORDER BY time_interval, rrgrid;"""
                else:
                    data_sql = f"""
                    SELECT
                        md.domain_cell, 
                        rd.iraindum 
                    FROM 
                        raincell_data AS rd
                    JOIN
                        schema_md_cells md ON rd.rrgrid = md.grid_fid
                    WHERE 
                        md.domain_fid = {subdomain}
                    ORDER BY rd.time_interval, md.domain_cell;
                    """
                size_sql = """SELECT COUNT(iraindum) FROM raincell_data"""
                line1 = "{0} {1} {2}\n"
                line2 = "{0} {1}\n"

                grid_lyr = self.lyrs.data["grid"]["qlyr"]
                n_cells = number_of_elements(self.gutils, grid_lyr)

                raincell_head = self.execute(head_sql).fetchone()
                raincell_rows = self.execute(data_sql)
                raincell_size = self.execute(size_sql).fetchone()[0]

                with open(raincell, "w") as r:
                    r.write(line1.format(*raincell_head))
                    progDialog = QProgressDialog("Exporting RealTime Rainfall (.DAT)...", None, 0, int(raincell_size))
                    progDialog.setModal(True)
                    progDialog.setValue(0)
                    progDialog.show()
                    i = 0

                    for row in raincell_rows:
                        # Check if it is the last grid element -> Needs to be printed every single interval
                        if row[0] == n_cells:
                            if row[1] is None:
                                r.write(line2.format(row[0], "0"))
                            else:
                                r.write(line2.format(row[0], "{0:.4f}".format(float(row[1]))))
                        elif row[1] is None or row[1] == 0:
                            pass
                        else:
                            r.write(line2.format(row[0], "{0:.4f}".format(float(row[1]))))
                        progDialog.setValue(i)
                        i += 1
                return True

            # Old RAINCELL.DAT
            elif msg_box.clickedButton() == button3:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                head_sql = """SELECT rainintime, irinters, timestamp FROM raincell LIMIT 1;"""
                if not subdomain:
                    data_sql = """SELECT rrgrid, iraindum FROM raincell_data ORDER BY time_interval, rrgrid;"""
                else:
                    data_sql = f"""
                    SELECT
                        md.domain_cell, 
                        rd.iraindum 
                    FROM 
                        raincell_data AS rd
                    JOIN
                        schema_md_cells md ON rd.rrgrid = md.grid_fid
                    WHERE 
                        md.domain_fid = {subdomain}
                    ORDER BY rd.time_interval, md.domain_cell;
                    """
                size_sql = """SELECT COUNT(iraindum) FROM raincell_data"""
                line1 = "{0} {1} {2}\n"
                line2 = "{0} {1}\n"

                raincell_head = self.execute(head_sql).fetchone()
                raincell_rows = self.execute(data_sql)
                raincell_size = self.execute(size_sql).fetchone()[0]

                with open(raincell, "w") as r:
                    r.write(line1.format(*raincell_head))
                    progDialog = QProgressDialog("Exporting RealTime Rainfall (.DAT)...", None, 0, int(raincell_size))
                    progDialog.setModal(True)
                    progDialog.setValue(0)
                    progDialog.show()
                    i = 0
                    for row in raincell_rows:
                        if row[1] is None:
                            r.write(line2.format(row[0], "0"))
                        else:
                            # r.write(line2.format(*row))
                            r.write(line2.format(row[0], "{0:.4f}".format(float(row[1]))))
                            # r.write(tline.format('{0:.3f}'.format(float(x)), '{0:.3f}'.format(float(y)), '{0:.2f}'.format(elev)))
                        progDialog.setValue(i)
                        i += 1

                return True

            # Close button
            elif msg_box.clickedButton() == button4:
                self.uc.bar_info("Export RealTime Rainfall canceled!")
                self.uc.log_info("Export RealTime Rainfall canceled!")
                return

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("Exporting RAINCELL.DAT failed!.\n", e)
            self.uc.log_info("Exporting RAINCELL.DAT failed!")
            return False
        finally:
            QApplication.restoreOverrideCursor()

    def export_raincell_hdf5(self, subdomain):
        try:
            if self.is_table_empty("raincell_data"):
                return False

            project_dir = os.path.dirname(self.parser.hdf5_filepath)
            self.uc.log_info(str(project_dir))

            raincell = os.path.join(project_dir, "RAINCELL.HDF5")
            if os.path.exists(raincell):
                msg = f"There is an existing RAINCELL.HDF5 file at: \n\n{project_dir}\n\n"
                msg += "Would you like to overwrite it?"
                QApplication.restoreOverrideCursor()
                answer = self.uc.customized_question("FLO-2D", msg)
                if answer == QMessageBox.No:
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    return
                else:
                    QApplication.setOverrideCursor(Qt.WaitCursor)

            qry_header = "SELECT rainintime, irinters, timestamp FROM raincell LIMIT 1;"
            header = self.gutils.execute(qry_header).fetchone()
            if header:
                rainintime, irinters, timestamp = header
                header_data = [rainintime, irinters, timestamp]
                if not subdomain:
                    qry_data = "SELECT iraindum FROM raincell_data"
                    qry_size = "SELECT COUNT(iraindum) FROM raincell_data"
                else:
                    qry_data = "SELECT iraindum FROM raincell_data AS rd JOIN schema_md_cells md ON rd.rrgrid = md.grid_fid"
                    qry_size = f"SELECT COUNT(iraindum) FROM raincell_data AS rd JOIN schema_md_cells md ON rd.rrgrid = md.grid_fid WHERE md.domain_fid = {subdomain}"
                qry_timeinterval = "SELECT DISTINCT time_interval FROM raincell_data"
                hdf_processor = HDFProcessor(raincell, self.iface)
                hdf_processor.export_rainfall_to_binary_hdf5(header_data, qry_data, qry_size, qry_timeinterval, subdomain)

                return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("Error while exporting RAINCELL data to hdf5 file!\n", e)
            self.uc.log_info("Error while exporting RAINCELL data to hdf5 file!")
            return False

    def export_raincellraw(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_raincellraw_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_raincellraw_hdf5(subdomain)

    def export_raincellraw_dat(self, outdir, subdomain):
        try:
            if self.is_table_empty("raincellraw") or self.is_table_empty("flo2d_raincell"):
                return False

            raincellraw = os.path.join(outdir, "RAINCELLRAW.DAT")

            head_sql = """SELECT rainintime, irinters FROM raincell LIMIT 1;"""
            data_sql = """SELECT nxrdgd, r_time, rrgrid FROM raincellraw ORDER BY nxrdgd, r_time;"""
            size_sql = """SELECT COUNT(fid) FROM raincellraw"""
            line1 = "{0}\t{1}\n"
            line2 = "N\t{0}\n"
            line3 = "R\t{0}\t{1}\n"

            raincellraw_head = self.execute(head_sql).fetchone()
            raincellraw_rows = self.execute(data_sql)
            raincellraw_size = self.execute(size_sql).fetchone()[0]

            with open(raincellraw, "w") as r:
                r.write(line1.format(int(raincellraw_head[0]), int(raincellraw_head[1])))

                progDialog = QProgressDialog("Exporting Cumulative Realtime Rainfall (.DAT)...", None, 0, int(raincellraw_size))
                progDialog.setModal(True)
                progDialog.setValue(0)
                progDialog.show()
                i = 0

                previous_nxrdgd = None
                for row in raincellraw_rows:
                    nxrdgd, r_time, rrgrid = row
                    if nxrdgd != previous_nxrdgd:
                        r.write(line2.format(nxrdgd))
                        previous_nxrdgd = nxrdgd
                    r.write(line3.format(r_time, rrgrid))
                    progDialog.setValue(i)
                    i += 1

            if not subdomain:
                data_sql = """SELECT iraindum, nxrdgd FROM flo2d_raincell ORDER BY iraindum, nxrdgd;"""
                size_sql = """SELECT COUNT(fid) FROM flo2d_raincell"""
            else:
                data_sql = f"""
                            SELECT 
                                md.domain_cell, 
                                fr.nxrdgd 
                            FROM 
                                flo2d_raincell AS fr
                            JOIN 
                                schema_md_cells md ON fr.iraindum = md.grid_fid
                            WHERE
                                md.domain_fid = {subdomain}
                            ORDER BY 
                                md.domain_cell, fr.nxrdgd;
                            """
                size_sql = f"""
                            SELECT 
                                COUNT(fr.fid) 
                            FROM 
                                flo2d_raincell AS fr
                            JOIN 
                                schema_md_cells md ON fr.iraindum = md.grid_fid
                            WHERE
                                md.domain_fid = {subdomain};"""
            line = "{0}\t{1}\n"

            flo2draincell_rows = self.execute(data_sql)
            flo2draincell_size = self.execute(size_sql).fetchone()[0]

            flo2draincell = os.path.join(outdir, "FLO2DRAINCELL.DAT")

            with open(flo2draincell, "w") as r:

                progDialog = QProgressDialog("Exporting Intersected Realtime Rainfall (.DAT)...", None, 0,
                                             int(flo2draincell_size))
                progDialog.setModal(True)
                progDialog.setValue(0)
                progDialog.show()
                i = 0

                for row in flo2draincell_rows:
                    iraindum, nxrdgd = row
                    r.write(line.format(iraindum, nxrdgd))
                    progDialog.setValue(i)
                    i += 1

            return True

        except Exception as e:
            self.uc.show_error("Exporting RAINCELLRAW.DAT and FLO2DRAINCELL.DAT failed!.\n", e)
            self.uc.log_info("Exporting RAINCELLRAW.DAT and FLO2DRAINCELL.DAT failed!")
            return False

    def export_raincellraw_hdf5(self, subdomain):

        try:
            if self.is_table_empty("raincellraw") or self.is_table_empty("flo2d_raincell"):
                return False

            project_dir = os.path.dirname(self.parser.hdf5_filepath)
            self.uc.log_info(str(project_dir))

            raincellraw = os.path.join(project_dir, "RAINCELLRAW.HDF5")
            if os.path.exists(raincellraw):
                msg = f"There is an existing RAINCELLRAW.HDF5 file at: \n\n{project_dir}\n\n"
                msg += "Would you like to overwrite it?"
                QApplication.restoreOverrideCursor()
                answer = self.uc.customized_question("FLO-2D", msg)
                if answer == QMessageBox.No:
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    return
                else:
                    QApplication.setOverrideCursor(Qt.WaitCursor)

            qry_header = "SELECT rainintime, irinters FROM raincell LIMIT 1;"
            header = self.gutils.execute(qry_header).fetchone()
            if header:
                rainintime, irinters = header
                header_data = [rainintime, irinters]
                raincellraw_qry_data = "SELECT nxrdgd, r_time, rrgrid FROM raincellraw ORDER BY nxrdgd, r_time"
                raincellraw_size = "SELECT COUNT(fid) FROM raincellraw"
                if not subdomain:
                    flo2draincell_qry_data = "SELECT iraindum, nxrdgd FROM flo2d_raincell ORDER BY iraindum, nxrdgd"
                    flo2draincell_size = "SELECT COUNT(fid) FROM flo2d_raincell"
                else:
                    flo2draincell_qry_data = f"""
                    SELECT 
                        md.domain_cell, 
                        fr.nxrdgd 
                    FROM 
                        flo2d_raincell AS fr
                    JOIN 
                        schema_md_cells md ON fr.iraindum = md.grid_fid
                    WHERE 
                        md.domain_fid = {subdomain}
                    ORDER BY 
                        md.domain_cell, fr.nxrdgd;"""
                    flo2draincell_size = f"""
                    SELECT 
                        COUNT(fr.fid) 
                    FROM 
                        flo2d_raincell AS fr
                    JOIN 
                        schema_md_cells md ON fr.iraindum = md.grid_fid
                    WHERE 
                        md.domain_fid = {subdomain};
                        """
                hdf_processor = HDFProcessor(raincellraw, self.iface)
                hdf_processor.export_rainfallraw_to_binary_hdf5(header_data, raincellraw_qry_data, raincellraw_size, flo2draincell_qry_data, flo2draincell_size)

                return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("Error while exporting RAINCELL data to hdf5 file!\n", e)
            self.uc.log_info("Error while exporting RAINCELL data to hdf5 file!")
            return False

    def export_infil(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_infil_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_infil_hdf5(subdomain)

    def export_infil_dat(self, outdir, subdomain):
        # check if there is any infiltration defined.
        try:
            if self.is_table_empty("infil"):
                return False
            infil_sql = """SELECT * FROM infil;"""
            infil_r_sql = """SELECT hydcx, hydcxfinal, soildepthcx FROM infil_chan_seg ORDER BY chan_seg_fid, fid;"""
            if not subdomain:
                green_sql = """SELECT grid_fid, hydc, soils, dtheta, abstrinf, rtimpf, soil_depth FROM infil_cells_green ORDER by grid_fid;"""
                scs_sql = """SELECT grid_fid,scsn FROM infil_cells_scs ORDER BY grid_fid;"""
                horton_sql = """SELECT grid_fid, fhorti, fhortf, deca FROM infil_cells_horton ORDER BY grid_fid;"""
                chan_sql = """SELECT grid_fid, hydconch FROM infil_chan_elems ORDER by grid_fid;"""
            else:
                green_sql = f"""SELECT 
                                    md.domain_cell, 
                                    hydc, 
                                    soils, 
                                    dtheta, 
                                    abstrinf, 
                                    rtimpf, 
                                    soil_depth 
                                FROM 
                                    infil_cells_green AS ga
                                JOIN 
                                    schema_md_cells md ON ga.grid_fid = md.grid_fid
                                WHERE 
                                    md.domain_fid = {subdomain}"""

                scs_sql = f"""SELECT 
                                    md.domain_cell, 
                                    scsn 
                                FROM 
                                    infil_cells_scs AS scs
                                JOIN 
                                    schema_md_cells md ON scs.grid_fid = md.grid_fid
                                WHERE 
                                    md.domain_fid = {subdomain}"""

                horton_sql = f"""SELECT 
                                    md.domain_cell, 
                                    fhorti, 
                                    fhortf, 
                                    deca 
                                FROM 
                                    infil_cells_horton AS ht
                                JOIN 
                                    schema_md_cells md ON ht.grid_fid = md.grid_fid
                                WHERE 
                                    md.domain_fid = {subdomain}"""

                chan_sql = f"""SELECT 
                                md.domain_cell, 
                                hydconch 
                              FROM 
                                infil_chan_elems AS ch
                              JOIN 
                                schema_md_cells md ON ch.grid_fid = md.grid_fid
                              WHERE 
                                md.domain_fid = {subdomain}"""

            line1 = "{0}"
            line2 = "\n" + "  {}" * 6
            line2h = "\n{0}"
            line3 = "\n" + "  {}" * 3
            line4 = "\n{0}"
            line4ab = "\nR  {0}  {1}  {2}"
            line5 = "\n{0}  {1}"
            line6 = "\nF {0:<8} {1:<7.4f} {2:<7.4f} {3:<7.4f} {4:<7.4f} {5:<7.4f} {6:<7.4f}"
            #         line6 = '\n' + 'F' + '  {}' * 7
            line7 = "\nS  {0}  {1}"
            line8 = "\nC  {0}  {1}"
            line9 = "\nI {0:<7.4f} {1:<7.4f} {2:<7.4f}"
            line10 = "\nH  {0:<8} {1:<7.4f} {2:<7.4f} {3:<7.4f}"

            infil_row = self.execute(infil_sql).fetchone()
            if infil_row is None:
                return False
            else:
                pass
            infil = os.path.join(outdir, "INFIL.DAT")
            with open(infil, "w") as i:
                gen = [x if x is not None else "" for x in infil_row[1:]]
                v1, v2, v3, v4, v5, v9, v2h = (
                    gen[0],
                    gen[1:7],
                    gen[7:10],
                    gen[10:11],
                    gen[11:13],
                    gen[13:16],
                    gen[16]
                )
                i.write(line1.format(v1))
                if v1 == 1 or v1 == 3:
                    i.write(line2.format(*v2))
                    i.write(line3.format(*v3))
                    if v2[5] == 1:
                        i.write(line4.format(*v4))
                    #                     for val, line in zip([v2, v3, v4], [line2, line3, line4]):
                    # #                         if any(val) is True:
                    #                             i.write(line.format(*val))
                    # #                         else:
                    # #                             pass
                    for row in self.execute(infil_r_sql):
                        row = [x if x is not None else "" for x in row]
                        i.write(line4ab.format(*row))
                if v1 == 2 or v1 == 3:
                    if any(v5) is True:
                        i.write(line5.format(*v5))
                    else:
                        pass
                for row in self.execute(green_sql):
                    i.write(line6.format(*row))
                for row in self.execute(scs_sql):
                    i.write(line7.format(*row))
                for row in self.execute(chan_sql):
                    i.write(line8.format(*row))
                if any(v9) is True:
                    i.write(line2h.format(str(v2h)))
                    i.write(line9.format(*v9))
                else:
                    pass
                for row in self.execute(horton_sql):
                    i.write(line10.format(*row))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1559: exporting INFIL.DAT failed!.\n", e)
            return False

    def export_infil_hdf5(self, subdomain):
        """
        Function to export infiltration data to HDF5
        """
        # check if there is any infiltration defined.
        # try:
        if self.is_table_empty("infil"):
            return False
        infil_sql = """SELECT * FROM infil;"""
        infil_r_sql = """SELECT hydcx, hydcxfinal, soildepthcx FROM infil_chan_seg ORDER BY chan_seg_fid, fid;"""
        if not subdomain:
            green_sql = """SELECT grid_fid, hydc, soils, dtheta, abstrinf, rtimpf, soil_depth FROM infil_cells_green ORDER by grid_fid;"""
            scs_sql = """SELECT grid_fid,scsn FROM infil_cells_scs ORDER BY grid_fid;"""
            horton_sql = """SELECT grid_fid, fhorti, fhortf, deca FROM infil_cells_horton ORDER BY grid_fid;"""
            chan_sql = """SELECT grid_fid, hydconch FROM infil_chan_elems ORDER by grid_fid;"""
        else:
            green_sql = f"""SELECT 
                                md.domain_cell, 
                                hydc, 
                                soils, 
                                dtheta, 
                                abstrinf, 
                                rtimpf, 
                                soil_depth 
                            FROM 
                                infil_cells_green AS ga
                            JOIN 
                                schema_md_cells md ON ga.grid_fid = md.grid_fid
                            WHERE 
                                md.domain_fid = {subdomain}"""

            scs_sql = f"""SELECT 
                                md.domain_cell, 
                                scsn 
                            FROM 
                                infil_cells_scs AS scs
                            JOIN 
                                schema_md_cells md ON scs.grid_fid = md.grid_fid
                            WHERE 
                                md.domain_fid = {subdomain}"""

            horton_sql = f"""SELECT 
                                md.domain_cell, 
                                fhorti, 
                                fhortf, 
                                deca 
                            FROM 
                                infil_cells_horton AS ht
                            JOIN 
                                schema_md_cells md ON ht.grid_fid = md.grid_fid
                            WHERE 
                                md.domain_fid = {subdomain}"""

            chan_sql = f"""SELECT 
                            md.domain_cell, 
                            hydconch 
                          FROM 
                            infil_chan_elems AS ch
                          JOIN 
                            schema_md_cells md ON ch.grid_fid = md.grid_fid
                          WHERE 
                            md.domain_fid = {subdomain}"""

        # line1 = "{0}"
        # line2 = "\n" + "  {}" * 6
        # line3 = "\n" + "  {}" * 3
        # line4 = "\n{0}"
        line4ab = "\n{0}  {1}  {2}"
        # line5 = "\n{0}  {1}"
        line6 = "\n{0:<8} {1:<7.4f} {2:<7.4f} {3:<7.4f} {4:<7.4f} {5:<7.4f} {6:<7.4f}"
        line7 = "\n{0}  {1}"
        line8 = "\n{0}  {1}"
        # line9 = "\nI {0:<7.4f} {1:<7.4f} {2:<7.4f}"
        line10 = "\n{0:<8} {1:<7.4f} {2:<7.4f} {3:<7.4f}"

        infil_row = self.execute(infil_sql).fetchone()
        if infil_row is None:
            return False
        else:
            pass

        infil_group = self.parser.infil_group
        infil_group.create_dataset('INFIL_METHOD', [])

        gen = [x if x is not None else "" for x in infil_row[1:]]
        v1, v2, v3, v4, v5, v9, v2h = (
            gen[0],
            gen[1:7],
            gen[7:10],
            gen[10:11],
            gen[11:13],
            gen[13:16],
            gen[16]
        )

        infil_group.datasets["INFIL_METHOD"].data.append(v1)

        # GA
        if v1 == 1:
            infil_group.create_dataset('INFIL_GA_GLOBAL', [])
            # v2: ABSTR SATI SATF POROS SOILD INFCHAN
            for var in v2:
                infil_group.datasets["INFIL_GA_GLOBAL"].data.append(var)
            # v3: HYDCALL SOILALL HYDCADJ
            for var in v3:
                infil_group.datasets["INFIL_GA_GLOBAL"].data.append(var)

            ga_cells_row = self.execute(green_sql).fetchone()
            if ga_cells_row is not None:
                infil_group.create_dataset('INFIL_GA_CELLS', [])
                for row in self.execute(green_sql):
                    infil_group.datasets["INFIL_GA_CELLS"].data.append(create_array(line6, 7, np.float64, row))

            # v2[5]: INFCHAN
            if v2[5] == 1:
                infil_group.create_dataset('INFIL_CHAN_GLOBAL', [])
                infil_group.datasets["INFIL_CHAN_GLOBAL"].data.append(v4)

                infil_chan_seg = self.execute(infil_r_sql).fetchone()
                if infil_chan_seg is not None:
                    infil_group.create_dataset('INFIL_CHAN_SEG', [])
                    for row in self.execute(infil_r_sql):
                        row = [x if (x is not None and x != "") else -9999 for x in row]
                        infil_group.datasets["INFIL_CHAN_SEG"].data.append(
                            create_array(line4ab, 3, np.float64, tuple(row)))

                infil_chan_elems = self.execute(chan_sql).fetchone()
                if infil_chan_elems is not None:
                    infil_group.create_dataset('INFIL_CHAN_ELEMS', [])
                    for row in self.execute(chan_sql):
                        infil_group.datasets["INFIL_CHAN_ELEMS"].data.append(create_array(line8, 2, np.float64, row))

        if v1 == 2:
            infil_group.create_dataset('INFIL_SCS_GLOBAL', [])
            # v5: SCSNALL ABSTR1
            for var in v5:
                infil_group.datasets["INFIL_SCS_GLOBAL"].data.append(var
                                                                     )
            scs_cells_row = self.execute(scs_sql).fetchone()
            if scs_cells_row is not None:
                infil_group.create_dataset('INFIL_SCS_CELLS', [])
                for row in self.execute(scs_sql):
                    infil_group.datasets["INFIL_SCS_CELLS"].data.append(create_array(line7, 2, np.float64, row))

        if v1 == 3:
            infil_group.create_dataset('INFIL_GA_GLOBAL', [])
            # v2: ABSTR SATI SATF POROS SOILD INFCHAN
            for var in v2:
                infil_group.datasets["INFIL_GA_GLOBAL"].data.append(var)
            # v3: HYDCALL SOILALL HYDCADJ
            for var in v3:
                infil_group.datasets["INFIL_GA_GLOBAL"].data.append(var)

            ga_cells_row = self.execute(green_sql).fetchone()
            if ga_cells_row is not None:
                infil_group.create_dataset('INFIL_GA_CELLS', [])
                for row in self.execute(green_sql):
                    infil_group.datasets["INFIL_GA_CELLS"].data.append(create_array(line6, 7, np.float64, row))

            infil_group.create_dataset('INFIL_SCS_GLOBAL', [])
            # v5: SCSNALL ABSTR1
            for var in v5:
                infil_group.datasets["INFIL_SCS_GLOBAL"].data.append(var
                                                                     )
            scs_cells_row = self.execute(scs_sql).fetchone()
            if scs_cells_row is not None:
                infil_group.create_dataset('INFIL_SCS_CELLS', [])
                for row in self.execute(scs_sql):
                    infil_group.datasets["INFIL_SCS_CELLS"].data.append(create_array(line7, 2, np.float64, row))

            # v2[5]: INFCHAN
            if v2[5] == 1:
                infil_group.create_dataset('INFIL_CHAN_GLOBAL', [])
                infil_group.datasets["INFIL_CHAN_GLOBAL"].data.append(v4)

                infil_chan_seg = self.execute(infil_r_sql).fetchone()
                if infil_chan_seg is not None:
                    infil_group.create_dataset('INFIL_CHAN_SEG', [])
                    for row in self.execute(infil_r_sql):
                        row = [x if (x is not None and x != "") else -9999 for x in row]
                        infil_group.datasets["INFIL_CHAN_SEG"].data.append(
                            create_array(line4ab, 3, np.float64, tuple(row)))

                infil_chan_elems = self.execute(chan_sql).fetchone()
                if infil_chan_elems is not None:
                    infil_group.create_dataset('INFIL_CHAN_ELEMS', [])
                    for row in self.execute(chan_sql):
                        infil_group.datasets["INFIL_CHAN_ELEMS"].data.append(create_array(line8, 2, np.float64, row))

        if v1 == 4:
            infil_group.create_dataset('INFIL_HORTON_GLOBAL', [])
            for var in v9:
                infil_group.datasets["INFIL_HORTON_GLOBAL"].data.append(var)
            infil_group.datasets["INFIL_HORTON_GLOBAL"].data.append(v2h)
            horton_cells_row = self.execute(horton_sql).fetchone()
            if horton_cells_row is not None:
                infil_group.create_dataset('INFIL_HORTON_CELLS', [])
                for row in self.execute(horton_sql):
                    infil_group.datasets["INFIL_HORTON_CELLS"].data.append(create_array(line10, 4, np.float64, row))

        self.parser.write_groups(infil_group)
        return True

        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error("ERROR 101218.1559: exporting INFIL.DAT failed!.\n", e)
        #     return False

    def export_evapor(self, output=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_evapor_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_evapor_hdf5()

    def export_evapor_hdf5(self):
        """
        Function to export evaporation data to hdf5 file
        """
        try:
            if self.is_table_empty("evapor"):
                return False
            evapor_sql = """SELECT ievapmonth, iday, clocktime FROM evapor;"""
            evapor_month_sql = """SELECT month, monthly_evap FROM evapor_monthly ORDER BY fid;"""
            evapor_hour_sql = """SELECT hourly_evap FROM evapor_hourly WHERE month = ? ORDER BY fid;"""

            head = "{0}   {1}   {2:.2f}\n"
            monthly = "  {0}  {1:.2f}\n"
            hourly = "    {0:.4f}\n"

            evapor_row = self.execute(evapor_sql).fetchone()
            if evapor_row is None:
                return False
            else:
                pass

            evap_group = self.parser.evap_group
            evap_group.create_dataset('EVAPOR', [])
            # evapor = os.path.join(outdir, "EVAPOR.DAT")

            evap_group.datasets["EVAPOR"].data.append(create_array(head, 3, np.bytes_, evapor_row))
            # e.write(head.format(*evapor_row))
            for mrow in self.execute(evapor_month_sql):
                month = mrow[0]
                evap_group.datasets["EVAPOR"].data.append(create_array(monthly, 3, np.bytes_, mrow))
                # e.write(monthly.format(*mrow))
                for hrow in self.execute(evapor_hour_sql, (month,)):
                    evap_group.datasets["EVAPOR"].data.append(create_array(hourly, 3, np.bytes_, hrow))
                    # e.write(hourly.format(*hrow))

            self.parser.write_groups(evap_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1544: exporting EVAPOR.DAT failed!.\n", e)
            return False

    def export_evapor_dat(self, outdir):
        # check if there is any evaporation defined.
        try:
            if self.is_table_empty("evapor"):
                return False
            evapor_sql = """SELECT ievapmonth, iday, clocktime FROM evapor;"""
            evapor_month_sql = """SELECT month, monthly_evap FROM evapor_monthly ORDER BY fid;"""
            evapor_hour_sql = """SELECT hourly_evap FROM evapor_hourly WHERE month = ? ORDER BY fid;"""

            head = "{0}   {1}   {2:.2f}\n"
            monthly = "  {0}  {1:.2f}\n"
            hourly = "    {0:.4f}\n"

            evapor_row = self.execute(evapor_sql).fetchone()
            if evapor_row is None:
                return False
            else:
                pass
            evapor = os.path.join(outdir, "EVAPOR.DAT")
            with open(evapor, "w") as e:
                e.write(head.format(*evapor_row))
                for mrow in self.execute(evapor_month_sql):
                    month = mrow[0]
                    e.write(monthly.format(*mrow))
                    for hrow in self.execute(evapor_hour_sql, (month,)):
                        e.write(hourly.format(*hrow))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1544: exporting EVAPOR.DAT failed!.\n", e)
            return False

    def export_chan(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_chan_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_chan_hdf5(subdomain)

    def export_chan_hdf5(self, subdomain):
        """
        Function to export channel data to hdf5
        """
        if self.is_table_empty("chan"):
            return False

        chan_wsel_sql = """SELECT istart, wselstart, iend, wselend FROM chan_wsel ORDER BY fid;"""
        chan_conf_sql = """SELECT chan_elem_fid FROM chan_confluences ORDER BY fid;"""

        if not subdomain:
            chan_sql = """SELECT fid, depinitial, froudc, roughadj, isedn, ibaseflow FROM chan ORDER BY fid;"""
            chan_elems_sql = (
                """SELECT fid, rbankgrid, fcn, xlen, type FROM chan_elems WHERE seg_fid = ? ORDER BY nr_in_seg;"""
            )
            chan_r_sql = """SELECT elem_fid, bankell, bankelr, fcw, fcd FROM chan_r WHERE elem_fid = ?;"""
            chan_v_sql = """SELECT elem_fid, bankell, bankelr, fcd, a1, a2, b1, b2, c1, c2,
                                                          excdep, a11, a22, b11, b22, c11, c22 FROM chan_v WHERE elem_fid = ?;"""
            chan_t_sql = """SELECT elem_fid, bankell, bankelr, fcw, fcd, zl, zr FROM chan_t WHERE elem_fid = ?;"""
            chan_n_sql = """SELECT elem_fid, nxsecnum FROM chan_n WHERE elem_fid = ?;"""
            chan_e_sql = """SELECT grid_fid FROM noexchange_chan_cells ORDER BY fid;"""
        else:
            subdomain_fids = self.execute(f"""
                       SELECT 
                           DISTINCT(c.fid)
                       FROM 
                           chan AS c
                       JOIN
                           chan_elems ce ON c.fid = ce.seg_fid 
                       JOIN
                           schema_md_cells left_grid_md ON ce.fid = left_grid_md.grid_fid AND left_grid_md.domain_fid = {subdomain}
                       JOIN
                           schema_md_cells right_grid_md ON ce.rbankgrid = right_grid_md.grid_fid AND right_grid_md.domain_fid = {subdomain}
                   """).fetchall()
            fid_list = [fid[0] for fid in subdomain_fids]
            placeholders = ",".join(str(fid) for fid in fid_list)
            chan_sql = f"""SELECT fid, depinitial, froudc, roughadj, isedn, ibaseflow FROM chan WHERE fid IN ({placeholders}) ORDER BY fid;"""
            chan_elems_sql = f"""
                       SELECT
                           left_grid_md.domain_cell AS left_grid,
                           right_grid_md.domain_cell AS right_grid,
                           ce.fcn,
                           ce.xlen,
                           ce.type
                       FROM
                           chan_elems AS ce
                       JOIN
                           schema_md_cells left_grid_md ON ce.fid = left_grid_md.grid_fid AND left_grid_md.domain_fid = {subdomain}
                       JOIN
                           schema_md_cells right_grid_md ON ce.rbankgrid = right_grid_md.grid_fid AND right_grid_md.domain_fid = {subdomain}
                       WHERE
                           ce.seg_fid = ?
                       ORDER BY ce.nr_in_seg;
                       """

            chan_r_sql = f"""
                       SELECT 
                           md.domain_cell, 
                           cr.bankell, 
                           cr.bankelr, 
                           cr.fcw, 
                           cr.fcd 
                       FROM 
                           chan_r AS cr
                       JOIN
                           schema_md_cells md ON cr.elem_fid = md.grid_fid
                       WHERE 
                           md.domain_cell = ? AND md.domain_fid = {subdomain};
                       """

            chan_v_sql = f"""
                       SELECT 
                           md.domain_cell, 
                           cv.bankell, 
                           cv.bankelr, 
                           cv.fcd, 
                           cv.a1, 
                           cv.a2, 
                           cv.b1, 
                           cv.b2, 
                           cv.c1, 
                           cv.c2,
                           cv.excdep, 
                           cv.a11, 
                           cv.a22, 
                           cv.b11, 
                           cv.b22, 
                           cv.c11, 
                           cv.c22 
                       FROM 
                           chan_v AS cv
                       JOIN
                           schema_md_cells md ON cv.elem_fid = md.grid_fid
                       WHERE 
                           md.domain_cell = ? AND md.domain_fid = {subdomain};
                           """

            chan_t_sql = f"""
                       SELECT 
                           md.domain_cell, 
                           ct.bankell, 
                           ct.bankelr, 
                           ct.fcw, 
                           ct.fcd, 
                           ct.zl, 
                           ct.zr 
                       FROM 
                           chan_t AS ct
                       JOIN
                           schema_md_cells md ON ct.elem_fid = md.grid_fid
                       WHERE 
                           md.domain_cell = ? AND md.domain_fid = {subdomain};
                           """

            chan_n_sql = f"""
                       SELECT 
                           md.domain_cell, 
                           cn.nxsecnum 
                       FROM 
                           chan_n AS cn
                       JOIN
                           schema_md_cells md ON cn.elem_fid = md.grid_fid
                       WHERE 
                           md.domain_cell = ? AND md.domain_fid = {subdomain};
                           """

            chan_e_sql = f"""
                       SELECT 
                           md.domain_cell 
                       FROM 
                           noexchange_chan_cells AS ne
                       JOIN
                           schema_md_cells md ON ne.grid_fid = md.grid_fid
                       WHERE 
                           md.domain_fid = {subdomain}
                       ORDER BY ne.fid;
                       """

        segment = "{}  {}  {}  {}  {}  {}\n"
        chanbank = " {0: <10} {1}\n"

        sqls = {
            "R": [chan_r_sql, 3, 6],
            "V": [chan_v_sql, 3, 5],
            "T": [chan_t_sql, 3, 6],
            "N": [chan_n_sql, 1, 2],
        }

        chan_rows = self.execute(chan_sql).fetchall()
        if not chan_rows:
            self.gutils.set_cont_par("ICHANNEL", 0)
            return False
        else:
            self.gutils.set_cont_par("ICHANNEL", 1)

        channel_group = self.parser.channel_group
        channel_group.create_dataset('CHAN_GLOBAL', [])
        channel_group.create_dataset('CHANBANK', [])

        ISED = self.gutils.get_cont_par("ISED")

        for i, row in enumerate(chan_rows, start=1):
            row = [x if x is not None else "0" for x in row]
            fid, depinitial, froudc, roughadj, isedn, ibaseflow = row
            if float(ISED) == 0:
                isedn = -9999
            channel_group.datasets["CHAN_GLOBAL"].data.append(create_array(segment, 6, np.float64, (i, depinitial, froudc, roughadj, ibaseflow, isedn)))
            # Writes depinitial, froudc, roughadj, isedn from 'chan' table (schematic layer).
            # A single line for each channel segment.
            for elems in self.execute(
                    chan_elems_sql, (fid,)
            ):  # each 'elems' is a list [(fid, rbankgrid, fcn, xlen, type)] from
                # 'chan_elems' table (the cross sections in the schematic layer),
                #  that has the 'fid' value indicated (the channel segment id).
                elems = [
                    x if x is not None else "" for x in elems
                ]  # If 'elems' has a None in any of above values of list, replace it by ''
                (
                    eid,
                    rbank,
                    fcn,
                    xlen,
                    typ,
                ) = elems  # Separates values of list into individual variables.
                sql, fcn_idx, xlen_idx = sqls[
                    typ
                ]  # depending on 'typ' (R,V,T, or N) select sql (the SQLite SELECT statement to execute),
                # line (format to write), fcn_idx (?), and xlen_idx (?)
                res_query = self.execute(sql, (eid,)).fetchone()
                if res_query is not None:
                    res = [x if x is not None else "" for x in
                           res_query]  # 'res' is a list of values depending on 'typ' (R,V,T, or N).
                    res.insert(
                        fcn_idx, fcn
                    )  # Add 'fcn' (coming from table ´chan_elems' (cross sections) to 'res' list) in position 'fcn_idx'.
                    res.insert(
                        xlen_idx, xlen
                    )  # Add ´xlen' (coming from table ´chan_elems' (cross sections) to 'res' list in position 'xlen_idx'.

                    if typ == 'R':
                        data = ([i] + res)
                        try:
                            channel_group.datasets["CHAN_RECTANGULAR"].data.append(data)
                        except:
                            channel_group.create_dataset('CHAN_RECTANGULAR', [])
                            channel_group.datasets["CHAN_RECTANGULAR"].data.append(data)

                    if typ == 'V':
                        data = ([i] + res)
                        try:
                            channel_group.datasets["CHAN_VARIABLE"].data.append(data)
                        except:
                            channel_group.create_dataset('CHAN_VARIABLE', [])
                            channel_group.datasets["CHAN_VARIABLE"].data.append(data)

                    if typ == 'T':
                        data = ([i] + res)
                        try:
                            channel_group.datasets["CHAN_TRAPEZOIDAL"].data.append(data)
                        except:
                            channel_group.create_dataset('CHAN_TRAPEZOIDAL', [])
                            channel_group.datasets["CHAN_TRAPEZOIDAL"].data.append(data)

                    if typ == 'N':
                        data = ([i] + res)
                        try:
                            channel_group.datasets["CHAN_NATURAL"].data.append(data)
                        except:
                            channel_group.create_dataset('CHAN_NATURAL', [])
                            channel_group.datasets["CHAN_NATURAL"].data.append(data)

                    channel_group.datasets["CHANBANK"].data.append(create_array(chanbank, 2, np.int_, eid, rbank))

        segment_added = []
        for row in self.execute(chan_wsel_sql):
            if row[0] not in segment_added:
                (
                    seg_fid,
                    istart,
                    wselstart,
                    iend,
                    wselend,
                ) = row
                try:
                    channel_group.datasets["CHAN_WSE"].data.append([seg_fid, istart, wselstart, iend, wselend])
                except:
                    channel_group.create_dataset('CHAN_WSE', [])
                    channel_group.datasets["CHAN_WSE"].data.append([seg_fid, istart, wselstart, iend, wselend])
                finally:
                    segment_added.append(row[0])

        for row in self.execute(chan_conf_sql):
            (
                conf_fid,
                typ,
                chan_elem_fid,
            ) = row

            try:
                channel_group.datasets["CONFLUENCES"].data.append([conf_fid, typ, chan_elem_fid])
            except:
                channel_group.create_dataset('CONFLUENCES', [])
                channel_group.datasets["CONFLUENCES"].data.append([conf_fid, typ, chan_elem_fid])

        for row in self.execute(chan_e_sql):
            try:
                channel_group.datasets["NOEXCHANGE"].data.append(row[0])
            except:
                channel_group.create_dataset('NOEXCHANGE', [])
                channel_group.datasets["NOEXCHANGE"].data.append(row[0])

        self.parser.write_groups(channel_group)
        return True

    def export_chan_dat(self, outdir, subdomain):
        # check if there are any channels defined.
        # try:
        if self.is_table_empty("chan"):
            return False

        chan_wsel_sql = """SELECT istart, wselstart, iend, wselend FROM chan_wsel ORDER BY fid;"""
        chan_conf_sql = """SELECT chan_elem_fid FROM chan_confluences ORDER BY fid;"""

        if not subdomain:
            chan_sql = """SELECT fid, depinitial, froudc, roughadj, isedn, ibaseflow FROM chan ORDER BY fid;"""
            chan_elems_sql = (
                """SELECT fid, rbankgrid, fcn, xlen, type FROM chan_elems WHERE seg_fid = ? ORDER BY nr_in_seg;"""
            )
            chan_r_sql = """SELECT elem_fid, bankell, bankelr, fcw, fcd FROM chan_r WHERE elem_fid = ?;"""
            chan_v_sql = """SELECT elem_fid, bankell, bankelr, fcd, a1, a2, b1, b2, c1, c2,
                                                   excdep, a11, a22, b11, b22, c11, c22 FROM chan_v WHERE elem_fid = ?;"""
            chan_t_sql = """SELECT elem_fid, bankell, bankelr, fcw, fcd, zl, zr FROM chan_t WHERE elem_fid = ?;"""
            chan_n_sql = """SELECT elem_fid, nxsecnum FROM chan_n WHERE elem_fid = ?;"""
            chan_e_sql = """SELECT grid_fid FROM noexchange_chan_cells ORDER BY fid;"""
        else:
            subdomain_fids = self.execute(f"""
                SELECT 
                    DISTINCT(c.fid)
                FROM 
                    chan AS c
                JOIN
                    chan_elems ce ON c.fid = ce.seg_fid 
                JOIN
                    schema_md_cells left_grid_md ON ce.fid = left_grid_md.grid_fid AND left_grid_md.domain_fid = {subdomain}
                JOIN
                    schema_md_cells right_grid_md ON ce.rbankgrid = right_grid_md.grid_fid AND right_grid_md.domain_fid = {subdomain}
            """).fetchall()
            fid_list = [fid[0] for fid in subdomain_fids]
            placeholders = ",".join(str(fid) for fid in fid_list)
            chan_sql = f"""SELECT fid, depinitial, froudc, roughadj, isedn, ibaseflow FROM chan WHERE fid IN ({placeholders}) ORDER BY fid;"""
            chan_elems_sql = f"""
                SELECT
                    left_grid_md.domain_cell AS left_grid,
                    right_grid_md.domain_cell AS right_grid,
                    ce.fcn,
                    ce.xlen,
                    ce.type
                FROM
                    chan_elems AS ce
                JOIN
                    schema_md_cells left_grid_md ON ce.fid = left_grid_md.grid_fid AND left_grid_md.domain_fid = {subdomain}
                JOIN
                    schema_md_cells right_grid_md ON ce.rbankgrid = right_grid_md.grid_fid AND right_grid_md.domain_fid = {subdomain}
                WHERE
                    ce.seg_fid = ?
                ORDER BY ce.nr_in_seg;
                """

            chan_r_sql = f"""
                SELECT 
                    md.domain_cell, 
                    cr.bankell, 
                    cr.bankelr, 
                    cr.fcw, 
                    cr.fcd 
                FROM 
                    chan_r AS cr
                JOIN
                    schema_md_cells md ON cr.elem_fid = md.grid_fid
                WHERE 
                    md.domain_cell = ? AND md.domain_fid = {subdomain};
                """

            chan_v_sql = f"""
                SELECT 
                    md.domain_cell, 
                    cv.bankell, 
                    cv.bankelr, 
                    cv.fcd, 
                    cv.a1, 
                    cv.a2, 
                    cv.b1, 
                    cv.b2, 
                    cv.c1, 
                    cv.c2,
                    cv.excdep, 
                    cv.a11, 
                    cv.a22, 
                    cv.b11, 
                    cv.b22, 
                    cv.c11, 
                    cv.c22 
                FROM 
                    chan_v AS cv
                JOIN
                    schema_md_cells md ON cv.elem_fid = md.grid_fid
                WHERE 
                    md.domain_cell = ? AND md.domain_fid = {subdomain};
                    """

            chan_t_sql = f"""
                SELECT 
                    md.domain_cell, 
                    ct.bankell, 
                    ct.bankelr, 
                    ct.fcw, 
                    ct.fcd, 
                    ct.zl, 
                    ct.zr 
                FROM 
                    chan_t AS ct
                JOIN
                    schema_md_cells md ON ct.elem_fid = md.grid_fid
                WHERE 
                    md.domain_cell = ? AND md.domain_fid = {subdomain};
                    """

            chan_n_sql = f"""
                SELECT 
                    md.domain_cell, 
                    cn.nxsecnum 
                FROM 
                    chan_n AS cn
                JOIN
                    schema_md_cells md ON cn.elem_fid = md.grid_fid
                WHERE 
                    md.domain_cell = ? AND md.domain_fid = {subdomain};
                    """

            chan_e_sql = f"""
                SELECT 
                    md.domain_cell 
                FROM 
                    noexchange_chan_cells AS ne
                JOIN
                    schema_md_cells md ON ne.grid_fid = md.grid_fid
                WHERE 
                    md.domain_fid = {subdomain}
                ORDER BY ne.fid;
                """

        segment = "   {0:.2f}   {1:.2f}   {2:.2f}   {3}\n"
        chan_r = "R" + "  {}" * 7 + "\n"
        chan_v = "V" + "  {}" * 19 + "\n"
        chan_t = "T" + "  {}" * 9 + "\n"
        chan_n = "N" + "  {}" * 4 + "\n"
        chanbank = " {0: <10} {1}\n"
        wsel = "{0} {1:.2f}\n"
        conf = " C {0}  {1}\n"
        chan_e = " E {0}\n"

        sqls = {
            "R": [chan_r_sql, chan_r, 3, 6],
            "V": [chan_v_sql, chan_v, 3, 5],
            "T": [chan_t_sql, chan_t, 3, 6],
            "N": [chan_n_sql, chan_n, 1, 2],
        }
        bLines = ""

        chan_rows = self.execute(chan_sql).fetchall()
        if not chan_rows:
            self.gutils.set_cont_par("ICHANNEL", 0)
            return False
        else:
            self.gutils.set_cont_par("ICHANNEL", 1)

        chan = os.path.join(outdir, "CHAN.DAT")
        bank = os.path.join(outdir, "CHANBANK.DAT")

        with open(chan, "w") as c, open(bank, "w") as b:
            ISED = self.gutils.get_cont_par("ISED")

            for row in chan_rows:
                row = [x if x is not None else "0" for x in row]
                fid = row[0]
                if ISED == "0":
                    row[4] = ""
                c.write(
                    segment.format(*row[1:5])
                )  # Writes depinitial, froudc, roughadj, isedn from 'chan' table (schematic layer).
                # A single line for each channel segment. The next lines will be the grid elements of
                # this channel segment.
                for elems in self.execute(
                        chan_elems_sql, (fid,)
                ):  # each 'elems' is a list [(fid, rbankgrid, fcn, xlen, type)] from
                    # 'chan_elems' table (the cross sections in the schematic layer),
                    #  that has the 'fid' value indicated (the channel segment id).
                    elems = [
                        x if x is not None else "" for x in elems
                    ]  # If 'elems' has a None in any of above values of list, replace it by ''
                    (
                        eid,
                        rbank,
                        fcn,
                        xlen,
                        typ,
                    ) = elems  # Separates values of list into individual variables.
                    sql, line, fcn_idx, xlen_idx = sqls[
                        typ
                    ]  # depending on 'typ' (R,V,T, or N) select sql (the SQLite SELECT statement to execute),
                    # line (format to write), fcn_idx (?), and xlen_idx (?)
                    res_query = self.execute(sql, (eid,)).fetchone()
                    if res_query is not None:
                        res = [x if x is not None else "" for x in res_query]  # 'res' is a list of values depending on 'typ' (R,V,T, or N).
                        res.insert(
                            fcn_idx, fcn
                        )  # Add 'fcn' (coming from table ´chan_elems' (cross sections) to 'res' list) in position 'fcn_idx'.
                        res.insert(
                            xlen_idx, xlen
                        )  # Add ´xlen' (coming from table ´chan_elems' (cross sections) to 'res' list in position 'xlen_idx'.
                        c.write(line.format(*res))
                        b.write(chanbank.format(eid, rbank))

                if row[5]: # ibaseflow
                    if str(row[5]) != "":
                        bLines += "B " + str(row[5]) + "\n"
                        # c.write("B " + str(row[5]) + "\n")

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

            if bLines != "":
                c.write(bLines)

        return True

        # except Exception as e:
        #     self.uc.bar_error("ERROR 090624.0624: exporting CHAN.DAT failed!")
        #     self.uc.log_info("ERROR 090624.0624: exporting CHAN.DAT failed!")
        #     return False

    def export_xsec(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_xsec_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_xsec_hdf5(subdomain)

    def export_xsec_hdf5(self, subdomain):
        """
        Function to export xsection data to hdf5 file
        """
        try:
            chan_n_sql = """SELECT DISTINCT nxsecnum, xsecname FROM chan_n ORDER BY nxsecnum;"""
            xsec_sql = """SELECT xi, yi FROM xsec_n_data WHERE chan_n_nxsecnum = ? ORDER BY fid;"""

            xsec_line = """{0}  {1}\n"""

            chan_n = self.execute(chan_n_sql).fetchall()
            if not chan_n:
                return False
            else:
                pass

            channel_group = self.parser.channel_group
            channel_group.create_dataset('XSEC_NAME', [])
            channel_group.create_dataset('XSEC_DATA', [])

            for nxecnum, xsecname in chan_n:
                channel_group.datasets["XSEC_NAME"].data.append(
                    create_array(xsec_line, 2, np.bytes_, tuple([nxecnum, xsecname])))
                for xi, yi in self.execute(xsec_sql, (nxecnum,)):
                    channel_group.datasets["XSEC_DATA"].data.append([nxecnum, xi, yi])

            self.parser.write_groups(channel_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1607:  exporting XSEC.DAT  failed!.\n", e)
            return False

    def export_xsec_dat(self, outdir, subdomain):
        try:
            chan_n_sql = """SELECT nxsecnum, xsecname FROM chan_n ORDER BY nxsecnum;"""
            xsec_sql = """SELECT xi, yi FROM xsec_n_data WHERE chan_n_nxsecnum = ? ORDER BY fid;"""

            xsec_line = """X     {0}  {1}\n"""
            pkt_line = """ {0:<10} {1: >10}\n"""
            nr = "{0:.2f}"

            chan_n = self.execute(chan_n_sql).fetchall()
            if not chan_n:
                return False
            else:
                pass

            xsec = os.path.join(outdir, "XSEC.DAT")
            with open(xsec, "w") as x:
                for nxecnum, xsecname in chan_n:
                    x.write(xsec_line.format(nxecnum, xsecname))
                    for xi, yi in self.execute(xsec_sql, (nxecnum,)):
                        x.write(pkt_line.format(nr.format(xi), nr.format(yi)))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1607:  exporting XSEC.DAT  failed!.\n", e)
            return False

    def export_hystruc(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_hystruc_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_hystruc_hdf5(subdomain)

    def export_hystruc_hdf5(self, subdomain):
        """
        Function to export Hydraulic Structure data to HDF5 file
        """
        try:
            # check if there is any hydraulic structure defined.
            if self.is_table_empty("struct"):
                return False
            else:
                nodes = self.execute("SELECT inflonod, outflonod FROM struct;").fetchall()
                for nod in nodes:
                    if nod[0] in [NULL, 0, ""] or nod[1] in [NULL, 0, ""]:
                        QApplication.restoreOverrideCursor()
                        self.uc.bar_warn(
                            "WARNING: some structures have no cells assigned.\nDid you schematize the structures?"
                        )
                        break

            ratc_sql = """SELECT * FROM rat_curves WHERE struct_fid = ? ORDER BY fid;"""
            repl_ratc_sql = """SELECT * FROM repl_rat_curves WHERE struct_fid = ? ORDER BY fid;"""
            ratt_sql = """SELECT * FROM rat_table WHERE struct_fid = ? ORDER BY fid;"""
            culvert_sql = """SELECT * FROM culvert_equations WHERE struct_fid = ? ORDER BY fid;"""
            bridge_sql = """SELECT fid, 
                                           struct_fid, 
                                           IBTYPE, 
                                           COEFF, 
                                           C_PRIME_USER, 
                                           KF_COEF, 
                                           KWW_COEF,  
                                           KPHI_COEF, 
                                           KY_COEF, 
                                           KX_COEF, 
                                           KJ_COEF,
                                           BOPENING, 
                                           BLENGTH, 
                                           BN_VALUE, 
                                           UPLENGTH12, 
                                           LOWCHORD,
                                           DECKHT, 
                                           DECKLENGTH, 
                                           PIERWIDTH, 
                                           SLUICECOEFADJ, 
                                           ORIFICECOEFADJ, 
                                           COEFFWEIRB, 
                                           WINGWALL_ANGLE, 
                                           PHI_ANGLE, 
                                           LBTOEABUT, 
                                           RBTOEABUT 
                                    FROM bridge_variables WHERE struct_fid = ? ORDER BY fid;"""

            if not subdomain:
                hystruct_sql = """SELECT * FROM struct ORDER BY fid;"""
                storm_sql = """SELECT * FROM storm_drains WHERE struct_fid = ? ORDER BY fid;"""

            else:
                hystruct_sql = f"""
                                SELECT 
                                    s.fid,
                                    s.type,
                                    s.structname, 
                                    s.ifporchan,
                                    s.icurvtable,
                                    inflow_md.domain_cell AS inflonod,
                                    outflow_md.domain_cell AS outflonod,
                                    s.inoutcont,
                                    s.headrefel,
                                    s.clength,
                                    s.cdiameter
                                FROM 
                                    struct AS s
                                JOIN
                                    schema_md_cells inflow_md ON s.inflonod = inflow_md.grid_fid AND inflow_md.domain_fid = {subdomain}
                                JOIN
                                    schema_md_cells outflow_md ON s.outflonod = outflow_md.grid_fid AND outflow_md.domain_fid = {subdomain}
                                ORDER BY s.fid;
                                """

                storm_sql = f"""
                                SELECT 
                                    sd.fid, 
                                    sd.struct_fid,
                                    md.domain_cell, 
                                    sd.stormdmax
                                FROM 
                                    storm_drains AS sd
                                JOIN
                                    schema_md_cells md ON sd.istormdout = md.grid_fid
                                WHERE 
                                    sd.struct_fid = ? AND md.domain_fid = {subdomain}
                                ORDER BY sd.fid;
                            """

            if self.execute(hystruct_sql).fetchone() is None:
                self.gutils.set_cont_par("IHYDRSTRUCT", 0)
                return False
            else:
                self.gutils.set_cont_par("IHYDRSTRUCT", 1)

            # line1 = "S" + "  {}" * 9 + "\n"
            line2 = "C" + "  {}" * 5 + "\n"
            line3 = "R" + "  {}" * 5 + "\n"

            line5 = "F" + "  {}" * 6 + "\n"
            line6 = "D" + "  {}" * 2 + "\n"
            line7a = "B" + "  {}" * 9 + "\n"
            line7b = "B" + "  {}" * 15 + "\n"

            two_values = "{}  {}\n"
            three_values = "{}  {}  {}\n"
            four_values = "{}  {}  {}  {}\n"
            five_values = "{}  {}  {}  {}  {}\n"
            six_values = "{}  {}  {}  {}  {}  {}\n"
            seven_values = "{}  {}  {}  {}  {}  {}  {}\n"
            nine_values = "{}  {}  {}  {}  {}  {}  {}  {}  {}\n"
            eleven_values = "{}  {}  {}  {}  {}  {}  {}  {}  {}  {}  {}\n"
            tfive_values = "{}" + " {}" * 24 + "\n"

            pairs = [
                [ratc_sql, line2],  # rating curve  ('C' lines)
                [ratt_sql, three_values],  # rating table ('T' lines)
                [culvert_sql, line5],  # culvert equation ('F' lines)
                [bridge_sql, line7a],  # bridge ('B' lines a
                [storm_sql, line6],  # storm drains ('D' lines)
            ]

            hystruc_rows = self.execute(hystruct_sql).fetchall()
            if not hystruc_rows:
                return False
            else:
                pass

            hystruc_group = self.parser.hystruc_group
            hystruc_group.create_dataset('STR_CONTROL', [])
            hystruc_group.create_dataset('STR_NAME', [])

            for stru in hystruc_rows:
                fid = stru[0]
                vals1 = [x if x is not None and x != "" else 0 for x in stru[2:8]]
                vals2 = [x if x is not None and x != "" else 0.0 for x in stru[8:11]]
                vals = vals1 + vals2
                (
                    struct_name,
                    ifporchan,
                    icurvtable,
                    inflonod,
                    outflonod,
                    inoutcont,
                    headrefel,
                    clength,
                    cdiameter
                ) = vals
                hystruc_group.datasets["STR_CONTROL"].data.append(create_array(
                    nine_values,
                    9,
                    np.float64,
                    fid,
                    ifporchan,
                    icurvtable,
                    inflonod,
                    outflonod,
                    inoutcont,
                    headrefel,
                    clength,
                    cdiameter))
                hystruc_group.datasets["STR_NAME"].data.append(create_array(two_values, 2, np.bytes_, fid, struct_name))

                #  0: rating curve
                #  1: rating table
                #  2: culvert equation
                #  3: bridge routine

                type = stru[4]

                for i, (qry, line) in enumerate(pairs):
                    if (
                            (type == 0 and i == 0)  # rating curve
                            or (type == 1 and i == 1)  # rating table
                            or (type == 2 and i == 2)  # culvert equation
                            or (type == 3 and i == 3)  # bridge routine
                            or i == 4  # storm drains
                    ):
                        for row in self.execute(qry, (fid,)):
                            if row:
                                subvals = [x if x is not None else 0.0 for x in row[1:]]

                                if i == 0:  # Rating curve line 'C' and 'R'
                                    # Replacement rating curve
                                    rrc_row = self.execute(repl_ratc_sql, (fid,)).fetchone()
                                    if rrc_row:
                                        rrc_row = [x if x is not None else 0.0 for x in rrc_row[2:]]
                                        try:
                                            hystruc_group.datasets["RATING_CURVE"].data.append(
                                                create_array(eleven_values, 11, np.float64, tuple(subvals + rrc_row)))
                                        except:
                                            hystruc_group.create_dataset('RATING_CURVE', [])
                                            hystruc_group.datasets["RATING_CURVE"].data.append(
                                                create_array(eleven_values, 11, np.float64, tuple(subvals + rrc_row)))
                                    else:
                                        try:
                                            hystruc_group.datasets["RATING_CURVE"].data.append(
                                                create_array(eleven_values, 11, np.float64, tuple(subvals + (5 * [0]))))
                                        except:
                                            hystruc_group.create_dataset('RATING_CURVE', [])
                                            hystruc_group.datasets["RATING_CURVE"].data.append(
                                                create_array(eleven_values, 11, np.float64, tuple(subvals + (5 * [0]))))

                                if i == 1:  # Rating table
                                    try:
                                        hystruc_group.datasets["RATING_TABLE"].data.append(
                                            create_array(four_values, 4, np.float64, tuple(subvals)))
                                    except:
                                        hystruc_group.create_dataset('RATING_TABLE', [])
                                        hystruc_group.datasets["RATING_TABLE"].data.append(
                                            create_array(four_values, 4, np.float64, tuple(subvals)))

                                if i == 2:  # Culvert equation.
                                    subvals[-1] = subvals[-1] if subvals[-1] not in [None, "0", "0.0"] else 1
                                    try:
                                        hystruc_group.datasets["CULVERT_EQUATIONS"].data.append(
                                            create_array(seven_values, 7, np.float64, tuple(subvals)))
                                    except:
                                        hystruc_group.create_dataset('CULVERT_EQUATIONS', [])
                                        hystruc_group.datasets["CULVERT_EQUATIONS"].data.append(
                                            create_array(seven_values, 7, np.float64, tuple(subvals)))

                                if i == 3:  # Bridge routine line
                                    try:
                                        for val in subvals:
                                            hystruc_group.datasets["BRIDGE_VARIABLES"].data.append(
                                                create_array("{0}", 1, np.float64, (val,))
                                            )
                                    except:
                                        hystruc_group.create_dataset('BRIDGE_VARIABLES', [])
                                        for val in subvals:
                                            hystruc_group.datasets["BRIDGE_VARIABLES"].data.append(
                                                create_array("{0}", 1, np.float64, (val,))
                                            )

                                if i == 4:
                                    try:
                                        hystruc_group.datasets["STORM_DRAIN"].data.append(
                                            create_array(three_values, 3, np.float64, tuple(subvals)))
                                    except:
                                        hystruc_group.create_dataset('STORM_DRAIN', [])
                                        hystruc_group.datasets["STORM_DRAIN"].data.append(
                                            create_array(three_values, 3, np.float64, tuple(subvals)))
                                else:
                                    pass

            self.parser.write_groups(hystruc_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1608: exporting HYSTRUC.DAT failed!.\n", e)
            return False

    def export_hystruc_dat(self, outdir, subdomain):
        try:
            # check if there is any hydraulic structure defined.
            if self.is_table_empty("struct"):
                return False
            else:
                nodes = self.execute("SELECT inflonod, outflonod FROM struct;").fetchall()
                for nod in nodes:
                    if nod[0] in [NULL, 0, ""] or nod[1] in [NULL, 0, ""]:
                        QApplication.restoreOverrideCursor()
                        self.uc.bar_warn(
                            "WARNING: some structures have no cells assigned.\nDid you schematize the structures?"
                        )
                        self.uc.log_info(
                            "WARNING: some structures have no cells assigned.\nDid you schematize the structures?"
                        )
                        break

            ratc_sql = """SELECT * FROM rat_curves WHERE struct_fid = ? ORDER BY fid;"""
            repl_ratc_sql = """SELECT * FROM repl_rat_curves WHERE struct_fid = ? ORDER BY fid;"""
            ratt_sql = """SELECT * FROM rat_table WHERE struct_fid = ? ORDER BY fid;"""
            culvert_sql = """SELECT * FROM culvert_equations WHERE struct_fid = ? ORDER BY fid;"""
            bridge_a_sql = """SELECT fid, struct_fid, IBTYPE, COEFF, C_PRIME_USER, KF_COEF, KWW_COEF,  KPHI_COEF, KY_COEF, KX_COEF, KJ_COEF 
                                FROM bridge_variables WHERE struct_fid = ? ORDER BY fid;"""
            bridge_b_sql = """SELECT fid, struct_fid, BOPENING, BLENGTH, BN_VALUE, UPLENGTH12, LOWCHORD,
                                     DECKHT, DECKLENGTH, PIERWIDTH, SLUICECOEFADJ, ORIFICECOEFADJ, 
                                    COEFFWEIRB, WINGWALL_ANGLE, PHI_ANGLE, LBTOEABUT, RBTOEABUT 
                                  FROM bridge_variables WHERE struct_fid = ? ORDER BY fid;"""

            if not subdomain:
                hystruct_sql = """SELECT * FROM struct ORDER BY fid;"""
                storm_sql = """SELECT * FROM storm_drains WHERE struct_fid = ? ORDER BY fid;"""

            else:
                hystruct_sql = f"""
                                SELECT 
                                    s.fid,
                                    s.type,
                                    s.structname, 
                                    s.ifporchan,
                                    s.icurvtable,
                                    inflow_md.domain_cell AS inflonod,
                                    outflow_md.domain_cell AS outflonod,
                                    s.inoutcont,
                                    s.headrefel,
                                    s.clength,
                                    s.cdiameter
                                FROM 
                                    struct AS s
                                JOIN
                                    schema_md_cells inflow_md ON s.inflonod = inflow_md.grid_fid AND inflow_md.domain_fid = {subdomain}
                                JOIN
                                    schema_md_cells outflow_md ON s.outflonod = outflow_md.grid_fid AND outflow_md.domain_fid = {subdomain}
                                ORDER BY s.fid;
                                """

                storm_sql = f"""
                                SELECT 
                                    sd.fid, 
                                    sd.struct_fid,
                                    md.domain_cell, 
                                    sd.stormdmax
                                FROM 
                                    storm_drains AS sd
                                JOIN
                                    schema_md_cells md ON sd.istormdout = md.grid_fid
                                WHERE 
                                    sd.struct_fid = ? AND md.domain_fid = {subdomain}
                                ORDER BY sd.fid;
                            """

            if self.execute(hystruct_sql).fetchone() is None:
                self.gutils.set_cont_par("IHYDRSTRUCT", 0)
                return False
            else:
                self.gutils.set_cont_par("IHYDRSTRUCT", 1)

            line1 = "S" + "  {}" * 9 + "\n"
            line2 = "C" + "  {}" * 5 + "\n"
            line3 = "R" + "  {}" * 5 + "\n"
            line4 = "T" + "  {}" * 3 + "\n"
            line5 = "F" + "  {}" * 6 + "\n"
            line6 = "D" + "  {}" * 2 + "\n"
            line7a = "B" + "  {}" * 9 + "\n"
            line7b = "B" + "  {}" * 15 + "\n"

            pairs = [
                [ratc_sql, line2],  # rating curve  ('C' lines)
                [repl_ratc_sql, line3],  # rating curve replacement ('R' lines)
                [ratt_sql, line4],  # rating table ('T' lines)
                [culvert_sql, line5],  # culvert equation ('F' lines)
                [bridge_a_sql, line7a],  # bridge ('B' lines a)
                [bridge_b_sql, line7b],  # bridge ('B' lines b)
                [storm_sql, line6],  # storm drains ('D' lines)
            ]

            hystruc_rows = self.execute(hystruct_sql).fetchall()
            if not hystruc_rows:
                return False
            else:
                pass
            hystruc = os.path.join(outdir, "HYSTRUC.DAT")
            d_lines = []
            with open(hystruc, "w") as h:
                for stru in hystruc_rows:
                    fid = stru[0]
                    vals1 = [x if x is not None and x != "" else 0 for x in stru[2:8]]
                    vals2 = [x if x is not None and x != "" else 0.0 for x in stru[8:11]]
                    vals = vals1 + vals2
                    h.write(line1.format(*vals))
                    type = stru[4]  # 0: rating curve
                    #  1: rating table
                    #  2: culvert equation
                    #  3: bridge routine
                    for i, (qry, line) in enumerate(pairs):
                        if (
                                (type == 0 and i == 0)  # rating curve line 'C'
                                or (type == 0 and i == 1)  # rating curve line 'R'
                                or (type == 1 and i == 2)  # rating table
                                or (type == 2 and i == 3)  # culvert equation
                                or (type == 3 and i == 4)  # bridge routine lines a
                                or (type == 3 and i == 5)  # bridge routine lines b
                                or i == 6  # storm drains
                        ):
                            for row in self.execute(qry, (fid,)):
                                if row:
                                    subvals = [x if x is not None else "0.0" for x in row[2:]]
                                    if i == 3:  # Culvert equation.
                                        subvals[-1] = subvals[-1] if subvals[-1] not in [None, "0", "0.0"] else 1
                                    if i == 4:  # bridge routine lines a. Assign correct bridge type configuration.
                                        t = subvals[0]
                                        t = 1 if t == 1 else 2 if (t == 2 or t == 3) else 3 if (t == 4 or t == 5) else 4
                                        subvals[0] = t
                                    if i == 6:
                                        d_lines.append(line.format(*subvals))
                                    else:
                                        h.write(line.format(*subvals))
                if d_lines:
                    for dl in d_lines:
                        h.write(dl)

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1608: exporting HYSTRUC.DAT failed!.\n", e)
            return False

    def export_bridge_xsec(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_bridge_xsec_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_bridge_xsec_hdf5(subdomain)

    def export_bridge_xsec_hdf5(self, subdomain):
        """
        Function to export bridge cross sections to hdf5 file\
        """
        try:
            # check if there is any hydraulic structure and bridge cross sections defined.
            if self.is_table_empty("struct") or self.is_table_empty("bridge_xs"):
                return False

            if not subdomain:
                hystruct_sql = """SELECT * FROM struct WHERE icurvtable = 3 ORDER BY fid;"""
            else:
                hystruct_sql = f"""
                                SELECT 
                                    s.fid,
                                    s.type,
                                    s.structname, 
                                    s.ifporchan,
                                    s.icurvtable,
                                    inflow_md.domain_cell AS inflonod,
                                    outflow_md.domain_cell AS outflonod,
                                    s.inoutcont,
                                    s.headrefel,
                                    s.clength,
                                    s.cdiameter
                                FROM 
                                    struct AS s
                                JOIN
                                    schema_md_cells inflow_md ON s.inflonod = inflow_md.grid_fid AND inflow_md.domain_fid = {subdomain}
                                JOIN
                                    schema_md_cells outflow_md ON s.outflonod = outflow_md.grid_fid AND outflow_md.domain_fid = {subdomain}
                                WHERE 
                                    s.icurvtable = 3
                                ORDER BY s.fid;
                                """

            bridge_xs_sql = """SELECT xup, yup, yb FROM bridge_xs WHERE struct_fid = ? ORDER BY struct_fid;"""

            hystruc_rows = self.execute(hystruct_sql).fetchall()
            if not hystruc_rows:
                return False
            else:
                pass

            hystruc_group = self.parser.hystruc_group
            hystruc_group.create_dataset('BRIDGE_XSEC', [])

            for stru in hystruc_rows:
                struct_fid = stru[0]
                bridge_rows = self.execute(bridge_xs_sql, (struct_fid,)).fetchall()
                if not bridge_rows:
                    continue
                else:

                    for row in bridge_rows:
                        row = [x if x not in [NULL, None, "None", "none"] else 0 for x in row]
                        line = str(struct_fid) + "  " + str(row[0]) + "  " + str(row[1]) + "  " + str(row[2]) + "\n"
                        hystruc_group.datasets["BRIDGE_XSEC"].data.append(create_array(line, 4, np.float64))

            self.parser.write_groups(hystruc_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101122.0753: exporting BRIDGE_XSEC.DAT failed!.\n", e)
            return False

    def export_bridge_xsec_dat(self, outdir, subdomain):
        try:
            # check if there is any hydraulic structure and bridge cross sections defined.
            if self.is_table_empty("struct") or self.is_table_empty("bridge_xs"):
                if os.path.isfile(outdir + r"\BRIDGE_XSEC.DAT"):
                    os.remove(outdir + r"\BRIDGE_XSEC.DAT")
                return False

            if not subdomain:
                hystruct_sql = """SELECT * FROM struct WHERE icurvtable = 3 ORDER BY fid;"""
            else:
                hystruct_sql = f"""
                                SELECT 
                                    s.fid,
                                    s.type,
                                    s.structname, 
                                    s.ifporchan,
                                    s.icurvtable,
                                    inflow_md.domain_cell AS inflonod,
                                    outflow_md.domain_cell AS outflonod,
                                    s.inoutcont,
                                    s.headrefel,
                                    s.clength,
                                    s.cdiameter
                                FROM 
                                    struct AS s
                                JOIN
                                    schema_md_cells inflow_md ON s.inflonod = inflow_md.grid_fid AND inflow_md.domain_fid = {subdomain}
                                JOIN
                                    schema_md_cells outflow_md ON s.outflonod = outflow_md.grid_fid AND outflow_md.domain_fid = {subdomain}
                                WHERE 
                                    s.icurvtable = 3
                                ORDER BY s.fid;
                                """

            bridge_xs_sql = """SELECT xup, yup, yb FROM bridge_xs WHERE struct_fid = ? ORDER BY struct_fid;"""

            hystruc_rows = self.execute(hystruct_sql).fetchall()
            if not hystruc_rows:
                if os.path.isfile(outdir + r"\BRIDGE_XSEC.DAT"):
                    os.remove(outdir + r"\BRIDGE_XSEC.DAT")
                return False
            else:
                pass
            bridge = os.path.join(outdir, "BRIDGE_XSEC.DAT")
            with open(bridge, "w") as b:
                for stru in hystruc_rows:
                    struct_fid = stru[0]
                    in_node = stru[5]
                    bridge_rows = self.execute(bridge_xs_sql, (struct_fid,)).fetchall()
                    if not bridge_rows:
                        continue
                    else:
                        b.write("X  " + str(in_node) + "\n")
                        for row in bridge_rows:
                            row = [x if x not in [NULL, None, "None", "none"] else 0 for x in row]
                            b.write(str(row[0]) + "  " + str(row[1]) + "  " + str(row[2]) + "\n")
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101122.0753: exporting BRIDGE_XSEC.DAT failed!.\n", e)
            return False

    def export_bridge_coeff_data(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_bridge_coeff_data_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_bridge_coeff_data_hdf5(subdomain)

    def export_bridge_coeff_data_hdf5(self, subdomain):
        """
        Export bridge coefficient data to the hdf5 file
        """
        try:
            if self.is_table_empty("struct"):
                return False
            hystruc_group = self.parser.hystruc_group
            hystruc_group.create_dataset('BRIDGE_COEFF_DATA', [])

            src = os.path.dirname(os.path.abspath(__file__)) + "/bridge_coeff_data.dat"''
            data = []
            with open(src, 'r') as bridge_coeff_data:
                for line in bridge_coeff_data:
                    hystruc_group.datasets["BRIDGE_COEFF_DATA"].data.append(create_array(line, 13, np.bytes_))

            self.parser.write_groups(hystruc_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101122.0754: exporting BRIDGE_COEFF_DATA.DAT failed!.\n", e)
            return False

    def export_bridge_coeff_data_dat(self, outdir, subdomain):
        try:
            # check if there is any hydraulic structure defined.
            if self.is_table_empty("struct"):
                return False
            src = os.path.dirname(os.path.abspath(__file__)) + "/bridge_coeff_data.dat"
            dst = os.path.join(outdir, "BRIDGE_COEFF_DATA.DAT")
            shutil.copy(src, dst)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101122.0754: exporting BRIDGE_COEFF_DATA.DAT failed!.\n", e)
            return False

    def export_street(self, output=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_street_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_street_hdf5()

    def export_street_hdf5(self):
        """
        Function to export street data to hdf5 file
        """
        try:
            if self.is_table_empty("streets"):
                return False
            street_gen_sql = """SELECT strman, istrflo, strfno, depx, widst FROM street_general ORDER BY fid;"""
            streets_sql = """SELECT fid, stname FROM streets ORDER BY fid;"""
            streets_seg_sql = """SELECT fid, igridn, depex, stman, elstr FROM street_seg WHERE str_fid = ? ORDER BY fid;"""
            streets_elem_sql = """SELECT seg_fid, istdir, widr FROM street_elems WHERE seg_fid = ? ORDER BY fid;"""

            head = self.execute(street_gen_sql).fetchone()

            if head is None:
                self.gutils.set_cont_par("MSTREET", 0)
                return False
            else:
                self.gutils.set_cont_par("MSTREET", 1)

            street_group = self.parser.street_group

            street_group.create_dataset('STREET_GLOBAL', [])
            strman, istrflo, strfno, depx, widst = head
            street_group.datasets["STREET_GLOBAL"].data.append([strman, int(istrflo), strfno, depx, widst])

            street_group.create_dataset('STREET_NAMES', [])
            street_group.create_dataset('STREET_SEG', [])
            street_group.create_dataset('STREET_ELEMS', [])
            for row in self.execute(streets_sql).fetchall():
                fid, stname = row
                if isinstance(stname, bytes):
                    stname = stname.decode('utf-8')
                street_group.datasets["STREET_NAMES"].data.append([stname])
                for seg in self.execute(streets_seg_sql, (fid,)):
                    seg_fid, igridn, depex, stman, elstr = seg
                    street_group.datasets["STREET_SEG"].data.append([int(fid), int(igridn), depex, stman, elstr])
                    for elem in self.execute(streets_elem_sql, (seg_fid,)):
                        seg_fid, istdir, widr = elem
                        street_group.datasets["STREET_ELEMS"].data.append([int(seg_fid), int(istdir), widr])

            self.parser.write_groups(street_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("Error while exporting STREET data to hdf5 file!\n", e)
            self.uc.log_info("Error while exporting STREET data to hdf5 file!")
            return False

    def export_street_dat(self, outdir):
        # check if there is any street defined.
        try:
            if self.is_table_empty("streets"):
                return False
            street_gen_sql = """SELECT * FROM street_general ORDER BY fid;"""
            streets_sql = """SELECT stname FROM streets ORDER BY fid;"""
            streets_seg_sql = """SELECT igridn, depex, stman, elstr FROM street_seg WHERE str_fid = ? ORDER BY fid;"""
            streets_elem_sql = """SELECT istdir, widr FROM street_elems WHERE seg_fid = ? ORDER BY fid;"""

            line1 = "  {}" * 5 + "\n"
            line2 = " N {}\n"
            line3 = " S" + "  {}" * 4 + "\n"
            line4 = " W" + "  {}" * 2 + "\n"

            head = self.execute(street_gen_sql).fetchone()

            if head is None:
                self.gutils.set_cont_par("MSTREET", 0)
                return False
            else:
                self.gutils.set_cont_par("MSTREET", 1)

            street = os.path.join(outdir, "STREET.DAT")
            with open(street, "w") as s:
                s.write(line1.format(*head[1:]))
                seg_fid = 1
                for i, sts in enumerate(self.execute(streets_sql), 1):
                    s.write(line2.format(*sts))
                    for seg in self.execute(streets_seg_sql, (i,)):
                        s.write(line3.format(*seg))
                        for elem in self.execute(streets_elem_sql, (seg_fid,)):
                            s.write(line4.format(*elem))
                        seg_fid += 1

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1609: exporting STREET.DAT failed!.\n", e)
            return False

    def export_arf(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_arf_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_arf_hdf5(subdomain)

    def export_arf_dat(self, outdir, subdomain):
        """
        Function to export arf data to data file
        """
        try:
            if self.is_table_empty("blocked_cells"):
                return False
            cont_sql = """SELECT name, value FROM cont WHERE name = 'IARFBLOCKMOD';"""
            # collapse_sql = """SELECT collapse, calc_arf, calc_wrf FROM user_blocked_areas WHERE fid = ?;"""
            if not subdomain:
                tbc_sql = """SELECT grid_fid, area_fid FROM blocked_cells WHERE arf = 1 ORDER BY grid_fid;"""
                pbc_sql = """SELECT grid_fid, area_fid,  arf, wrf1, wrf2, wrf3, wrf4, wrf5, wrf6, wrf7, wrf8
                             FROM blocked_cells WHERE arf < 1 ORDER BY grid_fid;"""
            else:
                tbc_sql = f"""SELECT 
                                md.domain_cell, 
                                area_fid 
                            FROM 
                                blocked_cells AS bc
                            JOIN 
                                schema_md_cells md ON bc.grid_fid = md.grid_fid
                            WHERE 
                                arf = 1 AND md.domain_fid = {subdomain};"""

                pbc_sql = f"""SELECT 
                                md.domain_cell, 
                                area_fid,  
                                arf, wrf1, wrf2, wrf3, wrf4, wrf5, wrf6, wrf7, wrf8
                             FROM 
                                blocked_cells AS bc
                             JOIN 
                                schema_md_cells md ON bc.grid_fid = md.grid_fid
                             WHERE 
                                arf < 1 AND md.domain_fid = {subdomain};"""

            if self.execute(tbc_sql).fetchone() is None and self.execute(pbc_sql).fetchone() is None:
                self.gutils.set_cont_par("IWRFS", 0)
                return False
            else:
                self.gutils.set_cont_par("IWRFS", 1)

            line1 = "S  {}\n"
            line2 = " T   {}\n"
            #         line3 = '   {}' * 10 + '\n'
            line3 = "{0:<8} {1:<5.2f} {2:<5.2f} {3:<5.2f} {4:<5.2f} {5:<5.2f} {6:<5.2f} {7:<5.2f} {8:5.2f} {9:<5.2f}\n"
            option = self.execute(cont_sql).fetchone()
            if option is None:
                # TODO: We need to implement correct export of 'IARFBLOCKMOD'
                option = ("IARFBLOCKMOD", 0)

            arf = os.path.join(outdir, "ARF.DAT")

            with open(arf, "w") as a:
                head = option[-1]
                if head is not None:
                    a.write(line1.format(head))
                else:
                    pass

                # Totally blocked grid elements:
                for row in self.execute(tbc_sql):
                    # collapse = self.execute(collapse_sql, (row[1],)).fetchone()
                    # if collapse:
                    #     cll = collapse[0]
                    # else:
                    #     cll = 0
                    # cll = [cll if cll is not None else 0]
                    cell = row[0]
                    # if cll[0] == 1:
                    #     cell = -cell
                    a.write(line2.format(cell))

                # Partially blocked grid elements:
                for row in self.execute(pbc_sql):
                    row = [x if x is not None else "" for x in row]
                    # Is there any side blocked? If not omit it:
                    # any_blocked = sum(row) - row[0] - row[1]
                    # if any_blocked > 0:
                    # collapse = self.execute(collapse_sql, (row[1],)).fetchone()
                    # if collapse:
                    #     cll = collapse[0]
                    # else:
                    #     cll = 0
                    # cll = [cll if cll is not None else 0]
                    cell = row[0]
                    arf_value = row[2]
                    # if cll[0] == 1:
                    #     arf_value = -arf_value
                    a.write(line3.format(cell, arf_value, *row[3:]))
        #                     a.write(line3.format(*row))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1610: exporting ARF.DAT failed!.", e)
            return False

    def export_arf_hdf5(self, subdomain):
        # check if there are any grid cells with ARF defined.
        try:
            if self.is_table_empty("blocked_cells"):
                return False
            cont_sql = """SELECT name, value FROM cont WHERE name = 'IARFBLOCKMOD';"""
            # collapse_sql = """SELECT collapse, calc_arf, calc_wrf FROM user_blocked_areas WHERE fid = ?;"""
            if not subdomain:
                tbc_sql = """SELECT grid_fid, area_fid, arf FROM blocked_cells WHERE arf IN (1, -1);"""
                pbc_sql = """SELECT grid_fid, area_fid,  arf, wrf1, wrf2, wrf3, wrf4, wrf5, wrf6, wrf7, wrf8
                             FROM blocked_cells WHERE arf < 1 ORDER BY grid_fid;"""

            else:
                tbc_sql = f"""SELECT 
                                md.domain_cell, 
                                area_fid 
                            FROM 
                                blocked_cells AS bc
                            JOIN 
                                schema_md_cells md ON bc.grid_fid = md.grid_fid
                            WHERE 
                                arf = 1 AND md.domain_fid = {subdomain};"""

                pbc_sql = f"""SELECT 
                                md.domain_cell, 
                                area_fid,  
                                arf, wrf1, wrf2, wrf3, wrf4, wrf5, wrf6, wrf7, wrf8
                             FROM 
                                blocked_cells AS bc
                             JOIN 
                                schema_md_cells md ON bc.grid_fid = md.grid_fid
                             WHERE 
                                arf < 1 AND md.domain_fid = {subdomain};"""

            if self.execute(tbc_sql).fetchone() is None and self.execute(pbc_sql).fetchone() is None:
                self.gutils.set_cont_par("IWRFS", 0)
                return False
            else:
                self.gutils.set_cont_par("IWRFS", 1)

            line3 = "{0:<8} {1:<5.2f} {2:<5.2f} {3:<5.2f} {4:<5.2f} {5:<5.2f} {6:<5.2f} {7:<5.2f} {8:5.2f} {9:<5.2f}\n"
            option = self.execute(cont_sql).fetchone()
            if option is None:
                option = ("IARFBLOCKMOD", 0)

            arfwrf_group = self.parser.arfwrf_group
            arfwrf_group.create_dataset('ARF_GLOBAL', [])

            head = option[-1]
            if head is not None:
                arfwrf_group.datasets["ARF_GLOBAL"].data.append(float(head))
            else:
                pass

            # arfwrf_group.create_dataset('COLLAPSE_CELLS', [])

            # Totally blocked grid elements:
            totally_blocked_grid = self.execute(tbc_sql).fetchone()
            if totally_blocked_grid is not None:
                arfwrf_group.create_dataset('ARF_TOTALLY_BLOCKED', [])
                for row in self.execute(tbc_sql):
                    cell = row[0]
                    # collapse = self.execute(collapse_sql, (row[1],)).fetchone()
                    # Check for collapse data, sometimes there is no collapse data
                    # # if collapse:
                    #     arfwrf_group.datasets["COLLAPSE_CELLS"].data.append(
                    #         [int(cell), int(collapse[0]), int(collapse[1]), int(collapse[2])])
                    #     if int(collapse[0]) == 1:
                    #         cell = -cell
                    arfwrf_group.datasets["ARF_TOTALLY_BLOCKED"].data.append(cell)

            # Partially blocked grid elements:
            partially_blocked_grid = self.execute(pbc_sql).fetchone()
            if partially_blocked_grid is not None:
                arfwrf_group.create_dataset('ARF_PARTIALLY_BLOCKED', [])
                for row in self.execute(pbc_sql):
                    row = [x if x is not None else "" for x in row]
                    # Is there any side blocked? If not omit it:
                    # any_blocked = sum(row) - row[0] - row[1]
                    # if any_blocked > 0:
                    cell = row[0]
                    arf_value = round(row[2], 2)
                    # collapse = self.execute(collapse_sql, (row[1],)).fetchone()
                    # if collapse:
                    #     arfwrf_group.datasets["COLLAPSE_CELLS"].data.append([int(cell), int(collapse[0]), int(collapse[1]), int(collapse[2])])
                    #     if int(collapse[0]) == 1:
                    #         arf_value = -arf_value
                    arfwrf_group.datasets["ARF_PARTIALLY_BLOCKED"].data.append(
                        create_array(line3, 10, np.float64, cell, arf_value, *row[3:]))

            self.parser.write_groups(arfwrf_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1610: exporting ARF.DAT failed!.", e)
            return False

    def export_mult(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_mult_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_mult_hdf5(subdomain)

    def export_mult_hdf5(self, subdomain):
        """
        Function to export mult data to hdf5 file
        """

        if self.is_table_empty("mult_cells") and self.is_table_empty("simple_mult_cells"):
            return False

        if self.is_table_empty("mult"):
            # Assign defaults to multiple channels globals:
            self.gutils.fill_empty_mult_globals()

        mult_sql = """SELECT * FROM mult;"""
        head = self.execute(mult_sql).fetchone()
        mults = []
        has_mult = False
        has_simple_mult = False

        mult_group = self.parser.mult_group
        # Check if there is any multiple channel cells defined.
        if not self.is_table_empty("mult_cells"):
            try:
                # Multiple Channels (not simplified):
                if not subdomain:
                    mult_cell_sql = """SELECT grid_fid, wdr, dm, nodchns, xnmult FROM mult_cells ORDER BY grid_fid ;"""
                else:
                    mult_cell_sql = f"""
                    SELECT 
                        md.domain_cell, 
                        mc.wdr, 
                        mc.dm, 
                        mc.nodchns, 
                        mc.xnmult 
                    FROM 
                        mult_cells AS mc
                    JOIN 
                        schema_md_cells md ON mc.grid_fid = md.grid_fid    
                    WHERE
                        md.domain_fid = {subdomain}
                    ORDER BY 
                        mc.grid_fid;"""

                if self.execute(mult_cell_sql).fetchone() is not None:
                    has_mult = True

                global_data_values = " {}" * 9 + "\n"
                five_values = " {}" * 5 + "\n"

                mult_group.create_dataset('MULT_GLOBAL', [])
                mult_group.create_dataset('MULT', [])

                mult_group.datasets["MULT_GLOBAL"].data.append(create_array(global_data_values, 9, np.float64, head[1:]))

                mult_cells = self.execute(mult_cell_sql).fetchall()

                seen = set()
                for a, b, c, d, e in mult_cells:
                    if not a in seen:
                        seen.add(a)
                        mults.append((a, b, c, d, e))

                for row in mults:
                    vals = [x if x is not None else "" for x in row]
                    mult_group.datasets["MULT"].data.append(create_array(five_values, 5, np.float64, tuple(vals)))

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error("ERROR 101218.1611: exporting MULT.DAT failed!.\n", e)
                return False

        if not self.is_table_empty("simple_mult_cells"):
            try:
                # Simplified Multiple Channels:
                if not subdomain:
                    simple_mult_cell_sql = """SELECT DISTINCT grid_fid FROM simple_mult_cells ORDER BY grid_fid;"""
                else:
                    simple_mult_cell_sql = f"""
                    SELECT DISTINCT
                        md.domain_cell 
                    FROM 
                        simple_mult_cells AS smc
                    JOIN 
                        schema_md_cells md ON smc.grid_fid = md.grid_fid    
                    WHERE
                        md.domain_fid = {subdomain}
                    ORDER BY 
                        smc.grid_fid;"""

                if self.execute(simple_mult_cell_sql).fetchone() is not None:
                    has_simple_mult = True

                global_data_values = "{}" + "\n"
                grid_values = "{}" + "\n"

                isany = self.execute(simple_mult_cell_sql).fetchone()
                if isany:
                    mult_group.create_dataset('SIMPLE_MULT', [])
                    mult_group.create_dataset('SIMPLE_MULT_GLOBAL', [])
                    repeats = ""

                    mult_group.datasets["SIMPLE_MULT_GLOBAL"].data.append(
                        create_array(global_data_values, 1, np.float64, head[9]))

                    for row in self.execute(simple_mult_cell_sql):
                        # See if grid number in row is any grid element in mults:
                        if [item for item in mults if item[0] == row[0]]:
                            repeats += str(row[0]) + "  "
                        else:
                            vals = [x if x is not None else "" for x in row]
                            mult_group.datasets["SIMPLE_MULT"].data.append(
                                create_array(grid_values, 1, np.int_, tuple(vals)))
                # if repeats:
                #     self.uc.log_info("Cells repeated in simple mult cells: " + repeats)

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error("ERROR 101218.1611: exporting SIMPLE_MULT.DAT failed!.\n", e)
                return False

        if has_mult or has_simple_mult:
            self.gutils.set_cont_par("IMULTC", 1)
        else:
            self.gutils.set_cont_par("IMULTC", 0)

        self.parser.write_groups(mult_group)
        return True

    def export_mult_dat(self, outdir, subdomain):
        rtrn = True
        has_mult = False
        has_simple_mult = False
        if self.is_table_empty("mult_cells") and self.is_table_empty("simple_mult_cells"):
            return False

        if self.is_table_empty("mult"):
            # Assign defaults to multiple channels globals:
            self.gutils.fill_empty_mult_globals()

        mult_sql = """SELECT * FROM mult;"""
        head = self.execute(mult_sql).fetchone()
        mults = []

        # Check if there is any multiple channel cells defined.
        if not self.is_table_empty("mult_cells"):
            try:
                # Multiple Channels (not simplified):
                if not subdomain:
                    mult_cell_sql = """SELECT grid_fid, wdr, dm, nodchns, xnmult FROM mult_cells ORDER BY grid_fid ;"""
                else:
                    mult_cell_sql = f"""
                    SELECT 
                        md.domain_cell, 
                        mc.wdr, 
                        mc.dm, 
                        mc.nodchns, 
                        mc.xnmult 
                    FROM 
                        mult_cells AS mc
                    JOIN 
                        schema_md_cells md ON mc.grid_fid = md.grid_fid    
                    WHERE
                        md.domain_fid = {subdomain}
                    ORDER BY 
                        mc.grid_fid;"""

                if self.execute(mult_cell_sql).fetchone() is not None:
                    has_mult = True

                line1 = " {}" * 8 + "\n"
                line2 = " {}" * 5 + "\n"

                mult = os.path.join(outdir, "MULT.DAT")
                with open(mult, "w") as m:
                    m.write(line1.format(*head[1:]).replace("None", ""))

                    mult_cells = self.execute(mult_cell_sql).fetchall()

                    seen = set()
                    for a, b, c, d, e in mult_cells:
                        if not a in seen:
                            seen.add(a)
                            mults.append((a, b, c, d, e))

                    for row in mults:
                        vals = [x if x is not None else "" for x in row]
                        m.write(line2.format(*vals))

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error("ERROR 101218.1611: exporting MULT.DAT failed!.\n", e)
                return False

        if not self.is_table_empty("simple_mult_cells"):
            try:
                # Simplified Multiple Channels:
                if not subdomain:
                    simple_mult_cell_sql = """SELECT DISTINCT grid_fid FROM simple_mult_cells ORDER BY grid_fid;"""
                else:
                    simple_mult_cell_sql = f"""
                    SELECT DISTINCT
                        md.domain_cell 
                    FROM 
                        simple_mult_cells AS smc
                    JOIN 
                        schema_md_cells md ON smc.grid_fid = md.grid_fid    
                    WHERE
                        md.domain_fid = {subdomain}
                    ORDER BY 
                        smc.grid_fid;"""

                if self.execute(simple_mult_cell_sql).fetchone() is not None:
                    has_simple_mult = True

                line1 = "{}" + "\n"
                line2 = "{}" + "\n"

                isany = self.execute(simple_mult_cell_sql).fetchone()
                if isany:
                    simple_mult = os.path.join(outdir, "SIMPLE_MULT.DAT")
                    repeats = ""
                    with open(simple_mult, "w") as sm:
                        sm.write(line1.format(head[9]))
                        for row in self.execute(simple_mult_cell_sql):
                            # See if grid number in row is any grid element in mults:
                            if [item for item in mults if item[0] == row[0]]:
                                repeats += str(row[0]) + "  "
                            else:
                                vals = [x if x is not None else "" for x in row]
                                sm.write(line2.format(*vals))
                    if repeats:
                        self.uc.log_info("Cells repeated in simple mult cells: " + repeats)

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error("ERROR 101218.1611: exporting SIMPLE_MULT.DAT failed!.\n", e)
                return False

        if has_mult or has_simple_mult:
            self.gutils.set_cont_par("IMULTC", 1)
        else:
            self.gutils.set_cont_par("IMULTC", 0)

        return rtrn

    def export_tolspatial(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_tolspatial_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_tolspatial_hdf5(subdomain)

    def export_tolspatial_hdf5(self, subdomain):
        """
        Function to export tolspatial to hdf5 file
        """
        # check if there is any tolerance data defined.
        try:
            if self.is_table_empty("tolspatial"):
                return False
            tol_poly_sql = """SELECT fid, tol FROM tolspatial ORDER BY fid;"""
            if not subdomain:
                tol_cells_sql = """SELECT grid_fid FROM tolspatial_cells WHERE area_fid = ? ORDER BY grid_fid;"""
            else:
                tol_cells_sql = f"""SELECT 
                                        md.domain_cell
                                    FROM 
                                        tolspatial_cells AS tc
                                    JOIN 
                                        schema_md_cells md ON tc.grid_fid = md.grid_fid    
                                    WHERE 
                                        area_fid = ? AND md.domain_fid = {subdomain}"""

            two_values = "{0}  {1}\n"

            tol_poly_rows = self.execute(tol_poly_sql).fetchall()  # A list of pairs (fid number, tolerance value)

            if not tol_poly_rows:
                return False
            else:
                pass

            spatially_variable_group = self.parser.spatially_variable_group
            spatially_variable_group.create_dataset('TOLSPATIAL', [])

            for fid, tol in tol_poly_rows:
                for row in self.execute(tol_cells_sql, (fid,)):
                    gid = row[0]
                    spatially_variable_group.datasets["TOLSPATIAL"].data.append(
                        create_array(two_values, 2, np.float64, gid, tol))

            self.parser.write_groups(spatially_variable_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1539: exporting TOLSPATIAL.DAT failed!", e)
            return False

    def export_tolspatial_dat(self, outdir, subdomain):
        # check if there is any tolerance data defined.
        try:
            if self.is_table_empty("tolspatial"):
                return False
            tol_poly_sql = """SELECT fid, tol FROM tolspatial ORDER BY fid;"""
            if not subdomain:
                tol_cells_sql = """SELECT grid_fid FROM tolspatial_cells WHERE area_fid = ? ORDER BY grid_fid;"""
            else:
                tol_cells_sql = f"""SELECT 
                                        md.domain_cell
                                    FROM 
                                        tolspatial_cells AS tc
                                    JOIN 
                                        schema_md_cells md ON tc.grid_fid = md.grid_fid    
                                    WHERE 
                                        area_fid = ? AND md.domain_fid = {subdomain}"""

            line1 = "{0}  {1}\n"

            tol_poly_rows = self.execute(tol_poly_sql).fetchall()  # A list of pairs (fid number, tolerance value),
            # one for each tolerance polygon.                                                       #(fid, tol), that is, (polygon fid, tolerance value)
            if not tol_poly_rows:
                return False
            else:
                pass
            tolspatial_dat = os.path.join(outdir, "TOLSPATIAL.DAT")  # path and name of file to write
            with open(tolspatial_dat, "w") as t:
                for fid, tol in tol_poly_rows:
                    for row in self.execute(tol_cells_sql, (fid,)):
                        gid = row[0]
                        t.write(line1.format(gid, tol))
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1539: exporting TOLSPATIAL.DAT failed!", e)
            return False

    def export_gutter(self, output=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_gutter_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_gutter_hdf5()

    def export_gutter_hdf5(self):
        """
        Export guttter data to the hdf5 file
        """

        # check if there are any gutters defined:
        if self.is_table_empty("gutter_cells"):
            return False
        if self.is_table_empty("gutter_globals"):
            self.uc.show_info("Gutter Global values are missing!.\n\nDefault values will be assigned.")
            update_qry = """INSERT INTO gutter_globals (height, width, n_value) VALUES (?,?,?);"""
            self.gutils.execute(update_qry, ("0.88", "0.99", "0.77"))

        gutter_globals_sql = """SELECT * FROM gutter_globals LIMIT 1;"""
        gutter_poly_sql = """SELECT fid, width, height, n_value, direction FROM gutter_areas ORDER BY fid;"""
        gutter_line_sql = """SELECT fid, width, height, n_value, direction FROM gutter_lines ORDER BY fid;"""
        gutter_area_cells_sql = (
            """SELECT grid_fid, area_fid FROM gutter_cells WHERE area_fid = ? ORDER BY grid_fid;"""
        )
        gutter_line_cells_sql = (
            """SELECT grid_fid, line_fid FROM gutter_cells WHERE line_fid = ? ORDER BY grid_fid;"""
        )

        three_values = "{0} {1} {2}\n"
        line2 = " {}" * 5 + "\n"

        head = self.execute(gutter_globals_sql).fetchone()

        # A list of tuples (areafid,  width, height, n_value, direction) for each gutter polygon:
        gutter_poly_rows = self.execute(gutter_poly_sql).fetchall()

        # A list of tuples (areafid,  width, height, n_value, direction) for each gutter line:
        gutter_line_rows = self.execute(gutter_line_sql).fetchall()

        if not gutter_poly_rows and not gutter_line_rows:
            return False
        else:
            pass

        gutter_group = self.parser.gutter_group
        gutter_group.create_dataset('GUTTER_DATA', [])
        gutter_group.create_dataset('GUTTER_GLOBAL', [])

        gutter_group.datasets["GUTTER_GLOBAL"].data.append(create_array(three_values, 3, np.float64, tuple(head[1:])))

        if gutter_poly_rows:
            for (
                    fid,
                    width,
                    height,
                    n_value,
                    direction,
            ) in (
                    gutter_poly_rows
            ):  # One tuple for each polygon.                    # self.uc.show_info("fid %s, width: %s, height: %s , heign_value: %s, direction: %s" % (fid, width, height, n_value, direction))
                for row in self.execute(
                        gutter_area_cells_sql, (fid,)
                ):  # Gets each cell number that pairs with area_fid.
                    grid_ID = row[0]
                    area = row[1]
                    if area:
                        gutter_group.datasets["GUTTER_DATA"].data.append(
                            create_array(line2, 5, np.float64, grid_ID, width, height, n_value, direction))

        if gutter_line_rows:
            for (
                    fid,
                    width,
                    height,
                    n_value,
                    direction,
            ) in (
                    gutter_line_rows
            ):  # One tuple for each line.                    # self.uc.show_info("fid %s, width: %s, height: %s , heign_value: %s, direction: %s" % (fid, width, height, n_value, direction))
                for row in self.execute(
                        gutter_line_cells_sql, (fid,)
                ):  # Gets each cell number that pairs with line_fid.
                    grid_ID = row[0]
                    line = row[1]
                    if line:
                        gutter_group.datasets["GUTTER_DATA"].data.append(
                            create_array(line2, 5, np.float64, grid_ID, width, height, n_value, direction))

        self.parser.write_groups(gutter_group)
        return True

    def export_gutter_dat(self, outdir):
        try:
            # check if there are any gutters defined:
            if self.is_table_empty("gutter_cells"):
                return False
            if self.is_table_empty("gutter_globals"):
                self.uc.show_info("Gutter Global values are missing!.\n\nDefault values will be assigned.")
                update_qry = """INSERT INTO gutter_globals (height, width, n_value) VALUES (?,?,?);"""
                self.gutils.execute(update_qry, ("0.88", "0.99", "0.77"))

            gutter_globals_sql = """SELECT * FROM gutter_globals LIMIT 1;"""
            gutter_poly_sql = """SELECT fid, width, height, n_value, direction FROM gutter_areas ORDER BY fid;"""
            gutter_line_sql = """SELECT fid, width, height, n_value, direction FROM gutter_lines ORDER BY fid;"""
            gutter_area_cells_sql = (
                """SELECT grid_fid, area_fid FROM gutter_cells WHERE area_fid = ? ORDER BY grid_fid;"""
            )
            gutter_line_cells_sql = (
                """SELECT grid_fid, line_fid FROM gutter_cells WHERE line_fid = ? ORDER BY grid_fid;"""
            )

            line1 = "{0} {1} {2}\n"
            line2 = "G  " + "   {}" * 5 + "\n"

            head = self.execute(gutter_globals_sql).fetchone()

            # A list of tuples (areafid,  width, height, n_value, direction) for each gutter polygon:
            gutter_poly_rows = self.execute(gutter_poly_sql).fetchall()

            # A list of tuples (areafid,  width, height, n_value, direction) for each gutter line:
            gutter_line_rows = self.execute(gutter_line_sql).fetchall()

            if not gutter_poly_rows and not gutter_line_rows:
                return False
            else:
                pass

            gutter_dat = os.path.join(outdir, "GUTTER.DAT")

            with open(gutter_dat, "w") as g:
                g.write(line1.format(*head[1:]))

                if gutter_poly_rows:
                    for (
                            fid,
                            width,
                            height,
                            n_value,
                            direction,
                    ) in (
                            gutter_poly_rows
                    ):  # One tuple for each polygon.                    # self.uc.show_info("fid %s, width: %s, height: %s , heign_value: %s, direction: %s" % (fid, width, height, n_value, direction))
                        for row in self.execute(
                                gutter_area_cells_sql, (fid,)
                        ):  # Gets each cell number that pairs with area_fid.
                            grid_ID = row[0]
                            area = row[1]
                            if area:
                                g.write(line2.format(grid_ID, width, height, n_value, direction))

                if gutter_line_rows:
                    for (
                            fid,
                            width,
                            height,
                            n_value,
                            direction,
                    ) in (
                            gutter_line_rows
                    ):  # One tuple for each line.                    # self.uc.show_info("fid %s, width: %s, height: %s , heign_value: %s, direction: %s" % (fid, width, height, n_value, direction))
                        for row in self.execute(
                                gutter_line_cells_sql, (fid,)
                        ):  # Gets each cell number that pairs with line_fid.
                            grid_ID = row[0]
                            line = row[1]
                            if line:
                                g.write(line2.format(grid_ID, width, height, n_value, direction))
            return True

        except Exception:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn('WARNING 060319.1613: Export to "GUTTER.DAT" failed!.')
            QApplication.restoreOverrideCursor()
            return False

    def export_sed(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_sed_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_sed_hdf5(subdomain)

    def export_sed_hdf5(self, subdomain):
        """
        Function to export sediment data to hdf5 file
        """
        try:
            # check if there is any sedimentation data defined.
            if self.is_table_empty("mud") and self.is_table_empty("sed"):
                return False

            ISED = self.gutils.get_cont_par("ISED")
            MUD = self.gutils.get_cont_par("MUD")

            if ISED == "0" and MUD == "0":
                return False

            sed_m_sql = """SELECT va, vb, ysa, ysb, sgsm, xkx FROM mud ORDER BY fid;"""
            sed_ce_sql = """SELECT isedeqg, isedsizefrac, dfifty, sgrad, sgst, dryspwt, cvfg, isedsupply, isedisplay, scourdep
                                        FROM sed ORDER BY fid;"""
            sed_z_sql = """SELECT dist_fid, isedeqi, bedthick, cvfi FROM sed_groups ORDER BY dist_fid;"""
            sed_p_sql = """SELECT sediam, sedpercent FROM sed_group_frac_data WHERE dist_fid = ? ORDER BY sedpercent;"""
            areas_d_sql = """SELECT fid, debrisv FROM mud_areas ORDER BY fid;"""
            areas_s_sql = """SELECT fid, dist_fid, isedcfp, ased, bsed FROM sed_supply_areas ORDER BY dist_fid;"""
            data_n_sql = """SELECT ssediam, ssedpercent FROM sed_supply_frac_data WHERE dist_fid = ? ORDER BY ssedpercent;"""

            if not subdomain:
                cells_d_sql = """SELECT grid_fid FROM mud_cells WHERE area_fid = ? ORDER BY grid_fid;"""
                cells_r_sql = """SELECT grid_fid FROM sed_rigid_cells ORDER BY grid_fid;"""
                cells_s_sql = """SELECT grid_fid FROM sed_supply_cells WHERE area_fid = ?;"""
                areas_g_sql = """SELECT fid, group_fid FROM sed_group_areas ORDER BY fid;"""
                cells_g_sql = """SELECT grid_fid FROM sed_group_cells WHERE area_fid = ? ORDER BY grid_fid;"""
            else:
                cells_d_sql = f"""SELECT 
                                                md.domain_cell 
                                            FROM 
                                                mud_cells AS mc
                                            JOIN 
                                                schema_md_cells md ON mc.grid_fid = md.grid_fid
                                            WHERE 
                                                area_fid = ? AND md.domain_fid = {subdomain};"""

                cells_r_sql = f"""SELECT 
                                                md.domain_cell 
                                            FROM 
                                                sed_rigid_cells AS rc
                                            JOIN 
                                                schema_md_cells md ON rc.grid_fid = md.grid_fid
                                            WHERE 
                                                md.domain_fid = {subdomain};"""
                cells_s_sql = f"""SELECT 
                                                md.domain_cell  
                                            FROM 
                                                sed_supply_cells AS sc
                                            JOIN 
                                                schema_md_cells md ON sc.grid_fid = md.grid_fid
                                            WHERE 
                                                area_fid = ? AND md.domain_fid = {subdomain};"""
                group_sql = f"""
                                            SELECT 
                                                md.domain_cell, sg.group_fid
                                            FROM 
                                                sed_group_areas AS sg
                                            JOIN 
                                                sed_group_cells AS gc ON sg.fid = gc.area_fid
                                            JOIN 
                                                schema_md_cells AS md ON gc.grid_fid = md.grid_fid
                                            WHERE 
                                                md.domain_fid = {subdomain}
                                            ORDER BY 
                                                sg.fid;
                                        """

            one_value = "{0}\n"
            two_values = "{0}  {1}\n"
            three_values = "{0}  {1}  {2}\n"
            four_values = "{0}  {1}  {2}  {3}\n"
            five_values = "{0}  {1}  {2}  {3}  {4}\n"
            six_values = "{0}  {1}  {2}  {3}  {4}  {5}\n"
            ten_values = "{0}  {1}  {2}  {3}  {4}  {5}  {6}  {7}  {8}  {9}\n"

            m_data = self.execute(sed_m_sql).fetchone()
            ce_data = self.execute(sed_ce_sql).fetchone()
            if m_data is None and ce_data is None:
                return False

            sed_group = self.parser.sed_group

            if MUD in ["1", "2"] and m_data is not None:
                # Mud/debris transport or 2 phase flow:
                try:
                    sed_group.datasets["MUDFLOW_PARAMS"].data.append(create_array(six_values, 6, np.float64, m_data))
                except:
                    sed_group.create_dataset('MUDFLOW_PARAMS', [])
                    sed_group.datasets["MUDFLOW_PARAMS"].data.append(create_array(six_values, 6, np.float64, m_data))

                if int(float(self.gutils.get_cont_par("IDEBRV"))) == 1:
                    for aid, debrisv in self.execute(areas_d_sql):
                        gid = self.execute(cells_d_sql, (aid,)).fetchone()[0]
                        try:
                            sed_group.datasets["MUDFLOW_AREAS"].data.append(
                                create_array(two_values, 2, np.float64, (gid, debrisv)))
                        except:
                            sed_group.create_dataset('MUDFLOW_AREAS', [])
                            sed_group.datasets["MUDFLOW_AREAS"].data.append(
                                create_array(two_values, 2, np.float64, (gid, debrisv)))

            if (ISED == "1" or MUD == "2") and ce_data is not None:
                # Sediment Transport or 2 phase flow:
                try:
                    sed_group.datasets["SED_PARAMS"].data.append(
                        create_array(ten_values, 10, np.float64, tuple(ce_data)))
                except:
                    sed_group.create_dataset('SED_PARAMS', [])
                    sed_group.datasets["SED_PARAMS"].data.append(
                        create_array(ten_values, 10, np.float64, tuple(ce_data)))

                for row in self.execute(sed_z_sql):
                    dist_fid = row[0]

                    try:
                        sed_group.datasets["SED_GROUPS"].data.append(
                            create_array(four_values, 4, np.float64, row))
                    except:
                        sed_group.create_dataset('SED_GROUPS', [])
                        sed_group.datasets["SED_GROUPS"].data.append(
                            create_array(four_values, 4, np.float64, row))

                    for prow in self.execute(sed_p_sql, (dist_fid,)):
                        try:
                            sed_group.datasets["SED_GROUPS_FRAC_DATA"].data.append(
                                create_array(three_values, 3, np.float64, dist_fid, *prow))
                        except:
                            sed_group.create_dataset('SED_GROUPS_FRAC_DATA', [])
                            sed_group.datasets["SED_GROUPS_FRAC_DATA"].data.append(
                                create_array(three_values, 3, np.float64, dist_fid, *prow))

                for row in self.execute(cells_r_sql):
                    try:
                        sed_group.datasets["SED_RIGID_CELLS"].data.append(
                            create_array(one_value, 1, np.int_, row))
                    except:
                        sed_group.create_dataset('SED_RIGID_CELLS', [])
                        sed_group.datasets["SED_RIGID_CELLS"].data.append(
                            create_array(one_value, 1, np.int_, row))

                for row in self.execute(areas_s_sql):
                    aid = row[0]
                    dist_fid = row[1] if row[1] != "" else 0
                    result = self.execute(cells_s_sql, (aid,)).fetchone()
                    if result:
                        gid = result[0]
                        try:
                            sed_group.datasets["SED_SUPPLY_AREAS"].data.append(
                                create_array(five_values, 5, np.float64, dist_fid, gid, *row[2:]))
                        except:
                            sed_group.create_dataset('SED_SUPPLY_AREAS', [])
                            sed_group.datasets["SED_SUPPLY_AREAS"].data.append(
                                create_array(five_values, 5, np.float64, dist_fid, gid, *row[2:]))

                    for nrow in self.execute(data_n_sql, (dist_fid,)):
                        try:
                            sed_group.datasets["SED_SUPPLY_FRAC_DATA"].data.append(
                                create_array(three_values, 3, np.float64, dist_fid, *nrow))
                        except:
                            sed_group.create_dataset('SED_SUPPLY_FRAC_DATA', [])
                            sed_group.datasets["SED_SUPPLY_FRAC_DATA"].data.append(
                                create_array(three_values, 3, np.float64, dist_fid, *nrow))

                if not subdomain:
                    areas_g = self.execute(areas_g_sql)
                    if areas_g:
                        for group_fid in areas_g:
                            gids = self.execute(cells_g_sql, (group_fid[0],)).fetchall()
                            if gids:
                                for g in gids:
                                    try:
                                        sed_group.datasets["SED_GROUPS_AREAS"].data.append(
                                            create_array(two_values, 2, np.int_, group_fid[0], g[0]))
                                    except:
                                        sed_group.create_dataset('SED_GROUPS_AREAS', [])
                                        sed_group.datasets["SED_GROUPS_AREAS"].data.append(
                                            create_array(two_values, 2, np.int_, group_fid[0], g[0]))
                else:
                    result = self.execute(group_sql).fetchall()
                    for grid_id, group_id in result:
                        try:
                            sed_group.datasets["SED_GROUPS_AREAS"].data.append(
                                create_array(two_values, 2, np.int_, group_id, grid_id))
                        except:
                            sed_group.create_dataset('SED_GROUPS_AREAS', [])
                            sed_group.datasets["SED_GROUPS_AREAS"].data.append(
                                create_array(two_values, 2, np.int_, group_id, grid_id))

            self.parser.write_groups(sed_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("Error while exporting sediment data to hdf5 failed!.\n", e)
            self.uc.log_info("Error while exporting sediment data to hdf5 failed!")
            return False

    def export_sed_dat(self, outdir, subdomain):
        try:
            # check if there is any sedimentation data defined.
            if self.is_table_empty("mud") and self.is_table_empty("sed"):
                return False

            ISED = self.gutils.get_cont_par("ISED")
            MUD = self.gutils.get_cont_par("MUD")

            if ISED == "0" and MUD == "0":
                return False

            sed_m_sql = """SELECT va, vb, ysa, ysb, sgsm, xkx FROM mud ORDER BY fid;"""
            sed_ce_sql = """SELECT isedeqg, isedsizefrac, dfifty, sgrad, sgst, dryspwt, cvfg, isedsupply, isedisplay, scourdep
                            FROM sed ORDER BY fid;"""
            sed_z_sql = """SELECT dist_fid, isedeqi, bedthick, cvfi FROM sed_groups ORDER BY dist_fid;"""
            sed_p_sql = """SELECT sediam, sedpercent FROM sed_group_frac_data WHERE dist_fid = ? ORDER BY sedpercent;"""
            areas_d_sql = """SELECT fid, debrisv FROM mud_areas ORDER BY fid;"""
            areas_s_sql = """SELECT fid, dist_fid, isedcfp, ased, bsed FROM sed_supply_areas ORDER BY dist_fid;"""
            data_n_sql = """SELECT ssediam, ssedpercent FROM sed_supply_frac_data WHERE dist_fid = ? ORDER BY ssedpercent;"""

            if not subdomain:
                cells_d_sql = """SELECT grid_fid FROM mud_cells WHERE area_fid = ? ORDER BY grid_fid;"""
                cells_r_sql = """SELECT grid_fid FROM sed_rigid_cells ORDER BY grid_fid;"""
                cells_s_sql = """SELECT grid_fid FROM sed_supply_cells WHERE area_fid = ?;"""
                areas_g_sql = """SELECT fid, group_fid FROM sed_group_areas ORDER BY fid;"""
                cells_g_sql = """SELECT grid_fid FROM sed_group_cells WHERE area_fid = ? ORDER BY grid_fid;"""
            else:
                cells_d_sql = f"""SELECT 
                                    md.domain_cell 
                                FROM 
                                    mud_cells AS mc
                                JOIN 
                                    schema_md_cells md ON mc.grid_fid = md.grid_fid
                                WHERE 
                                    area_fid = ? AND md.domain_fid = {subdomain};"""

                cells_r_sql = f"""SELECT 
                                    md.domain_cell 
                                FROM 
                                    sed_rigid_cells AS rc
                                JOIN 
                                    schema_md_cells md ON rc.grid_fid = md.grid_fid
                                WHERE 
                                    md.domain_fid = {subdomain};"""
                cells_s_sql = f"""SELECT 
                                    md.domain_cell  
                                FROM 
                                    sed_supply_cells AS sc
                                JOIN 
                                    schema_md_cells md ON sc.grid_fid = md.grid_fid
                                WHERE 
                                    area_fid = ? AND md.domain_fid = {subdomain};"""
                group_sql = f"""
                                SELECT 
                                    md.domain_cell, sg.group_fid
                                FROM 
                                    sed_group_areas AS sg
                                JOIN 
                                    sed_group_cells AS gc ON sg.fid = gc.area_fid
                                JOIN 
                                    schema_md_cells AS md ON gc.grid_fid = md.grid_fid
                                WHERE 
                                    md.domain_fid = {subdomain}
                                ORDER BY 
                                    sg.fid;
                            """

            line1 = "M  {0}  {1}  {2}  {3}  {4}  {5}\n"
            line2 = "C  {0}  {1}  {2}  {3}  {4}  {5}  {6} {7}  {8}\n"
            line3 = "Z  {0}  {1}  {2}\n"
            line4 = "P  {0}  {1}\n"
            line5 = "D  {0}  {1}\n"
            line6 = "E  {0}\n"
            line7 = "R  {0}\n"
            line8 = "S  {0}  {1}  {2}  {3}\n"
            line9 = "N  {0}  {1}\n"
            line10 = "G  {0}  {1}\n"

            m_data = self.execute(sed_m_sql).fetchone()
            ce_data = self.execute(sed_ce_sql).fetchone()
            if m_data is None and ce_data is None:
                return False

            sed = os.path.join(outdir, "SED.DAT")
            with open(sed, "w") as s:
                if MUD in ["1", "2"] and m_data is not None:
                    # Mud/debris transport or 2 phase flow:
                    s.write(line1.format(*m_data))

                    if int(self.gutils.get_cont_par("IDEBRV")) == 1:
                        for aid, debrisv in self.execute(areas_d_sql):
                            result = self.execute(cells_d_sql, (aid,)).fetchone()
                            if result:  # Ensure result is not None
                                gid = result[0]
                                s.write(line5.format(gid, debrisv))
                    e_data = None

                if (ISED == "1" or MUD == "2") and ce_data is not None:
                    # Sediment Transport or 2 phase flow:
                    e_data = ce_data[-1]
                    s.write(line2.format(*ce_data[:-1]))

                    for row in self.execute(sed_z_sql):
                        dist_fid = row[0]
                        s.write(line3.format(*row[1:]))
                        for prow in self.execute(sed_p_sql, (dist_fid,)):
                            s.write(line4.format(*prow))

                    if e_data is not None:
                        s.write(line6.format(e_data))

                    for row in self.execute(cells_r_sql):
                        s.write(line7.format(*row))

                    for row in self.execute(areas_s_sql):
                        aid = row[0]
                        dist_fid = row[1]
                        result = self.execute(cells_s_sql, (aid,)).fetchone()
                        if result:
                            gid = result[0]
                            s.write(line8.format(gid, *row[2:]))
                            for nrow in self.execute(data_n_sql, (dist_fid,)):
                                s.write(line9.format(*nrow))

                    if not subdomain:
                        areas_g = self.execute(areas_g_sql)
                        if areas_g:
                            for aid, group_fid in areas_g:
                                gids = self.execute(cells_g_sql, (aid,)).fetchall()
                                if gids:
                                    for g in gids[0]:
                                        s.write(line10.format(g, group_fid))
                    else:
                        result = self.execute(group_sql).fetchall()
                        for grid_id, group_id in result:
                            s.write(line10.format(grid_id, group_id))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1612: exporting SED.DAT failed!.\n", e)
            return False

    def export_levee(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_levee_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_levee_hdf5(subdomain)

    def export_levee_hdf5(self, subdomain):
        """
        Function to export levee data to HDF5 file
        """
        # check if there are any levees defined.
        # try:
        if self.is_table_empty("levee_data"):
            return False

        levee_gen_sql = """SELECT raiselev, ilevfail, gfragchar, gfragprob FROM levee_general;"""

        if not subdomain:
            levee_data_sql = """SELECT grid_fid, ldir, levcrest FROM levee_data ORDER BY grid_fid, fid;"""
            levee_fail_sql = """SELECT  grid_fid, 
                                        lfaildir, 
                                        failevel,
                                        failtime,
                                        levbase,
                                        failwidthmax,
                                        failrate,
                                        failwidrate 
                                    FROM levee_failure ORDER BY grid_fid, fid;"""
            levee_frag_sql = """SELECT grid_fid, levfragchar, levfragprob FROM levee_fragility ORDER BY grid_fid;"""
        else:
            levee_data_sql = f"""
                                     SELECT 
                                        md.domain_cell, 
                                        ld.ldir, 
                                        ld.levcrest 
                                     FROM 
                                        levee_data AS ld
                                     JOIN
                                        schema_md_cells md ON ld.grid_fid = md.grid_fid
                                     WHERE 
                                        md.domain_fid = {subdomain}
                                     ORDER BY 
                                        md.domain_cell, ld.fid;
                                     """

            levee_fail_sql = f"""
                                     SELECT 
                                        md.domain_cell, 
                                        lf.lfaildir, 
                                        lf.failevel,
                                        lf.failtime,
                                        lf.levbase,
                                        lf.failwidthmax,
                                        lf.failrate,
                                        lf.failwidrate
                                     FROM 
                                        levee_failure AS lf
                                     JOIN
                                        schema_md_cells md ON lf.grid_fid = md.grid_fid
                                     WHERE 
                                        md.domain_fid = {subdomain}
                                     ORDER BY 
                                        md.domain_cell, lf.fid;
                                     """

            levee_frag_sql = f"""
                                     SELECT 
                                        md.domain_cell, 
                                        lf.levfragchar, 
                                        lf.levfragprob 
                                     FROM 
                                        levee_fragility AS lf
                                     JOIN
                                        schema_md_cells md ON lf.grid_fid = md.grid_fid
                                     WHERE 
                                        md.domain_fid = {subdomain}
                                     ORDER BY 
                                        md.domain_cell;
                                     """

        # line1 = "{0}  {1}\n"
        # line3 = "{0}  {1}  {2}\n"
        # line4 = "F  {0}\n"
        # line5 = "W  {0}  {1}  {2}  {3}  {4}  {5}  {6}\n"
        line6 = "C  {0}  {1}\n"
        line7 = "P  {0}  {1}  {2}\n"

        has_levee = self.execute(levee_data_sql).fetchone()
        if has_levee is None:
            self.gutils.set_cont_par("LEVEE", 0)
            return False
        else:
            self.gutils.set_cont_par("LEVEE", 1)

        general = self.execute(levee_gen_sql).fetchone()
        if general is None:
            general = (0, 0, None, None)
        head = general[:2]
        glob_frag = general[2:]

        levee_group = self.parser.levee_group

        levee_group.create_dataset('LEVEE_GLOBAL', [])
        levee_group.datasets["LEVEE_GLOBAL"].data.append(np.array(head, dtype=float))

        levee_group.create_dataset('LEVEE_DATA', [])
        levee_data = self.execute(levee_data_sql).fetchall()
        for data in levee_data:
            levee_group.datasets["LEVEE_DATA"].data.append(np.array([data[0], data[1], data[2]], dtype=float))

        # levee_group.create_dataset('LEVEE', [])

        if head[1] == 1:
            levee_group.create_dataset('LEVEE_FAILURE', [])
            levee_failure = self.execute(levee_fail_sql).fetchall()
            for failure in levee_failure:
                levee_group.datasets["LEVEE_FAILURE"].data.append(np.array([
                    failure[0],
                    failure[1],
                    failure[2],
                    failure[3],
                    failure[4],
                    failure[5],
                    failure[6],
                    failure[7]],
                    dtype=float))

        # if None not in glob_frag:
        #     levee_group.datasets["LEVEE"].data.append(create_array(line6, 8, np.bytes_, glob_frag))
        # else:
        #     pass
        # for row in self.execute(levee_frag_sql):
        #     levee_group.datasets["LEVEE"].data.append(create_array(line7, 8, np.bytes_, row))

        self.parser.write_groups(levee_group)
        return True

        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error("ERROR 101218.1614: exporting LEVEE.DAT failed!.\n", e)
        #     return False

    def export_levee_dat(self, outdir, subdomain):
        # check if there are any levees defined.
        try:
            if self.is_table_empty("levee_data"):
                return False
            levee_gen_sql = """SELECT raiselev, ilevfail, gfragchar, gfragprob FROM levee_general;"""

            if not subdomain:
                levee_data_sql = """SELECT grid_fid, ldir, levcrest FROM levee_data ORDER BY grid_fid, fid;"""
                levee_fail_sql = """SELECT * FROM levee_failure ORDER BY grid_fid, fid;"""
                levee_frag_sql = """SELECT grid_fid, levfragchar, levfragprob FROM levee_fragility ORDER BY grid_fid;"""
            else:
                levee_data_sql = f"""
                                 SELECT 
                                    md.domain_cell, 
                                    ld.ldir, 
                                    ld.levcrest 
                                 FROM 
                                    levee_data AS ld
                                 JOIN
                                    schema_md_cells md ON ld.grid_fid = md.grid_fid
                                 WHERE 
                                    md.domain_fid = {subdomain}
                                 ORDER BY 
                                    md.domain_cell, ld.fid;
                                 """

                levee_fail_sql = f"""
                                 SELECT 
                                    md.domain_cell, 
                                    lf.lfaildir, 
                                    lf.failevel,
                                    lf.failtime,
                                    lf.levbase,
                                    lf.failwidthmax,
                                    lf.failrate,
                                    lf.failwidrate
                                 FROM 
                                    levee_failure AS lf
                                 JOIN
                                    schema_md_cells md ON lf.grid_fid = md.grid_fid
                                 WHERE 
                                    md.domain_fid = {subdomain}
                                 ORDER BY 
                                    md.domain_cell, lf.fid;
                                 """

                levee_frag_sql = f"""
                                 SELECT 
                                    md.domain_cell, 
                                    lf.levfragchar, 
                                    lf.levfragprob 
                                 FROM 
                                    levee_fragility AS lf
                                 JOIN
                                    schema_md_cells md ON lf.grid_fid = md.grid_fid
                                 WHERE 
                                    md.domain_fid = {subdomain}
                                 ORDER BY 
                                    md.domain_cell;
                                 """

            line1 = "{0}  {1}\n"
            line2 = "L  {0}\n"
            line3 = "D  {0}  {1}\n"
            line4 = "F  {0}\n"
            line5 = "W  {0}  {1}  {2}  {3}  {4}  {5}  {6}\n"
            line6 = "C  {0}  {1}\n"
            line7 = "P  {0}  {1}  {2}\n"

            has_levee = self.execute(levee_data_sql).fetchone()
            if has_levee is None:
                self.gutils.set_cont_par("LEVEE", 0)
                return False
            else:
                self.gutils.set_cont_par("LEVEE", 1)

            general = self.execute(levee_gen_sql).fetchone()
            if general is None:
                # TODO: Need to implement correct export for levee_general, levee_failure and levee_fragility
                general = (0, 0, None, None)
            head = general[:2]
            glob_frag = general[2:]
            levee = os.path.join(outdir, "LEVEE.DAT")
            with open(levee, "w") as l:
                l.write(line1.format(*head))
                levee_rows = groupby(self.execute(levee_data_sql), key=itemgetter(0))
                for gid, directions in levee_rows:
                    l.write(line2.format(gid))
                    for row in directions:
                        l.write(line3.format(*row[1:]))
                if head[1] == 1:
                    fail_rows = groupby(self.execute(levee_fail_sql), key=itemgetter(1))
                    for gid, directions in fail_rows:
                        l.write(line4.format(gid))
                        for row in directions:
                            rowl = list(row)
                            for i in range(0, len(rowl)):
                                rowl[i] = rowl[i] if rowl[i] is not None else 0
                                rowl[i] = rowl[i] if rowl[i] != "None" else 0
                            row = tuple(rowl)
                            l.write(line5.format(*row[2:]))
                if None not in glob_frag:
                    l.write(line6.format(*glob_frag))
                else:
                    pass
                for row in self.execute(levee_frag_sql):
                    l.write(line7.format(*row))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.bar_error("Exporting LEVEE.DAT failed!")
            self.uc.log_info("Exporting LEVEE.DAT failed!")
            return False

    def export_fpxsec(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_fpxsec_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_fpxsec_hdf5(subdomain)

    def export_fpxsec_hdf5(self, subdomain):
        """
        Function to export floodplain cross-section data to hdf5 file
        """

        if self.is_table_empty("fpxsec"):
            return False

        cont_sql = """SELECT name, value FROM cont WHERE name = 'NXPRT';"""
        fpxsec_sql = """SELECT fid, iflo, nnxsec FROM fpxsec ORDER BY fid;"""
        if not subdomain:
            cell_sql = """SELECT grid_fid FROM fpxsec_cells WHERE fpxsec_fid = ? ORDER BY grid_fid;"""
        else:
            cell_sql = f"""
                        SELECT
                            md.domain_cell  
                        FROM 
                            fpxsec_cells AS fc
                        JOIN
                            schema_md_cells md ON fc.grid_fid = md.grid_fid
                        WHERE 
                            fc.fpxsec_fid = ? AND md.domain_fid = {subdomain}
                        ORDER BY fc.grid_fid
                        """

        option = self.execute(cont_sql).fetchone()
        if option is None:
            return False
        else:
            pass

        max_grid = 0
        for row in self.execute(fpxsec_sql):
            fid, iflo, nnxsec = row
            grids = self.execute(cell_sql, (fid,)).fetchall()
            if len(grids) > max_grid:
                max_grid = len(grids)
        max_grid += 2

        floodplain_group = self.parser.floodplain_group
        floodplain_group.create_dataset('FPXSEC_DATA', [])
        floodplain_group.create_dataset('FPXSEC_GLOBAL', [])

        head = option[-1]
        floodplain_group.datasets["FPXSEC_GLOBAL"].data.append(int(head))

        for row in self.execute(fpxsec_sql):
            fid, iflo, _ = row
            grids = self.execute(cell_sql, (fid,)).fetchall()
            if len(grids) > 0:
                grids_txt = " ".join(["{}".format(x[0]) for x in grids])
                grids_list = [int(num) for num in grids_txt.split()]
                fpxsec = [iflo, len(grids)] + grids_list
                fpxsec.extend([-9999] * (max_grid - len(fpxsec)))
                values_str = "{} " * len(fpxsec)
                floodplain_group.datasets["FPXSEC_DATA"].data.append(
                    create_array(values_str, max_grid, np.int_, tuple(fpxsec)))

        self.parser.write_groups(floodplain_group)
        return True

    def export_fpxsec_dat(self, outdir, subdomain):
        # check if there are any floodplain cross section defined.
        try:
            if self.is_table_empty("fpxsec"):
                return False
            cont_sql = """SELECT name, value FROM cont WHERE name = 'NXPRT';"""
            fpxsec_sql = """SELECT fid, iflo, nnxsec FROM fpxsec ORDER BY fid;"""
            if not subdomain:
                cell_sql = """SELECT grid_fid FROM fpxsec_cells WHERE fpxsec_fid = ? ORDER BY grid_fid;"""
            else:
                cell_sql = f"""
                            SELECT
                                md.domain_cell  
                            FROM 
                                fpxsec_cells AS fc
                            JOIN
                                schema_md_cells md ON fc.grid_fid = md.grid_fid
                            WHERE 
                                fc.fpxsec_fid = ? AND md.domain_fid = {subdomain}
                            ORDER BY fc.grid_fid
                            """

            line1 = "P  {}\n"
            line2 = "X {0} {1} {2}\n"

            option = self.execute(cont_sql).fetchone()
            if option is None:
                return False
            else:
                pass
            fpxsec = os.path.join(outdir, "FPXSEC.DAT")
            with open(fpxsec, "w") as f:
                head = option[-1]
                f.write(line1.format(head))

                for row in self.execute(fpxsec_sql):
                    fid, iflo, nnxsec = row
                    grids = self.execute(cell_sql, (fid,)).fetchall()
                    if len(grids) > 0:
                        grids_txt = " ".join(["{}".format(x[0]) for x in grids])
                        f.write(line2.format(iflo, len(grids), grids_txt))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1613: exporting FPXSEC.DAT failed!.\n", e)
            return False

    def export_breach(self, output=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_breach_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_breach_hdf5()

    def export_breach_hdf5(self):
        """
        Function to export breach data to hdf5
        """
        # check if there is any breach defined.
        try:
            # Check conditions to save BREACH.DAT:
            if self.is_table_empty("levee_data"):
                return False
            ilevfail_sql = """SELECT ilevfail FROM levee_general;"""
            ilevfail = self.execute(ilevfail_sql).fetchone()
            if ilevfail is None:
                return False
            if ilevfail[0] != 2:
                return False
            if self.is_table_empty("breach"):
                return False

            # Writes BREACH.DAT if ILEVFAIL = 2.
            breach_global_columns = [
                "ibreachsedeqn", "gbratio", "gweircoef", "gbreachtime", "useglobaldata",
                "gzu", "gzd", "gzc", "gcrestwidth", "gcrestlength", "gbrbotwidmax", "gbrtopwidmax",
                "gbrbottomel", "gd50c", "gporc", "guwc", "gcnc", "gafrc", "gcohc", "gunfcc",
                "gd50s", "gpors", "guws", "gcns", "gafrs", "gcohs", "gunfcs", "ggrasslength",
                "ggrasscond", "ggrassvmaxp", "gsedconmax", "gd50df", "gunfcdf"
            ]

            breach_individual_columns = [
                "fid", "ibreachdir", "zu", "zd", "zc", "crestwidth", "crestlength",
                "brbotwidmax", "brtopwidmax", "brbottomel", "weircoef", "d50c", "porc", "uwc",
                "cnc", "afrc", "cohc", "unfcc", "d50s", "pors", "uws", "cns", "afrs", "cohs",
                "unfcs", "bratio", "grasslength", "grasscond", "grassvmaxp", "sedconmax",
                "d50df", "unfcdf", "breachtime"
            ]

            global_sql = f"""
                SELECT {', '.join(breach_global_columns)}
                FROM breach_global
                ORDER BY fid;
            """
            local_sql = f"""
                SELECT {', '.join(breach_individual_columns)} 
                FROM breach 
                ORDER BY fid;"""

            cells_sql = """SELECT grid_fid FROM breach_cells WHERE breach_fid = ?;"""
            frag_sql = """SELECT fragchar, prfail, prdepth FROM breach_fragility_curves ORDER BY fid;"""

            global_rows = self.execute(global_sql).fetchall()
            local_rows = self.execute(local_sql).fetchall()
            fragility_rows = self.execute(frag_sql).fetchall()

            if not global_rows and not local_rows:
                return False

            levee_group = self.parser.levee_group

            if global_rows:
                levee_group.create_dataset('BREACH_GLOBAL', [])
                for row in global_rows:
                    row = list(row)
                    row[0] = int(row[0])
                    row[4] = int(row[4])
                    for value in row:
                        levee_group.datasets["BREACH_GLOBAL"].data.append([value])

            if local_rows:
                levee_group.create_dataset('BREACH_INDIVIDUAL', [])
                columns = []
                for row in local_rows:
                    row = list(row)
                    fid = row[0]
                    row[1] = int(row[1])
                    gid = self.execute(cells_sql, (fid,)).fetchone()[0]
                    columns.append([gid] + row[1:])

                # Transpose to get columns
                columns = list(map(list, zip(*columns)))

                # Append each column as a new row (since HDF5 datasets are row-major)
                for col in columns:
                    levee_group.datasets["BREACH_INDIVIDUAL"].data.append(col)

            if fragility_rows:
                levee_group.create_dataset('FRAGILITY_CURVES', [])
                for row in fragility_rows:
                    fragchar, prfail, prdepth = row
                    levee_group.datasets["FRAGILITY_CURVES"].data.append([fragchar, prfail, prdepth])

            self.parser.write_groups(levee_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("Error while exporting BREACH data to hdf5 file!\n", e)
            self.uc.log_info("Error while exporting BREACH data to hdf5 file!")
            return False

    def export_breach_dat(self, outdir):
        # check if there is any breach defined.
        try:
            # Check conditions to save BREACH.DAT:
            if self.is_table_empty("levee_data"):
                return False
            ilevfail_sql = """SELECT ilevfail FROM levee_general;"""
            ilevfail = self.execute(ilevfail_sql).fetchone()
            if ilevfail is None:
                return False
            if ilevfail[0] != 2:
                return False
            if self.is_table_empty("breach"):
                return False

            # Writes BREACH.DAT if ILEVFAIL = 2.

            global_sql = """SELECT * FROM breach_global ORDER BY fid;"""
            local_sql = """SELECT * FROM breach ORDER BY fid;"""
            cells_sql = """SELECT grid_fid FROM breach_cells WHERE breach_fid = ?;"""
            frag_sql = """SELECT fragchar, prfail, prdepth FROM breach_fragility_curves ORDER BY fid;"""

            b1, g1, g2, g3, g4 = (
                slice(1, 5),
                slice(6, 14),
                slice(14, 21),
                slice(21, 28),
                slice(28, 34),
            )
            b2, d1, d2, d3, d4 = (
                slice(0, 2),
                slice(2, 11),
                slice(11, 18),
                slice(18, 25),
                slice(25, 33),
            )

            bline = "B{0} {1}\n"
            line_1 = "{0}1 {1}\n"
            line_2 = "{0}2 {1}\n"
            line_3 = "{0}3 {1}\n"
            line_4 = "{0}4 {1}\n"
            fline = "F {0} {1} {2}\n"

            parts = [
                [g1, d1, line_1],
                [g2, d2, line_2],
                [g3, d3, line_3],
                [g4, d4, line_4],
            ]

            global_rows = self.execute(global_sql).fetchall()
            local_rows = self.execute(local_sql).fetchall()
            fragility_rows = self.execute(frag_sql)

            if not global_rows and not local_rows:
                return False
            else:
                pass
            breach = os.path.join(outdir, "BREACH.DAT")
            with open(breach, "w") as b:
                c = 1

                for row in global_rows:
                    # Write 'B1' line (general variables):
                    row_slice = [str(x) if x is not None else "" for x in row[b1]]
                    b.write(bline.format(c, " ".join(row_slice)))

                    # Write G1,G2,G3,G4 lines if 'Use Global Data' checkbox is selected in Global Breach Data dialog:

                    if not local_rows:
                        if row[5] == 1:  # useglobaldata
                            for gslice, dslice, line in parts:
                                row_slice = [str(x) if x is not None else "" for x in row[gslice]]
                                if any(row_slice) is True:
                                    b.write(line.format("G", "  ".join(row_slice)))
                                else:
                                    pass

                c += 1

                for row in local_rows:
                    fid = row[0]
                    gid = self.execute(cells_sql, (fid,)).fetchone()[0]
                    row_slice = [str(x) if x is not None else "" for x in row[b2]]
                    row_slice[0] = str(gid)
                    row_slice[1] = str(int(row_slice[1]))
                    b.write(bline.format(c, " ".join(row_slice)))
                    for gslice, dslice, line in parts:
                        row_slice = [str(x) if x is not None else "" for x in row[dslice]]
                        if any(row_slice) is True:
                            b.write(line.format("D", "  ".join(row_slice)))
                        else:
                            pass
                c += 1

                for row in fragility_rows:
                    b.write(fline.format(*row))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1616: exporting BREACH.DAT failed!.\n", e)
            return False

    def export_fpfroude(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_fpfroude_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_fpfroude_hdf5(subdomain)

    def export_fpfroude_hdf5(self, subdomain):
        # check if there is any limiting Froude number defined.
        try:
            if self.is_table_empty("fpfroude"):
                return False

            if not subdomain:
                fpfroude_sql = """
                    SELECT fc.grid_fid, f.froudefp
                    FROM fpfroude_cells AS fc
                    JOIN fpfroude AS f ON fc.area_fid = f.fid
                    ORDER BY fc.area_fid;
                """
            else:
                fpfroude_sql = f"""
                                SELECT 
                                    md.domain_cell, 
                                    f.froudefp
                                FROM 
                                    fpfroude_cells AS fc
                                JOIN 
                                    fpfroude AS f ON fc.area_fid = f.fid
                                JOIN 
                                    schema_md_cells AS md ON fc.grid_fid = md.grid_fid
                                WHERE 
                                    md.domain_fid = {subdomain}
                                """

            line1 = "{0} {1}\n"

            fpfroude_rows = self.execute(fpfroude_sql).fetchall()
            if not fpfroude_rows:
                return False
            else:
                pass
            spatially_variable_group = self.parser.spatially_variable_group
            spatially_variable_group.create_dataset('FPFROUDE', [])

            for fid, froudefp in fpfroude_rows:
                spatially_variable_group.datasets["FPFROUDE"].data.append(
                    create_array(line1, 2, np.float64, fid, froudefp))

            self.parser.write_groups(spatially_variable_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1617: exporting FPFROUDE failed!.\n", e)
            return False

    def export_fpfroude_dat(self, outdir, subdomain):
        try:
            # Check if there is any limiting Froude number defined.
            if self.is_table_empty("fpfroude"):
                return False

            # Single query to get all necessary data
            if not subdomain:
                fpfroude_sql = """
                    SELECT fc.grid_fid, f.froudefp
                    FROM fpfroude_cells AS fc
                    JOIN fpfroude AS f ON fc.area_fid = f.fid
                    ORDER BY fc.area_fid;
                """
            else:
                fpfroude_sql = f"""
                                SELECT 
                                    md.domain_cell, 
                                    f.froudefp
                                FROM 
                                    fpfroude_cells AS fc
                                JOIN 
                                    fpfroude AS f ON fc.area_fid = f.fid
                                JOIN 
                                    schema_md_cells AS md ON fc.grid_fid = md.grid_fid
                                WHERE 
                                    md.domain_fid = {subdomain}
                                """

            # Fetch all rows at once
            fpfroude_rows = self.execute(fpfroude_sql).fetchall()
            if not fpfroude_rows:
                return False

            # Prepare file path
            fpfroude_dat = os.path.join(outdir, "FPFROUDE.DAT")

            # Batch write to the file
            with open(fpfroude_dat, "w") as f:
                lines = [f"F {gid} {froudefp}\n" for gid, froudefp in fpfroude_rows]
                f.writelines(lines)

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1617: exporting FPFROUDE.DAT failed!.\n", e)
            return False

    def export_shallowNSpatial(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_shallowNSpatial_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_shallowNSpatial_hdf5(subdomain)

    def export_shallowNSpatial_hdf5(self, subdomain):
        """
        Function to export shallow n values to hdf5 file
        """
        try:
            if self.is_table_empty("spatialshallow"):
                return False
            shallow_sql = """SELECT fid, shallow_n FROM spatialshallow ORDER BY fid;"""
            if not subdomain:
                cell_sql = """SELECT grid_fid FROM spatialshallow_cells WHERE area_fid = ? ORDER BY grid_fid;"""
            else:
                cell_sql = f"""SELECT 
                                    md.domain_cell 
                                FROM 
                                    spatialshallow_cells AS ss
                                JOIN 
                                    schema_md_cells md ON ss.grid_fid = md.grid_fid
                                WHERE 
                                    area_fid = ? AND md.domain_fid = {subdomain};"""

            line1 = "{0} {1}\n"

            shallow_rows = self.execute(shallow_sql).fetchall()
            if not shallow_rows:
                return False
            else:
                pass

            spatially_variable_group = self.parser.spatially_variable_group
            spatially_variable_group.create_dataset('SHALLOWN_SPATIAL', [])

            for fid, shallow_n in shallow_rows:
                for row in self.execute(cell_sql, (fid,)):
                    gid = row[0]
                    spatially_variable_group.datasets["SHALLOWN_SPATIAL"].data.append(
                        create_array(line1, 2, np.float64, gid, shallow_n))

            self.parser.write_groups(spatially_variable_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1901: exporting SHALLOWN_SPATIAL failed!", e)
            return False

    def export_shallowNSpatial_dat(self, outdir, subdomain):
        # check if there is any shallow-n defined.
        try:
            if self.is_table_empty("spatialshallow"):
                return False
            shallow_sql = """SELECT fid, shallow_n FROM spatialshallow ORDER BY fid;"""
            if not subdomain:
                cell_sql = """SELECT grid_fid FROM spatialshallow_cells WHERE area_fid = ? ORDER BY grid_fid;"""
            else:
                cell_sql = f"""SELECT 
                                    md.domain_cell 
                                FROM 
                                    spatialshallow_cells AS ss
                                JOIN 
                                    schema_md_cells md ON ss.grid_fid = md.grid_fid
                                WHERE 
                                    area_fid = ? AND md.domain_fid = {subdomain};"""

            line1 = "{0} {1}\n"

            shallow_rows = self.execute(shallow_sql).fetchall()
            if not shallow_rows:
                return False
            else:
                pass
            shallow_dat = os.path.join(outdir, "SHALLOWN_SPATIAL.DAT")
            with open(shallow_dat, "w") as s:
                for fid, shallow_n in shallow_rows:
                    for row in self.execute(cell_sql, (fid,)):
                        gid = row[0]
                        s.write(line1.format(gid, shallow_n))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1901: exporting SHALLOWN_SPATIAL.DAT failed!", e)
            return False

    def export_swmmflo(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_swmmflo_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_swmmflo_hdf5(subdomain)

    def export_swmmflodropbox(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_swmmflodropbox_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_swmmflodropbox_hdf5(subdomain)

    def export_sdclogging(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_sdclogging_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_sdclogging_hdf5(subdomain)

    # def export_swmminp(self, output, subdomain=None):
    #     if self.parsed_format == self.FORMAT_DAT:
    #         return self.export_swmminp(output, subdomain)
    #     elif self.parsed_format == self.FORMAT_HDF5:
    #         return self.export_swmminp("hdf5", subdomain)

    def select_this_INP_group(self, INP_groups, chars):
        """Returns the whole .INP group [´chars'xxx]

        ´chars' is the  beginning of the string. Only the first 4 or 5 lower case letters are used in all calls.
        Returns a list of strings of the whole group, one list item for each line of the original .INP file.

        """
        part = None
        if INP_groups is None:
            return part
        else:
            for tag in list(INP_groups.keys()):
                low_tag = tag.lower()
                if low_tag.startswith(chars):
                    part = INP_groups[tag]
                    break
                else:
                    continue
            return (
                part  # List of strings in .INT_groups dictionary item keyed by 'chars' (e.e.´junc', 'cond', 'outf',...)
            )

    def export_swmminp(self, outdir=None, subdomain=None):

        # If outdir is None, it means we are exporting to HDF5 format.
        if outdir is None or not os.path.isdir(outdir):
            outdir = os.path.dirname(self.parser.hdf5_filepath)

        try:

            if self.gutils.is_table_empty("user_swmm_inlets_junctions"):
                self.uc.bar_warn(
                    'User Layer "Storm Drain Inlets/Junctions" is empty!'
                )
                self.uc.log_info(
                    'User Layer "Storm Drain Inlets/Junctions" is empty!\n\n'
                    + "Please import components from .INP file or shapefile, or convert from schematized Storm Drains."
                )
                return

            # # Set the default SD control variables
            # if self.gutils.is_table_empty("swmm_control"):
            #     dlg_INP_groups = INP_GroupsDialog(self.con, self.iface)
            #     dlg_INP_groups.save_INP_control()

            INP_groups = OrderedDict()

            swmm_file = outdir + r"\SWMM.INP"
            if os.path.isfile(swmm_file):
                QApplication.setOverrideCursor(Qt.ArrowCursor)
                replace = self.uc.question("SWMM.INP already exists.\n\n" + "Would you like to replace it?")
                QApplication.restoreOverrideCursor()
                if not replace:
                    return

            if os.path.isfile(swmm_file):
                # File exist, therefore import groups:
                with open(swmm_file) as swmm_inp:  # open(file, mode='r',...) defaults to mode 'r' read.
                    for chunk in swmm_inp.read().split(
                            "["
                    ):  # chunk gets all text (including newlines) until next '[' (may be empty)
                        try:
                            key, value = chunk.split("]")  # divide chunk into:
                            # key = name of group (e.g. JUNCTIONS) and
                            # value = rest of text until ']'
                            INP_groups[key] = value.split(
                                "\n"
                            )  # add new item {key, value.split('\n')} to dictionary INP_groups.
                            # E.g.:
                            #   key:
                            #     JUNCTIONS
                            #   value.split('\n') is list of strings:
                            #    I1  4685.00    6.00000    0.00       0.00       0.00
                            #    I2  4684.95    6.00000    0.00       0.00       0.00
                            #    I3  4688.87    6.00000    0.00       0.00       0.00
                        except ValueError:
                            continue

            else:
                # File doen't exists.Create groups.
                pass


            # Show dialog with [TITLE], [OPTIONS], and [REPORT], with values taken from existing .INP file (if selected),
            # and project units, start date, report start.

            start_date = NULL
            end_date = NULL
            non_sync_dates = 0

            nodes_names = []
            links_names = []

            has_junctions = False
            has_outfalls = False
            has_storage = False
            has_conduits = False
            has_pumps = False
            has_orifices = False
            has_weirs = False

            with open(swmm_file, "w") as swmm_inp_file:
                no_in_out_conduits = 0
                no_in_out_pumps = 0
                no_in_out_orifices = 0
                no_in_out_weirs = 0

                # INP TITLE ##################################################
                swmm_inp_file.write("[TITLE]")
                title = self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'TITLE'").fetchone()
                if not title:
                    title = "INP file exported by FLO-2D"
                    swmm_inp_file.write("\n" + title + "\n")
                else:
                    swmm_inp_file.write("\n" + title[0] + "\n")

                # INP OPTIONS ##################################################
                swmm_inp_file.write("\n[OPTIONS]")
                flow_units = self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'FLOW_UNITS'").fetchone()
                if not flow_units:
                    self.uc.bar_warn(
                        'Storm Drain control variables not set!'
                    )
                    self.uc.log_info(
                        'Storm Drain control variables not set!\n\n'
                        + "Please, set the Storm Drain control variables."
                    )
                    return
                else:
                    flow_units = flow_units[0]
                swmm_inp_file.write("\nFLOW_UNITS           " + flow_units)
                swmm_inp_file.write("\nINFILTRATION         HORTON")
                swmm_inp_file.write("\nFLOW_ROUTING         DYNWAVE")
                start_date = self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'START_DATE'").fetchone()[
                    0]
                swmm_inp_file.write("\nSTART_DATE           " + start_date)
                start_time = self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'START_TIME'").fetchone()[
                    0]
                swmm_inp_file.write("\nSTART_TIME           " + start_time)
                report_start_date = \
                self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'REPORT_START_DATE'").fetchone()[0]
                swmm_inp_file.write("\nREPORT_START_DATE    " + report_start_date)
                report_start_time = \
                self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'REPORT_START_TIME'").fetchone()[0]
                swmm_inp_file.write("\nREPORT_START_TIME    " + report_start_time)
                end_date = self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'END_DATE'").fetchone()[0]
                swmm_inp_file.write("\nEND_DATE             " + end_date)
                end_time = self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'END_TIME'").fetchone()[0]
                swmm_inp_file.write("\nEND_TIME             " + end_time)
                swmm_inp_file.write("\nSWEEP_START          01/01")
                swmm_inp_file.write("\nSWEEP_END            12/31")
                swmm_inp_file.write("\nDRY_DAYS             0")
                report_step = \
                self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'REPORT_STEP'").fetchone()[0]
                swmm_inp_file.write("\nREPORT_STEP          " + report_step)
                swmm_inp_file.write("\nWET_STEP             00:05:00")
                swmm_inp_file.write("\nDRY_STEP             01:00:00")
                swmm_inp_file.write("\nROUTING_STEP         00:01:00")
                swmm_inp_file.write("\nALLOW_PONDING        NO")
                swmm_inp_file.write("\nINERTIAL_DAMPING     PARTIAL")
                swmm_inp_file.write("\nVARIABLE_STEP        0.75")
                swmm_inp_file.write("\nLENGTHENING_STEP     0")
                swmm_inp_file.write("\nMIN_SURFAREA         0")
                swmm_inp_file.write("\nNORMAL_FLOW_LIMITED  BOTH")
                skip_steady_state = \
                self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'SKIP_STEADY_STATE'").fetchone()[0]
                swmm_inp_file.write("\nSKIP_STEADY_STATE    " + skip_steady_state)
                force_main_equation = \
                self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'FORCE_MAIN_EQUATION'").fetchone()[0]
                if force_main_equation in ['Darcy-Weisbach (D-W)', 'D-W']:
                    force_main_equation = "D-W"
                else:
                    force_main_equation = "H-W"
                swmm_inp_file.write("\nFORCE_MAIN_EQUATION  " + force_main_equation)
                link_offsets = \
                self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'LINK_OFFSETS'").fetchone()[0]
                swmm_inp_file.write("\nLINK_OFFSETS         " + link_offsets)
                min_slope = self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'MIN_SLOPE'").fetchone()[0]
                swmm_inp_file.write("\nMIN_SLOPE            " + min_slope)

                # INP JUNCTIONS ##################################################
                try:
                    if not subdomain:
                        SD_junctions_sql = """SELECT name, junction_invert_elev, max_depth, init_depth, surcharge_depth, ponded_area
                                          FROM user_swmm_inlets_junctions WHERE sd_type = "I" or sd_type = "i" or sd_type = "J" ORDER BY name;"""
                    else:
                        SD_junctions_sql = f"""
                        SELECT 
                            usij.name, 
                            usij.junction_invert_elev, 
                            usij.max_depth, 
                            usij.init_depth, 
                            usij.surcharge_depth, 
                            usij.ponded_area
                        FROM 
                            user_swmm_inlets_junctions AS usij
                        LEFT JOIN
                            schema_md_cells md ON usij.grid = md.grid_fid
                        WHERE 
                            usij.sd_type IN ('I', 'i', 'J')
                            AND (
                                (md.domain_fid = {subdomain}
								OR usij.grid + 0 = 0)
                                AND EXISTS (
                                    SELECT 1
                                    FROM mult_domains AS mdm
                                    WHERE mdm.fid = {subdomain}
                                      AND ST_Intersects(CastAutomagic(usij.geom), CastAutomagic(mdm.geom))
                                )
                            )
                        ORDER BY 
                            usij.name;"""

                    junctions_rows = self.gutils.execute(SD_junctions_sql).fetchall()
                    if not junctions_rows:
                        pass
                    else:
                        has_junctions = True
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[JUNCTIONS]")
                        swmm_inp_file.write("\n;;               Invert     Max.       Init.      Surcharge  Ponded")
                        swmm_inp_file.write("\n;;Name           Elev.      Depth      Depth      Depth      Area")
                        swmm_inp_file.write(
                            "\n;;-------------- ---------- ---------- ---------- ---------- ----------"
                        )

                        line = "\n{0:16} {1:<10.2f} {2:<10.2f} {3:<10.2f} {4:<10.2f} {5:<10.2f}"
                        for row in junctions_rows:
                            nodes_names.append(row[0])
                            row = (
                                row[0],
                                0 if row[1] is None else row[1],
                                0 if row[2] is None else row[2],
                                0 if row[3] is None else row[3],
                                0 if row[4] is None else row[4],
                                0,
                            )
                            swmm_inp_file.write(line.format(*row))
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 070618.0851: error while exporting [JUNCTIONS] to .INP file!", e)
                    return

                # INP OUTFALLS ###################################################
                try:
                    if not subdomain:
                        SD_outfalls_sql = """SELECT name, outfall_invert_elev, outfall_type, time_series, tidal_curve, flapgate, fixed_stage 
                                          FROM user_swmm_outlets ORDER BY name;"""
                    else:
                        SD_outfalls_sql = f"""
                        SELECT 
                            uso.name, 
                            uso.outfall_invert_elev, 
                            uso.outfall_type, 
                            uso.time_series, 
                            uso.tidal_curve, 
                            uso.flapgate, 
                            uso.fixed_stage 
                        FROM 
                            user_swmm_outlets AS uso
                        LEFT JOIN
                            schema_md_cells md ON uso.grid = md.grid_fid
                        WHERE 
                            (
                                md.domain_fid = {subdomain} 
                                OR uso.grid + 0 = 0
                            )
                            AND EXISTS (
                                SELECT 1
                                FROM mult_domains AS mdm
                                WHERE mdm.fid = {subdomain}
                                  AND ST_Intersects(CastAutomagic(uso.geom), CastAutomagic(mdm.geom))
                            )
                        ORDER BY 
                            uso.name;"""

                    outfalls_rows = self.gutils.execute(SD_outfalls_sql).fetchall()
                    if not outfalls_rows:
                        pass
                    else:
                        has_outfalls = True
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[OUTFALLS]")
                        swmm_inp_file.write("\n;;               Invert     Outfall      Stage/Table       Tide")
                        swmm_inp_file.write("\n;;Name           Elev.      Type         Time Series       Gate")
                        swmm_inp_file.write("\n;;-------------- ---------- ------------ ----------------  ----")

                        line = "\n{0:16} {1:<10.2f} {2:<11} {3:<18} {4:<16}"

                        for row in outfalls_rows:
                            lrow = list(row)
                            nodes_names.append(lrow[0])
                            lrow = [
                                lrow[0],
                                0 if lrow[1] is None else lrow[1],
                                0 if lrow[2] is None else lrow[2],
                                "   " if lrow[3] is None else lrow[3],
                                0 if lrow[4] is None else lrow[4],
                                0 if lrow[5] is None else lrow[5],
                                0 if lrow[6] is None else lrow[6],
                            ]
                            lrow[3] = "*" if lrow[3] == "..." else "*" if lrow[3] == "" else lrow[3]
                            lrow[4] = "*" if lrow[4] == "..." else "*" if lrow[4] == "" else lrow[4]
                            lrow[2] = lrow[2].upper().strip()
                            if not lrow[2] in ("FIXED", "FREE", "NORMAL", "TIDAL", "TIMESERIES"):
                                lrow[2] = "NORMAL"
                            lrow[2] = (
                                "TIDAL"
                                if lrow[2] == "TIDAL CURVE"
                                else "TIMESERIES"
                                if lrow[2] == "TIME SERIES"
                                else lrow[2]
                            )

                            # Set 3rt. value:
                            if lrow[2] == "FREE" or lrow[2] == "NORMAL":
                                lrow[3] = "    "
                            elif lrow[2] == "TIMESERIES":
                                lrow[3] = lrow[3]
                            elif lrow[2] == "TIDAL":
                                lrow[3] = lrow[4]
                            elif lrow[2] == "FIXED":
                                lrow[3] = lrow[6]

                            lrow[5] = "YES" if lrow[5] in ("True", "true", "Yes", "yes", "1") else "NO"
                            swmm_inp_file.write(line.format(lrow[0], lrow[1], lrow[2], lrow[3], lrow[5]))

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 070618.1619: error while exporting [OUTFALLS] to .INP file!", e)
                    return

                # INP STORAGE ###################################################
                try:
                    if not subdomain:
                        SD_storages_sql = """SELECT name, invert_elev, max_depth, init_depth, storage_curve,
                                                    coefficient, exponent, constant, ponded_area, 
                                                    evap_factor, suction_head, conductivity, initial_deficit, curve_name, infiltration
                                             FROM user_swmm_storage_units ORDER BY name;"""
                    else:
                        SD_storages_sql = f"""
                        SELECT 
                            ussu.name, 
                            ussu.invert_elev,
                            ussu.max_depth, 
                            ussu.init_depth, 
                            ussu.storage_curve,
                            ussu.coefficient, 
                            ussu.exponent, 
                            ussu.constant, 
                            ussu.ponded_area, 
                            ussu.evap_factor, 
                            ussu.suction_head, 
                            ussu.conductivity, 
                            ussu.initial_deficit, 
                            ussu.curve_name, 
                            ussu.infiltration
                        FROM 
                            user_swmm_storage_units AS ussu
                        JOIN
                            schema_md_cells md ON ussu.grid = md.grid_fid
                        WHERE 
                            (
                                md.domain_fid = {subdomain} 
                                OR ussu.grid + 0 = 0
                            )
                            AND EXISTS (
                                SELECT 1
                                FROM mult_domains AS mdm
                                WHERE mdm.fid = {subdomain}
                                  AND ST_Intersects(CastAutomagic(ussu.geom), CastAutomagic(mdm.geom))
                            )
                        ORDER BY ussu.name;"""

                    storages_rows = self.gutils.execute(SD_storages_sql).fetchall()
                    if not storages_rows:
                        pass
                    else:
                        has_storage = True
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[STORAGE]")
                        swmm_inp_file.write(
                            "\n;;               Invert   Max.     Init.    Storage    Curve                      Ponded   Evap.")
                        swmm_inp_file.write(
                            "\n;;Name           Elev.    Depth    Depth    Curve      Params                     Area     Frac.    Infiltration Parameters")
                        swmm_inp_file.write(
                            "\n;;-------------- -------- -------- -------- ---------- -------- -------- -------- -------- -------- -----------------------")

                        line_functional_with_infil = "\n{0:16} {1:<8} {2:<8} {3:<8} {4:<10} {5:<8} {6:<8} {7:<8} {8:<8} {9:<8} {10:<8} {11:<8} {12:<8}"
                        line_tabular_with_infil = "\n{0:16} {1:<8} {2:<8} {3:<8} {4:<10} {5:<26} {6:<8} {7:<8} {8:<8} {9:<8} {10:<8}"
                        line_functional_no_infil = "\n{0:16} {1:<8} {2:<8} {3:<8} {4:<10} {5:<8} {6:<8} {7:<8} {8:<8} {9:<8}"
                        line_tabular_no_infil = "\n{0:16} {1:<8} {2:<8} {3:<8} {4:<10} {5:<26} {6:<8} {7:<8}"

                        for row in storages_rows:
                            lrow = list(row)
                            nodes_names.append(lrow[0])
                            lrow = [
                                lrow[0],
                                0 if lrow[1] is None else '%g' % lrow[1],
                                0 if lrow[2] is None else '%g' % lrow[2],
                                0 if lrow[3] is None else '%g' % lrow[3],
                                "FUNCTIONAL" if lrow[4] is None else lrow[4],
                                0 if lrow[5] is None else '%g' % lrow[5],
                                0 if lrow[6] is None else '%g' % lrow[6],
                                0 if lrow[7] is None else '%g' % lrow[7],
                                0,
                                0 if lrow[9] is None else '%g' % lrow[9],
                                0 if lrow[10] is None else '%g' % lrow[10],
                                0 if lrow[11] is None else '%g' % lrow[11],
                                0 if lrow[12] is None else '%g' % lrow[12],
                                lrow[13],
                                lrow[14]
                            ]
                            if lrow[4] == "FUNCTIONAL":
                                if lrow[14] == "True":
                                    swmm_inp_file.write(
                                        line_functional_with_infil.format(lrow[0], lrow[1], lrow[2], lrow[3], lrow[4],
                                                                          lrow[5],
                                                                          lrow[6], lrow[7], lrow[8], lrow[9],
                                                                          lrow[10], lrow[11], lrow[12]))
                                else:
                                    swmm_inp_file.write(
                                        line_functional_no_infil.format(lrow[0], lrow[1], lrow[2], lrow[3], lrow[4],
                                                                        lrow[5],
                                                                        lrow[6], lrow[7], lrow[8], lrow[9]))

                            else:
                                if lrow[14] == "True":
                                    swmm_inp_file.write(
                                        line_tabular_with_infil.format(lrow[0], lrow[1], lrow[2], lrow[3], lrow[4],
                                                                       lrow[13], lrow[8], lrow[9],
                                                                       lrow[10], lrow[11], lrow[12]))
                                else:
                                    swmm_inp_file.write(
                                        line_tabular_no_infil.format(lrow[0], lrow[1], lrow[2], lrow[3], lrow[4],
                                                                     lrow[13], lrow[8], lrow[9]))

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 160224.0541: error while exporting [STORAGE] to .INP file!", e)
                    return

                # INP CONDUITS ###################################################
                try:
                    if not subdomain:
                        SD_conduits_sql = """SELECT conduit_name, conduit_inlet, conduit_outlet, conduit_length, conduit_manning, conduit_inlet_offset, 
                                            conduit_outlet_offset, conduit_init_flow, conduit_max_flow 
                                      FROM user_swmm_conduits ORDER BY conduit_name;"""
                        conduits_rows = self.gutils.execute(SD_conduits_sql).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        SD_conduits_sql = f"""
                        SELECT
                            usc.conduit_name,
                            usc.conduit_inlet,
                            usc.conduit_outlet,
                            usc.conduit_length,
                            usc.conduit_manning,
                            usc.conduit_inlet_offset,
                            usc.conduit_outlet_offset,
                            usc.conduit_init_flow,
                            usc.conduit_max_flow
                        FROM
                            user_swmm_conduits AS usc
                        WHERE 
                            usc.conduit_inlet IN ({placeholders}) AND usc.conduit_outlet IN ({placeholders})
                        ORDER BY
                            usc.conduit_name;"""
                        conduits_rows = self.gutils.execute(SD_conduits_sql, nodes_names + nodes_names).fetchall()

                    if not conduits_rows:
                        pass
                    else:
                        has_conduits = True
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[CONDUITS]")
                        swmm_inp_file.write(
                            "\n;;               Inlet            Outlet                      Manning    Inlet      Outlet     Init.      Max."
                        )
                        swmm_inp_file.write(
                            "\n;;Name           Node             Node             Length     N          Offset     Offset     Flow       Flow"
                        )
                        swmm_inp_file.write(
                            "\n;;-------------- ---------------- ---------------- ---------- ---------- ---------- ---------- ---------- ----------"
                        )

                        line = "\n{0:16} {1:<16} {2:<16} {3:<10.2f} {4:<10.3f} {5:<10.2f} {6:<10.2f} {7:<10.2f} {8:<10.2f}"

                        for row in conduits_rows:
                            row = (
                                row[0],
                                "?" if row[1] is None or row[1] == "" else row[1],
                                "?" if row[2] is None or row[2] == "" else row[2],
                                0 if row[3] is None else row[3],
                                0 if row[4] is None else row[4],
                                0 if row[5] is None else row[5],
                                0 if row[6] is None else row[6],
                                0 if row[7] is None else row[7],
                                0 if row[8] is None else row[8],
                            )
                            links_names.append(row[0])
                            if row[1] == "?" or row[2] == "?":
                                no_in_out_conduits += 1
                            swmm_inp_file.write(line.format(*row))
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 070618.1620: error while exporting [CONDUITS] to .INP file!", e)
                    return

                # INP PUMPS ###################################################
                try:
                    if not subdomain:
                        SD_pumps_sql = """SELECT pump_name, pump_inlet, pump_outlet, pump_curve, pump_init_status, 
                                            pump_startup_depth, pump_shutoff_depth 
                                            FROM user_swmm_pumps ORDER BY fid;"""
                        pumps_rows = self.gutils.execute(SD_pumps_sql).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        SD_pumps_sql = f"""
                        SELECT 
                            usp.pump_name, 
                            usp.pump_inlet, 
                            usp.pump_outlet,
                            usp.pump_curve, 
                            usp.pump_init_status,            
                            usp.pump_startup_depth, 
                            usp.pump_shutoff_depth          
                        FROM 
                            user_swmm_pumps AS usp
                        WHERE 
                            usp.pump_inlet IN ({placeholders}) AND usp.pump_outlet IN ({placeholders})
                        ORDER BY 
                            usp.fid;"""
                        pumps_rows = self.gutils.execute(SD_pumps_sql, nodes_names + nodes_names).fetchall()

                    if not pumps_rows:
                        pass
                    else:
                        has_pumps = True
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[PUMPS]")
                        swmm_inp_file.write(
                            "\n;;               Inlet            Outlet           Pump             Init.      Startup    Shutup"
                        )
                        swmm_inp_file.write(
                            "\n;;Name           Node             Node             Curve            Status     Depth      Depth"
                        )
                        swmm_inp_file.write(
                            "\n;;-------------- ---------------- ---------------- ---------------- ---------- ---------- -------"
                        )

                        line = "\n{0:16} {1:<16} {2:<16} {3:<16} {4:<10} {5:<10.2f} {6:<10.2f}"

                        for row in pumps_rows:
                            row = (
                                row[0],
                                "?" if row[1] is None or row[1] == "" else row[1],
                                "?" if row[2] is None or row[2] == "" else row[2],
                                "*" if row[3] is None else row[3],
                                "OFF" if row[4] is None else row[4],
                                0 if row[5] is None else row[5],
                                0 if row[6] is None else row[6],
                            )
                            links_names.append(row[0])
                            if row[1] == "?" or row[2] == "?":
                                no_in_out_pumps += 1
                            swmm_inp_file.write(line.format(*row))
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 271121.0515: error while exporting [PUMPS] to .INP file!", e)
                    return

                # INP ORIFICES ###################################################
                try:
                    if not subdomain:
                        SD_orifices_sql = """SELECT orifice_name, orifice_inlet, orifice_outlet, orifice_type, orifice_crest_height, 
                                        orifice_disch_coeff, orifice_flap_gate, orifice_open_close_time 
                                        FROM user_swmm_orifices ORDER BY orifice_name;"""
                        orifices_rows = self.gutils.execute(SD_orifices_sql).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        SD_orifices_sql = f"""
                        SELECT 
                            uso.orifice_name, 
                            uso.orifice_inlet, 
                            uso.orifice_outlet, 
                            uso.orifice_type, 
                            uso.orifice_crest_height, 
                            uso.orifice_disch_coeff, 
                            uso.orifice_flap_gate, 
                            uso.orifice_open_close_time 
                        FROM 
                            user_swmm_orifices AS uso
                        WHERE 
                            uso.orifice_inlet IN ({placeholders}) AND uso.orifice_outlet IN ({placeholders})
                        ORDER BY 
                            uso.orifice_name;"""
                        orifices_rows = self.gutils.execute(SD_orifices_sql, nodes_names + nodes_names).fetchall()

                    if not orifices_rows:
                        pass
                    else:
                        has_orifices = True
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[ORIFICES]")
                        swmm_inp_file.write(
                            "\n;;               Inlet            Outlet           Orifice      Crest      Disch.      Flap      Open/Close"
                        )
                        swmm_inp_file.write(
                            "\n;;Name           Node             Node             Type         Height     Coeff.      Gate      Time"
                        )
                        swmm_inp_file.write(
                            "\n;;-------------- ---------------- ---------------- ------------ ---------- ----------- --------- -----------"
                        )

                        line = "\n{0:16} {1:<16} {2:<16} {3:<12} {4:<10.2f} {5:<11.2f} {6:<9} {7:<9.2f}"

                        for row in orifices_rows:
                            row = (
                                row[0],
                                "?" if row[1] is None or row[1] == "" else row[1],
                                "?" if row[2] is None or row[2] == "" else row[2],
                                "SIDE" if row[3] is None else row[3],
                                0 if row[4] is None else row[4],
                                0 if row[5] is None else row[5],
                                "NO" if row[6] is None else row[6],
                                0 if row[7] is None else row[7],
                            )
                            links_names.append(row[0])
                            if row[1] == "?" or row[2] == "?":
                                no_in_out_orifices += 1
                            swmm_inp_file.write(line.format(*row))
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 310322.1548: error while exporting [ORIFICES] to .INP file!", e)
                    return

                # INP WEIRS ###################################################
                try:
                    if not subdomain:
                        SD_weirs_sql = """SELECT weir_name, weir_inlet, weir_outlet, weir_type, weir_crest_height, 
                                            weir_disch_coeff, weir_flap_gate, weir_end_contrac, weir_end_coeff 
                                            FROM user_swmm_weirs ORDER BY weir_name;"""
                        weirs_rows = self.gutils.execute(SD_weirs_sql).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        SD_weirs_sql = f"""
                        SELECT 
                            usw.weir_name, 
                            usw.weir_inlet, 
                            usw.weir_outlet, 
                            usw.weir_type, 
                            usw.weir_crest_height, 
                            usw.weir_disch_coeff, 
                            usw.weir_flap_gate, 
                            usw.weir_end_contrac, 
                            usw.weir_end_coeff 
                        FROM 
                            user_swmm_weirs AS usw
                        WHERE 
                            usw.weir_inlet IN ({placeholders}) AND usw.weir_outlet IN ({placeholders})
                        ORDER BY 
                            usw.weir_name;"""
                        weirs_rows = self.gutils.execute(SD_weirs_sql, nodes_names + nodes_names).fetchall()

                    if not weirs_rows:
                        pass
                    else:
                        has_weirs = True
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[WEIRS]")
                        swmm_inp_file.write(
                            "\n;;               Inlet            Outlet           Weir         Crest      Disch.      Flap      End      End"
                        )
                        swmm_inp_file.write(
                            "\n;;Name           Node             Node             Type         Height     Coeff.      Gate      Con.     Coeff."
                        )
                        swmm_inp_file.write(
                            "\n;;-------------- ---------------- ---------------- ------------ ---------- ----------- --------- -------  ---------"
                        )

                        line = "\n{0:16} {1:<16} {2:<16} {3:<12} {4:<10.2f} {5:<11.2f} {6:<9} {7:<8} {8:<9.2f}"

                        for row in weirs_rows:
                            row = (
                                row[0],
                                "?" if row[1] is None or row[1] == "" else row[1],
                                "?" if row[2] is None or row[2] == "" else row[2],
                                "TRANSVERSE" if row[3] is None else row[3],
                                0 if row[4] is None else row[4],
                                0 if row[5] is None else row[5],
                                "NO" if row[6] is None else row[6],
                                "0" if row[7] is None else int(round(row[7], 0)),
                                0 if row[8] is None else row[8],
                            )
                            links_names.append(row[0])
                            if row[1] == "?" or row[2] == "?":
                                no_in_out_weirs += 1
                            swmm_inp_file.write(line.format(*row))
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 090422.0557: error while exporting [WEIRS] to .INP file!", e)
                    return

                # INP XSECTIONS ###################################################
                try:
                    swmm_inp_file.write("\n")
                    swmm_inp_file.write("\n[XSECTIONS]")
                    swmm_inp_file.write(
                        "\n;;Link           Shape        Geom1      Geom2      Geom3      Geom4      Barrels"
                    )
                    swmm_inp_file.write(
                        "\n;;-------------- ------------ ---------- ---------- ---------- ---------- ----------"
                    )

                    # XSections from user conduits:
                    if not subdomain:
                        SD_xsections_1_sql = """SELECT conduit_name, xsections_shape, xsections_max_depth, xsections_geom2, 
                                                xsections_geom3, xsections_geom4, xsections_barrels
                                          FROM user_swmm_conduits ORDER BY conduit_name;"""
                        xsections_rows_1 = self.gutils.execute(SD_xsections_1_sql).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        SD_xsections_1_sql = f"""
                        SELECT
                            usc.conduit_name,
                            usc.xsections_shape,
                            usc.xsections_max_depth,
                            usc.xsections_geom2,
                            usc.xsections_geom3,
                            usc.xsections_geom4,
                            usc.xsections_barrels
                        FROM
                            user_swmm_conduits AS usc
                        WHERE 
                            usc.conduit_inlet IN ({placeholders}) AND usc.conduit_outlet IN ({placeholders})
                        ORDER BY
                            usc.conduit_name;"""
                        xsections_rows_1 = self.gutils.execute(SD_xsections_1_sql, nodes_names + nodes_names).fetchall()

                    line = "\n{0:16} {1:<13} {2:<10.2f} {3:<10.2f} {4:<10.3f} {5:<10.2f} {6:<10}"

                    if not xsections_rows_1:
                        pass
                    else:
                        no_xs = 0

                        for row in xsections_rows_1:
                            lrow = list(row)
                            lrow = (
                                "?" if lrow[0] is None or lrow[0] == "" else lrow[0],
                                "?" if lrow[1] is None or lrow[0] == "" else lrow[1],
                                "?" if lrow[2] is None or lrow[0] == "" else lrow[2],
                                "?" if lrow[3] is None or lrow[0] == "" else lrow[3],
                                "?" if lrow[4] is None or lrow[0] == "" else lrow[4],
                                "?" if lrow[5] is None or lrow[0] == "" else lrow[5],
                                "?" if lrow[6] is None or lrow[0] == "" else lrow[6],
                            )
                            if (
                                    row[0] == "?"
                                    or row[1] == "?"
                                    or row[2] == "?"
                                    or row[3] == "?"
                                    or row[4] == "?"
                                    or row[5] == "?"
                                    or row[6] == "?"
                            ):
                                no_xs += 1
                            lrow = (
                                lrow[0],
                                lrow[1],
                                0.0 if lrow[2] == "?" else lrow[2],
                                0.0 if lrow[3] == "?" else lrow[3],
                                0.0 if lrow[4] == "?" else lrow[4],
                                0.0 if lrow[5] == "?" else lrow[5],
                                0.0 if lrow[6] == "?" else lrow[6],
                            )
                            row = tuple(lrow)
                            swmm_inp_file.write(line.format(*row))

                    # XSections from user orifices:
                    if not subdomain:
                        SD_xsections_2_sql = """SELECT orifice_name, orifice_shape, orifice_height, orifice_width
                                      FROM user_swmm_orifices ORDER BY orifice_name;"""
                        xsections_rows_2 = self.gutils.execute(SD_xsections_2_sql).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        SD_xsections_2_sql = f"""
                            SELECT 
                                uso.orifice_name, 
                                uso.orifice_shape, 
                                uso.orifice_height, 
                                uso.orifice_width
                            FROM 
                                user_swmm_orifices AS uso
                            WHERE 
                                uso.orifice_inlet IN ({placeholders}) AND uso.orifice_outlet IN ({placeholders})
                            ORDER BY 
                                uso.orifice_name;"""
                        xsections_rows_2 = self.gutils.execute(SD_xsections_2_sql, nodes_names + nodes_names).fetchall()

                    line = "\n{0:16} {1:<13} {2:<10.2f} {3:<10.2f} {4:<10.2f} {5:<10.2f} {6:<10}"
                    if not xsections_rows_2:
                        pass
                    else:
                        no_xs = 0

                        for row in xsections_rows_2:
                            lrow = list(row)
                            lrow = (
                                "?" if lrow[0] is None or lrow[0] == "" else lrow[0],
                                "?" if lrow[1] is None or lrow[0] == "" else lrow[1],
                                "?" if lrow[2] is None or lrow[0] == "" else lrow[2],
                                "?" if lrow[3] is None or lrow[0] == "" else lrow[3],
                                0.0,
                                0.0,
                                0,
                            )
                            if row[0] == "?" or row[1] == "?" or row[2] == "?" or row[3] == "?":
                                no_xs += 1
                            lrow = (
                                lrow[0],
                                lrow[1],
                                0.0 if lrow[2] == "?" else lrow[2],
                                0.0 if lrow[3] == "?" else 0.0 if lrow[1] == "CIRCULAR" else lrow[3],
                                0.0,
                                0.0,
                                " ",
                            )
                            row = tuple(lrow)
                            swmm_inp_file.write(line.format(*row))

                    # XSections from user weirs:
                    if not subdomain:
                        SD_xsections_3_sql = """SELECT weir_name, weir_shape, weir_height, weir_length, weir_side_slope, weir_side_slope
                                          FROM user_swmm_weirs ORDER BY weir_name;"""
                        xsections_rows_3 = self.gutils.execute(SD_xsections_3_sql).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        SD_xsections_3_sql = f"""
                        SELECT 
                            usw.weir_name, 
                            usw.weir_shape, 
                            usw.weir_height, 
                            usw.weir_length, 
                            usw.weir_side_slope, 
                            usw.weir_side_slope
                        FROM 
                            user_swmm_weirs AS usw
                        WHERE 
                            usw.weir_inlet IN ({placeholders}) AND usw.weir_outlet IN ({placeholders})
                        ORDER BY 
                            usw.weir_name;"""
                        xsections_rows_3 = self.gutils.execute(SD_xsections_3_sql, nodes_names + nodes_names).fetchall()

                    line = "\n{0:16} {1:<13} {2:<10.2f} {3:<10.2f} {4:<10.2f} {5:<10.2f} {6:<10}"
                    if not xsections_rows_3:
                        pass
                    else:
                        no_xs = 0

                        for row in xsections_rows_3:
                            lrow = list(row)
                            lrow = (
                                "?" if lrow[0] is None or lrow[0] == "" else lrow[0],
                                "?" if lrow[1] is None or lrow[0] == "" else lrow[1],
                                "?" if lrow[2] is None or lrow[0] == "" else lrow[2],
                                "?" if lrow[3] is None or lrow[0] == "" else lrow[3],
                                "?" if lrow[4] is None or lrow[4] == "" else lrow[4],
                                "?" if lrow[5] is None or lrow[5] == "" else lrow[5],
                                0,
                            )
                            if row[0] == "?" or row[1] == "?" or row[2] == "?" or row[3] == "?":
                                no_xs += 1
                            lrow = (
                                lrow[0],
                                lrow[1],
                                0.0 if lrow[2] == "?" else lrow[2],
                                0.0 if lrow[3] == "?" else 0.0 if lrow[1] == "CIRCULAR" else lrow[3],
                                0.0 if lrow[4] == "?" else lrow[4],
                                0.0 if lrow[5] == "?" else lrow[5],
                                " ",
                            )
                            row = tuple(lrow)
                            swmm_inp_file.write(line.format(*row))

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 090422.0601: error while exporting [XSECTIONS] to .INP file!", e)
                    return

                # INP LOSSES ###################################################
                try:
                    if not subdomain:
                        SD_losses_sql = """SELECT conduit_name, losses_inlet, losses_outlet, losses_average, losses_flapgate
                                          FROM user_swmm_conduits ORDER BY conduit_name;"""
                        losses_rows = self.gutils.execute(SD_losses_sql).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        SD_losses_sql = f"""
                        SELECT 
                            usc.conduit_name, 
                            usc.losses_inlet, 
                            usc.losses_outlet, 
                            usc.losses_average, 
                            usc.losses_flapgate
                        FROM
                            user_swmm_conduits AS usc
                        WHERE 
                            usc.conduit_inlet IN ({placeholders}) AND usc.conduit_outlet IN ({placeholders})
                        ORDER BY
                            usc.conduit_name;"""
                        losses_rows = self.gutils.execute(SD_losses_sql, nodes_names + nodes_names).fetchall()

                    if not losses_rows:
                        pass
                    else:
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[LOSSES]")
                        swmm_inp_file.write("\n;;Link           Inlet      Outlet     Average    Flap Gate")
                        swmm_inp_file.write("\n;;-------------- ---------- ---------- ---------- ----------")

                        line = "\n{0:16} {1:<10} {2:<10} {3:<10.2f} {4:<10}"

                        for row in losses_rows:
                            lrow = list(row)
                            lrow[4] = "YES" if lrow[4] in ("True", "true", "Yes", "yes", "1") else "NO"
                            swmm_inp_file.write(line.format(*lrow))
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 070618.1622: error while exporting [LOSSES] to .INP file!", e)
                    return

                # INP CONTROLS ##################################################
                items = self.select_this_INP_group(INP_groups, "controls")
                swmm_inp_file.write("\n\n[CONTROLS]")
                if items is not None:
                    for line in items[1:]:
                        if line != "":
                            swmm_inp_file.write("\n" + line)
                else:
                    swmm_inp_file.write("\n")

                # INP INFLOWS ###################################################
                try:
                    if not subdomain:
                        SD_inflows_sql = """SELECT node_name, constituent, baseline, pattern_name, time_series_name, scale_factor
                                          FROM swmm_inflows ORDER BY node_name;"""
                        inflows_rows = self.gutils.execute(SD_inflows_sql).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        SD_inflows_sql = f"""
                        SELECT 
                            si.node_name, 
                            si.constituent, 
                            si.baseline, 
                            si.pattern_name, 
                            si.time_series_name, 
                            si.scale_factor
                        FROM 
                            swmm_inflows AS si
                        WHERE 
                            si.node_name IN ({placeholders})
                        ORDER BY 
                            si.node_name;"""
                        inflows_rows = self.gutils.execute(SD_inflows_sql, nodes_names).fetchall()

                    if not inflows_rows:
                        pass
                    else:
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[INFLOWS]")
                        swmm_inp_file.write(
                            "\n;;Node           Constituent      Time Series      Type     Mfactor  Sfactor  Baseline Pattern"
                        )
                        swmm_inp_file.write(
                            "\n;;-------------- ---------------- ---------------- -------- -------- -------- -------- --------"
                        )
                        line = "\n{0:16} {1:<16} {2:<16} {3:<7}  {4:<8} {5:<8.2f} {6:<10} {7:<10}"
                        for row in inflows_rows:
                            lrow = [
                                row[0],
                                row[1],
                                row[4] if row[4] != "" else '""',
                                row[1],
                                "1.0",
                                row[5],
                                row[2] if row[2] != 0 else "",
                                row[3] if row[3] != "?" else "",
                            ]
                            swmm_inp_file.write(line.format(*lrow))
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 230220.0751.1622: error while exporting [INFLOWS] to .INP file!", e)
                    self.uc.log_info(f"ERROR 230220.0751.1622: error while exporting [INFLOWS] to .INP file!\n{e}")
                    return

                # INP CURVES ###################################################
                try:
                    # Pumps:
                    if not subdomain:
                        SD_pump_curves_sql = """SELECT pump_curve_name, pump_curve_type, x_value, y_value, description
                                          FROM swmm_pumps_curve_data ORDER BY pump_curve_name;"""
                        pump_curves_rows = self.gutils.execute(SD_pump_curves_sql).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(links_names))
                        SD_pump_curves_sql = f"""
                        SELECT 
                            spcd.pump_curve_name, 
                            spcd.pump_curve_type, 
                            spcd.x_value, 
                            spcd.y_value, 
                            spcd.description
                        FROM 
                            swmm_pumps_curve_data AS spcd
                        JOIN
                            user_swmm_pumps AS usp ON spcd.pump_curve_name = usp.pump_curve
                        WHERE 
                            spcd.pump_curve_name IN ({placeholders})
                        ORDER BY 
                            spcd.pump_curve_name;"""
                        pump_curves_rows = self.gutils.execute(SD_pump_curves_sql, links_names).fetchall()

                    # Tidal:
                    if not subdomain:
                        SD_tidal_curves_data_sql = """SELECT tidal_curve_name, hour, stage
                                          FROM swmm_tidal_curve_data ORDER BY tidal_curve_name;"""
                        tidal_curves_data_rows = self.gutils.execute(SD_tidal_curves_data_sql).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        SD_tidal_curves_data_sql = f"""
                        SELECT 
                            stcd.tidal_curve_name, 
                            stcd.hour, 
                            stcd.stage
                        FROM 
                            swmm_tidal_curve_data AS stcd
                        JOIN
                            user_swmm_outlets AS uso ON stcd.tidal_curve_name = uso.tidal_curve
                        WHERE 
                            uso.name IN ({placeholders})
                        ORDER BY 
                            stcd.tidal_curve_name;"""
                        tidal_curves_data_rows = self.gutils.execute(SD_tidal_curves_data_sql, nodes_names).fetchall()

                    # Other:
                    if not subdomain:
                        SD_other_curves_sql = """SELECT name, type, x_value, y_value, description
                                          FROM swmm_other_curves ORDER BY name;"""
                        other_curves_rows = self.gutils.execute(SD_other_curves_sql).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        SD_other_curves_sql = f"""
                        SELECT 
                            soc.name, 
                            soc.type, 
                            soc.x_value, 
                            soc.y_value, 
                            soc.description
                        FROM 
                            swmm_other_curves AS soc
                        JOIN
                            user_swmm_storage_units AS ussu ON soc.name = ussu.curve_name
                        WHERE 
                            ussu.name IN ({placeholders})
                        ORDER BY 
                            soc.name;"""
                        other_curves_rows = self.gutils.execute(SD_other_curves_sql, nodes_names).fetchall()

                    if not other_curves_rows and not pump_curves_rows and not tidal_curves_data_rows:
                        pass
                    else:
                        swmm_inp_file.write("\n")
                        swmm_inp_file.write("\n[CURVES]")
                        swmm_inp_file.write("\n;;Name           Type       X-Value    Y-Value")
                        swmm_inp_file.write("\n;;-------------- ---------- ---------- ----------")

                        # Write curves of type 'PumpN' (N being 1,2,3, or 4):
                        line1 = "\n{0:16} {1:<10} {2:<10.2f} {3:<10.2f}"
                        name = ""
                        for row in pump_curves_rows:
                            lrow = list(row)
                            if lrow[0] == name:
                                lrow[1] = "     "
                            else:
                                swmm_inp_file.write("\n")
                                if lrow[4]:
                                    swmm_inp_file.write("\n;" + lrow[4])
                                name = lrow[0]
                                if (len(lrow[1]) == 1 and lrow[1] != '*'):
                                    if lrow[1] == str(5):
                                        lrow[1] = '*'
                                    else:
                                        lrow[1] = f"Pump{lrow[1]}"

                            swmm_inp_file.write(line1.format(*lrow))

                        # Write curves of type 'Tidal'
                        qry_SD_tidal_curve = """SELECT tidal_curve_description
                                      FROM swmm_tidal_curve WHERE tidal_curve_name = ?;"""
                        line2 = "\n{0:16} {1:<10} {2:<10} {3:<10}"
                        name = ""
                        for row in tidal_curves_data_rows:
                            lrow = [row[0], "Tidal", row[1], row[2]]
                            if lrow[0] == name:
                                lrow[1] = "     "
                            else:
                                descr = self.gutils.execute(qry_SD_tidal_curve, (lrow[0],)).fetchone()
                                swmm_inp_file.write("\n")
                                if descr[0]:
                                    swmm_inp_file.write("\n;" + descr[0])
                                name = lrow[0]
                            swmm_inp_file.write(line2.format(*lrow))

                        # Write all other curves in storm_drain.INP_curves:
                        name = ""
                        for row in other_curves_rows:
                            lrow = list(row)
                            if lrow[0] == name:
                                lrow[1] = "     "
                            else:
                                swmm_inp_file.write("\n")
                                if lrow[4]:
                                    swmm_inp_file.write("\n;" + lrow[4])
                                name = lrow[0]
                            swmm_inp_file.write(line1.format(*lrow))

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error(
                        "ERROR 281121.0453: error while exporting [CURVES] to .INP file!\n"
                        + "Is the name or type of the curve missing in 'Storm Drain Pumps Curve Data' table?",
                        e,
                    )
                    return

                # INP TIMESERIES ###################################################
                try:
                    swmm_inp_file.write("\n")
                    swmm_inp_file.write("\n[TIMESERIES]")
                    swmm_inp_file.write("\n;;Name           Date       Time       Value     ")
                    swmm_inp_file.write("\n;;-------------- ---------- ---------- ----------")

                    if not subdomain:
                        SD_time_series_sql = """SELECT time_series_name, 
                                                            time_series_description, 
                                                            time_series_file,
                                                            time_series_data
                                          FROM swmm_time_series ORDER BY time_series_name;"""
                        time_series_rows = self.gutils.execute(SD_time_series_sql).fetchall()

                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        SD_time_series_sql = f"""
                        SELECT 
                            sts.time_series_name, 
                            sts.time_series_description, 
                            sts.time_series_file,
                            sts.time_series_data
                        FROM 
                            swmm_time_series AS sts
                        JOIN
                            swmm_inflows AS si ON sts.time_series_name = si.time_series_name
                        WHERE 
                            si.node_name IN ({placeholders})
                        ORDER BY 
                            sts.time_series_name;"""

                        time_series_rows = self.gutils.execute(SD_time_series_sql, nodes_names).fetchall()

                    SD_time_series_data_sql = """SELECT                                 
                                                        date, 
                                                        time,
                                                        value
                                      FROM swmm_time_series_data WHERE time_series_name = ?;"""

                    line1 = "\n;{0:16}"
                    line2 = "\n{0:16} {1:<10} {2:<50}"
                    line3 = "\n{0:16} {1:<10} {2:<10} {3:<7.4f}"


                    if not time_series_rows:
                        pass
                    else:
                        for row in time_series_rows:
                            if row[3] == "False":  # Inflow data comes from file:
                                description = [row[1]]
                                swmm_inp_file.write(line1.format(*description))
                                fileName = row[2].strip()
                                # fileName = os.path.basename(row[2].strip())
                                file = '"' + fileName + '"'
                                file = os.path.normpath(file)
                                lrow2 = [row[0], "FILE", file]
                                swmm_inp_file.write(line2.format(*lrow2))
                                swmm_inp_file.write("\n;")
                            else:
                                # Inflow data given in table 'swmm_time_series_data':
                                name = row[0]
                                time_series_data = self.gutils.execute(SD_time_series_data_sql, (name,)).fetchall()
                                if not time_series_data:
                                    pass
                                else:
                                    description = [row[1]]
                                    swmm_inp_file.write(line1.format(*description))
                                    for data in time_series_data:
                                        date = data[0] if data[0] is not None else "          "
                                        swmm_inp_file.write(
                                            line3.format(
                                                name if name is not None else " ",
                                                date,
                                                data[1] if data[1] is not None else "00:00",
                                                data[2] if data[2] is not None else 0.0,
                                            )
                                        )
                                        try:
                                            d0 = datetime.strptime(date, "%m/%d/%Y").date()
                                            start = datetime.strptime(start_date, "%m/%d/%Y").date()
                                            end = datetime.strptime(end_date, "%m/%d/%Y").date()
                                            if d0 < start or d0 > end:
                                                non_sync_dates += 1
                                        except ValueError:
                                            non_sync_dates += 1
                                    swmm_inp_file.write("\n;")

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 230220.1005: error while exporting [TIMESERIES] to .INP file!", e)
                    return

                # INP PATTERNS ###################################################
                try:
                    swmm_inp_file.write("\n")
                    swmm_inp_file.write("\n[PATTERNS]")
                    swmm_inp_file.write("\n;;Name           Type       Multipliers")
                    swmm_inp_file.write("\n;;-------------- ---------- -----------")

                    if not subdomain:
                        SD_inflow_patterns_sql = """SELECT pattern_name, pattern_description, hour, multiplier
                                          FROM swmm_inflow_patterns ORDER BY pattern_name;"""
                        pattern_rows = self.gutils.execute(SD_inflow_patterns_sql).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        SD_inflow_patterns_sql = f"""
                        SELECT 
                            sip.pattern_name, 
                            sip.pattern_description, 
                            sip.hour, 
                            sip.multiplier
                        FROM 
                            swmm_inflow_patterns AS sip
                        JOIN
                            swmm_inflows AS si ON sip.pattern_name = si.pattern_name
                        WHERE 
                            si.node_name IN ({placeholders})
                        ORDER BY 
                            sip.pattern_name;"""
                        pattern_rows = self.gutils.execute(SD_inflow_patterns_sql, nodes_names).fetchall()

                    # Description
                    line0 = "\n;{0:16}"
                    # Actual values
                    line1 = "\n{0:16} {1:<10} {2:<10.2f} {3:<10.2f} {4:<10.2f} {5:<10.2f} {6:<10.2f} {7:<10.2f}"

                    if not pattern_rows:
                        pass
                    else:
                        current_pattern = None
                        row_buffer = []

                        for row in pattern_rows:
                            pattern_name = row[0]
                            multiplier = row[3]

                            # Start a new pattern block
                            if pattern_name != current_pattern:
                                # if row_buffer:  # Write the previous pattern's buffered rows
                                #     row_buffer = []
                                #     swmm_inp_file.write(line1.format(*row_buffer))
                                #     swmm_inp_file.write("\n")

                                # Start the new pattern with a description
                                swmm_inp_file.write(line0.format(row[1]))  # Write description
                                current_pattern = pattern_name
                                row_buffer = [pattern_name, "HOURLY"]  # Reset buffer with pattern name and "HOURLY"

                            # Add the multiplier to the current row buffer
                            row_buffer.append(multiplier)

                            # Once buffer has 8 elements (1 pattern name, 1 HOURLY, 6 multipliers), write them
                            if len(row_buffer) == 8:
                                swmm_inp_file.write(line1.format(*row_buffer))
                                row_buffer = [pattern_name, ""]  # Reset buffer for continuation line

                        # Write any remaining data for the last pattern
                        if len(row_buffer) > 2:  # Ensure there are still multipliers left to write
                            swmm_inp_file.write(line1.format(*row_buffer))
                            swmm_inp_file.write("\n")

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 240220.0737: error while exporting [PATTERNS] to .INP file!", e)
                    self.uc.log_info(f"ERROR 240220.0737: error while exporting [PATTERNS] to .INP file!\n{e}")
                    return

                # INP REPORT ##################################################
                # items = self.select_this_INP_group(INP_groups, "report")
                swmm_inp_file.write("\n\n[REPORT]")
                input = self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'INPUT'").fetchone()[0]
                swmm_inp_file.write("\nINPUT           " + input)
                controls = self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'CONTROLS'").fetchone()[0]
                swmm_inp_file.write("\nCONTROLS        " + controls)
                swmm_inp_file.write("\nSUBCATCHMENTS   NONE")
                nodes = self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'NODES'").fetchone()[0]
                swmm_inp_file.write("\nNODES           " + nodes)
                links = self.gutils.execute("SELECT value FROM swmm_control WHERE name = 'LINKS'").fetchone()[0]
                swmm_inp_file.write("\nLINKS           " + links)

                # INP COORDINATES ##############################################
                try:
                    swmm_inp_file.write("\n")
                    swmm_inp_file.write("\n[COORDINATES]")
                    swmm_inp_file.write("\n;;Node           X-Coord            Y-Coord ")
                    swmm_inp_file.write("\n;;-------------- ------------------ ------------------")

                    if not subdomain:
                        SD_inlets_junctions_coords_sql = """SELECT name, ST_AsText(ST_Centroid(GeomFromGPB(geom)))
                                          FROM user_swmm_inlets_junctions ORDER BY name;"""
                        coordinates_rows = self.gutils.execute(SD_inlets_junctions_coords_sql).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        SD_inlets_junctions_coords_sql = f"""
                        SELECT 
                            name, 
                            ST_AsText(ST_Centroid(GeomFromGPB(geom)))
                        FROM 
                            user_swmm_inlets_junctions 
                        WHERE 
                            name IN ({placeholders})
                        ORDER BY 
                            name;"""
                        coordinates_rows = self.gutils.execute(SD_inlets_junctions_coords_sql, nodes_names).fetchall()

                    line = "\n{0:16} {1:<18} {2:<18}"

                    if not coordinates_rows:
                        pass
                    else:
                        for row in coordinates_rows:
                            x = row[:2][1].strip("POINT()").split()[0]
                            y = row[:2][1].strip("POINT()").split()[1]
                            swmm_inp_file.write(line.format(row[0], x, y))

                    if not subdomain:
                        SD_outlets_coords_sql = """SELECT name, ST_AsText(ST_Centroid(GeomFromGPB(geom)))
                                          FROM user_swmm_outlets ORDER BY name;"""
                        coordinates_rows = self.gutils.execute(SD_outlets_coords_sql).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        SD_outlets_coords_sql = f"""
                        SELECT 
                            name, 
                            ST_AsText(ST_Centroid(GeomFromGPB(geom)))
                        FROM 
                            user_swmm_outlets 
                        WHERE 
                            name IN ({placeholders})
                        ORDER BY 
                            name;"""
                        coordinates_rows = self.gutils.execute(SD_outlets_coords_sql, nodes_names).fetchall()

                    line = "\n{0:16} {1:<18} {2:<18}"

                    if not coordinates_rows:
                        pass
                    else:
                        for row in coordinates_rows:
                            x = row[:2][1].strip("POINT()").split()[0]
                            y = row[:2][1].strip("POINT()").split()[1]
                            swmm_inp_file.write(line.format(row[0], x, y))

                    if not subdomain:
                        SD_storage_coords_sql = """SELECT name, ST_AsText(ST_Centroid(GeomFromGPB(geom)))
                                          FROM user_swmm_storage_units ORDER BY name;"""
                        coordinates_rows = self.gutils.execute(SD_storage_coords_sql).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        SD_storage_coords_sql = f"""
                        SELECT 
                            name, 
                            ST_AsText(ST_Centroid(GeomFromGPB(geom)))
                        FROM 
                            user_swmm_storage_units 
                        WHERE 
                            name IN ({placeholders})
                        ORDER BY 
                            name;"""
                        coordinates_rows = self.gutils.execute(SD_storage_coords_sql, nodes_names).fetchall()

                    line = "\n{0:16} {1:<18} {2:<18}"

                    if not coordinates_rows:
                        pass
                    else:
                        for row in coordinates_rows:
                            x = row[:2][1].strip("POINT()").split()[0]
                            y = row[:2][1].strip("POINT()").split()[1]
                            swmm_inp_file.write(line.format(row[0], x, y))
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 070618.1623: error while exporting [COORDINATES] to .INP file!", e)
                    return

                # INP VERTICES ##############################################

                try:
                    swmm_inp_file.write("\n")
                    swmm_inp_file.write("\n[VERTICES]")
                    swmm_inp_file.write("\n;;Link           X-Coord            Y-Coord           ")
                    swmm_inp_file.write("\n;;-------------- ------------------ ------------------")

                    line = "\n{0:16} {1:<18} {2:<18}"

                    if not subdomain:
                        vertices_sql = self.execute("""
                            SELECT ST_AsBinary(GeomFromGPB(geom)), conduit_name 
                            FROM user_swmm_conduits
                        """).fetchall()
                    else:
                        placeholders = ','.join(['?'] * len(nodes_names))
                        vertices_sql = self.execute(f"""
                            SELECT ST_AsBinary(GeomFromGPB(geom)), conduit_name
                            FROM user_swmm_conduits
                            WHERE conduit_inlet IN ({placeholders}) AND conduit_outlet IN ({placeholders})
                        """, nodes_names + nodes_names).fetchall()

                    for row in vertices_sql:
                        wkb_geom, conduit_name = row

                        if not wkb_geom:
                            continue

                        # Ensure WKB is bytes (sqlite3 returns memoryview sometimes)
                        if isinstance(wkb_geom, memoryview):
                            wkb_geom = bytes(wkb_geom)

                        geom = QgsGeometry()
                        geom.fromWkb(wkb_geom)

                        if geom.isNull() or geom.type() != QgsWkbTypes.LineGeometry:
                            continue

                        if QgsWkbTypes.isSingleType(geom.wkbType()):
                            polyline = geom.asPolyline()
                            if len(polyline) > 2:
                                for pt in polyline[1:-1]:
                                    swmm_inp_file.write(line.format(conduit_name, pt.x(), pt.y()))

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 050624.0633: error while exporting [VERTICES] to .INP file!", e)
                    return

                # FUTURE GROUPS ##################################################
                future_groups = [
                    "FILES",
                    "RAINGAGES",
                    "HYDROGRAPHS",
                    "PROFILES",
                    "EVAPORATION",
                    "TEMPERATURE",
                    "SUBCATCHMENTS",
                    "SUBAREAS",
                    "INFILTRATION",
                    "AQUIFERS",
                    "GROUNDWATER",
                    "SNOWPACKS",
                    "DIVIDERS",
                    "OUTLETS",
                    "TRANSECTS",
                    "POLLUTANTS",
                    "LANDUSES",
                    "COVERAGES",
                    "BUILDUP",
                    "WASHOFF",
                    "TREATMENT",
                    "DWF",
                    "RDII",
                    "LOADINGS",
                    "TAGS",
                    "MAP",
                ]

                for group in future_groups:
                    items = self.select_this_INP_group(INP_groups, group.lower())
                    if items is not None:
                        swmm_inp_file.write("\n\n[" + group + "]")
                        for line in items[1:]:
                            if line != "":
                                swmm_inp_file.write("\n" + line)

                file = outdir + "/SWMM.INI"
                with open(file, "w") as ini_file:
                    ini_file.write("[SWMM5]")
                    ini_file.write("\nVersion=50022")
                    ini_file.write("\n[Results]")
                    ini_file.write("\nSaved=1")
                    ini_file.write("\nCurrent=1")

            if any((has_junctions, has_outfalls, has_storage, has_conduits, has_pumps, has_orifices, has_weirs)):
                self.gutils.set_cont_par("SWMM", 1)
            else:
                ini_file = outdir + "/SWMM.INI"
                swmm_file = outdir + "/SWMM.INP"
                if os.path.isfile(ini_file):
                    os.remove(ini_file)
                if os.path.isfile(swmm_file):
                    os.remove(swmm_file)
                self.gutils.set_cont_par("SWMM", 0)

            QApplication.setOverrideCursor(Qt.ArrowCursor)

            self.uc.log_info(
                swmm_file
                + "\n"
                + str(len(junctions_rows))
                + "\t[JUNCTIONS]\n"
                + str(len(outfalls_rows))
                + "\t[OUTFALLS]\n"
                + str(len(storages_rows))
                + "\t[STORAGE]\n"
                + str(len(conduits_rows))
                + "\t[CONDUITS]\n"
                + str(len(pumps_rows))
                + "\t[PUMPS]\n"
                + str(len(pump_curves_rows))
                + "\t[CURVES]\n"
                + str(len(orifices_rows))
                + "\t[ORIFICES]\n"
                + str(len(weirs_rows))
                + "\t[WEIRS]\n"
                + str(len(xsections_rows_1) + len(xsections_rows_2) + len(xsections_rows_3))
                + "\t[XSECTIONS]\n"
                + str(len(losses_rows))
                + "\t[LOSSES]\n"
                + str(len(coordinates_rows))
                + "\t[COORDINATES]\n"
                + str(len(inflows_rows))
                + "\t[INFLOWS]\n"
                + str(len(time_series_rows))
                + "\t[TIMESERIES]\n"
                + str(int(len(pattern_rows) / 24))
                + "\t[PATTERNS]"
            )

            warn = ""
            if no_in_out_conduits != 0:
                warn += (
                        "* "
                        + str(no_in_out_conduits)
                        + " conduits have no inlet and/or outlet!\nThe value '?' was written in [CONDUITS] group.\n\n"
                )

            if no_in_out_pumps != 0:
                warn += (
                        "* "
                        + str(no_in_out_pumps)
                        + " pumps have no inlet and/or outlet!\nThe value '?' was written in [PUMPS] group.\n\n"
                )

            if no_in_out_orifices != 0:
                warn += (
                        "* "
                        + str(no_in_out_orifices)
                        + " orifices have no inlet and/or outlet!\nThe value '?' was written in [ORIFICES] group.\n\n"
                )

            if no_in_out_weirs != 0:
                warn += (
                        "* "
                        + str(no_in_out_weirs)
                        + " weirs have no inlet and/or outlet!\nThe value '?' was written in [WEIRS] group.\n\n"
                )

            if non_sync_dates > 0:
                warn += (
                        "* "
                        + str(non_sync_dates)
                        + " time series dates are outside the start and end times of the simulation!\nSee [TIMESERIES] group.\n\n"
                )

            if warn != "":
                self.uc.show_warn(
                    "WARNING 090422.0554: SWMM.INP file:\n\n"
                    + warn
                    + "Please review these issues because they will cause errors during their processing."
                )

            QApplication.restoreOverrideCursor()

        except Exception as e:
            self.uc.show_error("ERROR 160618.0634: couldn't export .INP file!", e)

    def export_swmmflo_hdf5(self, subdomain):
        """
        Function to export the swmm flo to the hdf5 file
        """
        try:
            if self.is_table_empty("swmmflo"):
                return False

            if not subdomain:
                swmmflo_sql = """SELECT fid, swmmchar, swmm_jt, swmm_iden, intype, swmm_length, swmm_width, 
                                        swmm_height, swmm_coeff, swmm_feature, curbheight
                                 FROM swmmflo ORDER BY swmm_iden;"""
            else:
                swmmflo_sql = f"""
                                SELECT 
                                    sf.fid,
                                    sf.swmmchar, 
                                    md.domain_cell, 
                                    sf.swmm_iden, 
                                    sf.intype, 
                                    sf.swmm_length, 
                                    sf.swmm_width, 
                                    sf.swmm_height, 
                                    sf.swmm_coeff, 
                                    sf.swmm_feature, 
                                    sf.curbheight
                                FROM 
                                    swmmflo AS sf
                                JOIN
                                    schema_md_cells md ON sf.swmm_jt = md.grid_fid
                                 WHERE 
                                    md.domain_fid = {subdomain}
                                ORDER BY sf.swmm_iden;
                                """

            swmmflo_rows = self.execute(swmmflo_sql).fetchall()
            if not swmmflo_rows:
                return False
            else:
                pass

            stormdrain_group = self.parser.stormdrain_group
            stormdrain_group.create_dataset('SWMMFLO_DATA', [])
            stormdrain_group.create_dataset('SWMMFLO_NAME', [])

            swmmflo_name = "{}  {}\n"
            for row in swmmflo_rows:
                (
                    fid,
                    swmmchar,
                    swmm_jt,
                    swmm_iden,
                    intype,
                    swmm_length,
                    swmm_width,
                    swmm_height,
                    swmm_coeff,
                    swmm_feature,
                    curbheight
                ) = row

                # if intype != 0:
                stormdrain_group.datasets["SWMMFLO_NAME"].data.append(
                    create_array(swmmflo_name, 2, np.bytes_, tuple([fid, swmm_iden])))

                stormdrain_group.datasets["SWMMFLO_DATA"].data.append([
                    fid,
                    swmm_jt,
                    intype,
                    swmm_length,
                    swmm_width,
                    swmm_height,
                    swmm_coeff,
                    swmm_feature,
                    curbheight
                ])

            self.parser.write_groups(stormdrain_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1618: exporting SWMMFLO to hdf5 file failed!.\n", e)
            return False

    def export_swmmflo_dat(self, outdir, subdomain):
        # check if there is any SWMM data defined.
        try:
            if self.is_table_empty("swmmflo"):
                return False

            if not subdomain:
                swmmflo_sql = """SELECT swmmchar, swmm_jt, swmm_iden, intype, swmm_length, swmm_width, 
                                        swmm_height, swmm_coeff, swmm_feature, curbheight
                                 FROM swmmflo ORDER BY swmm_iden;"""
            else:
                swmmflo_sql = f"""
                                SELECT 
                                    sf.swmmchar, 
                                    md.domain_cell, 
                                    sf.swmm_iden, 
                                    sf.intype, 
                                    sf.swmm_length, 
                                    sf.swmm_width, 
                                    sf.swmm_height, 
                                    sf.swmm_coeff, 
                                    sf.swmm_feature, 
                                    sf.curbheight
                                FROM 
                                    swmmflo AS sf
                                JOIN
                                    schema_md_cells md ON sf.swmm_jt = md.grid_fid
                                 WHERE 
                                    md.domain_fid = {subdomain}
                                ORDER BY sf.swmm_iden;
                                """

            line1 = "{0}  {1} {2} {3} {4} {5} {6} {7} {8} {9}\n"

            swmmflo_rows = self.execute(swmmflo_sql).fetchall()
            if not swmmflo_rows:
                return False
            else:
                pass
            swmmflo = os.path.join(outdir, "SWMMFLO.DAT")
            with open(swmmflo, "w") as s:
                for row in swmmflo_rows:
                    new_row = []
                    if row[2][0] in ["I", "i"]:  # First letter of name (swmm_iden) is
                        # "I" or "i" for inlet,
                        # "IM" or "im" for manhole
                        # "j" or "J" for junctions
                        # "O" or "o" for outfalls.
                        for i, item in enumerate(row, 1):
                            new_row.append(item if item is not None else 0)
                        if new_row[1] < 1:
                            self.uc.bar_warn(
                                "WARNING: invalid grid number in 'swmmflo' (Storm Drain. SD Inlets) layer !")
                        else:
                            s.write(line1.format(*new_row))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1618: exporting SWMMFLO.DAT failed!.\n", e)
            return False

    def export_swmmflodropbox_hdf5(self, subdomain):
        """
        Function to export the SWMMFLODROPBOX to hdf5 file
        """

        if self.is_table_empty("user_swmm_inlets_junctions"):
            return False

        if not subdomain:
            qry = """        
                    SELECT 
                        swmmflo.fid as FID, 
                        user_swmm_inlets_junctions.drboxarea 
                    FROM 
                        swmmflo JOIN user_swmm_inlets_junctions ON swmmflo.swmm_jt = user_swmm_inlets_junctions.grid
                    WHERE (sd_type = 'I' OR sd_type = 'J') AND drboxarea > 0.0 GROUP BY user_swmm_inlets_junctions.grid;
                    """
        else:
            qry = f"""                    
                    SELECT 
                        swmmflo.fid as FID, 
                        user_swmm_inlets_junctions.drboxarea 
                    FROM 
                        swmmflo
                        JOIN user_swmm_inlets_junctions ON swmmflo.swmm_jt = user_swmm_inlets_junctions.grid
                        JOIN schema_md_cells md ON swmmflo.swmm_jt = md.grid_fid
                    WHERE 
                        (sd_type = 'I' OR sd_type = 'J') 
                        AND drboxarea > 0.0 
                        AND md.domain_fid = {subdomain}
                    GROUP BY 
                        md.domain_cell;
                    """

        rows = self.gutils.execute(qry).fetchall()

        if rows:

            stormdrain_group = self.parser.stormdrain_group
            stormdrain_group.create_dataset('SWMMFLODROPBOX', [])

            for row in rows:
                (fid,
                 drboxarea) = row
                stormdrain_group.datasets["SWMMFLODROPBOX"].data.append([fid, drboxarea])

            self.parser.write_groups(stormdrain_group)
            return True

    def export_swmmflodropbox_dat(self, outdir, subdomain):
        try:
            if self.is_table_empty("user_swmm_inlets_junctions"):
                return False

            if not subdomain:
                qry = """SELECT name, grid, drboxarea  FROM user_swmm_inlets_junctions WHERE SUBSTR(name, 1,1) NOT LIKE 'J%'  AND drboxarea > 0.0;"""
            else:
                qry = f"""SELECT 
                            usij.name, 
                            md.domain_cell, 
                            usij.drboxarea 
                        FROM 
                            user_swmm_inlets_junctions AS usij
                         JOIN
                            schema_md_cells md ON usij.grid = md.grid_fid
                        WHERE 
                            md.domain_fid = {subdomain} AND SUBSTR(usij.name, 1,1) NOT LIKE 'J%'  AND usij.drboxarea > 0.0;"""

            rows = self.gutils.execute(qry).fetchall()
            if rows:
                line1 = "{0:16} {1:<10} {2:<10.2f}\n"

                swmmflodropbox = os.path.join(outdir, "SWMMFLODROPBOX.DAT")
                with open(swmmflodropbox, "w") as s:
                    for row in rows:
                        s.write(line1.format(*row))
                return True
            else:
                # There are no drop box areas defined, delete SWMMFLODROPBOX.DAT if exists:
                if os.path.isfile(outdir + r"\SWMMFLODROPBOX.DAT"):
                    os.remove(outdir + r"\SWMMFLODROPBOX.DAT")
                return False

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 120424.0449: exporting SWMMFLODROPBOX.DAT failed!.\n", e)
            return False

    def export_sdclogging_hdf5(self, subdomain):
        """
        Function to export the sdclogging to a hdf5 file
        """
        if self.is_table_empty("user_swmm_inlets_junctions"):
            return False

        if not subdomain:
            qry = """SELECT 
                        swmmflo.fid as FID, 
                        user_swmm_inlets_junctions.swmm_clogging_factor, 
                        user_swmm_inlets_junctions.swmm_time_for_clogging 
                    FROM 
                        swmmflo 
                    JOIN 
                        user_swmm_inlets_junctions ON swmmflo.swmm_jt = user_swmm_inlets_junctions.grid 
                    WHERE 
                        (user_swmm_inlets_junctions.sd_type = 'I' OR user_swmm_inlets_junctions.sd_type = 'J') 
                        AND user_swmm_inlets_junctions.swmm_clogging_factor > 0.0 
                        AND user_swmm_inlets_junctions.swmm_time_for_clogging > 0.0 
                    GROUP BY
                        user_swmm_inlets_junctions.grid;
                    """
        else:
            qry = f"""
                    SELECT 
                        swmmflo.fid AS FID, 
                        user_swmm_inlets_junctions.swmm_clogging_factor, 
                        user_swmm_inlets_junctions.swmm_time_for_clogging 
                    FROM 
                        swmmflo
                        JOIN user_swmm_inlets_junctions ON swmmflo.swmm_jt = user_swmm_inlets_junctions.grid
                        JOIN schema_md_cells md ON swmmflo.swmm_jt = md.grid_fid
                    WHERE 
                        (user_swmm_inlets_junctions.sd_type = 'I' OR user_swmm_inlets_junctions.sd_type = 'J')
                        AND user_swmm_inlets_junctions.swmm_clogging_factor > 0.0
                        AND user_swmm_inlets_junctions.swmm_time_for_clogging > 0.0
                        AND md.domain_fid = {subdomain}
                    GROUP BY
                        user_swmm_inlets_junctions.grid;"""

        rows = self.gutils.execute(qry).fetchall()
        if rows:
            stormdrain_group = self.parser.stormdrain_group
            stormdrain_group.create_dataset('SDCLOGGING', [])

            for row in rows:
                (fid,
                 swmm_clogfac,
                 clogtime) = row
                stormdrain_group.datasets["SDCLOGGING"].data.append([fid, swmm_clogfac, clogtime])

            self.parser.write_groups(stormdrain_group)
            return True

    def export_sdclogging_dat(self, outdir, subdomain):
        try:
            if self.is_table_empty("user_swmm_inlets_junctions"):
                return False

            if not subdomain:
                qry = """SELECT grid, name, swmm_clogging_factor, swmm_time_for_clogging
                         FROM user_swmm_inlets_junctions 
                         WHERE (sd_type = 'I' OR sd_type = 'J') AND swmm_clogging_factor > 0.0 AND swmm_time_for_clogging > 0.0;"""
            else:
                qry = f"""
                        SELECT 
                            md.domain_cell, 
                            usij.name, 
                            usij.swmm_clogging_factor, 
                            usij.swmm_time_for_clogging
                        FROM 
                            user_swmm_inlets_junctions AS usij
                        JOIN
                            schema_md_cells md ON usij.grid = md.grid_fid
                        WHERE 
                            (usij.sd_type = 'I' OR usij.sd_type = 'J') 
                            AND usij.swmm_clogging_factor > 0.0 
                            AND usij.swmm_time_for_clogging > 0.0
                            AND md.domain_fid = {subdomain};
                        """

            rows = self.gutils.execute(qry).fetchall()
            if rows:
                line1 = "D {0:8}   {1:<16} {2:<10.2f} {3:<10.2f}\n"

                sdclogging = os.path.join(outdir, "SDCLOGGING.DAT")
                with open(sdclogging, "w") as s:
                    for row in rows:
                        s.write(line1.format(*row))
                return True
            else:
                # There are no cloggings defined, delete SDCLOGGING.DAT if exists:
                if os.path.isfile(outdir + r"\SDCLOGGING.DAT"):
                    os.remove(outdir + r"\SDCLOGGING.DAT")
                return False

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 140424.1828: exporting SDCLOGGING.DAT failed!.\n", e)
            return False

    def export_swmmflort(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_swmmflort_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_swmmflort_hdf5(subdomain)

    def export_swmmflort_hdf5(self, subdomain):
        """
        Function to export swmmflort to the hdf5 file.
        """
        if self.is_table_empty("swmmflort") and self.is_table_empty("swmmflo_culvert"):
            return False

        if not subdomain:
            swmmflort_sql = """
                            SELECT swmmflo.fid as FID, depth, q
                            FROM swmmflort_data
                            JOIN swmmflort ON swmmflort_data.swmm_rt_fid = swmmflort.fid
                            JOIN swmmflo ON swmmflort.grid_fid = swmmflo.swmm_jt;
                            """
            culverts_sql = """
                            SELECT swmmflo.fid as FID, cdiameter, typec, typeen, cubase, multbarrels
                            FROM swmmflo_culvert
                            JOIN swmmflo ON swmmflo_culvert.grid_fid = swmmflo.swmm_jt;
                            """
        else:
            swmmflort_sql = f"""
                            SELECT swmmflo.fid as FID, depth, q
                            FROM swmmflort_data
                            JOIN swmmflort ON swmmflort_data.swmm_rt_fid = swmmflort.fid
                            JOIN swmmflo ON swmmflort.grid_fid = swmmflo.swmm_jt
                            JOIN
                            schema_md_cells md ON swmmflort.grid_fid = md.grid_fid
                            WHERE 
                            md.domain_fid = {subdomain};
                            """
            culverts_sql = f"""
                            SELECT swmmflo.fid as FID, cdiameter, typec, typeen, cubase, multbarrels
                            FROM swmmflo_culvert
                            JOIN swmmflo ON swmmflo_culvert.grid_fid = swmmflo.swmm_jt
                            JOIN
                            schema_md_cells md ON swmmflo_culvert.grid_fid = md.grid_fid
                            WHERE 
                            md.domain_fid = {subdomain}
                            """

        swmmflort_rows = self.execute(swmmflort_sql).fetchall()

        if not swmmflort_rows and self.is_table_empty("swmmflo_culvert"):
            return False
        else:
            pass

        stormdrain_group = self.parser.stormdrain_group

        for fid, depth, q in swmmflort_rows:
            try:
                stormdrain_group.datasets["RATING_TABLE"].data.append([fid, depth, q])
            except:
                stormdrain_group.create_dataset('RATING_TABLE', [])
                stormdrain_group.datasets["RATING_TABLE"].data.append([fid, depth, q])

        culverts_rows = self.execute(culverts_sql).fetchall()

        for fid, cdiameter, typec, typeen, cubase, multbarrels in culverts_rows:
            try:
                stormdrain_group.datasets["CULVERT_EQUATIONS"].data.append(
                    [fid, cdiameter, typec, typeen, cubase, multbarrels])
            except:
                stormdrain_group.create_dataset('CULVERT_EQUATIONS', [])
                stormdrain_group.datasets["CULVERT_EQUATIONS"].data.append(
                    [fid, cdiameter, typec, typeen, cubase, multbarrels])

        self.parser.write_groups(stormdrain_group)
        return True

    def export_swmmflort_dat(self, outdir, subdomain):
        # check if there is any SWMM rating data defined.
        try:
            if self.is_table_empty("swmmflort") and self.is_table_empty("swmmflo_culvert"):
                if os.path.isfile(outdir + r"\SWMMFLORT.DAT"):
                    m = "* There are no SWMM Rating Tables or Culvert Equations defined in the project, but there is\n"
                    m += "an old SWMMFLORT.DAT in the project directory\n\n  " + outdir + "\n\n"
                    self.export_messages += m
                    return False

            if not subdomain:
                swmmflort_sql = """SELECT fid, grid_fid, name FROM swmmflort ORDER BY grid_fid;"""
                inlet_type_qry = "SELECT intype FROM swmmflo WHERE swmm_jt = ?;"
                inlet_type_qry2 = "SELECT intype FROM swmmflo WHERE swmm_jt = ? AND intype = '4';"
                inlet_name_qry = "SELECT swmm_iden FROM swmmflo WHERE swmm_jt = ?;"
                culvert_qry = "SELECT grid_fid, name, cdiameter, typec, typeen, cubase, multbarrels FROM swmmflo_culvert ORDER BY fid;"
            else:
                swmmflort_sql = f"""
                SELECT 
                    sf.fid, 
                    md.domain_cell, 
                    sf.name 
                FROM 
                    swmmflort AS sf
                JOIN
                    schema_md_cells md ON sf.grid_fid = md.grid_fid
                WHERE 
                    md.domain_fid = {subdomain}
                ORDER BY md.domain_cell;"""

                inlet_type_qry = f"""
                SELECT 
                    sf.intype 
                FROM 
                    swmmflo AS sf
                JOIN
                    schema_md_cells md ON sf.swmm_jt = md.grid_fid
                WHERE 
                    md.domain_cell = ? AND md.domain_fid = {subdomain};"""

                inlet_type_qry2 = f"""
                SELECT 
                    sf.intype 
                FROM 
                    swmmflo AS sf
                JOIN
                    schema_md_cells md ON sf.swmm_jt = md.grid_fid
                WHERE 
                    md.domain_cell = ? AND sf.intype = '4' AND md.domain_fid = {subdomain};"""

                inlet_name_qry = f"""
                SELECT 
                    sij.swmm_iden 
                FROM 
                    swmmflo AS sij
                JOIN
                    schema_md_cells md ON sij.swmm_jt = md.grid_fid
                WHERE md.domain_cell = ? AND md.domain_fid = {subdomain};"""

                culvert_qry = f"""
                SELECT 
                    md.domain_cell,
                    su.name, 
                    su.cdiameter, 
                    su.typec, 
                    su.typeen, 
                    su.cubase, 
                    su.multbarrels 
                FROM 
                    swmmflo_culvert AS su
                JOIN
                    schema_md_cells md ON su.grid_fid = md.grid_fid
                WHERE 
                    md.domain_fid = {subdomain}
                ORDER BY su.fid;"""

            data_sql = "SELECT depth, q FROM swmmflort_data WHERE swmm_rt_fid = ? ORDER BY depth;"

            line1 = "D {0}  {1}\n"
            line2 = "N {0}  {1}\n"
            errors = ""
            swmmflort_rows = self.execute(swmmflort_sql).fetchall()
            culverts = self.gutils.execute(culvert_qry).fetchall()
            if len(swmmflort_rows) == 0 and len(culverts) == 0:
                return False
            if not swmmflort_rows and self.is_table_empty("swmmflo_culvert"):
                return False
            else:
                pass
            swmmflort = os.path.join(outdir, "SWMMFLORT.DAT")
            error_mentioned = False
            with (open(swmmflort, "w") as s):
                for fid, gid, rtname in swmmflort_rows:
                    rtname = rtname.strip()
                    if gid is not None:
                        if str(gid).strip() != "":
                            if rtname is None or rtname == "":
                                errors += "* Grid element " + str(gid) + " has an empty rating table name.\n"
                            else:
                                inlet_type = self.execute(inlet_type_qry, (gid,)).fetchall()
                                if inlet_type is not None and len(inlet_type) != 0:
                                    # TODO: there may be more than one record. Why? Some may have intype = 4.
                                    if len(inlet_type) > 1:
                                        errors += "* Grid element " + str(gid) + " has has more than one inlet.\n"
                                    # See if there is a type 4:
                                    inlet_type = self.execute(inlet_type_qry2, (gid,)).fetchone()
                                    if inlet_type is not None:
                                        rows = self.execute(data_sql, (fid,)).fetchone()
                                        if not rows:
                                            inlet_name = self.execute(
                                                inlet_name_qry,
                                                (gid,),
                                            ).fetchone()
                                            if inlet_name != None:
                                                if inlet_name[0] == "":
                                                    errors += (
                                                            "* No data found for a rating table named '"
                                                            + rtname
                                                            + "' for grid element "
                                                            + str(gid)
                                                            + ".\n"
                                                    )
                                                else:
                                                    errors += (
                                                            "* No data found for a rating table named '"
                                                            + rtname
                                                            + "' for inlet '"
                                                            + inlet_name[0]
                                                            + "' for grid element "
                                                            + str(gid)
                                                            + ".\n"
                                                    )
                                        else:
                                            inlet_name = self.execute(inlet_name_qry, (gid,)).fetchone()
                                            if inlet_name not in [None, ""]:
                                                s.write(line1.format(gid, inlet_name[0]))
                                                table = self.execute(data_sql, (fid,)).fetchall()
                                                if table:
                                                    for row in table:
                                                        s.write(line2.format(*row))
                                                else:
                                                    errors += (
                                                            "* Could not find data for rating table '"
                                                            + rtname
                                                            + "' for grid element "
                                                            + str(gid)
                                                            + ".\n"
                                                    )
                                            else:
                                                if not error_mentioned:
                                                    errors += (
                                                            "* Rating table " + rtname + " doesn't have an inlet associated with node " + str(
                                                        gid) + ".\n"
                                                    )
                                                    error_mentioned = True
                    else:
                        errors += "* Unknown grid element for Rating Table " + rtname + ".\n"
                if culverts:
                    for culv in culverts:
                        (
                            grid_fid,
                            name,
                            cdiameter,
                            typec,
                            typeen,
                            cubase,
                            multbarrels,
                        ) = culv
                        if grid_fid:
                            s.write("S " + str(grid_fid) + " " + name + " " + str(cdiameter) + "\n")
                            s.write(
                                "F " + str(typec) + " " + str(typeen) + " " + str(cubase) + " " + str(
                                    multbarrels) + "\n"
                            )
                        else:
                            if name:
                                errors += "* Unknown grid element for Culverts eq. " + name + ".\n"
                            else:
                                errors += "* Unknown grid element in Culverts eq. table.\n"
            if errors:
                self.uc.show_info("WARNING 040319.0521:\n\n" + errors)
            return True

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            self.uc.show_error("ERROR 101218.1619: exporting SWMMFLORT.DAT failed!.\n", e)
            QApplication.restoreOverrideCursor()
            return False

    def export_swmmoutf(self, output=None, subdomain=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_swmmoutf_dat(output, subdomain)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_swmmoutf_hdf5(subdomain)

    def export_swmmoutf_hdf5(self, subdomain):
        """
        Function to export the swmmoutf to hdf5 file
        """
        try:
            if self.is_table_empty("swmmoutf"):
                return False

            if not subdomain:
                swmmoutf_sql = """SELECT fid, name, grid_fid, outf_flo FROM swmmoutf ORDER BY name;"""
            else:
                swmmoutf_sql = f"""
                SELECT 
                    sf.fid,
                    sf.name, 
                    md.domain_cell, 
                    sf.outf_flo 
                FROM
                    swmmoutf AS sf
                JOIN
                    schema_md_cells md ON sf.grid_fid = md.grid_fid
                WHERE 
                    md.domain_fid = {subdomain}    
                ORDER BY sf.name;"""

            swmmoutf_rows = self.execute(swmmoutf_sql).fetchall()
            if not swmmoutf_rows:
                return False
            else:
                pass

            stormdrain_group = self.parser.stormdrain_group
            stormdrain_group.create_dataset('SWMMOUTF_DATA', [])
            stormdrain_group.create_dataset('SWMMOUTF_NAME', [])

            swmmoutf_name = "{}  {}\n"

            for row in swmmoutf_rows:
                (
                    fid,
                    name,
                    grid_fid,
                    outf_flo
                ) = row

                if grid_fid is None or grid_fid == "":
                    grid_fid = -9999  # Use -9999 for missing grid_fid

                stormdrain_group.datasets["SWMMOUTF_DATA"].data.append([fid, grid_fid, outf_flo])
                stormdrain_group.datasets["SWMMOUTF_NAME"].data.append(
                    create_array(swmmoutf_name, 2, np.bytes_, tuple([fid, name])))

            self.parser.write_groups(stormdrain_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1620: exporting SWMMOUTF.DAT failed!.\n", e)
            return False

    def export_swmmoutf_dat(self, outdir, subdomain):
        # check if there is any SWMM data defined.
        try:
            if self.is_table_empty("swmmoutf"):
                return False

            if not subdomain:
                swmmoutf_sql = """SELECT name, grid_fid, outf_flo FROM swmmoutf ORDER BY name;"""
            else:
                swmmoutf_sql = f"""
                SELECT 
                    sf.name, 
                    md.domain_cell, 
                    sf.outf_flo 
                FROM
                    swmmoutf AS sf
                JOIN
                    schema_md_cells md ON sf.grid_fid = md.grid_fid
                WHERE 
                    md.domain_fid = {subdomain}    
                ORDER BY sf.name;"""

            line1 = "{0}  {1}  {2}\n"

            swmmoutf_rows = self.execute(swmmoutf_sql).fetchall()
            if not swmmoutf_rows:
                return False
            else:
                pass
            swmmoutf = os.path.join(outdir, "SWMMOUTF.DAT")
            with open(swmmoutf, "w") as s:
                for row in swmmoutf_rows:
                    name, grid_fid, outf_flo = row
                    if not grid_fid:
                        grid_fid = -9999
                    if isinstance(outf_flo, str):
                        if outf_flo.lower() == 'true':
                            outf_flo = 1
                        elif outf_flo.lower() == 'false':
                            outf_flo = 0
                        else:
                            outf_flo = int(outf_flo)
                    else:
                        outf_flo = int(outf_flo)
                    s.write(line1.format(name, grid_fid, outf_flo))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1620: exporting SWMMOUTF.DAT failed!.\n", e)
            return False

    def export_wsurf(self, outdir):
        # check if there is any water surface data defined.
        try:
            if self.is_table_empty("wsurf"):
                return False
            count_sql = """SELECT COUNT(fid) FROM wsurf;"""
            wsurf_sql = """SELECT grid_fid, wselev FROM wsurf ORDER BY fid;"""

            line1 = "{0}\n"
            line2 = "{0}  {1}\n"

            wsurf_rows = self.execute(wsurf_sql).fetchall()
            if not wsurf_rows:
                return False
            else:
                pass
            wsurf = os.path.join(outdir, "WSURF.DAT")
            with open(wsurf, "w") as w:
                count = self.execute(count_sql).fetchone()[0]
                w.write(line1.format(count))
                for row in wsurf_rows:
                    w.write(line2.format(*row))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1621: exporting WSURF.DAT failed!.\n", e)
            return False

    def export_wstime(self, outdir):
        # check if there is any water surface data defined.
        try:
            if self.is_table_empty("wstime"):
                return False
            count_sql = """SELECT COUNT(fid) FROM wstime;"""
            wstime_sql = """SELECT grid_fid, wselev, wstime FROM wstime ORDER BY fid;"""

            line1 = "{0}\n"
            line2 = "{0}  {1}  {2}\n"

            wstime_rows = self.execute(wstime_sql).fetchall()
            if not wstime_rows:
                return False
            else:
                pass
            wstime = os.path.join(outdir, "WSTIME.DAT")
            with open(wstime, "w") as w:
                count = self.execute(count_sql).fetchone()[0]
                w.write(line1.format(count))
                for row in wstime_rows:
                    w.write(line2.format(*row))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1622: exporting WSTIME.DAT failed!.\n", e)
            return False
