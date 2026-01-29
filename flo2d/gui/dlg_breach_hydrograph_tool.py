# -*- coding: utf-8 -*-
import math

import processing
from PyQt5.QtWidgets import QListWidgetItem
from qgis._core import QgsProject, QgsWkbTypes, QgsVectorLayer, QgsFeature
from qgis.core import QgsMapLayerType

from ..flo2dobjects import Inflow
# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from .ui_utils import load_ui
from qgis.PyQt.QtCore import Qt, NULL

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import numpy as np

uiDialog, qtBaseClass = load_ui("breach_hydrograph_tool")


class BreachHydrographToolDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs, bc_editor):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.bc_editor = bc_editor
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = GeoPackageUtils(con, iface)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint)

        self.t_hr, self.Qt = None, None

        self.check_dam_type()

        self.cancel_btn.clicked.connect(self.close_dialog)
        self.next_btn.clicked.connect(self.next_page)
        self.previous_btn.clicked.connect(self.previous_page)

        self.water_group.clicked.connect(self.check_dam_type)
        self.tailings_group.clicked.connect(self.check_dam_type)

        self.generate_breach_parameters_btn.clicked.connect(self.generate_breach_parameters)
        self.generate_hydrograph_btn.clicked.connect(self.generate_hydrograph)
        self.create_cd_btn.clicked.connect(self.create_computational_domain)

        self.water_add_btn.clicked.connect(self.add_ts_to_inflow)

        self.populate_information()
        self.stackedWidget.currentChanged.connect(self.populate_information)

    def add_ts_to_inflow(self):
        """
        Function to add time series to selected inflow
        """
        if self.t_hr is None or self.Qt is None or len(self.t_hr) == 0 or len(self.Qt) == 0:
            self.uc.bar_warn("No hydrograph data to add. Please generate a hydrograph first.")
            self.uc.log_info("No hydrograph data to add. Please generate a hydrograph first.")
            return

        selected_inflow_name = self.water_inflow_cbo.currentText()

        inflow_qry = self.gutils.execute("SELECT fid, time_series_fid FROM inflow WHERE name = ?", (selected_inflow_name,)).fetchone()
        if inflow_qry:
            inflow_fid = inflow_qry[0]
            inflow = Inflow(inflow_fid, self.iface.f2d["con"], self.iface)

            time_series_fid = inflow_qry[1]
            if time_series_fid is None:
                ts_name = f"Time Series {inflow_fid}"
                inflow.add_time_series(name=ts_name)
                time_series_fid = self.gutils.execute("SELECT fid FROM inflow_time_series WHERE name = ?", (ts_name,)).fetchone()[0]
            else:
                ts_name = self.gutils.execute("SELECT name FROM inflow_time_series WHERE fid = ?", (time_series_fid,)).fetchone()[0]
        else:
            return

        ts_data = []
        for t, q in zip(self.t_hr, self.Qt):
            ts_data.append((time_series_fid, round(float(t), 2), round(float(q), 2), None))

        inflow.time_series_fid = time_series_fid
        inflow.set_time_series_data(ts_name, ts_data)

        self.bc_editor.inflow_changed()

    def populate_information(self):
        """
        Function to populate information based on the current page
        """
        self.populate_user_channel()
        self.populate_user_inflow()

    def populate_user_inflow(self):
        """
        Function to populate user inflow combo box
        """
        all_inflows = self.gutils.get_inflows_list()
        if not all_inflows:
            return
        for i, row in enumerate(all_inflows):
            row = [x if x is not None else "" for x in row]
            fid, name, geom_type, ts_fid = row
            if not name:
                name = "Inflow {}".format(fid)
            self.water_inflow_cbo.addItem(name)

    def create_computational_domain(self):
        """
        Function to create computational domain from user channel
        """
        selected_layer_name = self.user_channel_cb.currentText()
        selected_layer = None

        buffer = self.buffer_dsb.value()
        if buffer <= 0:
            self.uc.bar_warn("Buffer distance must be greater than zero.")
            self.uc.log_info("Buffer distance must be greater than zero.")
            return

        empty = self.gutils.is_table_empty("user_model_boundary")
        # check if a grid exists in the grid table
        if not empty:
            q = "There is a computational domain already defined in GeoPackage. Overwrite it?"
            if self.uc.question(q):
                self.gutils.clear_tables("user_model_boundary", "grid")
            else:
                self.uc.bar_info("Creation of computational domain canceled!")
                self.uc.log_info("Creation of computational domain canceled!")
                return

        for l in QgsProject.instance().mapLayers().values():
            if l.name() == selected_layer_name:
                selected_layer = l
                break

        if selected_layer is None:
            self.uc.bar_error("Selected layer not found.")
            self.uc.log_info("Selected layer not found.")
            return

        params = {
            "INPUT": selected_layer,
            "DISTANCE": buffer,
            "SEGMENTS": 5,
            "END_CAP_STYLE": 1,
            "JOIN_STYLE": 0,
            "MITER_LIMIT": 2,
            "DISSOLVE": True,
            "SEPARATE_DISJOINT": False,
            "OUTPUT": "TEMPORARY_OUTPUT",
        }
        tmp = processing.run("native:buffer", params)["OUTPUT"]

        bl = self.lyrs.data["user_model_boundary"]["qlyr"]

        bl.startEditing()

        for f in tmp.getFeatures():
            new_f = QgsFeature(bl.fields())
            new_f.setGeometry(f.geometry())
            bl.addFeature(new_f)

        bl.commitChanges()

        cellSize = float(self.gutils.get_cont_par("CELLSIZE"))
        self.gutils.execute("UPDATE user_model_boundary SET cell_size = ?", (cellSize,))

        bl.triggerRepaint()

    def populate_user_channel(self):
        """
        Function to populate user channel combo box
        """
        self.user_channel_cb.clear()

        user_layers = []
        gpkg_path = self.gutils.get_gpkg_path()
        gpkg_path_adj = gpkg_path.replace("\\", "/")

        for l in QgsProject.instance().mapLayers().values():
            layer_source_adj = l.source().replace("\\", "/")
            if gpkg_path_adj not in layer_source_adj:
                if l.type() == QgsMapLayerType.VectorLayer:
                    geom_type = l.geometryType()

                    # Check against the line geometry types
                    if geom_type == QgsWkbTypes.LineGeometry:
                        user_layers.append(l)

        items = [f'{i.name()}' for i in user_layers]
        for s in items:
            self.user_channel_cb.addItem(s)

    def next_page(self):
        """
        Move to the next page based on the selected mode (water or tailings).
        """
        current = self.stackedWidget.currentIndex()
        max_index = self.stackedWidget.count() - 1
        if current >= max_index:
            return

        # Define allowed pages for each mode
        if self.water_group.isChecked():
            allowed = [0, 2]
        elif self.tailings_group.isChecked():
            allowed = [0, 1, 3]
        else:
            return

        for p in allowed:
            if p > current:
                self.stackedWidget.setCurrentIndex(min(p, max_index))
                return

    def previous_page(self):
        """
        Move to the previous page based on the selected mode (water or tailings).
        """
        current = self.stackedWidget.currentIndex()
        if current <= 0:
            return

        if self.water_group.isChecked():
            allowed = [0, 2]
        elif self.tailings_group.isChecked():
            allowed = [0, 1, 3]
        else:
            return

        for p in reversed(allowed):
            if p < current:
                self.stackedWidget.setCurrentIndex(max(p, 0))
                return

    def close_dialog(self):
        """
        Function to close the dialog
        """
        self.close()

    def check_dam_type(self):
        """
        Function to check the selected dam type and adjust the UI accordingly.
        """

        if self.water_group.isChecked():
            self.tailings_group.blockSignals(True)
            self.tailings_group.setChecked(False)
            self.tailings_group.blockSignals(False)

            self.tailings_group.setEnabled(True)
            self.water_group.setEnabled(True)

        elif self.tailings_group.isChecked():
            self.water_group.blockSignals(True)
            self.water_group.setChecked(False)
            self.water_group.blockSignals(False)

            self.water_group.setEnabled(True)
            self.tailings_group.setEnabled(True)

    def generate_breach_parameters(self):
        """
        Function to generate breach parameters based on the selected method.
        """

        peak_discharge = None
        time_to_peak = None
        ave_breach_width = None
        hydrograph_length = None
        k = None
        g = 9.81 # TODO AJUSTAR

        dam_height = self.dam_height_dsb.value()
        dam_volume = self.dam_volume_dsb.value()
        failure_mechanism = self.failure_mechanism_cb.currentIndex()
        baseflow = self.baseflow_dsb.value()

        # if self.gutils.get_cont_par("METRIC") == "1":
        #     g = 9.81  # m/s2
        # else:
        #     g = 32.2  # ft/s2

        if self.froehlich_1995_rb.isChecked():
            peak_discharge = 0.607 * pow(dam_volume, 0.295) * pow(dam_height, 1.24)
            time_to_peak = 0.00254 * pow(dam_volume, 0.53) * pow(dam_height, -0.9)
            if failure_mechanism == 0:
                k = 1.4
            else:
                k = 1.0
            ave_breach_width = 0.1803 * k * pow(dam_volume, 0.32) * pow(dam_height, 0.19)

        if self.froehlich_2008_rb.isChecked():
            peak_discharge = 0.607 * pow(dam_volume, 0.295) * pow(dam_height, 1.24)
            time_to_peak = 0.0176 * pow((dam_volume / (g * pow(dam_height, 2))), 0.5)
            if failure_mechanism == 0:
                k = 1.3
            else:
                k = 1.0
            ave_breach_width = 0.27 * k * pow(dam_volume, 0.5)

        if self.mmc_rb.isChecked():
            peak_discharge = 0.0039042 * pow(dam_volume, 0.8122)
            ave_breach_width = 3 * dam_height
            time_to_peak = 0.011 * ave_breach_width

        if self.analnec_rb.isChecked():
            peak_discharge_1 = 0.607 * pow(dam_volume, 0.295) * pow(dam_height, 1.24)
            peak_discharge_2 = 0.0039 * pow(dam_volume, 0.8122)
            peak_discharge = max(peak_discharge_1, peak_discharge_2)
            time_to_peak = 0.00254 * pow(dam_volume, 0.53) * pow(dam_height, -0.9)
            if failure_mechanism == 0:
                k = 1.4
            else:
                k = 1.0
            ave_breach_width = 0.1803 * k * pow(dam_volume, 0.32) * pow(dam_height, 0.19)

        hydrograph_length = 2.0 * dam_volume / peak_discharge / 3600.0  # hours

        if peak_discharge is not None:
            self.peak_discharge_le.setText(str(round(peak_discharge, 2)))
        if time_to_peak is not None:
            self.time_to_peak_le.setText(str(round(time_to_peak, 2)))
        if ave_breach_width is not None:
            self.ave_breach_width_le.setText(str(round(ave_breach_width, 2)))
        if hydrograph_length is not None:
            self.hyd_length_le.setText(str(round(hydrograph_length, 2)))

    def generate_hydrograph(self):
        """
        Function to generate breach hydrograph based on the calculated parameters.
        """

        peak_discharge = float(self.peak_discharge_le.text())
        time_to_peak = float(self.time_to_peak_le.text())
        baseflow = float(self.baseflow_dsb.value())
        dam_volume = self.dam_volume_dsb.value()
        T_total = float(self.hyd_length_le.text())

        if self.tr66_rb.isChecked():
            self.t_hr, self.Qt = self.tr66_hydrograph(peak_discharge, time_to_peak, dam_volume, T_total, baseflow)

        if self.parabolic_rb.isChecked():
            self.t_hr, self.Qt = self.ana_lnec_hydrograph(peak_discharge, time_to_peak, T_total, baseflow)

        # --------------------------------------------------
        # Compute total volume under the hydrograph
        # --------------------------------------------------
        t_sec = np.asarray(self.t_hr) * 3600.0  # hours → seconds
        Qt = np.asarray(self.Qt)

        total_volume = np.trapz(Qt, t_sec)  # m³
        ratio = round(total_volume / dam_volume, 2)
        # --------------------------------------------------

        fig = Figure()
        ax = fig.add_subplot(111)
        ax.plot(self.t_hr, self.Qt)
        ax.set_xlabel('Time (hrs)')
        ax.set_ylabel('Discharge (m³/s)')
        ax.set_title(f'Total Volume = {total_volume:,.1f} m³ ({ratio})')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(False)

        canvas = FigureCanvas(fig)

        # Clear previous plot and add new one
        while self.verticalLayout.count():
            item = self.verticalLayout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        self.verticalLayout.addWidget(canvas)

    def tr66_hydrograph(self, Qp, Tf, V, T_total, Qbase=0.0, dt_hr = 0.1):
        """
       TR66 (SCS, 1981) hydrograph (as in your table).

       Parameters
       ----------
       Qp : float
           Peak discharge (m3/s).
       Tf : float
           Rising-limb time threshold (hours).
       V : float
           Volume (m3).
       Qbase : float
           Base flow (m3/s).
       dt_hr : float
           Time step in hours (default 0.1 hr).

       Returns
       -------
       t_hr : np.ndarray
           Time vector (hours).
       Qt : np.ndarray
           Discharge vector (m3/s).
       """
        if Qp <= 0:
            raise ValueError("Qp must be > 0.")
        if Tf <= 0:
            raise ValueError("Tf must be > 0.")
        if V <= 0:
            raise ValueError("V must be > 0.")
        if dt_hr <= 0:
            raise ValueError("dt_hr must be > 0.")

        # Convert hours to seconds internally to match V/Qp units (m3)/(m3/s) = s
        Tf_s = Tf * 3600.0
        dt_s = dt_hr * 3600.0

        T_total = T_total * 3600.0  # total time in seconds

        # Number of steps
        n_steps = int(np.floor(T_total / dt_s)) + 1

        # Time array in seconds and hours
        t_s = np.arange(n_steps, dtype=float) * dt_s
        t_hr = t_s / 3600.0

        # Build hydrograph
        Qt = np.empty_like(t_s)

        # Rising limb: t <= Tf
        mask_rise = t_s <= Tf_s
        Qt[mask_rise] = Qbase + Qp * (t_s[mask_rise] / Tf_s)

        # Falling limb: t > Tf
        mask_fall = ~mask_rise
        Qt[mask_fall] = Qbase + Qp * np.exp(-(t_s[mask_fall] - Tf_s) * (Qp / V))

        # Optional: clip any numerical negatives (can happen if Tp is large)
        Qt = np.maximum(Qt, 0.0)

        return t_hr, Qt

    def ana_lnec_hydrograph(self, Qp, Tf, T_total, Qbase=0.0, dt_hr=0.1, beta=10):
        """
        ANA LNEC Adaptado (Petry et al., 2018) hydrograph as in your table.

        Qt = Qbase + Qx * [ (t/tf) * exp(1 - t/tp) ]^beta

        Parameters
        ----------
        Qp : float
            Peak discharge (used to compute Qx).
        Tf : float
            Time to peak
        V : float
            Volume used to compute Qx (V > 0).
        Qbase : float
            Baseflow discharge.

        Returns
        -------
        t_hr : np.ndarray
           Time vector (hours).
        Qt : np.ndarray
           Discharge vector (m3/s).
        """

        Tf_s = Tf * 3600.0
        dt_s = dt_hr * 3600.0

        T_total = T_total * 3600.0  # total time in seconds

        n_steps = int(np.floor(T_total / dt_s)) + 1

        t_s = np.arange(n_steps, dtype=float) * dt_s
        t_hr = t_s / 3600.0

        x = t_s / Tf_s
        core = x * np.exp(1.0 - x)
        core = np.maximum(core, 0.0)

        Qt = Qbase + Qp * (core ** beta)

        return t_hr, Qt









