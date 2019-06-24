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
from qgis.core import * 
from qgis.PyQt.QtCore import Qt, QSettings, QVariant
# ( QgsFields, QgsField, QgsFeature, QgsVectorFileWriter, QgsFeatureRequest, 
#                         QgsWkbTypes, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer )
from qgis.PyQt.QtWidgets import (QApplication, QDialogButtonBox, QInputDialog, QFileDialog, 
                                QTableWidgetItem, QListView, QComboBox, QTableView, QCompleter, QTableWidget )
from .ui_utils import load_ui, set_icon, center_canvas, zoom, zoom_show_n_cells
from .table_editor_widget import StandardItemModel, StandardItem
from ..utils import copy_tablewidget_selection
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..gui.dlg_sampling_xyz import SamplingXYZDialog
from ..gui.dlg_sampling_elev import SamplingElevDialog
from ..gui.dlg_sampling_buildings_elevations import SamplingBuildingsElevationsDialog
from ..flo2d_tools.grid_tools import grid_has_empty_elev
from qgis.PyQt.QtGui import QColor
# from ..flo2d_tools.conflicts import Conflicts

uiDialog, qtBaseClass = load_ui('errors')
class ErrorsDialog(qtBaseClass, uiDialog):

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
        self.debug_directory = ""
#         self.component1_cbo.setCurrentIndex(1)
        self.setup_connection()
        self.import_DEBUG_btn.clicked.connect(self.import_DEBUG_file)
        self.errors_in_current_project_btn.clicked.connect(self.errors_in_current_project)
        
    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)        

    def import_DEBUG_file(self):
        try:        
            dlg_issues = IssuesDialog(self.con, self.iface, self.lyrs)
            dlg_issues.exec_()
 
        except ValueError:  
            # Forced error during contructor to stop showing dialog.
            pass      

    def errors_in_current_project(self):
        if self.component1_cbo.currentText() == "" and self.component2_cbo.currentText() == "":
            self.uc.show_info("Select a component!")
        else:    
            try:   
                QApplication.setOverrideCursor(Qt.WaitCursor)     
                dlg_conflicts = ConflictsDialog(self.con, self.iface, self.lyrs, 
                                                self.n_issues_sbox, self.component1_cbo.currentText(), self.component2_cbo.currentText())
                QApplication.restoreOverrideCursor()
                dlg_conflicts.exec_() 
            except ValueError:  
                # Forced error during contructor to stop showing dialog.
                pass           


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
        self.debug_directory = ""
        set_icon(self.find_cell_btn, 'eye-svgrepo-com.svg')
        set_icon(self.zoom_in_btn, 'zoom_in.svg')
        set_icon(self.zoom_out_btn, 'zoom_out.svg')
        
        self.setup_connection()
        self.issues_codes_cbo.activated.connect(self.codes_cbo_activated)
        self.errors_cbo.activated.connect(self.errors_cbo_activated)    
        self.elements_cbo.activated.connect(self.elements_cbo_activated)        
        self.find_cell_btn.clicked.connect(self.find_cell_clicked)
        self.description_tblw.cellClicked.connect(self.description_tblw_cell_clicked)       
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        
        if (not self.populate_issues()):
            raise ValueError('Not a legal file!')
        self.import_other_issues_files()
        
        self.description_tblw.setColumnWidth(2,550)
        self.populate_elements_cbo()
        self.populate_errors_cbo()
        self.loadIssues()
        self.issues_codes_cbo.setCurrentIndex(1)
        self.codes_cbo_activated()        

    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_issues(self):
        """
        Reads DEBUG file.
        """
        self.uc.clear_bar_messages()

        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return False

        s = QSettings()
        last_dir = s.value('FLO-2D/lastGpkgDir', '')
        debug_file, __ = QFileDialog.getOpenFileName(
            None,
            'Select DEBUG file to import',
            directory=last_dir,
            filter='(DEBUG* debug*')
        if not debug_file:
            return False

        try: 
            if (not os.path.isfile(debug_file)):
                self.uc.show_warn(os.path.basename(debug_file) + " is being used by another process!")   
                return False   
            elif (os.path.getsize(debug_file) == 0):   
                self.uc.show_warn(os.path.basename(debug_file) + " is empty!")    
                return False   
            else:  
                self.debug_directory = os.path.dirname(debug_file)     
                with open(debug_file, 'r') as f1:
                    build = next(f1)
                    for line in f1:
                        row = line.split(',') 
                        if len(row) == 3: 
                            self.errors.append([row[0], row[1], row[2].strip()]) 
                if (self.errors):      
                    self.setWindowTitle("Error and Warnings in    " + os.path.basename(debug_file))
                    QApplication.restoreOverrideCursor()  
                    return True                        
                else:
                    self.uc.show_warn("Format of file " + os.path.basename(debug_file) + " is incorrect!")
                    return False     
                
        except UnicodeDecodeError:
             # non-text dat    
            self.uc.show_warn(os.path.basename(debug_file) + " is not a text file!")
            return False
 
    def import_other_issues_files(self):
            dlg_issues_files = IssuesFiles(self.con, self.iface, self.lyrs)
            ok = dlg_issues_files.exec_()
            if ok:
                if dlg_issues_files.files:
                    if "Depressed" in dlg_issues_files.files:
                        file = self.debug_directory + "/DEPRESSED_ELEMENTS.OUT"
                        if (not os.path.isfile(file)):
                            self.uc.show_warn(os.path.basename(file) + " is being used by another process!")   
                        elif (os.path.getsize(file) == 0):   
                            self.uc.show_warn(os.path.basename(file) + " is empty!")
                        else:   
                            lyr = self.lyrs.get_layer_by_name('Depressed Elements', self.lyrs.group)                       
                            if lyr:
                                self.uc.show_info("Layer 'Depressed Elements' already exists!")         
                            else:                                               
                                try:
                                    features = []        
                                    with open(file, 'r') as f:                                     
                                        for _ in range(4):
                                            next(f)
                                        for row in f:
                                            values  = row.split()
                                            self.errors.append([values[0], "9001", "DEPRESSED_ELEMENTS.OUT : Depressed Element by " + values[3]]) 
                                             
                                            features.append( [values[1], values[2], values[0], values[3]] ) # x, y, cell, elev
                                    shapefile = self.debug_directory + "/Depressed Elements.shp"
                                    name = "Depressed Elements"
                                    fields = [['cell','I'], ['min_elev','D']]
                                    if self.create_points_shapefile(shapefile, name, fields, features):
                                        vlayer = self.iface.addVectorLayer(shapefile, "" , 'ogr')      
                                except Exception as e:
                                    QApplication.restoreOverrideCursor()
                                    self.uc.show_error("ERROR 170519.0700: error while reading \n" + file  + "!\n", e)                
                    
                    if "Channels" in dlg_issues_files.files:
                        file = self.debug_directory + "/CHANBANKEL.CHK"
                        if (not os.path.isfile(file)):
                            self.uc.show_warn(os.path.basename(file) + " is being used by another process!")   
                        elif (os.path.getsize(file) == 0):   
                            self.uc.show_warn(os.path.basename(file) + " is empty!")
                        else: 
                            lyr = self.lyrs.get_layer_by_name('Channel Bank Elev Differences', self.lyrs.group)                        
                            if lyr:
                                self.uc.show_info("Layer 'Channel Bank Elev Differences' already exists!")         
                            else:  
                                try:
                                    features = []  
                                    with open(file, 'r') as f:
                                        for _ in range(6):
                                            next(f)
                                        for row in f:
                                            values  = row.split()
                                            self.errors.append([values[0], "9002", "CHANBANKEL.CHK : Bank - Floodplain = " + values[5]])   
    
                                            features.append( [values[1], values[2], values[0], values[3], values[4], values[5], values[6]] ) # x, y, cell, etc
                                    shapefile = self.debug_directory + "/Channel Bank Elev Differences.shp"
                                    name = "Channel Bank Elev Differences"
                                    fields = [['cell','I'], ['bank_elev','D'], ['floodplain_elev','D'], ['difference','D'], ['LB_RB','S']]
                                    if self.create_points_shapefile(shapefile, name, fields, features):
                                        vlayer = self.iface.addVectorLayer(shapefile, "" , 'ogr') 
                                                
                                except Exception as e:
                                    QApplication.restoreOverrideCursor()
                                    self.uc.show_error("ERROR 170519.0704: error while reading " + file  + "!\n", e)                               
                    
                    if "Rim" in dlg_issues_files.files:
                        file = self.debug_directory + "/FPRIMELEV.OUT"
                        if (not os.path.isfile(file)):
                            self.uc.show_warn(os.path.basename(file) + " is being used by another process!")   
                        elif (os.path.getsize(file) == 0):   
                            self.uc.show_warn(os.path.basename(file) + " is empty!")
                        else:  
                            lyr = self.lyrs.get_layer_by_name('Flooplain Rim Differences', self.lyrs.group)                        
                            if lyr:
                                self.uc.show_info("Layer 'Flooplain Rim Differences' already exists!")         
                            else:  
                                try:
                                    grid = self.lyrs.data['grid']['qlyr']
                                    features = []  
                                    with open(file, 'r') as f:
                                        for _ in range(1):
                                             next(f)
                                        for row in f:
                                            values  = row.split()
                                            self.errors.append([values[0], "9003", "FPRIMELEV.OUT : Floodplain - Rim = " + values[3]]) 
                                            
                                            cell = int(values[0])
                                            feat = next(grid.getFeatures(QgsFeatureRequest(cell)))
                                            x, y = feat.geometry().centroid().asPoint()
                                            
                                            features.append( [ x, y , values[0], values[1], values[2], values[3], values[4]] ) # x, y, cell, etc
                                    shapefile = self.debug_directory + "/Flooplain Rim Differences.shp"
                                    name = "Flooplain Rim Differences"
                                    fields = [['cell','I'], ['floodplain_elev','D'], ['rim_elev','D'], ['difference','D'], ['new_floodplain_elev','D']]
                                    if self.create_points_shapefile(shapefile, name, fields, features):
                                        vlayer = self.iface.addVectorLayer(shapefile, "" , 'ogr')                                         
                                        
                                except Exception as e:
                                    QApplication.restoreOverrideCursor()
                                    self.uc.show_error("ERROR 170519.0705: error while reading " + file  + "!\n", e)                                                                     


    def populate_elements_cbo(self):
        self.elements_cbo.clear()
        self.elements_cbo.addItem(" ")
        for x in self.errors:
            if self.elements_cbo.findText(x[0].strip()) == -1:
                self.elements_cbo.addItem(x[0].strip())
        self.elements_cbo.model().sort(0)
                
    def populate_errors_cbo(self):
        self.errors_cbo.clear()
        self.errors_cbo.addItem(" ")
        for x in self.errors:
            if self.errors_cbo.findText(x[1].strip()) == -1:
                self.errors_cbo.addItem(x[1].strip())
        self.errors_cbo.model().sort(0)        
                
    def codes_cbo_activated(self): 
        self.loadIssues()
        
    def loadIssues(self):
        
        self.description_tblw.setRowCount(0)
        
        codes = self.issues_codes_cbo.currentText()
        if codes == "Depressed Elements (DEPRESSED_ELEMENTS.OUT)":
            self.uc.bar_info("Depressed Elements (DEPRESSED_ELEMENTS.OUT)",2)
        elif codes == "Channel <> Floodplain (CHANBANKEL.CHK)":
           self.uc.bar_info("Channel <> Floodplain (CHANBANKEL.CHK)",2)
        elif codes == "Floodplain <> Storm Drain Rim (FPRIMELEV.OUT)": 
            self.uc.bar_info("Floodplain <> Storm Drain Rim (FPRIMELEV.OUT)",2)
        elif codes == "High Velocities (CHANSTABILITY.OUT)":
            self.uc.bar_info("High Velocities (CHANSTABILITY.OUT)",2)
        
        else:    
            first, second = "", ""
            codes = codes.split(' ')
            for item in codes:
                if (item != ''):
                    codes = item
                    break 
            if codes[0] != "":
                codes = codes.split('-') 
                if (len(codes) == 1): 
                    # There only one code.
                    first = codes[0]
                else:
                    first = codes[0]
                    second = codes[1]
                
                if first.isdigit():
                    for item in self.errors:
                        if (  second == "" and int(item[1]) == int(first) ):
                                rowPosition = self.description_tblw.rowCount()
                                self.description_tblw.insertRow(rowPosition)   
                                itm = QTableWidgetItem()
                                itm.setData(Qt.EditRole, item[0].strip())                 
                                self.description_tblw.setItem(rowPosition , 0, itm)
                                itm = QTableWidgetItem() 
                                itm.setData(Qt.EditRole, item[1].strip())  
                                self.description_tblw.setItem(rowPosition , 1, itm)
                                itm = QTableWidgetItem() 
                                itm.setData(Qt.EditRole, item[2])  
                                self.description_tblw.setItem(rowPosition , 2, itm)                   
                        elif ( second != "" and int(item[1]) >= int(first) and int(item[1]) <= int(second) ):
                                rowPosition = self.description_tblw.rowCount()
                                self.description_tblw.insertRow(rowPosition)   
                                itm = QTableWidgetItem()
                                itm.setData(Qt.EditRole, item[0].strip())                 
                                self.description_tblw.setItem(rowPosition , 0, itm)
                                itm = QTableWidgetItem() 
                                itm.setData(Qt.EditRole, item[1].strip() ) 
                                self.description_tblw.setItem(rowPosition , 1, itm)
                                itm = QTableWidgetItem() 
                                itm.setData(Qt.EditRole, item[2])  
                                self.description_tblw.setItem(rowPosition , 2, itm) 
                elif first == "All":
                    for item in self.errors:                    
                        rowPosition = self.description_tblw.rowCount()
                        self.description_tblw.insertRow(rowPosition)   
                        itm = QTableWidgetItem()
                        itm.setData(Qt.EditRole, item[0].strip())                 
                        self.description_tblw.setItem(rowPosition , 0, itm)
                        itm = QTableWidgetItem() 
                        itm.setData(Qt.EditRole, item[1].strip() ) 
                        self.description_tblw.setItem(rowPosition , 1, itm)
                        itm = QTableWidgetItem() 
                        itm.setData(Qt.EditRole, item[2])  
                        self.description_tblw.setItem(rowPosition , 2, itm) 
                        
            self.errors_cbo.setCurrentIndex(0)
            self.elements_cbo.setCurrentIndex(0)                   
            
    def elements_cbo_activated(self):
        self.description_tblw.setRowCount(0)
        nElems = self.elements_cbo.count()
        if nElems > 0:
            cell = self.elements_cbo.currentText().strip()
            for item in self.errors:
                if item[0].strip() == cell:
                    rowPosition = self.description_tblw.rowCount()
                    self.description_tblw.insertRow(rowPosition)   
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[0].strip())                 
                    self.description_tblw.setItem(rowPosition , 0, itm)
                    itm = QTableWidgetItem() 
                    itm.setData(Qt.EditRole, item[1].strip())  
                    self.description_tblw.setItem(rowPosition , 1, itm)
                    itm = QTableWidgetItem() 
                    itm.setData(Qt.EditRole, item[2])  
                    self.description_tblw.setItem(rowPosition , 2, itm) 
            
            self.find_cell(cell)             
            self.errors_cbo.setCurrentIndex(0)
            self.issues_codes_cbo.setCurrentIndex(0)
              
    def errors_cbo_activated(self):
        self.description_tblw.setRowCount(0)
        nElems = self.errors_cbo.count()
        if nElems > 0:
            for item in self.errors:
                if item[1].strip() == self.errors_cbo.currentText().strip():
                    rowPosition = self.description_tblw.rowCount()
                    self.description_tblw.insertRow(rowPosition)   
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[0].strip())                 
                    self.description_tblw.setItem(rowPosition , 0, itm)
                    itm = QTableWidgetItem() 
                    itm.setData(Qt.EditRole, item[1].strip())  
                    self.description_tblw.setItem(rowPosition , 1, itm)
                    itm = QTableWidgetItem() 
                    itm.setData(Qt.EditRole, item[2])  
                    self.description_tblw.setItem(rowPosition , 2, itm) 
            self.elements_cbo.setCurrentIndex(0)
            self.issues_codes_cbo.setCurrentIndex(0)
            
    def find_cell_clicked(self):
        cell = self.elements_cbo.currentText()
        self.find_cell(cell)   

    def find_cell(self, cell):
        try: 
            grid = self.lyrs.data['grid']['qlyr']
            if grid is not None:
                if grid:
                    if cell != '':
                        cell = int(cell)
                        if len(grid) >= cell and cell > 0:
                            self.lyrs.show_feat_rubber(grid.id(), cell, QColor(Qt.yellow))
                            feat = next(grid.getFeatures(QgsFeatureRequest(cell)))
                            x, y = feat.geometry().centroid().asPoint()
                            center_canvas(self.iface, x, y)
                        else:
                            if cell != -999:
                                self.uc.bar_warn('Cell ' + str(cell) + ' not found.',2)
                                self.lyrs.clear_rubber()                          
                    else:
                        if cell.strip() != "-999" and cell.strip() != "":                        
                            self.uc.bar_warn('Cell ' + str(cell) + ' not found.',2)
                            self.lyrs.clear_rubber()              
        except ValueError:
            self.uc.bar_warn('Cell ' + str(cell) + ' not valid.')
            self.lyrs.clear_rubber()    
            pass  
            
            
    def description_tblw_cell_clicked(self, row, column):
        cell  = self.description_tblw.item(row,0).text()
        self.find_cell(cell)        
 
    def zoom_in(self):
        zoom(self.iface,  0.4)

    def zoom_out(self):
        zoom(self.iface,  -0.4)        
    
    def create_points_shapefile(self, shapefile, name, fields, features):
        try: 
            lyr = QgsProject.instance().mapLayersByName(name)
            
            if lyr:
                QgsProject.instance().removeMapLayers([lyr[0].id()])

            # define fields for feature attributes. A QgsFields object is needed
            f = QgsFields()
            for field in fields:
                f.append(QgsField(field[0], QVariant.Int if field[1] == 'I' else QVariant.Double if field[1] == 'D'  else QVariant.String))

