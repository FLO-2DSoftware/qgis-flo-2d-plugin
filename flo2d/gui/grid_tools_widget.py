# -*- coding: utf-8 -*-
import math
# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import time
import traceback

from ..misc.project_review_utils import SCENARIO_COLOURS, SCENARIO_STYLES, timdep_dataframe_from_hdf5_scenarios

try:
    import h5py
except ImportError:
    pass

import numpy as np
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices, QColor
from PyQt5.QtWidgets import QProgressDialog
from qgis._core import QgsFeatureRequest, QgsProject, QgsMeshLayer, QgsMeshDatasetIndex
from qgis.core import NULL, Qgis, QgsFeature, QgsGeometry, QgsMessageLog, QgsWkbTypes
from qgis.PyQt.QtCore import QSettings, Qt, QThread
from qgis.PyQt.QtWidgets import (
    QApplication,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
)

from .dlg_sampling_rc import SamplingRCDialog
from .table_editor_widget import StandardItemModel, StandardItem
from ..flo2d_tools.grid_tools import (
    ZonalStatistics,
    ZonalStatisticsOther,
    add_col_and_row_fields,
    assign_col_row_indexes_to_grid,
    evaluate_arfwrf,
    evaluate_roughness,
    evaluate_spatial_froude,
    evaluate_spatial_gutter,
    evaluate_spatial_noexchange,
    evaluate_spatial_shallow,
    evaluate_spatial_tolerance,
    number_of_elements,
    poly2grid,
    poly2poly_geos,
    render_grid_elevations2,
    square_grid,
    grid_compas_neighbors,
)
from ..geopackage_utils import GeoPackageUtils
from ..gui.dlg_arf_wrf import EvaluateReductionFactorsDialog
from ..gui.dlg_create_grid import CreateGridDialog
from ..gui.dlg_grid_elev import GridCorrectionDialog
from ..gui.dlg_sampling_elev import SamplingElevDialog
from ..gui.dlg_sampling_mann import SamplingManningDialog
from ..gui.dlg_sampling_point_elev import SamplingPointElevDialog
from ..gui.dlg_sampling_raster_roughness import (
    SamplingRoughnessDialog,
)  # update this after elevation test is ok
from ..gui.dlg_sampling_tailings import SamplingTailingsDialog2
from ..gui.dlg_sampling_variable_into_grid import SamplingOtherVariableDialog
from ..gui.dlg_sampling_xyz import SamplingXYZDialog
from ..user_communication import UserCommunication
from ..utils import second_smallest, set_min_max_elevs, time_taken
from .ui_utils import load_ui, set_icon

uiDialog, qtBaseClass = load_ui("grid_tools_widget")


class GridToolsWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs, plot, table):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None
        self.globlyr = None

        self.system_units = {
            "CMS": ["m", "mps", "cms"],
            "CFS": ["ft", "fps", "cfs"]
             }

        self.plot = plot
        self.plot_item_name = None
        self.table = table
        self.tview = table.tview
        self.data_model = StandardItemModel()
        self.tview.setModel(self.data_model)

        set_icon(self.create_grid_btn, "create_grid.svg")
        set_icon(self.raster_elevation_btn, "sample_elev.svg")
        set_icon(self.point_elevation_btn, "sample_elev_point.svg")
        set_icon(self.xyz_elevation_btn, "sample_elev_xyz.svg")
        set_icon(self.polygon_elevation_btn, "sample_elev_polygon.svg")
        set_icon(self.roughness_btn, "sample_manning.svg")
        set_icon(self.raster_roughness_btn, "sample_raster_roughness.svg")
        set_icon(self.arfwrf_btn, "eval_arfwrf.svg")
        set_icon(self.froude_btn, "sample_froude.svg")
        set_icon(self.tolerance_btn, "sample_tolerance.svg")
        set_icon(self.shallow_n_btn, "sample_shallow_n.svg")
        set_icon(self.gutter_btn, "sample_gutter.svg")
        set_icon(self.noexchange_btn, "sample_noexchange.svg")
        set_icon(self.other_variable_btn, "sample_grid_variable.svg")
        # set_icon(self.tailings_btn, "sample_tailings.svg")

        self.create_grid_btn.clicked.connect(self.create_grid)
        self.raster_elevation_btn.clicked.connect(self.raster_elevation)
        self.raster_roughness_btn.clicked.connect(self.raster_roughness)
        self.point_elevation_btn.clicked.connect(self.point_elevation)
        self.xyz_elevation_btn.clicked.connect(self.xyz_elevation)
        self.polygon_elevation_btn.clicked.connect(self.correct_elevation)
        # self.rc_elevation_btn.clicked.connect(self.rc_elevation)
        self.roughness_btn.clicked.connect(self.get_roughness)
        self.arfwrf_btn.clicked.connect(self.eval_arfwrf)
        self.froude_btn.clicked.connect(self.eval_froude)
        self.tolerance_btn.clicked.connect(self.eval_tolerance)
        self.shallow_n_btn.clicked.connect(self.eval_shallow_n)
        self.gutter_btn.clicked.connect(self.eval_gutter)
        self.noexchange_btn.clicked.connect(self.eval_noexchange)
        self.steep_slopen_btn.clicked.connect(self.eval_steep_slopen)
        self.lid_volume_btn.clicked.connect(self.eval_lid_volume)
        self.other_variable_btn.clicked.connect(self.other_variable)
        # self.tailings_btn.clicked.connect(self.get_tailings)
        self.help_btn.clicked.connect(self.show_grid_widget_help)

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def get_cell_size(self):
        """
        Get cell size from:
            - Computational Domain attr table (if defined, will be written to cont table)
            - cont table
            - ask user
        """
        bl = self.lyrs.data["user_model_boundary"]["qlyr"]
        bfeat = next(bl.getFeatures())
        if bfeat["cell_size"]:
            cs = int(bfeat["cell_size"])
            if cs <= 0:
                self.uc.show_warn(
                    "WARNING 060319.1706: Cell size must be positive. Change the feature attribute value in Computational Domain layer."
                )
                self.uc.log_info(
                    "WARNING 060319.1706: Cell size must be positive. Change the feature attribute value in Computational Domain layer."
                )
                return None
            self.gutils.set_cont_par("CELLSIZE", cs)
        else:
            cs = self.gutils.get_cont_par("CELLSIZE")
            cs = None if cs == "" else cs
        if cs:
            if cs <= 0:
                self.uc.show_warn(
                    "WARNING 060319.1707: Cell size must be positive. Change the feature attribute value in Computational Domain layer or default cell size in the project settings."
                )
                self.uc.log_info(
                    "WARNING 060319.1707: Cell size must be positive. Change the feature attribute value in Computational Domain layer or default cell size in the project settings."
                )
                return None
            return cs
        else:
            r, ok = QInputDialog.getInt(
                None,
                "Grid Cell Size",
                "Enter grid element cell size",
                value=100,
                min=0,
                max=99999,
            )
            if ok:
                cs = r
                self.gutils.set_cont_par("CELLSIZE", cs)
            else:
                return None

    def create_grid(self):
        create_grid_dlg = CreateGridDialog(self.lyrs)
        ok = create_grid_dlg.exec_()
        if not ok:
            return
        try:
            if not self.lyrs.save_edits_and_proceed("Computational Domain"):
                return
            if create_grid_dlg.use_external_layer():
                (
                    external_layer,
                    cell_size_field,
                    raster_file,
                ) = create_grid_dlg.external_layer_parameters()
                if not self.import_comp_domain(external_layer, cell_size_field):
                    return

            if self.gutils.count("user_model_boundary") > 1:
                warn = "WARNING 060319.1708: There are multiple features in Computational Domain layer.\n"
            if self.gutils.is_table_empty("user_model_boundary"):
                self.uc.bar_warn("There is no Computational Domain! Please digitize it before running tool.")
                self.uc.log_info("There is no Computational Domain! Please digitize it before running tool.")
                return
            if self.gutils.count("user_model_boundary") > 1:
                warn = "WARNING 060319.1708: There are multiple features created on Computational Domain layer.\n"
                warn += "Only ONE will be used with the lowest fid (first created)."
                self.uc.show_warn(warn)
                self.uc.log_info(warn)
            if not self.gutils.is_table_empty("grid"):
                if not self.uc.question("There is a grid already saved in the database. Overwrite it?"):
                    return
            if not self.get_cell_size():
                return

            QApplication.setOverrideCursor(Qt.WaitCursor)
            ini_time = time.time()
            boundary = self.lyrs.data["user_model_boundary"]["qlyr"]

            upper_left_coords_override = None

            if create_grid_dlg.use_external_layer() and raster_file:
                # compute upper left coordinate aligning it with source raster pixel
                feat = next(boundary.getFeatures())
                geom = feat.geometry()
                bbox = geom.boundingBox()
                xmin = bbox.xMinimum()
                ymax = bbox.yMaximum()
                from ..misc.gdal_utils import GDALRasterLayer

                gdal_layer = GDALRasterLayer(raster_file)
                # get pixel corresponding to xmin, ymax
                row, col = gdal_layer.index(xmin, ymax)
                # get coordinate of upper left corner of pixel
                xmin_new, ymax_new = gdal_layer.xy(row, col, offset="ul")
                upper_left_coords_override = (xmin_new, ymax_new)

            grid_lyr = self.lyrs.data["grid"]["qlyr"]
            field_index = grid_lyr.fields().indexFromName("col")
            if field_index == -1:
                QApplication.restoreOverrideCursor()

                add_new_colums = self.uc.customized_question(
                    "FLO-2D",
                    "WARNING 290521.0500:    Old GeoPackage.\n\nGrid table doesn't have 'col' and 'row' fields!\n"
                    + "Some functionality will be unavailable.\n\n"
                    + "Would you like to add the 'col' and 'row' fields to the grid table?",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.Cancel,
                )

                if add_new_colums == QMessageBox.Cancel:
                    return

            if field_index == -1:
                if add_new_colums == QMessageBox.No:
                    square_grid(self.gutils, boundary, upper_left_coords_override)
                else:
                    if add_col_and_row_fields(grid_lyr):
                        assign_col_row_indexes_to_grid(grid_lyr, self.gutils)
                    else:
                        square_grid(self.gutils, boundary, upper_left_coords_override)
            else:
                square_grid(self.gutils, boundary, upper_left_coords_override)

            # Assign default manning value (as set in Control layer ('cont')
            default = self.gutils.get_cont_par("MANNING")
            self.gutils.execute("UPDATE grid SET n_value=?;", (default,))

            n_cells = number_of_elements(self.gutils, grid_lyr)

            progDialog = QProgressDialog("Checking grid elements. Please wait...", None, 0, n_cells)
            progDialog.setModal(True)
            progDialog.setValue(0)
            progDialog.show()
            QApplication.processEvents()
            i = 0

            dangling = False
            for idx, row in enumerate(grid_compas_neighbors(self.gutils), start=1):
                n = row[0]
                e = row[1]
                s = row[2]
                w = row[3]
                ne = row[4]
                se = row[5]
                sw = row[6]
                nw = row[7]
                cardinal_directions = sum(1 for var in [n, e, s, w] if var == 0)
                ordinal_directions = sum(1 for var in [ne, se, sw, nw] if var == 0)
                # Check if at least 3 directions are zero -> dangling grid element
                if cardinal_directions >= 3 or (ordinal_directions >= 3 and cardinal_directions == 4):
                    dangling = True
                    delete_grid_elem_query = f"DELETE FROM grid WHERE fid = {idx};"
                    self.gutils.execute(delete_grid_elem_query)

                progDialog.setValue(i)
                i += 1

            if dangling:
                create_temp_table_query = """
                CREATE TABLE temp_table AS
                SELECT *, ROW_NUMBER() OVER () AS new_fid
                FROM grid;
                """
                self.gutils.execute(create_temp_table_query)

                # Delete data from the original table
                delete_data_query = "DELETE FROM grid;"
                self.gutils.execute(delete_data_query)

                # Copy data from the temporary table back to the original table
                copy_data_query = "INSERT INTO grid SELECT new_fid, col, row, n_value, elevation, water_elevation, " \
                                  "flow_depth, geom FROM temp_table;"
                self.gutils.execute(copy_data_query)

                # Drop the temporary table
                drop_temp_table_query = "DROP TABLE temp_table;"
                self.gutils.execute(drop_temp_table_query)

            # Update grid_lyr:
            grid_lyr = self.lyrs.data["grid"]["qlyr"]
            self.lyrs.update_layer_extents(grid_lyr)
            if grid_lyr:
                grid_lyr.triggerRepaint()
            self.uc.clear_bar_messages()

            n_cells = number_of_elements(self.gutils, grid_lyr)
            cell_size = self.gutils.get_cont_par("CELLSIZE")
            units = " mts" if self.gutils.get_cont_par("METRIC") == "1" else " ft"

            fin_time = time.time()
            duration = time_taken(ini_time, fin_time)

            grid_summary = (
                "Grid created.\n\nCell size:  "
                + cell_size
                + units
                + "\n\nTotal number of cells:  "
                + "{:,}".format(n_cells)
                + "\n\n(Elapsed time: "
                + duration
                + ")"
            )
            QApplication.restoreOverrideCursor()
            self.uc.log_info(grid_summary)
            self.uc.show_info(grid_summary)

        except Exception as e:
            msg = "Creating grid aborted! Please check Computational Domain layer, cell size, and optional parameters."
            self.uc.log_info(msg)
            self.uc.bar_error(msg)
        finally:
            QApplication.restoreOverrideCursor()

    def raster_elevation(self):
        if self.gutils.is_table_empty("user_model_boundary"):
            self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
            self.uc.log_info("There is no computational domain! Please digitize it before running tool.")
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            self.uc.log_info("There is no grid! Please create it before running tool.")
            return
        cell_size = self.get_cell_size()
        dlg = SamplingElevDialog(self.con, self.iface, self.lyrs, cell_size)
        ok = dlg.exec_()
        if ok:
            pass
        else:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            res = dlg.probe_elevation()
            QApplication.restoreOverrideCursor()
            if res:
                dlg.show_probing_result_info()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn("WARNING 060319.1710: Probing grid elevation failed! Please check your raster layer.")

    def rc_elevation(self):
        """
        Function to calculate the Surface Water Rating Tables from a point layer
        """
        if self.gutils.is_table_empty("user_model_boundary"):
            self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
            self.uc.log_info("There is no computational domain! Please digitize it before running tool.")
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            self.uc.log_info("There is no grid! Please create it before running tool.")
            return
        cell_size = self.get_cell_size()
        dlg = SamplingRCDialog(self.con, self.iface, self.lyrs, cell_size)
        ok = dlg.exec_()
        if ok:
            pass
        else:
            return
        # try:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        # res = dlg.probe_elevation()
        dlg.create_elev_rc()
        QApplication.restoreOverrideCursor()
        # if res:
        #     dlg.show_probing_result_info()
        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.log_info(traceback.format_exc())
        #     self.uc.show_warn("ERROR")

    def raster_roughness(self):
        if self.gutils.is_table_empty("user_model_boundary"):
            self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
            self.uc.log_info("There is no computational domain! Please digitize it before running tool.")
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            self.uc.log_info("There is no grid! Please create it before running tool.")
            return
        cell_size = self.get_cell_size()
        dlg = SamplingRoughnessDialog(self.con, self.iface, self.lyrs, cell_size)
        ok = dlg.exec_()
        if ok:
            pass
        else:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            res = dlg.probe_roughness()
            QApplication.restoreOverrideCursor()
            if res:
                dlg.show_probing_result_info()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn("WARNING 060319.1710: Probing grid roughness failed! Please check your raster layer.")

    def point_elevation(self):
        if self.gutils.is_table_empty("user_model_boundary"):
            self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
            self.uc.log_info("There is no computational domain! Please digitize it before running tool.")
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            self.uc.log_info("There is no grid! Please create it before running tool.")
            return
        cell_size = self.get_cell_size()
        dlg = SamplingPointElevDialog(self.con, self.iface, self.lyrs, cell_size)
        ok = dlg.exec_()

    def xyz_elevation(self):
        try:
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn(
                    "WARNING 060319.1711: Schematic grid layer 'grid' is empty! Please create it before running tool."
                )
                self.uc.log_info(
                    "WARNING 060319.1711: Schematic grid layer 'grid' is empty! Please create it before running tool."
                )
                return

            grid = self.lyrs.data["grid"]["qlyr"]
            # grid_extent = grid.extent()

            dlg = SamplingXYZDialog(self.con, self.iface, self.lyrs)
            ok = dlg.exec_()
            if ok:
                if dlg.points_layer_grp.isChecked():
                    # Interpolate from points layer:
                    points_lyr = dlg.current_lyr
                    if not points_lyr:
                        self.uc.show_info("Select a points layer!")
                    else:
                        zfield = dlg.fields_cbo.currentText()
                        calc_type = dlg.calc_cbo.currentText()
                        search_distance = dlg.search_spin_box.value()

                        try:
                            ini_time = time.time()
                            QApplication.setOverrideCursor(Qt.WaitCursor)
                            # grid_lyr = self.lyrs.data["grid"]["qlyr"]
                            zs = ZonalStatistics(
                                self.gutils,
                                grid,
                                points_lyr,
                                zfield,
                                calc_type,
                                search_distance,
                            )
                            points_elevation = zs.points_elevation()
                            zs.set_elevation(points_elevation)
                            cmd, out = zs.rasterize_grid()
                            self.uc.log_info(cmd)
                            self.uc.log_info(out)
                            cmd, out = zs.fill_nodata()
                            self.uc.log_info(cmd)
                            self.uc.log_info(out)
                            null_elevation = zs.null_elevation()
                            zs.set_elevation(null_elevation)
                            zs.remove_rasters()

                            self.gutils.execute("UPDATE grid SET elevation = -9999 WHERE elevation IS NULL;")
                            elevs = [x[0] for x in self.gutils.execute("SELECT elevation FROM grid").fetchall()]
                            # elevs = [x if x is not None else -9999 for x in elevs]
                            if elevs:
                                mini = min(elevs)
                                mini2 = second_smallest(elevs)
                                maxi = max(elevs)
                                render_grid_elevations2(grid, True, mini, mini2, maxi)
                                set_min_max_elevs(mini, maxi)
                                self.lyrs.lyrs_to_repaint = [grid]
                                self.lyrs.repaint_layers()

                            QApplication.restoreOverrideCursor()

                            fin_time = time.time()
                            duration = time_taken(ini_time, fin_time)
                            self.uc.show_info(
                                "Calculating elevation finished." + "\n\n(Elapsed time: " + duration + ")"
                            )

                        except Exception as e:
                            QApplication.restoreOverrideCursor()
                            self.uc.log_info(traceback.format_exc())
                            self.uc.show_error(
                                "ERROR 060319.1712: Calculating grid elevation aborted! Please check elevation points layer.\n",
                                e,
                            )

                else:
                    # Interpolate from LIDAR:
                    # grid_lyr = self.lyrs.data["grid"]["qlyr"]
                    field_index = grid.fields().indexFromName("col")
                    if field_index == -1:
                        if self.gutils.is_table_empty("user_model_boundary"):
                            QApplication.restoreOverrideCursor()
                            self.uc.show_warn(
                                "WARNING 310521.0524: Old GeoPackage.\n\nGrid table doesn't have 'col' and 'row' fields!\n\n"
                                + "and there is no Computational Domain to create them!"
                            )
                            self.uc.log_info(
                                "WARNING 310521.0524: Old GeoPackage.\n\nGrid table doesn't have 'col' and 'row' fields!\n\n"
                                + "and there is no Computational Domain to create them!"
                            )
                        else:
                            proceed = self.uc.question(
                                "WARNING 290521.0602: Old GeoPackage.\n\nGrid table doesn't have 'col' and 'row' fields!\n\n"
                                + "Would you like to add the 'col' and 'row' fields to the grid table?"
                            )
                            if proceed:
                                if add_col_and_row_fields(grid):
                                    assign_col_row_indexes_to_grid(self.lyrs.data["grid"]["qlyr"], self.gutils)
                                    dlg.interpolate_from_lidar()
                    else:
                        cell = self.gutils.execute("SELECT col FROM grid WHERE fid = 1").fetchone()
                        if cell[0] != NULL:
                            dlg.interpolate_from_lidar()
                        else:
                            QApplication.setOverrideCursor(Qt.ArrowCursor)
                            proceed = self.uc.question(
                                "Grid layer's fields 'col' and 'row' have NULL values!\n\nWould you like to assign them?"
                            )
                            QApplication.restoreOverrideCursor()
                            if proceed:
                                QApplication.setOverrideCursor(Qt.WaitCursor)
                                assign_col_row_indexes_to_grid(self.lyrs.data["grid"]["qlyr"], self.gutils)
                                QApplication.restoreOverrideCursor()
                                dlg.interpolate_from_lidar()
                            else:
                                return

                QApplication.restoreOverrideCursor()
            else:
                QApplication.restoreOverrideCursor()
                return

        except Exception:
            QApplication.restoreOverrideCursor()
            self.uc.bar_error("ERROR 100721.1952: is the grid defined?")
            self.uc.log_info("ERROR 100721.1952: is the grid defined?")

    def interpolate_from_lidar_THREAD_original(self, layer):
        # create a new interpolate_from_LIDAR_thread instance
        LIDAR_walker_instance = LIDARWorker(layer)

        # configure the QgsMessageBar
        messageBar = self.iface.messageBar().createMessage(
            "Interpolating from LIDAR files...",
        )
        self.advanceBar = QProgressBar()
        self.advanceBar.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.cancelButton = QPushButton()
        self.cancelButton.setText("Cancel")
        self.cancelButton.clicked.connect(LIDAR_walker_instance.THREAD_kill)
        messageBar.layout().addWidget(self.advanceBar)
        messageBar.layout().addWidget(self.cancelButton)
        self.iface.messageBar().pushWidget(messageBar, Qgis.Info)
        self.messageBar = messageBar

        statBar = self.iface.mainWindow().statusBar()
        self.statusLabel = QLabel()
        self.statusLabel.setText("Interpolating from LIDAR files...")
        statBar.addWidget(self.statusLabel)
        statBar.addWidget(self.advanceBar)
        statBar.addWidget(self.cancelButton)
        self.iface.mainWindow().statusBar().addWidget(statBar)
        self.statBar = statBar

        # start the worker in a new thread
        thread = QThread(self)
        LIDAR_walker_instance.moveToThread(thread)
        LIDAR_walker_instance.THREAD_finished.connect(self.workerFinished)
        LIDAR_walker_instance.THREAD_error.connect(self.workerError)
        LIDAR_walker_instance.THREAD_progrss.connect(self.advanceBar.setValue)
        thread.started.connect(LIDAR_walker_instance.run)
        thread.start()
        self.thread = thread
        self.LIDAR_walker_instance = LIDAR_walker_instance

    def interpolate_from_lidar_THREAD(self, lidar_files, lyrs):
        # create a new interpolate_from_LIDAR_thread instance
        LIDAR_walker_instance = LIDARWorker(self.iface, lidar_files, lyrs)

        # configure the QgsMessageBar
        messageBar = self.iface.messageBar().createMessage(
            "Interpolating from LIDAR files...",
        )
        self.advanceBar = QProgressBar()
        self.advanceBar.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.cancelButton = QPushButton()
        self.cancelButton.setText("Cancel")
        self.cancelButton.clicked.connect(LIDAR_walker_instance.THREAD_kill)
        messageBar.layout().addWidget(self.advanceBar)
        messageBar.layout().addWidget(self.cancelButton)
        self.iface.messageBar().pushWidget(messageBar, Qgis.Info)
        self.messageBar = messageBar

        statBar = self.iface.mainWindow().statusBar()
        self.statusLabel = QLabel()
        self.statusLabel.setText("Interpolating from LIDAR files...")
        statBar.addWidget(self.statusLabel)
        statBar.addWidget(self.advanceBar)
        statBar.addWidget(self.cancelButton)
        self.iface.mainWindow().statusBar().addWidget(statBar)
        self.statBar = statBar

        # start the worker in a new thread
        thread = QThread(self)
        LIDAR_walker_instance.moveToThread(thread)
        LIDAR_walker_instance.THREAD_finished.connect(self.workerFinished)
        LIDAR_walker_instance.THREAD_error.connect(self.workerError)
        LIDAR_walker_instance.THREAD_progrss.connect(self.advanceBar.setValue)
        thread.started.connect(LIDAR_walker_instance.run)
        thread.start()
        self.thread = thread
        self.LIDAR_walker_instance = LIDAR_walker_instance

    def workerFinished(self):
        # clean up the worker and thread
        self.LIDAR_walker_instance.deleteLater()
        self.thread.quit()
        self.thread.wait()
        self.thread.deleteLater()
        # remove widget from message bar
        self.iface.messageBar().popWidget(self.messageBar)
        self.statBar.removeWidget(self.statusLabel)
        self.statBar.removeWidget(self.advanceBar)
        self.statBar.removeWidget(self.cancelButton)

    def workerError(self, e, exception_string):
        QgsMessageLog.logMessage(
            "Worker thread raised an exception:\n".format(exception_string),
            level=Qgis.Critical,
        )

    def other_variable(self):
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            self.uc.log_info("There is no grid! Please create it before running tool.")
            return

        n_point_layers = False
        layers = self.lyrs.list_group_vlayers()
        for l in layers:
            if l.geometryType() == QgsWkbTypes.PointGeometry:
                if l.featureCount() != 0:
                    n_point_layers = True
                    break

        if not n_point_layers:
            QApplication.restoreOverrideCursor()
            self.uc.bar_warn("There are not any point layers selected (or visible)")
            self.uc.log_info("There are not any point layers selected (or visible)")
            return
        else:
            dlg = SamplingOtherVariableDialog(self.con, self.iface, self.lyrs)
            ok = dlg.exec_()
            if ok:
                pass
            else:
                return
            points_lyr = dlg.current_lyr
            zfield = dlg.points_layer_fields_cbo.currentText()
            grid_field = dlg.grid_fields_cbo.currentText()
            calc_type = dlg.calc_cbo.currentText()
            search_distance = dlg.search_spin_box.value()

            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                grid_lyr = self.lyrs.data["grid"]["qlyr"]
                zs = ZonalStatisticsOther(
                    self.gutils,
                    grid_lyr,
                    grid_field,
                    points_lyr,
                    zfield,
                    calc_type,
                    search_distance,
                )
                points_elevation = zs.points_elevation()
                zs.set_other(points_elevation)
                cmd, out = zs.rasterize_grid()
                self.uc.log_info(cmd)
                self.uc.log_info(out)
                cmd, out = zs.fill_nodata()
                self.uc.log_info(cmd)
                self.uc.log_info(out)
                null_elevation = zs.null_elevation()
                zs.set_other(null_elevation)
                zs.remove_rasters()
                QApplication.restoreOverrideCursor()
                self.uc.show_info("Sampling of grid field '" + grid_field + "' finished!")
            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.log_info(traceback.format_exc())
                self.uc.show_warn(
                    "WARNING 060319.1713: Calculating sampling of grid field '"
                    + grid_field
                    + "' aborted!\n\nPlease check grid layer or input points layer.\n\n"
                    + repr(e)
                )

    def correct_elevation(self):
        try:
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                self.uc.log_info("There is no grid! Please create it before running tool.")
                return
            lyrs = ["Elevation Points", "Elevation Polygons", "Blocked Areas"]
            for lyr in lyrs:
                if lyr is None:
                    continue
                else:
                    if not self.lyrs.save_edits_and_proceed(lyr):
                        return
            correct_dlg = GridCorrectionDialog(self.con, self.iface, self.lyrs)
            ok = correct_dlg.exec_()
            if not ok:
                return
            tab = correct_dlg.correction_tab.currentIndex()
            if tab == 0:
                if not correct_dlg.internal_methods:
                    self.uc.show_warn("Please choose at least one elevation source!")
                    self.uc.log_info("Please choose at least one elevation source!")
                    return
                method = correct_dlg.run_internal
            else:
                correct_dlg.setup_external_method()
                if correct_dlg.external_method is None:
                    self.uc.show_warn("WARNING 060319.1714: Please choose at least one elevation source!")
                    self.uc.log_info("WARNING 060319.1714: Please choose at least one elevation source!")
                    return
                method = correct_dlg.run_external

            QApplication.setOverrideCursor(Qt.WaitCursor)
            method()
            QApplication.restoreOverrideCursor()
            self.uc.show_info("Assigning grid elevation finished!")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error(
                "ERROR 060319.1607: Assigning grid elevation aborted! Please check your input layers."
                + "\n___________________________________________________",
                e,
            )

    def get_roughness(self):
        if not self.lyrs.save_edits_and_proceed("Roughness"):
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            self.uc.log_info("There is no grid! Please create it before running tool.")
            return
        mann_dlg = SamplingManningDialog(self.con, self.iface, self.lyrs)
        ok = mann_dlg.exec_()
        if ok:
            pass
        else:
            return

        if mann_dlg.allGridElemsRadio.isChecked():
            if mann_dlg.current_lyr is None:
                self.uc.show_warn("A polygons layer must be selected!")
                self.uc.log_info("A polygons layer must be selected!")
                return
            rough_lyr = mann_dlg.current_lyr
            nfield = mann_dlg.srcFieldCbo.currentText()
            if nfield == "":
                self.uc.show_warn("A roughness coefficient field must be selected!")
                self.uc.log_info("A roughness coefficient field must be selected!")
                return
            else:
                flag = True
        else:
            rough_name = "Roughness"
            rough_lyr = self.lyrs.get_layer_by_name(rough_name, group=self.lyrs.group).layer()
            nfield = "n"
            flag = False
            if self.gutils.is_table_empty("user_roughness"):
                self.uc.show_warn(
                    "WARNING 060319.1715: There are no roughness polygons! Please digitize them before running tool."
                )
                self.uc.log_info(
                    "WARNING 060319.1715: There are no roughness polygons! Please digitize them before running tool."
                )
                return
            else:
                pass
        #  Assign values:
        try:

            start_time = time.time()
            QApplication.setOverrideCursor(Qt.WaitCursor)
            grid_lyr = self.lyrs.data["grid"]["qlyr"]
            if mann_dlg.intersect_cell_rectangle_radio.isChecked():
                method = "Areas"
            else:
                method = "Centroids"
            if evaluate_roughness(self.gutils, grid_lyr, rough_lyr, nfield, method, reset=flag):
                end_time = time.time()
                QApplication.restoreOverrideCursor()
                #             debugMsg('\t{0:.3f} seconds'.format(end_time - start_time))

                QApplication.restoreOverrideCursor()
                self.uc.show_info(
                    "Assigning roughness finished!\n\n" + "\t{0:.3f} seconds".format(end_time - start_time)
                )
            else:
                pass

        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 060319.1716: Assigning roughness aborted! Please check roughness layer."
                + "\n___________________________________________________",
                e,
            )

    def get_tailings(self):
        tailings_dlg = SamplingTailingsDialog2()
        ok = tailings_dlg.exec_()
        if not ok:
            return
        try:
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid. Please, create it before sampling tailings.")
                self.uc.log_info("There is no grid. Please, create it before sampling tailings.")
                return

            QApplication.setOverrideCursor(Qt.WaitCursor)
            qry = ["""INSERT INTO tailing_cells (grid_fid, thickness) VALUES""", 2]

            if tailings_dlg.use_external_layer():
                external_layer, tailing_field = tailings_dlg.external_layer_parameters()

                grid_lyr = self.lyrs.data["grid"]["qlyr"]

                writeVals = []

                use_centroid = True  # Hardwired to use/not use centroid.

                cellSize = float(self.gutils.get_cont_par("CELLSIZE"))

                if use_centroid:
                    values2 = poly2grid(
                        cellSize,
                        grid_lyr,
                        external_layer,
                        None,
                        True,
                        False,
                        False,
                        1,
                        tailing_field,
                    )
                    for value, gid in values2:
                        if value:
                            value = "%.2f" % value
                            writeVals.append([gid, value])

                else:
                    values = poly2poly_geos(grid_lyr, external_layer, None, tailing_field)  # this returns 2 values
                    for gid, values in values:
                        if values:
                            thickness = sum(ma * float(subarea) for ma, subarea in values)
                            # thickness = thickness + (1.0 - sum(float(subarea) for ma, subarea in values)) * float(globalnValue)
                            # thickness = '{:10.3f}'.format(thickness)
                            thickness = "%.2f" % thickness
                            writeVals.append([gid, thickness])
                            # qry += [(gid, thickness)]

                if len(writeVals) > 0:
                    self.gutils.clear_tables("tailing_cells")
                    qry += writeVals
                    self.gutils.batch_execute(qry)
                    # self.con.executemany(qry, writeVals)
                    # self.con.commit()
                    QApplication.restoreOverrideCursor()
                    self.uc.show_info("Assigning tailing cells finished!")
                else:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_info(
                        "There are no intersections between the grid and layer '" + external_layer.name() + "' !"
                    )

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error(
                "ERROR 030922.1128: Evaluation of tailings failed!\n"
                "________________________________________________________________",
                e,
            )
            QApplication.restoreOverrideCursor()

    def eval_arfwrf(self):
        eval_dlg = EvaluateReductionFactorsDialog(self.lyrs)
        ok = eval_dlg.exec_()
        if not ok:
            return
        try:
            grid_empty = self.gutils.is_table_empty("grid")
            if grid_empty:
                self.uc.bar_warn("There is no grid. Please, create it before evaluating the reduction factors.")
                self.uc.log_info("There is no grid. Please, create it before evaluating the reduction factors.")
                return
            else:
                pass
            if not self.gutils.is_table_empty("blocked_cells"):
                q = "There are some ARFs and WRFs already defined in the database. Overwrite them?\n\n"
                q += "Please, note that the new reduction factors will be evaluated for existing blocked areas ONLY."
                if not self.uc.question(q):
                    return
            if not self.lyrs.save_edits_and_proceed("Blocked Areas"):
                return
            if eval_dlg.use_external_layer():
                (
                    external_layer,
                    collapse_field,
                    arf_field,
                    wrf_field,
                ) = eval_dlg.external_layer_parameters()
                if not self.import_external_blocked_areas(external_layer, collapse_field, arf_field, wrf_field):
                    return
            else:
                if self.gutils.is_table_empty("user_blocked_areas"):
                    self.uc.bar_warn(
                        'There are no any blocking polygons in "Blocked Areas" layer!'
                    )
                    self.uc.log_info(
                        'There are no any blocking polygons in "Blocked Areas" layer! '
                        "Please digitize (or import) them before running tool."
                    )
                    return

            QApplication.setOverrideCursor(Qt.WaitCursor)
            grid_lyr = self.lyrs.data["grid"]["qlyr"]
            user_arf_lyr = self.lyrs.data["user_blocked_areas"]["qlyr"]
            if evaluate_arfwrf(self.gutils, grid_lyr, user_arf_lyr):
                if self.replace_ARF_WRF_duplicates():
                    arf_lyr = self.lyrs.data["blocked_cells"]["qlyr"]
                    arf_lyr.reload()
                    self.lyrs.update_layer_extents(arf_lyr)

                    self.lyrs.update_style_blocked(arf_lyr.id())
                    self.iface.mapCanvas().clearCache()
                    user_arf_lyr.triggerRepaint()
                    QApplication.restoreOverrideCursor()
                    self.uc.bar_info("ARF and WRF values calculated! The ARF and WRF switch is now enabled.")
                    self.uc.log_info("ARF and WRF values calculated! The ARF and WRF switch is now enabled.")
                    # Set ARFs on the Control Parameters
                    self.gutils.set_cont_par("IWRFS", 1)
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error(
                "ERROR 060319.1608: Evaluation of ARFs and WRFs failed! Please check your Blocked Areas User Layer.\n"
                "________________________________________________________________",
                e,
            )
            QApplication.restoreOverrideCursor()

    def replace_ARF_WRF_duplicates(self):
        try:
            new_feats = []
            arf_lyr = self.lyrs.data["blocked_cells"]["qlyr"]
            fields = arf_lyr.fields()
            arf_feats = arf_lyr.getFeatures()
            # get first 'blocked_cells' (ARF_WRF layer) feature.
            f0 = next(arf_feats)
            grid0 = f0["grid_fid"]

            # Assign initial values for variables to accumulate duplicate cell.
            area_fid = f0["area_fid"]
            arf = f0["arf"]
            wrf1 = f0["wrf1"]
            wrf2 = f0["wrf2"]
            wrf3 = f0["wrf3"]
            wrf4 = f0["wrf4"]
            wrf5 = f0["wrf5"]
            wrf6 = f0["wrf6"]
            wrf7 = f0["wrf7"]
            wrf8 = f0["wrf8"]

            try:
                while True:
                    f1 = next(arf_feats)
                    grid1 = f1["grid_fid"]
                    if grid1 == grid0:
                        # Accumulate values for all fields of this duplicate cell.
                        #                         area_fid += f1['area_fid']
                        arf += f1["arf"]
                        wrf1 += f1["wrf1"]
                        wrf2 += f1["wrf2"]
                        wrf3 += f1["wrf3"]
                        wrf4 += f1["wrf4"]
                        wrf5 += f1["wrf5"]
                        wrf6 += f1["wrf6"]
                        wrf7 += f1["wrf7"]
                        wrf8 += f1["wrf8"]
                    else:
                        # Create feature with the accumulated values of duplicated cell.
                        new_feat = QgsFeature()
                        new_feat.setFields(fields)

                        geom0 = f0.geometry()
                        point0 = geom0.asPoint()
                        new_geom0 = QgsGeometry.fromPointXY(point0)
                        new_feat.setGeometry(new_geom0)

                        new_feat["grid_fid"] = grid0
                        new_feat["area_fid"] = area_fid
                        new_feat["arf"] = arf if arf <= 1 else 1
                        new_feat["wrf1"] = wrf1 if wrf1 <= 1 else 1
                        new_feat["wrf2"] = wrf2 if wrf2 <= 1 else 1
                        new_feat["wrf3"] = wrf3 if wrf3 <= 1 else 1
                        new_feat["wrf4"] = wrf4 if wrf4 <= 1 else 1
                        new_feat["wrf5"] = wrf5 if wrf5 <= 1 else 1
                        new_feat["wrf6"] = wrf6 if wrf6 <= 1 else 1
                        new_feat["wrf7"] = wrf7 if wrf7 <= 1 else 1
                        new_feat["wrf8"] = wrf8 if wrf8 <= 1 else 1
                        new_feats.append(new_feat)

                        # Make f1 feature the next f0:
                        f0 = f1
                        grid0 = f0["grid_fid"]
                        area_fid = f0["area_fid"]
                        arf = f0["arf"]
                        wrf1 = f0["wrf1"]
                        wrf2 = f0["wrf2"]
                        wrf3 = f0["wrf3"]
                        wrf4 = f0["wrf4"]
                        wrf5 = f0["wrf5"]
                        wrf6 = f0["wrf6"]
                        wrf7 = f0["wrf7"]
                        wrf8 = f0["wrf8"]
            except StopIteration:
                new_feat = QgsFeature()
                new_feat.setFields(fields)

                geom0 = f0.geometry()
                point0 = geom0.asPoint()
                new_geom0 = QgsGeometry.fromPointXY(point0)
                new_feat.setGeometry(new_geom0)

                new_feat["grid_fid"] = grid0
                new_feat["area_fid"] = area_fid
                new_feat["arf"] = arf
                new_feat["wrf1"] = wrf1
                new_feat["wrf2"] = wrf2
                new_feat["wrf3"] = wrf3
                new_feat["wrf4"] = wrf4
                new_feat["wrf5"] = wrf5
                new_feat["wrf6"] = wrf6
                new_feat["wrf7"] = wrf7
                new_feat["wrf8"] = wrf8
                new_feats.append(new_feat)

            # Clear 'blocked_cells' and add all features with values accumulated.
            self.gutils.clear_tables("blocked_cells")
            arf_lyr.startEditing()
            arf_lyr.addFeatures(new_feats)
            arf_lyr.commitChanges()
            arf_lyr.updateExtents()
            arf_lyr.triggerRepaint()
            arf_lyr.removeSelection()

            return True

        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 060319.1609: Replacing duplicated ARFs and WRFs failed!.\n"
                "________________________________________________________________",
                e,
            )
            return False

    def import_comp_domain(self, external_layer, cell_size_field):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if not all([external_layer, cell_size_field]):
                raise UserWarning("Missing Parameters!")
            user_model_boundary_lyr = self.lyrs.data["user_model_boundary"]["qlyr"]
            user_model_boundary_fields = user_model_boundary_lyr.dataProvider().fields()
            field_names_map = {
                "cell_size": cell_size_field,
            }
            user_feats = []
            for feat in external_layer.getFeatures():
                geom = feat.geometry()
                if not geom.isGeosValid():
                    geom = geom.buffer(0.0, 5)
                    if not geom.isGeosValid():
                        continue
                if geom.isMultipart():
                    new_geoms = [QgsGeometry.fromPolygonXY(g) for g in geom.asMultiPolygon()]
                else:
                    new_geoms = [geom]
                for new_geom in new_geoms:
                    user_feat = QgsFeature(user_model_boundary_fields)
                    user_feat.setGeometry(new_geom)
                    for user_field_name, external_field_name in field_names_map.items():
                        external_value = feat[external_field_name]
                        user_feat[user_field_name] = int(external_value) if external_value != NULL else external_value
                    user_feats.append(user_feat)
            user_model_boundary_lyr.startEditing()
            user_model_boundary_lyr.deleteFeatures([f.id() for f in user_model_boundary_lyr.getFeatures()])
            user_model_boundary_lyr.addFeatures(user_feats)
            user_model_boundary_lyr.commitChanges()
            user_model_boundary_lyr.updateExtents()
            user_model_boundary_lyr.triggerRepaint()
            QApplication.restoreOverrideCursor()
            return True
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error(
                "ERROR: Import Computational Domain failed! Please check your external layer.\n"
                "________________________________________________________________",
                e,
            )
            return False

    def import_external_blocked_areas(self, external_layer, collapse_field, arf_field, wrf_field):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if not all([external_layer, collapse_field, arf_field, wrf_field]):
                raise UserWarning("Missing external layers parameters!")
            blocked_areas_lyr = self.lyrs.data["user_blocked_areas"]["qlyr"]
            blocked_areas_fields = blocked_areas_lyr.dataProvider().fields()
            field_names_map = {
                "collapse": collapse_field,
                "calc_arf": arf_field,
                "calc_wrf": wrf_field,
            }
            user_feats = []
            for feat in external_layer.getFeatures():
                geom = feat.geometry()
                if not geom.isGeosValid():
                    geom = geom.buffer(0.0, 5)
                    if not geom.isGeosValid():
                        continue
                if geom.isMultipart():
                    new_geoms = [QgsGeometry.fromPolygonXY(g) for g in geom.asMultiPolygon()]
                else:
                    new_geoms = [geom]
                for new_geom in new_geoms:
                    user_feat = QgsFeature(blocked_areas_fields)
                    user_feat.setGeometry(new_geom)
                    for user_field_name, external_field_name in field_names_map.items():
                        external_value = feat[external_field_name]
                        user_feat[user_field_name] = int(external_value) if external_value != NULL else external_value
                    user_feats.append(user_feat)
            blocked_areas_lyr.startEditing()
            blocked_areas_lyr.deleteFeatures([f.id() for f in blocked_areas_lyr.getFeatures()])
            blocked_areas_lyr.addFeatures(user_feats)
            blocked_areas_lyr.commitChanges()
            blocked_areas_lyr.updateExtents()
            blocked_areas_lyr.triggerRepaint()
            QApplication.restoreOverrideCursor()
            return True
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error(
                "ERROR: Import of ARFs and WRFs failed! Please check your external layer.\n"
                "________________________________________________________________",
                e,
            )
            return False

    def eval_tolerance(self):
        grid_empty = self.gutils.is_table_empty("grid")
        if grid_empty:
            self.uc.bar_warn("There is no grid. Please, create it before evaluating the tolerance values.")
            self.uc.log_info("There is no grid. Please, create it before evaluating the tolerance values.")
            return
        else:
            pass
        if not self.gutils.is_table_empty("tolspatial_cells"):
            q = "There are some spatial tolerance cells already defined in the database. Overwrite them?\n\n"
            q += "Please, note that the new spatial tolerance will be evaluated for existing tolerance polygons ONLY."
            if not self.uc.question(q):
                return
        if not self.lyrs.save_edits_and_proceed("Tolerance Areas"):
            return
        if self.gutils.is_table_empty("tolspatial"):
            w = "There are no tolerance polygons in Tolerance Areas (User Layers)!.\n\n"
            w += "Please digitize them before running tool."
            self.uc.bar_warn(w)
            self.uc.log_info(w)
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            grid_lyr = self.lyrs.data["grid"]["qlyr"]
            user_tol_lyr = self.lyrs.data["tolspatial"]["qlyr"]
            evaluate_spatial_tolerance(self.gutils, grid_lyr, user_tol_lyr)
            tol_lyr = self.lyrs.data["tolspatial"]["qlyr"]
            tol_lyr.reload()
            self.lyrs.update_layer_extents(tol_lyr)
            QApplication.restoreOverrideCursor()
            self.uc.show_info("Spatial tolerance values calculated!")
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn(
                "ERROR 060319.1834: Evaluation of spatial tolerance failed! Please check your Tolerance Areas (Schematic layer)."
            )
            QApplication.restoreOverrideCursor()

    def eval_froude(self):
        grid_empty = self.gutils.is_table_empty("grid")
        if grid_empty:
            self.uc.bar_warn("There is no grid. Please, create it before evaluating the Froude values.")
            self.uc.log_info("There is no grid. Please, create it before evaluating the Froude values.")
            return
        else:
            pass
        if not self.gutils.is_table_empty("fpfroude_cells"):
            q = "There are some spatial Froude cells already defined in the database. Overwrite them?\n\n"
            q += "Please, note that the new Froude values will be evaluated for existing Froude polygons ONLY."
            if not self.uc.question(q):
                return
        if not self.lyrs.save_edits_and_proceed("Froude Areas"):
            return
        if self.gutils.is_table_empty("fpfroude"):
            w = "There are no Froude polygons in Froude Areas (User Layers)!.\n\n"
            w += "Please digitize them before running tool."
            self.uc.bar_warn(w)
            self.uc.log_info(w)
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            grid_lyr = self.lyrs.data["grid"]["qlyr"]
            user_froude_lyr = self.lyrs.data["fpfroude"]["qlyr"]
            evaluate_spatial_froude(self.gutils, grid_lyr, user_froude_lyr)
            froude_lyr = self.lyrs.data["fpfroude"]["qlyr"]
            froude_lyr.reload()
            self.lyrs.update_layer_extents(froude_lyr)
            # self.lyrs.update_style_blocked(froude_lyr.id())
            # self.iface.mapCanvas().clearCache()
            # user_tol_lyr.triggerRepaint()
            QApplication.restoreOverrideCursor()
            self.uc.show_info("Spatial Froude values calculated!")
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn(
                "WARNING 060319.1717: Evaluation of spatial Froude failed! Please check your Froude Areas (Schematic layer)."
            )
            QApplication.restoreOverrideCursor()

    def eval_shallow_n(self):
        grid_empty = self.gutils.is_table_empty("grid")
        if grid_empty:
            self.uc.bar_warn(
                "WARNING 060319.1718: There is no grid. Please, create it before evaluating the shallow-n values."
            )
            self.uc.log_info(
                "WARNING 060319.1718: There is no grid. Please, create it before evaluating the shallow-n values."
            )
            return
        else:
            pass
        if not self.gutils.is_table_empty("spatialshallow_cells"):
            q = "There are some spatial shallow-n cells already defined in the database. Overwrite them?\n\n"
            q += "Please, note that the new shallow-n values will be evaluated for existing shallow-n polygons ONLY."
            if not self.uc.question(q):
                return
        if not self.lyrs.save_edits_and_proceed("Shallow-n Areas"):
            return
        if self.gutils.is_table_empty("spatialshallow"):
            w = "There are no shallow polygons in Shallow-n Areas (User Layers)!.\n\n"
            w += "Please digitize them before running tool."
            self.uc.bar_warn(w)
            self.uc.log_info(w)
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            grid_lyr = self.lyrs.data["grid"]["qlyr"]
            user_shallow_lyr = self.lyrs.data["spatialshallow"]["qlyr"]
            evaluate_spatial_shallow(self.gutils, grid_lyr, user_shallow_lyr)
            shallow_lyr = self.lyrs.data["spatialshallow"]["qlyr"]
            shallow_lyr.reload()
            self.lyrs.update_layer_extents(shallow_lyr)
            # self.lyrs.update_style_blocked(shallow_lyr.id())
            # self.iface.mapCanvas().clearCache()
            # user_tol_lyr.triggerRepaint()
            QApplication.restoreOverrideCursor()
            self.uc.show_info("Spatial shallow-n values calculated!")
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn(
                "WARNING 060319.1719: Evaluation of spatial shallow-n failed! Please check your Shallow-n Areas (Schematic layer)."
            )
            QApplication.restoreOverrideCursor()

    def eval_gutter(self):
        grid_empty = self.gutils.is_table_empty("grid")
        if grid_empty:
            self.uc.bar_warn("There is no grid. Please, create it before evaluating the gutter values.")
            self.uc.log_info("There is no grid. Please, create it before evaluating the gutter values.")
            return
        if not self.lyrs.save_edits_and_proceed(
            "Gutter Areas"
        ):  # Gutter polygons in User Layer, save them or cancel them.
            return
        if not self.lyrs.save_edits_and_proceed(
            "Gutter Lines"
        ):  # Gutter polygons in User Layer, save them or cancel them.
            return
        else:
            pass

        if not self.gutils.is_table_empty("gutter_areas") or not self.gutils.is_table_empty("gutter_lines"):
            if not self.gutils.is_table_empty("gutter_cells"):  # Gutter cells in Table Gutter Cells
                q = 'There are some spatial gutter cells already defined in the database (in Table "Gutter Cells"). Overwrite them?\n\n'
                q += "Please, note that the new gutter values will be evaluated for existing gutter polygons and lines ONLY (from the User Layers)."
                if not self.uc.question(q):
                    return

        if self.gutils.is_table_empty("gutter_areas") and self.gutils.is_table_empty("gutter_lines"):
            self.uc.show_warn(
                "There are no gutter polygons or lines in Gutter Areas  and Gutter Lines (User Layers)!.\n\n"
                + "Please digitize them to create Gutter Cells."
            )
            self.uc.log_info(
                "There are no gutter polygons or lines in Gutter Areas  and Gutter Lines (User Layers)!.\n\n"
                + "Please digitize them to create Gutter Cells."
            )

        else:
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                grid_lyr = self.lyrs.data["grid"]["qlyr"]

                user_gutter_areas_lyr = self.lyrs.data["gutter_areas"]["qlyr"]
                user_gutter_lines_lyr = self.lyrs.data["gutter_lines"]["qlyr"]
                evaluate_spatial_gutter(self.gutils, grid_lyr, user_gutter_areas_lyr, user_gutter_lines_lyr)
                gutter_lyr = self.lyrs.data["gutter_areas"]["qlyr"]
                gutter_lyr.reload()
                self.lyrs.update_layer_extents(gutter_lyr)
                self.lyrs.data["gutter_cells"]["qlyr"].triggerRepaint()

                self.assign_gutter_globals()
                self.iface.actionPan().trigger()

                QApplication.restoreOverrideCursor()
                self.uc.show_info("Spatial gutter values calculated into the Gutter Cells table!")

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.log_info(traceback.format_exc())
                self.uc.show_warn(
                    'WARNING 060319.1720: Evaluation of spatial gutter failed!\nPlease check "Gutter Areas" and "Gutter Lines" (User layers).'
                )
                QApplication.restoreOverrideCursor()

    def assign_gutter_globals(self):
        if self.gutils.is_table_empty("gutter_globals"):
            self.globlyr = self.lyrs.data["gutter_globals"]["qlyr"]
            self.iface.setActiveLayer(self.globlyr)
            self.globlyr.featureAdded.connect(self.feature_added)

            self.globlyr.startEditing()
            self.iface.actionAddFeature().trigger()
            self.globlyr.removeSelection()

    # Define a function called when a feature is added to the layer
    def feature_added(self):
        # Disconnect from the signal
        self.globlyr.featureAdded.disconnect()

        # Save changes and end edit mode
        self.globlyr.commitChanges()

    def evaluate_gutter(self):
        self.eval_gutter()

    #         self.iface.actionPan().trigger()
    #         self.iface.activeLayer().stopEditing()

    #         if not self.lyrs.any_lyr_in_edit("gutter_globals"):
    #             self.lyrs.save_lyrs_edits('gutter_globals')

    #         lyr = self.lyrs.data["gutter_globals"]['qlyr']
    #         lyr.commitChanges()
    #         lyr.updateExtents()
    #         lyr.triggerRepaint()
    #         lyr.removeSelection()

    def eval_noexchange(self):
        grid_empty = self.gutils.is_table_empty("grid")
        if grid_empty:
            self.uc.bar_warn("There is no grid. Please, create it before evaluating the no-exchange cells.")
            self.uc.log_info("There is no grid. Please, create it before evaluating the no-exchange cells.")
            return
        else:
            pass
        if not self.gutils.is_table_empty("noexchange_chan_cells"):
            q = "There are some no-exchange cells already defined in the database. Overwrite them?\n\n"
            q += "Please, note that the new no-exchange cells will be evaluated for existing no-exchange polygons ONLY."
            if not self.uc.question(q):
                return
        if not self.lyrs.save_edits_and_proceed("No-Exchange Channel Cells"):
            return
        if self.gutils.is_table_empty("user_noexchange_chan_areas"):
            w = 'There are no "no-exchange" polygons in No-Exchange Channel Areas (User Layers)!.\n\n'
            w += "Please digitize them before running tool."
            self.uc.bar_warn(w)
            self.uc.log_info(w)
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            grid_lyr = self.lyrs.data["grid"]["qlyr"]
            user_tol_lyr = self.lyrs.data["user_noexchange_chan_areas"]["qlyr"]
            evaluate_spatial_noexchange(self.gutils, grid_lyr, user_tol_lyr)
            tol_lyr = self.lyrs.data["user_noexchange_chan_areas"]["qlyr"]
            tol_lyr.reload()
            self.lyrs.update_layer_extents(tol_lyr)
            QApplication.restoreOverrideCursor()
            self.uc.show_info("No-exchange areas selected!")
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn(
                "WARNING 060319.1721: Selection of no-exchange cells failed! Please check your No-xchange Cells (Tables layer)."
            )
            QApplication.restoreOverrideCursor()

    def eval_steep_slopen(self):
        grid_empty = self.gutils.is_table_empty("grid")
        if grid_empty:
            self.uc.bar_warn("There is no grid. Please, create it before evaluating the steep slope-n cells.")
            self.uc.log_info("There is no grid. Please, create it before evaluating the steep slope-n cells.")
            return
        else:
            pass
        if not self.gutils.is_table_empty("steep_slope_n_cells"):
            q = "There are some steep slope-n cells already defined in the database. Overwrite them?\n\n"
            q += "Please, note that the new steep slope-n cells will be evaluated for existing steep slope-n polygons ONLY."
            if not self.uc.question(q):
                return
        if not self.lyrs.save_edits_and_proceed("Steep Slope n Cells"):
            return
        if self.gutils.is_table_empty("user_steep_slope_n_areas"):
            w = 'There are no "steep slope-n" polygons in Steep Slope n Areas (User Layers)!.\n\n'
            w += "Please digitize them before running tool."
            self.uc.bar_warn(w)
            self.uc.log_info(w)
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.gutils.clear_tables("steep_slope_n_cells")
            qry = """SELECT COUNT(*) FROM user_steep_slope_n_areas WHERE global = 1;"""
            result = self.gutils.execute(qry).fetchone()
            # Save global steep slope n value
            if result and result[0] > 0:
                insert_qry = """INSERT INTO steep_slope_n_cells (global) VALUES (?);"""
                self.gutils.execute(insert_qry, (1,))
            # Save individual cells
            else:
                intersection_qry = """
                                        INSERT INTO steep_slope_n_cells (global, area_fid, grid_fid)
                                        SELECT 0, a.fid AS area_fid, g.fid AS grid_fid
                                        FROM
                                            grid AS g,
                                            user_steep_slope_n_areas AS a
                                        WHERE
                                            ST_Intersects(CastAutomagic(g.geom), CastAutomagic(a.geom));
                                    """
                self.gutils.execute(intersection_qry)
            steep_slopen_lyr = self.lyrs.data["user_steep_slope_n_areas"]["qlyr"]
            steep_slopen_lyr.reload()
            self.lyrs.update_layer_extents(steep_slopen_lyr)
            QApplication.restoreOverrideCursor()
            self.uc.show_info("Steep Slope-n areas selected!")
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn(
                "WARNING 060319.1721: Selection of Steep Slope-n cells failed! Please check your Steep Slope-n Cells (Tables layer)."
            )
            QApplication.restoreOverrideCursor()

    def eval_lid_volume(self):
        grid_empty = self.gutils.is_table_empty("grid")
        if grid_empty:
            self.uc.bar_warn("There is no grid. Please, create it before sampling LID Volume cells.")
            self.uc.log_info("There is no grid. Please, create it before sampling LID Volume cells.")
            return
        else:
            pass
        if not self.gutils.is_table_empty("lid_volume_cells"):
            q = "There are some LID Volume cells already defined in the database. Overwrite them?\n\n"
            q += "Please, note that the new LID Volume cells will be evaluated for existing LID Volume polygons ONLY."
            if not self.uc.question(q):
                return
        if not self.lyrs.save_edits_and_proceed("LID Volume Cells"):
            return
        if self.gutils.is_table_empty("user_lid_volume_areas"):
            w = 'There are no "LID Volume" polygons in LID Volume Areas (User Layers)!.\n\n'
            w += "Please digitize them before running tool."
            self.uc.bar_warn(w)
            self.uc.log_info(w)
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.gutils.clear_tables("lid_volume_cells")
            intersection_qry = """
                                    INSERT INTO lid_volume_cells (volume, area_fid, grid_fid)
                                    SELECT a.volume AS volume, a.fid AS area_fid, g.fid AS grid_fid
                                    FROM
                                        grid AS g,
                                        user_lid_volume_areas AS a
                                    WHERE
                                        ST_Intersects(CastAutomagic(g.geom), CastAutomagic(a.geom));
                                """
            self.gutils.execute(intersection_qry)
            lid_volume_lyr = self.lyrs.data["user_lid_volume_areas"]["qlyr"]
            lid_volume_lyr.reload()
            self.lyrs.update_layer_extents(lid_volume_lyr)
            QApplication.restoreOverrideCursor()
            self.uc.show_info("LID Volume areas selected!")
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn(
                "WARNING 060319.1721: Selection of LID Volume cells failed! Please check your LID Volume Cells (Tables layer)."
            )
            QApplication.restoreOverrideCursor()

    def show_grid_widget_help(self):
        """
        Function to show the grid widget help
        """
        QDesktopServices.openUrl(QUrl("https://flo-2dsoftware.github.io/FLO-2D-Documentation/Plugin1000/widgets/grid-tools/index.html"))

    def plot_2d_grid_data(self, grid_element):
        """
        Function to create the 2d time series plot for a specific grid element.
        """

        QApplication.setOverrideCursor(Qt.WaitCursor)

        units = "CMS" if self.gutils.get_cont_par("METRIC") == "1" else "CFS"

        processed_results_file = self.gutils.get_cont_par("SCENARIOS_RESULTS")
        use_prs = self.gutils.get_cont_par("USE_SCENARIOS")

        if use_prs == '1' and os.path.exists(processed_results_file):
            dict_df = timdep_dataframe_from_hdf5_scenarios(processed_results_file, grid_element)

            try:
                # Clear the plots
                self.plot.clear()
                if self.plot.plot.legend is not None:
                    plot_scene = self.plot.plot.legend.scene()
                    if plot_scene is not None:
                        plot_scene.removeItem(self.plot.plot.legend)

                # Set up legend and plot title
                self.plot.plot.legend = None
                self.plot.plot.addLegend(offset=(0, 30))
                self.plot.plot.setTitle(title=f"Grid Element - {grid_element}")
                self.plot.plot.setLabel("bottom", text="Time (hrs)")
                self.plot.plot.setLabel("left", text="")

                # Create a new data model for the table view.
                data_model = StandardItemModel()
                self.tview.undoStack.clear()
                self.tview.setModel(data_model)
                data_model.clear()
                headers = ["Time (hours)"]

                # Create the plot items for each scenario and fill the table view.
                for i, (key, value) in enumerate(dict_df.items(), start=0):
                    self.plot.add_item(f"{key} - Depth ({self.system_units[units][0]}) ", [value['Time'], value['Depth']],
                                       col=SCENARIO_COLOURS[i], sty=SCENARIO_STYLES[0])
                    self.plot.add_item(f"{key} - Velocity ({self.system_units[units][1]})", [value['Time'], value['Velocity']],
                                       col=SCENARIO_COLOURS[i], sty=SCENARIO_STYLES[1], hide=True)
                    self.plot.add_item(f"{key} - WSE ({self.system_units[units][0]})",
                                       [value['Time'], value['WSE']], col=SCENARIO_COLOURS[i],
                                       sty=SCENARIO_STYLES[2], hide=True)

                    headers.extend([
                        f"{key} - Depth ({self.system_units[units][0]})",
                        f"{key} - Velocity ({self.system_units[units][1]})",
                        f"{key} - WSE ({self.system_units[units][0]})"
                    ])
                    data_model.setHorizontalHeaderLabels(headers)

                    for row_idx, row in enumerate(value):
                        if i == 0:
                            data_model.setItem(row_idx, 0,
                                               StandardItem("{:.2f}".format(row[0]) if row[0] is not None else ""))
                        data_model.setItem(row_idx, 1 + i * 3,
                                           StandardItem("{:.2f}".format(row[1]) if row[1] is not None else ""))
                        data_model.setItem(row_idx, 2 + i * 3,
                                           StandardItem("{:.2f}".format(row[2]) if row[2] is not None else ""))
                        data_model.setItem(row_idx, 3 + i * 3,
                                           StandardItem("{:.2f}".format(row[3]) if row[3] is not None else ""))

            except:
                QApplication.restoreOverrideCursor()
                self.uc.bar_warn("Error while creating the plots!")
                self.uc.log_info("Error while creating the plots!")
                return

        else:
            # check if there is a FLO-2D mesh file.
            has_mesh = False
            temporal_mesh = False
            flo2d_mesh = False
            mesh_layer = None

            # Check for mesh layer
            layers = QgsProject.instance().mapLayers().values()
            for layer in layers:
                if isinstance(layer, QgsMeshLayer):
                    mesh_layer = layer
                    has_mesh = True

            if has_mesh:
                # Check temporal layer
                temporal_properties = mesh_layer.temporalProperties()
                if temporal_properties.isActive():
                    temporal_mesh = True

            if has_mesh and temporal_mesh:
                self.uc.bar_info("Reading data from mesh layer!")
                self.uc.log_info("Reading data from mesh layer!")
                try:
                    df = self.dataframe_from_mesh(mesh_layer, grid_element)
                except:
                    QApplication.restoreOverrideCursor()
                    self.uc.bar_warn("Error while retrieving data from mesh layer!")
                    self.uc.log_info("Error while retrieving data from mesh layer!")
                    return

            else:
                # Check if there is an TIMDEP.OUT file on the export folder and has data
                s = QSettings()
                project_dir = s.value("FLO-2D/lastGdsDir")
                TIMDEPOUT_file = project_dir + r"/TIMDEP.OUT"
                TIMDEPHDF5_file = project_dir + r"/TIMDEP.HDF5"

                # Check if the TIMDEP_file.HDF5 exists
                if os.path.isfile(TIMDEPHDF5_file):
                    # Check if the TIMDEP_file.HDF5 has data on it
                    if os.path.getsize(TIMDEPHDF5_file) == 0:
                        QApplication.restoreOverrideCursor()
                        self.uc.bar_warn("File  '" + os.path.basename(TIMDEPHDF5_file) + "'  is empty!")
                        self.uc.log_info("File  '" + os.path.basename(TIMDEPHDF5_file) + "'  is empty!")
                        return
                    else:
                        self.uc.bar_info("Reading data from TIMDEP.HDF5!")
                        self.uc.log_info("Reading data from TIMDEP.HDF5!")
                        try:
                            df = self.dataframe_from_hdf5(TIMDEPHDF5_file, grid_element)
                        except:
                            QApplication.restoreOverrideCursor()
                            self.uc.bar_warn("Error while retrieving data from TIMDEP.HDF5!")
                            self.uc.log_info("Error while retrieving data from TIMDEP.HDF5!")
                            return
                else:
                    # Check if the TIMDEP_file.OUT exists
                    if not os.path.isfile(TIMDEPOUT_file):
                        QApplication.restoreOverrideCursor()
                        self.uc.bar_warn(
                            "No mesh layer, TIMDEP.HDF5 or TIMDEP.OUT file found. "
                            "Please ensure the simulation has completed and verify the project export folder.")
                        self.uc.log_info(
                            "No mesh layer, TIMDEP.HDF5 or TIMDEP.OUT file found. "
                            "Please ensure the simulation has completed and verify the project export folder.")
                        return
                    else:
                        # Check if the TIMDEP_file.OUT has data on it
                        if os.path.getsize(TIMDEPOUT_file) == 0:
                            QApplication.restoreOverrideCursor()
                            self.uc.bar_warn("File  '" + os.path.basename(TIMDEPHDF5_file) + "'  is empty!")
                            self.uc.log_info("File  '" + os.path.basename(TIMDEPHDF5_file) + "'  is empty!")
                            return
                        else:
                            self.uc.bar_info("Reading data from TIMDEP.OUT!")
                            self.uc.log_info("Reading data from TIMDEP.OUT!")
                            try:
                                df = self.dataframe_from_out(TIMDEPOUT_file, grid_element)
                            except:
                                QApplication.restoreOverrideCursor()
                                self.uc.bar_warn("Error while retrieving data from TIMDEP.OUT!")
                                self.uc.log_info("Error while retrieving data from TIMDEP.OUT!")
                                return

            try:  # Create the plots
                self.plot.clear()
                if self.plot.plot.legend is not None:
                    plot_scene = self.plot.plot.legend.scene()
                    if plot_scene is not None:
                        plot_scene.removeItem(self.plot.plot.legend)

                self.plot.plot.legend = None
                self.plot.plot.addLegend(offset=(0, 30))
                self.plot.plot.setTitle(title=f"Grid Element - {grid_element}")
                self.plot.plot.setLabel("bottom", text="Time (hrs)")
                self.plot.plot.setLabel("left", text="")
                self.plot.add_item(f"Depth ({self.system_units[units][0]})", [df['Time'], df['Depth']], col=QColor(Qt.darkBlue), sty=Qt.SolidLine)
                self.plot.add_item(f"Velocity ({self.system_units[units][1]})", [df['Time'], df['Velocity']], col=QColor(Qt.yellow), sty=Qt.SolidLine, hide=True)
                self.plot.add_item(f"Water Surface Elevation ({self.system_units[units][0]})", [df['Time'], df['Water_Surface_Elevation']], col=QColor(Qt.darkGreen), sty=Qt.SolidLine, hide=True)

            except:
                QApplication.restoreOverrideCursor()
                self.uc.bar_warn("Error while creating the plots!")
                self.uc.log_info("Error while creating the plots!")
                return

            try:  # Build table.
                data_model = StandardItemModel()
                self.tview.undoStack.clear()
                self.tview.setModel(data_model)
                data_model.clear()
                data_model.setHorizontalHeaderLabels([
                    "Time (hours)",
                    f"Depth ({self.system_units[units][0]})",
                    f"Velocity ({self.system_units[units][1]})",
                    f"Water Surface Elevation ({self.system_units[units][0]})"
                ])

                data = zip(df['Time'],
                           df['Depth'],
                           df['Velocity'],
                           df['Water_Surface_Elevation']
                           )
                for time, depth, velocity, wse in data:
                    time_item = StandardItem("{:.2f}".format(time)) if time is not None else StandardItem("")
                    depth_item = StandardItem("{:.2f}".format(depth)) if depth is not None else StandardItem("")
                    velocity_item = StandardItem("{:.2f}".format(velocity)) if velocity is not None else StandardItem("")
                    wse_item = StandardItem("{:.2f}".format(wse)) if wse is not None else StandardItem("")
                    data_model.appendRow([time_item,
                                          depth_item,
                                          velocity_item,
                                          wse_item])

                self.tview.horizontalHeader().setStretchLastSection(True)
                for col in range(3):
                    self.tview.setColumnWidth(col, 100)
                for i in range(data_model.rowCount()):
                    self.tview.setRowHeight(i, 20)
            except:
                QApplication.restoreOverrideCursor()
                self.uc.bar_warn("Error while creating table for grid element!")
                self.uc.log_info("Error while creating table for grid element!")
                return

        QApplication.restoreOverrideCursor()

    def dataframe_from_hdf5(self, hdf5_file, grid_element):
        """
        Function to get the data from hdf5 using numpy arrays.
        """
        file = h5py.File(hdf5_file)

        time_series = np.array(file['/TIMDEP NETCDF OUTPUT RESULTS/FLOW DEPTH/Times'])
        time_series = time_series.flatten()

        flow_depth = np.array(file['/TIMDEP NETCDF OUTPUT RESULTS/FLOW DEPTH/Values'])
        flow_depth = flow_depth[:, grid_element - 1].flatten()

        wse = np.array(file['/TIMDEP NETCDF OUTPUT RESULTS/Floodplain Water Surface Elevation/Values'])
        wse = wse[:, grid_element - 1].flatten()

        velocity = np.array(file['/TIMDEP NETCDF OUTPUT RESULTS/Velocity MAG/Values'])
        velocity = velocity[:, grid_element - 1].flatten()

        # Combine arrays into a structured numpy array
        data = np.core.records.fromarrays([time_series, flow_depth, velocity, wse],
                                          names='Time, Depth, Velocity, Water_Surface_Elevation')

        return data

    def dataframe_from_out(self, out_file, grid_element):
        """
        Function to get the data frame from out
        """
        data = []
        with open(out_file, 'r') as file:
            for line in file:
                line = line.strip()
                if line:
                    parts = line.split()
                    if len(parts) == 1:
                        # This line contains the time
                        current_time = float(parts[0])
                    else:
                        # This line contains the data for a grid element
                        current_grid_element = int(parts[0])
                        if current_grid_element == grid_element:
                            depth = float(parts[1])
                            velocity = float(parts[2])
                            # velocity_x = float(parts[3])
                            # velocity_y = float(parts[4])
                            water_surface_elevation = float(parts[5])

                            data.append(
                                [current_time, depth, velocity, water_surface_elevation])

        data = np.array(data)

        # Combine arrays into a structured numpy array
        data = np.core.records.fromarrays([data[:, 0], data[:, 1], data[:, 2], data[:, 3]],
                                                     names='Time, Depth, Velocity, Water_Surface_Elevation')

        return data

    def dataframe_from_mesh(self, mesh_layer, grid_element):
        """
        Function to get the data from mesh layer using numpy arrays.
        """
        grid = self.lyrs.data["grid"]["qlyr"]
        feature = next(grid.getFeatures(QgsFeatureRequest(grid_element)))
        geom = feature.geometry()
        point = geom.centroid().asPoint()

        time_series = []
        flow_depth = []
        velocity = []
        wse = []

        # HDF5 Present
        if mesh_layer.dataProvider().datasetGroupCount() == 5:
            for i in range(mesh_layer.dataProvider().datasetCount(1)):
                # TIME SERIES
                meta = mesh_layer.dataProvider().datasetMetadata(QgsMeshDatasetIndex(1, i))
                t = meta.time()
                time_series.append(t)

                # FLOW DEPTH
                dataset = QgsMeshDatasetIndex(1, i)
                value = mesh_layer.datasetValue(dataset, point, 0).scalar()
                value = 0 if math.isnan(value) else value
                flow_depth.append(value)

                # VELOCITY
                dataset = QgsMeshDatasetIndex(4, i)
                value = mesh_layer.datasetValue(dataset, point, 0).scalar()
                value = 0 if math.isnan(value) else value
                velocity.append(value)

                # WSE
                dataset = QgsMeshDatasetIndex(2, i)
                value = mesh_layer.datasetValue(dataset, point, 0).scalar()
                value = 0 if math.isnan(value) else value
                wse.append(value)

        # Only OUT
        if mesh_layer.dataProvider().datasetGroupCount() == 6:
            for i in range(mesh_layer.dataProvider().datasetCount(1)):
                # TIME SERIES
                meta = mesh_layer.dataProvider().datasetMetadata(QgsMeshDatasetIndex(1, i))
                t = meta.time()
                time_series.append(t)

                # FLOW DEPTH
                dataset = QgsMeshDatasetIndex(1, i)
                value = mesh_layer.datasetValue(dataset, point, 0).scalar()
                value = 0 if math.isnan(value) else value
                flow_depth.append(value)

                # VELOCITY
                dataset = QgsMeshDatasetIndex(2, i)
                value = mesh_layer.datasetValue(dataset, point, 0).scalar()
                value = 0 if math.isnan(value) else value
                velocity.append(value)

                # WSE
                dataset = QgsMeshDatasetIndex(3, i)
                value = mesh_layer.datasetValue(dataset, point, 0).scalar()
                value = 0 if math.isnan(value) else value
                wse.append(value)

        # Convert lists to numpy arrays
        time_series = np.array(time_series)
        flow_depth = np.array(flow_depth)
        velocity = np.array(velocity)
        wse = np.array(wse)

        data = np.core.records.fromarrays([time_series, flow_depth, velocity, wse],
                                          names='Time, Depth, Velocity, Water_Surface_Elevation')

        return data
