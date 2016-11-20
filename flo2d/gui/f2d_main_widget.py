# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import QEvent, QObject, Qt
from PyQt4.QtGui import QKeySequence, QStandardItemModel, QStandardItem, QColor, QApplication
from .utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..flo2dobjects import Inflow
from grid_info_widget import GridInfoWidget
from bc_editor_widget import BCEditorWidget
from ..user_communication import UserCommunication
from ..utils import m_fdata
import StringIO
import csv


uiDialog, qtBaseClass = load_ui('f2d_widget')


class FLO2DWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs, plot):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.con = None
        self.lyrs = lyrs
        self.plot = plot
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')

        self.setup_bc_editor()
        # self.setup_plot()
        self.setup_grid_info()

    def setup_bc_editor(self):
        self.bc_editor = BCEditorWidget(self.iface, self.plot, self.lyrs)
        self.bc_editor_lout.addWidget(self.bc_editor)

    # def setup_plot(self):
    #     self.plot = PlotWidget()
    #     self.plot_lout.addWidget(self.plot)

    def setup_grid_info(self):
        self.grid_info = GridInfoWidget(self.iface, self.lyrs)
        self.grid_info_lout.addWidget(self.grid_info)