#                 f.append(QgsField("min_elev", QVariant.Double))
            
            mapCanvas = self.iface.mapCanvas()
            my_crs = mapCanvas.mapSettings().destinationCrs()
            QgsVectorFileWriter.deleteShapeFile(shapefile)
            writer = QgsVectorFileWriter(shapefile, "system", f, QgsWkbTypes.Point, my_crs, "ESRI Shapefile")
            if writer.hasError() != QgsVectorFileWriter.NoError:
                self.uc.bar_error("Error when creating shapefile: " + shapefile)
            
            # add features:
            for feat in features:
                attr = []
                fet = QgsFeature()
                fet.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(feat[0]),float(feat[1]))))
                non_coord_feats =[]
                for i in range(2, len(fields)+2):
                   non_coord_feats.append( int(feat[i]) if fields[i-2][1] == 'I' else float(feat[i]) if fields[i-2][1] == 'D' else feat[i])
                
                fet.setAttributes(non_coord_feats)
#                 fet.setAttributes([int(feat[2]), float(feat[3])])
                writer.addFeature(fet)
            
            # delete the writer to flush features to disk
            del writer
            return True
            
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 190519.0441: error while creating layer  " + name  + "!\n", e)     
            return False                                   

    def load_shapefile(self, shapefile, layerName):
        try:
            vlayer = self.iface.addVectorLayer(shapefile, layerName , 'ogr')            
     
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 190519.2015: error while loading shapefile\n\n " + shapefile  + "!\n", e)     
            return False      
    
