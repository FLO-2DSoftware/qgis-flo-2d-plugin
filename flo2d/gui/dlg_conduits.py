# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from ..utils import is_true
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QApplication, QTableWidgetItem, QDialogButtonBox
from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui('conduits')

class ConduitsDialog(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = None
        self.gutils = None

        self.conduits_buttonBox.button(QDialogButtonBox.Save).setText("Save to 'Storm Drain Conduits' User Layer")
        self.conduit_name_cbo.currentIndexChanged.connect(self.fill_individual_controls_with_current_conduit_in_table)
        self.conduits_buttonBox.accepted.connect(self.save_conduits)

        # Connections from individual controls to particular cell in conduits_tblw table widget:
        # self.from_inlet_txt.textChanged.connect(self.from_inlet_txt_textChanged)
        # self.to_inlet_txt.textChanged.connect(self.to_inlet_txt_txtChanged)
        # self.inlet_inv_dbox.valueChanged.connect(self.inlet_inv_dbox_valueChanged)
        # self.outlet_inv_dbox.valueChanged.connect(self.outlet_inv_dbox_valueChanged)
        self.inlet_offset_dbox.valueChanged.connect(self.inlet_offset_dbox_valueChanged)
        self.outlet_offset_dbox.valueChanged.connect(self.outlet_offset_dbox_valueChanged)

        self.conduit_shape_cbo.currentIndexChanged.connect(self.conduit_shape_cbo_currentIndexChanged)
        self.barrels_sbox.valueChanged.connect(self.barrels_sbox_valueChanged)
        self.max_depth_dbox.valueChanged.connect(self.max_depth_dbox_valueChanged)
        self.geom2_dbox.valueChanged.connect(self.geom2_dbox_valueChanged)
        self.geom3_dbox.valueChanged.connect(self.geom3_dbox_valueChanged)
        self.geom4_dbox.valueChanged.connect(self.geom4_dbox_valueChanged)
        self.length_dbox.valueChanged.connect(self.length_dbox_valueChanged)
        self.mannings_dbox.valueChanged.connect(self.mannings_dbox_valueChanged)
        self.initial_flow_dbox.valueChanged.connect(self.initial_flow_dbox_valueChanged)
        self.max_flow_dbox.valueChanged.connect(self.max_flow_dbox_valueChanged)
        self.inlet_losses_dbox.valueChanged.connect(self.inlet_losses_dbox_valueChanged)
        self.outlet_losses_dbox.valueChanged.connect(self.outlet_losses_dbox_valueChanged)
        self.average_losses_dbox.valueChanged.connect(self.average_losses_dbox_valueChanged)
        self.flap_gate_chbox.stateChanged.connect(self.flap_gate_chbox_stateChanged)

        self.shape = ('Circular',
                      'Circular Force Main',
                      'Filled Circular',
                      'Semi-Circular',
                      'Rectangular Closed',
                      'Rectangular Open',
                      'Rectangular Triangular',
                      'Rectangular Round',
                      'Trapezoidal',
                      'Triangular',
                      'Horizontal Ellipse',
                      'Vertical Ellipse',
                      'Semi-Elliptical',
                      'Basket Handle',
                      'Modified Basket Handle',
                      'Arch',
                      'Parabolic',
                      'Power',
                      'Egg',
                      'Horse Shoe',
                      'Gothic',
                      'Catenary',
                      'Irregular',
                      'Custom')

        # self.set_header()
        self.setup_connection()
        self.populate_conduits()

        self.conduits_tblw.cellClicked.connect(self.conduits_tblw_cell_clicked)

    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    # def from_inlet_txt_textChanged(self):
    #     self.text_valueChanged(self.inlet_inv_dbox, 2)
    #
    # def to_inlet_txt_textChanged(self):
    #     self.text_valueChanged(self.inlet_inv_dbox, 3)
    #
    # def inlet_inv_dbox_valueChanged(self):
    #     self.box_valueChanged(self.inlet_inv_dbox, 4)

    """
    Events for changes in values of widgets: 
    
    """

    def inlet_offset_dbox_valueChanged(self):
        self.box_valueChanged(self.inlet_offset_dbox, 3)

    def outlet_offset_dbox_valueChanged(self):
        self.box_valueChanged(self.outlet_offset_dbox, 4)

    def conduit_shape_cbo_currentIndexChanged(self):
        # self.combo_valueChanged(self.conduit_shape_cbo, 5)
        # row = self.conduit_name_cbo.currentIndex()
        # item = QTableWidgetItem()
        # item.setData(Qt.EditRole, self.conduit_shape_cbo.currentIndex()+1)
        # self.conduits_tblw.setItem(row, 5, item)
        shape = self.conduit_shape_cbo.currentText()
        row = self.conduit_name_cbo.currentIndex()
        item = QTableWidgetItem()
        item.setData(Qt.EditRole, shape)
        self.conduits_tblw.setItem(row, 5, item)

    def barrels_sbox_valueChanged(self):
        self.box_valueChanged(self.barrels_sbox, 6)

    def max_depth_dbox_valueChanged(self):
        self.box_valueChanged(self.max_depth_dbox, 7)

    def geom2_dbox_valueChanged(self):
        self.box_valueChanged(self.geom2_dbox, 8)

    def geom3_dbox_valueChanged(self):
        self.box_valueChanged(self.geom3_dbox, 9)

    def geom4_dbox_valueChanged(self):
        self.box_valueChanged(self.geom4_dbox, 10)

    def length_dbox_valueChanged(self):
        self.box_valueChanged(self.length_dbox, 11)

    def mannings_dbox_valueChanged(self):
        self.box_valueChanged(self.mannings_dbox, 12)

    def initial_flow_dbox_valueChanged(self):
        self.box_valueChanged(self.initial_flow_dbox, 13)

    def max_flow_dbox_valueChanged(self):
        self.box_valueChanged(self.max_flow_dbox, 14)

    def inlet_losses_dbox_valueChanged(self):
        self.box_valueChanged(self.inlet_losses_dbox, 15)

    def outlet_losses_dbox_valueChanged(self):
        self.box_valueChanged(self.outlet_losses_dbox, 16)

    def average_losses_dbox_valueChanged(self):
        self.box_valueChanged(self.average_losses_dbox, 17)

    def flap_gate_chbox_stateChanged(self):
        self.checkbox_valueChanged(self.flap_gate_chbox, 18)

    """
    General routines for changes in widgets:
    
    """

    def box_valueChanged(self, widget, col):
        row = self.conduit_name_cbo.currentIndex()
        item = QTableWidgetItem()
        item.setData(Qt.EditRole, widget.value())
        self.conduits_tblw.setItem(row, col, item)

    def checkbox_valueChanged(self, widget, col):
        row = self.conduit_name_cbo.currentIndex()
        item = QTableWidgetItem()
        item.setData(Qt.EditRole, widget.isChecked())
        self.conduits_tblw.setItem(row, col, item)

    def combo_valueChanged(self, widget, col):
        row = self.conduit_name_cbo.currentIndex()
        item = QTableWidgetItem()
        data = widget.currentText()
        item.setData(Qt.EditRole, data)
        self.conduits_tblw.setItem(row, col, item)

    def conduits_tblw_cell_clicked(self, row, column):
        try:
            # self.blockSignals(True)
            self.conduit_name_cbo.blockSignals(True)
            self.conduit_name_cbo.setCurrentIndex(row)
            self.conduit_name_cbo.blockSignals(False)

            self.from_node_txt.setText(self.conduits_tblw.item(row, 1).text())
            self.to_node_txt.setText(self.conduits_tblw.item(row, 2).text())

            value = self.conduits_tblw.item(row, 3).text()
            value = 0 if value == "" else float(value)
            self.inlet_offset_dbox.setValue(value)

            value = self.conduits_tblw.item(row, 4).text()
            value = 0 if value == "" else float(value)
            self.outlet_offset_dbox.setValue(value)

            # # Set index of conduit_shape_cbo (a combo) depending of text contents:
            # item =  self.conduits_tblw.item(row,5)
            # if item is not None:
            #     itemTxt = item.text()
            #     if itemTxt in ['Circular', 'Rectangular', 'Ellipse', 'Arch']:
            #         index = self.conduit_shape_cbo.findText(itemTxt)
            #     else:
            #         if itemTxt == "":
            #             index = 0
            #         else:
            #             index  = int(itemTxt)
            #     index = 3 if index > 3 else 0 if index < 0 else index
            #     self.conduit_shape_cbo.setCurrentIndex(index)
            #     item = QTableWidgetItem()
            #     item.setData(Qt.EditRole,self.conduit_shape_cbo.currentText() )
            #     self.conduits_tblw.setItem(row, 5, item)

            shape = self.conduits_tblw.item(row, 5).text()
            if shape.isdigit():
                index = int(shape)-1
                index = 23 if index > 23 else 0 if index < 0 else index
                self.conduit_shape_cbo.setCurrentIndex(index)
            else:
                shape = shape.title().strip()
                index = self.shape.index(shape) if shape in self.shape else 0
                self.conduit_shape_cbo.setCurrentIndex(index)

            self.barrels_sbox.setValue(float(self.conduits_tblw.item(row, 6).text()))
            self.max_depth_dbox.setValue(float(self.conduits_tblw.item(row, 7).text()))
            self.geom2_dbox.setValue(float(self.conduits_tblw.item(row, 8).text()))
            self.geom3_dbox.setValue(float(self.conduits_tblw.item(row, 9).text()))
            self.geom4_dbox.setValue(float(self.conduits_tblw.item(row, 10).text()))

            self.length_dbox.setValue(float(self.conduits_tblw.item(row, 11).text()))
            self.mannings_dbox.setValue(float(self.conduits_tblw.item(row, 12).text()))
            self.initial_flow_dbox.setValue(float(self.conduits_tblw.item(row, 13).text()))
            self.max_flow_dbox.setValue(float(self.conduits_tblw.item(row, 14).text()))

            self.inlet_losses_dbox.setValue(float(self.conduits_tblw.item(row, 15).text()))
            self.outlet_losses_dbox.setValue(float(self.conduits_tblw.item(row, 16).text()))
            self.average_losses_dbox.setValue(float(self.conduits_tblw.item(row, 17).text()))
            self.flap_gate_chbox.setChecked(True if self.conduits_tblw.item(row, 18).text() == 'True' else False)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 200618.0707: assignment of value failed!.\n", e)

    def populate_conduits(self):
        qry = '''SELECT fid,
                        conduit_name,
                        conduit_inlet, 
                        conduit_outlet,
                        conduit_inlet_offset,
                        conduit_outlet_offset,
                        xsections_shape,
                        xsections_barrels,
                        xsections_max_depth,
                        xsections_geom2,  
                        xsections_geom3,  
                        xsections_geom4,                                                  
                        conduit_length,
                        conduit_manning,
                        conduit_init_flow,
                        conduit_max_flow,
                        losses_inlet,
                        losses_outlet,
                        losses_average,
                        losses_flapgate
                FROM user_swmm_conduits;'''

        try:
            rows = self.gutils.execute(qry).fetchall()
            self.conduits_tblw.setRowCount(0)
            for row_number, row_data in enumerate(rows):     # In each iteration gets, for example:
                                                             # ('C1',  'J3','O2', 2581, 123, 3, 32, 12.5, 2.34, 4.5, 7.0, 2.1, 0.04, 2.6, 0.87)
                self.conduits_tblw.insertRow(row_number)
                for element, data in enumerate(row_data): # For each iteration gets, for example: first iteration:
                                                             # 'C1', 2nd. iteration 1, 'J3', etc
                    item = QTableWidgetItem()
                    item.setData(Qt.DisplayRole, data)  # item gets value of data (as QTableWidgetItem Class)

                    # Fill the list of inlet names:
                    if element == 1:   #We need 2nd. element: 'J3' in the example above, and its fid from row_data[0]
                        self.conduit_name_cbo.addItem(data, row_data[0])

                    # Fill all text boxes with data of first feature of query (first element in table user_swmm_conduits):
                    if row_number == 0:
                        if element == 2:
                            self.from_node_txt.setText(str(data))

                        elif element == 3:
                            self.to_node_txt.setText(str(data))

                        elif element == 4:
                            self.inlet_offset_dbox.setValue(data if data is not None else 0)

                        elif element == 5:
                            self.outlet_offset_dbox.setValue(data if data is not None else 0)

                        elif element == 6:
                            if data.isdigit():
                                self.conduit_shape_cbo.setCurrentIndex(data-1)
                            else:
                                data = data.title().strip()
                                index = self.shape.index(data) if data in self.shape else -1
                                self.conduit_shape_cbo.setCurrentIndex(index)

                        elif element == 7:
                            self.barrels_sbox.setValue(data if data is not None else 0)

                        elif element == 8:
                            self.max_depth_dbox.setValue(data if data is not None else 0)

                        elif element == 9:
                            self.geom2_dbox.setValue(data if data is not None else 0)

                        elif element == 10:
                            self.geom3_dbox.setValue(data if data is not None else 0)

                        elif element == 11:
                            self.geom4_dbox.setValue(data if data is not None else 0)

                        elif element == 12:
                            self.length_dbox.setValue(data if data is not None else 0)

                        elif element == 13:
                            self.mannings_dbox.setValue(data if data is not None else 0)

                        elif element == 14:
                            self.initial_flow_dbox.setValue(data if data is not None else 0)

                        elif element == 15:
                            self.max_flow_dbox.setValue(data if data is not None else 0)

                        elif element == 16:
                            self.inlet_losses_dbox.setValue(data if data is not None else 0)

                        elif element == 17:
                            self.outlet_losses_dbox.setValue(data if data is not None else 0)

                        elif element == 18:
                            self.average_losses_dbox.setValue(data if data is not None else 0)

                        elif element == 19:
                            self.flap_gate_chbox.setChecked(True if is_true(data) else False)

                    if element > 0:    # For this row omit fid number
                        if element == 1 or element == 2 or element == 3:
                            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                        self.conduits_tblw.setItem(row_number, element-1, item)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 200618.0705: assignment of value from conduits users layer failed!.\n", e)

    def fill_individual_controls_with_current_conduit_in_table(self):
        try:
            # Highlight row in table:
            row = self.conduit_name_cbo.currentIndex()
            self.conduits_tblw.selectRow(row)

            # Load controls (text boxes, etc.) with selected row in table:
            item = QTableWidgetItem()

            item = self.conduits_tblw.item(row, 1)
            if item is not None:
                self.from_node_txt.setText(str(item.text()))

            item = self.conduits_tblw.item(row, 2)
            if item is not None:
                self.to_node_txt.setText(str(item.text()))

            item = self.conduits_tblw.item(row, 3)
            if item is not None and item.text() != "":
                self.inlet_offset_dbox.setValue(float(item.text()))

            item = self.conduits_tblw.item(row, 4)
            if item is not None and item.text() != "":
                self.outlet_offset_dbox.setValue(float(item.text()))

            item = self.conduits_tblw.item(row, 5)
            if item is not None:
                if item.text().isdigit():
                    index = int(item.text())
                    index = 23 if index > 23 else 0 if index < 0 else index - 1
                    self.conduit_shape_cbo.setCurrentIndex(index)
                else:
                    txt = item.text().capitalize()
                    index = self.shape.index(txt) if txt in self.shape else -1
                    self.conduit_shape_cbo.setCurrentIndex(index)

            item = self.conduits_tblw.item(row, 6)
            if item is not None:
                self.barrels_sbox.setValue(float(item.text()))

            item = self.conduits_tblw.item(row, 7)
            if item is not None and item.text() != "":
                self.max_depth_dbox.setValue(float(item.text()))

            item = self.conduits_tblw.item(row, 8)
            if item is not None and item.text() != "":
                self.geom2_dbox.setValue(float(item.text()))

            item = self.conduits_tblw.item(row, 9)
            if item is not None and item.text() != "":
                self.geom3_dbox.setValue(float(item.text()))

            item = self.conduits_tblw.item(row, 10)
            if item is not None and item.text() != "":
                self.geom4_dbox.setValue(float(item.text()))

            item = self.conduits_tblw.item(row, 11)
            if item is not None and item.text() != "":
                self.length_dbox.setValue(float(item.text()))

            item = self.conduits_tblw.item(row, 12)
            if item is not None and item.text() != "":
                self.mannings_dbox.setValue(float(item.text()))

            item = self.conduits_tblw.item(row, 13)
            if item is not None and item.text() != "":
                self.initial_flow_dbox.setValue(float(item.text()))

            item = self.conduits_tblw.item(row, 14)
            if item is not None and item.text() != "":
                self.max_flow_dbox.setValue(float(item.text()))

            item = self.conduits_tblw.item(row, 15)
            if item is not None and item.text() != "":
                self.inlet_losses_dbox.setValue(float(item.text()))

            item = self.conduits_tblw.item(row, 16)
            if item is not None and item.text() != "":
                self.outlet_losses_dbox.setValue(float(item.text()))

            item = self.conduits_tblw.item(row, 17)
            if item is not None and item.text() != "":
                self.average_losses_dbox.setValue(float(item.text()))

            item = self.conduits_tblw.item(row, 18)
            if item is not None:
                self.flap_gate_chbox.setChecked(True if item.text() == 'True' or item.text() == 'True' or item.text() == '1' else False)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 200618.0631: assignment of value failed!.\n", e)

    def save_conduits(self):
        """
        Save changes of user_swmm_conduits layer.
        """
        # self.save_attrs()
        update_qry = '''
                        UPDATE user_swmm_conduits
                        SET
                            conduit_name = ?,
                            conduit_inlet = ?, 
                            conduit_outlet = ?,
                            conduit_inlet_offset = ?,
                            conduit_outlet_offset = ?,
                            xsections_shape = ?,
                            xsections_barrels = ?,
                            xsections_max_depth = ?,
                            xsections_geom2 = ?,  
                            xsections_geom3 = ?,  
                            xsections_geom4 = ?,  
                            conduit_length = ?,
                            conduit_manning = ?,
                            conduit_init_flow = ?,
                            conduit_max_flow = ?,
                            losses_inlet = ?,
                            losses_outlet = ?,
                            losses_average = ?,
                            losses_flapgate  = ?                            
                        WHERE fid = ?;'''

        for row in range(0, self.conduits_tblw.rowCount()):
            item = QTableWidgetItem()
            # fid = row + 1
            fid = self.conduit_name_cbo.itemData(row)

            item = self.conduits_tblw.item(row, 0)
            if item is not None:
                conduit_name = str(item.text())

            item = self.conduits_tblw.item(row, 1)
            if item is not None:
                conduit_inlet = str(item.text())

            item = self.conduits_tblw.item(row, 2)
            if item is not None:
                conduit_outlet = str(item.text())

            item = self.conduits_tblw.item(row, 3)
            if item is not None:
                conduit_inlet_offset = str(item.text())

            item = self.conduits_tblw.item(row, 4)
            if item is not None:
                conduit_outlet_offset = str(item.text())

            item = self.conduits_tblw.item(row, 5)
            if item is not None:
                xsections_shape = str(item.text())

            item = self.conduits_tblw.item(row, 6)
            if item is not None:
                xsections_barrels = str(item.text())

            item = self.conduits_tblw.item(row, 7)
            if item is not None:
                xsections_max_depth = str(item.text())

            item = self.conduits_tblw.item(row, 8)
            if item is not None:
                xsections_geom2 = str(item.text())

            item = self.conduits_tblw.item(row, 9)
            if item is not None:
                xsections_geom3 = str(item.text())

            item = self.conduits_tblw.item(row, 10)
            if item is not None:
                xsections_geom4 = str(item.text())

            item = self.conduits_tblw.item(row, 11)
            if item is not None:
                conduit_length = str(item.text())

            item = self.conduits_tblw.item(row, 12)
            if item is not None:
                conduit_manning = str(item.text())

            item = self.conduits_tblw.item(row, 13)
            if item is not None:
                conduit_init_flow = str(item.text())

            item = self.conduits_tblw.item(row, 14)
            if item is not None:
                conduit_max_flow = str(item.text())

            item = self.conduits_tblw.item(row, 15)
            if item is not None:
                losses_inlet = str(item.text())

            item = self.conduits_tblw.item(row, 16)
            if item is not None:
                losses_outlet = str(item.text())

            item = self.conduits_tblw.item(row, 17)
            if item is not None:
                losses_average = str(item.text())

            item = self.conduits_tblw.item(row, 18)
            if item is not None:
                losses_flapgate = str(item.text())

            self.gutils.execute(update_qry, (conduit_name,
                                             conduit_inlet,
                                             conduit_outlet,
                                             conduit_inlet_offset,
                                             conduit_outlet_offset,
                                             xsections_shape,
                                             xsections_barrels,
                                             xsections_max_depth,
                                             xsections_geom2,
                                             xsections_geom3,
                                             xsections_geom4,
                                             conduit_length,
                                             conduit_manning,
                                             conduit_init_flow,
                                             conduit_max_flow,
                                             losses_inlet,
                                             losses_outlet,
                                             losses_average,
                                             losses_flapgate,
                                             fid))
