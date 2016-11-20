# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import Qt
from PyQt4.QtGui import QVBoxLayout, QColor, QWidget

from ..deps import safe_pyqtgraph as pg

pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')
pg.setConfigOption('antialias', True)


class PlotWidget(QWidget):

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

    def clear(self):
        self.plot.clear()
        self.items = {}

    def add_item(self, name, data, col=QColor("#0000aa"), sty=Qt.SolidLine):
        x, y = data
        pen = pg.mkPen(color=col, width=2, style=sty, cosmetic=True)
        self.items[name] = self.plot.plot(x=x, y=y, connect='finite', pen=pen, name=name)

    def update_item(self, name, data):
        x, y = data
        self.items[name].setData(x,y)

    def remove_item(self, name):
        self.plot.removeItem(self.items[name])

    # specific plot items

    def add_org_bed_plot(self, data):
        x, y = data
        pen = pg.mkPen(color=QColor("#000000"), width=1, cosmetic=True)
        self.items['org_bed'] = self.plot.plot(x=x, y=y, connect='finite', pen=pen, name='Original Bed')

    def add_new_bed_plot(self, data):
        x, y = data
        pen = pg.mkPen(color=QColor("#17874e"), width=2, cosmetic=True)
        self.items['new_bed'] = self.plot.plot(x=x, y=y, connect='finite', pen=pen, name='Current Bed')