uiDialog, qtBaseClass = load_ui('issues_files')
class IssuesFiles(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.gutils = GeoPackageUtils(con, iface)
        self.current_lyr = None
        self.files = []

        self.complementary_files_buttonBox.accepted.connect(self.load_selected_complementary_files)
        self.setFixedSize(self.size())

        self.populate_complementary_files_dialog()

    def populate_complementary_files_dialog(self):
        s = QSettings()
        last_dir = s.value('FLO-2D/lastGdsDir', '')

        if os.path.isfile(last_dir + '\DEPRESSED_ELEMENTS.OUT'):
            self.depressed_elements_chbox.setChecked(True)
            self.depressed_elements_chbox.setEnabled(True)

        if os.path.isfile(last_dir + '\CHANBANKEL.CHK'):
            self.chanbankel_chbox.setChecked(True)
            self.chanbankel_chbox.setEnabled(True)
            
        if os.path.isfile(last_dir + '\FPRIMELEV.OUT'):
            self.fprimelev_chbox.setChecked(True)
            self.fprimelev_chbox.setEnabled(True)
        

    def load_selected_complementary_files(self):

        if self.depressed_elements_chbox.isChecked():
            self.files.append('Depressed')

        if self.chanbankel_chbox.isChecked():
            self.files.append('Channels')

        if self.fprimelev_chbox.isChecked():
            self.files.append('Rim')

uiDialog, qtBaseClass = load_ui('conflicts')
class ConflictsDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs, numErrors, issue1, issue2):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.numErrors = numErrors
        self.issue1 = issue1
        self.issue2 = issue2
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = None
        self.gutils = None
        self.errors = []              
        self.ext = self.iface.mapCanvas().extent()
        self.init_ext = self.iface.mapCanvas().extent()
        self.currentCell = None
        
        self.debug_directory = ""
        set_icon(self.find_cell_btn, 'eye-svgrepo-com.svg')
        set_icon(self.zoom_in_btn, 'zoom_in.svg')
        set_icon(self.zoom_out_btn, 'zoom_out.svg')
        set_icon(self.copy_btn, 'copy.svg')
        
        self.setup_connection()
        self.component1_cbo.activated.connect(self.component1_cbo_activated)
        self.component2_cbo.activated.connect(self.component2_cbo_activated)
        self.errors_cbo.activated.connect(self.errors_cbo_activated)    
        self.elements_cbo.activated.connect(self.elements_cbo_activated)        
#         self.find_cell_btn.clicked.connect(self.find_cell_clicked)
        self.copy_btn.clicked.connect(self.copy_to_clipboard)        
        self.description_tblw.cellClicked.connect(self.description_tblw_cell_clicked)       
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        
        self.description_tblw.setSortingEnabled(False)
        self.description_tblw.setColumnWidth(2,450)
        self.description_tblw.resizeRowsToContents()
        
#         self.elements_cbo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLength);


#         tw = QTableWidget()
#         tw.resizeRowsToContents()

#         qList = QListView()
#         qList.setUniformItemSizes(True)
#         qList.setLayoutMode(QListView.Batched)
#         self.elements_cbo.setView(qList)

        
#         table.horizontalHeader.setVisible(False)
#         table.horizontalHeader.setSectionResizeMode(QHeaderView.Stretch) 
#         table.verticalHeader.setVisible(False)
#         table.resizeRowsToContents()
#         table = StandardItemModel()
         
#         self.elements_cbo.setView(self.description_tblw)
#         self.elements_cbo.horizontalHeader().setStretchLastSection(True)

#         self.tweak1(self.elements_cbo)

#         completer = QCompleter();
#         completer.setCaseSensitivity(Qt.CaseInsensitive) 
#         completer.setModelSorting(QCompleter.CaseSensitivelySortedModel)        
#         self.elements_cbo.setCompleter(completer)



        self.populate_issues()
#         self.populate_elements_cbo()
        self.populate_errors_cbo()
        self.errors_cbo.setCurrentIndex(0)
        self.errors_cbo_activated()
        
        self.component1_cbo.setCurrentIndex(1)
        self.loadIssuePairs()

        if self.currentCell:
            x, y = self.currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            cell_size = float(self.gutils.get_cont_par('CELLSIZE'))
            zoom_show_n_cells(iface, cell_size, 30)
            self.update_extent()
###########################################


    def tweak1(self, combo):
#       //  For performance reasons use this policy on large models
#       // or AdjustToMinimumContentsLengthWithIcon
      combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLength)
    
#       // Improve combobox view performance
      self.tweak2(combo.view)
    
#       // Improve combobox completer performance
      self.tweak3(combo.completer);

    def tweak2(self, view):
#           // Improving Performance:  It is possible to give the view hints
#           // about the data it is handling in order to improve its performance
#           // when displaying large numbers of items. One approach that can be taken
#           // for views that are intended to display items with equal sizes
#           // is to set the uniformItemSizes property to true.
          view.setUniformItemSizes(True)
#           // This property holds the layout mode for the items. When the mode is Batched,
#           // the items are laid out in batches of batchSize items, while processing events.
#           // This makes it possible to instantly view and interact with the visible items
#           // while the rest are being laid out.
          view.setLayoutMode(QListView.Batched)
#           // batchSize : int
#           // This property holds the number of items laid out in each batch
#           // if layoutMode is set to Batched. The default value is 100.
#           // view.setBatchSize(100)

    def tweak3(self, completer):
          completer.setCaseSensitivity(Qt.CaseInsensitive);
#           // If the model's data for the completionColumn() and completionRole() is sorted
#           // in ascending order, you can set ModelSorting property
#           // to CaseSensitivelySortedModel or CaseInsensitivelySortedModel.
#           // On large models, this can lead to significant performance improvements
#           // because the completer object can then use a binary search algorithm
#           // instead of linear search algorithm.
          completer.setModelSorting(QCompleter.CaseSensitivelySortedModel);
    
#           // Improve completer popup (view) performance
          tweak(completer.popup())

######################################################################

    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)                                                            

    def populate_issues(self):
   
# TODO: review this!!
#         repeats = self.conflict_outfall_partialARF()
#         if repeats:
#             for r in repeats:
#                 self.errors.append([str(r), "Storm Drain Outfalls", "Partial ARF", "Storm Drain Outfalls(s) and partial ARF in same cell"])         
#  
#         repeats = self.conflict_inlet_partialARF()
#         if repeats:
#             for r in repeats:
#                 self.errors.append([str(r), "Storm Drain Inlets", "Partial ARF", "Storm Drain Inlets(s) and partial ARF in same cell"])         

