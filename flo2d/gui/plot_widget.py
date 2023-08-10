# -*- coding: utf-8 -*-

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
        self.plot.scene().sigMouseClicked.connect(self.mouse_clicked)     

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
        self.plot.setLabel("bottom", text="")
        self.plot.setLabel("left", text="")
        self.items = {}

    def add_item(self, name, data, col=QColor("#0000aa"), sty=Qt.SolidLine):
        x, y = data
        pen = pg.mkPen(color=col, width=2, style=sty, cosmetic=True)
        self.items[name] = self.plot.plot(x=x, y=y, connect="finite", pen=pen, name=name)

    # def addItem(self, item, name):
    #     widget = QRadioButton(name)
    #     palette = widget.palette()
    #     # palette.setColor(QPalette.Window, Qt.transparent)
    #     # palette.setColor(QPalette.WindowText, Qt.white)
    #     widget.setPalette(palette)
    #     # self._group.addButton(widget)
    #     # row = self.layout.rowCount()
    #     # widget.clicked.connect(lambda: self.clicked.emit(row))
    #     proxy = item.scene().addWidget(widget)
    #     if isinstance(item, ItemSample):
    #         sample = item
    #     else:
    #         sample = ItemSample(item)
    #     self.layout.addItem(proxy, row, 0)
    #     self.layout.addItem(sample, row, 1)
    #     self.items.append((proxy, sample))
    #     self.updateSize()

    def mouse_clicked(self, mouseClickEvent):
            # mouseClickEvent is a pyqtgraph.GraphicsScene.mouseEvents.MouseClickEvent
            print('clicked plot 0x{:x}, event: {}'.format(id(self),mouseClickEvent ))
            actions = []
            if mouseClickEvent.button() == 1:
                title = self.plot.titleLabel.text
                if "Discharge" in title:
                    menu = QMenu()
              
                    n_items = len(self.plot.legend.items)
                    if n_items > 0:
                        self.chbox = []
                        for i in range(0,n_items):
                            a_chbox = QCheckBox(" " + self.plot.legend.items[i][1].text)
                            checkableAction = QWidgetAction(menu)
                            checkableAction.setDefaultWidget(a_chbox)
                            action = menu.addAction(checkableAction) 
                            a_chbox.setChecked(True)
                            a_chbox.stateChanged.connect(self.checkboxChanged)                            
                            self.chbox.append([a_chbox,action])
                            
                            self.plot.legend.items[i][1].show()
                            self.plot.items[i].show()                            
                            
                        selected_action = menu.exec_(QPoint(mouseClickEvent.screenPos().x(), mouseClickEvent.screenPos().y()))
                    
    def checkboxChanged(self, state):
        n_chboxes = len(self.chbox)
        if  n_chboxes > 0:
            # Redraw plot with checked/unchecked variables:
            for i in range(0, n_chboxes):
                if not self.chbox[i][0].isChecked():
                    self.plot.legend.items[i][1].hide()
                    self.plot.items[i].hide()
                else:
                    self.plot.legend.items[i][1].show()
                    self.plot.items[i].show()
        else:
            print("No checkboxes")         

    def mouseDoubleClickEvent(self, e):
 
        # increase the scale of the graph
        # x-axis by 2 and y-axis by 2
        # self.scale(2, 2)
 
        # print the message
        print("Mouse Double Click Event")


    def update_item(self, name, data):
        x, y = data
        self.items[name].setData(x, y)

    def remove_item(self, name):
        if self.plot.legend:
            if name in self.items:
                self.plot.removeItem(self.items[name])
                # self.plot.plot.legend.scene().removeItem(self.items[name])

    # def add_org_bed_plot(self, data):
    #     x, y = data
    #     pen = pg.mkPen(color=QColor("#000000"), width=1, cosmetic=True)
    #     self.items["org_bed"] = self.plot.plot(x=x, y=y, connect="finite", pen=pen, name="Original Bed")
    #
    # def add_new_bed_plot(self, data):
    #     x, y = data
    #     pen = pg.mkPen(color=QColor("#17874e"), width=2, cosmetic=True)
    #     self.items["new_bed"] = self.plot.plot(x=x, y=y, connect="finite", pen=pen, name="Current Bed")
