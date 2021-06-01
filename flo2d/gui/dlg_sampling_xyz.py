# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import sys
import os
import stat
import time
import traceback

# import PyQt5.sip 
from qgis.core import (
        QgsWkbTypes, 
        Qgis, 
        QgsFeatureRequest, 
        QgsVectorLayer, 
        QgsField, 
        QgsFields, 
        QgsFeature, 
        QgsGeometry, 
        QgsPointXY, 
        QgsProject,
        QgsVectorFileWriter,
        QgsMarkerSymbol
    )
from qgis.PyQt.QtCore import QSettings, Qt, QVariant, QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QFileDialog, QApplication, QProgressBar, qApp, QMessageBox,  QPushButton, QLabel, QWidget
from plugins.processing.tools.vector import values
from qgis.PyQt import  QtCore, QtGui

from ..errors import Flo2dError
from .ui_utils import load_ui
from ..utils import get_file_path, time_taken, grid_index, get_grid_index, set_grid_index, clear_grid_index, is_grid_index
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..flo2d_tools.grid_tools import number_of_elements, fid_from_grid, adjacent_grid_elevations, render_grid_elevations
from pickle import TRUE
# from flo2d.__init__ import classFactory
# from ..flo2d import xxx

uiDialog, qtBaseClass = load_ui("sampling_xyz")
class SamplingXYZDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.con = con
        self.iface = iface
        self.lyrs = lyrs
        self.grid = self.lyrs.data["grid"]["qlyr"]
        
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)
        self.gpkg_path = self.gutils.get_gpkg_path()
        self.uc = UserCommunication(iface, "FLO-2D")
        self.current_lyr = None
        self.setup_layer_cbo()
        
        self.cell_size = float(self.gutils.get_cont_par("CELLSIZE"))
        grid_extent = self.grid.extent()
        self.xMinimum = grid_extent.xMinimum()
        self.yMinimum = grid_extent.yMinimum() 
        
        # connections
        self.points_cbo.currentIndexChanged.connect(self.populate_fields_cbo)
        self.points_layer_grp.clicked.connect(self.points_layer_selected)
        self.lidar_grp.clicked.connect(self.lidar_selected)

    def setup_layer_cbo(self):
        """
        Filter layer combo for points and connect field cbo.
        """
        try:
            lyrs = self.lyrs.list_group_vlayers()
            for l in lyrs:
                if l.geometryType() == QgsWkbTypes.PointGeometry:
                    if l.featureCount() != 0:
                        self.points_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                else:
                    pass
            self.populate_fields_cbo(self.points_cbo.currentIndex())
        except Exception as e:
            pass

    def populate_fields_cbo(self, idx):
        uri = self.points_cbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri)
        self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()
        self.fields_cbo.setLayer(self.current_lyr)
        self.fields_cbo.setCurrentIndex(0)

    def points_layer_selected(self):
        self.lidar_grp.setChecked(not self.points_layer_grp.isChecked())

    def lidar_selected(self):
        self.points_layer_grp.setChecked(not self.lidar_grp.isChecked())
        self.use_sql_chbox.setEnabled(self.lidar_grp.isChecked())
        self.use_all_radio.setEnabled(False)
        self.use_porcentage_radio.setEnabled(False)
        self.porcentage_dbox.setEnabled(False)
                   
    def interpolate_from_lidar(self):
        
        s = QSettings()
        last_dir = s.value("FLO-2D/lastLIDARDir", "")
        lidar_files, __ = QFileDialog.getOpenFileNames(
            None,
            "Select LIDAR files",
            directory=last_dir,
            filter="*.TXT ; *.DAT;;Normal text file (*.txt;*.TXT) ;;*.DAT;;All files (*)",
        )
        
        if not lidar_files:
            return
        s.setValue("FLO-2D/lastLIDARDir", os.path.dirname(lidar_files[0]))
        
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            elevs = {}
            read_error = "Error reading files:\n\n"
            outside_grid, inside_grid = 0, 0
            n_grid_cells = number_of_elements(self.gutils, self.grid)
   
            gid_indx = {}
            cells = self.gutils.execute("SELECT fid, col, row FROM grid").fetchall()
            for cell in cells:
                    gid_indx[cell[1], cell[2]] = [cell[0], 0.0, 0]

            start_time = time.time()

            statBar = self.iface.mainWindow().statusBar()
            statusLabel = QLabel()
            statBar.addWidget(statusLabel,5)   
            advanceBar = QProgressBar()
            advanceBar.setStyleSheet("QProgressBar::chunk { background-color: lightskyblue}")
            advanceBar.setAlignment(Qt.AlignCenter | Qt.AlignVCenter) 
            advanceBar.setMinimum(0)
            statBar.addWidget(advanceBar,2) 

            size = 0
            lines = 0
            for file in lidar_files: 
                file_size = os.path.getsize(file)
                with open(file, "r") as f:
                    line = f.readline()
                    
                    line_size = len(line) + 1
                size += file_size / line_size

            progress = self.uc.progress_bar2("Reading " + "{:,}".format(int(size)) + " lines from " + str(len(lidar_files)) + " files...", 0, len(lidar_files), 0)
            step = 50000   
            for i, file in enumerate(lidar_files,1):
            
                progress.setValue(i)
                # advanceBar.setValue(i) 
                 
                n_commas =  0
                n_spaces = 0             
 
                # See if comma or space delimited:
                with open(file, "r") as f:
                    while True:    
                        line = f.readline()
                        line = line.replace('\t', '') 
                        if line.strip() != "": 
                            n_commas = line.count(",")
                            if n_commas == 0:
                                n_spaces = len(line.split())
                            break

                if n_commas != 0 or n_spaces != 0:
                    # Read file: 
                    with open(file, "r") as f1:
                        try:
                            lines = f1.readlines()
                            n_lines = len(lines)     
                            statusLabel.setText('Reading  ' +  "{:,}".format(n_lines) + '  lines from ' +  '<FONT COLOR=blue>' + os.path.basename(file) + '</FONT>')     
                            advanceBar.setMaximum(n_lines)
                            
                            step = int(n_lines/ 20)

                            if n_lines > step:
                                advanceBar.setValue(int(step/2)) 
                                # self.iface.mainWindow().repaint()   
                                       
                            for i, line in enumerate(lines, 1): 
                            
                                if (int(i%step) == 0):                            
                                    advanceBar.setValue(i) 
                                    qApp.processEvents()
                                
                                line = line.replace('\t', '')                            
                                if n_commas == 0: # No commas, values separated by spaces.
                                    values = line.split()   
                                    n_values = len(values)
                                    if n_values == 3:
                                        xpp, ypp, zpp  = values
                                    elif n_values == 4:
                                        xpp, ypp, zpp, dummy  = values  
                                    elif n_values == 5:
                                        dummy1, xpp, ypp, zpp, dummy2  = values  
                                    else:
                                        break          
                                elif n_commas == 2:  # 3 columns.
                                    xpp, ypp, zpp  = line.split(",") 
                                elif n_commas == 3:  # 4 columns.
                                    xpp, ypp, zpp, dummy  = line.split(",") 
                                elif n_commas == 4:  # 5 columns.
                                    dummy1, xpp, ypp, zpp, dummy2  = line.split(",")  
                                else:
                                    break  
                                 
                                if self.use_sql_chbox.isChecked():
                                    cell = self.gutils.grid_on_point(xpp, ypp)
                                    if cell is not None:
                                        if cell in elevs:
                                            elevs[cell][0] += float(zpp)
                                            elevs[cell][1] += 1
                                        else:
                                            elevs[cell] = [float(zpp), 1]
                                        inside_grid += 1                         
                                    else:
                                        outside_grid += 1    
                                else: 
                                    col = int((float(xpp) - self.xMinimum)/self.cell_size) + 2
                                    row = int((float(ypp) - self.yMinimum)/self.cell_size) + 2                                    
                                    if (col, row) in gid_indx:
                                        gid_indx[col, row][1] += float(zpp)
                                        gid_indx[col, row][2] += 1
                                        inside_grid += 1   
                                    else:
                                        outside_grid += 1    
                                    
                        except ValueError:
                            read_error += os.path.basename(file) + "\n\n"


            self.uc.clear_bar_messages() 
            self.uc.bar_info("Updating grid elevations...")                        
            statBar.removeWidget(statusLabel)
            statBar.removeWidget(advanceBar)    
            qApp.processEvents()   
                                                                
            # Assign -9999 to all cell elevations prior to the assignment from LIDAR points: 
            self.gutils.execute("UPDATE grid SET elevation = -9999;")
            
            # Update cell elevations from LIDAR points:
            nope = []
            if self.use_sql_chbox.isChecked():
                if elevs:
                    for cell, value in elevs.items():
                        elevation = round(value[0]/value[1],4)
                        self.gutils.execute("UPDATE grid SET elevation = ? WHERE fid = ?;", (elevation, cell))      
                        
                    # Get non-assigned cells:
                    for i in range(1, n_grid_cells + 1):
                        if i not in elevs:
                            nope.append(i)
                        else:
                            pass                                            
            else:                 
                if inside_grid > 0:
                    for gi in gid_indx.items():
                        if gi[1][2] != 0:
                            elevation = round(gi[1][1]/gi[1][2],4)
                            self.gutils.execute("UPDATE grid SET elevation = ? WHERE fid = ?;", (elevation, gi[1][0]))         
                        else:
                            nope.append(gi[1][0])

            self.uc.clear_bar_messages()       
            QApplication.restoreOverrideCursor()    
            
            end_time = time.time()   
            time_passed = self.elapsed_time(start_time, end_time)
            self.uc.show_info("Elevations assigned from LIDAR files.\n\n" + '{0:,d}'.format(inside_grid) + 
                              " points inside the grid, and " + '{0:,d}'.format(outside_grid) + " points outside." + 
                              "\n\n(Elapsed time: " + str(time_passed) + ")")
                              
            if read_error != "Error reading files:\n\n":
                self.uc.show_info(read_error)

            if nope:
                self.process_non_interpolated_cells(nope)   
            
            self.lyrs.refresh_layers()
            self.lyrs.zoom_to_all()
             
            QApplication.restoreOverrideCursor()
            
        except Exception as e:
            self.uc.clear_bar_messages()   
            QApplication.restoreOverrideCursor()
            # self.iface.messageBar().clearWidgets() 
            self.uc.show_error("ERROR 140321.1653: importing LIDAR files failed!", e)
            return    
             
    def elapsed_time(self, start, end):   
        et = round((end - start)/60.0 , 2)
        hours, rem = divmod(end - start, 3600)
        minutes, seconds = divmod(rem, 60)            
        et = "{:0>2}:{:0>2}:{:0>2}".format(int(hours),int(minutes),int(seconds))        
        return et
        
        
         
    def  read_LIDAR_points(self):
        n_commas =  0
        n_spaces = 0             
        
        # See if comma or space delimited:
        with open(file, "r") as f:
            while True:    
                line = f.readline()
                line = line.replace('\t', '') 
                if line.strip() != "": 
                    n_commas = line.count(",")
                    if n_commas == 0:
                        n_spaces = len(line.split())
                    break
        if n_commas != 0 or n_spaces != 0:
            # Read file: 
        
            with open(file, "r") as f1:
                try:
                    k = 0
                    for line in f1: 
                        line = line.replace('\t', '')                            
                        if n_commas == 0: # No commas, values separated by spaces.
                            values = line.split()   
                            n_values = len(values)
                            if n_values == 3:
                                xpp, ypp, zpp  = values
                            elif n_values == 4:
                                xpp, ypp, zpp, dummy  = values  
                            elif n_values == 5:
                                dummy1, xpp, ypp, zpp, dummy2  = values  
                            else:
                                break          
                        elif n_commas == 2:  # 3 columns.
                            xpp, ypp, zpp  = line.split(",") 
                        elif n_commas == 3:  # 4 columns.
                            xpp, ypp, zpp, dummy  = line.split(",") 
                        elif n_commas == 4:  # 5 columns.
                             dummy1, xpp, ypp, zpp, dummy2  = line.split(",")  
                        else:
                            break  
                          
                        cell = self.gutils.grid_on_point(xpp, ypp)
                        
                        if cell is not None:
                            if cell in elevs:
                                elevs[cell][0] += float(zpp)
                                elevs[cell][1] += 1
                            else:
                                elevs[cell] = [float(zpp), 1]
                            inside_grid += 1                         
                            
                        else:
                            outside_grid += 1
                except ValueError:
                    read_error += os.path.basename(file) + "\n\n"        
        
    def process_non_interpolated_cells(self, nope):  
        try:   
            QApplication.restoreOverrideCursor()  
            dlg = LidarOptionsDialog(self.con, self.iface, self.lyrs)
            dlg.label.setText("There are " + str(len(nope)) + " non-interpolated grid elements.")                
            
            while True:
                ok = dlg.exec_()
                if not ok:
                    break
                else:
                    s = QSettings()
                    lastDir = s.value("FLO-2D/lastGdsDir", "")
                    qApp.processEvents()
                    
                    shapefile = lastDir + "/Non-interpolated cells.shp"
                    name = "Non-interpolated cells"
                    lyr = QgsProject.instance().mapLayersByName(name)
                    if lyr:
                        QgsProject.instance().removeMapLayers([lyr[0].id()])                  

                    update_qry = "UPDATE grid SET elevation = ?  WHERE fid = ?;"
                    qry_values = []
                    
                    if dlg.interpolate_radio.isChecked():
                        
                        ini_time = time.time()
                        QApplication.setOverrideCursor(Qt.WaitCursor)
                        
                        for this_cell in nope:
                            xx, yy = self.cell_centroid(this_cell)                           
            
                            heights = []
                            
                            # North cell:
                            y = yy + self.cell_size
                            x = xx
                            heights.append(self.adjacent_elev(x, y))

                            # NorthEast cell
                            y = yy + self.cell_size
                            x = xx + self.cell_size
                            heights.append(self.adjacent_elev(x, y))

                            # East cell:
                            x = xx + self.cell_size
                            y = yy
                            heights.append(self.adjacent_elev(x, y))

                            # SouthEast cell:
                            y = yy - self.cell_size
                            x = xx + self.cell_size
                            heights.append(self.adjacent_elev(x, y))

                            # South cell:
                            y = yy - self.cell_size
                            x = xx
                            heights.append(self.adjacent_elev(x, y))

                            # SouthWest cell:
                            y = yy - self.cell_size
                            x = xx - self.cell_size
                            heights.append(self.adjacent_elev(x, y))

                            # West cell:
                            y = yy
                            x = xx - self.cell_size
                            heights.append(self.adjacent_elev(x, y))
 
                            # NorthWest cell:
                            y = yy + self.cell_size
                            x = xx - self.cell_size
                            heights.append(self.adjacent_elev(x, y))

                            if len(heights) == 0:
                                pass
                            else:
                                elev = round(sum(heights)/len(heights), 3)
                                qry_values.append((elev, this_cell))
                        
                        cur = self.gutils.con.cursor()    
                        cur.executemany(update_qry, qry_values)  
                        self.gutils.con.commit()

                        self.lyrs.repaint_layers()
        
                        QApplication.restoreOverrideCursor()  
                        fin_time = time.time()  
                        
                        duration = time_taken(ini_time, fin_time)  
                        
                        self.uc.show_info("Elevation to " + str(len(nope)) + " non-interpolated cells were assigned from adjacent elevations." + 
                                           "\n\n(Elapsed time: " + duration + ")")
         
                    elif dlg.assign_radio.isChecked():
                        
                        ini_time = time.time()
                        QApplication.setOverrideCursor(Qt.WaitCursor)                              
                        
                        value = dlg.non_interpolated_value_dbox.value()
                        for this_cell in nope:
                            qry_values.append((value, this_cell))
                         
                        cur = self.gutils.con.cursor()    
                        cur.executemany(update_qry, qry_values) 
                        self.gutils.con.commit() 
                            
                        self.lyrs.repaint_layers()
        
                        QApplication.restoreOverrideCursor()                               
                        fin_time = time.time()      
                        
                        duration = time_taken(ini_time, fin_time)  
                         
                        self.uc.show_info("Elevation " + str(value) + " was assigned to "   + str(len(nope)) +  " non-interpolated cells." +
                                          "\n\n(Elapsed time: " + duration + ")")      
  
                    elif dlg.highlight_radio.isChecked():
                        if False:   
                            ini_time = time.time()    
                            QApplication.setOverrideCursor(Qt.WaitCursor)     
            
                            # Define fields for feature attributes. 
                            fields = QgsFields()
                            fields.append(QgsField("cell", QVariant.Int))
                            fields.append(QgsField("elevation", QVariant.Int))
            
                            mapCanvas = self.iface.mapCanvas()
                            crs = mapCanvas.mapSettings().destinationCrs()
                            QgsVectorFileWriter.deleteShapeFile(shapefile)                               
                            writer = QgsVectorFileWriter(shapefile, "system", fields, QgsWkbTypes.Point, crs, "ESRI Shapefile")
                
                            if writer.hasError() == QgsVectorFileWriter.NoError:
                                # Add features:
                                features = []
                                for this_cell in nope:  
                                    xx, yy = self.cell_centroid(this_cell)
                                     
                                    # add a feature
                                    fet = QgsFeature()
                                    fet.setFields(fields)
                                    fet.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(xx, yy)))
                                    fet.setAttributes([this_cell, -9999])
                                    features.append(fet)
                                
                                writer.addFeatures(features)                            
            
                                # Delete the writer to flush features to disk.
                                del writer
                    
                                vlayer = self.iface.addVectorLayer(shapefile, "", "ogr")
                    
                                symbol = QgsMarkerSymbol.createSimple({'name': 'square', 'color': 'black'})
                                vlayer.renderer().setSymbol(symbol)
                    
                                # Show the change.
                                vlayer.triggerRepaint()   
                                                                      
                                QApplication.restoreOverrideCursor()
                                fin_time = time.time()     
                                duration = time_taken(ini_time, fin_time)  
                                self.uc.show_info(str(len(nope)) +  " non-interpolated cells are highlighted." +
                                                  "\n\n(Elapsed time: " + duration + ")")                                  
            
                            else:
                                QApplication.restoreOverrideCursor()
                                
                                answer = self.uc.customized_question("FLO-2D. Could not create shapefile",  writer.errorMessage(),
                                                                     QMessageBox.Cancel | QMessageBox.Retry |  QMessageBox.Help , 
                                                                     QMessageBox.Cancel,
                                                                     QMessageBox.Critical)
                                
                                if answer ==  QMessageBox.Cancel:
                                    pass
                                                                    
                                elif answer ==  QMessageBox.Retry:
                                    pass                                                                                                          
                            
                                elif answer ==  QMessageBox.Help:  
                                    self.uc.show_info("Error while creating shapefile: " + shapefile + 
                                                      "\n\nIs the file or directory read only?")
                        else:
                            ini_time = time.time()    
                            QApplication.setOverrideCursor(Qt.WaitCursor)    
                            
                            # style_path2 = get_file_path("styles", "grid.qml")
                            # if os.path.isfile(style_path2):
                                # err_msg, res = self.grid.loadNamedStyle(style_path2)
                                # if not res:
                                    # QApplication.restoreOverrideCursor()
                                    # msg = "Unable to load style {}.\n{}".format(style_path2, err_msg)
                                    # raise Flo2dError(msg)
                            # else:
                                # QApplication.restoreOverrideCursor()
                                # raise Flo2dError("Unable to load style {}".format(style_path2))                                                 
                        
                            render_grid_elevations(self.grid, True);
                            
                            style_path1 = get_file_path("styles", "grid_nodata.qml")
                            # if os.path.isfile(style_path1):
                                # err_msg, res = self.grid.loadNamedStyle(style_path1)
                                # if not res:
                                    # QApplication.restoreOverrideCursor()
                                    # msg = "Unable to load style {}.\n{}".format(style_path1, err_msg)
                                    # raise Flo2dError(msg)
                            # else:
                                # QApplication.restoreOverrideCursor()
                                # raise Flo2dError("Unable to load style file {}".format(style_path1))


                            QApplication.restoreOverrideCursor()
                            fin_time = time.time()     
                            duration = time_taken(ini_time, fin_time)  
                            self.uc.show_info(str(len(nope)) +  " non-interpolated cells are highlighted." +
                                              "\n\n(Elapsed time: " + duration + ")")   
                            
                            self.lyrs.lyrs_to_repaint = [self.grid]
                            self.lyrs.repaint_layers()

        except Exception as e: 
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 030521.0848: failed to process non-interpolated cells!", e)
            return   


   
    def adjacent_elev(self, x, y):
        
        if False:
            elev = 0
            altitude = self.cell_elevation(x, y)
            if altitude is not None:
                if altitude[0] != -9999:
                    elev =  altitude[0] 
            return elev                              
        else:
            elev = 0
            elem = self.gutils.grid_on_point(x, y)
            if elem is not None:
                altitude = self.gutils.execute("SELECT elevation FROM grid WHERE fid = ?;", (elem,)).fetchone()[0]
                if altitude != -9999:
                    elev = altitude
            return elev
                
    def cell_centroid(self, cell):        
        col, row = self.gutils.execute("SELECT col, row FROM grid WHERE fid = ?;",(cell,)).fetchone()
        x = self.xMinimum + (col-2)*self.cell_size + self.cell_size/2
        y = self.yMinimum + (row-2)*self.cell_size + self.cell_size/2
        return x, y

    def cell_elevation(self, x, y):
        col = int((float(x) - self.xMinimum)/self.cell_size) + 2
        row = int((float(y) - self.yMinimum)/self.cell_size) + 2                                    
        elev = self.gutils.execute("SELECT elevation FROM grid WHERE col = ? AND row = ?;", (col, row,)).fetchone()
        return elev     
                                      
    def check_LIDAR_file(self, file):
        file_name, file_ext = os.path.splitext(os.path.basename(file))
        error0 = ""
        error1 = ""

        # Is file empty?:
        if not os.path.isfile(file):
            error0 = "File " + file_name + file_ext + " is being used by another process!"
            return error0, error1
        elif os.path.getsize(file) == 0:
            error0 = "File " + file_name + file_ext + " is empty!"
            return error0, error1

        # Check 2 float values in columns:
        try:
            with open(file, "r") as f:
                for line in f:
                    row = line.split()
                    if row:
                        if len(row) != 2:
                            error1 = "File " + file_name + file_ext + " must have 2 columns in all lines!"
                            return error0, error1
        except UnicodeDecodeError:
            error0 = "File " + file_name + file_ext + " is not a text file!"
        finally:
             return error0, error1

