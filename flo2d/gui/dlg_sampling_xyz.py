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
from ..utils import (
        get_file_path, 
        time_taken, 
        grid_index, 
        get_grid_index, 
        set_grid_index, 
        clear_grid_index, 
        is_grid_index, 
        get_min_max_elevs, 
        set_min_max_elevs,
        second_smallest
    )
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..flo2d_tools.grid_tools import (
        number_of_elements, 
        fid_from_grid, 
        adjacent_grid_elevations, 
        render_grid_elevations2, 
        adjacent_average_elevation,
        cell_centroid,
        cell_elevation
    )
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
        self.lidar_chbox.clicked.connect(self.lidar_selected)

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
        self.lidar_chbox.setChecked(not self.points_layer_grp.isChecked())

    def lidar_selected(self):
        self.points_layer_grp.setChecked(not self.lidar_chbox.isChecked())
                   
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
            statBar.removeWidget(statusLabel)
            statBar.removeWidget(advanceBar)    
            qApp.processEvents()   
            self.uc.bar_info("Updating grid elevations...")   
                                                           
            # Assign -9999 to all cell elevations prior to the assignment from LIDAR points: 
            self.gutils.execute("UPDATE grid SET elevation = -9999;")
            
            # Update cell elevations from LIDAR points:
            nope = []
            cell_elev = [] 
            
            if inside_grid > 0:
                qry = "UPDATE grid SET elevation = ? WHERE fid = ?;"
                for gi in gid_indx.items():
                    if gi[1][2] != 0:
                        elevation = round(gi[1][1]/gi[1][2],4)
                        cell_elev.append((elevation, gi[1][0]))       
                    else:
                        nope.append((gi[1][0],gi[0][0], gi[0][1]))   # element, col, row
                self.gutils.execute_many(qry, cell_elev)                                

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
                QApplication.setOverrideCursor(Qt.WaitCursor) 
                elevs =  [x[0] for x in cell_elev]
                mini = -9999
                mini2 = min(elevs) 
                maxi = max(elevs)                                                        
                render_grid_elevations2(self.grid, True, mini, mini2, maxi);                
                set_min_max_elevs(mini, maxi)  
                self.lyrs.lyrs_to_repaint = [self.grid]
                self.lyrs.repaint_layers()
                
                self.process_non_interpolated_cells(nope, cell_elev)   
            
            # self.lyrs.refresh_layers()
            self.lyrs.zoom_to_all()
             
            QApplication.restoreOverrideCursor()
            
        except Exception as e:
            self.uc.clear_bar_messages()   
            QApplication.restoreOverrideCursor()
            # self.iface.messageBar().clearWidgets() 
            self.uc.show_error("ERROR 140321.1653: importing LIDAR files failed!", e)
            return    
             
    def elapsed_time(self, start, end):   
        hours, rem = divmod(end - start, 3600)
        minutes, seconds = divmod(rem, 60)            
        et = "{:0>2}:{:0>2}:{:0>2}".format(int(hours),int(minutes),int(seconds))        
        return et     
        
    def process_non_interpolated_cells(self, nope, assigned):  
        try:   
            adjacent = []
            tot_adjacent = 0
            while True:
                QApplication.restoreOverrideCursor()  
                dlg = LidarOptionsDialog(self.con, self.iface, self.lyrs)
                if nope:
                    if adjacent:
                        tot_adjacent += len(adjacent)
                        dlg.label.setText("Elevations from LIDAR files assigned to " + '{0:,d}'.format(len(assigned)) + " cells," + 
                                          "\n\nand " + '{0:,d}'.format(tot_adjacent) + " from adjacent cells."
                                          "\n\nThere are still " + '{0:,d}'.format(len(nope)) + " non-interpolated cells.\n")
                    else:
                        dlg.label.setText("Elevations from LIDAR files assigned to " + '{0:,d}'.format(len(assigned)) + " cells." + 
                                          "\n\nThere are still " + '{0:,d}'.format(len(nope)) + " non-interpolated cells.\n")                        
                else:
                    dlg.label.setText("Elevations from LIDAR files assigned to " + '{0:,d}'.format(len(assigned)) + " cells.")                                                       
                
                ok = dlg.exec_()
                if not ok:
                    break
                else:
                    
                    qApp.processEvents()                

                    update_qry = "UPDATE grid SET elevation = ?  WHERE fid = ?;"
                    qry_values = []
                    adjacent = []
                    
                    if dlg.interpolate_radio.isChecked():
                        
                        ini_time = time.time()
                        QApplication.setOverrideCursor(Qt.WaitCursor)
                        
                        for this_cell in nope:
                            
                            xx = self.xMinimum + (this_cell[1]-2)*self.cell_size + self.cell_size/2
                            yy = self.yMinimum + (this_cell[2]-2)*self.cell_size + self.cell_size/2                        
                            
                            avrg = adjacent_average_elevation(self.gutils, self.grid, xx, yy, self.cell_size)
                            if avrg != -9999:
                                qry_values.append((avrg, this_cell[0]))
                                adjacent.append(this_cell[0])
                                
                        self.gutils.execute_many(update_qry, qry_values)   
                        
                        nope = [i for i in nope if i[0] not in adjacent]
                        
                        QApplication.restoreOverrideCursor()  
                        fin_time = time.time()  
                        
                        duration = time_taken(ini_time, fin_time)  

                        self.lyrs.lyrs_to_repaint = [self.grid]
                        self.lyrs.repaint_layers()
                                                                         
                        self.uc.show_info("Elevation to " + '{0:,d}'.format(len(qry_values)) + " non-interpolated cells were assigned from adjacent elevations." + 
                                          "\n\n There are still " + '{0:,d}'.format(len(nope)) + " non-interpolated cells."
                                           "\n\n(Elapsed time: " + duration + ")")
         
                    elif dlg.assign_radio.isChecked():
                        
                        ini_time = time.time()
                        QApplication.setOverrideCursor(Qt.WaitCursor)                              
                        
                        value = dlg.non_interpolated_value_dbox.value()
                        for this_cell in nope:
                            qry_values.append((value, this_cell[0]))
                         
                        cur = self.gutils.con.cursor()    
                        cur.executemany(update_qry, qry_values) 
                        self.gutils.con.commit() 

                        elevs = [x[0]  for x in self.gutils.execute("SELECT elevation FROM grid").fetchall()]
                        mini = min(elevs)
                        mini2 = mini 
                        maxi = max(elevs)       
                        render_grid_elevations2(self.grid, True, mini, mini2, maxi) 
                        set_min_max_elevs(mini, maxi) 
                        self.lyrs.lyrs_to_repaint = [self.grid]
                        self.lyrs.repaint_layers()
        
                        QApplication.restoreOverrideCursor()                               
                        fin_time = time.time()      
                        
                        duration = time_taken(ini_time, fin_time)  
                         
                        self.uc.show_info("Elevation " + str(value) + " was assigned to "  + '{0:,d}'.format(len(nope)) + " non-interpolated cells." +
                                          "\n\n(Elapsed time: " + duration + ")") 
                        
                        nope = []     
  
                    elif dlg.highlight_radio.isChecked():
                        pass

                        # ini_time = time.time()    
                        # QApplication.setOverrideCursor(Qt.WaitCursor)    
                        #
                        # render_grid_elevations(self.grid, True);
                        #
                        # self.lyrs.lyrs_to_repaint = [self.grid]
                        # self.lyrs.repaint_layers()
                        #
                        # QApplication.restoreOverrideCursor()
                        # fin_time = time.time()     
                        # duration = time_taken(ini_time, fin_time)  
                        # self.uc.show_info('{0:,d}'.format(len(nope)) +  " non-interpolated cells are highlighted." +
                        #                   "\n\n(Elapsed time: " + duration + ")")   
 
        except Exception as e: 
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 030521.0848: failed to process non-interpolated cells!", e)
            return   
   
    def adjacent_elev(self, x, y):            
        elev = 0
        elem = self.gutils.grid_on_point(x, y)
        if elem is not None:
            altitude = self.gutils.execute("SELECT elevation FROM grid WHERE fid = ?;", (elem,)).fetchone()[0]
            if altitude != -9999:
                elev = altitude
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
           
        self.highlight_radio.setVisible(False)
        
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


           