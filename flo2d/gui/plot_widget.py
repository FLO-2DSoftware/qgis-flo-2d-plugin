# # -*- coding: utf-8 -*-
#  
# # FLO-2D Preprocessor tools for QGIS
# # Copyright © 2016 Lutra Consulting for FLO-2D
#  
# # This program is free software; you can redistribute it and/or
# # modify it under the terms of the GNU General Public License
# # as published by the Free Software Foundation; either version 2
# # of the License, or (at your option) any later version
#  
# from qgis.PyQt.QtCore import Qt, QSize
# from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget
# from qgis.PyQt.QtGui import QColor
#  
# from ..deps import safe_pyqtgraph as pg
#  
# pg.setConfigOption('background', 'w')
# pg.setConfigOption('foreground', 'k')
# pg.setConfigOption('antialias', True)
#  
#  
# class PlotWidget(QWidget):
#     _sizehint = None
#  
#     def __init__(self):
#         QWidget.__init__(self)
#         self.items = {}
#         self.org_bed_plot = None
#         self.new_bed_plot = None
#         self.org_plot = None
#         self.new_plot = None
#         self.layout = QVBoxLayout()
#         self.pw = pg.PlotWidget()
#         self.plot = self.pw.getPlotItem()
#         self.plot.showGrid(x=True, y=True)
#         self.layout.addWidget(self.pw)
#         self.setLayout(self.layout)
#  
#     def setSizeHint(self, width, height):
#         self._sizehint = QSize(width, height)
#  
#     def sizeHint(self):
#         # print('sizeHint:', self._sizehint)
#         if self._sizehint is not None:
#             return self._sizehint
#         return super(PlotWidget, self).sizeHint()
#  
#     def clear(self):
# #         self.clear_plot_legend()
#         self.plot.clear()
#         self.plot.setTitle()
#         self.plot.setLabel('bottom', text='')
#         self.plot.setLabel('left', text='')
#  
#     def add_item(self, name, data, col=QColor("#0000aa"), sty=Qt.SolidLine):
#         x, y = data
#         pen = pg.mkPen(color=col, width=2, style=sty, cosmetic=True)
#         self.items[name] = self.plot.plot(x=x, y=y, connect='finite', pen=pen, name=name)
#  
#     def update_item(self, name, data):
#         x, y = data
#         self.items[name].setData(x, y)
#  
#     def remove_item(self, name):
#         self.plot.removeItem(self.items[name])
#  
#     # specific plot items
#  
#     def add_org_bed_plot(self, data):
#         x, y = data
#         pen = pg.mkPen(color=QColor("#000000"), width=1, cosmetic=True)
#         self.items['org_bed'] = self.plot.plot(x=x, y=y, connect='finite', pen=pen, name='Original Bed')
#  
#     def add_new_bed_plot(self, data):
#         x, y = data
#         pen = pg.mkPen(color=QColor("#17874e"), width=2, cosmetic=True)
#         self.items['new_bed'] = self.plot.plot(x=x, y=y, connect='finite', pen=pen, name='Current Bed')
#  
#     def clear_plot_legend(self):
# #         self.plot.legend.scene().removeItem(self.plot.legend)  
# #         for x in self.items:
# #             self.plot.removeItem(x)
# #             x.close() 
# #         self.items = {} 
# #         self.plot.legend.updateSize()   
#                      
#         layout = self.layout
#         layout = None
#         self.layout = None
# #         self.plot.legend.updateSize()
# #         layout.removeItem(layout.itemAt(0))
# #         layout.itemAt(0).close()
#         # bulk removal of everything based on code in LegendItem.py
#         if self.items:
#             pass
# #             for x in layout:
# #     #             layout.removeItem(sample)
# #     #             sample.close()
# #                 layout.removeItem(x)
# #                 x.close()
#         self.items = {}
# #         self.plot.legend.updateSize()
# 
#     def removeItem(self, name):
#         """
#         Removes one item from the legend. 
# 
#         =========== ========================================================
#         Arguments
#         title       The title displayed for this item.
#         =========== ========================================================
#         """
#         # Thanks, Ulrich!
#         # cycle for a match
#         for sample, label in self.items:
#             if label.text == name:  # hit
#                 self.items.remove( (sample, label) )    # remove from itemlist
#                 self.layout.removeItem(sample)          # remove from layout
#                 sample.close()                          # remove from drawing
#                 self.layout.removeItem(label)
#                 label.close()
#                 self.updateSize()                       # redraq box


########################################################

# -*- coding: utf-8 -*-
 
# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D
 
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
 
from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget
from qgis.PyQt.QtGui import QColor 
from ..deps import safe_pyqtgraph as pg
from ..utils import Msge
 
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')
pg.setConfigOption('antialias', True)
 
 
class PlotWidget(QWidget):
    _sizehint = None
 
    def __init__(self):
        QWidget.__init__(self)
        self.items = {}
        self.org_bed_plot = None
        self.new_bed_plot = None
        self.org_plot = None
        self.new_plot = None
        self.layout = QVBoxLayout()
        self.pw = pg.PlotWidget()
        self.plot = self.pw.getPlotItem()
        self.plot.showGrid(x=True, y=True)
        self.layout.addWidget(self.pw)
        self.setLayout(self.layout)
 
    def setSizeHint(self, width, height):
        self._sizehint = QSize(width, height)
 
    def sizeHint(self):
        # print('sizeHint:', self._sizehint)
        if self._sizehint is not None:
            return self._sizehint
        return super(PlotWidget, self).sizeHint()
 
    def clear(self):
        self.plot.clear()
        self.plot.setTitle()
        self.plot.setLabel('bottom', text='')
        self.plot.setLabel('left', text='')
        self.items = {}
 
    def add_item(self, name, data, col=QColor("#0000aa"), sty=Qt.SolidLine):
        x, y = data
        pen = pg.mkPen(color=col, width=2, style=sty, cosmetic=True)
        self.items[name] = self.plot.plot(x=x, y=y, connect='finite', pen=pen, name=name)
 
    def update_item(self, name, data):
        x, y = data
        self.items[name].setData(x, y)
 
    def remove_item(self, name):
        if self.plot.legend:
            if name in self.items:
                self.plot.removeItem(self.items[name])
                self.plot.plot.legend.scene().removeItem(self.items[name])
                
 
    def add_org_bed_plot(self, data):
        x, y = data
        pen = pg.mkPen(color=QColor("#000000"), width=1, cosmetic=True)
        self.items['org_bed'] = self.plot.plot(x=x, y=y, connect='finite', pen=pen, name='Original Bed')
 
    def add_new_bed_plot(self, data):
        x, y = data
        pen = pg.mkPen(color=QColor("#17874e"), width=2, cosmetic=True)
        self.items['new_bed'] = self.plot.plot(x=x, y=y, connect='finite', pen=pen, name='Current Bed')







