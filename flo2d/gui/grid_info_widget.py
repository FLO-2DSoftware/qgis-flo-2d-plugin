# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright Â© 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.core import QgsFeatureRequest
from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtGui import QColor, QIntValidator, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QApplication

from ..flo2d_tools.grid_tools import number_of_elements, render_grid_elevations2
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..utils import (
    is_number,
    m_fdata,
    second_smallest,
    set_min_max_elevs,
)
from .ui_utils import center_canvas, load_ui, set_icon, zoom

uiDialog, qtBaseClass = load_ui("grid_info_widget")


class GridInfoWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.uc = UserCommunication(iface, "FLO-2D")
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
        self.cell_Edit = None
        self.n_cells = 0
        self.d1 = []
        self.d2 = []

        self.control_lyr = self.lyrs.data["cont"]["qlyr"]

        self.setup_connection()
        validator = QIntValidator()
        self.idEdit.setValidator(validator)

        self.render_elevations_chbox.clicked.connect(self.render_elevations)
        self.find_cell_btn.clicked.connect(self.find_cell)
        set_icon(self.find_cell_btn, "eye-svgrepo-com.svg")

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def setSizeHint(self, width, height):
        self._sizehint = QSize(width, height)

    def sizeHint(self):
        if self._sizehint is not None:
            return self._sizehint
        return super(GridInfoWidget, self).sizeHint()

    def set_info_layer(self, lyr):
        self.grid = lyr
        self.n_cells = number_of_elements(self.gutils, self.grid)
        self.n_cells_lbl.setText("Number of cells: " + "{:,}".format(self.n_cells) + "   ")

    def update_fields(self, fid):
        try:
            if not fid == -1:
                feat = next(self.grid.getFeatures(QgsFeatureRequest(fid)))
                # cell_size = sqrt(feat.geometry().area())
                gid = str(fid)
                if feat["elevation"]:
                    elev = "{:10.4f}".format(feat["elevation"]).strip()
                    elev = elev if float(elev) > -9999 else "-9999"
                    n = feat["n_value"]
                    if not n:
                        n = "{} (default)".format(self.mann_default)
                    else:
                        pass
                    self.idEdit.setText(gid)
                    self.elevEdit.setText(elev)
                    self.mannEdit.setText(str(n))
                    self.cellEdit.setText(str(self.gutils.get_cont_par("CELLSIZE")))
                    self.grid = self.lyrs.data["grid"]["qlyr"]
                    self.n_cells = number_of_elements(self.gutils, self.grid)
                    self.n_cells_lbl.setText("Number of cells: " + "{:,}".format(self.n_cells) + "   ")
                    if self.plot_ckbox.isChecked():
                        self.plot_grid_rainfall(feat)
                    self.lyrs.show_feat_rubber(self.grid.id(), int(gid), QColor(Qt.yellow))
                else:
                    self.idEdit.setText("")
                    self.elevEdit.setText("")
                    self.mannEdit.setText("")
                    self.cellEdit.setText("")
                    self.n_cells_lbl.setText("Number of cells:       ")
                    self.lyrs.clear_rubber()
            else:
                self.idEdit.setText("")
                self.elevEdit.setText("")
                self.mannEdit.setText("")
                self.cellEdit.setText("")
                self.n_cells_lbl.setText("Number of cells:       ")
                self.lyrs.clear_rubber()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 290718.1934: error while displaying elevation of cell "
                + str(fid)
                + "\n____________________________________________",
                e,
            )

    def check_render_elevations(self):
        qry = """SELECT value FROM cont WHERE name = 'IBACKUP';"""
        row = self.gutils.execute(qry).fetchone()
        if is_number(row[0]):
            if row[0] == "0":
                self.render_elevations_chbox.setChecked(False)
            else:
                self.render_elevations_chbox.setChecked(True)

    def render_elevations(self):
        try:
            if self.gutils.is_table_empty("user_model_boundary"):
                self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
                return
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                return
            elevs = [x[0] for x in self.gutils.execute("SELECT elevation FROM grid").fetchall()]
            elevs = [x if x is not None else -9999 for x in elevs]
            if elevs:
                mini = min(elevs)
                mini2 = second_smallest(elevs)
                maxi = max(elevs)
                render_grid_elevations2(
                    self.grid,
                    self.render_elevations_chbox.isChecked(),
                    mini,
                    mini2,
                    maxi,
                )
                set_min_max_elevs(mini, maxi)
                self.lyrs.lyrs_to_repaint = [self.grid]
                self.lyrs.repaint_layers()
        except Exception as e:
            self.uc.show_error("ERROR 110721.0545: render of elevations failed!.\n", e)
            # self.uc.bar_error("ERROR 100721.1759: is the grid defined?")
            self.lyrs.clear_rubber()

    def plot_grid_rainfall(self, feat):
        si = "inches" if self.gutils.get_cont_par("METRIC") == "0" else "mm"
        qry = "SELECT time_interval, iraindum FROM raincell_data WHERE rrgrid=? ORDER BY time_interval;"
        fid = feat["fid"]
        rainfall = self.gutils.execute(qry, (fid,))
        self.create_plot()
        self.tview.setModel(self.data_model)
        self.data_model.clear()
        self.data_model.setHorizontalHeaderLabels(["Time", "Cumulative rainfall"])
        self.d1, self.d2 = [[], []]
        for row in rainfall:
            items = [QStandardItem("{:.4f}".format(x)) if x is not None else QStandardItem("") for x in row]
            self.data_model.appendRow(items)
            self.d1.append(row[0] if not row[0] is None else float("NaN"))
            self.d2.append(row[1] if not row[1] is None else float("NaN"))
        rc = self.data_model.rowCount()
        if rc < 500:
            for row in range(rc, 500 + 1):
                items = [QStandardItem(x) for x in ("",) * 2]
                self.data_model.appendRow(items)
        self.tview.horizontalHeader().setStretchLastSection(True)
        for col in range(2):
            self.tview.setColumnWidth(col, 100)
        for i in range(self.data_model.rowCount()):
            self.tview.setRowHeight(i, 20)
        self.plot.plot.setTitle("GRID FID: {}".format(fid))
        self.plot.plot.setLabel("bottom", text="Time (minutes)")
        self.plot.plot.setLabel("left", text="Rainfall ({})".format(si))
        self.update_plot()

    def create_plot(self):
        self.plot.clear()
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)
        self.plot.plot.addLegend()

        self.plot_item_name = "Grid realtime rainfall"
        self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))

    def update_plot(self):
        if not self.plot_item_name:
            return
        self.d1, self.d2 = [[], []]
        for i in range(self.data_model.rowCount()):
            self.d1.append(m_fdata(self.data_model, i, 0))
            self.d2.append(m_fdata(self.data_model, i, 1))
        self.plot.update_item(self.plot_item_name, [self.d1, self.d2])

    def find_cell(self, cell=None):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                return
            grid = self.lyrs.data["grid"]["qlyr"]
            if grid is not None:
                if grid:
                    if not cell:
                        cell = self.idEdit.text()
                    else:
                        cell = cell
                        self.idEdit.setText(str(cell))
                    if cell != "":
                        cell = int(cell)
                        n_cells = number_of_elements(self.gutils, grid)
                        if n_cells > 0 and cell > 0:
                            if cell <= n_cells:
                                self.lyrs.show_feat_rubber(grid.id(), cell, QColor(Qt.yellow))
                                feat = next(grid.getFeatures(QgsFeatureRequest(cell)))
                                x, y = feat.geometry().centroid().asPoint()
                                center_canvas(self.iface, x, y)
                                zoom(self.iface, 0.4)
                                self.mannEdit.setText(str(feat["n_value"]))
                                self.elevEdit.setText(str(feat["elevation"]).strip())
                                self.cellEdit.setText(str(self.gutils.get_cont_par("CELLSIZE")))
                                self.n_cells = n_cells
                                self.n_cells_lbl.setText("Number of cells: " + "{:,}".format(n_cells) + "   ")
                            else:
                                self.uc.bar_warn("Cell " + str(cell) + " not found.")
                                self.lyrs.clear_rubber()
                        else:
                            self.uc.bar_warn("Cell " + str(cell) + " not found.")
                            self.lyrs.clear_rubber()
                    else:
                        self.uc.bar_warn("Cell " + str(cell) + " not found.")
                        self.lyrs.clear_rubber()

        except Exception:
            self.uc.bar_warn("Cell is not valid.")
            self.lyrs.clear_rubber()
            pass

        # except ValueError:
        #     self.uc.bar_warn("Cell " + str(cell) + " is not valid.")
        #     self.lyrs.clear_rubber()
        #     pass
        finally:
            QApplication.restoreOverrideCursor()