class LIDARWorker(QObject) :
    def __init__(self, iface, lidar_files, lyrs):
        QObject.__init__(self)
        self.lidar_files = lidar_files
        self.THREAD_killed = False
        
        self.iface = iface
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None        
        
        self.setup_connection()
        
        
    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            
    def run(self):
        try:
            # elevs = {}
            # errors0 = []
            # errors1 = []
            # warnings = []
            # read_error = "Error reading files:\n\n"
            # accepted_files = []
            # outside_grid, inside_grid = 0, 0
            
            
            # cell_size = self.gutils.execute.get_cont_par("CELLSIZE")
            # cell_size = float(cell_size)
            
            
            THREAD_progress_count = 0 
            n_files = len(self.lidar_files)             
            for i, file in enumerate(self.lidar_files,1): 
                if self.THREAD_killed is True:
                    # kill request received, exit loop early
                    break   
                time.sleep(0.2) # simulate a more time consuming task
                # increment progrss   
                THREAD_progress_count += 1
                self.THREAD_progrss.emit(THREAD_progress_count * 100 / n_files)

                n_commas =  0
                n_spaces = 0             
                
#                 err0, err1 = self.check_LIDAR_file(file)
#                 if err0 == "" and err1 == "" :
  
                # See if comma or space delimited:
                with open(file, "r") as f:
                    while True:    
                        line = f.readline()
                        line = line.replace('\t', '') 
                        if line.strip() != "": 
                            n_commas = line.count(",")
                            if n_commas == 0:
                                n_spaces = len(line.split())
                            break
                            
                if n_commas != 0 or n_spaces != 0:
                    # Read file: 
                    
                    with open(file, "r") as f1:
                        try:
                            k = 0
                            for line in f1: 
                                line = line.replace('\t', '')                            
                                if n_commas == 0: # No commas, values separated by spaces.
                                    values = line.split()   
                                    n_values = len(values)
                                    if n_values == 3:
                                        xpp, ypp, zpp  = values
                                    elif n_values == 4:
                                        xpp, ypp, zpp, dummy  = values  
                                    elif n_values == 5:
                                        dummy1, xpp, ypp, zpp, dummy2  = values  
                                    else:
                                        break          
                                elif n_commas == 2:  # 3 columns.
                                    xpp, ypp, zpp  = line.split(",") 
                                elif n_commas == 3:  # 4 columns.
                                    xpp, ypp, zpp, dummy  = line.split(",") 
                                elif n_commas == 4:  # 5 columns.
                                     dummy1, xpp, ypp, zpp, dummy2  = line.split(",")  
                                else:
                                    break  
                                    