#....................................................................................    
#         topN = self.numErrors    
# 
#         inflow_cells = self.get_n_cells("inflow_cells","grid_fid", topN)
#         outflow_cells = self.get_n_cells("outflow_cells", "grid_fid",  topN)
#         reduction_cells = self.get_n_cells("blocked_cells", "grid_fid", topN)
#         hyd_struct_in_cells = self.get_n_cells("struct", "inflonod", topN)
#         hyd_struct_out_cells = self.get_n_cells("struct", "outflonod", topN)        
#         chennels_left_cells = self.get_n_cells("chan_elems", "fid", topN)
#         channels_right_cells = self.get_n_cells("chan_elems", "rbankgrid", topN)
#         levees_cells = self.get_n_cells("levee_data", "grid_fid", topN)
#         mult_channels_cells = self.get_n_cells("mult_cells", "grid_fid", topN)
#         storm_inlets_cells = self.get_n_cells("swmmflo", "swmm_jt", topN)
#         storm_outfalls_cells = self.get_n_cells("swmmoutf", "grid_fid", topN)
#         street_cells = self.get_n_cells("street_seg", "igridn", topN)
# 
#     # Inflow conflicts:
#         sql = '''SELECT grid_fid FROM inflow_cells 
#                 WHERE grid_fid IN 
#                 (
#                     SELECT grid_fid
#                     FROM inflow_cells
#                     INTERSECT
#                     SELECT grid_fid
#                     FROM outflow_cells
#                 )'''    
#         rows = self.gutils.execute(sql).fetchall() 
#         
#         n_conflits = self.conflict3("Inflows", inflow_cells, 
#                       "Inflows" , inflow_cells, 
#                       "2 or more inflows in same cell")   
# 
#         n_conflits = self.conflict3("Inflows", inflow_cells, 
#                       "Outflows", outflow_cells, 
#                       "Inflow and outflow in same cell") 
#         
#         n_conflits = self.conflict3("Inflows", inflow_cells, 
#                       "Reduction Factors" , reduction_cells, 
#                       "Inflow and Reduction Factors in same cell (check partial ARF, full ARF, or WRF)")        
#         
#         n_conflits = self.conflict3("Inflows", inflow_cells, 
#                       "Hydr. Structures" , hyd_struct_in_cells, 
#                       "Inflow and Hyd. Struct in-cell in same cell")        
# 
#         n_conflits = self.conflict3("Inflows", inflow_cells, 
#                       "Hydr. Structures" , hyd_struct_out_cells, 
#                       "Inflow and Hyd. Struct out-cell in same cell")        
# 
#         n_conflits = self.conflict3("Inflows", inflow_cells, 
#                       "Channels (Left Bank)" , chennels_left_cells, 
#                       "Inflow and Channel Left Bank in same cell")        
# 
#         n_conflits = self.conflict3("Inflows", inflow_cells, 
#                       "Channels (Right Bank)" , channels_right_cells, 
#                       "Inflow and Channel Right Bank in same cell")   
#         
#         n_conflits = self.conflict3("Inflows", inflow_cells, 
#                       "Levees" , levees_cells,
#                       "Inflow and levee in same cell")  
# 
#         n_conflits = self.conflict3("Inflows", inflow_cells, 
#                       "Mult. Channels" , mult_channels_cells,
#                       "Inflow and Multiple Channels in same cell")  
# 
#         n_conflits = self.conflict3("Inflows", inflow_cells, 
#                       "Storm Drain Inlets" ,  storm_inlets_cells,
#                       "Inflow and Storm Drain Inlet in same cell")  
# 
#         n_conflits = self.conflict3("Inflows", inflow_cells, 
#                       "Storm Drain Outfalls" , storm_outfalls_cells, 
#                       "Inflow and Storm Drain Outfall in same cell") 
#         
#         
#     # Outflow conflicts: 
#         n_conflits = self.conflict3("Outflows", outflow_cells, 
#                       "Outflows", outflow_cells, 
#                       "2 or more outflows in same cell")        
# 
#         n_conflits = self.conflict3("Outflows", outflow_cells, 
#                       "Reduction Factors" , reduction_cells, 
#                       "Outflow and Reduction Factors in same cell (check partial ARF, full ARF, or WRF)")  
#                 
# #         repeats = self.conflict_outflow_fullARF()
# #         if repeats:
# #             for r in repeats:
# #                 self.errors.append([str(r), "Outflows", "Full ARF", "Outflow(s) and full ARF in same cell"])                   
# #          
# #         repeats = self.conflict_outflow_partialARF()
# #         if repeats:
# #             for r in repeats:
# #                 self.errors.append([str(r), "Outflows", "Partial ARF", "Outflow(s) and partial ARF in same cell"])                   
#         
#         n_conflits = self.conflict3("Outflows", outflow_cells, 
#                       "Hydr. Structures" , hyd_struct_in_cells, 
#                       "Outflow and Hyd. Struct in-cell in same cell")        
# 
#         n_conflits = self.conflict3("Outflows", outflow_cells, 
#                       "Hydr. Structures" , hyd_struct_out_cells, 
#                       "Outflow and Hyd. Struct out-cell in same cell")  
# 
#         n_conflits = self.conflict3("Outflows", outflow_cells, 
#                       "Channels (Left Bank)" , chennels_left_cells, 
#                       "Outflow and Channel Left Bank in same cell")        
# 
#         n_conflits = self.conflict3("Outflows", outflow_cells, 
#                       "Channels (Right Bank)" , channels_right_cells, 
#                       "Outflow and Channel Right Bank in same cell")   
#                 
#         n_conflits = self.conflict3("Outflows", outflow_cells, 
#                       "Levees" , levees_cells, 
#                       "Outflow and levee in same cell") 
#         
#         n_conflits = self.conflict3("Outflows", outflow_cells, 
#                       "Mult. Channels" , mult_channels_cells, 
#                       "Outflow and Multiple Channels in same cell") 
# 
#         n_conflits = self.conflict3("Outflows", outflow_cells, 
#                       "Storm Drain Inlets" , storm_inlets_cells, 
#                       "Outflow and Storm Drain Inlet in same cell")  
#  
#         n_conflits = self.conflict3("Outflows", outflow_cells, 
#                       "Storm Drain Outfalls" , storm_outfalls_cells, 
#                       "Outflow and Storm Drain Outfall in same cell") 
# 
#         n_conflits = self.conflict3( "Outflows" , outflow_cells, 
#                        "Streets", street_cells, 
#                        "Outflow and Street in same cell")
#         
#     # Reduction Factors conflicts: 
#         
#         n_conflits = self.conflict3("Reduction Factors", reduction_cells, 
#                       "Reduction Factors" , reduction_cells, 
#                       "Duplicate Reduction Factors in same cell (check partial ARF, full ARF, or WRF)")  
# 
#         n_conflits = self.conflict3("Reduction Factors", reduction_cells, 
#                       "Hydr. Structures" , hyd_struct_in_cells, 
#                       "Reduction Factors and Hyd. Struct in-cell in same cell (not recomended)")            
#         
#         n_conflits = self.conflict3("Reduction Factors", reduction_cells, 
#                       "Hydr. Structures" , hyd_struct_out_cells, 
#                       "Reduction Factors and Hyd. Struc out-cell in same cell (not recomended)")         
# 
#         n_conflits = self.conflict3("Reduction Factors", reduction_cells, 
#                       "Channels (Left Bank)" , chennels_left_cells, 
#                       "Reduction Factors and Channel Left Bank in same cell")        
# 
#         n_conflits = self.conflict3("Reduction Factors", reduction_cells, 
#                       "Channels (Right Bank)" , channels_right_cells, 
#                       "Reduction Factors and Channel Right Bank in same cell")   
# 
#         n_conflits = self.conflict3("Reduction Factors", reduction_cells, 
#                       "Levees" , levees_cells, 
#                       "Reduction Factors and Levees in same cell (not recomended)")         
# 
#         n_conflits = self.conflict3("Reduction Factors", reduction_cells, 
#                       "Mult. Channels" , mult_channels_cells, 
#                       "Reduction Factors and Multiple Channels in same cell (not recomended)")         
# 
#         n_conflits = self.conflict3("Reduction Factors", reduction_cells, 
#                       "Storm Drain Inlets" , storm_inlets_cells, 
#                       "Reduction Factors and Storm Drain Inlet in same cell (not recomended)") 
# 
#         n_conflits = self.conflict3("Reduction Factors", reduction_cells, 
#                       "Storm Drain Outfalls" , storm_outfalls_cells, 
#                       "Reduction Factors and Storm Drain Outfall in same cell (not recomended)") 
#         
#     # Full ARF conflicts: 
#     # Partial ARF conflicts: 
#     # WRF conflicts:
# 
#     # Hydraulic Structures conflicts:
# 
#         n_conflits = self.conflict3("Hydr. Structures" , hyd_struct_in_cells,
#                       "Hydr. Structures" , hyd_struct_in_cells, 
#                       "More than one Hyd. Struct in-cell in same element")            
# 
#         n_conflits = self.conflict3("Hydr. Structures" , hyd_struct_in_cells,
#                       "Hydr. Structures" , hyd_struct_out_cells, 
#                       "Hyd. Struct in-cell and Hyd. Struct out-cell in same element")  
# 
#         n_conflits = self.conflict3("Hydr. Structures" , hyd_struct_in_cells,
#                       "Channels (Right Bank)" , channels_right_cells, 
#                       "Hyd. Struc in-cell and Channel Right Bank in same cell")   
#         n_conflits = self.conflict3("Hydr. Structures" , hyd_struct_in_cells, 
#                       "Levees" , levees_cells, 
#                       "Hyd. Struc in-cell and Levee in same element (not recomended)")         
# 
#         n_conflits = self.conflict3("Hydr. Structures" , hyd_struct_in_cells, 
#                       "Mult. Channels" , mult_channels_cells, 
#                       "Hyd. Struc in-cell and Multiple Channel in same cell")  
#                
#         n_conflits = self.conflict3("Hydr. Structures" , hyd_struct_in_cells, 
#                       "Storm Drain Inlets" , storm_inlets_cells, 
#                       "Hyd. Struc in-cell and Storm Drain Inlet in same cell")         
# 
#         n_conflits = self.conflict3("Hydr. Structures" , hyd_struct_in_cells, 
#                       "Streets", street_cells, 
#                       "Hyd. Struct in-cell and Street in same cell")         
# 
#         n_conflits = self.conflict3("Hydr. Structures" , hyd_struct_out_cells,
#                       "Streets", street_cells, 
#                       "Hyd. Struct out-cell and Streett in same cell") 
#         
#         n_conflits = self.conflict3("Hydr. Structures" , hyd_struct_out_cells, 
#                       "Hydr. Structures" , hyd_struct_out_cells, 
#                       "More than one Hyd. Struc out-cell in same element")         
# 
#         n_conflits = self.conflict3("Hydr. Structures" , hyd_struct_out_cells,
#                       "Channels (Right Bank)" , channels_right_cells, 
#                       "Hyd. Struc out-cell and Channel Right Bank in same cell")   
# 
#         n_conflits = self.conflict3("Hydr. Structures" , hyd_struct_out_cells,
#                       "Levees" , levees_cells,
#                       "Hyd. Struct out-cell and Levee in same element (not recomended)")           
# 
#         n_conflits = self.conflict3("Hydr. Structures" , hyd_struct_out_cells,
#                       "Mult. Channels" , mult_channels_cells, 
#                       "Hyd. Struct out-cell and Multiple Channel in same cell")  
# 
#         n_conflits = self.conflict3("Hydr. Structures" , hyd_struct_out_cells,
#                       "Storm Drain Outfalls" , storm_outfalls_cells, 
#                       "Hyd. Struct out-cell and Storm Drain Outlet in same cell (not recomended)")  
#         
#         
#     # Channels conflicts:
#     
# 
#         n_conflits = self.conflict3("Channels (Left Bank)" , chennels_left_cells, 
#                       "Channels (Left Bank)" , chennels_left_cells, 
#                       "2 or more Channel Left Banks in same cell")        
# 
#         n_conflits = self.conflict3("Channels (Left Bank)" , chennels_left_cells, 
#                       "Channels (Right Bank)" , channels_right_cells, 
#                       "Channel Left Bank and Channel Right Bank in same cell")        
# 
# 
#         n_conflits = self.conflict3("Channels (Left Bank)" , chennels_left_cells, 
#                       "Levees" , levees_cells, 
#                       "Channel Left Banks and Levee in same cell")        
# 
#         n_conflits = self.conflict3("Channels (Left Bank)" , chennels_left_cells, 
#                       "Mult. Channels" , mult_channels_cells, 
#                       "Channel Left Banks and Multiple Channel in same cell")        
#         n_conflits = self.conflict3("Channels (Right Bank)" , channels_right_cells, 
#                       "Storm Drain Inlets" , storm_inlets_cells, 
#                       "Channel Right Bank and Storm Drain Inlet same cell") 
# 
#         n_conflits = self.conflict3("Channels (Left Bank)" , chennels_left_cells, 
#                       "Streets", street_cells, 
#                       "Channel Left Banks and Street in same cell")        
# 
#         n_conflits = self.conflict3("Channels (Right Bank)" , channels_right_cells, 
#                       "Streets", street_cells, 
#                       "Channel Right Bank and Street in same cell")  
#         
#         # TODO: left bank and right bank are in same attribute, this is wrong!!
#         n_conflits = self.conflict3("Channels (Right Bank)" , channels_right_cells, 
#                        "Channels (Right Bank)" , channels_right_cells, 
#                       "2 or more Channel Right Banks in same cell")   
# 
#         n_conflits = self.conflict3("Channels (Right Bank)" , channels_right_cells, 
#                       "Levees" , levees_cells, 
#                       "Channel Right Bank and Levee in same cell")   
# 
#         n_conflits = self.conflict3("Channels (Right Bank)" , channels_right_cells, 
#                       "Mult. Channels" , mult_channels_cells, 
#                       "Channel Right Bank and Multiple Channel same cell") 
# 
#         n_conflits = self.conflict3("Channels (Right Bank)" , channels_right_cells, 
#                       "Storm Drain Outfalls" , storm_outfalls_cells, 
#                       "Channel Right Bank and Storm Drain Outfall same cell") 
#               
#     # Right bank Channels conflicts:
#     
#     
#     # Levee conflicts:
# 
#         n_conflits = self.conflict3("Levees" , levees_cells, 
#                       "Levees" , levees_cells, 
#                       "2 or more Levees in same cell")  
# 
#         n_conflits = self.conflict3("Levees" , levees_cells, 
#                       "Mult. Channels" , mult_channels_cells, 
#                       "Levee and Multiple Channels in same cell")  
# 
#         n_conflits = self.conflict3("Levees" , levees_cells, 
#                       "Storm Drain Inlets" , storm_inlets_cells, 
#                       "Levee and Strom Drain Inlet in same cell")  
# 
#         n_conflits = self.conflict3("Levees" , levees_cells, 
#                       "Storm Drain Outfalls" , storm_outfalls_cells, 
#                       "Levee and Strom Drain Outfall in same cell")  
# 
#     # Multiple Channels conflicts:
# 
# 
#         n_conflits = self.conflict3("Mult. Channels" , mult_channels_cells, 
#                       "Mult. Channels" , mult_channels_cells, 
#                       "2 or more Multiple Channels in same cell") 
# 
#         n_conflits = self.conflict3("Mult. Channels" , mult_channels_cells, 
#                       "Storm Drain Inlets" , storm_inlets_cells, 
#                       "Multiple Channels and Storm Drain Inlet in same cell")  
# 
#         n_conflits = self.conflict3("Mult. Channels" , mult_channels_cells, 
#                       "Storm Drain Outfalls" , storm_outfalls_cells, 
#                       "Multiple Channels and Strom Drain Outfall in same cell") 
# 
#         n_conflits = self.conflict3("Mult. Channels" , mult_channels_cells, 
#                       "Streets", street_cells, 
#                       "Multiple Channels and Street in same cell") 
# 
#     
#     # Storm Drain inlets conflicts:
#         
#         n_conflits = self.conflict3("Storm Drain Inlets" , storm_inlets_cells, 
#                       "Storm Drain Inlets" , storm_inlets_cells, 
#                       "2 or more Storm Drain Inlets in same cell")         
# 
#         n_conflits = self.conflict3("Storm Drain Inlets" , storm_inlets_cells, 
#                       "Storm Drain Outfalls" , storm_outfalls_cells, 
#                       "Storm Drain Inlet and Storm Drain Outfall in same cell")         
#   
#            
#     # Storm Drain outfalls conflicts:
# 
#         n_conflits = self.conflict3("Storm Drain Outfalls" , storm_outfalls_cells, 
#                       "Storm Drain Outfalls" , storm_outfalls_cells, 
#                       "2 or more Storm Drain Outfalls in same cell")            
#         
#     # Street conflicts:
# 
#         n_conflits = self.conflict3("Streets", street_cells,  
#                       "Streets", street_cells, 
#                       "2 or more Streets in same cell") 
#............................................................        
        
        
                   
