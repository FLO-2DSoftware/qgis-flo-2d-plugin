# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os, stat
from qgis.core import *
# QgsWkbTypes, Qgis, QgsFeatureRequest, QgsVectorLayer, QgsField, QgsFields, QgsFeature, QgsGeometry, QgsPointXY, QgsProject
from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from qgis.PyQt.QtCore import QSettings, Qt, QVariant
from qgis.PyQt.QtWidgets import QFileDialog, QApplication, QProgressBar, qApp, QMessageBox
from ..flo2d_tools.grid_tools import number_of_elements, fid_from_grid, adjacent_grid_elevations
from plugins.processing.tools.vector import values
import time

uiDialog, qtBaseClass = load_ui("sampling_xyz")
class SamplingXYZDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.con = con
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)
        self.gpkg_path = self.gutils.get_gpkg_path()
        self.uc = UserCommunication(iface, "FLO-2D")
        self.current_lyr = None
        self.setup_layer_cbo()
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
        self.use_all_radio.setEnabled(False)
        self.use_porcentage_radio.setEnabled(False)
        self.porcentage_dbox.setEnabled(False)
                   
    def interpolate_from_lidar(self, n_max_points = 20):

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
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            elevs = {}
            errors0 = []
            errors1 = []
            warnings = []
            read_error = "Error reading files:\n\n"
            accepted_files = []
            outside_grid, inside_grid = 0, 0
            cell_size = float(self.gutils.get_cont_par("CELLSIZE"))

            progressMessageBar1= self.iface.messageBar().createMessage("Reading LIDAR files...")
            progress1 = QProgressBar()
            progress1.setMaximum(len(lidar_files) + 1)
            progress1.setAlignment(Qt.AlignCenter|Qt.AlignVCenter)
            progressMessageBar1.layout().addWidget(progress1)
            self.iface.messageBar().pushWidget(progressMessageBar1, Qgis.Info)


#             progressMessageBar2= self.iface.messageBar().createMessage("Reading LIDAR files...")
#             progress2 = QProgressBar()
#             progress2.setMaximum(len(lidar_files) + 1)
#             progress2.setAlignment(Qt.AlignCenter|Qt.AlignVCenter)
#             progressMessageBar2.layout().addWidget(progress2)
#             self.iface.messageBar().pushWidget(progressMessageBar2, Qgis.Info)
            
#             # Create points layer:
#             vl = QgsVectorLayer("Point", "temporary_points", "memory")
#             vl.startEditing()
#             pr = vl.dataProvider()
#             # add fields
#             pr.addAttributes([QgsField("elevation", QVariant.Double)])
#             vl.updateFields() # tell the vector layer to fetch changes from the provider

            start_time = time.time()
            
            for i, file in enumerate(lidar_files,1):
