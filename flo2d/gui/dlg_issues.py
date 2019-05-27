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
from qgis.core import * 
from qgis.PyQt.QtCore import Qt, QSettings, QVariant

# ( QgsFields, QgsField, QgsFeature, QgsVectorFileWriter, QgsFeatureRequest, 
#                         QgsWkbTypes, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer )
from qgis.PyQt.QtWidgets import QApplication, QDialogButtonBox, QInputDialog, QFileDialog, QTableWidgetItem
from .ui_utils import load_ui, set_icon, center_canvas, zoom
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..gui.dlg_sampling_xyz import SamplingXYZDialog
from ..gui.dlg_sampling_elev import SamplingElevDialog
from ..gui.dlg_sampling_buildings_elevations import SamplingBuildingsElevationsDialog
from ..flo2d_tools.grid_tools import grid_has_empty_elev
from qgis.PyQt.QtGui import QColor
from collections import OrderedDict
from pickle import FALSE
from msilib.schema import SelfReg

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
        self.populate_elements_cbo()
        self.populate_errors_cbo()
        self.loadIssues()

    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            
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
                                name = "Channel Bank Elev Diferences"
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
                                shapefile = self.debug_directory + "/Flooplain_Rim differences.shp"
                                name = "Flooplain_Rim differences"
                                fields = [['cell','I'], ['floodplain_elev','D'], ['rim_elev','D'], ['difference','D'], ['new_floodplain_elev','D']]
                                if self.create_points_shapefile(shapefile, name, fields, features):
                                    vlayer = self.iface.addVectorLayer(shapefile, "" , 'ogr')                                         
                                        
                                        
                            except Exception as e:
                                QApplication.restoreOverrideCursor()
                                self.uc.show_error("ERROR 170519.0705: error while reading " + file  + "!\n", e)                                                                     

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
                            self.errors.append([row[0], row[1], row[2]])  
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
 

    def populate_elements_cbo(self):
        self.elements_cbo.clear()
        for x in self.errors:
            if self.elements_cbo.findText(x[0].strip()) == -1:
                self.elements_cbo.addItem(x[0].strip())
        self.elements_cbo.model().sort(0)
                
    def populate_errors_cbo(self):
        self.errors_cbo.clear()
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
                        if cell != -999:                        
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
       
        
       