#############################
    # Inflow conflicts:

        self.conflict4("Inflows", "inflow_cells", "grid_fid", 
                      "Inflows" , "inflow_cells", "grid_fid", 
                      "2 or more inflows")

        self.conflict4("Inflows", "inflow_cells", "grid_fid", 
                      "Outflows" , "outflow_cells", "grid_fid", 
                      "Inflow and outflow in same cell")
        
        self.conflict4("Inflows", "inflow_cells", "grid_fid", 
                      "Reduction Factors" , "blocked_cells", "grid_fid", 
                      "Inflow and Reduction Factors in same cell (check partial ARF, full ARF, or WRF)")        
        
        self.conflict4("Inflows", "inflow_cells", "grid_fid", 
                      "Hydr. Structures" , "struct", "inflonod", 
                      "Inflow and Hyd. Struct in-cell in same cell")        

        self.conflict4("Inflows", "inflow_cells", "grid_fid", 
                      "Hydr. Structures" , "struct", "outflonod", 
                      "Inflow and Hyd. Struct out-cell in same cell")        

        self.conflict4("Inflows", "inflow_cells", "grid_fid", 
                      "Channels (Left Bank)" , "chan_elems", "fid", 
                      "Inflow and Channel Left Bank in same cell")        

        self.conflict4("Inflows", "inflow_cells", "grid_fid", 
                      "Channels (Right Bank)" , "chan_elems", "rbankgrid", 
                      "Inflow and Channel Right Bank in same cell")   
        
        self.conflict4("Inflows", "inflow_cells", "grid_fid", 
                      "Levees" , "levee_data", "grid_fid", 
                      "Inflow and levee in same cell")  

        self.conflict4("Inflows", "inflow_cells", "grid_fid", 
                      "Mult. Channels" , "mult_cells", "grid_fid", 
                      "Inflow and Multiple Channels in same cell")  

        self.conflict4("Inflows", "inflow_cells", "grid_fid", 
                      "Storm Drain Inlets" , "swmmflo", "swmm_jt", 
                      "Inflow and Storm Drain Inlet in same cell")  

        self.conflict4("Inflows", "inflow_cells", "grid_fid", 
                      "Storm Drain Outfalls" , "swmmoutf", "grid_fid", 
                      "Inflow and Storm Drain Outfall in same cell") 
        
        
    # Outflow conflicts: 
        self.conflict4("Outflows", "outflow_cells", "grid_fid", 
                      "Outflows", "outflow_cells", "grid_fid", 
                      "2 or more outflows")        

        self.conflict4("Outflows", "outflow_cells", "grid_fid", 
                      "Reduction Factors" , "blocked_cells", "grid_fid", 
                      "Outflow and Reduction Factors in same cell (check partial ARF, full ARF, or WRF)")  
                
