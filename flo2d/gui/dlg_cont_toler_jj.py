# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from collections import OrderedDict

from PyQt5.QtCore import QCoreApplication
from qgis.PyQt import QtCore
from qgis.PyQt.QtWidgets import QApplication, QCheckBox, QDoubleSpinBox, qApp

from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..utils import float_or_zero, old_IDEBRV
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("cont_toler_jj")

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:

    def _fromUtf8(s):
        return s


try:
    _encoding = QApplication.UnicodeUTF8

    def _translate(context, text, disambig):
        return QApplication.translate(context, text, disambig, _encoding)

except AttributeError:

    def _translate(context, text, disambig):
        return QApplication.translate(context, text, disambig)


class ContToler_JJ(qtBaseClass, uiDialog):
    PARAMS = OrderedDict(
        [
            [
                "AMANN",
                {
                    "label": "Increment n Value at runtime",
                    "type": "r",
                    "dat": "CONT",
                    "min": 0.00,
                    "max": float("inf"),
                    "dec": 2,
                },
            ],
            [
                "DEPTHDUR",
                {
                    "label": "Depth Duration",
                    "type": "r",
                    "dat": "CONT",
                    "min": 0,
                    "max": 100,
                    "dec": 3,
                },
            ],
            [
                "ENCROACH",
                {
                    "label": "Encroachment Analysis Depth",
                    "type": "r",
                    "dat": "CONT",
                    "min": 0,
                    "max": 10,
                    "dec": 1,
                },
            ],
            [
                "FROUDL",
                {
                    "label": "Global Limiting Froude",
                    "type": "r",
                    "dat": "CONT",
                    "min": 0,
                    "max": 5,
                    "dec": 2,
                },
            ],
            [
                "GRAPTIM",
                {
                    "label": "Graphical Update Interval",
                    "type": "r",
                    "dat": "CONT",
                    "min": 0.01,
                    "max": float("inf"),
                    "dec": 2,
                },
            ],
            ["IBACKUP", {"label": "Backup Switch", "type": "s2", "dat": "CONT"}],
            ["ICHANNEL", {"label": "Channel Switch", "type": "s", "dat": "CONT"}],
            ["IDEBRV", {"label": "Debris Switch", "type": "s", "dat": "CONT"}],
            ["IEVAP", {"label": "Evaporation Switch", "type": "s", "dat": "CONT"}],
            [
                "IFLOODWAY",
                {"label": "Floodway Analysis Switch", "type": "s", "dat": "CONT"},
            ],
            [
                "IHYDRSTRUCT",
                {"label": "Hydraulic Structure Switch", "type": "s", "dat": "CONT"},
            ],
            [
                "IMULTC",
                {"label": "Multiple Channel Switch", "type": "s", "dat": "CONT"},
            ],
            ["IMODFLOW", {"label": "Modflow Switch", "type": "s", "dat": "CONT"}],
            ["INFIL", {"label": "Infiltration Switch", "type": "s", "dat": "CONT"}],
            ["IRAIN", {"label": "Rain Switch", "type": "s", "dat": "CONT"}],
            [
                "ISED",
                {"label": "Sediment Transport Switch", "type": "s", "dat": "CONT"},
            ],
            [
                "ITIMTEP",
                {"label": "Time Series Selection Switch", "type": "s5", "dat": "CONT"},
            ],
            [
                "STARTIMTEP",
                {
                    "label": "Time Series Start Time",
                    "type": "r",
                    "dat": "CONT",
                    "min": 0.00,
                    "max": float("inf"),
                    "dec": 2,
                },
            ],
            [
                "ENDTIMTEP",
                {
                    "label": "Time Series End Time",
                    "type": "r",
                    "dat": "CONT",
                    "min": 0.00,
                    "max": float("inf"),
                    "dec": 2,
                },
            ],
            ["IWRFS", {"label": "Building Switch", "type": "s", "dat": "CONT"}],
            ["LEVEE", {"label": "Levee Switch", "type": "s", "dat": "CONT"}],
            ["LGPLOT", {"label": "Graphic Mode", "type": "s2", "dat": "CONT"}],
            ["METRIC", {"label": "Metric Switch", "type": "s", "dat": "CONT"}],
            ["MSTREET", {"label": "Street Switch", "type": "s", "dat": "CONT"}],
            ["MUD", {"label": "Mudflow Switch", "type": "s", "dat": "CONT"}],
            [
                "NOPRTC",
                {
                    "label": "Detailed Channel Output Options",
                    "type": "s2",
                    "dat": "CONT",
                    "min": 2,
                },
            ],
            [
                "NOPRTFP",
                {
                    "label": "Detailed Floodplain Output Options",
                    "type": "s3",
                    "dat": "CONT",
                    "min": 2,
                },
            ],
            [
                "SHALLOWN",
                {
                    "label": "Shallow n Value",
                    "type": "r",
                    "dat": "CONT",
                    "min": 0.00,
                    "max": 0.4,
                    "dec": 2,
                },
            ],
            [
                "SIMUL",
                {
                    "label": "Simulation Time",
                    "type": "r",
                    "dat": "CONT",
                    "min": 0.01,
                    "max": float("inf"),
                    "dec": 2,
                },
            ],
            [
                "DEPRESSDEPTH",
                {
                    "label": "Depress Depth",
                    "type": "r",
                    "dat": "CONT",
                    "min": 0.00,
                    "max": float("inf"),
                    "dec": 2,
                },
            ],
            ["SWMM", {"label": "Storm Drain Switch", "type": "s", "dat": "CONT"}],
            [
                "TIMTEP",
                {
                    "label": "Time Series Output Interval",
                    "type": "r",
                    "dat": "CONT",
                    "min": 0,
                    "max": 100,
                    "dec": 2,
                },
            ],
            [
                "TOUT",
                {
                    "label": "Output Data Interval",
                    "type": "r",
                    "dat": "CONT",
                    "min": 0,
                    "max": float("inf"),
                    "dec": 2,
                },
            ],
            [
                "XARF",
                {
                    "label": "Global Area Reduction",
                    "type": "r",
                    "dat": "CONT",
                    "min": 0,
                    "max": 1,
                    "dec": 2,
                },
            ],
            [
                "IARFBLOCKMOD",
                {
                    "label": "Global ARF=1 Revision",
                    "type": "r",
                    "dat": "CONT",
                    "min": 0,
                    "max": 1,
                    "dec": 2,
                },
            ],
            [
                "XCONC",
                {
                    "label": "Global Sediment Concentration",
                    "type": "r",
                    "dat": "CONT",
                    "min": 0,
                    "max": 0.50,
                    "dec": 2,
                },
            ],
            [
                "COURANTC",
                {
                    "label": "Courant Stability C",
                    "type": "r",
                    "dat": "TOLER",
                    "min": 0,
                    "max": 1,
                    "dec": 1,
                },
            ],
            [
                "COURANTFP",
                {
                    "label": "Courant Stability FP",
                    "type": "r",
                    "dat": "TOLER",
                    "min": 0,
                    "max": 1,
                    "dec": 1,
                },
            ],
            [
                "COURANTST",
                {
                    "label": "Courant Stability St",
                    "type": "r",
                    "dat": "TOLER",
                    "min": 0,
                    "max": 1,
                    "dec": 1,
                },
            ],
            [
                "COURCHAR_C",
                {"label": "Stability Line 2 Character", "type": "c", "dat": "TOLER"},
            ],
            [
                "COURCHAR_T",
                {"label": "Stability Line 3 Character", "type": "c", "dat": "TOLER"},
            ],
            [
                "DEPTOL",
                {
                    "label": "Percent Change in Depth",
                    "type": "r",
                    "dat": "TOLER",
                    "min": 0,
                    "max": 0.5,
                    "dec": 1,
                },
            ],
            [
                "TIME_ACCEL",
                {
                    "label": "Timestep Sensitivity",
                    "type": "r",
                    "dat": "TOLER",
                    "min": 0.1,
                    "max": 100,
                    "dec": 2,
                },
            ],
            [
                "TOLGLOBAL",
                {
                    "label": "Low flow exchange limit",
                    "type": "r",
                    "dat": "TOLER",
                    "min": 0.000,
                    "max": 0.5,
                    "dec": 4,
                },
            ],
            [
                "WAVEMAX",
                {
                    "label": "Wavemax Sensitivity",
                    "type": "r",
                    "dat": "TOLER",
                    "min": 0,
                    "max": 2,
                    "dec": 2,
                },
            ],
        ]
    )

    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.con = con
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)
        self.uc = UserCommunication(iface, "FLO-2D")

        self._startimtep = 1111
        self._endtimtep = 9999
        old_IDEBRV = self.gutils.get_cont_par("IDEBRV")

        self.use_time_interval_grp.toggled.connect(self.use_time_interval_grp_checked)
        self.ITIMTEP.currentIndexChanged.connect(self.ITIMTEP_currentIndexChanged)
        self.ISED.currentIndexChanged.connect(self.ISED_currentIndexChanged)
        self.IDEBRV.clicked.connect(self.IDEBRV_clicked)

        # self.timeAndPlotGroupBox.setObjectName("ColoredGroupBox")
        # self.timeAndPlotGroupBox.setStyleSheet("QGroupBox#ColoredGroupBox { border: 1px solid blue;}")
        #
        # self.globalDataGroup.setObjectName("ColoredGroupBox")
        # self.globalDataGroup.setStyleSheet("QGroupBox#ColoredGroupBox { border: 1px solid blue;}")
        #
        # self.systemComponentsSwitchesGroup.setObjectName("ColoredGroupBox")
        # self.systemComponentsSwitchesGroup.setStyleSheet("QGroupBox#ColoredGroupBox { border: 1px solid blue;}")
        #
        # self.physicalProcessesSwitchesGroup.setObjectName("ColoredGroupBox")
        # self.physicalProcessesSwitchesGroup.setStyleSheet("QGroupBox#ColoredGroupBox { border: 1px solid blue;}")
        #
        # self.conveyanceSrtructureSwitchesGroup.setObjectName("ColoredGroupBox")
        # self.conveyanceSrtructureSwitchesGroup.setStyleSheet("QGroupBox#ColoredGroupBox { border: 1px solid blue;}")
        #
        # self.floodplainChannelDisplayOptionsGroup.setObjectName("ColoredGroupBox")
        # self.floodplainChannelDisplayOptionsGroup.setStyleSheet("QGroupBox#ColoredGroupBox { border: 1px solid blue;}")
        #
        # self.timeLapseOutputGroup.setObjectName("ColoredGroupBox")
        # self.timeLapseOutputGroup.setStyleSheet("QGroupBox#ColoredGroupBox { border: 1px solid blue;}")
        #
        # self.numericalStabilityParametersGroupBox.setObjectName("ColoredGroupBox")
        # self.numericalStabilityParametersGroupBox.setStyleSheet("QGroupBox#ColoredGroupBox { border: 1px solid blue;}")
        #
        # self.courantNumbersGroup.setObjectName("ColoredGroupBox")
        # self.courantNumbersGroup.setStyleSheet("QGroupBox#ColoredGroupBox { border: 1px solid blue;}")

        self.polulate_values_JJ()

    def set_spinbox_JJ(self, key, spin):
        values = self.PARAMS[key]
        spin.setDecimals(values["dec"])
        spin.setRange(values["min"], values["max"])

    def polulate_values_JJ(self):
        try:
            _mud = False
            _sed = False
            # _idebrv = self.gutils.get_cont_par("IDEBRV")
            for key, values in list(self.PARAMS.items()):
                if key == "COURCHAR_C" or key == "COURCHAR_T":
                    continue

                db_val = self.gutils.get_cont_par(key)
                if db_val is None:
                    db_val = 0
                elif db_val in ["C", "T"]:
                    db_val = 1
                else:
                    db_val = float(db_val)

                if key == "MUD":
                    _mud = db_val
                    # _mud = True if db_val in [1, 2] else False
                    continue
                if key == "ISED":
                    _sed = db_val
                    # _sed = True if db_val == 1 else False
                    continue

                widget = getattr(self, key)
                if isinstance(widget, QCheckBox):
                    if db_val == 1:
                        widget.setChecked(True)
                    else:
                        widget.setChecked(False)
                elif isinstance(widget, QDoubleSpinBox):
                    self.set_spinbox_JJ(key, widget)
                    widget.setValue(db_val)
                else:
                    widget.setCurrentIndex(db_val)

                if key == "STARTIMTEP":
                    self._startimtep = float_or_zero(db_val)
                if key == "ENDTIMTEP":
                    self._endtimtep = float_or_zero(db_val)

            widgetISED = getattr(self, "ISED")
            if _mud == 0 and _sed == 0:
                widgetISED.setCurrentIndex(2)  # None
            elif _mud == 0 and _sed == 1:
                widgetISED.setCurrentIndex(1)  # Sediment Transport
            elif _mud == 1 and _sed == 0:
                widgetISED.setCurrentIndex(0)  # Mud/Debris
            elif _mud == 2:
                widgetISED.setCurrentIndex(3)  # Two Phase

            self.ITIMTEP_currentIndexChanged()

            self.use_time_interval_grp.setChecked(self._startimtep != 0.0 or self._endtimtep != 0.0)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 310718.1942: error populating control variables dialog."
                + "\n__________________________________________________",
                e,
            )

    def use_time_interval_grp_checked(self):
        if self.use_time_interval_grp.isChecked():
            self.STARTIMTEP.setValue(self._startimtep)
            self.ENDTIMTEP.setValue(self._endtimtep)
        else:
            self.STARTIMTEP.setValue(0.00)
            self.ENDTIMTEP.setValue(0.00)

    def ITIMTEP_currentIndexChanged(self):
        if self.ITIMTEP.currentIndex() == 0:
            self.use_time_interval_grp.setChecked(False)
            self.use_time_interval_grp.setDisabled(True)
        else:
            self.use_time_interval_grp.setChecked(True)
            self.use_time_interval_grp.setDisabled(False)

    def ISED_currentIndexChanged(self):
        if self.ISED.currentIndex() in [1, 2]:
            self.IDEBRV.setChecked(False)

    def IDEBRV_clicked(self):
        if self.IDEBRV.isChecked() and self.ISED.currentIndex() != 0:
            self.uc.bar_warn("WARNING: Debris Basin is only used with Mud/Debris (in Physical Processes)")
            self.IDEBRV.setChecked(False)

    def save_parameters_JJ(self):
        try:
            if self.use_time_interval_grp.isChecked():
                if not self.ENDTIMTEP.value() > self.STARTIMTEP.value():
                    self.uc.show_warn("WARNING 220522.0526: time lapse end time must be greater than start time.")
                    return False

            # See value of combobox 'ISED' for later set parameters MUD and ISED in 'for key...' loop.
            _mud = 0
            _sed = 0
            widget = getattr(self, "ISED")
            val = widget.currentIndex()
            if val == 0:
                _mud = 1
                _sed = 0
            elif val == 1:
                _mud = 0
                _sed = 1
            elif val == 2:
                _mud = 0
                _sed = 0
            elif val == 3:
                _mud = 2
                _sed = 0

            for key in list(self.PARAMS.keys()):
                if key == "COURCHAR_C":
                    val = "C"
                elif key == "COURCHAR_T":
                    val = "T"
                elif key == "MUD":
                    val = _mud
                elif key == "ISED":
                    val = _sed
                else:
                    widget = getattr(self, key)
                    if isinstance(widget, QCheckBox):
                        if key == "COURCHAR_C":
                            val = "C" if widget.isChecked() else None
                        elif key == "COURCHAR_T":
                            val = "T" if widget.isChecked() else None
                        else:
                            val = 1 if widget.isChecked() else 0

                    elif isinstance(widget, QDoubleSpinBox):
                        val = widget.value()
                    else:
                        val = widget.currentIndex()

                self.gutils.set_cont_par(key, val)
                control_lyr = self.lyrs.data["cont"]["qlyr"]
                control_lyr.startEditing()
                control_lyr.commitChanges()
                QCoreApplication.processEvents()

            if _mud == 1:
                self.gutils.execute(
                    "INSERT INTO mud (va, vb, ysa, ysb, sgsm, xkx) VALUES (1.0, 0.0, 1.0, 0.0, 2.5, 4285);"
                )
            if _sed == 1:
                self.gutils.execute(
                    "INSERT INTO sed (dfifty, sgrad, sgst, dryspwt, cvfg, scourdep, isedisplay) VALUES (0.0625, 2.5, 2.5, 14700.0, 0.03000, 3.0, 0);"
                )

            old_IDEBRV = self.IDEBRV.isChecked()

            return True

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 110618.1806: Could not save FLO-2D parameters!!", e)
            return False
