# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.PyQt import QtCore
from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from collections import OrderedDict
from qgis.PyQt.QtWidgets import QCheckBox, QDoubleSpinBox, QApplication, qApp
from PyQt5.QtCore import QCoreApplication

uiDialog, qtBaseClass = load_ui('cont_toler_jj')

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

    PARAMS = OrderedDict([
        ['AMANN', {'label': 'Increment n Value at runtime', 'type': 'r', 'dat': 'CONT', 'min': 0.00, 'max': float('inf'), 'dec': 2}],
        ['DEPTHDUR', {'label': 'Depth Duration', 'type': 'r', 'dat': 'CONT', 'min': 0, 'max': 100, 'dec': 3}],
        ['ENCROACH', {'label': 'Encroachment Analysis Depth', 'type': 'r', 'dat': 'CONT', 'min': 0, 'max': 10, 'dec': 1}],
        ['FROUDL', {'label': 'Global Limiting Froude', 'type': 'r', 'dat': 'CONT', 'min': 0, 'max': 5, 'dec': 2}],
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
        ['NOPRTC', {'label': 'Detailed Channel Output Options', 'type': 's2', 'dat': 'CONT', 'min': 2}],
        ['NOPRTFP', {'label': 'Detailed Floodplain Output Options', 'type': 's3', 'dat': 'CONT', 'min': 2}],
        ['SHALLOWN', {'label': 'Shallow n Value', 'type': 'r', 'dat': 'CONT', 'min': 0.00, 'max': 0.4, 'dec': 2}],
        ['SIMUL', {'label': 'Simulation Time', 'type': 'r', 'dat': 'CONT', 'min': 0.01, 'max': float('inf'), 'dec': 2}],
        ['DEPRESSDEPTH', {'label': 'Depress Depth', 'type': 'r', 'dat': 'CONT', 'min': 0.00, 'max': float('inf'), 'dec': 2}],
        ['SWMM', {'label': 'Storm Drain Switch', 'type': 's', 'dat': 'CONT'}],
        ['TIMTEP', {'label': 'Time Series Output Interval', 'type': 'r', 'dat': 'CONT', 'min': 0, 'max': 100, 'dec': 2}],
        ['TOUT', {'label': 'Output Data Interval', 'type': 'r', 'dat': 'CONT', 'min': 0, 'max': float('inf'), 'dec': 2}],
        ['XARF', {'label': 'Global Area Reduction', 'type': 'r', 'dat': 'CONT', 'min': 0, 'max': 1, 'dec': 2}],
        ['IARFBLOCKMOD', {'label': 'Global ARF=1 Revision', 'type': 'r', 'dat': 'CONT', 'min': 0, 'max': 1, 'dec': 2}],
        ['XCONC', {'label': 'Global Sediment Concentration', 'type': 'r', 'dat': 'CONT', 'min': 0, 'max': 0.50, 'dec': 2}],
        ['COURANTC', {'label': 'Courant Stability C', 'type': 'r', 'dat': 'TOLER', 'min': 0, 'max': 1, 'dec': 1}],
        ['COURANTFP', {'label': 'Courant Stability FP', 'type': 'r', 'dat': 'TOLER', 'min': 0, 'max': 1, 'dec': 1}],
        ['COURANTST', {'label': 'Courant Stability St', 'type': 'r', 'dat': 'TOLER', 'min': 0, 'max': 1, 'dec': 1}],
        ['COURCHAR_C', {'label': 'Stability Line 2 Character', 'type': 'c', 'dat': 'TOLER'}],
        ['COURCHAR_T', {'label': 'Stability Line 3 Character', 'type': 'c', 'dat': 'TOLER'}],
        ['DEPTOL', {'label': 'Percent Change in Depth', 'type': 'r', 'dat': 'TOLER', 'min': 0, 'max': 0.5, 'dec': 1}],
        ['TIME_ACCEL', {'label': 'Timestep Sensitivity', 'type': 'r', 'dat': 'TOLER', 'min': 0.1, 'max': 100, 'dec': 2}],
        ['TOLGLOBAL', {'label': 'Low flow exchange limit', 'type': 'r', 'dat': 'TOLER', 'min': 0.000, 'max': 0.5, 'dec': 4}],
        ['WAVEMAX', {'label': 'Wavemax Sensitivity', 'type': 'r', 'dat': 'TOLER', 'min': 0, 'max': 2, 'dec': 2}]
    ])

    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.con = con
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.polulate_values_JJ()

    def set_spinbox_JJ(self, key, spin):
        values = self.PARAMS[key]
        spin.setDecimals(values['dec'])
        spin.setRange(values['min'], values['max'])

    def polulate_values_JJ(self):
        try:
            _mud = False
            _sed = False
            for key, values in list(self.PARAMS.items()):
                if key ==  'COURCHAR_C' or key == 'COURCHAR_T':
                    continue

                db_val = self.gutils.get_cont_par(key)
                if db_val is None:
                    db_val = 0
                elif db_val in ['C', 'T']:
                    db_val = 1
                else:
                    db_val = float(db_val)

                if key == 'MUD':
                    _mud = True if db_val == 1 else False
                    continue
                if key == 'ISED':
                    _sed = True if db_val == 1 else False
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

            widget = getattr(self, 'ISED')
            if _mud and not _sed:
                widget.setCurrentIndex(0)
            elif not _mud and _sed:
                widget.setCurrentIndex(1)
            else:
                widget.setCurrentIndex(2)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error('ERROR 310718.1942: error populating control variables dialog.'
                               +'\n__________________________________________________', e)

    def save_parameters_JJ(self):
        try:
            # See value of combobox 'ISED' for later set parameters MUD and ISED in 'for key...' loop.
            _mud = 0
            _sed = 0
            widget = getattr(self, 'ISED')
            val = widget.currentIndex()
            if val == 0:
                _mud = 1
            elif val == 1:
                _sed = 1

            for key in list(self.PARAMS.keys()):
                if key ==  'COURCHAR_C':
                    val = 'C'
                elif key == 'COURCHAR_T':
                    val = 'T'
                elif key == 'MUD':
                    val = _mud
                elif key == 'ISED':
                    val = _sed
                else:
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
                control_lyr = self.lyrs.data['cont']['qlyr']  
                control_lyr.startEditing()   
                control_lyr.commitChanges()        
                QCoreApplication.processEvents() 
                
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 110618.1806: Could not save FLO-2D parameters!!", e)