#         repeats = self.conflict_outflow_fullARF()
#         if repeats:
#             for r in repeats:
#                 self.errors.append([str(r), "Outflows", "Full ARF", "Outflow(s) and full ARF in same cell"])                   
#          
#         repeats = self.conflict_outflow_partialARF()
#         if repeats:
#             for r in repeats:
#                 self.errors.append([str(r), "Outflows", "Partial ARF", "Outflow(s) and partial ARF in same cell"])                   
        
        self.conflict4("Outflows", "outflow_cells", "grid_fid", 
                      "Hydr. Structures" , "struct", "inflonod", 
                      "Outflow and Hyd. Struct in-cell in same cell")        

        self.conflict4("Outflows", "outflow_cells", "grid_fid", 
                      "Hydr. Structures" , "struct", "outflonod", 
                      "Outflow and Hyd. Struct out-cell in same cell")  

        self.conflict4("Outflows", "outflow_cells", "grid_fid", 
                      "Channels (Left Bank)" , "chan_elems", "fid", 
                      "Outflow and Channel Left Bank in same cell")        

        self.conflict4("Outflows", "outflow_cells", "grid_fid", 
                      "Channels (Right Bank)" , "chan_elems", "rbankgrid", 
                      "Outflow and Channel Right Bank in same cell")   
                
        self.conflict4("Outflows", "outflow_cells", "grid_fid", 
                      "Levees" , "levee_data", "grid_fid", 
                      "Outflow and levee in same cell") 
        
        self.conflict4("Outflows", "outflow_cells", "grid_fid", 
                      "Mult. Channels" , "mult_cells", "grid_fid", 
                      "Outflow and Multiple Channels in same cell") 

        self.conflict4("Outflows", "outflow_cells", "grid_fid", 
                      "Storm Drain Inlets" , "swmmflo", "swmm_jt", 
                      "Outflow and Storm Drain Inlet in same cell")  
 
        self.conflict4("Outflows", "outflow_cells", "grid_fid", 
                      "Storm Drain Outfalls" , "swmmoutf", "grid_fid", 
                      "Outflow and Storm Drain Outfall in same cell") 

        self.conflict4( "Outflows" , "outflow_cells", "grid_fid", 
                       "Streets", "street_seg", "igridn", 
                       "Outflow and Street in same cell")
        
    # Reduction Factors conflicts: 
        
        self.conflict4("Reduction Factors", "blocked_cells", "grid_fid", 
                      "Reduction Factors" , "blocked_cells", "grid_fid", 
                      "Duplicate Reduction Factors in same cell (check partial ARF, full ARF, or WRF)")  

        self.conflict4("Reduction Factors", "blocked_cells", "grid_fid", 
                      "Hydr. Structures" , "struct", "inflonod", 
                      "Reduction Factors and Hyd. Struct in-cell in same cell (not recomended)")            
        
        self.conflict4("Reduction Factors", "blocked_cells", "grid_fid", 
                      "Hydr. Structures" , "struct", "outflonod", 
                      "Reduction Factors and Hyd. Struc out-cell in same cell (not recomended)")         

        self.conflict4("Reduction Factors", "blocked_cells", "grid_fid", 
                      "Channels (Left Bank)" , "chan_elems", "fid", 
                      "Reduction Factors and Channel Left Bank in same cell")        

        self.conflict4("Reduction Factors", "blocked_cells", "grid_fid", 
                      "Channels (Right Bank)" , "chan_elems", "rbankgrid", 
                      "Reduction Factors and Channel Right Bank in same cell")   

        self.conflict4("Reduction Factors", "blocked_cells", "grid_fid", 
                      "Levees" , "levee_data", "grid_fid", 
                      "Reduction Factors and Levees in same cell (not recomended)")         

        self.conflict4("Reduction Factors", "blocked_cells", "grid_fid", 
                      "Mult. Channels" , "mult_cells", "grid_fid", 
                      "Reduction Factors and Multiple Channels in same cell (not recomended)")         

        self.conflict4("Reduction Factors", "blocked_cells", "grid_fid", 
                      "Storm Drain Inlets" , "swmmflo", "swmm_jt", 
                      "Reduction Factors and Storm Drain Inlet in same cell (not recomended)") 

        self.conflict4("Reduction Factors", "blocked_cells", "grid_fid", 
                      "Storm Drain Outfalls" , "swmmoutf", "grid_fid", 
                      "Reduction Factors and Storm Drain Outfall in same cell (not recomended)") 
        
    # Full ARF conflicts: 
    # Partial ARF conflicts: 
    # WRF conflicts:

    # Hydraulic Structures conflicts:

        self.conflict4("Hydr. Structures" , "struct", "inflonod",
                      "Hydr. Structures" , "struct", "inflonod", 
                      "More than one Hyd. Struct in-cell in same element")            
        
        self.conflict4("Hydr. Structures" , "struct", "outflonod", 
                      "Hydr. Structures" , "struct", "outflonod", 
                      "More than one Hyd. Struc out-cell in same element")         

        self.conflict4("Hydr. Structures" , "struct", "inflonod",
                      "Hydr. Structures" , "struct", "outflonod", 
                      "Hyd. Struct in-cell and Hyd. Struct out-cell in same element")  

        self.conflict4("Hydr. Structures" , "struct", "inflonod",
                      "Channels (Right Bank)" , "chan_elems", "rbankgrid", 
                      "Hyd. Struc in-cell and Channel Right Bank in same cell")   

        self.conflict4("Hydr. Structures" , "struct", "outflonod",
                      "Channels (Right Bank)" , "chan_elems", "rbankgrid", 
                      "Hyd. Struc out-cell and Channel Right Bank in same cell")   

        self.conflict4("Hydr. Structures" , "struct", "inflonod", 
                      "Levees" , "levee_data", "grid_fid", 
                      "Hyd. Struc in-cell and Levee in same element (not recomended)")         

        self.conflict4("Hydr. Structures" , "struct", "outflonod",
                      "Levees" , "levee_data", "grid_fid",
                      "Hyd. Struct out-cell and Levee in same element (not recomended)")           

        self.conflict4("Hydr. Structures" , "struct", "inflonod", 
                      "Mult. Channels" , "mult_cells", "grid_fid", 
                      "Hyd. Struc in-cell and Multiple Channel in same cell")         

        self.conflict4("Hydr. Structures" , "struct", "outflonod",
                      "Mult. Channels" , "mult_cells", "grid_fid", 
                      "Hyd. Struct out-cell and Multiple Channel in same cell")  
        
        self.conflict4("Hydr. Structures" , "struct", "inflonod", 
                      "Storm Drain Inlets" , "swmmflo", "swmm_jt", 
                      "Hyd. Struc in-cell and Storm Drain Inlet in same cell")         

        self.conflict4("Hydr. Structures" , "struct", "outflonod",
                      "Storm Drain Outfalls" , "swmmoutf", "grid_fid", 
                      "Hyd. Struct out-cell and Storm Drain Outlet in same cell (not recomended)")  

        self.conflict4("Hydr. Structures" , "struct", "inflonod", 
                      "Streets", "street_seg", "igridn", 
                      "Hyd. Struc in-cell and Street in same cell")         

        self.conflict4("Hydr. Structures" , "struct", "outflonod",
                      "Streets", "street_seg", "igridn", 
                      "Hyd. Struct out-cell and Streett in same cell") 
        
    # Channels conflicts:
    

        self.conflict4("Channels (Left Bank)" , "chan_elems", "fid", 
                      "Channels (Left Bank)" , "chan_elems", "fid", 
                      "2 or more Channel Left Banks in same cell")        

        self.conflict4("Channels (Left Bank)" , "chan_elems", "fid", 
                      "Channels (Right Bank)" , "chan_elems", "rbankgrid", 
                      "Channel Left Bank and Channel Right Bank in same cell")        

        # TODO: left bank and right bank are in same attribute, this is wrong!!
        self.conflict4("Channels (Right Bank)" , "chan_elems", "rbankgrid", 
                       "Channels (Right Bank)" , "chan_elems", "rbankgrid", 
                      "2 or more Channel Right Banks in same cell")   

        self.conflict4("Channels (Left Bank)" , "chan_elems", "fid", 
                      "Levees" , "levee_data", "grid_fid", 
                      "Channel Left Bank and Levee in same cell")        

        self.conflict4("Channels (Right Bank)" , "chan_elems", "rbankgrid", 
                      "Levees" , "levee_data", "grid_fid", 
                      "Channel Right Bank and Levee in same cell")   

        self.conflict4("Channels (Left Bank)" , "chan_elems", "fid", 
                      "Mult. Channels" , "mult_cells", "grid_fid", 
                      "Channel Left Bank and Multiple Channel in same cell")        

        self.conflict4("Channels (Right Bank)" , "chan_elems", "rbankgrid", 
                      "Mult. Channels" , "mult_cells", "grid_fid", 
                      "Channel Right Bank and Multiple Channel same cell") 
              
        self.conflict4("Channels (Right Bank)" , "chan_elems", "rbankgrid", 
                      "Storm Drain Inlets" , "swmmflo", "swmm_jt", 
                      "Channel Right Bank and Storm Drain Inlet same cell") 

        self.conflict4("Channels (Right Bank)" , "chan_elems", "rbankgrid", 
                      "Storm Drain Outfalls" , "swmmoutf", "grid_fid", 
                      "Channel Right Bank and Storm Drain Outfall same cell") 

        self.conflict4("Channels (Left Bank)" , "chan_elems", "fid", 
                      "Streets", "street_seg", "igridn", 
                      "Channel Left Bank and Street in same cell")        

        self.conflict4("Channels (Right Bank)" , "chan_elems", "rbankgrid", 
                      "Streets", "street_seg", "igridn", 
                      "Channel Right Bank and Street in same cell")  
         
    # Right bank Channels conflicts:
    
    
    # Levee conflicts:

        self.conflict4("Levees" , "levee_data", "grid_fid", 
                      "Levees" , "levee_data", "grid_fid", 
                      "2 or more Levees in same cell (review)")  

        self.conflict4("Levees" , "levee_data", "grid_fid", 
                      "Mult. Channels" , "mult_cells", "grid_fid", 
                      "Levee and Multiple Channels in same cell")  

        self.conflict4("Levees" , "levee_data", "grid_fid", 
                      "Storm Drain Inlets" , "swmmflo", "swmm_jt", 
                      "Levee and Storm Drain Inlet in same cell")  

        self.conflict4("Levees" , "levee_data", "grid_fid", 
                      "Storm Drain Outfalls" , "swmmoutf", "grid_fid", 
                      "Levee and Storm Drain Outfall in same cell")  

    # Multiple Channels conflicts:


        self.conflict4("Mult. Channels" , "mult_cells", "grid_fid", 
                      "Mult. Channels" , "mult_cells", "grid_fid", 
                      "2 or more Multiple Channels in same cell") 

        self.conflict4("Mult. Channels" , "mult_cells", "grid_fid", 
                      "Storm Drain Inlets" , "swmmflo", "swmm_jt", 
                      "Multiple Channels and Storm Drain Inlet in same cell")  

        self.conflict4("Mult. Channels" , "mult_cells", "grid_fid", 
                      "Storm Drain Outfalls" , "swmmoutf", "grid_fid", 
                      "Multiple Channels and Storm Drain Outfall in same cell") 

        self.conflict4("Mult. Channels" , "mult_cells", "grid_fid", 
                      "Streets", "street_seg", "igridn", 
                      "Multiple Channels and Street in same cell") 

    
    # Storm Drain inlets conflicts:
        
        self.conflict4("Storm Drain Inlets" , "swmmflo", "swmm_jt", 
                      "Storm Drain Inlets" , "swmmflo", "swmm_jt", 
                      "2 or more Storm Drain Inlets in same cell")         

        self.conflict4("Storm Drain Inlets" , "swmmflo", "swmm_jt", 
                      "Storm Drain Outfalls" , "swmmoutf", "grid_fid", 
                      "Storm Drain Inlet and Storm Drain Outfall in same cell")         
  
           
    # Storm Drain outfalls conflicts:

        self.conflict4("Storm Drain Outfalls" , "swmmoutf", "grid_fid", 
                      "Storm Drain Outfalls" , "swmmoutf", "grid_fid", 
                      "2 or more Storm Drain Outfalls in same cell")            
        
    # Street conflicts:

        self.conflict4("Streets", "street_seg", "igridn",  
                      "Streets", "street_seg", "igridn", 
                      "2 or more Streets in same cell") 
        
        
        self.setWindowTitle("Errors and Warnings for " + self.issue1 + " components with " + self.issue2 + " components")
        
