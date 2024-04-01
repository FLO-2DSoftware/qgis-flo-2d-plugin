# -*- coding: utf-8 -*-
# FLO-2D Preprocessor tools for QGIS
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from qgis._core import QgsFeatureRequest

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from flo2d.gui.ui_utils import load_ui, center_canvas, zoom, zoom_show_n_cells

uiDialog, qtBaseClass = load_ui("channel_check_report")


class ChannelCheckReportDialog(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs, gutils):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.currentCell = None
        self.gutils = gutils
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.grid = self.lyrs.data["grid"]["qlyr"]
        self.cell_size = self.gutils.get_cont_par("CELLSIZE")

        # connections
        self.previous_btn.clicked.connect(self.show_prev)
        self.next_btn.clicked.connect(self.show_next)
        self.error_grids_cbo.currentIndexChanged.connect(self.show_grid)

    def close_dialog(self):
        """
        Function to close the dialog
        """
        self.report_te.clear()
        self.close()

    def show_prev(self):
        """
        Function to show the previous grid element
        """
        if self.error_grids_cbo.currentIndex() == 0:
            self.previous_btn.setEnabled(False)
        else:
            self.error_grids_cbo.setCurrentIndex((self.error_grids_cbo.currentIndex() - 1))
            self.previous_btn.setEnabled(True)
            self.next_btn.setEnabled(True)
            self.currentCell = next(self.grid.getFeatures(QgsFeatureRequest(int(self.error_grids_cbo.currentText()))))
            x, y = self.currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom_show_n_cells(self.iface, int(self.cell_size), 30)
            self.lyrs.show_feat_rubber(self.grid.id(), int(self.error_grids_cbo.currentText()), QColor(Qt.yellow))

    def show_next(self):
        """
        Function to show the next grid element
        """
        if self.error_grids_cbo.currentIndex() == self.error_grids_cbo.count() - 1:
            self.next_btn.setEnabled(False)
        else:
            self.error_grids_cbo.setCurrentIndex((self.error_grids_cbo.currentIndex() + 1))
            self.previous_btn.setEnabled(True)
            self.next_btn.setEnabled(True)
            self.currentCell = next(self.grid.getFeatures(QgsFeatureRequest(int(self.error_grids_cbo.currentText()))))
            x, y = self.currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom_show_n_cells(self.iface, int(self.cell_size), 30)
            self.lyrs.show_feat_rubber(self.grid.id(), int(self.error_grids_cbo.currentText()), QColor(Qt.yellow))

    def show_grid(self):
        """
        Function to show the current grid element
        """
        if self.error_grids_cbo.currentIndex() == 0:
            self.previous_btn.setEnabled(False)
            self.next_btn.setEnabled(True)
        elif self.error_grids_cbo.currentIndex() == self.error_grids_cbo.count() - 1:
            self.next_btn.setEnabled(False)
            self.previous_btn.setEnabled(True)
        else:
            self.previous_btn.setEnabled(True)
            self.next_btn.setEnabled(True)

        self.currentCell = next(self.grid.getFeatures(QgsFeatureRequest(int(self.error_grids_cbo.currentText()))))
        x, y = self.currentCell.geometry().centroid().asPoint()
        center_canvas(self.iface, x, y)
        zoom_show_n_cells(self.iface, int(self.cell_size), 30)
        self.lyrs.show_feat_rubber(self.grid.id(), int(self.error_grids_cbo.currentText()), QColor(Qt.yellow))