#                 progress1.setValue(i) 
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
#                     self.uc.progress_bar("Reading " + file)                 
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

                        
            # Assign -9999 to all cell elevations prior to the assignment from LIDAR points: 
            self.gutils.execute("UPDATE grid SET elevation = -9999;")
            
            # Update cell elevations from LIDAR points:
            if elevs:
                for cell, value in elevs.items():
                    elevation = round(value[0]/value[1],4)
                    self.gutils.execute("UPDATE grid SET elevation = ? WHERE fid = ?;", (elevation, cell))

            self.iface.messageBar().clearWidgets()        
            QApplication.restoreOverrideCursor()    
             
            end_time = time.time()   
            elapsed_time = round((end_time - start_time)/60.0 , 2)
            hours, rem = divmod(end_time-start_time, 3600)
            minutes, seconds = divmod(rem, 60)            
            elapsed_time = "{:0>2}:{:0>2}:{:0>2}".format(int(hours),int(minutes),int(seconds))
            
            self.uc.show_info("Elevations assigned from LIDAR files.\n\n" + '{0:,d}'.format(inside_grid) + 
                              " points inside the grid, and " + '{0:,d}'.format(outside_grid) + " points outside." + 
                              "\n\n(Elapsed time: " + str(elapsed_time) + ")")
            
            if read_error != "Error reading files:\n\n":
                self.uc.show_info(read_error)
            self.grid = self.lyrs.data["grid"]["qlyr"]
            
            n_cells = number_of_elements(self.gutils, self.grid)
            n_no_assigned_cells = n_cells - len(elevs)
            if n_no_assigned_cells > 0:
                
                while True:
                    QApplication.restoreOverrideCursor()       
                    # Get non-assigned cells:
                    nope = []
                    for i in range(1, n_cells + 1):
                        if i not in elevs:
                            nope.append(i)
                        else:
                            pass      
                                                  
                    dlg = LidarOptionsDialog(self.con, self.iface, self.lyrs)
                    dlg.label.setText("There are " + str(n_no_assigned_cells) + " non-interpolated grid elements.")
                    ok = dlg.exec_()
                    if not ok:
                        return
                    else:
                        s = QSettings()
                        lastDir = s.value("FLO-2D/lastGdsDir", "")
                        qApp.processEvents()
                        
                        shapefile = lastDir + "/Non-interpolated cells.shp"
                        name = "Non-interpolated cells"
            
                        lyr = QgsProject.instance().mapLayersByName(name)
            
                        if lyr:
                            QgsProject.instance().removeMapLayers([lyr[0].id()])                  
                        
                        if dlg.interpolate_radio.isChecked():
                            
                            ini_time = time.time()
                            QApplication.setOverrideCursor(Qt.WaitCursor)
    
                            for this_cell in nope:
                                currentCell = next(self.grid.getFeatures(QgsFeatureRequest(this_cell)))
                                xx, yy = currentCell.geometry().centroid().asPoint()
                
                                elevs = []
                                sel_elev_qry = """SELECT elevation FROM grid WHERE fid = ?;"""
                                # North cell:
                                y = yy + cell_size
                                x = xx
                                grid = self.gutils.grid_on_point(x, y)
                                if grid is not None:
                                    altitude = self.gutils.execute(sel_elev_qry, (grid,)).fetchone()[0]
                                    if altitude != -9999:
                                        elevs.append(altitude)
                
                                # NorthEast cell
                                y = yy + cell_size
                                x = xx + cell_size
                                grid = self.gutils.grid_on_point(x, y)
                                if grid is not None:
                                    altitude = self.gutils.execute(sel_elev_qry, (grid,)).fetchone()[0]
                                    if altitude != -9999:
                                        elevs.append(altitude)
                
                                # East cell:
                                x = xx + cell_size
                                y = yy
                                grid = self.gutils.grid_on_point(x, y)
                                if grid is not None:
                                    altitude = self.gutils.execute(sel_elev_qry, (grid,)).fetchone()[0]
                                    if altitude != -9999:
                                        elevs.append(altitude)
                
                                # SouthEast cell:
                                y = yy - cell_size
                                x = xx + cell_size
                                grid = self.gutils.grid_on_point(x, y)
                                if grid is not None:
                                    altitude = self.gutils.execute(sel_elev_qry, (grid,)).fetchone()[0]
                                    if altitude != -9999:
                                        elevs.append(altitude)
                
                                # South cell:
                                y = yy - cell_size
                                x = xx
                                grid = self.gutils.grid_on_point(x, y)
                                if grid is not None:
                                    altitude = self.gutils.execute(sel_elev_qry, (grid,)).fetchone()[0]
                                    if altitude != -9999:
                                        elevs.append(altitude)
                
                                # SouthWest cell:
                                y = yy - cell_size
                                x = xx - cell_size
                                grid = self.gutils.grid_on_point(x, y)
                                if grid is not None:
                                    altitude = self.gutils.execute(sel_elev_qry, (grid,)).fetchone()[0]
                                    if altitude != -9999:
                                        elevs.append(altitude)
                
                                # West cell:
                                y = yy
                                x = xx - cell_size
                                grid = self.gutils.grid_on_point(x, y)
                                if grid is not None:
                                    altitude = self.gutils.execute(sel_elev_qry, (grid,)).fetchone()[0]
                                    if altitude != -9999:
                                        elevs.append(altitude)
                
                                # NorthWest cell:
                                y = yy + cell_size
                                x = xx - cell_size
                                grid = self.gutils.grid_on_point(x, y)
                                if grid is not None:
                                    altitude = self.gutils.execute(sel_elev_qry, (grid,)).fetchone()[0]
                                    if altitude != -9999:
                                        elevs.append(altitude)
                
                                if len(elevs) == 0:
                                    pass
                                else:
                                    elev = round(sum(elevs)/len(elevs), 3)
                                    self.gutils.execute("UPDATE grid SET elevation = ? WHERE fid = ?;", (elev, this_cell))  
                            
                            self.lyrs.repaint_layers()

                            QApplication.restoreOverrideCursor()  
                            fin_time = time.time()  
                            
                            duration = self.time_taken(ini_time, fin_time)  
                            
                            self.uc.show_info("Elevation to " + str(len(nope)) + " non-interpolated cells were assigned from adjacent elevations." + 
                                               "\n\n(Elapsed time: " + duration + ")")
                        
                            del dlg
                            break
                        elif dlg.assign_radio.isChecked():
                            
                            ini_time = time.time()
                            QApplication.setOverrideCursor(Qt.WaitCursor)                              
                            
                            value = dlg.non_interpolated_value_dbox.value()
                            for this_cell in nope:
                                self.gutils.execute("UPDATE grid SET elevation = ? WHERE fid = ?;", (value, this_cell)) 
                                
                            self.lyrs.repaint_layers()
    
                            QApplication.restoreOverrideCursor()                               
                            fin_time = time.time()      
                            
                            duration = self.time_taken(ini_time, fin_time)  
                             
                            self.uc.show_info("Elevation " + str(value) + " was assigned to "   + str(len(nope)) +  " non-interpolated cells." +
                                              "\n\n(Elapsed time: " + duration + ")")      
                             
                            del dlg                         
                            break
                        
                        elif dlg.highlight_radio.isChecked():
                             
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
                                pass
                            else:
                                QApplication.restoreOverrideCursor()
                                
                                answer = self.uc.customized_question("FLO-2D. Could not create shapefile",  writer.errorMessage(),
                                                                     QMessageBox.Cancel | QMessageBox.Retry |  QMessageBox.Help , 
                                                                     QMessageBox.Cancel,
                                                                     QMessageBox.Critical)
                                
                                if answer ==  QMessageBox.Cancel:
                                    del writer
                                    del dlg
                                    break
                                
                                elif answer ==  QMessageBox.Retry:
                                    pass
                                                                                                                    