#############################                
    def get_n_cells(self, table, cell, n):
        sqr = "SELECT {0} FROM {1} ORDER BY {0} LIMIT {2}".format(cell, table, n.text())
        return self.gutils.execute(sqr).fetchall()        
          
    def populate_elements_cbo(self):
        self.elements_cbo.clear()
        self.elements_cbo.addItem(" ")
        for x in self.errors:
            if self.elements_cbo.findText(x[0].strip()) == -1:
                self.elements_cbo.addItem(x[0].strip())
        self.elements_cbo.model().sort(0)
                
    def populate_errors_cbo(self):
        self.errors_cbo.clear()
        self.errors_cbo.addItem(" ")
        self.errors_cbo.addItem("All")
        for x in self.errors:
            if self.errors_cbo.findText(x[1].strip()) == -1:
                self.errors_cbo.addItem(x[1].strip())
            if self.errors_cbo.findText(x[2].strip()) == -1:
                self.errors_cbo.addItem(x[2].strip())                
        self.errors_cbo.model().sort(0)                                   

    def component1_cbo_activated(self):
        self.loadIssuePairs()
        
    def component2_cbo_activated(self):
        self.loadIssuePairs()         
        
    def loadIssuePairs(self): 
        QApplication.setOverrideCursor(Qt.WaitCursor) 
        self.description_tblw.setRowCount(0)
        comp1 = self.component1_cbo.currentText()
        comp2 = self.component2_cbo.currentText()
        for item in self.errors:
            if (  (item[1] == comp1 and item[2] == comp2)  or
                  (item[1] == comp2 and item[2] == comp1) or
                  
                  (comp1 == "" and (item[1] == comp2 or item[2] == comp2)) or
                  (comp2 == "" and (item[1] == comp1 or item[2] == comp1)) or
                  
                  
                  (comp1 == "All" and comp2 == "All") or
                  (comp1 == "All" and comp2 == "") or
                  (comp1 == "" and comp2 == "All") or
                  
                  
                  (comp1 == "All" and (item[1] == comp2 or item[2] == comp2)) or
                  (comp2 == "All" and (item[1] == comp1 or item[2] == comp1))
                ): 
                rowPosition = self.description_tblw.rowCount()
                self.description_tblw.insertRow(rowPosition)   
                itm = QTableWidgetItem()
                itm.setData(Qt.EditRole, item[0].strip())                 
                self.description_tblw.setItem(rowPosition , 0, itm)
                itm = QTableWidgetItem() 
                itm.setData(Qt.EditRole, item[3])  
                self.description_tblw.setItem(rowPosition , 2, itm)  
            else:
                self.lyrs.clear_rubber()       
        self.errors_cbo.setCurrentIndex(0)
        self.elements_cbo.setCurrentIndex(0)
        if self.description_tblw.rowCount() > 0:
            self.description_tblw.selectRow(0)
            cell  = self.description_tblw.item(0,0).text()
            self.find_cell(cell) 
        QApplication.restoreOverrideCursor()   
         
    def elements_cbo_activated(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)   
        self.description_tblw.setRowCount(0)
        nElems = self.elements_cbo.count()
        if nElems > 0:
            cell = self.elements_cbo.currentText().strip()
            for item in self.errors:
                if item[0].strip() == cell:
                    rowPosition = self.description_tblw.rowCount()
                    self.description_tblw.insertRow(rowPosition)   
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[0].strip())                 
                    self.description_tblw.setItem(rowPosition , 0, itm)
                    itm = QTableWidgetItem() 
                    itm.setData(Qt.EditRole, item[3])  
                    self.description_tblw.setItem(rowPosition , 2, itm) 
            self.component1_cbo.setCurrentIndex(0)
            self.component2_cbo.setCurrentIndex(0)
            self.errors_cbo.setCurrentIndex(0)
            self.find_cell(cell)             
        QApplication.restoreOverrideCursor()
        
    def errors_cbo_activated(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)   
        self.description_tblw.setRowCount(0)
        nElems = self.errors_cbo.count()
        if nElems > 0:
            for item in self.errors:
                if ( item[1].strip() == self.errors_cbo.currentText().strip() or
                     item[2].strip() == self.errors_cbo.currentText().strip() or  
                     self.errors_cbo.currentText().strip() == "All"): 
                    
                    rowPosition = self.description_tblw.rowCount()
                    self.description_tblw.insertRow(rowPosition)   
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, item[0].strip())                 
                    self.description_tblw.setItem(rowPosition , 0, itm)
                    itm = QTableWidgetItem() 
                    itm.setData(Qt.EditRole, item[3])  
                    self.description_tblw.setItem(rowPosition , 2, itm) 
                else:
                    self.lyrs.clear_rubber()       
        self.component1_cbo.setCurrentIndex(0)
        self.component2_cbo.setCurrentIndex(0)
        QApplication.restoreOverrideCursor()
        
    def find_cell_clicked(self):
        cell = self.elements_cbo.currentText()
        self.find_cell(cell)   

    def find_cell(self, cell):
        try: 
            grid = self.lyrs.data['grid']['qlyr']
            if grid is not None:
                if grid:
                    if cell != '':
                        cell = int(cell)
                        if len(grid) >= cell and cell > 0:
                            self.lyrs.show_feat_rubber(grid.id(), cell, QColor(Qt.yellow))
                            self.currentCell = next(grid.getFeatures(QgsFeatureRequest(cell)))
                            x, y = self.currentCell.geometry().centroid().asPoint()
                            if x < self.ext.xMinimum() or x > self.ext.xMaximum() or y < self.ext.yMinimum() or y > self.ext.yMaximum():
                                center_canvas(self.iface, x, y)
                                self.update_extent()
                        else:
                                self.lyrs.clear_rubber()                          
                    else:
                            self.lyrs.clear_rubber()              
        except ValueError:
            self.uc.bar_warn('Cell ' + str(cell) + ' not valid.')
            self.lyrs.clear_rubber()    
            pass  
            
            
    def description_tblw_cell_clicked(self, row, column):
        cell  = self.description_tblw.item(row,0).text()
        self.find_cell(cell)        
 
    def zoom_in(self):
        if self.currentCell:
            x, y = self.currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface,  0.4)
            self.update_extent()
            
    def zoom_out(self):
        if self.currentCell:
            x, y = self.currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)        
            zoom(self.iface,  -0.4) 
            self.update_extent()
        
    def update_extent(self):  
        self.ext = self.iface.mapCanvas().extent()                 

    def copy_to_clipboard(self):
        copy_tablewidget_selection(self.description_tblw)
     
    def conflict(self, comp1, table1, cell_1, comp2, table2, cell_2, description):
        cells1 = []
        cells2 = []
        repeated = [] 
        sqr1 = "SELECT {0} FROM {1}".format(cell_1, table1)
        sqr2 = "SELECT {0} FROM {1}".format(cell_2, table2)
        rows1 = self.gutils.execute(sqr1).fetchall()
        rows2 = self.gutils.execute(sqr2).fetchall()
        if not rows1 or not rows2:
            pass
        else:
            for row in rows1:
                cells1.append(row)
            for row in rows2:
                cells2.append(row)                
            size1 = len(cells1)
            size2 = len(cells2)
            
            if comp1 == comp2:
                for i in range(size1): 
                    k = i + 1
                    for j in range(k, size1): 
                        if cells1[i][0] == cells1[j][0] and cells1[i][0] not in repeated: 
                            repeated.append(cells1[i][0]) 
                            break
            else:
                for i in range(size1): 
                    for j in range(size2):  
                        if cells1[i][0] == cells2[j][0] and cells1[i][0] not in repeated: 
                            repeated.append(cells1[i][0]) 
                            break
        if repeated:
            for r in repeated:
                self.errors.append([str(r), comp1, comp2, description]) 


    def conflict2(self, comp1, table1, cell_1, comp2, table2, cell_2, description):

        repeated = [] 
        rows1 = []
        rows2 = []
        
        sqr1 = "SELECT {0} FROM {1} ORDER BY {0} LIMIT {2}".format(cell_1, table1, self.numErrors.text())
        sqr2 = "SELECT {0} FROM {1} ORDER BY {0} LIMIT {2}".format(cell_2, table2, self.numErrors.text())
        
        rows1 = self.gutils.execute(sqr1).fetchall()
        rows2 = self.gutils.execute(sqr2).fetchall()        
        
        
