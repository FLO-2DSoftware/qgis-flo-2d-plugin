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
from itertools import chain, groupby
from math import isclose
from operator import itemgetter

import numpy as np
from qgis._core import QgsMessageLog
from qgis.core import NULL, QgsApplication
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QApplication, QProgressDialog

from ..flo2d_tools.grid_tools import grid_compas_neighbors
from ..geopackage_utils import GeoPackageUtils
from ..gui.bc_editor_widget import BCEditorWidget
from ..layers import Layers
from ..utils import BC_BORDER, float_or_zero, get_BC_Border
from .flo2d_parser import ParseDAT, ParseHDF5


def create_array(line_format, max_columns, *args):
    if len(args) == 1 and isinstance(args[0], tuple):
        values = line_format.format(*args[0]).split()
    else:
        values = line_format.format(*args).split()
    array = np.array(values[:max_columns] + [""] * (max_columns - len(values)), dtype=np.string_)
    return array


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
        elif self.parsed_format == self.FORMAT_HDF5:
            self.parser = ParseHDF5()
            self.parser.hdf5_filepath = fpath
        else:
            raise NotImplementedError("Unsupported extension type.")
        if not get_cell_size:
            return True
        self.cell_size = self.parser.calculate_cellsize()
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
        sql = ["""INSERT OR REPLACE INTO cont (name, value, note) VALUES""", 3]
        mann = self.get_cont_par("MANNING")
        control_group = self.parser.read_groups("Control")[0]
        mann_dataset = control_group.datasets["MANNING"]
        man_from_dataset = mann_dataset.data[0]
        if not mann and not man_from_dataset:
            mann = "0.05"
        else:
            pass
        self.clear_tables("cont")
        for option, dataset in control_group.datasets.items():
            option_value = dataset.data[0]
            sql += [(option, option_value.decode(), self.PARAMETER_DESCRIPTION[option])]
        sql += [("CELLSIZE", self.cell_size, self.PARAMETER_DESCRIPTION["CELLSIZE"])]
        sql += [("MANNING", mann, self.PARAMETER_DESCRIPTION["MANNING"])]
        self.batch_execute(sql)

    def import_mannings_n_topo(self):
        if self.parsed_format == self.FORMAT_DAT:
            return self.import_mannings_n_topo_dat()
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.import_mannings_n_topo_hdf5()

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
            grid_group = self.parser.read_groups("Grid")[0]

            c = 0
            grid_code_list = grid_group.datasets["GRIDCODE"].data
            manning_list = grid_group.datasets["MANNING"].data
            elevation_list = grid_group.datasets["Z"].data
            x_list = grid_group.datasets["X"].data
            y_list = grid_group.datasets["Y"].data
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

        errors = ""

        try:  # See if n_value exists in table:
            self.execute("SELECT n_value FROM reservoirs")
            # Yes, n_value exists.
            try:  # See if tailings exists in table:
                self.execute("SELECT tailings FROM reservoirs")
                # Yes, tailings exists
                schematic_reservoirs_sql = [
                    """INSERT INTO reservoirs (grid_fid, wsel, n_value, use_n_value, tailings, geom) VALUES""",
                    6,
                ]
                user_reservoirs_sql = [
                    """INSERT INTO user_reservoirs (wsel, n_value, use_n_value, tailings, geom) VALUES""",
                    5,
                ]

                with_n_values = True
                with_tailings = True
            except:
                # tailings doesn't exist.
                schematic_reservoirs_sql = [
                    """INSERT INTO reservoirs (grid_fid, wsel, n_value, use_n_value, geom) VALUES""",
                    5,
                ]
                user_reservoirs_sql = [
                    """INSERT INTO user_reservoirs (wsel, n_value, use_n_value, geom) VALUES""",
                    4,
                ]
                with_n_values = True
                with_tailings = False
        except:
            # n_value doesn't exist.
            schematic_reservoirs_sql = [
                """INSERT INTO reservoirs (grid_fid, wsel, geom) VALUES""",
                3,
            ]
            user_reservoirs_sql = [
                """INSERT INTO user_reservoirs (wsel, geom) VALUES""",
                2,
            ]
            with_n_values = False
            with_tailingss = False

        try:
            self.clear_tables(
                "inflow",
                "inflow_cells",
                "reservoirs",
                "user_reservoirs",
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
                value = ()
                row = res[gid]["row"]
                grid = row[1]
                wsel = row[2]
                square = self.build_square(cells[gid], self.shrink)
                centroid = self.single_centroid(gid, buffers=True)
                if with_n_values and with_tailings:
                    if len(row) == 3:
                        # R  grid  wsel:
                        value = (wsel, "0.25", False, "-1.0")
                    elif len(row) == 4:
                        # R  grid  wsel  n_value_or_tailing:
                        if float_or_zero(row[3]) > 1.0:
                            # 3rd. value is a tailing depth:
                            value = (wsel, "0.25", False, row[3])
                        else:
                            # 3rd. value is n_value:
                            value = (wsel, row[3], True, "-1.0")

                    elif len(row) == 5:
                        # R  grid  wsel  tailing  n_value:
                        value = (wsel, row[4], True, row[3])
                    else:
                        errors += "R line with more than 5 values"

                elif with_n_values and not with_tailings:
                    if len(row) == 3:
                        # R  grid  wsel:
                        value = (wsel, "0.25", False)
                    elif len(row) == 4:
                        # R  grid  wsel  n_value:
                        value = (wsel, row[3], True)
                    else:
                        errors += "Inflow table without tailings. R line with more than 4 values"

                elif not with_n_values and not with_tailings:
                    if len(row) == 3:
                        # R  grid  wsel:
                        value = wsel
                    else:
                        errors += "Inflow table without n_values and tailings. R line with more than 3 values"

                if value:
                    user_reservoirs_sql += [(*value, centroid)]
                    value2 = (grid, *value, square)
                    schematic_reservoirs_sql += [value2]

            self.batch_execute(user_reservoirs_sql)
            self.batch_execute(schematic_reservoirs_sql)

            qry = """UPDATE user_reservoirs SET name = 'Reservoir ' ||  cast(fid as text);"""
            self.execute(qry)
            qry = """UPDATE reservoirs SET user_res_fid = fid, name = 'Reservoir ' ||  cast(fid as text);"""
            self.execute(qry)

        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error("ERROR 070719.1051: Import inflows failed!.", e)

    def import_tailings(self):
        tailingsf_sql = [
            """INSERT INTO tailing_cells (grid_fid, thickness) VALUES""",
            2,
        ]
        self.clear_tables("tailing_cells")
        data = self.parser.parse_tailings()
        for row in data:
            grid_fid, thinkness = row
            tailingsf_sql += [(grid_fid, thinkness)]
        self.batch_execute(tailingsf_sql)

    def import_outflow(self):
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

    def import_rain(self):
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

    def import_raincell(self):
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
        data_gen = (data[i : i + grid_count] for i in range(0, data_len, grid_count))
        time_interval = 0
        for data_series in data_gen:
            for row in data_series:
                data_sql += [(time_interval,) + tuple(row)]
            time_interval += time_step
        self.batch_execute(head_sql, data_sql)

    def import_infil(self):
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
        ]
        infil_sql = ["INSERT INTO infil (" + ", ".join(infil_params) + ") VALUES", 16]
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
        # s = QSettings()
        # last_dir = s.value("FLO-2D/lastGdsDir", "")
        # if not os.path.isfile(last_dir + r"\CHAN.DAT"):
        #     self.uc.show_warn("WARNING 060319.1612: Can't import channels!.\n\nCHAN.DAT doesn't exist.")
        #     return
        # if not os.path.isfile(last_dir + r"\CHANBANK.DAT"):
        #     self.uc.show_warn("WARNING 060319.1632: Can't import channels!.\n\nCHANBANK.DAT doesn't exist.")
        #     return

        chan_sql = [
            """INSERT INTO chan (geom, depinitial, froudc, roughadj, isedn) VALUES""",
            5,
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
                chan_sql += [(geom,) + tuple(options)]

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

        except Exception:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn(
                "WARNING 010219.0742: Import channels failed!. Check CHAN.DAT and CHANBANK.DAT files."
            )  # self.uc.show_warn('Import channels failed!.\nMaybe the number of left bank and right bank cells are different.')

    def import_xsec(self):
        xsec_sql = ["""INSERT INTO xsec_n_data (chan_n_nxsecnum, xi, yi) VALUES""", 3]
        self.clear_tables("xsec_n_data")
        data = self.parser.parse_xsec()
        for key in list(data.keys()):
            xsec_no, xsec_name = key
            nodes = data[key]
            for row in nodes:
                xsec_sql += [(xsec_no,) + tuple(row)]

        self.batch_execute(xsec_sql)

    #     def import_hystruc(self):
    #         try:
    #             hystruc_params = ['geom', 'type', 'structname', 'ifporchan', 'icurvtable', 'inflonod', 'outflonod', 'inoutcont',
    #                               'headrefel', 'clength', 'cdiameter']
    #             hystruc_sql = ['INSERT INTO struct (' + ', '.join(hystruc_params) + ') VALUES', 11]
    #             ratc_sql = ['''INSERT INTO rat_curves (struct_fid, hdepexc, coefq, expq, coefa, expa) VALUES''', 6]
    #             repl_ratc_sql = ['''INSERT INTO repl_rat_curves (struct_fid, repdep, rqcoef, rqexp, racoef, raexp) VALUES''', 6]
    #             ratt_sql = ['''INSERT INTO rat_table (struct_fid, hdepth, qtable, atable) VALUES''', 4]
    #             culvert_sql = ['''INSERT INTO culvert_equations (struct_fid, typec, typeen, culvertn, ke, cubase) VALUES''', 6]
    #             storm_sql = ['''INSERT INTO storm_drains (struct_fid, istormdout, stormdmax) VALUES''', 3]
    #
    #             sqls = {
    #                 'C': ratc_sql,
    #                 'R': repl_ratc_sql,
    #                 'T': ratt_sql,
    #                 'F': culvert_sql,
    #                 'D': storm_sql
    #             }
    #
    #             self.clear_tables('struct', 'rat_curves', 'repl_rat_curves', 'rat_table', 'culvert_equations', 'storm_drains')
    #             data = self.parser.parse_hystruct()
    #             nodes = slice(3, 5)
    #             for i, hs in enumerate(data, 1):
    #                 params = hs[:-1]   # Line 'S' (first line of next structure)
    #                 elems = hs[-1]     # Lines 'C', 'R', 'I', 'F', and/ or 'D' (rest of lines of next structure)
    #                 geom = self.build_linestring(params[nodes])
    #                 typ = list(elems.keys())[0] if len(elems) == 1 else 'C'
    #                 hystruc_sql += [(geom, typ) + tuple(params)]
    #                 for char in list(elems.keys()):
    #                     for row in elems[char]:
    #                         sqls[char] += [(i,) + tuple(row)]
    #
    #             self.batch_execute(hystruc_sql, ratc_sql, repl_ratc_sql, ratt_sql, culvert_sql, storm_sql)
    #             qry = '''UPDATE struct SET notes = 'imported';'''
    #             self.execute(qry)
    #         except Exception:
    #             QApplication.restoreOverrideCursor()
    #             self.uc.show_warn('ERROR 040220.0742: Importing hydraulic structures from HYSTRUC.DAT failed!')

    def import_hystruc(self):
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

        except Exception:
            QApplication.restoreOverrideCursor()
            self.uc.show_warn(
                "ERROR 040220.0742: Importing hydraulic structures failed!\nPlease check HYSTRUC.DAT data format and values."
            )

    def import_hystruc_bridge_xs(self):
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
            QApplication.setOverrideCursor(Qt.WaitCursor)

    def import_street(self):
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

    def import_arf(self):
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

    def import_mult(self):
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

    def import_sed(self):
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

    def import_levee(self):
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

    def import_fpxsec(self):
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

    def import_breach(self):
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

    def import_fpfroude(self):
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

    def import_gutter(self):
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

    def import_swmmflo(self):
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
            swmmflo_sql += [(geom,) + tuple(row)]

        self.batch_execute(swmmflo_sql)

    def import_swmmflort(self):
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

    def import_swmmoutf(self):
        swmmoutf_sql = [
            """INSERT INTO swmmoutf (geom, name, grid_fid, outf_flo) VALUES""",
            4,
        ]

        self.clear_tables("swmmoutf")
        data = self.parser.parse_swmmoutf()
        gids = (x[1] for x in data)
        cells = self.grid_centroids(gids, buffers=True)
        for row in data:
            gid = row[1]
            geom = cells[gid]
            swmmoutf_sql += [(geom,) + tuple(row)]

        self.batch_execute(swmmoutf_sql)

    def import_tolspatial(self):
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

    def export_cont_toler(self, output=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_cont_toler_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_cont_toler_hdf5()

    def export_cont_toler_hdf5(self):
        # try:
        sql = """SELECT name, value FROM cont;"""
        cont_group = self.parser.control_group
        for option_name, option_value in self.execute(sql).fetchall():
            dataset_data = np.string_([option_value]) if option_value is not None else np.string_([""])
            cont_group.create_dataset(option_name, dataset_data)
        self.parser.write_groups(cont_group)
        return True
        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error("ERROR 101218.1535: exporting Control data failed!.\n", e)
        #     return False

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
            if options["MSTREET"] == "0":
                del options["COURANTST"]

            first_gid = self.execute("""SELECT grid_fid FROM inflow_cells ORDER BY fid LIMIT 1;""").fetchone()
            first_gid = first_gid[0] if first_gid is not None else 0

            if options["LGPLOT"] == "0":
                options["IDEPLT"] = "0"
                self.set_cont_par("IDEPLT", 0)
            elif first_gid > 0:
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
                                _itimtep = ("11", "21", "31", "41", "51")[int(options["ITIMTEP"]) - 1]
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

    def export_mannings_n_topo(self, output=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_mannings_n_topo_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_mannings_n_topo_hdf5()

    def export_mannings_n_topo_hdf5(self):
        try:
            sql = (
                """SELECT fid, n_value, elevation, ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM grid ORDER BY fid;"""
            )
            records = self.execute(sql)
            nulls = 0
            grid_group = self.parser.grid_group
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
                grid_group.datasets["Z"].data.append(elev)
                grid_group.datasets["X"].data.append(x)
                grid_group.datasets["Y"].data.append(y)
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
                QApplication.setOverrideCursor(Qt.WaitCursor)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1541: exporting Grid data failed!.\n", e)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            return False

    def export_mannings_n_topo_dat(self, outdir):
        try:
            sql = (
                """SELECT fid, n_value, elevation, ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM grid ORDER BY fid;"""
            )
            records = self.execute(sql)
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

    def export_neighbours(self):
        if self.parsed_format == self.FORMAT_DAT:
            raise NotImplementedError("Exporting NEIGHBOURS.DAT is not supported!")
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_neighbours_hdf5()

    def export_neighbours_hdf5(self):
        try:
            neighbors_group = self.parser.neighbors_group
            for row in grid_compas_neighbors(self.gutils):
                directions = ["N", "E", "S", "W", "NE", "SE", "SW", "NW"]
                for direction, neighbor_gid in zip(directions, row):
                    neighbors_group.datasets[direction].data.append(neighbor_gid)
            self.parser.write_groups(neighbors_group)
            return True
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR: exporting grid neighbors data failed!.\n", e)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            return False

    def export_inflow(self, output=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_inflow_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_inflow_hdf5()

    def export_inflow_hdf5(self):
        """
        Function to export inflow data to hdf5
        """
        if self.is_table_empty("inflow") and self.is_table_empty("reservoirs"):
            return False
        cont_sql = """SELECT value FROM cont WHERE name = ?;"""
        inflow_sql = """SELECT fid, time_series_fid, ident, inoutfc FROM inflow WHERE bc_fid = ?;"""
        inflow_cells_sql = """SELECT inflow_fid, grid_fid FROM inflow_cells ORDER BY inflow_fid, grid_fid;"""
        ts_data_sql = (
            """SELECT time, value, value2 FROM inflow_time_series_data WHERE series_fid = ? ORDER BY fid;"""
        )

        head_line = " {0: <15} {1}"
        inf_line = "{0: <15} {1: <15} {2}"
        tsd_line = "H   {0: <15} {1: <15} {2}"

        ideplt = self.execute(cont_sql, ("IDEPLT",)).fetchone()
        ihourdaily = self.execute(cont_sql, ("IHOURDAILY",)).fetchone()

        # TODO: Need to implement correct export for ideplt and ihourdaily parameters
        if ihourdaily is None:
            ihourdaily = (0,)
        if ideplt is None:
            first_gid = self.execute("""SELECT grid_fid FROM inflow_cells ORDER BY fid LIMIT 1;""").fetchone()
            ideplt = first_gid if first_gid is not None else (0,)

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
                    tsd_row = [x if x is not None else "" for x in tsd_row]
                    inflow_lines.append(tsd_line.format(*tsd_row).rstrip())

        if not self.is_table_empty("reservoirs"):
            schematic_reservoirs_sql = (
                """SELECT grid_fid, wsel, n_value, use_n_value, tailings FROM reservoirs ORDER BY fid;"""
            )

            res_line1a = "R   {0: <15} {1:<10.2f} {2:<10.2f}"
            res_line1at = "R   {0: <15} {1:<10.2f} {4:<10.2f} {2:<10.2f}"

            res_line1b = "R   {0: <15} {1:<10.2f}"
            res_line1bt = "R   {0: <15} {1:<10.2f} {2:<10.2f}"

            res_line2a = "R     {0: <15} {1:<10.2f} {2:<10.2f}"
            res_line2at = "R     {0: <15} {1:<10.2f} {4:<10.2f} {2:<10.2f}"

            res_line2b = "R     {0: <15} {1:<10.2f}"
            res_line2bt = "R     {0: <15} {1:<10.2f} {4:<10.2f}"

            for res in self.execute(schematic_reservoirs_sql):
                res = [x if x is not None else "" for x in res]

                if res[3] == 1:  # write n value
                    if res[4] == -1.0:
                        # Do not write tailings
                        inflow_lines.append(res_line2a.format(*res))
                    else:
                        # Write tailings:
                        inflow_lines.append(res_line2at.format(*res))
                else:  # do not write n value
                    if res[4] == -1.0:
                        # Do not write tailings:
                        inflow_lines.append(res_line2b.format(*res))
                    else:
                        # Write tailings:
                        inflow_lines.append(res_line2bt.format(*res))

        if inflow_lines:
            bc_group = self.parser.bc_group
            bc_group.create_dataset('Inflow', [])
            for line in inflow_lines:
                if line:
                    values = line.split()
                    c1 = values[0]
                    c2 = values[1]
                    c3 = values[2] if len(values) == 3 else ""
                    data_array = np.array([c1, c2, c3], dtype=np.string_)
                    bc_group.datasets["Inflow"].data.append(data_array)
            self.parser.write_groups(bc_group)

        return True

    def export_inflow_dat(self, outdir):
        # check if there are any inflows defined
        try:
            if self.is_table_empty("inflow") and self.is_table_empty("reservoirs"):
                return False
            cont_sql = """SELECT value FROM cont WHERE name = ?;"""
            inflow_sql = """SELECT fid, time_series_fid, ident, inoutfc FROM inflow WHERE bc_fid = ?;"""
            inflow_cells_sql = """SELECT inflow_fid, grid_fid FROM inflow_cells ORDER BY inflow_fid, grid_fid;"""
            ts_data_sql = (
                """SELECT time, value, value2 FROM inflow_time_series_data WHERE series_fid = ? ORDER BY fid;"""
            )

            head_line = " {0: <15} {1}"
            inf_line = "{0: <15} {1: <15} {2}"
            tsd_line = "H   {0: <15} {1: <15} {2}"

            ideplt = self.execute(cont_sql, ("IDEPLT",)).fetchone()
            ihourdaily = self.execute(cont_sql, ("IHOURDAILY",)).fetchone()

            # TODO: Need to implement correct export for ideplt and ihourdaily parameters
            if ihourdaily is None:
                ihourdaily = (0,)
            if ideplt is None:
                first_gid = self.execute("""SELECT grid_fid FROM inflow_cells ORDER BY fid LIMIT 1;""").fetchone()
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
                        tsd_row = [x if x is not None else "" for x in tsd_row]
                        inflow_lines.append(tsd_line.format(*tsd_row).rstrip())

            if not self.is_table_empty("reservoirs"):
                schematic_reservoirs_sql = (
                    """SELECT grid_fid, wsel, n_value, use_n_value, tailings FROM reservoirs ORDER BY fid;"""
                )

                res_line1a = "R   {0: <15} {1:<10.2f} {2:<10.2f}"
                res_line1at = "R   {0: <15} {1:<10.2f} {4:<10.2f} {2:<10.2f}"

                res_line1b = "R   {0: <15} {1:<10.2f}"
                res_line1bt = "R   {0: <15} {1:<10.2f} {2:<10.2f}"

                res_line2a = "R     {0: <15} {1:<10.2f} {2:<10.2f}"
                res_line2at = "R     {0: <15} {1:<10.2f} {4:<10.2f} {2:<10.2f}"

                res_line2b = "R     {0: <15} {1:<10.2f}"
                res_line2bt = "R     {0: <15} {1:<10.2f} {4:<10.2f}"

                for res in self.execute(schematic_reservoirs_sql):
                    res = [x if x is not None else "" for x in res]

                    if res[3] == 1:  # write n value
                        if res[4] == -1.0:
                            # Do not write tailings
                            inflow_lines.append(res_line2a.format(*res))
                        else:
                            # Write tailings:
                            inflow_lines.append(res_line2at.format(*res))
                    else:  # do not write n value
                        if res[4] == -1.0:
                            # Do not write tailings:
                            inflow_lines.append(res_line2b.format(*res))
                        else:
                            # Write tailings:
                            inflow_lines.append(res_line2bt.format(*res))

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

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1542: exporting INFLOW.DAT failed!.\n", e)
            return False

    def export_tailings(self, outdir):
        try:
            if self.is_table_empty("tailing_cells"):
                return False

            tailings_sql = """SELECT grid_fid, thickness FROM tailing_cells ORDER BY grid_fid;"""
            line1 = "{0}  {1}\n"

            rows = self.execute(tailings_sql).fetchall()
            if not rows:
                return False
            else:
                pass
            tailingsf = os.path.join(outdir, "TAILINGS.DAT")
            with open(tailingsf, "w") as t:
                for row in rows:
                    t.write(line1.format(*row))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 040822.0442: exporting TAILINGS.DAT failed!.\n", e)
            return False

    def export_outflow(self, output=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_outflow_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_outflow_hdf5()

    def export_outflow_dat(self, outdir):
        # check if there are any outflows defined.
        try:
            if self.is_table_empty("outflow") or self.is_table_empty("outflow_cells"):
                return False

            outflow_sql = """
            SELECT fid, fp_out, chan_out, hydro_out, chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid
            FROM outflow WHERE fid = ?;"""
            outflow_cells_sql = """SELECT outflow_fid, grid_fid FROM outflow_cells ORDER BY outflow_fid, grid_fid;"""
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
            if not out_cells:
                return False
            else:
                pass
            outflow = os.path.join(outdir, "OUTFLOW.DAT")
            floodplains = {}
            previous_oid = -1
            row = None
            border = get_BC_Border()

            warning = ""
            with open(outflow, "w") as o:
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
                            for values in self.execute(qh_params_data_sql, (chan_qhpar_fid,)):
                                o.write(qh_params_line.format(*values))
                            for values in self.execute(qh_table_data_sql, (chan_qhtab_fid,)):
                                o.write(qh_table_line.format(*values))
                        else:
                            pass

                        if chan_tser_fid > 0 or fp_tser_fid > 0:
                            if border is not None:
                                if gid in border:
                                    continue
                            nostacfp = 1 if chan_tser_fid == 1 else 0
                            o.write(n_line.format(gid, nostacfp))
                            series_fid = chan_tser_fid if chan_tser_fid > 0 else fp_tser_fid
                            for values in self.execute(ts_data_sql, (series_fid,)):
                                o.write(ts_line.format(*values))
                        else:
                            pass

                # Write O1, O2, ... lines:
                for gid, hydro_out in sorted(iter(floodplains.items()), key=lambda items: (items[1], items[0])):
                    #                     if border is not None:
                    #                         if gid in border:
                    #                             continue
                    ident = "O{0}".format(hydro_out) if hydro_out > 0 else "O"
                    o.write(o_line.format(ident, gid))
                    if border is not None:
                        if gid in border:
                            border.remove(gid)

                # Write lines 'O cell_id":
                if border is not None:
                    for b in border:
                        o.write(o_line.format("O", b))

            QApplication.restoreOverrideCursor()
            if warning != "":
                msg = "ERROR 170319.2018: error while exporting OUTFLOW.DAT!<br><br>" + warning
                msg += "<br><br><FONT COLOR=red>Did you schematize the Boundary Conditions?</FONT>"
                self.uc.show_warn(msg)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1543: exporting OUTFLOW.DAT failed!.\n", e)
            return False

    def export_outflow_hdf5(self):
        """
        Function to export outflow data to HDF5 file
        """

        # check if there are any outflows defined.
        # try:
        if self.is_table_empty("outflow") or self.is_table_empty("outflow_cells"):
            return False

        outflow_sql = """
        SELECT fid, fp_out, chan_out, hydro_out, chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid
        FROM outflow WHERE fid = ?;"""
        outflow_cells_sql = """SELECT outflow_fid, grid_fid FROM outflow_cells ORDER BY outflow_fid, grid_fid;"""
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
        if not out_cells:
            return False
        else:
            pass
        bc_group = self.parser.bc_group
        bc_group.create_dataset('Outflow', [])

        floodplains = {}
        previous_oid = -1
        row = None
        border = get_BC_Border()

        warning = ""

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
                    bc_group.datasets["Outflow"].data.append(create_array(k_line, 4, gid))
                    for qh_params_values in self.execute(qh_params_data_sql, (chan_qhpar_fid,)):
                        bc_group.datasets["Outflow"].data.append(create_array(qh_params_line, 4, qh_params_values))
                    for qh_table_values in self.execute(qh_table_data_sql, (chan_qhtab_fid,)):
                        bc_group.datasets["Outflow"].data.append(create_array(qh_table_line, 4, qh_table_values))
                else:
                    pass

                if chan_tser_fid > 0 or fp_tser_fid > 0:
                    if border is not None:
                        if gid in border:
                            continue
                    nostacfp = 1 if chan_tser_fid == 1 else 0
                    bc_group.datasets["Outflow"].data.append(create_array(n_line, 4, gid, nostacfp))
                    series_fid = chan_tser_fid if chan_tser_fid > 0 else fp_tser_fid
                    for ts_line_values in self.execute(ts_data_sql, (series_fid,)):
                        bc_group.datasets["Outflow"].data.append(create_array(ts_line, 4, ts_line_values))
                else:
                    pass

        # Write O1, O2, ... lines:
        for gid, hydro_out in sorted(iter(floodplains.items()), key=lambda items: (items[1], items[0])):
            #                     if border is not None:
            #                         if gid in border:
            #                             continue
            ident = "O{0}".format(hydro_out) if hydro_out > 0 else "O"
            bc_group.datasets["Outflow"].data.append(create_array(o_line, 4, ident, gid))
            if border is not None:
                if gid in border:
                    border.remove(gid)

        # Write lines 'O cell_id':
        if border is not None:
            for b in border:
                bc_group.datasets["Outflow"].data.append(create_array(o_line, 4, "0", b))

        self.parser.write_groups(bc_group)
        QApplication.restoreOverrideCursor()
        if warning != "":
            msg = "ERROR 170319.2018: error while exporting OUTFLOW.DAT!<br><br>" + warning
            msg += "<br><br><FONT COLOR=red>Did you schematize the Boundary Conditions?</FONT>"
            self.uc.show_warn(msg)
        return True

        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error("ERROR 101218.1543: exporting OUTFLOW.DAT failed!.\n", e)
        #     return False

    def export_rain(self, output=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_rain_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_rain_hdf5()

    def export_rain_hdf5(self):
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
        rain_cells_sql = """SELECT grid_fid, arf FROM rain_arf_cells ORDER BY fid;"""

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
        if rain_row is None:
            return False
        else:
            pass

        rain_group = self.parser.rain_group
        rain_group.create_dataset('Rain', [])

        rain_group.datasets["Rain"].data.append(create_array(rain_line1, 4, rain_row[1:3]))
        rain_group.datasets["Rain"].data.append(create_array(rain_line2, 4, rain_row[3:7]))

        fid = rain_row[
            0
        ]  # time_series_fid (pointer to the 'rain_time_series_data' table where the pairs (time , distribution) are.
        for row in self.execute(ts_data_sql, (fid,)):
            if None not in row:  # Writes 3rd. lines if rain_time_series_data exists (Rainfall distribution).
                rain_group.datasets["Rain"].data.append(create_array(tsd_line3, 4, row))
                # This is a time series created from the Rainfall Distribution tool in the Rain Editor,
                # selected from a list

        if rain_row[6] == 1:  # if movingstorm from rain = 0, omit this line.
            if (
                rain_row[-1] is not None
            ):  # row[-1] is the last value of tuple (time_series_fid, irainreal, irainbuilding, tot_rainfall,
                # rainabs, irainarf, movingstorm, rainspeed, iraindir).
                rain_group.datasets["Rain"].data.append(create_array(rain_line4, 4, rain_row[-2:]))
            else:
                pass
        else:
            pass

        if rain_row[5] == 1:  # if irainarf from rain = 0, omit this line.
            for row in self.execute(rain_cells_sql):
                rain_group.datasets["Rain"].data.append(create_array(cell_line5, 4, row[0], "{0:.3f}".format(row[1])))

        self.parser.write_groups(rain_group)
        return True

        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error("ERROR 101218.1543: exporting RAIN.DAT failed!.\n", e)
        #     return False

    def export_rain_dat(self, outdir):
        # check if there is any rain defined.
        # try:
        if self.is_table_empty("rain"):
            return False
        rain_sql = """SELECT time_series_fid, irainreal, irainbuilding, tot_rainfall,
                             rainabs, irainarf, movingstorm, rainspeed, iraindir
                      FROM rain;"""

        ts_data_sql = """SELECT time, value FROM rain_time_series_data WHERE series_fid = ? ORDER BY fid;"""
        rain_cells_sql = """SELECT grid_fid, arf FROM rain_arf_cells ORDER BY fid;"""

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
        if rain_row is None:
            return False
        else:
            pass

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

        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error("ERROR 101218.1543: exporting RAIN.DAT failed!.\n", e)
        #     return False

    def export_raincell(self, outdir):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if self.is_table_empty("raincell"):
                return False
            head_sql = """SELECT rainintime, irinters, timestamp FROM raincell LIMIT 1;"""
            data_sql = """SELECT rrgrid, iraindum FROM raincell_data ORDER BY time_interval, rrgrid;"""
            size_sql = """SELECT COUNT(iraindum) FROM raincell_data"""
            line1 = "{0} {1} {2}\n"
            line2 = "{0} {1}\n"

            raincell_head = self.execute(head_sql).fetchone()
            raincell_rows = self.execute(data_sql)
            raincell_size = self.execute(size_sql).fetchone()[0]
            raincell = os.path.join(outdir, "RAINCELL.DAT")
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

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1558: exporting RAINCELL.DAT failed!.\n", e)
            return False
        finally:
            QApplication.restoreOverrideCursor()

    def export_infil(self, output=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_infil_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_infil_hdf5()

    def export_infil_dat(self, outdir):
        # check if there is any infiltration defined.
        try:
            if self.is_table_empty("infil"):
                return False
            infil_sql = """SELECT * FROM infil;"""
            infil_r_sql = """SELECT hydcx, hydcxfinal, soildepthcx FROM infil_chan_seg ORDER BY chan_seg_fid, fid;"""
            green_sql = """SELECT grid_fid, hydc, soils, dtheta, abstrinf, rtimpf, soil_depth FROM infil_cells_green ORDER by grid_fid;"""
            scs_sql = """SELECT grid_fid,scsn FROM infil_cells_scs ORDER BY grid_fid;"""
            horton_sql = """SELECT grid_fid,fhorti, fhortf, deca FROM infil_cells_horton ORDER BY grid_fid;"""
            chan_sql = """SELECT grid_fid, hydconch FROM infil_chan_elems ORDER by grid_fid;"""

            line1 = "{0}"
            line2 = "\n" + "  {}" * 6
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
                v1, v2, v3, v4, v5, v9 = (
                    gen[0],
                    gen[1:7],
                    gen[7:10],
                    gen[10:11],
                    gen[11:13],
                    gen[13:],
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

    def export_infil_hdf5(self):
        """
        Function to export infiltration data to HDF5
        """
        # check if there is any infiltration defined.
        # try:
        if self.is_table_empty("infil"):
            return False
        infil_sql = """SELECT * FROM infil;"""
        infil_r_sql = """SELECT hydcx, hydcxfinal, soildepthcx FROM infil_chan_seg ORDER BY chan_seg_fid, fid;"""
        green_sql = """SELECT grid_fid, hydc, soils, dtheta, abstrinf, rtimpf, soil_depth FROM infil_cells_green ORDER by grid_fid;"""
        scs_sql = """SELECT grid_fid,scsn FROM infil_cells_scs ORDER BY grid_fid;"""
        horton_sql = """SELECT grid_fid,fhorti, fhortf, deca FROM infil_cells_horton ORDER BY grid_fid;"""
        chan_sql = """SELECT grid_fid, hydconch FROM infil_chan_elems ORDER by grid_fid;"""

        line1 = "{0}"
        line2 = "\n" + "  {}" * 6
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

        infil_group = self.parser.infil_group
        infil_group.create_dataset('Infiltration', [])

        gen = [x if x is not None else "" for x in infil_row[1:]]
        v1, v2, v3, v4, v5, v9 = (
            gen[0],
            gen[1:7],
            gen[7:10],
            gen[10:11],
            gen[11:13],
            gen[13:],
        )

        infil_group.datasets["Infiltration"].data.append(create_array(line1, 8, v1))
        if v1 == 1 or v1 == 3:
            infil_group.datasets["Infiltration"].data.append(create_array(line2, 8, tuple(v2)))
            infil_group.datasets["Infiltration"].data.append(create_array(line3, 8, tuple(v3)))
            if v2[5] == 1:
                infil_group.datasets["Infiltration"].data.append(create_array(line4, 8, tuple(v4)))
            for row in self.execute(infil_r_sql):
                row = [x if x is not None else "" for x in row]
                infil_group.datasets["Infiltration"].data.append(create_array(line4ab, 8, row))
        if v1 == 2 or v1 == 3:
            if any(v5) is True:
                infil_group.datasets["Infiltration"].data.append(create_array(line5, 8, tuple(v5)))
            else:
                pass
        for row in self.execute(green_sql):
            infil_group.datasets["Infiltration"].data.append(create_array(line6, 8, row))
        for row in self.execute(scs_sql):
            infil_group.datasets["Infiltration"].data.append(create_array(line7, 8, row))
        for row in self.execute(chan_sql):
            infil_group.datasets["Infiltration"].data.append(create_array(line8, 8, row))
        if any(v9) is True:
            infil_group.datasets["Infiltration"].data.append(create_array(line9, 8, tuple(v9)))
        else:
            pass
        for row in self.execute(horton_sql):
            infil_group.datasets["Infiltration"].data.append(create_array(line10, 8, row))
        self.parser.write_groups(infil_group)
        return True

        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error("ERROR 101218.1559: exporting INFIL.DAT failed!.\n", e)
        #     return False

    def export_evapor(self, outdir):
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

    def export_chan(self, output = None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_chan_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_chan_hdf5()

    def export_chan_hdf5(self):
        """
        Function to export channel data to hdf5
        """
        if self.is_table_empty("chan"):
            return False

        chan_sql = """SELECT fid, depinitial, froudc, roughadj, isedn FROM chan ORDER BY fid;"""
        chan_elems_sql = (
            """SELECT fid, rbankgrid, fcn, xlen, type FROM chan_elems WHERE seg_fid = ? ORDER BY nr_in_seg;"""
        )

        chan_r_sql = """SELECT elem_fid, bankell, bankelr, fcw, fcd FROM chan_r WHERE elem_fid = ?;"""
        chan_v_sql = """SELECT elem_fid, bankell, bankelr, fcd, a1, a2, b1, b2, c1, c2,
                                   excdep, a11, a22, b11, b22, c11, c22 FROM chan_v WHERE elem_fid = ?;"""
        chan_t_sql = """SELECT elem_fid, bankell, bankelr, fcw, fcd, zl, zr FROM chan_t WHERE elem_fid = ?;"""
        chan_n_sql = """SELECT elem_fid, nxsecnum FROM chan_n WHERE elem_fid = ?;"""

        chan_wsel_sql = """SELECT istart, wselstart, iend, wselend FROM chan_wsel ORDER BY fid;"""
        chan_conf_sql = """SELECT chan_elem_fid FROM chan_confluences ORDER BY fid;"""
        chan_e_sql = """SELECT grid_fid FROM noexchange_chan_cells ORDER BY fid;"""

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

        chan_rows = self.execute(chan_sql).fetchall()
        if not chan_rows:
            return False
        else:
            pass

        channel_group = self.parser.channel_group
        channel_group.create_dataset('Chan', [])
        channel_group.create_dataset('Chanbank', [])

        ISED = self.gutils.get_cont_par("ISED")

        for row in chan_rows:
            row = [x if x is not None else "0" for x in row]
            fid = row[0]
            if ISED == "0":
                row[4] = ""
            channel_group.datasets["Chan"].data.append(create_array(segment, 20, tuple(row[1:5])))
            # Writes depinitial, froudc, roughadj, isedn from 'chan' table (schematic layer).
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
                res = [
                    x if x is not None else "" for x in self.execute(sql, (eid,)).fetchone()
                ]  # 'res' is a list of values depending on 'typ' (R,V,T, or N).

                res.insert(
                    fcn_idx, fcn
                )  # Add 'fcn' (coming from table ´chan_elems' (cross sections) to 'res' list) in position 'fcn_idx'.
                res.insert(
                    xlen_idx, xlen
                )  # Add ´xlen' (coming from table ´chan_elems' (cross sections) to 'res' list in position 'xlen_idx'.
                channel_group.datasets["Chan"].data.append(create_array(line, 20, tuple(res)))
                channel_group.datasets["Chanbank"].data.append(create_array(chanbank, 20, eid, rbank))

        for row in self.execute(chan_wsel_sql):
            channel_group.datasets["Chan"].data.append(create_array(wsel, 20, tuple(row[:2])))
            channel_group.datasets["Chan"].data.append(create_array(wsel, 20, tuple(row[2:])))

        pairs = []
        for row in self.execute(chan_conf_sql):
            chan_elem = row[0]
            if not pairs:
                pairs.append(chan_elem)
            else:
                pairs.append(chan_elem)
                channel_group.datasets["Chan"].data.append(create_array(conf, 20, pairs))
                del pairs[:]

        for row in self.execute(chan_e_sql):
            channel_group.datasets["Chan"].data.append(create_array(chan_e, 20, row[0]))

        self.parser.write_groups(channel_group)
        return True

    def export_chan_dat(self, outdir):
        # check if there are any channels defined.
        #         try:
        if self.is_table_empty("chan"):
            return False
        chan_sql = """SELECT fid, depinitial, froudc, roughadj, isedn FROM chan ORDER BY fid;"""
        chan_elems_sql = (
            """SELECT fid, rbankgrid, fcn, xlen, type FROM chan_elems WHERE seg_fid = ? ORDER BY nr_in_seg;"""
        )

        chan_r_sql = """SELECT elem_fid, bankell, bankelr, fcw, fcd FROM chan_r WHERE elem_fid = ?;"""
        chan_v_sql = """SELECT elem_fid, bankell, bankelr, fcd, a1, a2, b1, b2, c1, c2,
                                   excdep, a11, a22, b11, b22, c11, c22 FROM chan_v WHERE elem_fid = ?;"""
        chan_t_sql = """SELECT elem_fid, bankell, bankelr, fcw, fcd, zl, zr FROM chan_t WHERE elem_fid = ?;"""
        chan_n_sql = """SELECT elem_fid, nxsecnum FROM chan_n WHERE elem_fid = ?;"""

        chan_wsel_sql = """SELECT istart, wselstart, iend, wselend FROM chan_wsel ORDER BY fid;"""
        chan_conf_sql = """SELECT chan_elem_fid FROM chan_confluences ORDER BY fid;"""
        chan_e_sql = """SELECT grid_fid FROM noexchange_chan_cells ORDER BY fid;"""

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

        chan_rows = self.execute(chan_sql).fetchall()
        if not chan_rows:
            return False
        else:
            pass

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
                    res = [
                        x if x is not None else "" for x in self.execute(sql, (eid,)).fetchone()
                    ]  # 'res' is a list of values depending on 'typ' (R,V,T, or N).

                    res.insert(
                        fcn_idx, fcn
                    )  # Add 'fcn' (coming from table ´chan_elems' (cross sections) to 'res' list) in position 'fcn_idx'.
                    res.insert(
                        xlen_idx, xlen
                    )  # Add ´xlen' (coming from table ´chan_elems' (cross sections) to 'res' list in position 'xlen_idx'.
                    c.write(line.format(*res))
                    b.write(chanbank.format(eid, rbank))

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

        return True

    #         except Exception as e:
    #             QApplication.restoreOverrideCursor()
    #             self.uc.show_error("ERROR 101218.1623: exporting CHAN.DAT failed!.\n", e)
    #             return False

    def export_xsec(self, output = None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_xsec_data(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_xsec_hdf5()

    def export_xsec_hdf5(self):
        """
        Function to export xsection data to hdf5 file
        """
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

            channel_group = self.parser.channel_group
            channel_group.create_dataset('Cross Sections', [])
            for nxecnum, xsecname in chan_n:
                channel_group.datasets["Cross Sections"].data.append(create_array(xsec_line, 3, nxecnum, xsecname))
                for xi, yi in self.execute(xsec_sql, (nxecnum,)):
                    channel_group.datasets["Cross Sections"].data.append(create_array(pkt_line, 3, xi, yi))

            self.parser.write_groups(channel_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1607:  exporting XSEC.DAT  failed!.\n", e)
            return False

    def export_xsec_dat(self, outdir):
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

    def export_xsec_dat(self, outdir):
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

    def export_hystruc(self, output = None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_hystruc_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_hystruc_hdf5()

    def export_hystruc_hdf5(self):
        """
        Function to export Hydraulic Structure data to HDF5 file
        """
        # try:
        # check if there is any hydraulic structure defined.
        if self.is_table_empty("struct"):
            return False
        else:
            nodes = self.execute("SELECT outflonod, outflonod FROM struct;").fetchall()
            for nod in nodes:
                if nod[0] in [NULL, 0, ""] or nod[1] in [NULL, 0, ""]:
                    QApplication.restoreOverrideCursor()
                    self.uc.bar_warn(
                        "WARNING: some structures have no cells assigned.\nDid you schematize the structures?"
                    )
                    break

        hystruct_sql = """SELECT * FROM struct ORDER BY fid;"""
        ratc_sql = """SELECT * FROM rat_curves WHERE struct_fid = ? ORDER BY fid;"""
        repl_ratc_sql = """SELECT * FROM repl_rat_curves WHERE struct_fid = ? ORDER BY fid;"""
        ratt_sql = """SELECT * FROM rat_table WHERE struct_fid = ? ORDER BY fid;"""
        culvert_sql = """SELECT * FROM culvert_equations WHERE struct_fid = ? ORDER BY fid;"""
        storm_sql = """SELECT * FROM storm_drains WHERE struct_fid = ? ORDER BY fid;"""
        bridge_a_sql = """SELECT fid, struct_fid, IBTYPE, COEFF, C_PRIME_USER, KF_COEF, KWW_COEF,  KPHI_COEF, KY_COEF, KX_COEF, KJ_COEF 
                            FROM bridge_variables WHERE struct_fid = ? ORDER BY fid;"""
        bridge_b_sql = """SELECT fid, struct_fid, BOPENING, BLENGTH, BN_VALUE, UPLENGTH12, LOWCHORD,
                                 DECKHT, DECKLENGTH, PIERWIDTH, SLUICECOEFADJ, ORIFICECOEFADJ, 
                                COEFFWEIRB, WINGWALL_ANGLE, PHI_ANGLE, LBTOEABUT, RBTOEABUT 
                              FROM bridge_variables WHERE struct_fid = ? ORDER BY fid;"""

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

        # hystruc = os.path.join(outdir, "HYSTRUC.DAT")
        hystruc_group = self.parser.hystruc_group
        hystruc_group.create_dataset('Hystruct', [])

        d_lines = []
        for stru in hystruc_rows:
            fid = stru[0]
            vals1 = [x if x is not None and x != "" else 0 for x in stru[2:8]]
            vals2 = [x if x is not None and x != "" else 0.0 for x in stru[8:11]]
            vals = vals1 + vals2
            hystruc_group.datasets["Hystruct"].data.append(create_array(line1, 16, tuple(vals)))
            # h.write(line1.format(*vals))
            type = stru[4]  #  0: rating curve
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
                                hystruc_group.datasets["Hystruct"].data.append(create_array(line, 16, tuple(subvals)))
                                # h.write(line.format(*subvals))

        # TODO: Fix the D lines for HDF5
        # if d_lines:
        #     for dl in d_lines:
        #         h.write(dl)

        self.parser.write_groups(hystruc_group)
        return True

        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error("ERROR 101218.1608: exporting HYSTRUC.DAT failed!.\n", e)
        #     return False

    def export_hystruc_dat(self, outdir):
        try:
            # check if there is any hydraulic structure defined.
            if self.is_table_empty("struct"):
                return False
            else:
                nodes = self.execute("SELECT outflonod, outflonod FROM struct;").fetchall()
                for nod in nodes:
                    if nod[0] in [NULL, 0, ""] or nod[1] in [NULL, 0, ""]:
                        QApplication.restoreOverrideCursor()
                        self.uc.bar_warn(
                            "WARNING: some structures have no cells assigned.\nDid you schematize the structures?"
                        )
                        break

            hystruct_sql = """SELECT * FROM struct ORDER BY fid;"""
            ratc_sql = """SELECT * FROM rat_curves WHERE struct_fid = ? ORDER BY fid;"""
            repl_ratc_sql = """SELECT * FROM repl_rat_curves WHERE struct_fid = ? ORDER BY fid;"""
            ratt_sql = """SELECT * FROM rat_table WHERE struct_fid = ? ORDER BY fid;"""
            culvert_sql = """SELECT * FROM culvert_equations WHERE struct_fid = ? ORDER BY fid;"""
            storm_sql = """SELECT * FROM storm_drains WHERE struct_fid = ? ORDER BY fid;"""
            bridge_a_sql = """SELECT fid, struct_fid, IBTYPE, COEFF, C_PRIME_USER, KF_COEF, KWW_COEF,  KPHI_COEF, KY_COEF, KX_COEF, KJ_COEF 
                                FROM bridge_variables WHERE struct_fid = ? ORDER BY fid;"""
            bridge_b_sql = """SELECT fid, struct_fid, BOPENING, BLENGTH, BN_VALUE, UPLENGTH12, LOWCHORD,
                                     DECKHT, DECKLENGTH, PIERWIDTH, SLUICECOEFADJ, ORIFICECOEFADJ, 
                                    COEFFWEIRB, WINGWALL_ANGLE, PHI_ANGLE, LBTOEABUT, RBTOEABUT 
                                  FROM bridge_variables WHERE struct_fid = ? ORDER BY fid;"""

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
                    type = stru[4]  #  0: rating curve
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

    def export_bridge_xsec(self, outdir):
        try:
            # check if there is any hydraulic structure and bridge cross sections defined.
            if self.is_table_empty("struct") or self.is_table_empty("bridge_xs"):
                if os.path.isfile(outdir + r"\BRIDGE_XSEC.DAT"):
                    os.remove(outdir + r"\BRIDGE_XSEC.DAT")
                return False

            hystruct_sql = """SELECT * FROM struct WHERE icurvtable = 3 ORDER BY fid;"""
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

    def export_bridge_coeff_data(self, output = None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_bridge_coeff_data_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_bridge_coeff_data_hdf5()

    def export_bridge_coeff_data_hdf5(self):
        """
        Export bridge coefficient data to the hdf5 file
        """
        try:
            if self.is_table_empty("struct"):
                return False
            hystruc_group = self.parser.hystruc_group
            hystruc_group.create_dataset('Bridge Coefficientt Data', [])

            src = os.path.dirname(os.path.abspath(__file__)) + "/bridge_coeff_data.dat"''
            data = []
            with open(src, 'r') as bridge_coeff_data:
                for line in bridge_coeff_data:
                    hystruc_group.datasets["Bridge Coefficientt Data"].data.append(create_array(line, 13))

            self.parser.write_groups(hystruc_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101122.0754: exporting BRIDGE_COEFF_DATA.DAT failed!.\n", e)
            return False

    def export_bridge_coeff_data_dat(self, outdir):
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

    def export_street(self, outdir):
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
                return False
            else:
                pass
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

    def export_arf(self, output=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_arf_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_arf_hdf5()

    def export_arf_dat(self, outdir):
        """
        Function to export arf data to HDF5 file
        """
        try:
            if self.is_table_empty("blocked_cells"):
                return False
            cont_sql = """SELECT name, value FROM cont WHERE name = 'IARFBLOCKMOD';"""
            tbc_sql = """SELECT grid_fid, area_fid FROM blocked_cells WHERE arf = 1 ORDER BY grid_fid;"""

            pbc_sql = """SELECT grid_fid, area_fid,  arf, wrf1, wrf2, wrf3, wrf4, wrf5, wrf6, wrf7, wrf8
                         FROM blocked_cells WHERE arf < 1 ORDER BY grid_fid;"""
            collapse_sql = """SELECT collapse FROM user_blocked_areas WHERE fid = ?;"""

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
                    collapse = self.execute(collapse_sql, (row[1],)).fetchone()
                    if collapse:
                        cll = collapse[0]
                    else:
                        cll = 0
                    cll = [cll if cll is not None else 0]
                    cell = row[0]
                    if cll[0] == 1:
                        cell = -cell
                    a.write(line2.format(cell))

                # Partially blocked grid elements:
                for row in self.execute(pbc_sql):
                    row = [x if x is not None else "" for x in row]
                    # Is there any side blocked? If not omit it:
                    any_blocked = sum(row) - row[0] - row[1]
                    if any_blocked > 0:
                        collapse = self.execute(collapse_sql, (row[1],)).fetchone()
                        if collapse:
                            cll = collapse[0]
                        else:
                            cll = 0
                        cll = [cll if cll is not None else 0]
                        cell = row[0]
                        arf_value = row[2]
                        if cll[0] == 1:
                            arf_value = -arf_value
                        a.write(line3.format(cell, arf_value, *row[3:]))
            #                     a.write(line3.format(*row))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1610: exporting ARF.DAT failed!.", e)
            return False


    def export_arf_hdf5(self):
        # check if there are any grid cells with ARF defined.
        try:
            if self.is_table_empty("blocked_cells"):
                return False
            cont_sql = """SELECT name, value FROM cont WHERE name = 'IARFBLOCKMOD';"""
            tbc_sql = """SELECT grid_fid, area_fid FROM blocked_cells WHERE arf = 1 ORDER BY grid_fid;"""

            pbc_sql = """SELECT grid_fid, area_fid,  arf, wrf1, wrf2, wrf3, wrf4, wrf5, wrf6, wrf7, wrf8
                         FROM blocked_cells WHERE arf < 1 ORDER BY grid_fid;"""
            collapse_sql = """SELECT collapse FROM user_blocked_areas WHERE fid = ?;"""

            line1 = "S  {}\n"
            line2 = " T   {}\n"
            line3 = "{0:<8} {1:<5.2f} {2:<5.2f} {3:<5.2f} {4:<5.2f} {5:<5.2f} {6:<5.2f} {7:<5.2f} {8:5.2f} {9:<5.2f}\n"
            option = self.execute(cont_sql).fetchone()
            if option is None:
                # TODO: We need to implement correct export of 'IARFBLOCKMOD'
                option = ("IARFBLOCKMOD", 0)

            # arf = os.path.join(outdir, "ARF.DAT")
            arfwrf_group = self.parser.arfwrf_group
            arfwrf_group.create_dataset('ARF', [])

            # with open(arf, "w") as a:
            head = option[-1]
            if head is not None:
                arfwrf_group.datasets["ARF"].data.append(create_array(line1, 10, head))
                # a.write(line1.format(head))
            else:
                pass

            # Totally blocked grid elements:
            for row in self.execute(tbc_sql):
                collapse = self.execute(collapse_sql, (row[1],)).fetchone()
                if collapse:
                    cll = collapse[0]
                else:
                    cll = 0
                cll = [cll if cll is not None else 0]
                cell = row[0]
                if cll[0] == 1:
                    cell = -cell
                arfwrf_group.datasets["ARF"].data.append(create_array(line2, 10, cell))
                # a.write(line2.format(cell))

            # Partially blocked grid elements:
            for row in self.execute(pbc_sql):
                row = [x if x is not None else "" for x in row]
                # Is there any side blocked? If not omit it:
                any_blocked = sum(row) - row[0] - row[1]
                if any_blocked > 0:
                    collapse = self.execute(collapse_sql, (row[1],)).fetchone()
                    if collapse:
                        cll = collapse[0]
                    else:
                        cll = 0
                    cll = [cll if cll is not None else 0]
                    cell = row[0]
                    arf_value = row[2]
                    if cll[0] == 1:
                        arf_value = -arf_value
                    # a.write(line3.format(cell, arf_value, *row[3:]))
                    arfwrf_group.datasets["ARF"].data.append(create_array(line3, 10, cell, arf_value, *row[3:]))
            self.parser.write_groups(arfwrf_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1610: exporting ARF.DAT failed!.", e)
            return False

    def export_mult(self, output=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_mult_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_mult_hdf5()

    def export_mult_hdf5(self):
        """
        Function to export mult data to hdf5 file
        """

        rtrn = True
        if self.is_table_empty("mult_cells") and self.is_table_empty("simple_mult_cells"):
            return False

        if self.is_table_empty("mult"):
            # Assign defaults to multiple channels globals:
            self.gutils.fill_empty_mult_globals()

        mult_sql = """SELECT * FROM mult;"""
        head = self.execute(mult_sql).fetchone()
        mults = []

        channel_group = self.parser.channel_group
        # Check if there is any multiple channel cells defined.
        if not self.is_table_empty("mult_cells"):
            try:
                # Multiple Channels (not simplified):
                mult_cell_sql = """SELECT grid_fid, wdr, dm, nodchns, xnmult FROM mult_cells ORDER BY grid_fid ;"""
                line1 = " {}" * 8 + "\n"
                line2 = " {}" * 5 + "\n"

                channel_group.create_dataset('Mult', [])

                channel_group.datasets["Mult"].data.append(create_array(line1, 8, head[1:]))
                # m.write(line1.format(*head[1:]).replace("None", ""))

                mult_cells = self.execute(mult_cell_sql).fetchall()

                seen = set()
                for a, b, c, d, e in mult_cells:
                    if not a in seen:
                        seen.add(a)
                        mults.append((a, b, c, d, e))

                for row in mults:
                    vals = [x if x is not None else "" for x in row]
                    channel_group.datasets["Mult"].data.append(create_array(line2, 8, tuple(vals)))
                    # m.write(line2.format(*vals))

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error("ERROR 101218.1611: exporting MULT.DAT failed!.\n", e)
                return False

        if not self.is_table_empty("simple_mult_cells"):
            try:
                # Simplified Multiple Channels:
                simple_mult_cell_sql = """SELECT DISTINCT grid_fid FROM simple_mult_cells ORDER BY grid_fid;"""
                line1 = "{}" + "\n"
                line2 = "{}" + "\n"

                isany = self.execute(simple_mult_cell_sql).fetchone()
                if isany:
                    channel_group.create_dataset('Simple Mult', [])
                    repeats = ""

                    channel_group.datasets["Simple Mult"].data.append(create_array(line1, 1, head[9]))
                    # sm.write(line1.format(head[9]))
                    for row in self.execute(simple_mult_cell_sql):
                        # See if grid number in row is any grid element in mults:
                        if [item for item in mults if item[0] == row[0]]:
                            repeats += str(row[0]) + "  "
                        else:
                            vals = [x if x is not None else "" for x in row]
                            channel_group.datasets["Simple Mult"].data.append(create_array(line2, 1, tuple(vals)))
                            # sm.write(line2.format(*vals))
                if repeats:
                    self.uc.log_info("Cells repeated in simple mult cells: " + repeats)
                self.parser.write_groups(channel_group)
                return True

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error("ERROR 101218.1611: exporting SIMPLE_MULT.DAT failed!.\n", e)
                return False

        return rtrn

    def export_mult_dat(self, outdir):
        rtrn = True
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
                mult_cell_sql = """SELECT grid_fid, wdr, dm, nodchns, xnmult FROM mult_cells ORDER BY grid_fid ;"""
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
                simple_mult_cell_sql = """SELECT DISTINCT grid_fid FROM simple_mult_cells ORDER BY grid_fid;"""
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
                return True

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error("ERROR 101218.1611: exporting SIMPLE_MULT.DAT failed!.\n", e)
                return False

        return rtrn

    def export_tolspatial(self, outdir):
        # check if there is any tolerance data defined.
        try:
            if self.is_table_empty("tolspatial"):
                return False
            tol_poly_sql = """SELECT fid, tol FROM tolspatial ORDER BY fid;"""
            tol_cells_sql = """SELECT grid_fid FROM tolspatial_cells WHERE area_fid = ? ORDER BY grid_fid;"""

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

    def export_gutter(self, outdir):
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

    def export_sed(self, outdir):
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
            cells_d_sql = """SELECT grid_fid FROM mud_cells WHERE area_fid = ? ORDER BY grid_fid;"""
            cells_r_sql = """SELECT grid_fid FROM sed_rigid_cells ORDER BY grid_fid;"""
            areas_s_sql = """SELECT fid, dist_fid, isedcfp, ased, bsed FROM sed_supply_areas ORDER BY dist_fid;"""
            cells_s_sql = """SELECT grid_fid FROM sed_supply_cells WHERE area_fid = ?;"""
            data_n_sql = (
                """SELECT ssediam, ssedpercent FROM sed_supply_frac_data WHERE dist_fid = ? ORDER BY ssedpercent;"""
            )
            areas_g_sql = """SELECT fid, group_fid FROM sed_group_areas ORDER BY fid;"""
            cells_g_sql = """SELECT grid_fid FROM sed_group_cells WHERE area_fid = ? ORDER BY grid_fid;"""

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
                            gid = self.execute(cells_d_sql, (aid,)).fetchone()[0]
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
                        gid = self.execute(cells_s_sql, (aid,)).fetchone()[0]
                        s.write(line8.format(gid, *row[2:]))
                        for nrow in self.execute(data_n_sql, (dist_fid,)):
                            s.write(line9.format(*nrow))

                    areas_g = self.execute(areas_g_sql)
                    if areas_g:
                        for aid, group_fid in areas_g:
                            gids = self.execute(cells_g_sql, (aid,)).fetchall()
                            if gids:
                                for g in gids:
                                    s.write(line10.format(g[0], group_fid))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1612: exporting SED.DAT failed!.\n", e)
            return False

    def export_levee(self, output=None):
        if self.parsed_format == self.FORMAT_DAT:
            return self.export_levee_dat(output)
        elif self.parsed_format == self.FORMAT_HDF5:
            return self.export_levee_hdf5()

    def export_levee_hdf5(self):
        """
        Function to export levee data to HDF5 file
        """
        # check if there are any levees defined.
        # try:
        if self.is_table_empty("levee_data"):
            return False
        levee_gen_sql = """SELECT raiselev, ilevfail, gfragchar, gfragprob FROM levee_general;"""
        levee_data_sql = """SELECT grid_fid, ldir, levcrest FROM levee_data ORDER BY grid_fid, fid;"""
        levee_fail_sql = """SELECT * FROM levee_failure ORDER BY grid_fid, fid;"""
        levee_frag_sql = """SELECT grid_fid, levfragchar, levfragprob FROM levee_fragility ORDER BY grid_fid;"""

        line1 = "{0}  {1}\n"
        line2 = "L  {0}\n"
        line3 = "D  {0}  {1}\n"
        line4 = "F  {0}\n"
        line5 = "W  {0}  {1}  {2}  {3}  {4}  {5}  {6}\n"
        line6 = "C  {0}  {1}\n"
        line7 = "P  {0}  {1}  {2}\n"

        general = self.execute(levee_gen_sql).fetchone()
        if general is None:
            # TODO: Need to implement correct export for levee_general, levee_failure and levee_fragility
            general = (0, 0, None, None)
        head = general[:2]
        glob_frag = general[2:]

        levee_group = self.parser.levee_group
        levee_group.create_dataset('Levee', [])

        levee_group.datasets["Levee"].data.append(create_array(line1, 8, head))
        levee_rows = groupby(self.execute(levee_data_sql), key=itemgetter(0))
        for gid, directions in levee_rows:
            levee_group.datasets["Levee"].data.append(create_array(line2, 8, gid))
            for row in directions:
                levee_group.datasets["Levee"].data.append(create_array(line3, 8, row[1:]))
        if head[1] == 1:
            fail_rows = groupby(self.execute(levee_fail_sql), key=itemgetter(1))
            for gid, directions in fail_rows:
                levee_group.datasets["Levee"].data.append(create_array(line4, 8, gid))
                for row in directions:
                    rowl = list(row)
                    for i in range(0, len(rowl)):
                        rowl[i] = rowl[i] if rowl[i] is not None else 0
                        rowl[i] = rowl[i] if rowl[i] != "None" else 0
                    row = tuple(rowl)
                    levee_group.datasets["Levee"].data.append(create_array(line5, 8, row[2:]))
        if None not in glob_frag:
            levee_group.datasets["Levee"].data.append(create_array(line6, 8, glob_frag))
        else:
            pass
        for row in self.execute(levee_frag_sql):
            levee_group.datasets["Levee"].data.append(create_array(line7, 8, row))

        self.parser.write_groups(levee_group)
        return True

        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error("ERROR 101218.1614: exporting LEVEE.DAT failed!.\n", e)
        #     return False

    def export_levee_dat(self, outdir):
        # check if there are any levees defined.
        try:
            if self.is_table_empty("levee_data"):
                return False
            levee_gen_sql = """SELECT raiselev, ilevfail, gfragchar, gfragprob FROM levee_general;"""
            levee_data_sql = """SELECT grid_fid, ldir, levcrest FROM levee_data ORDER BY grid_fid, fid;"""
            levee_fail_sql = """SELECT * FROM levee_failure ORDER BY grid_fid, fid;"""
            levee_frag_sql = """SELECT grid_fid, levfragchar, levfragprob FROM levee_fragility ORDER BY grid_fid;"""

            line1 = "{0}  {1}\n"
            line2 = "L  {0}\n"
            line3 = "D  {0}  {1}\n"
            line4 = "F  {0}\n"
            line5 = "W  {0}  {1}  {2}  {3}  {4}  {5}  {6}\n"
            line6 = "C  {0}  {1}\n"
            line7 = "P  {0}  {1}  {2}\n"

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
            self.uc.show_error("ERROR 101218.1614: exporting LEVEE.DAT failed!.\n", e)
            return False

    def export_fpxsec(self, outdir):
        # check if there are any floodplain cross section defined.
        try:
            if self.is_table_empty("fpxsec"):
                return False
            cont_sql = """SELECT name, value FROM cont WHERE name = 'NXPRT';"""
            fpxsec_sql = """SELECT fid, iflo, nnxsec FROM fpxsec ORDER BY fid;"""
            cell_sql = """SELECT grid_fid FROM fpxsec_cells WHERE fpxsec_fid = ? ORDER BY grid_fid;"""

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
                    grids = self.execute(cell_sql, (fid,))
                    grids_txt = " ".join(["{}".format(x[0]) for x in grids])
                    f.write(line2.format(iflo, nnxsec, grids_txt))

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
        Function to export brach data to hdf5
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

            levee_group = self.parser.levee_group
            levee_group.create_dataset('Breach', [])

            c = 1

            for row in global_rows:
                # Write 'B1' line (general variables):
                row_slice = [str(x) if x is not None else "" for x in row[b1]]
                levee_group.datasets["Breach"].data.append(create_array(bline, 10, c, " ".join(row_slice)))

                # Write G1,G2,G3,G4 lines if 'Use Global Data' checkbox is selected in Global Breach Data dialog:
                if not local_rows:
                    if row[5] == 1:  # useglobaldata
                        for gslice, dslice, line in parts:
                            row_slice = [str(x) if x is not None else "" for x in row[gslice]]
                            if any(row_slice) is True:
                                levee_group.datasets["Breach"].data.append(create_array(line, 10, "G", "  ".join(row_slice)))
                            else:
                                pass

            c += 1

            for row in local_rows:
                fid = row[0]
                gid = self.execute(cells_sql, (fid,)).fetchone()[0]
                row_slice = [str(x) if x is not None else "" for x in row[b2]]
                row_slice[0] = str(gid)
                row_slice[1] = str(int(row_slice[1]))
                levee_group.datasets["Breach"].data.append(create_array(bline, 10, c, " ".join(row_slice)))
                for gslice, dslice, line in parts:
                    row_slice = [str(x) if x is not None else "" for x in row[dslice]]
                    if any(row_slice) is True:
                        levee_group.datasets["Breach"].data.append(create_array(line, 10, "D", "  ".join(row_slice)))
                    else:
                        pass
            c += 1

            for row in fragility_rows:
                levee_group.datasets["Breach"].data.append(create_array(fline, 10, row))

            self.parser.write_groups(levee_group)
            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1616: exporting BREACH.DAT failed!.\n", e)
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

    def export_fpfroude(self, outdir):
        # check if there is any limiting Froude number defined.
        try:
            if self.is_table_empty("fpfroude"):
                return False
            fpfroude_sql = """SELECT fid, froudefp FROM fpfroude ORDER BY fid;"""
            cell_sql = """SELECT grid_fid FROM fpfroude_cells WHERE area_fid = ? ORDER BY grid_fid;"""

            line1 = "F {0} {1}\n"

            fpfroude_rows = self.execute(fpfroude_sql).fetchall()
            if not fpfroude_rows:
                return False
            else:
                pass
            fpfroude_dat = os.path.join(outdir, "FPFROUDE.DAT")
            with open(fpfroude_dat, "w") as f:
                for fid, froudefp in fpfroude_rows:
                    for row in self.execute(cell_sql, (fid,)):
                        gid = row[0]
                        f.write(line1.format(gid, froudefp))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1617: exporting FPFROUDE.DAT failed!.\n", e)
            return False

    def export_shallowNSpatial(self, outdir):
        # check if there is any shallow-n defined.
        try:
            if self.is_table_empty("spatialshallow"):
                return False
            shallow_sql = """SELECT fid, shallow_n FROM spatialshallow ORDER BY fid;"""
            cell_sql = """SELECT grid_fid FROM spatialshallow_cells WHERE area_fid = ? ORDER BY grid_fid;"""

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

    def export_swmmflo(self, outdir):
        # check if there is any SWMM data defined.
        try:
            if self.is_table_empty("swmmflo"):
                return False
            # swmmflo_sql = '''SELECT swmmchar, swmm_jt, swmm_iden, intype, swmm_length, swmm_width, swmm_height, swmm_coeff, flapgate, curbheight
            #                  FROM swmmflo ORDER BY fid;'''

            swmmflo_sql = """SELECT swmmchar, swmm_jt, swmm_iden, intype, swmm_length, swmm_width, 
                                    swmm_height, swmm_coeff, swmm_feature, curbheight
                             FROM swmmflo ORDER BY fid;"""
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
                            self.uc.bar_warn("WARNING: invalid grid number in 'swmmflo' (Storm Drain. SD Inlets) layer !")  
                        else:
                            s.write(line1.format(*new_row))

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1618: exporting SWMMFLO.DAT failed!.\n", e)
            return False

    def export_swmmflort(self, outdir):
        # check if there is any SWMM rating data defined.
        try:
            if self.is_table_empty("swmmflort") and self.is_table_empty("swmmflo_culvert"):
                if os.path.isfile(outdir + r"\SWMMFLORT.DAT"):
                    m = "* There are no SWMM Rating Tables or Culvert Equations defined in the project, but there is\n"
                    m += "an old SWMMFLORT.DAT in the project directory\n  " + outdir + "\n\n"
                    self.export_messages += m
                    return False

            swmmflort_sql = "SELECT fid, grid_fid, name FROM swmmflort ORDER BY grid_fid;"
            data_sql = "SELECT depth, q FROM swmmflort_data WHERE swmm_rt_fid = ? ORDER BY depth;"
            #             line1 = 'D {0}\n'
            line1 = "D {0}  {1}\n"
            line2 = "N {0}  {1}\n"
            errors = ""
            swmmflort_rows = self.execute(swmmflort_sql).fetchall()
            if not swmmflort_rows and self.is_table_empty("swmmflo_culvert") :
                return False
            else:
                pass
            swmmflort = os.path.join(outdir, "SWMMFLORT.DAT")
            error_mentioned = False
            with open(swmmflort, "w") as s:
                for fid, gid, rtname in swmmflort_rows:
                    rtname = rtname.strip()
                    if gid is not None:
                        if str(gid).strip() != "":
                            if rtname is None or rtname == "":
                                errors += "* Grid element " + str(gid) + " has an empty rating table name.\n"
                            else:
                                inlet_type_qry = "SELECT intype FROM swmmflo WHERE swmm_jt = ?;"
                                inlet_type = self.execute(inlet_type_qry, (gid,)).fetchall()
                                if inlet_type is not None:
                                    # TODO: there may be more than one record. Why? Some may have intype = 4.
                                    if len(inlet_type) > 1:
                                        errors += "* Grid element " + str(gid) + " has has more than one inlet.\n"
                                    # See if there is a type 4:
                                    inlet_type_qry2 = "SELECT intype FROM swmmflo WHERE swmm_jt = ? AND intype = '4';"
                                    inlet_type = self.execute(inlet_type_qry2, (gid,)).fetchone()
                                    if inlet_type is not None:
                                        rows = self.execute(data_sql, (fid,)).fetchone()
                                        if not rows:
                                            inlet_name = self.execute(
                                                "SELECT name FROM user_swmm_nodes WHERE grid = ?;",
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
                                            if not self.gutils.is_table_empty("user_swmm_nodes"):
                                                inlet_name = self.execute(
                                                    "SELECT name FROM user_swmm_nodes WHERE grid = ?;",
                                                    (gid,),
                                                ).fetchone()
                                                if inlet_name != None:
                                                    if inlet_name[0] != "":
                                                        s.write(line1.format(gid, inlet_name[0]))
                                                        # s.write(line1.format(gid))
                                                        # s.write(line1.format(gid, rtname, inlet_name[0]))
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
                                                    errors += "Storm Drain Nodes layer in User Layers is empty.\nSWMMFLORT.DAT may be incomplete!"
                                                    error_mentioned = True
                    else:
                        errors += "* Unknown grid element in Rating Table.\n"                                   
                culverts = self.gutils.execute(
                    "SELECT grid_fid, name, cdiameter, typec, typeen, cubase, multbarrels FROM swmmflo_culvert ORDER BY fid;"
                ).fetchall()
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
                                "F " + str(typec) + " " + str(typeen) + " " + str(cubase) + " " + str(multbarrels) + "\n"
                            )
                        else:
                            if name:
                                errors += "* Unknown grid element for Culverts eq. " + name +".\n"
                            else:    
                                errors += "* Unknown grid element in Culverts eq. table.\n"
            if errors:
                QApplication.restoreOverrideCursor()
                self.uc.show_info("WARNING 040319.0521:\n\n" + errors)
                QApplication.setOverrideCursor(Qt.WaitCursor)

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 101218.1619: exporting SWMMFLORT.DAT failed!.\n", e)
            return False

    def export_swmmoutf(self, outdir):
        # check if there is any SWMM data defined.
        try:
            if self.is_table_empty("swmmoutf"):
                return False
            swmmoutf_sql = """SELECT name, grid_fid, outf_flo FROM swmmoutf ORDER BY fid;"""

            line1 = "{0}  {1}  {2}\n"

            swmmoutf_rows = self.execute(swmmoutf_sql).fetchall()
            if not swmmoutf_rows:
                return False
            else:
                pass
            swmmoutf = os.path.join(outdir, "SWMMOUTF.DAT")
            with open(swmmoutf, "w") as s:
                for row in swmmoutf_rows:
                    s.write(line1.format(*row))

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

