# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

# from qgis.PyQt.QtCore import Qt
# from ..flo2d_tools.grid_tools import highlight_selected_segment, highlight_selected_xsection_a
# from qgis.PyQt.QtWidgets import QTableWidgetItem, QApplication
# from .ui_utils import load_ui
# from ..geopackage_utils import GeoPackageUtils
# from ..user_communication import UserCommunication
# from ..utils import float_or_zero, int_or_zero



import traceback
from qgis.core import QgsWkbTypes
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QApplication, QDialogButtonBox, QInputDialog
from .ui_utils import load_ui, set_icon
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..gui.dlg_sampling_xyz import SamplingXYZDialog
from ..gui.dlg_sampling_elev import SamplingElevDialog
from ..gui.dlg_sampling_buildings_elevations import SamplingBuildingsElevationsDialog
from ..flo2d_tools.grid_tools import grid_has_empty_elev


uiDialog, qtBaseClass = load_ui('issue')

class IssuesDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = None
        self.gutils = None

        self.setup_connection()
        self.codes_cbo.currentIndexChanged.connect(self.codes_cbo_currentIndexChanged)
        self.elements_cbo.currentIndexChanged.connect(self.elements_cbo_currentIndexChanged)        


    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def codes_cbo_currentIndexChanged(self):
        self.uc.show_info("Code changed")
        pass

    def elements_cbo_currentIndexChanged(self):
        self.uc.show_info("Element changed")
        pass        