#         r1 = self.gutils.execute(sqr1).fetchall()
#         r2 = self.gutils.execute(sqr2).fetchall()        
#         
#         size1 = len(r1)
#         size2 = len(r2) 
#         
#         grid = self.lyrs.data['grid']['qlyr']
#         for i in range(size1):
#             feat = next(grid.getFeatures(QgsFeatureRequest(r1[i][0])))
#             x, y = feat.geometry().centroid().asPoint()  
#             if x >  self.ext.xMinimum() and x  < self.ext.xMaximum() and y > self.ext.yMinimum() and y < self.ext.yMaximum():
#                 rows1.append(r1[i][0])     
#  
#         for i in range(size2):
#             feat = next(grid.getFeatures(QgsFeatureRequest(r2[i][0])))
#             x, y = feat.geometry().centroid().asPoint()  
#             if x >  self.ext.xMinimum() and x  < self.ext.xMaximum() and y > self.ext.yMinimum() and y < self.ext.yMaximum():
#                 rows2.append(r2[i][0])         

    
        size1 = len(rows1)
        size2 = len(rows2) 

        if not rows1 or not rows2:
            pass
        else:
            if comp1 == comp2:
                for i in range(size1-2): 
                    if rows1[i][0] == rows1[i+1][0]:
                        if rows1[i][0] not in repeated:
                            repeated.append(rows1[i][0]) 
            else:
                try:
                    k = 0
                    for i in range(size1):
                        while True: 
                            if rows2[k][0] < rows1[i][0]:
                                if k < size2-1:
                                    k += 1
                                    continue
                                else:
                                    k = 0
                                    break
                            elif rows2[k][0]> rows1[i][0]:
                                break                                
                            elif rows1[i][0] not in repeated: 
                                repeated.append(rows1[i][0])
                            if k < size2-1:
                                k += 1
                            else:
                                k = 0
                                break

                except ValueError: 
                    pass
                           
        if repeated:
            for r in repeated:
                self.errors.append([str(r), comp1, comp2, description]) 
            
    def conflict3(self, comp1, rows1, comp2, rows2, description):

        repeated = [] 

        size1 = len(rows1)
        size2 = len(rows2) 

        if not rows1 or not rows2:
            return 0
        else:
            if comp1 == comp2:
                for i in range(size1-2): 
                    if rows1[i][0] == rows1[i+1][0]:
                        if rows1[i][0] not in repeated:
                            repeated.append(rows1[i][0]) 
            else:
                try:
                    k = 0
                    for i in range(size1):
                        while True: 
                            if rows2[k][0] < rows1[i][0]:
                                if k < size2-1:
                                    k += 1
                                    continue
                                else:
                                    k = 0
                                    break
                            elif rows2[k][0]> rows1[i][0]:
                                break                                
                            elif rows1[i][0] not in repeated: 
                                repeated.append(rows1[i][0])
                            if k < size2-1:
                                k += 1
                            else:
                                k = 0
                                break

                except ValueError: 
                    pass
                           
        if repeated:
            for r in repeated:
                self.errors.append([str(r), comp1, comp2, description])     
        return len(repeated)    

    def conflict4(self, comp1, table1, cell_1, comp2, table2, cell_2, description):
        
        cond1 = self.issue1 == "All" and self.issue2 == "All"
        cond2 = self.issue1 == "All" and self.issue2 == ""
        cond3 = self.issue1 == "" and self.issue2 == "All"
        cond4 = self.issue1 == "All" and (comp1 == self.issue2 or comp2 == self.issue2)
        cond5 = self.issue2 == "All" and (comp1 == self.issue1 or comp2 == self.issue1)
        cond6 = (comp1 == self.issue1 and comp2 in self.issue2) or (comp2 == self.issue1 and comp1 in self.issue2)
      
        if cond1 or cond2 or cond3 or cond4 or cond5 or cond6:
            repeated = []
            
            if table1 == table2 and cell_1 == cell_2:
                sql = '''SELECT {0}, COUNT(*) 
                        FROM {1} 
                        GROUP BY {0}
                        HAVING COUNT(*) > 1 ORDER BY {0}
                    '''.format(cell_1, table1)            
               
            else:    
                sql = '''SELECT {0} FROM {1} 
                WHERE {0} IN 
                (
                    SELECT {0}
                    FROM {1}
                    INTERSECT
                    SELECT {2}
                    FROM {3}
                ) ORDER BY {0}'''.format(cell_1, table1, cell_2, table2)
                
            rows = self.gutils.execute(sql).fetchall()
            
            if not rows: 
                pass
            else:
                size = len(rows)
                for i in range(size):   
                    if rows[i][0] not in repeated: 
                        repeated.append(rows[i][0]) 
            if repeated:
                for r in repeated:
                    self.errors.append([str(r), comp1, comp2, description]) 


    def conflict_inflow_partialARF(self):
        in_cells = []
        ARF_cells = []
        repeated = [] 
        inf = "SELECT grid_fid FROM inflow_cells"
        ARF = "SELECT grid_fid, arf FROM blocked_cells"
        in_rows = self.gutils.execute(inf).fetchall()
        ARF_rows = self.gutils.execute(ARF).fetchall()
        if not in_rows or not ARF_rows:
            return repeated
        else:
            for row in in_rows:
                in_cells.append(row)
            for row in ARF_rows:
                ARF_cells.append(row)                
            in_size = len(in_cells)
            ARF_size = len(ARF_cells)
            for i in range(in_size): 
                for j in range(ARF_size):  
                    if in_cells[i][0] == ARF_cells[j][0] and float(ARF_cells[j][1]) < 1.0 and in_cells[i][0] not in repeated: 
                        repeated.append(in_cells[i][0]) 
                        break
            return repeated    
        
    
    def conflict_outflow_partialARF(self):
        out_cells = []
        ARF_cells = []
        repeated = [] 
        outf = "SELECT grid_fid FROM outflow_cells"
        ARF = "SELECT grid_fid, arf FROM blocked_cells"
        out_rows = self.gutils.execute(outf).fetchall()
        ARF_rows = self.gutils.execute(ARF).fetchall()
        if not out_rows or not ARF_rows:
            return repeated
        else:
            for row in out_rows:
                out_cells.append(row)
            for row in ARF_rows:
                ARF_cells.append(row)                
            in_size = len(out_cells)
            ARF_size = len(ARF_cells)
            for i in range(in_size): 
                for j in range(ARF_size):  
                    if out_cells[i][0] == ARF_cells[j][0] and float(ARF_cells[j][1]) < 1.0 and out_cells[i][0] not in repeated: 
                        repeated.append(out_cells[i][0]) 
                        break
            return repeated

    def conflict_outfall_partialARF(self):
        out_cells = []
        ARF_cells = []
        repeated = [] 
        outf = "SELECT grid_fid FROM swmmoutf"
        ARF = "SELECT grid_fid, arf FROM blocked_cells"
        out_rows = self.gutils.execute(outf).fetchall()
        ARF_rows = self.gutils.execute(ARF).fetchall()
        if not out_rows or not ARF_rows:
            return repeated
        else:
            for row in out_rows:
                out_cells.append(row)
            for row in ARF_rows:
                ARF_cells.append(row)                
            in_size = len(out_cells)
            ARF_size = len(ARF_cells)
            for i in range(in_size): 
                for j in range(ARF_size):  
                    if out_cells[i][0] == ARF_cells[j][0] and float(ARF_cells[j][1]) < 1.0 and out_cells[i][0] not in repeated: 
                        repeated.append(out_cells[i][0]) 
                        break
            return repeated

    def conflict_inlet_partialARF(self):
        out_cells = []
        ARF_cells = []
        repeated = [] 
        outf = "SELECT swmm_jt FROM swmmflo"
        ARF = "SELECT grid_fid, arf FROM blocked_cells"
        out_rows = self.gutils.execute(outf).fetchall()
        ARF_rows = self.gutils.execute(ARF).fetchall()
        if not out_rows or not ARF_rows:
            return repeated
        else:
            for row in out_rows:
                out_cells.append(row)
            for row in ARF_rows:
                ARF_cells.append(row)                
            in_size = len(out_cells)
            ARF_size = len(ARF_cells)
            for i in range(in_size): 
                for j in range(ARF_size):  
                    if out_cells[i][0] == ARF_cells[j][0] and float(ARF_cells[j][1]) < 1.0 and out_cells[i][0] not in repeated: 
                        repeated.append(out_cells[i][0]) 
                        break
            return repeated
        
    def conflict_outflow_fullARF(self):
        out_cells = []
        ARF_cells = []
        repeated = [] 
        outf = "SELECT grid_fid FROM outflow_cells"
        ARF = "SELECT grid_fid, arf FROM blocked_cells"
        out_rows = self.gutils.execute(outf).fetchall()
        ARF_rows = self.gutils.execute(ARF).fetchall()
        if not out_rows or not ARF_rows:
            return repeated
        else:
            for row in out_rows:
                out_cells.append(row)
            for row in ARF_rows:
                ARF_cells.append(row)                
            in_size = len(out_cells)
            ARF_size = len(ARF_cells)
            for i in range(in_size): 
                for j in range(ARF_size):  
                    if out_cells[i][0] == ARF_cells[j][0] and float(ARF_cells[j][1]) == 1.0 and out_cells[i][0] not in repeated: 
                        repeated.append(out_cells[i][0]) 
                        break
            return repeated 















































































