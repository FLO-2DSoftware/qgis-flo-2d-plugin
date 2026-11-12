# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.core import QgsRectangle, QgsFeatureRequest
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QComboBox, QTableWidgetItem

from ..flo2d_tools.grid_tools import find_this_cell
from ..flo2d_tools.confluence_tools import ConfluenceManager
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from .ui_utils import load_ui
from ..utils import qt_item_role

uiDialog, qtBaseClass = load_ui("tributaries")


class TributariesDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.lyrs = lyrs
        self.rubber_bands = []
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None
        self.confluences_tblw.itemSelectionChanged.connect(self.highlight_confluence)
        self.reset_confluences_btn.clicked.connect(self.reset_confluences)
        self.setup_connection()
        self.manager = ConfluenceManager(self.gutils, self.lyrs)
        candidates = self.manager.assess_confluences()
        self.manager.reconcile_confluences()
        self.confluences = {a: [a] + mains for a, mains in candidates.items()}
        if self.manager.issues:
            for issue in self.manager.issues:
                self.uc.log_info("Channel confluence: " + issue)
            self.uc.bar_warn("Channel connections need review. See the FLO-2D log for grid IDs and details.")
        self.populate_table()
        self.find_chan_confluences()
        self.highlight_all_tributaries()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_table(self):
        i = -1
        for row_position, confluence in enumerate(self.confluences.values()):
            if len(confluence) > 1:
                i += 1
                self.confluences_tblw.insertRow(i)
                item = QTableWidgetItem()
                item.setData(qt_item_role("DisplayRole"), confluence[0])
                self.confluences_tblw.setItem(i, 0, item)
                combo = QComboBox()
                combo.setStyleSheet("QComboBox { border: 1px gray; } QFrame { border: 3px solid blue; }")
                combo.addItem("")
                for t in confluence[1:]:
                    combo.addItem(str(t))
                combo.currentIndexChanged.connect(lambda: self.highlight_confluence())
                combo.view().entered.connect(
                    lambda index, row=i: self.preview_main_cell(row, index)
                )
                self.confluences_tblw.setCellWidget(i, 1, combo)

    def find_chan_confluences(self):
        selected = self.manager.selected_connections()
        for row in range(self.confluences_tblw.rowCount()):
            tributary = int(self.confluences_tblw.item(row, 0).text())
            mains = selected.get(tributary, [])
            widget = self.confluences_tblw.cellWidget(row, 1)
            widget.blockSignals(True)
            if len(mains) == 1:
                widget.setCurrentIndex(widget.findText(str(mains[0])))
            elif len(mains) > 1:
                widget.insertItem(0, "Choose main cell...")
                widget.setCurrentIndex(0)
            widget.blockSignals(False)

    def highlight_confluence(self):
        row = self.confluences_tblw.currentRow()
        if row >= 0:
            self.confluences_tblw_cell_update(row)

    def confluences_tblw_cell_update(self, row):
        self.clear_confluences_rubber()
        self.lyrs.clear_rubber()
        tributary_cell = self.confluences_tblw.item(row, 0).text()
        find_this_cell(
            self.iface,
            self.lyrs,
            self.uc,
            self.gutils,
            tributary_cell,
            Qt.yellow,
            zoom_in=False,
            clear_previous=False,
        )
        # Zoom to a 10 x 10 grid-cell area around the tributary.
        grid_layer = self.lyrs.data["grid"]["qlyr"]
        cell_size = float(self.gutils.get_cont_par("CELLSIZE"))

        feature = next(
            grid_layer.getFeatures(
                QgsFeatureRequest().setFilterFid(int(tributary_cell))
            ),
            None
        )

        if feature is not None:
            center = feature.geometry().boundingBox().center()
            half_width = 5 * cell_size

            extent = QgsRectangle(
                center.x() - half_width,
                center.y() - half_width,
                center.x() + half_width,
                center.y() + half_width
            )

            self.canvas.setExtent(extent)
            self.canvas.refresh()
        self.rubber_bands.append(self.lyrs.rb)

        current_widget = self.confluences_tblw.cellWidget(row, 1)
        if current_widget:
            main_cell = current_widget.currentText()
            if main_cell != "":
                find_this_cell(
                    self.iface,
                    self.lyrs,
                    self.uc,
                    self.gutils,
                    main_cell,
                    Qt.blue,
                    zoom_in=False,
                    clear_previous=False,
                )
                self.rubber_bands.append(self.lyrs.rb)

    def highlight_all_tributaries(self):
        self.lyrs.clear_rubber()
        for i in range(self.confluences_tblw.rowCount()):
            tributary_cell = self.confluences_tblw.item(i, 0).text()
            find_this_cell(
                self.iface,
                self.lyrs,
                self.uc,
                self.gutils,
                tributary_cell,
                Qt.cyan,
                zoom_in=False,
                clear_previous=False,
            )
            self.rubber_bands.append(self.lyrs.rb)

    def reset_confluences(self):
        self.confluences_tblw.setRowCount(0)
        self.populate_table()

    def clear_confluences_rubber(self):
        for rb in self.rubber_bands:
            try:
                if rb.scene() is not None:
                    self.canvas.scene().removeItem(rb)
            except RuntimeError:
                pass
        self.rubber_bands = []

    def save(self):
        selections = {}
        for row in range(self.confluences_tblw.rowCount()):
            tributary = int(self.confluences_tblw.item(row, 0).text())
            main = self.confluences_tblw.cellWidget(row, 1).currentText()
            if main == "Choose main cell...":
                raise ValueError(f"Endpoint {tributary}: choose a main cell or the blank option before saving.")
            selections[tributary] = int(main) if main else None
        self.manager.save(selections)

    def preview_main_cell(self, row, index):
        """Preview a main-channel cell while hovering over the dropdown."""
        if not index.isValid():
            return

        main_cell = index.data()
        if not main_cell or not str(main_cell).isdigit():
            return

        # Temporarily redraw the tributary and hovered main cell.
        self.clear_confluences_rubber()
        self.lyrs.clear_rubber()

        tributary_cell = self.confluences_tblw.item(row, 0).text()

        find_this_cell(
            self.iface, self.lyrs, self.uc, self.gutils,
            tributary_cell, Qt.yellow,
            zoom_in=False, clear_previous=False
        )
        self.rubber_bands.append(self.lyrs.rb)

        find_this_cell(
            self.iface, self.lyrs, self.uc, self.gutils,
            str(main_cell), Qt.blue,
            zoom_in=False, clear_previous=False
        )
        self.rubber_bands.append(self.lyrs.rb)