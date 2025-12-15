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
from PyQt5.QtWidgets import QMenu, QCheckBox, QWidgetAction
from qgis._core import QgsMessageLog

from ..deps import safe_pyqtgraph as pg
import numpy as np

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
        self.plot.showGrid(True, True, 0.25)
        self.layout.addWidget(self.pw)

        # Create a horizontal layout for the auto range button
        button_layout = QHBoxLayout()

        self.hover_chbox = QCheckBox("Inspect values")
        self.hover_chbox.setChecked(True)
        self.hover_chbox.stateChanged.connect(self.toggle_hover)
        button_layout.addWidget(self.hover_chbox)

        self.auto_range_btn = QPushButton('Auto Range', self)
        self.auto_range_btn.clicked.connect(self.auto_range)
        button_layout.addWidget(self.auto_range_btn)

        button_layout.setAlignment(Qt.AlignRight)

        # Add the button layout to the main layout
        self.layout.addLayout(button_layout)
        self.setLayout(self.layout)

        self.plot.scene().sigMouseClicked.connect(self.mouse_clicked)
        self.plot.scene().sigPrepareForPaint.connect(self.prepareForPaint)
        self.pw.scene().sigMouseMoved.connect(self.mouse_moved)

        self.init_hover_items()

        self.hover_enabled = True

    def init_hover_items(self):
        self.vb = self.plot.getViewBox()

        self.vline = pg.InfiniteLine(angle=90, movable=False)
        self.hline = pg.InfiniteLine(angle=0, movable=False)

        pen = pg.mkPen(
            color=(0, 0, 0),  # RGB or QColor
            width=0.25
        )

        self.vline.setPen(pen)
        self.hline.setPen(pen)

        self.hover_label = pg.TextItem(anchor=(0, 1))
        self.hover_label.setColor(QColor("#000000"))  # black

        # Marker at snapped point
        self.hover_marker = pg.ScatterPlotItem(size=8, pen=pg.mkPen(None), brush=pg.mkBrush(50, 50, 50, 200))

        for it in (self.vline, self.hline, self.hover_label, self.hover_marker):
            it.setZValue(1e9)

        self.plot.addItem(self.vline, ignoreBounds=True)
        self.plot.addItem(self.hline, ignoreBounds=True)
        self.plot.addItem(self.hover_label)
        self.plot.addItem(self.hover_marker)

        if not getattr(self, "hover_enabled", True):
            self.vline.hide()
            self.hline.hide()
            self.hover_label.hide()
            self.hover_marker.hide()

    def _visible_curves(self):
        return [(name, item) for name, item in self.items.items() if item is not None and item.isVisible()]

    def _nearest_index_sorted(self, x_arr, x_target):
        # x_arr must be 1D sorted ascending
        idx = int(np.searchsorted(x_arr, x_target))
        if idx <= 0:
            return 0
        if idx >= len(x_arr):
            return len(x_arr) - 1
        # choose closer of idx and idx-1
        return idx if abs(x_arr[idx] - x_target) < abs(x_arr[idx - 1] - x_target) else idx - 1

    def _nearest_point_on_curve(self, item, x_target):
        x_arr, y_arr = item.getData()
        if x_arr is None or y_arr is None:
            return None

        x_arr = np.asarray(x_arr, dtype=float)
        y_arr = np.asarray(y_arr, dtype=float)

        finite = np.isfinite(x_arr) & np.isfinite(y_arr)
        if not np.any(finite):
            return None

        x = x_arr[finite]
        y = y_arr[finite]

        if len(x) == 0:
            return None

        # If x is sorted, use searchsorted (fast). If not, fall back to argmin.
        if np.all(x[1:] >= x[:-1]):
            i = self._nearest_index_sorted(x, x_target)
        else:
            i = int(np.abs(x - x_target).argmin())

        return float(x[i]), float(y[i])

    def mouse_moved(self, evt):

        if not getattr(self, "hover_enabled", True):
            return

        pos = evt[0] if isinstance(evt, (tuple, list)) else evt

        if not self.pw.sceneBoundingRect().contains(pos):
            self.vline.hide()
            self.hline.hide()
            self.hover_label.hide()
            self.hover_marker.hide()
            return

        mp = self.vb.mapSceneToView(pos)
        x_mouse = float(mp.x())
        y_mouse = float(mp.y())

        best = None  # (dist2, name, x_snap, y_snap)

        for name, item in self._visible_curves():
            pt = self._nearest_point_on_curve(item, x_mouse)
            if pt is None:
                continue

            x_snap, y_snap = pt

            # Compare distances in scene (pixel-like) coordinates
            scene_snap = self.vb.mapViewToScene(pg.Point(x_snap, y_snap))
            dx = float(scene_snap.x() - pos.x())
            dy = float(scene_snap.y() - pos.y())
            dist2 = dx * dx + dy * dy

            if best is None or dist2 < best[0]:
                best = (dist2, name, x_snap, y_snap)

        if best is None:
            # fall back to plain coords if nothing visible
            self.vline.setPos(x_mouse)
            self.hline.setPos(y_mouse)
            self.hover_label.setText(f"x = {x_mouse:.3f}\ny = {y_mouse:.3f}")
            self.hover_label.setPos(x_mouse, y_mouse)

            self.vline.show()
            self.hline.show()
            self.hover_label.show()
            self.hover_marker.hide()
            return

        _dist2, name, x_snap, y_snap = best

        self.vline.setPos(x_snap)
        self.hline.setPos(y_snap)
        self.vline.show()
        self.hline.show()

        self.hover_marker.setData([x_snap], [y_snap])
        self.hover_marker.show()

        self.hover_label.setText(f"{name}\nx = {x_snap:.3f}\ny = {y_snap:.3f}")
        self.hover_label.setPos(x_snap, y_snap)
        self.hover_label.show()

    def prepareForPaint(self):
        """
        Function to update the axis when changing the plots
        """
        # any_checked = any(self.plot.legend.items[i][1].isVisible() for i in range(0, len(self.plot.legend.items))) #Commented out on 21st June 2025
        if self.plot.legend is None: # Change made on 21st June 2025
            return   # Change made on 21st June 2025

        any_checked = any(self.plot.legend.items[i][1].isVisible() for i in range(len(self.plot.legend.items))) # Change made on 21st June 2025

        for i in range(len(self.plot.legend.items)):
            data_tuple = self.items[self.plot.legend.items[i][1].text].getData()
            any_nan = any(np.isnan(data) for data in data_tuple[0])

        # if any_checked and not any_nan:
        #     self.plot.autoRange()

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
        self.init_hover_items()

    def add_item(self, name, data, col=QColor("#0000aa"), sty=Qt.SolidLine, hide=False):
        x, y = data
        pen = pg.mkPen(color=col, width=2, style=sty, cosmetic=True)
        self.items[name] = self.plot.plot(x=x, y=y, connect="finite", pen=pen, name=name)

        if not hide:
            self.items[name].show()
        else:
            self.items[name].hide()

        self.plot.autoRange()

    def mouse_clicked(self, mouseClickEvent):

        if mouseClickEvent.button() == 1:
            title = self.plot.titleLabel.text
            if "Discharge" in title or "Channel" in title or "Cross" in title:
                menu = QMenu()
                n_items = len(self.plot.legend.items)
                if n_items > 0:
                    self.chbox = []
                    # Build menu from your curve registry (stable)
                    for name, item in self.items.items():
                        a_chbox = QCheckBox(" " + name)
                        a_chbox.setChecked(item.isVisible())  # reflect current state

                        checkableAction = QWidgetAction(menu)
                        checkableAction.setDefaultWidget(a_chbox)
                        action = menu.addAction(checkableAction)

                        # Store mapping: checkbox -> curve name
                        a_chbox.stateChanged.connect(lambda state, n=name: self.checkboxChanged(state, n))

                        self.chbox.append([a_chbox, action])

                    menu.exec_(
                        QPoint(int(mouseClickEvent.screenPos().x()), int(mouseClickEvent.screenPos().y()))
                    )

    def checkboxChanged(self, state, name):
        try:
            item = self.items.get(name)
            if item is None:
                return

            visible = (state == Qt.Checked)
            item.setVisible(visible)

            # Keep legend label in sync (if legend exists)
            if self.plot.legend is not None:
                for sample, label in self.plot.legend.items:
                    if label.text == name:
                        label.setVisible(visible)
                        break

            # If nothing is visible, do not leave a "latest plot" on screen
            any_visible = any(it.isVisible() for it in self.items.values())
            if not any_visible:
                self._hide_hover_overlays()
                self.pw.repaint()  # force refresh in some QGIS embed cases
                return

            self.plot.autoRange()

        except:
            return

    def _hide_hover_overlays(self):
        if hasattr(self, "vline"):
            self.vline.hide()
        if hasattr(self, "hline"):
            self.hline.hide()
        if hasattr(self, "hover_label"):
            self.hover_label.hide()
        if hasattr(self, "hover_marker"):
            self.hover_marker.hide()

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

    def auto_range(self):
        """
        Function to auto range the plot
        """
        self.plot.autoRange()

    def toggle_hover(self, state):
        self.hover_enabled = bool(state)

        if not self.hover_enabled:
            # Hide overlays immediately
            if hasattr(self, "vline"):
                self.vline.hide()
            if hasattr(self, "hline"):
                self.hline.hide()
            if hasattr(self, "hover_label"):
                self.hover_label.hide()
            if hasattr(self, "hover_marker"):
                self.hover_marker.hide()