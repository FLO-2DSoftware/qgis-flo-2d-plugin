# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtGui import *
from ..deps import safe_pyqtgraph as pg

pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')
pg.setConfigOption('antialias', True)


class PlotWidget(QWidget):

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
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

    def clear_plot(self):
        self.plot.clear()

    def add_org_bed_plot(self, data):
        x, y = data
        pen = pg.mkPen(color=QColor("#000000"), width=1, cosmetic=True)
        self.org_bed_plot = self.plot.plot(x=x, y=y, connect='finite', pen=pen, name='Existing')

    def add_new_bed_plot(self, data):
        x, y = data
        pen = pg.mkPen(color=QColor("#17874e"), width=2, cosmetic=True)
        self.new_bed_plot = self.plot.plot(x=x, y=y, connect='finite', pen=pen, name='Changed')

    def add_org_plot(self, data):
        x, y = data
        pen = pg.mkPen(color=QColor("#000000"), width=1, cosmetic=True)
        self.org_plot = self.plot.plot(x=x, y=y, connect='finite', pen=pen, name='Existing')

    def add_new_plot(self, data):
        x, y = data
        pen = pg.mkPen(color=QColor("#0000aa"), width=2, cosmetic=True)
        self.new_plot = self.plot.plot(x=x, y=y, connect='finite', pen=pen, name='Changed')
