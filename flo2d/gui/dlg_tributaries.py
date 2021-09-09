# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QTableWidgetItem,  QComboBox
from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..flo2d_tools.grid_tools import find_this_cell


uiDialog, qtBaseClass = load_ui("tributaries")
class TributariesDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs, confluences):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.lyrs = lyrs
        self.confluences = confluences
        self.rubber_bands = []
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None
        self.confluences_tblw.itemSelectionChanged.connect(self.highlight_confluence)
        self.reset_confluences_btn.clicked.connect(self.reset_confluences)
        self.setup_connection()
        self.populate_table()
        self.find_chan_confluences()
        self.highlight_all_tributaries()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_table(self):
        for row_position, confluence in enumerate(self.confluences.values()):
            self.confluences_tblw.insertRow(row_position)
            item = QTableWidgetItem()
            item.setData(Qt.DisplayRole, confluence[0])
            self.confluences_tblw.setItem(row_position, 0, item)
            if len(confluence) > 1:
                combo = QComboBox()
                combo.setStyleSheet("QComboBox { border: 1px gray; } QFrame { border: 3px solid blue; }")
                combo.addItem("")
                for t in confluence[1:]:
                    combo.addItem(str(t))
                combo.currentIndexChanged.connect(lambda : self.highlight_confluence() )       
                self.confluences_tblw.setCellWidget(row_position,1,combo)  
                
    def find_chan_confluences(self):
        for row in range(0, self.confluences_tblw.rowCount() - 1):
            tributary = self.confluences_tblw.item(row, 0).text()
            conf_fid = self.gutils.execute("SELECT conf_fid FROM chan_confluences WHERE type = ? AND chan_elem_fid = ?;", (0, tributary,)).fetchone()
            if conf_fid:
                main = self.gutils.execute("SELECT chan_elem_fid FROM chan_confluences WHERE conf_fid = ? AND type = ?;", (conf_fid[0], 1,)).fetchone()
                if main:
                    widget = self.confluences_tblw.cellWidget(row, 1)
                    for i in range(1, widget.count()):
                        if widget.itemText(i) == str(main[0]):
                            widget.setCurrentIndex(i)
                
                 
    def highlight_confluence(self):
        row = self.confluences_tblw.currentRow()
        if row >= 0:
            self.confluences_tblw_cell_update(row)

    def confluences_tblw_cell_update(self, row):
        
        tributary_cell = self.confluences_tblw.item(row, 0).text()
        find_this_cell(self.iface, self.lyrs, self.uc, self.gutils, tributary_cell, Qt.cyan, zoom_in = True, clear_previous = True)   
        self.rubber_bands.append(self.lyrs.rb)
               
        current_widget = self.confluences_tblw.cellWidget(row, 1)
        if current_widget:
                main_cell = current_widget.currentText()
                if main_cell != "":
                    find_this_cell(self.iface, self.lyrs, self.uc, self.gutils, main_cell, Qt.blue, zoom_in = False, clear_previous = False) 
                    self.rubber_bands.append(self.lyrs.rb)                      
                    
    def highlight_all_tributaries(self):
        self.lyrs.clear_rubber()
        for i in range(1, self.confluences_tblw.rowCount() - 1):
            
            tributary_cell = self.confluences_tblw.item(i, 0).text()
            find_this_cell(self.iface, self.lyrs, self.uc, self.gutils, tributary_cell, Qt.cyan, zoom_in = False, clear_previous = False) 
            self.rubber_bands.append(self.lyrs.rb)         

    def reset_confluences(self): 
        self.confluences_tblw.setRowCount(0)
        self.populate_table()
 
        
    def clear_confluences_rubber(self): 
        for rb in self.rubber_bands:
            self.canvas.scene().removeItem(rb)   
            
            
    def save(self):   
        chan_conf_sql = ["""INSERT INTO chan_confluences (geom, conf_fid, type, chan_elem_fid) VALUES""", 4]
        
        for row in range(0, self.confluences_tblw.rowCount() - 1):
            
            widget = self.confluences_tblw.cellWidget(row, 1)
            if widget:
                main = widget.currentText()
                if main != "":
                    tributary = self.confluences_tblw.item(row, 0).text()
                
                    cells = self.gutils.grid_centroids([tributary, main], buffers=True)
    
                    geom1, geom2 = cells[tributary], cells[main]
                    chan_conf_sql += [(geom1, row + 1, 0, tributary)]
                    chan_conf_sql += [(geom2, row + 1, 1, main)]   
        pass        
        self.gutils.clear_tables("chan_confluences")                     
        self.gutils.batch_execute(chan_conf_sql)       
                
                
           