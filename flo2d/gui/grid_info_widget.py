# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from math import sqrt
from qgis.core import QgsFeatureRequest
from qgis.PyQt.QtGui import QStandardItemModel, QStandardItem, QColor, QIntValidator
from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtCore import QSize, Qt
from .ui_utils import load_ui, center_canvas, set_icon, zoom
from ..utils import m_fdata
from ..user_communication import UserCommunication


uiDialog, qtBaseClass = load_ui('grid_info_widget')
class GridInfoWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.canvas = iface.mapCanvas()
        self.plot = plot
        self.plot_item_name = None
        self.table = table
        self.tview = table.tview
        self.data_model = QStandardItemModel()
        self.lyrs = lyrs
        self.setupUi(self)
        self.setEnabled(True)
        self.gutils = None
        self.grid = None
        self.mann_default = None
        self.d1 = []
        self.d2 = []
        
        validator = QIntValidator()
        self.idEdit.setValidator(validator)        
        
        self.find_cell_btn.clicked.connect(self.find_cell)
        set_icon(self.find_cell_btn, 'eye-svgrepo-com.svg')
        
                
    def setSizeHint(self, width, height):
        self._sizehint = QSize(width, height)

    def sizeHint(self):
        if self._sizehint is not None:
            return self._sizehint
        return super(GridInfoWidget, self).sizeHint()

    def set_info_layer(self, lyr):
        self.grid = lyr

    def update_fields(self, fid):
        try:
            if not fid == -1:
                feat = next(self.grid.getFeatures(QgsFeatureRequest(fid)))
                cell_size = sqrt(feat.geometry().area())
                gid = str(fid)
                elev = str(feat['elevation'])
                n = feat['n_value']
                cell = '{}'.format(cell_size)
                if not n:
                    n = '{} (default)'.format(self.mann_default)
                else:
                    pass
                self.idEdit.setText(gid)
                self.elevEdit.setText(elev)
                self.mannEdit.setText(str(n))
                self.cellEdit.setText(cell)
                if self.plot_ckbox.isChecked():
                    self.plot_grid_rainfall(feat)
            else:
                self.idEdit.setText('')
                self.elevEdit.setText('')
                self.mannEdit.setText('')
                self.cellEdit.setText('')
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error('ERROR 290718.1934: error while displaying elevation of cell ' + str(fid)
                               +'\n____________________________________________', e)

    def plot_grid_rainfall(self, feat):
        si = 'inches' if self.gutils.get_cont_par('METRIC') == '0' else 'mm'
        qry = 'SELECT time_interval, iraindum FROM raincell_data WHERE rrgrid=? ORDER BY time_interval;'
        fid = feat['fid']
        rainfall = self.gutils.execute(qry, (fid,))
        self.create_plot()
        self.tview.setModel(self.data_model)
        self.data_model.clear()
        self.data_model.setHorizontalHeaderLabels(['Time', 'Cumulative rainfall'])
        self.d1, self.d1 = [[], []]
        for row in rainfall:
            items = [QStandardItem('{:.4f}'.format(x)) if x is not None else QStandardItem('') for x in row]
            self.data_model.appendRow(items)
            self.d1.append(row[0] if not row[0] is None else float('NaN'))
            self.d2.append(row[1] if not row[1] is None else float('NaN'))
        rc = self.data_model.rowCount()
        if rc < 500:
            for row in range(rc, 500 + 1):
                items = [QStandardItem(x) for x in ('',) * 2]
                self.data_model.appendRow(items)
        self.tview.horizontalHeader().setStretchLastSection(True)
        for col in range(2):
            self.tview.setColumnWidth(col, 100)
        for i in range(self.data_model.rowCount()):
            self.tview.setRowHeight(i, 20)
        self.plot.plot.setTitle('GRID FID: {}'.format(fid))
        self.plot.plot.setLabel('bottom', text='Time (minutes)')
        self.plot.plot.setLabel('left', text='Rainfall ({})'.format(si))
        self.update_plot()

    def create_plot(self):
        
        self.plot.clear()
        if self.plot.plot.legend is not None:
            self.plot.plot.legend.scene().removeItem(self.plot.plot.legend) 
        self.plot.plot.addLegend()         
        
        self.plot_item_name = 'Grid realtime rainfall'
        self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))

    def update_plot(self):
        if not self.plot_item_name:
            return
        self.d1, self.d2 = [[], []]
        for i in range(self.data_model.rowCount()):
            self.d1.append(m_fdata(self.data_model, i, 0))
            self.d2.append(m_fdata(self.data_model, i, 1))
        self.plot.update_item(self.plot_item_name, [self.d1, self.d2])
        
    def find_cell(self):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)  
            grid = self.lyrs.data['grid']['qlyr']
            if grid is not None:
                if grid:
                    cell = self.idEdit.text()
                    if cell != '':
                        cell = int(cell)
                        if len(grid) >= cell and cell > 0:
                            self.lyrs.show_feat_rubber(grid.id(), cell, QColor(Qt.yellow))
                            feat = next(grid.getFeatures(QgsFeatureRequest(cell)))
                            x, y = feat.geometry().centroid().asPoint()                           
                            center_canvas(self.iface, x, y)
                            zoom(self.iface,  0.4)
                            self.mannEdit.setText(str(feat['n_value']))
                            self.elevEdit.setText(str(feat['elevation']))
                            self.cellEdit.setText(str(sqrt(feat.geometry().area())))
                        else:
                            self.uc.bar_warn('Cell ' + str(cell) + ' not found.')
                            self.lyrs.clear_rubber()                            
                    else:
                        self.uc.bar_warn('Cell ' + str(cell) + ' not found.')
                        self.lyrs.clear_rubber()              
        except ValueError:
            self.uc.bar_warn('Cell ' + str(cell) + ' is not valid.')
            self.lyrs.clear_rubber()    
            pass          
        finally:
            QApplication.restoreOverrideCursor()      