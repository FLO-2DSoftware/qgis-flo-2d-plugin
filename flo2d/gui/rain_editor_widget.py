# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import traceback
from datetime import datetime
from math import isnan

from PyQt5.QtWidgets import QProgressDialog
from qgis.core import QgsProject
from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices, QStandardItem, QStandardItemModel

from .dlg_sampling_raincellraw import SamplingRaincellRawDialog
from ..flo2d_ie.flo2dgeopackage import Flo2dGeoPackage
from ..flo2d_ie.rainfall_io import ASCProcessor, HDFProcessor, NetCDFProcessor, TIFProcessor
from ..flo2dobjects import Rain
from ..geopackage_utils import GeoPackageUtils
from ..gui.dlg_sampling_rain import SamplingRainDialog
from ..user_communication import UserCommunication
from ..utils import is_number, m_fdata, get_flo2dpro_release_date, second_smallest, set_min_max_elevs
from .table_editor_widget import CommandItemEdit, StandardItem, StandardItemModel
from .ui_utils import load_ui, set_icon, try_disconnect

uiDialog, qtBaseClass = load_ui("rain_editor")


class RainEditorWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.con = None
        self.setupUi(self)
        self.lyrs = lyrs
        self.plot = plot
        self.plot_item_name = None
        self.table = table
        self.tview = table.tview
        self.rain = None
        self.gutils = None
        self.uc = UserCommunication(iface, "FLO-2D")
        self.rain_data_model = StandardItemModel()
        self.rain_tseries_data = None

        self.d1, self.d2 = [[], []]

        set_icon(self.raster_rain_btn, "sample_rain.svg")
        set_icon(self.show_table_btn, "show_cont_table.svg")
        set_icon(self.remove_tseries_btn, "mActionDeleteSelected.svg")
        set_icon(self.add_tseries_btn, "mActionAddRainTimeSeries.svg")
        set_icon(self.add_predefined_tseries_btn, "mActionOpenFile.svg")
        set_icon(self.rename_tseries_btn, "change_name.svg")

        self.control_lyr = self.lyrs.data["cont"]["qlyr"]
        # self.grid = self.lyrs.data["grid"]["qlyr"]
        # self.raincell_data = self.lyrs.data["raincell_data"]["qlyr"]

        self.table.before_paste.connect(self.block_saving)
        self.table.after_paste.connect(self.unblock_saving)
        self.table.after_delete.connect(self.populate_tseries_data)

    def block_saving(self):
        try_disconnect(self.rain_data_model.dataChanged, self.save_tseries_data)

    def unblock_saving(self):
        self.rain_data_model.dataChanged.connect(self.save_tseries_data)

    def itemDataChangedSlot(self, item, oldValue, newValue, role, save=True):
        """
        Slot used to push changes of existing items onto undoStack.
        """
        if role == Qt.EditRole:
            command = CommandItemEdit(
                self,
                item,
                oldValue,
                newValue,
                "Text changed from '{0}' to '{1}'".format(oldValue, newValue),
            )
            self.tview.undoStack.push(command)
            return True

    def connect_signals(self):
        self.realtime_btn.clicked.connect(self.import_rainfall)
        self.delete_realtime_rainfall_btn.clicked.connect(self.delete_realtime_rainfall)
        self.tseries_cbo.currentIndexChanged.connect(self.populate_tseries_data)
        self.simulate_rain_grp.toggled.connect(self.set_rain)
        self.realtime_rainfall_grp.toggled.connect(self.set_realtime)
        self.building_chbox.stateChanged.connect(self.set_building)
        self.rain_help_btn.clicked.connect(self.rain_help)
        self.spatial_variation_grp.toggled.connect(self.set_arf)
        self.moving_storm_grp.toggled.connect(self.set_moving_storm)
        self.moving_storm_speed_dbox.editingFinished.connect(self.set_moving_storm_speed)
        self.rainfall_time_distribution_grp.toggled.connect(self.set_time_series_fid)
        self.realtime_raw_btn.clicked.connect(self.import_raincellraw)
        self.realtime_rainfall_raw_grp.toggled.connect(self.set_realtime_raw)
        self.delete_realtime_rainfall_raw_btn.clicked.connect(self.delete_realtime_raw_rainfall)

        self.n_radio.clicked.connect(self.set_n_radio)
        self.e_radio.clicked.connect(self.set_e_radio)
        self.s_radio.clicked.connect(self.set_s_radio)
        self.w_radio.clicked.connect(self.set_w_radio)
        self.ne_radio.clicked.connect(self.set_ne_radio)
        self.se_radio.clicked.connect(self.set_se_radio)
        self.sw_radio.clicked.connect(self.set_sw_radio)
        self.nw_radio.clicked.connect(self.set_nw_radio)

        self.raster_rain_btn.clicked.connect(self.raster_rain)

        self.total_rainfall_sbox.editingFinished.connect(self.set_tot_rainfall)
        self.rainfall_abst_sbox.editingFinished.connect(self.set_rainfall_abst)
        self.show_table_btn.clicked.connect(self.populate_tseries_data)
        self.add_tseries_btn.clicked.connect(self.add_tseries)
        self.add_predefined_tseries_btn.clicked.connect(self.add_predefined_tseries)
        self.remove_tseries_btn.clicked.connect(self.delete_tseries)
        self.rename_tseries_btn.clicked.connect(self.rename_tseries)
        self.rain_data_model.dataChanged.connect(self.save_tseries_data)
        self.rain_data_model.itemDataChanged.connect(self.itemDataChangedSlot)

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        self.con = con
        self.gutils = GeoPackageUtils(self.con, self.iface)

        # qry = '''SELECT movingstorm FROM rain;'''
        # row = self.gutils.execute(qry).fetchone()
        # if is_number(row[0]):
        #     if row[0] == '0':
        #         self.moving_storm_chbox.setChecked(False)
        #     else:
        #         self.moving_storm_chbox.setChecked(True)

        qry = """SELECT value FROM cont WHERE name = 'IRAIN';"""
        row = self.gutils.execute(qry).fetchone()
        if row:
            if is_number(row[0]):
                if row[0] == "0":
                    self.simulate_rain_grp.setChecked(False)
                else:
                    self.simulate_rain_grp.setChecked(True)

        self.rain = Rain(self.con, self.iface)
        self.control_lyr.editingStopped.connect(self.check_simulate_rainfall)

    def import_rainfall(self):
        s = QSettings()
        last_dir = s.value("FLO-2D/lastASC", "")

        head_qry = "INSERT INTO raincell (rainintime, irinters, timestamp) VALUES(?,?,?);"
        data_qry = ["""INSERT INTO raincell_data (time_interval, rrgrid, iraindum) VALUES""", 3]

        try:
            grid_lyr = self.lyrs.data["grid"]["qlyr"]

            realtime_file = QFileDialog.getOpenFileName(
                None,
                "Select Realtime Rainfall File",
                directory=last_dir,
                filter="Realtime Rainfall Files (*.asc *.tif *.tiff *.geotiff *.nc)")[0]

            if not realtime_file:
                return

            QApplication.setOverrideCursor(Qt.WaitCursor)

            s.setValue("FLO-2D/lastASC", os.path.dirname(realtime_file))

            extension = os.path.splitext(realtime_file)[1]

            if extension == ".asc":

                asc_dir = os.path.dirname(realtime_file)

                asc_processor = ASCProcessor(grid_lyr, asc_dir, self.iface)  # as_processor, an instance of the ASCProcessor class,
                self.gutils.clear_tables("raincell", "raincell_data")
                header = asc_processor.parse_rfc()
                time_step = float(header[0])
                irinters = int(header[1]) - 1
                self.gutils.execute(head_qry, header)
                time_interval = 0

                pd = QProgressDialog("Importing RealTime Rainfall...", None, 0, irinters)
                pd.setModal(True)
                pd.setValue(0)
                pd.show()
                i = 0

                for rain_series in asc_processor.rainfall_sampling():
                    pd.setValue(i)
                    for val, gid in rain_series:
                        data_qry += [(time_interval, gid, val)]
                    time_interval += time_step
                    i += 1

                self.gutils.batch_execute(data_qry)

                self.uc.bar_info("ASCII Realtime Rainfall imported successfully!")
                self.uc.log_info("ASCII Realtime Rainfall imported successfully!")

            if extension == ".nc":

                era_file = realtime_file

                try:

                    # 1. Create processor
                    netcdf_proc = NetCDFProcessor(grid_lyr, era_file, self.iface, self.gutils)

                    # 2. Read header for raincell table
                    header = netcdf_proc.parse_header()  # [interval_time, num_intervals, start_timestamp]
                    time_step = float(header[0])
                    irinters = int(header[1]) - 1

                    # 3. Clear previous data
                    self.gutils.clear_tables("raincell", "raincell_data")

                    # 4. Insert raincell header
                    self.gutils.execute(head_qry, header)

                    # 5. Insert data
                    time_interval = 0
                    pd = QProgressDialog("Importing ERA5 Rainfall...", None, 0, irinters)
                    pd.setModal(True)
                    pd.setValue(0)
                    pd.show()

                    for timestep_data in netcdf_proc.sample_all():
                        pd.setValue(int(time_interval))
                        QApplication.processEvents()

                        for rainfall, fid in timestep_data:
                            data_qry += [(time_interval, fid, round(rainfall,4))]

                        time_interval += time_step

                    self.gutils.batch_execute(data_qry)

                    self.uc.bar_info("ERA5 Realtime Rainfall imported successfully!")
                    self.uc.log_info("ERA5 Realtime Rainfall imported successfully!")

                except ImportError as err:
                    return

            if extension in [".tif", ".tiff", ".geotiff"]:

                tif_dir = os.path.dirname(realtime_file)

                tif_processor = TIFProcessor(grid_lyr, tif_dir,
                                             self.iface)  # as_processor, an instance of the ASCProcessor class,
                self.gutils.clear_tables("raincell", "raincell_data")
                header = tif_processor.parse_rfc()
                time_step = float(header[0])
                irinters = int(header[1]) - 1
                self.gutils.execute(head_qry, header)
                time_interval = 0

                pd = QProgressDialog("Importing RealTime Rainfall...", None, 0, irinters)
                pd.setModal(True)
                pd.setValue(0)
                pd.show()
                i = 0

                for rain_series in tif_processor.rainfall_sampling():
                    pd.setValue(i)
                    for val, gid in rain_series:
                        data_qry += [(time_interval, gid, val)]
                    time_interval += time_step
                    i += 1

                self.gutils.batch_execute(data_qry)

                self.uc.bar_info("Raster Realtime Rainfall imported successfully!")
                self.uc.log_info("Raster Realtime Rainfall imported successfully!")

        except Exception as e:
                self.uc.log_info(traceback.format_exc())
                self.uc.bar_error("Importing Realtime Rainfall Data failed!")
                self.uc.log_info("Importing Realtime Rainfall Data failed!")

        finally:
            QApplication.restoreOverrideCursor()

    def import_raincellraw(self):
        """
        Function to load the dialog that processes the NEXRAD data into the raincellraw & flo2d_raincell tables.
        """
        if self.gutils.is_table_empty("user_model_boundary"):
            self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
            self.uc.log_info("There is no computational domain! Please digitize it before running tool.")
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            self.uc.log_info("There is no grid! Please create it before running tool.")
            return

        dlg = SamplingRaincellRawDialog(self.con, self.iface, self.lyrs)
        ok = dlg.exec_()
        if ok:
            dlg.process_raincellraw()
        else:
            return
        # try:
        #     QApplication.setOverrideCursor(Qt.WaitCursor)
        #     res = dlg.probe_roughness()
        #     QApplication.restoreOverrideCursor()
        #     if res:
        #         dlg.show_probing_result_info()
        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.log_info(traceback.format_exc())
        #     self.uc.show_warn("WARNING 060319.1710: Probing grid roughness failed! Please check your raster layer.")


    def create_plot(self):
        """
        Create initial plot.
        """
        self.plot.clear()
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)
        self.plot.plot.addLegend()

        self.plot_item_name = "Rain timeseries"
        self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))

    def check_simulate_rainfall(self):
        qry = """SELECT value FROM cont WHERE name = 'IRAIN';"""
        row = self.gutils.execute(qry).fetchone()
        if is_number(row[0]):
            if row[0] == "0":
                self.simulate_rain_grp.setChecked(False)
            else:
                self.simulate_rain_grp.setChecked(True)

    def rain_properties(self):
        if not self.rain:
            return

        row = self.rain.get_row()

        if row["movingstorm"] == 1:
            self.moving_storm_grp.setChecked(True)
        else:
            self.moving_storm_grp.setChecked(False)

        if self.gutils.get_cont_par("IRAIN") == "1":
            self.simulate_rain_grp.setChecked(True)
            self.populate_tseries()
            idx = self.tseries_cbo.findData(self.rain.series_fid)
            self.tseries_cbo.setCurrentIndex(idx)
            self.populate_tseries_data()
        else:
            self.simulate_rain_grp.setChecked(False)

        if row["irainreal"] == 1:
            if not self.gutils.is_table_empty("raincell_data"):
                self.realtime_rainfall_grp.setChecked(True)
            elif not self.gutils.is_table_empty("raincellraw"):
                self.realtime_rainfall_raw_grp.setChecked(True)
            else:
                self.realtime_rainfall_grp.setChecked(True)
                self.realtime_rainfall_raw_grp.setChecked(False)
        else:
            self.realtime_rainfall_grp.setChecked(False)
            self.realtime_rainfall_raw_grp.setChecked(False)

        if row["irainbuilding"] == 1:
            self.building_chbox.setChecked(True)
        else:
            self.building_chbox.setChecked(False)

        if row["irainarf"] == 1:
            self.spatial_variation_grp.setChecked(True)
        else:
            self.spatial_variation_grp.setChecked(False)

        if is_number(row["tot_rainfall"]):
            self.total_rainfall_sbox.setValue(float((row["tot_rainfall"])))
        else:
            self.total_rainfall_sbox.setValue(0)

        if is_number(row["rainabs"]):
            self.rainfall_abst_sbox.setValue(float(row["rainabs"]))
        else:
            self.rainfall_abst_sbox.setValue(0)

        if is_number(row["rainspeed"]):
            self.moving_storm_speed_dbox.setValue(float((row["rainspeed"])))
        else:
            self.moving_storm_speed_dbox.setValue(0)

        self.connect_signals()

    def populate_tseries(self):
        self.tseries_cbo.clear()
        for row in self.rain.get_time_series():
            ts_fid, name = [x if x is not None else "" for x in row]
            self.tseries_cbo.addItem(name, ts_fid)

    def add_tseries(self):
        if not self.rain:
            return
        rtn = self.rain.add_time_series()
        self.populate_tseries()
        if type(rtn) is str:
            newIdx = self.tseries_cbo.findText(rtn)
            if newIdx == -1:
                self.tseries_cbo.setCurrentIndex(self.tseries_cbo.count() - 1)
            else:
                self.tseries_cbo.setCurrentIndex(newIdx)
        self.populate_tseries_data()

    def add_predefined_tseries(self):
        self.uc.clear_bar_messages()
        s = QSettings()
        last_dir = s.value("FLO-2D/lastPredefinedSeriesDir", "")
        predefined_files, __ = QFileDialog.getOpenFileNames(
            None,
            "Select time series files to import data",
            directory=last_dir,
            filter="(*.DAT *.TXT)",
        )
        if not predefined_files:
            return
        s.setValue("FLO-2D/lastPredefinedSeriesDir", os.path.dirname(predefined_files[0]))
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if not self.rain:
                return
            for file in predefined_files:
                tail = os.path.splitext(os.path.basename(file))[0]
                self.rain.add_time_series(tail, True)
                self.read_predefined_tseries_data(file)
                self.populate_tseries()

            QApplication.restoreOverrideCursor()
            self.uc.show_info("Importing predefined time series finished!")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("Importing predefined time series failed! Please check your input data.")

    def read_predefined_tseries_data(self, file):
        tsd_sql = "INSERT INTO rain_time_series_data (series_fid, time, value) VALUES (?, ?, ?);"
        data = self.parse_timeseries(file)
        ts_list = []
        for item in data:
            ts_list.append((self.rain.series_fid, float(item[0]), float(item[1])))
        self.gutils.execute_many(tsd_sql, ts_list)

    def parse_timeseries(self, filename):
        par = self.single_parser(filename)
        data = [row for row in par]
        return data

    def single_parser(self, file):
        with open(file, "r") as f1:
            for line in f1:
                row = line.split()
                if row:
                    yield row

    def delete_tseries(self):
        if not self.rain:
            return
        self.rain.del_time_series()
        self.populate_tseries()

    def rename_tseries(self):
        if not self.rain:
            return
        new_name, ok = QInputDialog.getText(None, "Change timeseries name", "New name:")
        if not ok or not new_name:
            return
        if not self.tseries_cbo.findText(new_name) == -1:
            msg = "WARNING 060319.1725: Time series with name {} already exists in the database. Please, choose another name.".format(
                new_name
            )
            self.uc.show_warn(msg)
            self.uc.log_info(msg)
            return
        self.rain.set_time_series_data_name(new_name)
        self.populate_tseries()

    def populate_tseries_data(self):
        """
        Get current time series data, populate data table and create plot.
        """
        self.table.after_delete.disconnect()
        self.table.after_delete.connect(self.save_tseries_data)

        cur_ts_idx = self.tseries_cbo.currentIndex()
        cur_ts_fid = self.tseries_cbo.itemData(cur_ts_idx)
        self.rain.series_fid = cur_ts_fid
        self.rain_tseries_data = self.rain.get_time_series_data()
        if not self.rain_tseries_data:
            return
        self.create_plot()
        self.tview.undoStack.clear()
        self.tview.setModel(self.rain_data_model)
        self.rain_data_model.clear()
        self.rain_data_model.setHorizontalHeaderLabels(["Time", "% of Total Storm"])
        self.d1, self.d2 = [[], []]
        for row in self.rain_tseries_data:
            items = [StandardItem("{:.4f}".format(x)) if x is not None else StandardItem("") for x in row]
            self.rain_data_model.appendRow(items)
            self.d1.append(row[0] if not row[0] is None else float("NaN"))
            self.d2.append(row[1] if not row[1] is None else float("NaN"))
        rc = self.rain_data_model.rowCount()
        if rc < 500:
            for row in range(rc, 500 + 1):
                items = [StandardItem(x) for x in ("",) * 2]
                self.rain_data_model.appendRow(items)
        self.tview.horizontalHeader().setStretchLastSection(True)
        for col in range(2):
            self.tview.setColumnWidth(col, 100)
        for i in range(self.rain_data_model.rowCount()):
            self.tview.setRowHeight(i, 20)
        self.rain.set_row()  # Inserts or replaces values in table 'rain'
        self.update_plot()

    def save_tseries_data(self):
        """
        Get rain timeseries data and save them in gpkg.
        """
        self.update_plot()
        ts_data = []
        for i in range(self.rain_data_model.rowCount()):
            # save only rows with a number in the first column
            if is_number(m_fdata(self.rain_data_model, i, 0)) and not isnan(m_fdata(self.rain_data_model, i, 0)):
                ts_data.append(
                    (
                        self.rain.series_fid,
                        m_fdata(self.rain_data_model, i, 0),
                        m_fdata(self.rain_data_model, i, 1),
                    )
                )
            else:
                pass
        data_name = self.tseries_cbo.currentText()
        self.rain.set_time_series_data(data_name, ts_data)

    def update_plot(self):
        """
        When time series data for plot change, update the plot.
        """
        if not self.plot_item_name:
            return
        self.d1, self.d2 = [[], []]
        for i in range(self.rain_data_model.rowCount()):
            self.d1.append(m_fdata(self.rain_data_model, i, 0))
            self.d2.append(m_fdata(self.rain_data_model, i, 1))
        self.plot.update_item(self.plot_item_name, [self.d1, self.d2])

    def raster_rain(self):
        if self.gutils.is_table_empty("user_model_boundary"):
            self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        cell_size = self.get_cell_size()
        dlg = SamplingRainDialog(self.con, self.iface, self.lyrs, cell_size)
        ok = dlg.exec_()
        if ok:
            pass
        else:
            return
        try:
            if not self.gutils.is_table_empty("rain_arf_cells"):
                q = "There are some Rain ARF cells already defined in the database. Overwrite them?"
                if not self.uc.question(q):
                    return
                del_cells = "DELETE FROM rain_arf_cells;"
                self.gutils.execute(del_cells)

            QApplication.setOverrideCursor(Qt.WaitCursor)
            res = dlg.probe_rain()

            delete_null = """DELETE FROM rain_arf_cells WHERE arf IS NULL;"""
            self.gutils.execute(delete_null)
            QApplication.restoreOverrideCursor()
            msg = "Rain ARF sampling performed!.\n\n"
            msg += 'Data was stored in the "Rain ARF Cells" layer.\n'
            msg += "Each sampled cell was assigned a rainfall depth area reduction value.\n"
            msg += "They will be saved in the RAIN.DAT FLO-2D file as lines 5 if the\n"
            msg += '"Spatial Variation (Depth Area Reduction)" checkbox is toggled.'
            self.uc.show_info(msg)

        #             if res:
        #                 dlg.show_probing_result_info()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn("WARNING 060319.1726: Probing grid rain failed! Please check your raster layer.")

    def get_cell_size(self):
        """
        Get cell size from:
            - Computational Domain attr table (if defined, will be written to cont table)
            - cont table
            - ask user
        """
        bl = self.lyrs.data["user_model_boundary"]["qlyr"]
        bfeat = next(bl.getFeatures())
        if bfeat["cell_size"]:
            cs = int(bfeat["cell_size"])
            if cs <= 0:
                self.uc.show_warn(
                    "WARNING 060319.1727: Cell size must be positive. Change the feature attribute value in Computational Domain layer."
                )
                return None
            self.gutils.set_cont_par("CELLSIZE", cs)
        else:
            cs = self.gutils.get_cont_par("CELLSIZE")
            cs = None if cs == "" else cs
        if cs:
            if cs <= 0:
                self.uc.show_warn(
                    "WARNING 060319.1728: Cell size must be positive. Change the feature attribute value in Computational Domain layer or default cell size in the project settings."
                )
                return None
            return cs
        else:
            r, ok = QInputDialog.getDouble(
                None,
                "Grid Cell Size",
                "Enter grid element cell size",
                value=100,
                min=0.1,
                max=99999,
            )
            if ok:
                cs = r
                self.gutils.set_cont_par("CELLSIZE", cs)
            else:
                return None

    def set_rain(self):
        if not self.rain:
            return
        if self.simulate_rain_grp.isChecked():
            self.gutils.set_cont_par("IRAIN", 1)
            self.populate_tseries()
            idx = self.tseries_cbo.findData(self.rain.series_fid)
            self.tseries_cbo.setCurrentIndex(idx)
            self.populate_tseries_data()
        else:
            self.gutils.set_cont_par("IRAIN", 0)

    def set_realtime(self):
        if self.realtime_rainfall_grp.isChecked():
            self.realtime_rainfall_raw_grp.setChecked(False)
            if self.rain:
                self.rain.irainreal = True
                self.rain.set_row()
        else:
            if self.rain:
                self.rain.irainreal = False
                self.rain.set_row()

    def set_realtime_raw(self):
        if self.realtime_rainfall_raw_grp.isChecked():
            self.realtime_rainfall_grp.setChecked(False)
            if self.rain:
                self.rain.irainreal = True
                self.rain.set_row()
        else:
            if self.rain:
                self.rain.irainreal = False
                self.rain.set_row()

    def set_building(self):
        if not self.rain:
            return
        self.rain.irainbuilding = self.building_chbox.isChecked()
        self.rain.set_row()

    def rain_help(self):
        QDesktopServices.openUrl(QUrl("https://flo-2dsoftware.github.io/FLO-2D-Documentation/Plugin1000/widgets/rain-editor/Rain%20Editor.html"))        

    def set_arf(self):
        if not self.rain:
            return
        self.rain.irainarf = self.spatial_variation_grp.isChecked()
        self.rain.set_row()

    def set_time_series_fid(self):
        if not self.rain:
            return
        if not self.rainfall_time_distribution_grp.isChecked():
            self.rain.series_fid = ""
        else:
            cur_ts_idx = self.tseries_cbo.currentIndex()
            cur_ts_fid = self.tseries_cbo.itemData(cur_ts_idx)
            self.rain.series_fid = cur_ts_fid
        self.rain.set_row()

    def set_moving_storm(self):
        if not self.rain:
            return
        self.rain.movingstorm = self.moving_storm_grp.isChecked()
        self.rain.set_row()

    def set_moving_storm_speed(self):
        if not self.rain:
            return
        self.rain.rainspeed = self.moving_storm_speed_dbox.value()
        self.rain.set_row()

    def set_n_radio(self):
        if not self.rain:
            return
        self.rain.iraindir = 1
        self.rain.set_row()

    def set_e_radio(self):
        if not self.rain:
            return
        self.rain.iraindir = 2
        self.rain.set_row()

    def set_s_radio(self):
        if not self.rain:
            return
        self.rain.iraindir = 3
        self.rain.set_row()

    def set_w_radio(self):
        if not self.rain:
            return
        self.rain.iraindir = 4
        self.rain.set_row()

    def set_ne_radio(self):
        if not self.rain:
            return
        self.rain.iraindir = 5
        self.rain.set_row()

    def set_se_radio(self):
        if not self.rain:
            return
        self.rain.iraindir = 6
        self.rain.set_row()

    def set_sw_radio(self):
        if not self.rain:
            return
        self.rain.iraindir = 7
        self.rain.set_row()

    def set_nw_radio(self):
        if not self.rain:
            return
        self.rain.iraindir = 8
        self.rain.set_row()

    def set_tot_rainfall(self):
        if not self.rain:
            return
        self.rain.tot_rainfall = self.total_rainfall_sbox.value()
        self.rain.set_row()

    def set_rainfall_abst(self):
        if not self.rain:
            return
        self.rain.rainabs = self.rainfall_abst_sbox.value()
        self.rain.set_row()

    def delete_realtime_rainfall(self):
        """
        Delete all realtime rainfall data from the database.
        """
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.gutils.clear_tables("raincell", "raincell_data")
        self.uc.bar_info("Realtime Rainfall (RAINCELL.DAT) deleted successfully!")
        self.uc.log_info("Realtime Rainfall (RAINCELL.DAT) deleted successfully!")
        QApplication.restoreOverrideCursor()

    def delete_realtime_raw_rainfall(self):
        """
        Delete all realtime rainfall data from the database.
        """
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.gutils.clear_tables("raincell", "raincellraw", "flo2d_raincell")
        self.uc.bar_info("Realtime Rainfall (RAINCELLRAW.DAT) deleted successfully!")
        self.uc.log_info("Realtime Rainfall (RAINCELLRAW.DAT) deleted successfully!")
        QApplication.restoreOverrideCursor()

    def realtime_rainfall(self, fid):
        si = "inches" if self.gutils.get_cont_par("METRIC") in ["0", "0.0"] else "mm"

        # If not raincell_data table or empty, use raincellraw and flo2d_raincell
        if self.gutils.is_table_empty("raincell_data") and self.gutils.is_table_empty("raincellraw"):
            self.uc.bar_warn("Realtime Rainfall data does not exist in this project! Please, import it first.")
            self.uc.log_info("Realtime Rainfall data does not exist in this project! Please, import it first.")
            return

        if self.gutils.is_table_empty("raincell_data"):
            qry = f"""
            SELECT rr.r_time,
                   rr.rrgrid
            FROM 
                raincellraw AS rr
            JOIN 
                flo2d_raincell fr ON fr.nxrdgd = rr.nxrdgd
            WHERE 
                fr.iraindum=?
            ORDER 
                BY rr.r_time
            """
            header = ["Time", "Cumulative Realtime Rainfall"]
        else:
            qry = "SELECT (time_interval / 60), iraindum FROM raincell_data WHERE rrgrid=? ORDER BY time_interval;"
            header = ["Time", "Realtime Rainfall"]
        rainfall = self.gutils.execute(qry, (fid,))
        self.create_plot()
        self.tview.setModel(self.rain_data_model)
        self.rain_data_model.clear()
        self.rain_data_model.setHorizontalHeaderLabels(header)
        self.d1, self.d2 = [[], []]
        for row in rainfall:
            items = [QStandardItem("{:.4f}".format(x)) if x is not None else QStandardItem("") for x in row]
            self.rain_data_model.appendRow(items)
            self.d1.append(row[0] if not row[0] is None else float("NaN"))
            self.d2.append(row[1] if not row[1] is None else float("NaN"))
        rc = self.rain_data_model.rowCount()
        if rc < 500:
            for row in range(rc, 500 + 1):
                items = [QStandardItem(x) for x in ("",) * 2]
                self.rain_data_model.appendRow(items)
        self.tview.horizontalHeader().setStretchLastSection(True)
        for col in range(2):
            self.tview.setColumnWidth(col, 100)
        for i in range(self.rain_data_model.rowCount()):
            self.tview.setRowHeight(i, 20)
        self.plot.plot.setTitle("Grid - {}".format(fid))
        self.plot.plot.setLabel("bottom", text="Time (hours)")
        self.plot.plot.setLabel("left", text="Rainfall ({})".format(si))
        self.update_plot()
        self.plot.auto_range()