#                                 elif answer ==  QMessageBox.Ignore: 
#                                     del writer
#                                     del dlg
#                                     break
                            
                                elif answer ==  QMessageBox.Help:  
                                    self.uc.show_info("Error while creating shapefile: " + shapefile + 
                                                      "\n\nIs the file or directory read only?")
                                    del writer
                                    del dlg                                  
                                     
                            QApplication.setOverrideCursor(Qt.WaitCursor)   
                            
                            if writer.hasError() == QgsVectorFileWriter.NoError:                             
                                # Add features:
                                features = []
                                for this_cell in nope:  
                                        currentCell = next(self.grid.getFeatures(QgsFeatureRequest(this_cell)))
                                        xx, yy = currentCell.geometry().centroid().asPoint()
                                         
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
                                del dlg      
                                                                      
                                QApplication.restoreOverrideCursor()
                                fin_time = time.time()  
                                       
                                duration = self.time_taken(ini_time, fin_time)  
                                 
                                QApplication.restoreOverrideCursor() 
                                self.uc.show_info(str(len(nope)) +  " non-interpolated cells are highlighted." +
                                                  "\n\n(Elapsed time: " + duration + ")")   

                                break
                      
                self.lyrs.refresh_layers()
                self.lyrs.zoom_to_all()
                
                QApplication.restoreOverrideCursor()
                               
#                 time_passed = round((fin_time - ini_time)/60.0 , 2)
#                 hours, rem = divmod(fin_time - ini_time, 3600)
#                 minutes, seconds = divmod(rem, 60)            
#                 time_passed = "{:0>2}:{:0>2}:{:0>2}".format(int(hours),int(minutes),int(seconds))
#                 self.uc.show_info("Elapsed time: " + str(time_passed))

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.iface.messageBar().clearWidgets()        
            self.uc.show_error("ERROR 140321.1653: importing LIDAR files failed!", e)
            return
    def time_taken(self, ini, fin):  
        time_passed = round((fin - ini)/60.0 , 2)
        hours, rem = divmod(fin - ini, 3600)
        minutes, seconds = divmod(rem, 60)            
        time_passed = "{:0>2}:{:0>2}:{:0>2}".format(int(hours),int(minutes),int(seconds))
        return time_passed      
        
          
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
        
    def _del_(self): 
        pass
  



           