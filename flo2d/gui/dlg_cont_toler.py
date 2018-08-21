# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from collections import OrderedDict
from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from qgis.PyQt.QtWidgets import QLabel, QComboBox, QCheckBox, QDoubleSpinBox

uiDialog, qtBaseClass = load_ui('cont_toler')


class ContTolerDialog(qtBaseClass, uiDialog):

    PARAMS = OrderedDict([
        ['AMANN', {'label': 'Increment n Value at runtime', 'type': 'r', 'dat': 'CONT', 'min': -99, 'max': float('inf'), 'dec': 1}],
        ['DEPTHDUR', {'label': 'Depth Duration', 'type': 'r', 'dat': 'CONT', 'min': 0, 'max': 100, 'dec': 3}],
        ['ENCROACH', {'label': 'Encroachment Analysis Depth', 'type': 'r', 'dat': 'CONT', 'min': 0, 'max': 10, 'dec': 1}],
        ['FROUDL', {'label': 'Global Limiting Froude', 'type': 'r', 'dat': 'CONT', 'min': 0, 'max': 5, 'dec': 1}],
        ['GRAPTIM', {'label': 'Graphical Update Interval', 'type': 'r', 'dat': 'CONT', 'min': 0.01, 'max': float('inf'), 'dec': 2}],
        ['IBACKUP', {'label': 'Backup Switch', 'type': 's2', 'dat': 'CONT'}],
        ['ICHANNEL', {'label': 'Channel Switch', 'type': 's', 'dat': 'CONT'}],
        ['IDEBRV', {'label': 'Debris Switch', 'type': 's', 'dat': 'CONT'}],
        ['IEVAP', {'label': 'Evaporation Switch', 'type': 's', 'dat': 'CONT'}],
        ['IFLOODWAY', {'label': 'Floodway Analysis Switch', 'type': 's', 'dat': 'CONT'}],
        ['IHYDRSTRUCT', {'label': 'Hydraulic Structure Switch', 'type': 's', 'dat': 'CONT'}],
        ['IMULTC', {'label': 'Multiple Channel Switch', 'type': 's', 'dat': 'CONT'}],
        ['IMODFLOW', {'label': 'Modflow Switch', 'type': 's', 'dat': 'CONT'}],
        ['INFIL', {'label': 'Infiltration Switch', 'type': 's', 'dat': 'CONT'}],
        ['IRAIN', {'label': 'Rain Switch', 'type': 's', 'dat': 'CONT'}],
        ['ISED', {'label': 'Sediment Transport Switch', 'type': 's', 'dat': 'CONT'}],
        ['ITIMTEP', {'label': 'Time Series Selection Switch', 'type': 's5', 'dat': 'CONT'}],
        ['IWRFS', {'label': 'Building Switch', 'type': 's', 'dat': 'CONT'}],
        ['LEVEE', {'label': 'Levee Switch', 'type': 's', 'dat': 'CONT'}],
        ['LGPLOT', {'label': 'Graphic Mode', 'type': 's2', 'dat': 'CONT'}],
        ['METRIC', {'label': 'Metric Switch', 'type': 's', 'dat': 'CONT'}],
        ['MSTREET', {'label': 'Street Switch', 'type': 's', 'dat': 'CONT'}],
        ['MUD', {'label': 'Mudflow Switch', 'type': 's', 'dat': 'CONT'}],
        ['NOPRTC', {'label': 'Detailed Channel Output Options', 'type': 's2', 'dat': 'CONT'}],
        ['NOPRTFP', {'label': 'Detailed Floodplain Output Options', 'type': 's3', 'dat': 'CONT'}],
        ['SHALLOWN', {'label': 'Shallow n Value', 'type': 'r', 'dat': 'CONT', 'min': 0, 'max': 0.4, 'dec': 2}],
        ['SIMUL', {'label': 'Simulation Time', 'type': 'r', 'dat': 'CONT', 'min': 0.01, 'max': float('inf'), 'dec': 2}],
        ['DEPRESSDEPTH', {'label': 'Depress Depth', 'type': 's', 'dat': 'CONT'}],
        ['SWMM', {'label': 'Storm Drain Switch', 'type': 's', 'dat': 'CONT'}],
        ['TIMTEP', {'label': 'Time Series Output Interval', 'type': 'r', 'dat': 'CONT', 'min': 0, 'max': 100, 'dec': 1}],
        ['TOUT', {'label': 'Output Data Interval', 'type': 'r', 'dat': 'CONT', 'min': 0, 'max': float('inf'), 'dec': 2}],
        ['XARF', {'label': 'Global Area Reduction', 'type': 'r', 'dat': 'CONT', 'min': 0, 'max': 1, 'dec': 2}],
        ['XCONC', {'label': 'Global Sediment Concentration', 'type': 'r', 'dat': 'CONT', 'min': 0, 'max': 0.50, 'dec': 2}],
        ['COURANTC', {'label': 'Courant Stability C', 'type': 'r', 'dat': 'TOLER', 'min': 0.2, 'max': 1, 'dec': 1}],
        ['COURANTFP', {'label': 'Courant Stability FP', 'type': 'r', 'dat': 'TOLER', 'min': 0, 'max': 1, 'dec': 1}],
        ['COURANTST', {'label': 'Courant Stability St', 'type': 'r', 'dat': 'TOLER', 'min': 0, 'max': 1, 'dec': 1}],
        ['COURCHAR_C', {'label': 'Stability Line 2 Character', 'type': 'c', 'dat': 'TOLER'}],
        ['COURCHAR_T', {'label': 'Stability Line 3 Character', 'type': 'c', 'dat': 'TOLER'}],
        ['DEPTOL', {'label': 'Percent Change in Depth', 'type': 'r', 'dat': 'TOLER', 'min': 0, 'max': 0.5, 'dec': 1}],
        ['TIME_ACCEL', {'label': 'Timestep Sensitivity', 'type': 'r', 'dat': 'TOLER', 'min': 0.01, 'max': 100, 'dec': 2}],
        ['TOLGLOBAL', {'label': 'Low flow exchange limit', 'type': 'r', 'dat': 'TOLER', 'min': 0, 'max': 0.5, 'dec': 4}],
        ['WAVEMAX', {'label': 'Wavemax Sensitivity', 'type': 'r', 'dat': 'TOLER', 'min': 0, 'max': 2, 'dec': 2}]
    ])

    COMBO_KEYS = {
            'IBACKUP': ['OFF', 'ON [1]', 'ON [2]'],
            'ITIMTEP': ['OFF', 'ON [1]', 'ON [2]', 'ON [3]', 'ON [4]', 'ON [5]'],
            'LGPLOT': ['TEXT', 'BATCH', 'GRAPHIC'],
            'NOPRTC': ['data is reported', 'data is not reported', 'none is reported'],
            'NOPRTFP': ['data is reported', 'data is not reported', 'none is reported']
        }

    def __init__(self, con, iface):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.con = con
        self.iface = iface
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.setup_layout()
        self.polulate_values()

    def set_combo(self, key, combo):
        for i in self.COMBO_KEYS[key]:
            combo.addItem(i)

    def set_spinbox(self, key, spin):
        values = self.PARAMS[key]
        spin.setDecimals(values['dec'])
        spin.setRange(values['min'], values['max'])

    def setup_layout(self):
        for i, (key, values) in enumerate(self.PARAMS.items()):
            if i < 17:
                first_col = 0
                second_col = 1
                row_no = i
            else:
                first_col = 2
                second_col = 3
                row_no = i - 17
            lab = QLabel(values['label'])
            lab.setToolTip(key)
            typ = values['type']
            if typ == 's' or typ == 'c':
                widget = QCheckBox()
            elif values['type'] == 'r':
                widget = QDoubleSpinBox()
                widget.setMaximumWidth(100)
            else:
                widget = QComboBox()
                self.set_combo(key, widget)
                widget.setMaximumWidth(120)
            widget.setLayoutDirection(1)
            lout = self.cont_lout if values['dat'] == 'CONT' else self.toler_lout
            lout.addWidget(lab, row_no, first_col)
            lout.addWidget(widget, row_no, second_col)
            setattr(self, key, widget)

    def polulate_values(self):
        for key, values in list(self.PARAMS.items()):
            db_val = self.gutils.get_cont_par(key)
            if db_val is None:
                db_val = 0
            elif db_val in ['C', 'T']:
                db_val = 1
            else:
                db_val = float(db_val)
            widget = getattr(self, key)
            if isinstance(widget, QCheckBox):
                if db_val == 1:
                    widget.setChecked(True)
                else:
                    widget.setChecked(False)
            elif isinstance(widget, QDoubleSpinBox):
                self.set_spinbox(key, widget)
                widget.setValue(db_val)
            else:
                widget.setCurrentIndex(db_val)

    def save_parameters(self):
        for key in list(self.PARAMS.keys()):
            widget = getattr(self, key)
            if isinstance(widget, QCheckBox):
                if key == 'COURCHAR_C':
                    val = 'C' if widget.isChecked() else None
                elif key == 'COURCHAR_T':
                    val = 'T' if widget.isChecked() else None
                else:
                    val = 1 if widget.isChecked() else 0

            elif isinstance(widget, QDoubleSpinBox):
                val = widget.value()
            else:
                val = widget.currentIndex()
            self.gutils.set_cont_par(key, val)
