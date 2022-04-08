# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from ..utils import is_true, is_number, m_fdata
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsFeatureRequest
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QApplication, QTableWidgetItem, QDialogButtonBox, QInputDialog
from .table_editor_widget import StandardItemModel, StandardItem
from .ui_utils import load_ui, set_icon, center_canvas, zoom, try_disconnect
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from math import isnan

uiDialog, qtBaseClass = load_ui("orifices")
class OrificesDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None
        
        set_icon(self.find_orifice_btn, "eye-svgrepo-com.svg")
        set_icon(self.zoom_in_orifice_btn, "zoom_in.svg")
        set_icon(self.zoom_out_orifice_btn, "zoom_out.svg") 

        self.find_orifice_btn.clicked.connect(self.find_orifice)
        self.zoom_in_orifice_btn.clicked.connect(self.zoom_in_orifice)
        self.zoom_out_orifice_btn.clicked.connect(self.zoom_out_orifice)   
        
        self.orifices_buttonBox.button(QDialogButtonBox.Save).setText("Save to 'Storm Drain Orifices' User Layer")
        self.orifice_name_cbo.currentIndexChanged.connect(self.fill_individual_controls_with_current_orifice_in_table)
        
        self.orifices_buttonBox.accepted.connect(self.save_orifices)  
        
        self.orifice_type_cbo.currentIndexChanged.connect(self.orifice_type_cbo_currentIndexChanged)
        self.orifice_flap_gate_cbo.currentIndexChanged.connect(self.orifice_flap_gate_cbo_currentIndexChanged)
        self.orifice_shape_cbo.currentIndexChanged.connect(self.orifice_shape_cbo_currentIndexChanged)
        self.orifice_crest_height_dbox.valueChanged.connect(self.orifice_crest_height_dbox_valueChanged)
        self.orifice_discharge_coeff_dbox.valueChanged.connect(self.orifice_discharge_coeff_dbox_valueChanged)
        self.orifice_open_close_time_dbox.valueChanged.connect(self.orifice_open_close_time_dbox_valueChanged)
        self.orifice_height_dbox.valueChanged.connect(self.orifice_height_dbox_valueChanged)
        self.orifice_width_dbox.valueChanged.connect(self.orifice_width_dbox_valueChanged)        
        
        self.setup_connection()
        self.grid_lyr = self.lyrs.data["grid"]["qlyr"]
        self.orifices_lyr = self.lyrs.data["user_swmm_orifices"]["qlyr"]
        self.populate_orifices()

        self.orifices_tblw.cellClicked.connect(self.orifices_tblw_cell_clicked)
        self.orifices_tblw.verticalHeader().sectionClicked.connect(self.onVerticalSectionClicked)    

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_orifices(self):
        qry = """SELECT fid,
                        orifice_name,
                        orifice_inlet, 
                        orifice_outlet,
                        orifice_type,
                        orifice_crest_height,
                        orifice_disch_coeff,
                        orifice_flap_gate,
                        orifice_open_close_time,
                        orifice_shape,
                        orifice_height,
                        orifice_width
                FROM user_swmm_orifices;"""
        wrong_status = 0
        try:
            rows = self.gutils.execute(qry).fetchall()
            self.orifices_tblw.setRowCount(0)
            for row_number, row_data in enumerate(rows): 
                self.orifices_tblw.insertRow(row_number)
                for column, data in enumerate(row_data):
                    item = QTableWidgetItem()
                    item.setData(Qt.DisplayRole, data)  # item gets value of data (as QTableWidgetItem Class)

                    if column == 1:  
                        # Fill the list of orifices names:
                        self.orifice_name_cbo.addItem(data, row_data[0])
                    if row_number == 0:
                        if column == 2:
                            self.orifice_from_node_txt.setText(str(data))

                        elif column == 3:
                            self.orifice_to_node_txt.setText(str(data))

                        elif column == 4: 
                            if data not in ("SIDE", "BOTTOM", "side", "botton", "Side", "Bottom"):  
                                wrong_status += 1   
                                data = "SIDE" 
                                item.setData(Qt.DisplayRole, data)       
                            index = self.orifice_type_cbo.findText(data)
                            if index == -1:
                                index = 0
                            self.orifice_type_cbo.setCurrentIndex(index)
                            
                        elif column == 5:
                            self.orifice_crest_height_dbox.setValue(data)  
 
                        elif column == 6:
                            self.orifice_discharge_coeff_dbox.setValue(data)  
                                                                                 
                        elif column == 7:
                            if data not in ("YES", "NO", "yes", "no", "Yes", "No"):  
                                wrong_status += 1 
                                data = "YES"  
                                item.setData(Qt.DisplayRole, data) 
                            index = self.orifice_flap_gate_cbo.findText(data)
                            if index == -1:
                                index = 0
                            self.orifice_flap_gate_cbo.setCurrentIndex(index)
                               
                        elif column == 8:
                            self.orifice_open_close_time_dbox.setValue(data)                                 
                                           
                        elif column == 9:
                            if data not in ("CIRCULAR", "RECT_CLOSED", "Circular", "Rect_Closed", "circular", "rect_closed"):  
                                wrong_status += 1 
                                data = "CIRCULAR"  
                                item.setData(Qt.DisplayRole, data) 
                            index = self.orifice_shape_cbo.findText(data)
                            if index == -1:
                                index = 0
                            self.orifice_shape_cbo.setCurrentIndex(index)

                        elif column == 10:
                            self.orifice_height_dbox.setValue(data)  
                                       
                        elif column == 11:
                            self.orifice_width_dbox.setValue(data)

                    if column > 0:  # Omit fid number (in column = 0)
                        if column in (1, 2, 3, 4, 7, 9):
                            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
 
                        self.orifices_tblw.setItem(row_number, column - 1, item)
                        
            self.highlight_orifice(self.orifice_name_cbo.currentText())                        
            QApplication.restoreOverrideCursor()
            if wrong_status > 0:
                self.uc.show_info("WARNING 070422.0530: there were " + str(wrong_status) + " orifices with wrong type, shape, or flap gate!\n\n" +
                                  "All wrong values were changed to their defaults.\n\n" + 
                                  "Edit them as wished and then 'Save' to replace the values in the 'Storm Drain Orifices' User layers.")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 070422.0730: assignment of value from orifices users layer failed!.\n", e)


    def orifice_crest_height_dbox_valueChanged(self):
        self.box_valueChanged(self.orifice_crest_height_dbox, 4)

    def orifice_discharge_coeff_dbox_valueChanged(self):
        self.box_valueChanged(self.orifice_discharge_coeff_dbox, 5)

    def orifice_open_close_time_dbox_valueChanged(self):
        self.box_valueChanged(self.orifice_open_close_time_dbox, 7)
        
    def orifice_height_dbox_valueChanged(self):
        self.box_valueChanged(self.orifice_height_dbox, 9)
        
    def orifice_width_dbox_valueChanged(self):
        self.box_valueChanged(self.orifice_width_dbox, 10)
        
    def box_valueChanged(self, widget, col):
        row = self.orifice_name_cbo.currentIndex()
        item = QTableWidgetItem()
        item.setData(Qt.EditRole, widget.value())
        # if col in (1, 2, 3, 4, 7, 9):
        #     item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.orifices_tblw.setItem(row, col, item)

    def combo_valueChanged(self, widget, col):
        row = self.orifice_name_cbo.currentIndex()
        item = QTableWidgetItem()
        data = widget.currentText()
        item.setData(Qt.EditRole, data)
        if col in (3, 6, 8):
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)        
        self.orifices_tblw.setItem(row, col, item)

    def orifice_type_cbo_currentIndexChanged(self):
        self.combo_valueChanged(self.orifice_type_cbo, 3)  
              
    def orifice_flap_gate_cbo_currentIndexChanged(self):
        self.combo_valueChanged(self.orifice_flap_gate_cbo, 6) 
        
    def orifice_shape_cbo_currentIndexChanged(self):
        self.combo_valueChanged(self.orifice_shape_cbo, 8)         

    def orifices_tblw_cell_clicked(self, row, column):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.orifice_name_cbo.blockSignals(True)
            self.orifice_name_cbo.setCurrentIndex(row)
            self.orifice_name_cbo.blockSignals(False)

            self.orifice_from_node_txt.setText(self.orifices_tblw.item(row, 1).text())
            self.orifice_to_node_txt.setText(self.orifices_tblw.item(row, 2).text())         

            typ = self.orifices_tblw.item(row, 3).text()
            if typ.isdigit():
                index = int(typ) - 1
                index = 1 if index > 1 else 0 if index < 0 else index
            else:
                index = 0 if typ == "SIDE" else 1
            self.orifice_type_cbo.setCurrentIndex(index)            

            self.orifice_crest_height_dbox.setValue(float(self.orifices_tblw.item(row, 4).text()))
            self.orifice_discharge_coeff_dbox.setValue(float(self.orifices_tblw.item(row, 5).text()))
            
            flap = self.orifices_tblw.item(row, 6).text()
            if flap.isdigit():
                index = int(flap) - 1
                index = 1 if index > 1 else 0 if index < 0 else index
            else:
                index = 0 if flap == "YES" else 1
            self.orifice_flap_gate_cbo.setCurrentIndex(index)             

            self.orifice_open_close_time_dbox.setValue(float(self.orifices_tblw.item(row, 7).text()))
            
            shape = self.orifices_tblw.item(row, 8).text()
            if shape.isdigit():
                index = int(shape) - 1
                index = 1 if index > 1 else 0 if index < 0 else index
            else:
                index = 0 if shape == "CIRCULAR" else 1
            self.orifice_shape_cbo.setCurrentIndex(index)              
            
            self.orifice_height_dbox.setValue(float(self.orifices_tblw.item(row, 9).text()))
            self.orifice_width_dbox.setValue(float(self.orifices_tblw.item(row, 10).text()))            
            
            self.highlight_orifice(self.orifice_name_cbo.currentText()) 
            
            QApplication.restoreOverrideCursor()
            
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 261121.0707: assignment of value failed!.\n", e)

    def onVerticalSectionClicked(self, logicalIndex):
        self.orifices_tblw_cell_clicked(logicalIndex, 0)

    def fill_individual_controls_with_current_orifice_in_table(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            # highlight row in table:
            row = self.orifice_name_cbo.currentIndex()
            self.orifices_tblw.selectRow(row)

            # load controls (text boxes, etc.) with selected row in table:
            item = QTableWidgetItem()

            item = self.orifices_tblw.item(row, 1)
            if item is not None:
                self.orifice_from_node_txt.setText(str(item.text()))

            item = self.orifices_tblw.item(row, 2)
            if item is not None:
                self.orifice_to_node_txt.setText(str(item.text()))

            item = self.orifices_tblw.item(row, 3)
            if item is not None:
                indx = self.orifice_type_cbo.findText(item.text())
                if indx != -1:
                    self.orifice_type_cbo.setCurrentIndex(indx)
                else:
                    self.uc.bar_warn("WARNING 070422.0839: orifice type curve not found.")

            item = self.orifices_tblw.item(row, 4)
            if item is not None:
                self.orifice_crest_height_dbox.setValue(float(str(item.text())))

            item = self.orifices_tblw.item(row, 5)
            if item is not None:
                self.orifice_discharge_coeff_dbox.setValue(float(str(item.text())))

            item = self.orifices_tblw.item(row, 6)
            if item is not None:
                if item.text() in ('YES', 'yes', 'Yes', '0'):
                    self.orifice_flap_gate_cbo.setCurrentIndex(0)  
                else:  
                    self.orifice_flap_gate_cbo.setCurrentIndex(1)  
                
            item = self.orifices_tblw.item(row, 7)
            if item is not None:
                self.orifice_open_close_time_dbox.setValue(float(str(item.text())))
                

            item = self.orifices_tblw.item(row, 8)
            if item is not None:
                if item.text() in ('CIRCULAR', 'circular', 'Circular', '0'):
                    self.orifice_shape_cbo.setCurrentIndex(0)  
                else:  
                    self.orifice_shape_cbo.setCurrentIndex(1)                 
                

            item = self.orifices_tblw.item(row, 9)
            if item is not None:
                self.orifice_height_dbox.setValue(float(str(item.text())))

            item = self.orifices_tblw.item(row, 10)
            if item is not None:
                self.orifice_width_dbox.setValue(float(str(item.text())))

            self.highlight_orifice(self.orifice_name_cbo.currentText()) 
          
            QApplication.restoreOverrideCursor()
            
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 200618.0632: assignment of value failed!.\n", e)

    def find_orifice(self):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.grid_lyr is not None:
                if self.grid_lyr:
                    orifice = self.orifice_to_find_le.text()
                    if orifice != "":
                        indx = self.orifice_name_cbo.findText(orifice)
                        if  indx != -1:
                            self.orifice_name_cbo.setCurrentIndex(indx)
                        else:
                            self.uc.bar_warn("WARNING 070422.0836: orifice '" + str(orifice) + "' not found.")
                    else:
                        self.uc.bar_warn("WARNING  070422.0734: orifice '" + str(orifice) + "' not found.")
        except ValueError:
            self.uc.bar_warn("WARNING  070422.0735: orifice '" + str(orifice) + "' not found.")
            pass
        finally:
            QApplication.restoreOverrideCursor()

    def highlight_orifice(self, orifice):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if self.orifices_lyr is not None:
                if orifice != "":
                    fid = self.gutils.execute("SELECT fid FROM user_swmm_orifices WHERE orifice_name = ?;", (orifice,)).fetchone()
                    self.lyrs.show_feat_rubber(self.orifices_lyr.id(), fid[0], QColor(Qt.yellow))
                    feat = next(self.orifices_lyr.getFeatures(QgsFeatureRequest(fid[0])))
                    x, y = feat.geometry().centroid().asPoint()
                    self.lyrs.zoom_to_all()
                    center_canvas(self.iface, x, y)
                    zoom(self.iface, 0.45)
                else:
                    self.uc.bar_warn("WARNING 070422.0758: orifice '" + str(orifice) + "' not found.")
                    self.lyrs.clear_rubber()
            QApplication.restoreOverrideCursor()
                    
        except ValueError:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("WARNING 070422.0759: orifice '" + str(orifice) + "' is not valid.")
            self.lyrs.clear_rubber()
            pass

    def zoom_in_orifice(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        orifice = self.orifice_name_cbo.currentText()
        fid = self.gutils.execute("SELECT fid FROM user_swmm_orifices WHERE orifice_name = ?;", (orifice,)).fetchone()
        self.lyrs.show_feat_rubber(self.orifices_lyr.id(), fid[0], QColor(Qt.yellow))
        feat = next(self.orifices_lyr.getFeatures(QgsFeatureRequest(fid[0])))
        x, y = feat.geometry().centroid().asPoint()
        center_canvas(self.iface, x, y)
        zoom(self.iface, 0.4)
        QApplication.restoreOverrideCursor()

    def zoom_out_orifice(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        orifice = self.orifice_name_cbo.currentText()
        fid = self.gutils.execute("SELECT fid FROM user_swmm_orifices WHERE orifice_name = ?;", (orifice,)).fetchone()
        self.lyrs.show_feat_rubber(self.orifices_lyr.id(), fid[0], QColor(Qt.yellow))
        feat = next(self.orifices_lyr.getFeatures(QgsFeatureRequest(fid[0])))
        x, y = feat.geometry().centroid().asPoint()
        center_canvas(self.iface, x, y)
        zoom(self.iface, -0.4)
        QApplication.restoreOverrideCursor()

    def save_orifices(self):
        """
        Save changes of user_swmm_orifices layer.
        """
        update_qry = """
                        UPDATE user_swmm_orifices
                        SET
                            orifice_name = ?,
                            orifice_inlet = ?, 
                            orifice_outlet = ?,
                            orifice_type = ?,
                            orifice_crest_height = ?,
                            orifice_disch_coeff = ?,
                            orifice_flap_gate = ?,
                            orifice_open_close_time = ?,
                            orifice_shape = ?,
                            orifice_height = ?,
                            orifice_width = ?                                                
                        WHERE fid = ?;"""

        for row in range(0, self.orifices_tblw.rowCount()):
            item = QTableWidgetItem()
            fid = self.orifice_name_cbo.itemData(row)

            item = self.orifices_tblw.item(row, 0)
            if item is not None:
                orifice_name = str(item.text())

            item = self.orifices_tblw.item(row, 1)
            if item is not None:
                orifice_inlet = str(item.text())

            item = self.orifices_tblw.item(row, 2)
            if item is not None:
                orifice_outlet = str(item.text())
                
            item = self.orifices_tblw.item(row, 3)
            if item is not None:
                typ = str(item.text())
                orifice_type = typ if typ in ["SIDE", "BOTTOM"] else "SIDE"                

            item = self.orifices_tblw.item(row, 4)
            if item is not None:
                orifice_crest_height = str(item.text())

            item = self.orifices_tblw.item(row, 5)
            if item is not None:
                orifice_disch_coeff = str(item.text())
                
            item = self.orifices_tblw.item(row, 6)
            if item is not None:
                gate = str(item.text())
                orifice_flap_gate = gate if gate in ["YES", "NO"] else "YES"

            item = self.orifices_tblw.item(row, 7)
            if item is not None:
                orifice_open_close_time = str(item.text())
                
            item = self.orifices_tblw.item(row, 8)
            if item is not None:
                shape = str(item.text())
                orifice_shape = shape if shape in ["CIRCULAR", "RECT_CLOSED"] else "CIRCULAR"                

            item = self.orifices_tblw.item(row, 9)
            if item is not None:
                orifice_height = str(item.text())

            item = self.orifices_tblw.item(row, 10)
            if item is not None:
                orifice_width = str(item.text())                
                
            self.gutils.execute(
                update_qry,
                (
                    orifice_name,
                    orifice_inlet, 
                    orifice_outlet,
                    orifice_type,
                    orifice_crest_height,
                    orifice_disch_coeff,
                    orifice_flap_gate,
                    orifice_open_close_time,
                    orifice_shape,
                    orifice_height,
                    orifice_width,                      
                    fid,
                ),
            )


     