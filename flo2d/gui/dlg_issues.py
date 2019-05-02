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


import os
import traceback
from qgis.core import QgsWkbTypes, QgsFeatureRequest
from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtWidgets import QApplication, QDialogButtonBox, QInputDialog, QFileDialog, QTableWidgetItem
from .ui_utils import load_ui, set_icon, center_canvas
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..gui.dlg_sampling_xyz import SamplingXYZDialog
from ..gui.dlg_sampling_elev import SamplingElevDialog
from ..gui.dlg_sampling_buildings_elevations import SamplingBuildingsElevationsDialog
from ..flo2d_tools.grid_tools import grid_has_empty_elev
from qgis.PyQt.QtGui import QColor
from collections import OrderedDict

uiDialog, qtBaseClass = load_ui('issues')

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
        self.errors = []

        self.setup_connection()
        self.populate_issues()
        self.populate_elements_cbo()
        self.issues_codes_cbo.currentIndexChanged.connect(self.codes_cbo_currentIndexChanged)
        self.elements_cbo.currentIndexChanged.connect(self.elements_cbo_currentIndexChanged)        
        self.find_cell_btn.clicked.connect(self.find_cell)
        set_icon(self.find_cell_btn, 'eye-svgrepo-com.svg')

    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_issues(self):
        self.import_DEBUG_file()
        
        
    def import_DEBUG_file(self):
        """
        Reads DEBUG file.
        """
        self.uc.clear_bar_messages()

        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return

        s = QSettings()
        last_dir = s.value('FLO-2D/lastGpkgDir', '')
        debug_file, __ = QFileDialog.getOpenFileName(
            None,
            'Select DEBUG file to import',
            directory=last_dir,
            filter='(DEBUG* debug*')
        if not debug_file:
            return

        with open(debug_file, 'r') as f1:
            for line in f1:
                row = line.split(',') 
                if len(row) == 3: 
                    self.errors.append([row[0], row[1], row[2]])                   

        QApplication.restoreOverrideCursor()        
        
           
    def populate_elements_cbo(self):
        self.elements_cbo.clear()
        for x in self.errors:
            if self.elements_cbo.findText(x[0]) == -1:
                self.elements_cbo.addItem(x[0])


    def codes_cbo_currentIndexChanged(self):
        pass

    def elements_cbo_currentIndexChanged(self):
        self.description_tblw.setRowCount(0)
        nElems = self.elements_cbo.count()
        if nElems > 0:
            for item in self.errors:
                if item[0] == self.elements_cbo.currentText():
                    rowPosition = self.description_tblw.rowCount()
                    self.description_tblw.insertRow(rowPosition)   
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[0])                 
                    self.description_tblw.setItem(rowPosition , 0, itm)
                    itm = QTableWidgetItem() 
                    itm.setData(Qt.EditRole, item[1])  
                    self.description_tblw.setItem(rowPosition , 1, itm)
                    itm = QTableWidgetItem() 
                    itm.setData(Qt.EditRole, item[2])  
                    self.description_tblw.setItem(rowPosition , 2, itm) 
                         

    def find_cell(self):
        try: 
            grid = self.lyrs.data['grid']['qlyr']
            if grid is not None:
                if grid:
                    cell = self.elements_cbo.currentText()
                    if cell != '':
                        cell = int(cell)
                        if len(grid) >= cell and cell > 0:
                            self.lyrs.show_feat_rubber(grid.id(), cell, QColor(Qt.yellow))
                            feat = next(grid.getFeatures(QgsFeatureRequest(cell)))
                            x, y = feat.geometry().centroid().asPoint()
                            self.lyrs.zoom_to_all()
                            center_canvas(self.iface, x, y)
                        else:
                            self.uc.bar_warn('Cell ' + str(cell) + ' not found.')
                            self.lyrs.clear_rubber()                          
                    else:
                        self.uc.bar_warn('Cell ' + str(cell) + ' not found.')
                        self.lyrs.clear_rubber()              
        except ValueError:
            self.uc.bar_warn('Cell ' + str(cell) + ' not valid.')
            self.lyrs.clear_rubber()    
            pass  
            