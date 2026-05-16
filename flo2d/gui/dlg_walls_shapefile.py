# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import datetime

from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsProject,
    QgsWkbTypes,
    QgsFieldProxyModel,
)
from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import QApplication, QComboBox, QDialogButtonBox
from qgis.gui import QgsFieldComboBox

from ..geopackage_utils import GeoPackageUtils, extractPoints
from ..user_communication import UserCommunication
from ..utils import float_or_zero, qt_cursor_shape, qdialogbuttonbox_button, qt_window_flag
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("walls_shapefile")


class WallsShapefile(qtBaseClass, uiDialog):
    def __init__(self, con, iface, layers):
        qtBaseClass.__init__(self, iface.mainWindow())
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = layers
        self.setupUi(self)
        self.setWindowFlags(qt_window_flag("Dialog") | qt_window_flag("Tool"))
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = con
        self.gutils = GeoPackageUtils(con, iface)
        self.user_levee_lines_lyr = self.lyrs.data["user_levee_lines"]["qlyr"]
        self.levee_failure_lyr = self.lyrs.data["levee_failure"]["qlyr"]
        self.current_user_lines = self.user_levee_lines_lyr.featureCount()
        self.current_lyr = None
        self.saveSelected = None

        # try to get grid layer
        self.grid_lyr = self.lyrs.data["grid"]["qlyr"]

        self.walls_to_levees_buttonbox.button(qdialogbuttonbox_button("Save")).setText("Add Walls to User Levee Lines")
        self.walls_shapefile_cbo.currentIndexChanged.connect(self.populate_walls_attributes)

        # Connections to clear inlets fields.
        self.clear_crest_elevation_btn.clicked.connect(self.clear_crest_elevation)
        self.clear_name_btn.clicked.connect(self.clear_name)
        self.clear_correction_btn.clicked.connect(self.clear_correction)
        self.clear_failure_height_btn.clicked.connect(self.clear_failure_height)
        self.clear_duration_btn.clicked.connect(self.clear_duration)
        self.clear_base_elevation_btn.clicked.connect(self.clear_base_elevation)
        self.clear_maximum_width_btn.clicked.connect(self.clear_maximum_width)
        self.clear_vertical_fail_rate_btn.clicked.connect(self.clear_vertical_fail_rate)
        self.clear_horizontal_fail_rate_btn.clicked.connect(self.clear_horizontal_fail_rate)

        self.clear_all_walls_attributes_btn.clicked.connect(self.clear_all_walls_attributes)

        self.setup_layers_comboxes()

        self.restore_wall_shapefile_field_names()

        if self.gutils.is_table_empty("user_levee_lines"):
            self.levees_append_chbox.setVisible(False)
            self.ask_append = False
        else:
            self.levees_append_chbox.setVisible(True)
            self.ask_append = True

        self.fail_elev_radio.toggled.connect(lambda checked: self.smart_assign_walls() if checked else None)
        self.fail_depth_radio.toggled.connect(lambda checked: self.smart_assign_walls() if checked else None)

    # Read previously saved field name from QGIS settings
    def restore_field_name(self, setting_name, field_names):
        s = QSettings()
        field_name = "" if s.value(setting_name) is None else s.value(setting_name)

        if field_name in field_names:
            return field_name
        else:
            return ""

    # Substring matching
    def find_best_field_match(self,combo, preferred_names, excluded_names=None):
        if excluded_names is None:
            excluded_names = []

        def clean(text):
            return text.lower().replace("_", "").replace("-", "").replace(" ", "") # Normalize field names

        preferred_names = [clean(name) for name in preferred_names]
        excluded_names = [clean(name) for name in excluded_names]

        for i in range(combo.count()):
            item_text = combo.itemText(i)
            clean_item = clean(item_text)

            if any(excluded in clean_item for excluded in excluded_names):
                continue
            if any(preferred in clean_item for preferred in preferred_names):
                return i
        return -1

    # Decide whether to restore saved field names or run smart asignment
    def restore_wall_shapefile_field_names(self):
        s=QSettings()

        layer = "" if s.value("sf_walls_layer_name") is None else s.value("sf_walls_layer_name")

        if layer != "":
            if layer == self.walls_shapefile_cbo.currentText():
                lyr = self.lyrs.get_layer_by_name(layer).layer()
                field_names = [field.name() for field in lyr.fields()]

                self.crest_elevation_FieldCbo.setField(self.restore_field_name("sf_walls_crest_elevation_name", field_names))
                self.name_FieldCbo.setField(self.restore_field_name("sf_walls_name_name", field_names))
                self.correction_FieldCbo.setField(self.restore_field_name("sf_walls_correction_name", field_names))
                self.failure_height_FieldCbo.setField(self.restore_field_name("sf_walls_failure_height_name", field_names))
                self.duration_FieldCbo.setField(self.restore_field_name("sf_walls_duration_name", field_names))
                self.base_elevation_FieldCbo.setField(self.restore_field_name("sf_walls_base_elevation_name", field_names))
                self.maximum_width_FieldCbo.setField(self.restore_field_name("sf_walls_maximum_width_name", field_names))
                self.vertical_fail_rate_FieldCbo.setField(self.restore_field_name("sf_walls_vertical_fail_rate_name", field_names))
                self.horizontal_fail_rate_FieldCbo.setField(self.restore_field_name("sf_walls_horizontal_fail_rate_name", field_names))
            else:
                self.smart_assign_walls()

        elif self.walls_shapefile_cbo.currentText() != "":
            self.smart_assign_walls()
        else:
            self.clear_all_walls_attributes()

    # Assign
    def smart_assign_walls(self):
        try:
            self.clear_all_walls_attributes()

            self.name_FieldCbo.setCurrentIndex(self.find_best_field_match(self.name_FieldCbo, ["name"]))

            self.crest_elevation_FieldCbo.setCurrentIndex(
                self.find_best_field_match(
                    self.crest_elevation_FieldCbo,
                    ["elev", "crest_elev", "crestelev"],
                    ["failelev", "fail", "baseelev", "base", "nullelev", "null"]
                )
            )

            self.correction_FieldCbo.setCurrentIndex(
                self.find_best_field_match(
                    self.correction_FieldCbo,
                    ["correction", "corr"]
                )
            )

            if self.fail_elev_radio.isChecked():
                self.failure_height_FieldCbo.setCurrentIndex(
                    self.find_best_field_match(
                        self.failure_height_FieldCbo,
                        ["failelev", "fail_elev", "failureelev"],
                        ["faildepth", "depth"]
                    )
                )
            else:
                self.failure_height_FieldCbo.setCurrentIndex(
                    self.find_best_field_match(
                        self.failure_height_FieldCbo,
                        ["faildepth", "fail_depth", "failuredepth"],
                        ["failelev", "elev"]
                    )
                )

            self.duration_FieldCbo.setCurrentIndex(self.find_best_field_match(self.duration_FieldCbo, ["duration", "failduration"]))

            self.base_elevation_FieldCbo.setCurrentIndex(
                self.find_best_field_match(
                    self.base_elevation_FieldCbo,
                    ["baseelev", "base_elev", "baseelevation"],
                    ["failelev", "fail"]
                )
            )

            self.maximum_width_FieldCbo.setCurrentIndex(self.find_best_field_match(self.maximum_width_FieldCbo, ["maxwidth", "max_width", "maximumwidth"]))

            self.vertical_fail_rate_FieldCbo.setCurrentIndex(self.find_best_field_match(self.vertical_fail_rate_FieldCbo, ["failratev", "vertical", "vrate"]))

            self.horizontal_fail_rate_FieldCbo.setCurrentIndex(
                self.find_best_field_match(self.horizontal_fail_rate_FieldCbo, ["failrateh", "horizontal", "hrate"])
            )

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR: Smart wall field assignment failed!"
                + "\n__________________________________________________",
                e,
            )


    def setup_layers_comboxes(self):
        try:
            self.walls_shapefile_cbo.blockSignals(True)
            lyrs = self.lyrs.list_group_vlayers()
            for l in lyrs:
                if l.geometryType() == QgsWkbTypes.LineGeometry:
                    l.reload()
                    if l.featureCount() > 0:
                        self.walls_shapefile_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                else:
                    pass

            s = QSettings()
            previous_wall = "" if s.value("sf_walls_layer_name") is None else s.value("sf_walls_layer_name")
            idx = self.walls_shapefile_cbo.findText(previous_wall)
            if idx != -1:
                self.walls_shapefile_cbo.setCurrentIndex(idx)
            elif self.walls_shapefile_cbo.count() > 0:
                self.walls_shapefile_cbo.setCurrentIndex(0)

            self.walls_shapefile_cbo.blockSignals(False)

            if self.walls_shapefile_cbo.currentIndex() != -1:
                self.populate_walls_attributes(self.walls_shapefile_cbo.currentIndex())

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 051218.1146: couldn't load point or/and line layers!"
                + "\n__________________________________________________",
                e,
            )

        finally:
            self.walls_shapefile_cbo.blockSignals(False)

    def populate_walls_attributes(self, idx):
        try:
            uri = self.walls_shapefile_cbo.itemData(idx)
            lyr_id = self.lyrs.layer_exists_in_group(uri)
            self.current_lyr = self.lyrs.get_layer_by_id(lyr_id)

            # List of combo boxes that should be filtered to string fields
            string_combos = [
                self.walls_fields_groupBox.findChild(QgsFieldComboBox, "name_FieldCbo")
            ]

            # List of combo boxes that should be filtered to numeric fields
            numeric_combos = [
                self.walls_fields_groupBox.findChild(QgsFieldComboBox, "crest_elevation_FieldCbo"),
                self.walls_fields_groupBox.findChild(QgsFieldComboBox, "correction_FieldCbo"),
                self.walls_fields_groupBox.findChild(QgsFieldComboBox, "failure_height_FieldCbo"),
                self.walls_fields_groupBox.findChild(QgsFieldComboBox, "duration_FieldCbo"),
                self.walls_fields_groupBox.findChild(QgsFieldComboBox, "base_elevation_FieldCbo"),
                self.walls_fields_groupBox.findChild(QgsFieldComboBox, "maximum_width_FieldCbo"),
                self.walls_fields_groupBox.findChild(QgsFieldComboBox, "vertical_fail_rate_FieldCbo"),
                self.walls_fields_groupBox.findChild(QgsFieldComboBox, "horizontal_fail_rate_FieldCbo"),
            ]

            # Remove any None values in case the UI object name changes later.
            string_combos = [combo for combo in string_combos if combo is not None]
            numeric_combos = [combo for combo in numeric_combos if combo is not None]

            for combo in string_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.String)  # Only show string fields

            for combo in numeric_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.Numeric)  # Only show numeric fields

            nFeatures = self.current_lyr.featureCount()
            self.walls_fields_groupBox.setTitle(
                "Walls Fields Selection (from '"
                + self.walls_shapefile_cbo.currentText()
                + "' layer with "
                + str(nFeatures)
                + " features (lines))"
            )

            self.restore_wall_shapefile_field_names()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 051218.0559:  there are not defined or visible point layers to select inlets/junctions components!"
                + "\n__________________________________________________",
                e,
            )

    # Clear wall fields:
    def clear_crest_elevation(self):
        self.crest_elevation_FieldCbo.setCurrentIndex(-1)

    def clear_name(self):
        self.name_FieldCbo.setCurrentIndex(-1)

    def clear_correction(self):
        self.correction_FieldCbo.setCurrentIndex(-1)

    def clear_failure_height(self):
        self.failure_height_FieldCbo.setCurrentIndex(-1)

    def clear_duration(self):
        self.duration_FieldCbo.setCurrentIndex(-1)

    def clear_base_elevation(self):
        self.base_elevation_FieldCbo.setCurrentIndex(-1)

    def clear_maximum_width(self):
        self.maximum_width_FieldCbo.setCurrentIndex(-1)

    def clear_vertical_fail_rate(self):
        self.vertical_fail_rate_FieldCbo.setCurrentIndex(-1)

    def clear_horizontal_fail_rate(self):
        self.horizontal_fail_rate_FieldCbo.setCurrentIndex(-1)

    def clear_all_walls_attributes(self):
        self.crest_elevation_FieldCbo.setCurrentIndex(-1)
        self.name_FieldCbo.setCurrentIndex(-1)
        self.correction_FieldCbo.setCurrentIndex(-1)
        self.failure_height_FieldCbo.setCurrentIndex(-1)
        self.duration_FieldCbo.setCurrentIndex(-1)
        self.base_elevation_FieldCbo.setCurrentIndex(-1)
        self.maximum_width_FieldCbo.setCurrentIndex(-1)
        self.vertical_fail_rate_FieldCbo.setCurrentIndex(-1)
        self.horizontal_fail_rate_FieldCbo.setCurrentIndex(-1)

    def accept(self):
        if (
            self.crest_elevation_FieldCbo.currentText() == ""
            or self.name_FieldCbo.currentText() == ""  # not strictly required
            # or self.correction_FieldCbo.currentText() == "" # not strictly required
            or (
                self.failure_groupBox.isChecked()
                and (
                    self.failure_height_FieldCbo.currentText() == ""
                    or self.duration_FieldCbo.currentText() == ""
                    or self.base_elevation_FieldCbo.currentText() == ""
                    or self.maximum_width_FieldCbo.currentText() == ""
                    or self.vertical_fail_rate_FieldCbo.currentText() == ""
                    or self.horizontal_fail_rate_FieldCbo.currentText() == ""
                )
            )
        ):
            QApplication.restoreOverrideCursor()
            self.uc.show_info("All fields must be selected!")
            return

        self.close()
        self.create_user_levees_from_walls_shapefile()

    def create_user_levees_from_walls_shapefile(self):
        self.uc.clear_bar_messages()

        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool!")
            self.uc.log_info("There is no grid! Please create it before running tool!")
            return

        load_walls = False

        for field in self.walls_fields_groupBox.findChildren(QComboBox):
            if field.currentIndex() != -1:
                load_walls = True
                break

        self.save_wall_shapefile_fields()

        if not load_walls:
            self.uc.bar_warn("No data was selected!")
            self.uc.log_info("No data was selected!")
        else:
            # Load walls from shapefile:
            walls_sf = self.walls_shapefile_cbo.currentText()
            lyr = self.lyrs.get_layer_by_name(walls_sf).layer()

            # Create user levee lines from walls shapefile:
            try:
                # iterate over wall elements using the extents of the grid
                userLeveeLinesAddedCounter = 0
                if self.ask_append:
                    if not self.levees_append_chbox.isChecked():
                        if not self.gutils.is_table_empty("user_levee_lines"):
                            if not self.uc.question(
                                "There are "
                                + str(self.current_user_lines)
                                + " User Levee Lines already defined.\n"
                                + "They will be deleted.\n\n"
                                + "Would you like to continue?"
                            ):
                                return
                            else:
                                QApplication.setOverrideCursor(qt_cursor_shape("WaitCursor"))
                                self.gutils.clear_tables("user_levee_lines", "levee_failure")
                                self.user_levee_lines_lyr.reload()
                                self.current_user_lines = -self.current_user_lines
                                QApplication.restoreOverrideCursor()
                    else:
                        if not self.gutils.is_table_empty("user_levee_lines"):
                            if not self.uc.question(
                                "There are "
                                + str(self.current_user_lines)
                                + " User Levee Lines already defined.\n"
                                + "New"
                                + " wall lines will be added to them.\n\n"
                                + "Would you like to continue?"
                            ):
                                return

                QApplication.setOverrideCursor(qt_cursor_shape("WaitCursor"))
                starttime = datetime.datetime.now()

                extent_request = QgsFeatureRequest()
                extent_request.setDestinationCrs(self.grid_lyr.crs(), QgsProject.instance().transformContext())
                extent_request.setFilterRect(self.grid_lyr.extent())
                wall_features = lyr.getFeatures(extent_request)

                levee_lines_fields = self.user_levee_lines_lyr.fields()

                if levee_lines_fields.indexFromName("failDuration") == -1:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_warn(
                        "ERROR 060120.0629.: fields missing!\nThe User Levee Lines layer do not have all the required fields.\n\n"
                        + "Your project is old. Please create a new project and import your old data."
                    )
                    self.uc.log_info(
                        "ERROR 060120.0629.: fields missing!\nThe User Levee Lines layer do not have all the required fields.\n\n"
                        + "Your project is old. Please create a new project and import your old data."
                    )
                    return

                self.user_levee_lines_lyr.startEditing()

                feat_to_add = []

                for wall_feat in wall_features:
                    item = wall_feat[self.crest_elevation_FieldCbo.currentText()]
                    elev = float(item) if item and item != "" else None

                    item = wall_feat[self.name_FieldCbo.currentText()]
                    name = str(item) if item and item != "" else str(int(wall_feat["fid"]))

                    item = wall_feat[self.correction_FieldCbo.currentText()]
                    correction = float(item) if item and item != "" else None

                    levee_feat = QgsFeature()
                    levee_feat.setFields(levee_lines_fields)

                    if elev is not None:
                        levee_feat.setAttribute("elev", elev)
                    levee_feat.setAttribute("name", name)
                    if correction is not None:
                        levee_feat.setAttribute("correction", correction)

                    # Set failure:
                    if self.failure_groupBox.isChecked():
                        try:
                            item = wall_feat[self.failure_height_FieldCbo.currentText()]
                        except:
                            item = 0.0
                        failElev = float_or_zero(item)

                        try:
                            item = wall_feat[self.duration_FieldCbo.currentText()]
                        except:
                            item = 0.0

                        failDuration = float_or_zero(item)

                        try:
                            item = wall_feat[self.base_elevation_FieldCbo.currentText()]
                        except:
                            item = 0.0
                        failBaseElev = float_or_zero(item)

                        try:
                            item = wall_feat[self.maximum_width_FieldCbo.currentText()]
                        except:
                            item = 0.0
                        failMaxWidth = float_or_zero(item)

                        try:
                            item = wall_feat[self.vertical_fail_rate_FieldCbo.currentText()]
                        except:
                            item = 0.0
                        failVRate = float_or_zero(item)

                        try:
                            item = wall_feat[self.horizontal_fail_rate_FieldCbo.currentText()]
                        except:
                            item = 0.0
                        failHRate = float_or_zero(item)

                        if self.fail_elev_radio.isChecked():
                            levee_feat.setAttribute("failElev", failElev)
                            levee_feat.setAttribute("failDepth", 0.0)
                        else:  # use depth => compute fail from highest adjacent cell elevation.
                            levee_feat.setAttribute("failElev", 0.0)
                            levee_feat.setAttribute("failDepth", failElev)

                        levee_feat.setAttribute("failDuration", failDuration)
                        levee_feat.setAttribute("failBaseElev", failBaseElev)
                        levee_feat.setAttribute("failMaxWidth", failMaxWidth)
                        levee_feat.setAttribute("failVRate", failVRate)
                        levee_feat.setAttribute("failHRate", failHRate)

                    else:
                        levee_feat.setAttribute("failElev", 0.0)
                        levee_feat.setAttribute("failDepth", 0.0)
                        levee_feat.setAttribute("failDuration", 0.0)
                        levee_feat.setAttribute("failBaseElev", 0.0)
                        levee_feat.setAttribute("failMaxWidth", 0.0)
                        levee_feat.setAttribute("failVRate", 0.0)
                        levee_feat.setAttribute("failHRate", 0.0)

                    geom = wall_feat.geometry()
                    if geom is None:
                        self.uc.show_warn("WARNING 071219.0428: Error processing geometry of walls '" + name + "' !")
                        self.uc.log_info("WARNING 071219.0428: Error processing geometry of walls '" + name + "' !")
                        continue

                    points = extractPoints(geom)
                    if points is None:
                        self.uc.show_warn("WARNING 071219.0429: Wall line " + name + " is faulty!")
                        self.uc.log_info("WARNING 071219.0429: Wall line " + name + " is faulty!")
                        continue

                    new_geom = QgsGeometry.fromPolylineXY(points)
                    if new_geom is None:
                        continue

                    levee_feat.setGeometry(new_geom)

                    feat_to_add.append(levee_feat)
                    userLeveeLinesAddedCounter += 1

                self.user_levee_lines_lyr.addFeatures(feat_to_add)

                self.user_levee_lines_lyr.commitChanges()
                self.user_levee_lines_lyr.updateExtents()
                self.user_levee_lines_lyr.triggerRepaint()
                self.user_levee_lines_lyr.removeSelection()

                QApplication.restoreOverrideCursor()
                print("User levee lines added in %s seconds" % (datetime.datetime.now() - starttime).total_seconds())
                if self.current_user_lines < 0:
                    info = (
                        "Creation of User Levee Lines from walls finished!\n\n"
                        + str(userLeveeLinesAddedCounter)
                        + " lines were added."
                    )
                    info += "\n\nAnd " + str(-self.current_user_lines) + " previous User Levee Lines were deleted."
                elif self.current_user_lines > 0:
                    info = (
                        "Creation of User Levee Lines from walls finished!\n\n"
                        + str(userLeveeLinesAddedCounter)
                        + " new lines were added from walls to"
                    )
                    info += "\nthe previous " + str(self.current_user_lines) + " User Levee Lines."
                else:
                    info = (
                        "Creation of User Levee Lines from walls finished!\n\n"
                        + str(userLeveeLinesAddedCounter)
                        + " lines were added to the User Levee Lines layer."
                    )

                info += "\n\nYou can now use the 'Levee Elevation Tool' to intersect the User Levee Lines with the grid system to create the levee directions for each cell."

                QApplication.restoreOverrideCursor()
                self.uc.show_info(info)

                QApplication.restoreOverrideCursor()

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error(
                    "ERROR 010120.0451: creation of levees from walls shapefile failed! "
                    + "\n__________________________________________________",
                    e,
                )

    def cancel_message(self):
        self.uc.bar_info("No data was selected!")
        self.uc.log_info("No data was selected!")

    def save_wall_shapefile_fields(self):
        s = QSettings()

        s.setValue("sf_walls_layer_name", self.walls_shapefile_cbo.currentText())
        s.setValue("sf_walls_crest_elevation", self.crest_elevation_FieldCbo.currentIndex())
        s.setValue("sf_walls_name", self.name_FieldCbo.currentIndex())
        s.setValue("sf_walls_correction", self.correction_FieldCbo.currentIndex())
        s.setValue("sf_walls_failure_height", self.failure_height_FieldCbo.currentIndex())
        s.setValue("sf_walls_duration", self.duration_FieldCbo.currentIndex())
        s.setValue("sf_walls_base_elevation", self.base_elevation_FieldCbo.currentIndex())
        s.setValue("sf_walls_maximum_width", self.maximum_width_FieldCbo.currentIndex())
        s.setValue("sf_walls_vertical_fail_rate", self.vertical_fail_rate_FieldCbo.currentIndex())
        s.setValue("sf_walls_horizontal_fail_rate", self.horizontal_fail_rate_FieldCbo.currentIndex())

        s.setValue("sf_walls_crest_elevation_name", self.crest_elevation_FieldCbo.currentText())
        s.setValue("sf_walls_name_name", self.name_FieldCbo.currentText())
        s.setValue("sf_walls_correction_name", self.correction_FieldCbo.currentText())
        s.setValue("sf_walls_failure_height_name", self.failure_height_FieldCbo.currentText())
        s.setValue("sf_walls_duration_name", self.duration_FieldCbo.currentText())
        s.setValue("sf_walls_base_elevation_name", self.base_elevation_FieldCbo.currentText())
        s.setValue("sf_walls_maximum_width_name", self.maximum_width_FieldCbo.currentText())
        s.setValue("sf_walls_vertical_fail_rate_name", self.vertical_fail_rate_FieldCbo.currentText())
        s.setValue("sf_walls_horizontal_fail_rate_name", self.horizontal_fail_rate_FieldCbo.currentText())