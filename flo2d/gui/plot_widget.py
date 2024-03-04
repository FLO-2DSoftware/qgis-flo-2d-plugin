# -*- coding: utf-8 -*-
import numpy as np
# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.PyQt.QtCore import QSize, Qt, QPoint
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import *
from PyQt5.QtWidgets import QMenu, QApplication, QCheckBox, QWidgetAction
from qgis._core import QgsMessageLog

from ..deps import safe_pyqtgraph as pg
from ..utils import Msge

pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "k")
pg.setConfigOption("antialias", True)


class PlotWidget(QWidget):
    _sizehint = None

    def __init__(self):
        QWidget.__init__(self)
        self.items = {}
        self.chbox = []
        self.layout = QVBoxLayout()
        self.pw = pg.PlotWidget()
        self.plot = self.pw.getPlotItem()
        self.plot.showGrid(x=True, y=True)
        self.layout.addWidget(self.pw)
        self.setLayout(self.layout)
        self.plot.scene().sigMouseClicked.connect(self.mouse_clicked)
        self.plot.scene().sigPrepareForPaint.connect(self.prepareForPaint)

    def prepareForPaint(self):
        """
        Function to update the axis when changing the plots
        """
        any_checked = any(self.plot.legend.items[i][1].isVisible() for i in range(0, len(self.plot.legend.items)))
        for i in range(len(self.plot.legend.items)):
            data_tuple = self.items[self.plot.legend.items[i][1].text].getData()
            any_nan = any(np.isnan(data) for data in data_tuple[0])

        if any_checked and not any_nan:
            self.plot.autoRange()

    def setSizeHint(self, width, height):
        self._sizehint = QSize(width, height)

    def sizeHint(self):
        if self._sizehint is not None:
            return self._sizehint
        return super(PlotWidget, self).sizeHint()

    def clear(self):
        self.plot.clear()
        self.plot.setTitle()
        self.plot.setLabel("bottom", text="")
        self.plot.setLabel("left", text="")
        self.items = {}

    def add_item(self, name, data, col=QColor("#0000aa"), sty=Qt.SolidLine, hide=False):
        x, y = data
        pen = pg.mkPen(color=col, width=2, style=sty, cosmetic=True)
        self.items[name] = self.plot.plot(x=x, y=y, connect="finite", pen=pen, name=name)

        if not hide:
            self.items[name].show()
        else:
            self.items[name].hide()

    def mouse_clicked(self, mouseClickEvent):

        if mouseClickEvent.button() == 1:
            title = self.plot.titleLabel.text
            if "Discharge" in title or "Channel" in title or "Cross":
                menu = QMenu()
                n_items = len(self.plot.legend.items)
                if n_items > 0:
                    self.chbox = []
                    for i in range(0, n_items):
                        name = self.plot.legend.items[i][1].text
                        a_chbox = QCheckBox(" " + name)
                        checkableAction = QWidgetAction(menu)
                        checkableAction.setDefaultWidget(a_chbox)
                        action = menu.addAction(checkableAction)
                        a_chbox.stateChanged.connect(self.checkboxChanged)
                        self.chbox.append([a_chbox, action])
                        a_chbox.setChecked(False)
                        self.plot.legend.items[i][1].hide()
                        self.plot.items[i].hide()

                    selected_action = menu.exec_(QPoint(int(mouseClickEvent.screenPos().x()), int(mouseClickEvent.screenPos().y())))
                    
    def checkboxChanged(self, state):
        n_chboxes = len(self.chbox)
        try:
            if n_chboxes > 0:
                # Redraw plot with checked/unchecked variables:
                for i in range(0, n_chboxes):
                    if not self.chbox[i][0].isChecked():
                        self.plot.legend.items[i][1].hide()
                        self.plot.items[i].hide()
                    else:
                        self.plot.legend.items[i][1].show()
                        self.plot.items[i].show()
                self.plot.autoRange()
            else:
                print("No checkboxes")
        except:
            return

    def mouseDoubleClickEvent(self, e):

        # print the message
        print("Mouse Double Click Event")

    def update_item(self, name, data):
        x, y = data
        if name in self.items:
            self.items[name].setData(x, y)

    def remove_item(self, name):
        if self.plot.legend:
            if name in self.items:
                self.plot.removeItem(self.items[name])
