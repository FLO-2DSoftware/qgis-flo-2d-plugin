# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import re
import struct
import traceback
from collections import defaultdict

import numpy as np
from PyQt5.QtCore import QSettings, Qt, QUrl
from PyQt5.QtGui import QColor, QDesktopServices
from PyQt5.QtWidgets import QApplication
from qgis._core import QgsPointXY, QgsGeometry
from qgis.core import QgsFeatureRequest, QgsSpatialIndex
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QInputDialog
from shapely.speedups import available

from .table_editor_widget import StandardItemModel, StandardItem
from ..flo2d_tools.schematic_tools import FloodplainXS
from ..geopackage_utils import GeoPackageUtils
from ..misc.project_review_utils import hycross_dataframe_from_hdf5_scenarios, SCENARIO_COLOURS, SCENARIO_STYLES, \
    crossq_dataframe_from_hdf5_scenarios
from ..user_communication import UserCommunication
from .ui_utils import center_canvas, load_ui, set_icon, switch_to_selected

from ..deps import safe_h5py as h5py

uiDialog, qtBaseClass = load_ui("fpxsec_editor")


class FPXsecEditorWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs, plot, table):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.con = None
        self.gutils = None
        self.fpxsec_lyr = None
        self.plot = plot
        self.uc = UserCommunication(iface, "FLO-2D")
        self.table = table
        self.tview = table.tview

        self.system_units = {
            "CMS": ["m", "mps", "cms"],
            "CFS": ["ft", "fps", "cfs"]
             }

        # set button icons
        set_icon(self.add_user_fpxs_btn, "add_fpxs.svg")
        set_icon(self.revert_changes_btn, "mActionUndo.svg")
        set_icon(self.delete_fpxs_btn, "mActionDeleteSelected.svg")
        set_icon(self.schem_fpxs_btn, "schematize_fpxs.svg")
        set_icon(self.rename_fpxs_btn, "change_name.svg")

        self.fill_iflo_directions()

        # Buttons connections
        self.add_user_fpxs_btn.clicked.connect(self.create_user_fpxs)
        self.revert_changes_btn.clicked.connect(self.revert_fpxs_lyr_edits)
        self.delete_fpxs_btn.clicked.connect(self.delete_cur_fpxs)
        self.schem_fpxs_btn.clicked.connect(self.schematize_fpxs)
        self.del_schem_fpxs_btn.clicked.connect(self.delete_schema_fpxs)
        self.rename_fpxs_btn.clicked.connect(self.rename_fpxs)
        self.fpxs_cbo.activated.connect(self.cur_fpxs_changed)
        self.flow_dir_cbo.activated.connect(self.save_fpxs)
        self.help_btn.clicked.connect(self.show_fp_xs_widget_help)

        self.fpxsec_lyr = self.lyrs.data["user_fpxsec"]["qlyr"]
        self.schema_fpxsec_lyr = self.lyrs.data["fpxsec"]["qlyr"]

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

            self.report_chbox.setEnabled(True)
            nxprt = self.gutils.get_cont_par("NXPRT")
            if nxprt == "0":
                self.report_chbox.setChecked(False)
            elif nxprt == "1":
                self.report_chbox.setChecked(True)
            else:
                self.report_chbox.setChecked(False)
                self.set_report()
            self.report_chbox.stateChanged.connect(self.set_report)

    def switch2selected(self):
        switch_to_selected(self.fpxsec_lyr, self.fpxs_cbo)
        self.cur_fpxs_changed()

    def populate_cbos(self, fid=None, show_last_edited=True):
        self.fpxs_cbo.clear()
        qry = """SELECT fid, name, iflo FROM user_fpxsec ORDER BY name COLLATE NOCASE"""
        rows = self.gutils.execute(qry).fetchall()
        if rows:
            cur_idx = 0
            for i, row in enumerate(rows):
                self.fpxs_cbo.addItem(row[1], row)
                if fid and row[0] == fid:
                    cur_idx = i
            self.fpxs_cbo.setCurrentIndex(cur_idx)
            self.cur_fpxs_changed()
        else:
            self.lyrs.clear_rubber()

    def cur_fpxs_changed(self):
        """
        Function to change the floodplain cross-section combobox
        """
        row = self.fpxs_cbo.itemData(self.fpxs_cbo.currentIndex())
        if row is None:
            return
        self.fpxs_fid = row[0]

        fpxs_name = self.fpxs_cbo.currentText()

        if fpxs_name:
            # Get the feature associated with the combobox
            request = QgsFeatureRequest().setFilterExpression(f'"fid" = {self.fpxs_fid}')
            matching_features = self.fpxsec_lyr.getFeatures(request)
            feature = next(matching_features, None)
            geometry = feature.geometry()
            geom_poly = geometry.asPolyline()
            start, end = geom_poly[0], geom_poly[-1]
            # Calculate azimuth
            azimuth = start.azimuth(end)

            # Figure out the allowed directions
            iflo_allowed_directions = self.get_iflo_direction(azimuth)
            self.fill_iflo_directions()
            for i in range(8, 0, -1):  # Iterate in reverse (8 to 1)
                if i not in iflo_allowed_directions:
                    self.flow_dir_cbo.removeItem(i - 1)

            self.fpxs_fid, iflo = self.gutils.execute(f"SELECT fid, iflo FROM user_fpxsec WHERE name = '{fpxs_name}';").fetchone()
            index = self.flow_dir_cbo.findText(str(iflo))
            # If index equal -1, the direction is wrong. Needs to be fixed
            if index == -1:
                iflo = iflo_allowed_directions[0]
                qry = f"""UPDATE user_fpxsec SET iflo={iflo} WHERE fid={self.fpxs_fid};"""
                self.gutils.execute(qry)
            else:
                self.flow_dir_cbo.setCurrentIndex(index)

            self.lyrs.clear_rubber()
            if self.center_fpxs_chbox.isChecked():
                self.show_fpxs_rb()
                feat = next(self.fpxsec_lyr.getFeatures(QgsFeatureRequest(self.fpxs_fid)))
                x, y = feat.geometry().centroid().asPoint()
                center_canvas(self.iface, x, y)

    def show_fpxs_rb(self):
        if not self.fpxs_fid:
            return
        self.lyrs.show_feat_rubber(self.fpxsec_lyr.id(), self.fpxs_fid)

    def populate_fpxs_signal(self):
        self.add_user_fpxs_btn.setChecked(False)
        self.gutils.fill_empty_fpxs_names()
        self.populate_cbos(fid=self.gutils.get_max("user_fpxsec") - 1)

    def create_user_fpxs(self):

        if self.lyrs.any_lyr_in_edit("user_fpxsec"):
            self.save_fpxs_lyr_edits()
            self.add_user_fpxs_btn.setChecked(False)
            return

        self.add_user_fpxs_btn.setCheckable(True)
        self.add_user_fpxs_btn.setChecked(True)

        self.lyrs.enter_edit_mode("user_fpxsec")

    def save_fpxs_lyr_edits(self):
        if not self.lyrs.any_lyr_in_edit("user_fpxsec"):
            return
        has_data = self.gutils.is_table_empty("user_fpxsec")
        self.lyrs.save_lyrs_edits("user_fpxsec")
        if has_data:
            self.populate_cbos(fid=0)
        else:
            self.populate_cbos(fid=self.gutils.get_max("user_fpxsec"))

        self.cur_fpxs_changed()

        self.uc.bar_info("Floodplain cross-sections created!")
        self.uc.log_info("Floodplain cross-sections created!")

    def rename_fpxs(self):
        if not self.fpxs_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, "Change name", "New name:")
        if not ok or not new_name:
            return
        if not self.fpxs_cbo.findText(new_name) == -1:
            msg = "WARNING 060319.1704: Floodplain cross-sections with name {} already exists in the database. Please, choose another name."
            msg = msg.format(new_name)
            self.uc.show_warn(msg)
            self.uc.log_info(msg)
            return
        self.fpxs_cbo.setItemText(self.fpxs_cbo.currentIndex(), new_name)
        self.save_fpxs()

    def revert_fpxs_lyr_edits(self):
        user_fpxs_edited = self.lyrs.rollback_lyrs_edits("user_fpxsec")
        if user_fpxs_edited:
            self.populate_cbos()

    def delete_cur_fpxs(self):
        if not self.fpxs_cbo.count():
            return
        q = "Are you sure, you want delete the current floodplain cross-section?"
        if not self.uc.question(q):
            return
        self.gutils.execute("DELETE FROM user_fpxsec WHERE fid = ?;", (self.fpxs_fid,))
        self.populate_cbos(fid=0)
        self.fpxsec_lyr.triggerRepaint()

        fpxs_name = self.fpxs_cbo.currentText()
        self.fill_iflo_directions()
        self.uc.bar_info(f"The {fpxs_name} floodplain cross-section is deleted!")
        self.uc.log_info(f"The {fpxs_name} floodplain cross-section is deleted!")

    def save_fpxs(self):
        if not self.fpxs_cbo.count():
            return
        row = self.fpxs_cbo.itemData(self.fpxs_cbo.currentIndex())
        fid = row[0]
        name = self.fpxs_cbo.currentText()
        iflo = self.flow_dir_cbo.currentText()
        qry = "UPDATE user_fpxsec SET name = ?, iflo = ? WHERE fid = ?;"
        if fid > 0:
            self.gutils.execute(
                qry,
                (
                    name,
                    iflo,
                    fid,
                ),
            )
        self.populate_cbos(fid=fid, show_last_edited=False)

    def validate_schematized_fpxs(self):
        """
        Validate schematized floodplain cross-sections.
        If any schematized XS cross or touch each other, the whole schematization is rolled back.
        Also conflicting original user floodplain cross-sections are selected in the user_fpxsec layer.
        """
        layer = self.schema_fpxsec_lyr
        if layer is None:
            return True

        feats = [f for f in layer.getFeatures()]
        if not feats:
            return True

        # Build spatial index for fast conflict checks on schematized XS (use bounding-box)
        index = QgsSpatialIndex()
        index.addFeatures(feats)

        # Prepare containers for original user features
        user_layer = self.fpxsec_lyr # Gets the original user floodplain XS layer
        user_index = None # Placeholder for a spatial index on the user layer, initialized as None.
        user_feats = [] # Will hold the original user features, if available
        if user_layer is not None: # If the user layer exists:
            user_feats = [uf for uf in user_layer.getFeatures()] # Load all user-drawn XS features into a list.
            if user_feats: # If there are actually features, create another QgsSpatialIndex() and add those user features.
                user_index = QgsSpatialIndex() # will be used later to quickly find which user XS correspond to conflicting schematized XS.
                user_index.addFeatures(user_feats)

        # Create set of FIDs from schematized layer that are in conflict, and their corresponding user layer FIDs (for highlighing)
        conflict_schema_fids = set()
        conflict_user_fids = set()

        # First validation pass: find conflicts between schematized XS
        for feat in feats:
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue

            # First get candidate features ONLY via bounding box intersection
            cand_ids = index.intersects(geom.boundingBox())
            for cid in cand_ids:

                # Skip self-comparison
                if cid == feat.id():
                    continue

                # Fetch the candidate feature
                other = next(layer.getFeatures(QgsFeatureRequest(cid)), None)
                if other is None:
                    continue

                other_geom = other.geometry()
                if not other_geom or other_geom.isEmpty():
                    continue

                # Any cross OR touch is considered a conflict
                if geom.crosses(other_geom) or geom.touches(other_geom):
                    conflict_schema_fids.add(feat.id())
                    conflict_schema_fids.add(other.id())

        # If no conflicts found, validation passes
        if not conflict_schema_fids:
            return True

        # Second validation pass — find matching original USER XS so that the GUI can highlight what to inspect/fix.
        # Both bounding box matching AND actual geometry intersection tests because geometries may not be identical after schematization.
        if user_index is not None and user_layer is not None:
            for feat in feats:
                if feat.id() not in conflict_schema_fids:
                    continue # Only need to check conflicting schematized IDs

                geom = feat.geometry()
                if not geom or geom.isEmpty():
                    continue

                # Find possible intersect candidates
                cand_user_ids = user_index.intersects(geom.boundingBox())
                for uid in cand_user_ids:
                    user_feat = next(user_layer.getFeatures(QgsFeatureRequest(uid)), None)
                    if user_feat is None:
                        continue
                    user_geom = user_feat.geometry()
                    if not user_geom or user_geom.isEmpty():
                        continue

                    # If they intersect at all,consider this user XS "conflicting" for highlighting.
                    if user_geom.intersects(geom) or user_geom.touches(geom):
                        conflict_user_fids.add(uid)

        # Convert conflicting schematized FIDs to readable form for logging
        ids_str = ", ".join(str(fid) for fid in sorted(conflict_schema_fids))

        self.uc.bar_error("Schematization cancelled: one or more schematized floodplain cross-sections cross or touch each other.")
        self.uc.log_info("Schematization rolled back. Cross/touch conflicts in schematized FIDs: " + ids_str)

        # Completely clear schematized results to avoid retaining an invalid partial result set.
        try:
            if self.gutils is not None:
                self.gutils.clear_tables("fpxsec", "fpxsec_cells")
        except Exception:
            pass

        # Refresh layers so the user sees that everything was rolled back
        try:
            if self.lyrs is not None:
                self.lyrs.clear_rubber()

                # Refresh line layer
                if "fpxsec" in self.lyrs.data and self.lyrs.data["fpxsec"]["qlyr"]:
                    self.lyrs.data["fpxsec"]["qlyr"].triggerRepaint()

                # Refresh cell layer
                if "fpxsec_cells" in self.lyrs.data and self.lyrs.data["fpxsec_cells"]["qlyr"]:
                    self.lyrs.data["fpxsec_cells"]["qlyr"].triggerRepaint()
        except Exception:
            pass

        # Finally highlight original (user drawn) XS that let to the conflict(s)
        try:
            if conflict_user_fids and user_layer is not None:
                user_layer.removeSelection() # Clear any existing selection,
                user_layer.selectByIds(list(conflict_user_fids)) # then select the conflicting ones

                # Draw rubberbands on top of the conflicting us XS
                if self.lyrs is not None:
                    self.lyrs.clear_rubber()  # Clear any existing rubberbands first
                    for uid in conflict_user_fids:
                        self.lyrs.show_feat_rubber(user_layer.id(), uid)  # Add a rubberband for each conflicting user XS
        except Exception:
            pass

        return False # Validation failed

    def schematize_fpxs(self):
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool!")
            self.uc.log_info("There is no grid! Please create it before running tool!")
            return

        try:
            if self.lyrs.any_lyr_in_edit("user_fpxsec"):
                self.save_fpxs_lyr_edits()
                self.add_user_fpxs_btn.setChecked(False)
            fpxs = FloodplainXS(self.con, self.iface, self.lyrs)
            fpxs.schematize_floodplain_xs()

            if not self.validate_schematized_fpxs():
                return

        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn(
                "WARNING 060319.1705: Process failed on schematizing floodplain cross-sections! "
                "Please check your User Layers."
            )
            return
        self.uc.bar_info("Floodplain cross-sections schematized!")
        self.uc.log_info("Floodplain cross-sections schematized!")

    def delete_schema_fpxs(self):
        """
        Function to delete the floodplain cross-section schematized data
        """
        if self.gutils.is_table_empty("fpxsec") and self.gutils.is_table_empty("fpxsec_cells"):
            self.uc.bar_warn("There is no schematized floodplain cross sections!")
            self.uc.log_info("There is no schematized floodplain cross sections!")
            return

        self.gutils.clear_tables("fpxsec", "fpxsec_cells")

        self.uc.bar_info("Schematized floodplain cross sections deleted!")
        self.uc.log_info("Schematized floodplain cross sections deleted!")

        self.lyrs.clear_rubber()
        self.lyrs.data["fpxsec"]["qlyr"].triggerRepaint()
        self.lyrs.data["fpxsec_cells"]["qlyr"].triggerRepaint()

        self.fill_iflo_directions()

    def set_report(self):
        if self.report_chbox.isChecked():
            self.gutils.set_cont_par("NXPRT", "1")
        else:
            self.gutils.set_cont_par("NXPRT", "0")

    def show_hydrograph(self, table, fid, extra):
        """
        Function to load the hydrograph and flododplain hydraulics from HYCROSS.OUT
        """
        self.uc.clear_bar_messages()
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            self.uc.log_info("There is no grid! Please create it before running tool.")
            return False

        units = "CMS" if self.gutils.get_cont_par("METRIC") == "1" else "CFS"

        s = QSettings()

        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            processed_results_file = self.gutils.get_cont_par("SCENARIOS_RESULTS")
            use_prs = self.gutils.get_cont_par("USE_SCENARIOS")

            xs_no = fid

            if use_prs == '1' and os.path.exists(processed_results_file):
                dict_df = hycross_dataframe_from_hdf5_scenarios(processed_results_file, xs_no) # Replace fid with xs_no
                if not dict_df:
                    self.uc.bar_warn("No scenario results found for this floodplain cross-section. The project and the results file may be out of sync.")
                    self.uc.log_info("No scenario results found for this floodplain cross-section. The project and the results file may be out of sync.")

                # Clear the plots
                self.plot.clear()
                if self.plot.plot.legend is not None:
                    plot_scene = self.plot.plot.legend.scene()
                    if plot_scene is not None:
                        plot_scene.removeItem(self.plot.plot.legend)

                # Set up legend and plot title
                self.plot.plot.legend = None
                self.plot.plot.addLegend(offset=(0, 30))
                self.plot.plot.setTitle(title=f"Floodplain XS - {fid}")
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
                    self.plot.add_item(f"{key} - Discharge ({self.system_units[units][2]}) ",
                                       [value['Time'], value['Discharge']],
                                       col=SCENARIO_COLOURS[i], sty=SCENARIO_STYLES[0])
                    self.plot.add_item(f"{key} - Velocity ({self.system_units[units][1]})",
                                       [value['Time'], value['Velocity']],
                                       col=SCENARIO_COLOURS[i], sty=SCENARIO_STYLES[1], hide=True)
                    self.plot.add_item(f"{key} - WSE ({self.system_units[units][0]})",
                                       [value['Time'], value['WSE']],
                                       col=SCENARIO_COLOURS[i], sty=SCENARIO_STYLES[2], hide=True)
                    self.plot.add_item(f"{key} - Ave. Depth ({self.system_units[units][0]}) ",
                                       [value['Time'], value['Ave. Depth']],
                                       col=SCENARIO_COLOURS[i], sty=SCENARIO_STYLES[3], hide=True)
                    self.plot.add_item(f"{key} - Flow Width ({self.system_units[units][0]})",
                                       [value['Time'], value['Flow Width']],
                                       col=SCENARIO_COLOURS[i], sty=SCENARIO_STYLES[4], hide=True)

                    headers.extend([
                        f"{key} - Discharge ({self.system_units[units][2]})",
                        f"{key} - Velocity ({self.system_units[units][1]})",
                        f"{key} - WSE ({self.system_units[units][0]})",
                        f"{key} - Ave. Depth ({self.system_units[units][0]})",
                        f"{key} - Flow Width ({self.system_units[units][0]})"
                    ])
                    data_model.setHorizontalHeaderLabels(headers)

                    for row_idx, row in enumerate(value):
                        if i == 0:
                            data_model.setItem(row_idx, 0,
                                               StandardItem("{:.2f}".format(row[0]) if row[0] is not None else ""))
                        data_model.setItem(row_idx, 1 + i * 5,
                                           StandardItem("{:.2f}".format(row[5]) if row[5] is not None else ""))
                        data_model.setItem(row_idx, 2 + i * 5,
                                           StandardItem("{:.2f}".format(row[4]) if row[4] is not None else ""))
                        data_model.setItem(row_idx, 3 + i * 5,
                                           StandardItem("{:.2f}".format(row[3]) if row[3] is not None else ""))
                        data_model.setItem(row_idx, 4 + i * 5,
                                           StandardItem("{:.2f}".format(row[2]) if row[2] is not None else ""))
                        data_model.setItem(row_idx, 5 + i * 5,
                                           StandardItem("{:.2f}".format(row[1]) if row[1] is not None else ""))
            else:

                GDS_dir = s.value("FLO-2D/lastGdsDir", "")
                if extra == "HYCROSS":
                    HYCROSS_file = s.value("FLO-2D/lastHYCROSSFile", "")
                    CROSSMAX_file = GDS_dir + r"/CROSSMAX.OUT"
                    if not os.path.isfile(HYCROSS_file):
                        HYCROSS_file = GDS_dir + r"/HYCROSS.OUT"

                    # Check if there is an HYCROSS.OUT file on the export folder
                    if os.path.isfile(HYCROSS_file):
                        # Check if the HYCROSS.OUT has data on it
                        if os.path.getsize(HYCROSS_file) == 0:
                            self.uc.bar_warn("No HYCROSS.OUT file found. Please ensure the simulation has completed and verify the project export folder.")
                            self.uc.log_info("No HYCROSS.OUT file found. Please ensure the simulation has completed and verify the project export folder.")
                            return
                        else:
                            self.uc.bar_info("Reading floodplain cross section results from HYCROSS.OUT!")
                            self.uc.log_info("Reading floodplain cross section results from HYCROSS.OUT!")
                            time_list, discharge_list, flow_width_list, wse_list = self.process_hycross(
                                HYCROSS_file, CROSSMAX_file, xs_no)
                            if not time_list:
                                self.uc.bar_error("Unable to read Floodplain Cross Section data!")
                                self.uc.log_info("Unable to read Floodplain Cross Section data!")
                                return
                    else:
                        self.uc.bar_warn(
                            "No HYCROSS.OUT file found. Please ensure the simulation has completed and verify the project export folder.")
                        self.uc.log_info(
                            "No HYCROSS.OUT file found. Please ensure the simulation has completed and verify the project export folder.")
                        return

                if extra == "TIMDEPFPXSEC":
                    TIMDEPFPXSEC_file = GDS_dir + r"/TIMDEPFPXSEC.HDF5"

                    if os.path.isfile(TIMDEPFPXSEC_file):
                        # Check if the TIMDEPFPXSEC.HDF5 has data on it
                        if os.path.getsize(TIMDEPFPXSEC_file) == 0:
                            self.uc.bar_error("Unable to read Floodplain Cross Section data!")
                            self.uc.log_info("Unable to read Floodplain Cross Section data!")
                            return
                        else:
                            self.uc.bar_info("Reading floodplain cross section results from TIMDEPFPXSEC.HDF5!")
                            self.uc.log_info("Reading floodplain cross section results from TIMDEPFPXSEC.HDF5!")
                            time_list, discharge_list, flow_width_list, wse_list = self.process_timdepfpxsec(
                                TIMDEPFPXSEC_file, fid)
                            if not time_list:
                                self.uc.bar_warn(
                                    "No TIMDEPFPXSEC.HDF5 file found. Please ensure the simulation has completed and verify the project export folder.")
                                self.uc.log_info(
                                    "No TIMDEPFPXSEC.HDF5 file found. Please ensure the simulation has completed and verify the project export folder.")
                                return
                    else:
                        self.uc.bar_warn(
                            "No TIMDEPFPXSEC.HDF5 file found. Please ensure the simulation has completed and verify the project export folder.")
                        self.uc.log_info(
                            "No TIMDEPFPXSEC.HDF5 file found. Please ensure the simulation has completed and verify the project export folder.")
                        return

                self.plot.clear()
                if self.plot.plot.legend is not None:
                    plot_scene = self.plot.plot.legend.scene()
                    if plot_scene is not None:
                        plot_scene.removeItem(self.plot.plot.legend)

                self.plot.plot.legend = None
                self.plot.plot.addLegend(offset=(0, 30))
                self.plot.plot.setTitle(title=f"Floodplain Cross Section - {fid}")
                self.plot.plot.setLabel("bottom", text="Time (hrs)")
                self.plot.plot.setLabel("left", text="")
                self.plot.add_item(f"Discharge ({self.system_units[units][2]})", [time_list, discharge_list], col=QColor(Qt.darkYellow), sty=Qt.SolidLine)
                self.plot.add_item(f"Flow Width ({self.system_units[units][0]})", [time_list, flow_width_list], col=QColor(Qt.black), sty=Qt.SolidLine, hide=True)
                self.plot.add_item(f"Water Surface Elevation ({self.system_units[units][0]})", [time_list, wse_list], col=QColor(Qt.darkGreen), sty=Qt.SolidLine, hide=True)

                try:  # Build table.
                    discharge_data_model = StandardItemModel()
                    self.tview.undoStack.clear()
                    self.tview.setModel(discharge_data_model)
                    discharge_data_model.clear()
                    headers = ["Time (hours)",
                                f"Discharge ({self.system_units[units][2]})",
                                f"Flow Width ({self.system_units[units][0]})",
                                f"Water Surface Elevation ({self.system_units[units][0]})"]
                    discharge_data_model.setHorizontalHeaderLabels(headers)

                    data = zip(time_list, discharge_list, flow_width_list, wse_list)
                    for row, (time, discharge, flow, wse) in enumerate(data):
                        time_item = StandardItem("{:.2f}".format(time)) if time is not None else StandardItem("")
                        discharge_item = StandardItem("{:.2f}".format(discharge)) if discharge is not None else StandardItem("")
                        flow_item = StandardItem("{:.2f}".format(flow)) if flow is not None else StandardItem("")
                        wse_item = StandardItem("{:.2f}".format(wse)) if wse is not None else StandardItem("")
                        discharge_data_model.setItem(row, 0, time_item)
                        discharge_data_model.setItem(row, 1, discharge_item)
                        discharge_data_model.setItem(row, 2, flow_item)
                        discharge_data_model.setItem(row, 3, wse_item)

                    self.tview.horizontalHeader().setStretchLastSection(True)
                    for col in range(3):
                        self.tview.setColumnWidth(col, 100)
                    for i in range(discharge_data_model.rowCount()):
                        self.tview.setRowHeight(i, 20)
                except:
                    QApplication.restoreOverrideCursor()
                    self.uc.bar_error("Error while building table for floodplain cross section!")
                    self.uc.log_info("Error while building table for floodplain cross section!")
                    return

        except Exception as e:
            self.uc.bar_error("Error while building the plots! Check if the number of floodplain cross sections are consistent with HYCROSS.OUT or scenarios data.")
            self.uc.log_info("Error while building the plots! Check if the number of floodplain cross sections are consistent with HYCROSS.OUT or scenarios data.")
        finally:
            QApplication.restoreOverrideCursor()

    def show_cells_hydrograph(self, table, fid):
        """
        Function to load the floodplain cells hydrograph from CROSSQ.OUT
        """
        self.uc.clear_bar_messages()
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            self.uc.log_info("There is no grid! Please create it before running tool.")
            return False

        units = "CMS" if self.gutils.get_cont_par("METRIC") == "1" else "CFS"

        s = QSettings()

        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)

            grid_fid = self.gutils.execute(f"SELECT grid_fid FROM fpxsec_cells WHERE fid = '{fid}'").fetchone()[0]

            self.plot.clear()
            if self.plot.plot.legend is not None:
                plot_scene = self.plot.plot.legend.scene()
                if plot_scene is not None:
                    plot_scene.removeItem(self.plot.plot.legend)

            self.plot.plot.legend = None
            self.plot.plot.addLegend(offset=(0, 30))
            self.plot.plot.setTitle(title=f"Floodplain Cell - {grid_fid}")
            self.plot.plot.setLabel("bottom", text="Time (hrs)")
            self.plot.plot.setLabel("left", text="")

            discharge_data_model = StandardItemModel()
            self.tview.undoStack.clear()
            self.tview.setModel(discharge_data_model)
            discharge_data_model.clear()

            processed_results_file = self.gutils.get_cont_par("SCENARIOS_RESULTS")
            use_prs = self.gutils.get_cont_par("USE_SCENARIOS")

            if use_prs == '1' and os.path.exists(processed_results_file):
                dict_df = crossq_dataframe_from_hdf5_scenarios(processed_results_file, grid_fid)
                headers = ["Time (hours)"]

                for i, (scenario, dataset_dict) in enumerate(dict_df.items(), start=0):

                    discharge = dataset_dict[1]
                    time_series = dataset_dict[0]

                    min_len = min(len(time_series), len(discharge))
                    time_series = time_series[:min_len]
                    discharge = discharge[:min_len]

                    if i == 0:
                        self.plot.add_item(f"{scenario} - Discharge ({self.system_units[units][2]})",
                                           [time_series, discharge],
                                           col=SCENARIO_COLOURS[i], sty=SCENARIO_STYLES[0])
                    else:
                        self.plot.add_item(f"{scenario} - Discharge ({self.system_units[units][2]})",
                                           [time_series, discharge],
                                           col=SCENARIO_COLOURS[i], sty=SCENARIO_STYLES[0], hide=True)

                    headers.extend([f"{scenario} - Discharge ({self.system_units[units][2]})"])
                    discharge_data_model.setHorizontalHeaderLabels(headers)

                    data = zip(time_series, discharge)

                    for row_idx, (time, disch) in enumerate(data):
                        time_item = StandardItem("{:.2f}".format(time)) if time is not None else StandardItem("")
                        discharge_item = StandardItem("{:.2f}".format(disch)) if disch is not None else StandardItem("")
                        if i == 0:
                            discharge_data_model.setItem(row_idx, 0,time_item)
                        discharge_data_model.setItem(row_idx, 1 + i * 1, discharge_item)

            else:

                CROSSQ_file = s.value("FLO-2D/lastCROSSQFile", "")
                GDS_dir = s.value("FLO-2D/lastGdsDir", "")
                # Check if there is a CROSSQ.OUT file on the FLO-2D QSettings
                if not os.path.isfile(CROSSQ_file):
                    CROSSQ_file = GDS_dir + r"/CROSSQ.OUT"
                    # Check if there is a CROSSQ.OUT file on the export folder
                    if not os.path.isfile(CROSSQ_file):
                        self.uc.bar_warn(
                            "No CROSSQ.OUT file found. Please ensure the simulation has completed and verify the project export folder.")
                        self.uc.log_info(
                            "No CROSSQ.OUT file found. Please ensure the simulation has completed and verify the project export folder.")
                        return
                # Check if the CROSSQ.OUT has data on it
                if os.path.getsize(CROSSQ_file) == 0:
                    QApplication.restoreOverrideCursor()
                    self.uc.bar_warn("File  '" + os.path.basename(CROSSQ_file) + "'  is empty!")
                    self.uc.log_info("File  '" + os.path.basename(CROSSQ_file) + "'  is empty!")
                    return

                with open(CROSSQ_file, "r") as myfile:
                    while True:
                        time_list = []
                        discharge_list = []
                        line = next(myfile)
                        if len(line.split()) == 3 and line.split()[0] == str(grid_fid):
                            time_list.append(float(line.split()[1]))
                            discharge_list.append(float(line.split()[2]))
                            while True:
                                try:
                                    line = next(myfile)
                                    if len(line.split()) == 3:
                                        break
                                    time_list.append(float(line.split()[0]))
                                    discharge_list.append(float(line.split()[1]))
                                except StopIteration:
                                    break
                            break

                self.plot.add_item(f"Discharge ({self.system_units[units][2]})", [time_list, discharge_list], col=QColor(Qt.darkYellow), sty=Qt.SolidLine)

                try:  # Build table.
                    discharge_data_model.setHorizontalHeaderLabels(["Time (hours)",
                                                                    f"Discharge ({self.system_units[units][2]})"])

                    data = zip(time_list, discharge_list)
                    for time, discharge in data:
                        time_item = StandardItem("{:.2f}".format(time)) if time is not None else StandardItem("")
                        discharge_item = StandardItem("{:.2f}".format(discharge)) if discharge is not None else StandardItem("")
                        discharge_data_model.appendRow([time_item, discharge_item])

                except:
                    QApplication.restoreOverrideCursor()
                    self.uc.bar_error("Error while building table for floodplain cells!")
                    self.uc.log_info("Error while building table for floodplain cells!")
                    return

            self.tview.horizontalHeader().setStretchLastSection(True)
            for col in range(discharge_data_model.columnCount()):
                self.tview.setColumnWidth(col, 150)
            for i in range(discharge_data_model.rowCount()):
                self.tview.setRowHeight(i, 20)
            return
        except Exception as e:
            self.uc.bar_error("Error while building the plots!")
            self.uc.log_info("Error while building the plots!")
        finally:
            QApplication.restoreOverrideCursor()

    def fpxs_feature_changed(self, fid):
        """
        Function to set the fpxs_cbo index equal to the feature edited
        """
        try:
            fpxs_name = self.gutils.execute(f"SELECT name FROM user_fpxsec WHERE fid = '{fid}'").fetchone()[0]
            index = self.fpxs_cbo.findText(fpxs_name)
            self.populate_cbos(fid=index)
        except:
            return

    def show_fp_xs_widget_help(self):
        """
        Function to show the fp xs widget help
        """
        QDesktopServices.openUrl(QUrl("https://documentation.flo-2d.com/Build25/flo-2d_plugin/user_manual/widgets/floodplain-cross-section-editor/Floodplain%20Cross%20Section%20Editor.html"))

    def fill_iflo_directions(self):
        """
        Function to fill the iflo directions on the directions combobox
        """
        self.setup_connection()
        self.flow_dir_cbo.clear()
        if self.gutils.is_table_empty("user_fpxsec"):
            return
        parent_dir = os.path.dirname(os.path.abspath(__file__))
        idir = os.path.join(os.path.dirname(parent_dir), "img")
        for i in range(8):
            self.flow_dir_cbo.addItem(str(i + 1))
            icon_file = "arrow_{}.svg".format(i + 1)
            self.flow_dir_cbo.setItemIcon(i, QIcon(os.path.join(idir, icon_file)))

    def get_iflo_direction(self, azimuth):
        """
        Function to get the iflo directions based on the azimuth
        """

        # Ensure azimuth is positive
        if azimuth < 0:
            azimuth += 360

        perp_azimuth = (azimuth + 90) % 360

        if 337.5 <= perp_azimuth or perp_azimuth < 22.5:
            return [1, 3]
        elif 22.5 <= perp_azimuth < 67.5:
            return [5, 7]
        elif 67.5 <= perp_azimuth < 112.5:
            return [2, 4]
        elif 112.5 <= perp_azimuth < 157.5:
            return [6, 8]
        elif 157.5 <= perp_azimuth < 202.5:
            return [3, 1]
        elif 202.5 <= perp_azimuth < 247.5:
            return [7, 5]
        elif 247.5 <= perp_azimuth < 292.5:
            return [4, 2]
        elif 292.5 <= perp_azimuth < 337.5:
            return [8, 6]

    def show_fpxsec_info(self, fid):
        """
        Function to show the floodplain cross-section info: Elevation and Roughness
        """
        try:

            QApplication.setOverrideCursor(Qt.WaitCursor)

            units = "m" if self.gutils.get_cont_par("METRIC") == "1" else "ft"

            self.plot.clear()
            if self.plot.plot.legend is not None:
                plot_scene = self.plot.plot.legend.scene()
                if plot_scene is not None:
                    plot_scene.removeItem(self.plot.plot.legend)

            self.plot.plot.legend = None
            self.plot.plot.addLegend(offset=(0, 30))
            self.plot.plot.setTitle(title=f"Floodplain XS - {fid}")
            self.plot.plot.setLabel("bottom", text=f"Station ({units})")
            self.plot.plot.setLabel("left", text="")

            data_model = StandardItemModel()
            self.tview.undoStack.clear()
            self.tview.setModel(data_model)
            data_model.clear()

            fpxs = FloodplainXS(self.con, self.iface, self.lyrs)
            cell_qry = """SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM grid WHERE fid = ?;"""

            feat_iter = self.schema_fpxsec_lyr.getFeatures(QgsFeatureRequest(fid))
            feature = next(feat_iter, None)
            if feature is not None:
                geom = feature.geometry()
                geom_poly = geom.asPolyline()
                start, end = geom_poly[0], geom_poly[-1]

                # Getting start grid fid and its centroid
                start_gid = fpxs.grid_on_point(start.x(), start.y())
                start_wkt = self.gutils.execute(cell_qry, (start_gid,)).fetchone()[0]
                start_x, start_y = [float(s) for s in start_wkt.strip("POINT()").split()]
                # Finding shift vector between original start point and start grid centroid
                shift = QgsPointXY(start_x, start_y) - start
                # Shifting start and end point of line
                start += shift
                end += shift
                # Calculating and adjusting line angle
                azimuth = start.azimuth(end)
                if azimuth < 0:
                    azimuth += 360
                closest_angle = round(azimuth / 45) * 45
                rotation = closest_angle - azimuth
                end_geom = QgsGeometry.fromPointXY(end)
                end_geom.rotate(rotation, start)
                end_point = end_geom.asPoint()
                # Getting shifted and rotated end grid fid and its centroid
                end_gid = fpxs.grid_on_point(end_point.x(), end_point.y())
                step = fpxs.cell_size if closest_angle % 90 == 0 else fpxs.diagonal
                end_wkt = self.gutils.execute(cell_qry, (end_gid,)).fetchone()[0]
                end_x, end_y = [float(e) for e in end_wkt.strip("POINT()").split()]
                fpxec_line = QgsGeometry.fromPolylineXY([QgsPointXY(start_x, start_y), QgsPointXY(end_x, end_y)])
                sampling_points = tuple(fpxs.interpolate_points(fpxec_line, step))

                elevation_data = []
                roughness_data = []
                step_data = [0]
                cumulative_step = 0
                for _, gid in sampling_points:
                    elevation_data.append(self.gutils.execute("SELECT elevation FROM grid WHERE fid = ?;", (gid,)).fetchone()[0])
                    roughness_data.append(self.gutils.execute("SELECT n_value FROM grid WHERE fid = ?;", (gid,)).fetchone()[0])
                    cumulative_step += step
                    step_data.append(cumulative_step)

                self.plot.add_item(f"Elevation ({units})", [step_data[:-1], elevation_data],
                                   col=QColor(Qt.black), sty=Qt.SolidLine)
                self.plot.add_item(f"Mannings", [step_data[:-1], roughness_data],
                                   col=QColor(Qt.red), sty=Qt.SolidLine, hide=True)

                headers = ["Station", f"Elevation ({units})", f"Mannings"]
                data_model.setHorizontalHeaderLabels(headers)

                data = zip(step_data, elevation_data, roughness_data)
                for row, (step, elev, roughness) in enumerate(data):
                    step_item = StandardItem("{:.2f}".format(step)) if step is not None else StandardItem("")
                    elev_item = StandardItem("{:.2f}".format(elev)) if elev is not None else StandardItem("")
                    roughness_item = StandardItem("{:.2f}".format(roughness)) if roughness is not None else StandardItem("")
                    data_model.setItem(row, 0, step_item)
                    data_model.setItem(row, 1, elev_item)
                    data_model.setItem(row, 2, roughness_item)

        except Exception as e:
            self.uc.bar_error("Error while building the plots!")
            self.uc.log_info("Error while building the plots!")

        finally:
            QApplication.restoreOverrideCursor()

    def process_hycross(self, HYCROSS_file, CROSSMAX_file, xs_no):

        time_list = []
        discharge_list = []
        flow_width_list = []
        wse_list = []

        found = False

        # Parse the CROSSMAX to identify correctly the fp cross section being selected by the user
        crossmax_dict = self.process_crossmax(CROSSMAX_file)

        # Get the grid elements associated with the fp cross section
        grid_elements = self.gutils.execute(f"SELECT grid_fid FROM fpxsec_cells WHERE fpxsec_fid = {xs_no};").fetchall()
        if not grid_elements:
            return None, None, None, None
        grid_fid_list = [g[0] for g in grid_elements]

        for cross_section_no, grid_fids in crossmax_dict.items():
            if sorted(grid_fid_list) == sorted(grid_fids):
                xs_no = cross_section_no
                break

        with open(HYCROSS_file, "r") as myfile:
            while True:
                try:
                    line = next(myfile)
                except StopIteration:
                    # Reached EOF without finding the section
                    return None, None, None, None

                if "THE MAXIMUM DISCHARGE FROM CROSS SECTION" in line:
                    parts = line.split()

                    if len(parts) <= 6:
                        return None, None, None, None

                    if parts[6] == str(xs_no):
                        found = True

                        # Skip header block
                        for _ in range(9):
                            try:
                                line = next(myfile)
                            except StopIteration:
                                return None, None, None, None

                        # Read table
                        while True:
                            try:
                                line = next(myfile)
                            except StopIteration:
                                break  # EOF ends table

                            if not line.strip():
                                break

                            parts = line.split()

                            # If this line starts with the string "VELOCITY", it is a channel cross section
                            if parts and parts[0] == "VELOCITY":
                                for _ in range(5):
                                    try:
                                        line = next(myfile)
                                    except StopIteration:
                                        return None, None, None, None
                                parts = line.split()

                            # Need at least 6 columns: time, width, depth, wse, velocity, discharge
                            if len(parts) < 6:
                                return None, None, None, None

                            time_list.append(float(parts[0]))
                            discharge_list.append(float(parts[5]))
                            flow_width_list.append(float(parts[1]))
                            wse_list.append(float(parts[3]))

                        break  # stop scanning file once xs_no block is processed

        # If xs section wasn't found, or found but no data rows parsed, return None tuple
        if (not found) or (not time_list):
            return None, None, None, None

        return time_list, discharge_list, flow_width_list, wse_list

    def process_crossmax(self, CROSSMAX_file):
        """
        Parse CROSSMAX.OUT and return a dictionary
        with {cross_section_no: [node1, node2, ...]}.
        """

        xs_nodes = defaultdict(list)
        current_xs = None

        # Regular expression to capture cross section number
        xs_pattern = re.compile(r"FROM CROSS SECTION\s+(\d+)")
        # Regular expression to capture node id
        node_pattern = re.compile(r"FROM NODE\s+(\d+)")

        with open(CROSSMAX_file, "r", errors="ignore") as f:
            for line in f:

                # ---- Check for new cross section header ----
                xs_match = xs_pattern.search(line)
                if xs_match:
                    current_xs = int(xs_match.group(1))
                    # Ensure key exists
                    if current_xs not in xs_nodes:
                        xs_nodes[current_xs] = []
                    continue

                # ---- Check for node line ----
                node_match = node_pattern.search(line)
                if node_match and current_xs is not None:
                    node_id = int(node_match.group(1))
                    xs_nodes[current_xs].append(node_id)

        return dict(xs_nodes)

    def process_timdepfpxsec(self, TIMDEPFPXSEC_file, fid):

        grid_fids = self.gutils.execute(
            f"SELECT grid_fid FROM fpxsec_cells WHERE fpxsec_fid = {fid} ORDER BY grid_fid"
        ).fetchall()
        if not grid_fids:
            return [], [], [], []

        row = self.gutils.execute(f"SELECT iflo FROM fpxsec WHERE fid = {fid}").fetchone()
        if not row:
            return [], [], [], []
        iflo = int(row[0])

        path = os.path.join(os.path.dirname(TIMDEPFPXSEC_file), "NEIGHBORS.DAT")
        if not os.path.isfile(path):
            return [], [], [], []

        neighbors_list = []
        with open(path, "rb") as f:
            while True:
                len_bytes = f.read(4)
                if not len_bytes:
                    break
                reclen = struct.unpack("<i", len_bytes)[0]
                rec = f.read(reclen)
                endlen = struct.unpack("<i", f.read(4))[0]
                if endlen != reclen:
                    return [], [], [], []
                neighbors_list.append(struct.unpack("<8i", rec))

        neighbors = np.zeros((len(neighbors_list) + 1, 8), dtype=np.int32)
        neighbors[1:, :] = np.array(neighbors_list, dtype=np.int32)

        available_directions = {
            1: [1, 5, 8],
            2: [2, 5, 6],
            3: [3, 6, 7],
            4: [4, 7, 8],
            5: [5, 1, 2],
            6: [6, 2, 3],
            7: [7, 3, 4],
            8: [8, 4, 1],
        }

        directions = available_directions.get(iflo, [])

        cols0 = np.array([int(g[0]) - 1 for g in grid_fids], dtype=np.int64)  # 0-based
        cols1 = cols0 + 1  # 1-based, for neighbors lookup

        with h5py.File(TIMDEPFPXSEC_file, "r") as f:

            timtep_time = f["/TIMTEP_TIME/TTIMTEFPXSEC"][:].tolist()

            qfpn_1 = f[f"/AvgFlow_8directions/AvgQFPN{directions[0]}"]
            qfpn_2 = f[f"/AvgFlow_8directions/AvgQFPN{directions[1]}"]
            qfpn_3 = f[f"/AvgFlow_8directions/AvgQFPN{directions[2]}"]

            q1_xs = qfpn_1[cols0, :]
            q2_xs = qfpn_2[cols0, :]
            q3_xs = qfpn_3[cols0, :]

            qt_xs = q1_xs + q2_xs + q3_xs

            # Extra diagonal neighbor term only for IFLO 5..8 (diagonals)
            if iflo in (5, 6, 7, 8):
                # neighbors[JJ] = [N,E,S,W,NE,SE,SW,NW]
                # IFLO=5: NQ = IFPNQ(JJ,3) -> S neighbor
                # IFLO=6: NQ = IFPNQ(JJ,4) -> W neighbor
                # IFLO=7: NQ = IFPNQ(JJ,2) -> E neighbor
                # IFLO=8: NQ = IFPNQ(JJ,3) -> S neighbor
                if iflo == 5:
                    nq = neighbors[cols1, 2]  # S
                elif iflo == 6:
                    nq = neighbors[cols1, 3]  # W
                elif iflo == 7:
                    nq = neighbors[cols1, 1]  # E
                else:  # iflo == 8
                    nq = neighbors[cols1, 2]  # S

                mask = nq > 0
                if np.any(mask):
                    nq0 = (nq[mask] - 1).astype(np.int64)  # convert to 0-based HDF5 rows
                    q_diag_nq = f[f"/AvgFlow_8directions/AvgQFPN{directions[0]}"][nq0, :]
                    qt_xs[mask, :] = qt_xs[mask, :] + q_diag_nq

        qstot = qt_xs.sum(axis=0)

        n_steps = qstot.shape[0] + 1

        time_list = [0.0] + timtep_time
        discharge_list = [0.0] + qstot.tolist()
        flow_width_list = [0.0] * n_steps
        wse_list = [0.0] * n_steps

        return time_list, discharge_list, flow_width_list, wse_list

