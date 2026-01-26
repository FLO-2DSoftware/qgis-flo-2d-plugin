# -*- coding: utf-8 -*-
import math

from PyQt5.Qsci import QsciLexerHTML

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from .ui_utils import load_ui

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import numpy as np

uiDialog, qtBaseClass = load_ui("breach_hydrograph_tool")


class BreachHydrographToolDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = GeoPackageUtils(con, iface)

        self.check_dam_type()

        self.cancel_btn.clicked.connect(self.close_dialog)
        self.next_btn.clicked.connect(self.next_page)
        self.previous_btn.clicked.connect(self.previous_page)

        self.water_group.clicked.connect(self.check_dam_type)
        self.tailings_group.clicked.connect(self.check_dam_type)

        self.generate_breach_parameters_btn.clicked.connect(self.generate_breach_parameters)
        self.generate_hydrograph_btn.clicked.connect(self.generate_hydrograph)

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

        if peak_discharge is not None:
            self.peak_discharge_le.setText(str(round(peak_discharge, 2)))
        if time_to_peak is not None:
            self.time_to_peak_le.setText(str(round(time_to_peak, 2)))
        if ave_breach_width is not None:
            self.ave_breach_width_le.setText(str(round(ave_breach_width, 2)))

    def generate_hydrograph(self):
        """
        Function to generate breach hydrograph based on the calculated parameters.
        """

        t_hr, Qt = None, None

        peak_discharge = float(self.peak_discharge_le.text())
        time_to_peak = float(self.time_to_peak_le.text())
        baseflow = float(self.baseflow_dsb.value())
        ave_breach_width = float(self.ave_breach_width_le.text())
        dam_volume = self.dam_volume_dsb.value()

        if self.tr66_rb.isChecked():
            t_hr, Qt = self.tr66_hydrograph(peak_discharge, time_to_peak, dam_volume, baseflow)

        if self.parabolic_rb.isChecked():
            t_hr, Qt = self.ana_lnec_hydrograph(peak_discharge, time_to_peak, dam_volume, baseflow)



    def tr66_hydrograph(self, Qp, Tf, V, Qbase=0.0, dt_hr = 0.1):
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

        # Your total time estimate (seconds). 2*V/Qp is a reasonable first guess.
        T_total_s = 2.0 * V / Qp

        # Number of steps
        n_steps = int(np.floor(T_total_s / dt_s)) + 1

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

    def ana_lnec_hydrograph(self, Qp, Tf, V, Qbase=0.0, dt_hr=0.1, beta=10):
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

        T_total_s = 2.0 * V / Qp
        n_steps = int(np.floor(T_total_s / dt_s)) + 1

        t_s = np.arange(n_steps, dtype=float) * dt_s
        t_hr = t_s / 3600.0

        x = t_s / Tf_s
        core = x * np.exp(1.0 - x)
        core = np.maximum(core, 0.0)

        Qt = Qbase + Qp * (core ** beta)

        return t_hr, Qt









