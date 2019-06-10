# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 209 Juan Jose Rodriguez

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os
import sys
import math
import uuid
from qgis.PyQt.QtWidgets import QMessageBox
from collections import defaultdict
from subprocess import Popen, PIPE, STDOUT
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsSpatialIndex, QgsRasterLayer, QgsRaster, QgsFeatureRequest, QgsFeedback, NULL
from qgis.analysis import QgsInterpolator, QgsTinInterpolator, QgsZonalStatistics
from ..utils import is_number
from ..geopackage_utils import GeoPackageUtils


class Conflicts(object):

    def __init__(self, lyrs, con, iface):
        self.lyrs = lyrs
        self.gutils = GeoPackageUtils(con, iface)
        
    def conflict_inflow_inflow(self): 
        cells = []
        repeated = [] 
        sql = "SELECT grid_fid FROM inflow_cells"
        rows = self.gutils.execute(sql).fetchall()
        if not rows:
            return repeated
        else:
            for row in rows:
                cells.append(row)  
            size = len(cells)
            for i in range(size): 
                k = i + 1
                for j in range(k, size): 
                    if cells[i][0] == cells[j][0] and cells[i][0] not in repeated: 
                        repeated.append(cells[i][0]) 
                        break
            return repeated

    def conflict_outflow_outflow(self): 
        cells = []
        repeated = [] 
        sql = "SELECT grid_fid FROM outflow_cells"
        rows = self.gutils.execute(sql).fetchall()
        if not rows:
            return repeated
        else:
            for row in rows:
                cells.append(row)
            size = len(cells)
            for i in range(size): 
                k = i + 1
                for j in range(k, size): 
                    if cells[i][0] == cells[j][0] and cells[i][0] not in repeated: 
                        repeated.append(cells[i][0]) 
                        break
            return repeated
    
    
    def conflict_inflow_outflow(self):
        in_cells = []
        out_cells = []
        repeated = [] 
        inf = "SELECT grid_fid FROM inflow_cells"
        outf = "SELECT grid_fid FROM outflow_cells"
        in_rows = self.gutils.execute(inf).fetchall()
        out_rows = self.gutils.execute(outf).fetchall()
        if not in_rows or not out_rows:
            return repeated
        else:
            for row in in_rows:
                in_cells.append(row)
            for row in out_rows:
                out_cells.append(row)                
            in_size = len(in_cells)
            out_size = len(out_cells)
            for i in range(in_size): 
                for o in range(out_size):  
                    if in_cells[i][0] == out_cells[o][0] and in_cells[i][0] not in repeated: 
                        repeated.append(in_cells[i][0]) 
                        break
            return repeated

    
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

    def conflict(self, table1, grid1, table2, grid2):
        cells1 = []
        cells2 = []
        repeated = [] 
        sqr1 = "SELECT {0} FROM {1}".format(grid1, table1)
        sqr2 = "SELECT {0} FROM {1}".format(grid2, table2)
        rows1 = self.gutils.execute(sqr1).fetchall()
        rows2 = self.gutils.execute(sqr2).fetchall()
        if not rows1 or not rows2:
            return repeated
        else:
            for row in rows1:
                cells1.append(row)
            for row in rows2:
                cells2.append(row)                
            size1 = len(cells1)
            size2 = len(cells2)
            for i in range(size1): 
                for j in range(size2):  
                    if cells1[i][0] == cells2[j][0] and cells1[i][0] not in repeated: 
                        repeated.append(cells1[i][0]) 
                        break
            return repeated    
        
        
        
        
        
        
        
        
        
        