#                                 cell = self.gutils.grid_on_point(xpp, ypp)
#                                   
#                                 if cell is not None:
#                                     if cell in elevs:
#                                         elevs[cell][0] += float(zpp)
#                                         elevs[cell][1] += 1
#                                     else:
#                                         elevs[cell] = [float(zpp), 1]
#                                     inside_grid += 1                         
#                                       
#                                 else:
#                                     outside_grid += 1
                        except ValueError:
                            read_error += os.path.basename(file) + "\n\n"
                            
                            
            if self.THREAD_killed is False:
                self.THREAD_progrss.emit(100) 
                
        except Exception as e:
            # forward the exception upstream
            self.THREAD_error.emit(e, traceback.format_exc())   
            self.uc.show_error("ERROR 140321.1653: importing LIDAR files failed!", e)            
            
        self.THREAD_finished.emit()   
                   
    def THREAD_kill(self):
        self.THREAD_killed = True
        
    THREAD_finished = QtCore.pyqtSignal()
    THREAD_error = QtCore.pyqtSignal(Exception, basestring)
    THREAD_progrss = QtCore.pyqtSignal(float)

uiDialog, qtBaseClass = load_ui("lidar_options")
class LidarOptionsDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.con = con
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)
        self.uc = UserCommunication(iface, "FLO-2D")
        
        self.interpolate_radio.clicked.connect(self.enable_non_value)
        self.assign_radio.clicked.connect(self.enable_non_value)
        self.highlight_radio.clicked.connect(self.enable_non_value)
        
    def _del_(self): 
        pass
  
    def enable_non_value(self):
        if self.assign_radio.isChecked():
            self.non_interpolated_value_dbox.setEnabled(True)
        else:
            self.non_interpolated_value_dbox.setEnabled(False)   


           