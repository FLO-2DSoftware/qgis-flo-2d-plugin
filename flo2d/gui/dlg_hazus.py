# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import traceback
from qgis.core import QgsWkbTypes
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QApplication, QDialogButtonBox, QInputDialog
from .ui_utils import load_ui, set_icon
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..gui.dlg_sampling_elev import SamplingElevDialog
from ..gui.dlg_sampling_buildings_elevations import SamplingBuildingsElevationsDialog
from ..flo2d_tools.grid_tools import grid_has_empty_elev

uiDialog, qtBaseClass = load_ui("hazus")


class HazusDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = GeoPackageUtils(con, iface)
        self.current_lyr = None

        self.hazus_buttonBox.button(QDialogButtonBox.Save).setText("Compute")

        self.setup_layers_comboxes()
        self.setup_statistics()

        set_icon(self.buildings_raster_elevation_btn, "sample_elev.svg")
        set_icon(self.buildings_xyz_elevation_btn, "sample_elev_xyz.svg")
        set_icon(self.buildings_adjust_factor_from_polygons_btn, "sample_tolerance.svg")

        self.global_adjustment_radio.clicked.connect(self.enable_global_adjustment_radio)

        # connections
        self.compute_and_show_buildings_statistics_btn.clicked.connect(self.buildings_statistics)
        self.buildings_cbo.currentIndexChanged.connect(self.populate_lists_with_buildigns_attributes)
        self.buildings_layer_cbo.currentIndexChanged.connect(self.populate_statistics_fields)
        self.buildings_raster_elevation_btn.clicked.connect(self.raster_elevation)
#         self.buildings_xyz_elevation_btn.clicked.connect(self.xyz_elevation)
        self.buildings_adjust_factor_from_polygons_btn.clicked.connect(self.eval_buildings_adjustment_factor)

        # Buildings ground elevations group:
        self.elevation_from_shapefile_radio.clicked.connect(self.enable_elevation_from_shapefile_radio)
        self.intercept_grid_radio.clicked.connect(self.disable_all_buildings_extras)
        self.sample_from_raster_radio.clicked.connect(self.enable_sample_from_raster_radio)
        self.interpolate_from_DTM_points_radio.clicked.connect(self.enable_interpolate_from_DTM_points_radio)
        self.area_reduction_factors_radio.clicked.connect(self.disable_all_buildings_extras)

        # Finished floor adjustment group:
        self.global_radio.clicked.connect(self.enable_global_radio)
        self.adjust_factor_from_building_radio.clicked.connect(self.enable_adjust_factor_from_building_radio)
        self.adjust_factor__ID_from_building_radio.clicked.connect(self.enable_adjust_factor__ID_from_building_radio)
        self.adjust_factor_from_user_polygon_radio.clicked.connect(self.enable_adjust_factor_from_user_polygon_radio)
        self.none_radio.clicked.connect(self.disable_all_adjustments_extras)
        self.hazus_buttonBox.accepted.connect(self.compute_hazus)
        # self.buttonBox.clicked.connect(self.check_selections)
        # self.accepted.connect(self.check_selections)

        self.setFixedSize(self.size())

    def setup_layers_comboxes(self):
        try:
            self.buildings_cbo.clear()
            lyrs = self.lyrs.list_group_vlayers()
            for l in lyrs:
                if l.geometryType() == QgsWkbTypes.PolygonGeometry:
                    self.buildings_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())

            if self.buildings_cbo.count():
                self.populate_lists_with_buildigns_attributes(self.buildings_cbo.currentIndex())
            else:
                QApplication.restoreOverrideCursor()
                self.uc.bar_warn("There are not any polygon layers selected (or visible)")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 130618.1650: Hazus layers loading failed!.\n", e)

    def setup_statistics(self):
        try:
            self.buildings_layer_cbo.clear()
            lyrs = self.lyrs.list_group_vlayers()
            for l in lyrs:
                if l.geometryType() == QgsWkbTypes.PolygonGeometry:
                    if l.featureCount() != 0:
                        self.buildings_layer_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())

            if self.buildings_layer_cbo.count():
                self.populate_statistics_fields(self.buildings_layer_cbo.currentIndex())
            else:
                QApplication.restoreOverrideCursor()
                self.uc.bar_warn("There are not any polygon layers selected (or visible)")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 130618.1715: Hazus layers loading failed!.\n", e)

    def populate_lists_with_buildigns_attributes(self, idx):
        uri = self.buildings_cbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri)
        self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()

        self.ground_elev_buildings_field_FieldCbo.clear()
        self.ground_elev_buildings_field_FieldCbo.setLayer(self.current_lyr)

        self.adjust_factor_buildings_field_FieldCbo.clear()
        self.adjust_factor_buildings_field_FieldCbo.setLayer(self.current_lyr)

        self.ID_adjust_factor_buildings_field_FieldCbo.clear()
        self.ID_adjust_factor_buildings_field_FieldCbo.setLayer(self.current_lyr)

    def populate_statistics_fields(self, idx):
        uri = self.buildings_layer_cbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri)
        self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()

        self.building_ID_FieldCbo.clear()
        self.building_ID_FieldCbo.setLayer(self.current_lyr)
        self.building_ID_FieldCbo.setCurrentIndex(0)

        self.ground_elev_FieldCbo.clear()
        self.ground_elev_FieldCbo.setLayer(self.current_lyr)
        self.ground_elev_FieldCbo.setCurrentIndex(0)

        self.water_elev_FieldCbo.clear()
        self.water_elev_FieldCbo.setLayer(self.current_lyr)
        self.water_elev_FieldCbo.setCurrentIndex(0)

        self.max_flow_depth_FieldCbo.clear()
        self.max_flow_depth_FieldCbo.setLayer(self.current_lyr)
        self.max_flow_depth_FieldCbo.setCurrentIndex(0)

    def raster_elevation(self):
        if self.gutils.is_table_empty("user_model_boundary"):
            self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return
        rasters = self.lyrs.list_group_rlayers()
        if not rasters:
            self.uc.bar_warn("There are no raster layers in the project!")

        cell_size = self.get_cell_size()
        dlg = SamplingElevDialog(self.con, self.iface, self.lyrs, cell_size)
        ok = dlg.exec_()
        if ok:
            pass
        else:
            return
        try:
            pass
            # QApplication.setOverrideCursor(Qt.WaitCursor)
            # res = dlg.probe_elevation()
            # QApplication.restoreOverrideCursor()
            # if res:
            #     dlg.show_probing_result_info()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn("WARNING 060319.1627: Probing grid elevation failed! Please check your raster layer.")

#     def xyz_elevation(self):
#         if self.gutils.is_table_empty("grid"):
#             self.uc.bar_warn("WARNING 060319.1628: There is no grid! Please create it before running tool.")
#             return
#         dlg = SamplingXYZDialog(self.con, self.iface, self.lyrs)
#         ok = dlg.exec_()
#         if ok:
#             pass
#         else:
#             return
        
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
            cs = bfeat["cell_size"]
            if cs <= 0:
                self.uc.show_warn(
                    "WARNING 060319.1629: Cell size must be positive. Change the feature attribute value in Computational Domain layer."
                )
                return None
            self.gutils.set_cont_par("CELLSIZE", cs)
        else:
            cs = self.gutils.get_cont_par("CELLSIZE")
            cs = None if cs == "" else cs
        if cs:
            if cs <= 0:
                self.uc.show_warn(
                    "WARNING 060319.1630: Cell size must be positive. Change the feature attribute value in Computational Domain layer or default cell size in the project settings."
                )
                return None
            return cs
        else:
            r, ok = QInputDialog.getDouble(
                None, "Grid Cell Size", "Enter grid element cell size", value=100, min=0.1, max=99999
            )
            if ok:
                cs = r
                self.gutils.set_cont_par("CELLSIZE", cs)
            else:
                return None

    def eval_buildings_adjustment_factor(self):
        grid_empty = self.gutils.is_table_empty("grid")
        if grid_empty:
            self.uc.bar_warn(
                "WARNING 060319.1631: There is no grid. Please, create it before evaluating the tolerance values."
            )
            return
        else:
            pass

        if self.gutils.is_table_empty("buildings_areas"):
            w = "There are no buildings areas polygons in Buildings Areas (Schematic Layers)!.\n\n"
            w += "Please digitize them before running tool."
            self.uc.bar_warn(w)
            return
        try:
            self.uc.show_warn(
                "WARNING 060319.1632: Assignment of building areas to building polygons. Not implemented yet!"
            )
            # QApplication.setOverrideCursor(Qt.WaitCursor)
            # grid_lyr = self.lyrs.data['grid']['qlyr']
            # user_building_areas_lyr = self.lyrs.data['buildings_areas']['qlyr']
            # evaluate_spatial_buildings_adjustment_factor(self.gutils, grid_lyr, user_building_areas_lyr)
            # tol_lyr = self.lyrs.data['tolspatial']['qlyr']
            # tol_lyr.reload()
            # self.lyrs.update_layer_extents(tol_lyr)
            # QApplication.restoreOverrideCursor()
            # self.uc.show_info('Spatial tolerance values calculated!')
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn(
                "WARNING 060319.1650: Evaluation of buildings adjustment factor failed! Please check your Building Areas (Schematic layer)."
            )
            QApplication.restoreOverrideCursor()

    def enable_global_adjustment_radio(self):
        self.global_adjust_dbox.setEnabled(self.global_adjustment_radio.isChecked())

    def enable_elevation_from_shapefile_radio(self):
        self.disable_all_buildings_extras()
        self.ground_elev_buildings_field_FieldCbo.setEnabled(True)

    def enable_sample_from_raster_radio(self):
        self.disable_all_buildings_extras()
        self.buildings_raster_elevation_btn.setEnabled(True)

    def enable_interpolate_from_DTM_points_radio(self):
        self.disable_all_buildings_extras()
        self.buildings_xyz_elevation_btn.setEnabled(True)

    def disable_all_buildings_extras(self):
        self.ground_elev_buildings_field_FieldCbo.setEnabled(False)
        self.buildings_raster_elevation_btn.setEnabled(False)
        self.buildings_xyz_elevation_btn.setEnabled(False)

    def enable_global_radio(self):
        self.disable_all_adjustments_extras()
        self.global_adjust_factor_dbox.setEnabled(True)

    def enable_adjust_factor_from_building_radio(self):
        self.disable_all_adjustments_extras()
        self.adjust_factor_buildings_field_FieldCbo.setEnabled(True)

    def enable_adjust_factor__ID_from_building_radio(self):
        self.disable_all_adjustments_extras()
        self.ID_adjust_factor_buildings_field_FieldCbo.setEnabled(True)
        self.adjust_factor_table_cbo.setEnabled(True)

    def enable_adjust_factor_from_user_polygon_radio(self):
        self.disable_all_adjustments_extras()
        self.buildings_adjust_factor_from_polygons_btn.setEnabled(True)

    def disable_all_adjustments_extras(
        self,
    ):
        self.global_adjust_factor_dbox.setEnabled(False)
        self.adjust_factor_buildings_field_FieldCbo.setEnabled(False)
        self.ID_adjust_factor_buildings_field_FieldCbo.setEnabled(False)
        self.adjust_factor_table_cbo.setEnabled(False)
        self.buildings_adjust_factor_from_polygons_btn.setEnabled(False)

    def check_selections(self):
        if self.intercept_grid_radio.isChecked():
            null_elev = grid_has_empty_elev(self.gutils)
            if null_elev:
                msg = "INFO 060319.1633: There are {} grid elements that have no elevation value.".format(null_elev)
                self.uc.show_info(msg)
            else:
                self.uc.show_info("Perform average grid elevation interception.")

    def compute_hazus(self):
        if self.elevation_from_shapefile_radio.isChecked():
            self.close()
            self.uc.show_info("Perform elevation from shapefile.")

        elif self.intercept_grid_radio.isChecked():
            null_elev = grid_has_empty_elev(self.gutils)
            if null_elev:
                msg = "Warning: There are {} grid elements that have no elevation value.".format(null_elev)
                msg += "\n\nWould you like to continue the grid interception with the buildings?"
                if not self.uc.question(msg):
                    return

            else:
                self.close()
                success, fields = self.average_grid_elevation_interception()
                if success:
                    fieldsStr = ", ".join(fields)
                    if self.uc.question(
                        "Field(s) '"
                        + fieldsStr
                        + "' updated.\n\n"
                        + "Would you like to calculate the 'flow_depth' field?"
                    ):
                        self.compute_flow_depths()
                        self.uc.show_info("Flow depths were calculated.")

        elif self.sample_from_raster_radio.isChecked():
            self.close()
            self.uc.show_info("Perform sample from raster.")

        elif self.interpolate_from_DTM_points_radio.isChecked():
            self.close()
            self.uc.show_info("Perform interpolate from DTM points.")

        elif self.area_reduction_factors_radio.isChecked():
            self.close()
            self.uc.show_info("Compute from area reduction factors.")
        else:
            pass

    def average_grid_elevation_interception(self):

        del_statistics = "DELETE FROM buildings_stats;"
        insert_water_elev_statistics = """INSERT INTO buildings_stats 
                                    (   building_ID, 
                                        avg_grnd_elev, 
                                        min_grnd_elev,
                                        max_grnd_elev,
                                        avg_water_elev, 
                                        min_water_elev, 
                                        max_water_elev
                                    )  VALUES (?,?,?,?,?,?,?);
                                """

        insert_flow_depth_statistics = """INSERT INTO buildings_stats 
                                    (   building_ID, 
                                        avg_grnd_elev, 
                                        min_grnd_elev,
                                        max_grnd_elev,
                                        avg_depth,
                                        min_depth, 
                                        max_depth 
                                    )  VALUES (?,?,?,?,?,?,?);
                                """

        update_water_elev_statistics = """UPDATE buildings_stats 
                                        SET avg_water_elev = ?,
                                            min_water_elev = ?, 
                                            max_water_elev = ?
                                        WHERE building_ID = ?;
                                    """

        update_flow_depth_statistics = """UPDATE buildings_stats 
                                        SET avg_depth = ?,
                                            min_depth = ?, 
                                            max_depth = ?
                                        WHERE building_ID = ?;
                                    """
        try:
            self.gutils.execute(del_statistics)
            cur = self.gutils.con.cursor()
            uniformizedFields = []
            first_loop = True
            repeat = True
            while repeat is True:
                QApplication.restoreOverrideCursor()
                dlg = SamplingBuildingsElevationsDialog(self.con, self.iface, self.lyrs)
                ok = dlg.exec_()
                if ok:
                    pass
                else:
                    return False, ""

                building_name = dlg.buildings_cbo.currentText()
                field_to_uniformize = dlg.field_to_uniformize_cbo.currentText()
                mode = dlg.calc_cbo.currentText()
                ID_field = dlg.ID_field_cbo.currentText()

                QApplication.setOverrideCursor(Qt.WaitCursor)

                # Loop thru all features of layer of buildings to create list of
                # elevations (mean, min, or max) for groups with same building id:
                lyr = self.lyrs.get_layer_by_name(building_name, group=self.lyrs.group).layer()
                building_fts = lyr.getFeatures()
                n_features = lyr.featureCount()
                final_val_list = []
                i = 1
                building = next(building_fts)
                id0 = building[ID_field]
                val = building[field_to_uniformize]
                elev = building["elevation"]
                while i < n_features:
                    sum = val
                    avg = val
                    min = val
                    max = val
                    elev_sum = elev
                    elev_avg = elev
                    elev_min = elev
                    elev_max = elev
                    n = 1

                    while i < n_features:
                        building = next(building_fts)
                        i += 1
                        id1 = building[ID_field]
                        elev = building["elevation"]
                        if id1 == id0:
                            n += 1
                            sum += val
                            elev_sum += elev
                            if val < min:
                                min = val
                            if val > max:
                                max = val
                            if elev < elev_min:
                                elev_min = elev
                            if elev > elev_max:
                                elev_max = elev
                        else:
                            current_id = id0
                            id0 = id1
                            break

                    if i == n_features:
                        current_id = id1

                    if mode == "Mean":
                        final_val = sum / n
                        avg = sum / n
                    elif mode == "Min":
                        final_val = min
                    elif mode == "Max":
                        final_val = max
                    else:
                        final_val = -999

                    if first_loop:
                        if field_to_uniformize == "water_elev":
                            cur.execute(
                                insert_water_elev_statistics,
                                (current_id, elev_sum / n, elev_min, elev_max, avg, min, max),
                            )
                        elif field_to_uniformize == "flow_depth":
                            cur.execute(
                                insert_flow_depth_statistics,
                                (current_id, elev_sum / n, elev_min, elev_max, avg, min, max),
                            )
                    else:
                        if field_to_uniformize == "water_elev":
                            cur.execute(
                                update_water_elev_statistics,
                                (
                                    avg,
                                    min,
                                    max,
                                    current_id,
                                ),
                            )
                        elif field_to_uniformize == "flow_depth":
                            cur.execute(
                                update_flow_depth_statistics,
                                (
                                    avg,
                                    min,
                                    max,
                                    current_id,
                                ),
                            )

                    # 'UPDATE user_fpxsec SET name = ?, iflo = ? WHERE fid = ?;'
                    #     self.gutils.execute(qry, (name, iflo, fid,))

                    if self.global_radio.isChecked():
                        final_val += self.global_adjust_factor_dbox.value()
                    final_val_list.append(final_val)

                # Insert attributesin buildings_stats:
                self.gutils.con.commit()

                # Loop thru all features again and assign new elevation from final_val_list:
                building_fts = lyr.getFeatures()
                lyr.startEditing()

                index_lyr = 1
                index_val = 0
                f0 = next(building_fts)
                id0 = f0[ID_field]
                lyr.changeAttributeValue(
                    f0.id(), lyr.fields().lookupField(field_to_uniformize), final_val_list[index_val]
                )
                while index_lyr < n_features:
                    f1 = next(building_fts)
                    id1 = f1[ID_field]
                    index_lyr += 1
                    if id1 == id0:
                        lyr.changeAttributeValue(
                            f1.id(), lyr.fields().lookupField(field_to_uniformize), final_val_list[index_val]
                        )
                    else:
                        index_val += 1
                        lyr.changeAttributeValue(
                            f1.id(), lyr.fields().lookupField(field_to_uniformize), final_val_list[index_val]
                        )
                        id0 = id1

                lyr.commitChanges()
                lyr.updateExtents()
                lyr.triggerRepaint()
                lyr.removeSelection()

                uniformizedFields.append(field_to_uniformize)

                QApplication.restoreOverrideCursor()
                first_loop = False
                repeat = self.uc.question("Would you like to update another field?.")

            QApplication.restoreOverrideCursor()
            return True, uniformizedFields

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 080618.0456: Uniformization of field values failed!\n", e)
            lyr.rollBack()
            return False, ""

    def compute_flow_depths(self):
        # try:
        building_name = "Intersection"
        QApplication.setOverrideCursor(Qt.WaitCursor)
        lyr = self.lyrs.get_layer_by_name(building_name, group=self.lyrs.group).layer()
        lyr.startEditing()
        fts = lyr.getFeatures()
        for f in fts:
            flowDepth = f["water_elev"] - f["elevation"]
            if flowDepth < 0:
                flowdepth = 0
            lyr.changeAttributeValue(f.id(), lyr.fields().lookupField("flow_depth"), flowDepth)

        lyr.commitChanges()
        lyr.updateExtents()
        lyr.triggerRepaint()
        lyr.removeSelection()

        QApplication.restoreOverrideCursor()

    # except Exception as e:
    #     QApplication.restoreOverrideCursor()
    #     lyr.rollBack()
    #     self.uc.show_warn('Evaluation of flow depths failed!\n\n'+ repr(e))

    def buildings_statistics(self):
        try:
            null_elev = grid_has_empty_elev(self.gutils)
            if null_elev:
                msg = "Warning: There are {} grid elements that have no elevation value.".format(null_elev)
                msg += "\n\nWould you like to continue the grid interception with the buildings?"
                if not self.uc.question(msg):
                    return

            else:
                self.close()
                success, fields = self.compute_and_show_buildings_statistics()
                if success:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_info(
                        "Buildings statistics can be seen in 'Buildings Statistics' table.\n\n"
                        + "All attributes computed from '"
                        + fields[0]
                        + "' layer using buildings ID '"
                        + fields[1]
                        + "'\n\nand fields:\n\n'"
                        + fields[2]
                        + "' (for ground and 1st. floor elevations),\n'"
                        + fields[3]
                        + "' (for water elevations),  and \n'"
                        + fields[4]
                        + "' for flow depths.\n\n"
                        + "1st. floor elevations obtained by adding an adjustment factor of "
                        + str(fields[5])
                    )

                    stats_table = self.lyrs.get_layer_by_name("Buildings Statistics", group=self.lyrs.group).layer()
                    self.iface.setActiveLayer(stats_table)
                    self.iface.showAttributeTable(self.iface.activeLayer())

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 150618.0235: Error while computing buildings statistics!", e)

    def compute_and_show_buildings_statistics(self):

        del_statistics = "DELETE FROM buildings_stats;"
        insert_statistics = """INSERT INTO buildings_stats 
                                    (   building_ID, 
                                        grnd_elev_avg, 
                                        grnd_elev_min,
                                        grnd_elev_max,
                                        floor_avg, 
                                        floor_min,
                                        floor_max,                                        
                                        water_elev_avg, 
                                        water_elev_min, 
                                        water_elev_max,
                                        depth_avg,
                                        depth_min, 
                                        depth_max                               
                                    )  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?);
                                """

        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)

            self.gutils.execute(del_statistics)
            cur = self.gutils.con.cursor()
            uniformizedFields = []
            building_name = self.buildings_layer_cbo.currentText()
            ID_field = self.building_ID_FieldCbo.currentText()
            elev_field = self.ground_elev_FieldCbo.currentText()
            water_field = self.water_elev_FieldCbo.currentText()
            flow_field = self.max_flow_depth_FieldCbo.currentText()

            # Loop thru all features of layer of buildings to create list of
            # elevations (mean, min, or max) for groups with same building id:
            lyr = self.lyrs.get_layer_by_name(building_name, group=self.lyrs.group).layer()
            building_fts = lyr.getFeatures()
            n_features = lyr.featureCount()
            final_val_list = []
            i = 1

            building = next(building_fts)

            id0 = building[ID_field]
            elev = building[elev_field]
            water = building[water_field]
            flow = building[flow_field]
            while i < n_features:
                n = 1
                elev_sum = elev
                elev_min = elev
                elev_max = elev

                water_sum = water
                water_min = water
                water_max = water

                flow_sum = flow
                flow_min = flow
                flow_max = flow

                while i < n_features:

                    building = next(building_fts)

                    i += 1
                    id1 = building[ID_field]
                    elev = building[elev_field]
                    water = building[water_field]
                    flow = building[flow_field]
                    if id1 == id0:
                        n += 1
                        elev_sum += elev
                        water_sum += water
                        flow_sum += flow

                        if elev < elev_min:
                            elev_min = elev
                        if elev > elev_max:
                            elev_max = elev

                        if water < water_min:
                            water_min = water
                        if water > water_max:
                            water_max = water

                        if flow < flow_min:
                            flow_min = flow
                        if flow > flow_max:
                            flow_max = flow

                    else:
                        current_id = id0
                        id0 = id1
                        break

                if i == n_features:
                    current_id = id1
                if self.global_radio.isChecked():
                    adjust = self.global_adjust_dbox.value()
                else:
                    adjust = 0

                floor_avg = elev_sum / n + adjust
                floor_min = elev_min + adjust
                floor_max = elev_max + adjust

                cur.execute(
                    insert_statistics,
                    (
                        current_id,
                        "{:7.2f}".format(elev_sum / n),
                        "{:7.2f}".format(elev_min),
                        "{:7.2f}".format(elev_max),
                        "{:7.2f}".format(floor_avg),
                        "{:7.2f}".format(floor_min),
                        "{:7.2f}".format(floor_max),
                        "{:7.2f}".format(water_sum / n),
                        "{:7.2f}".format(water_min),
                        "{:7.2f}".format(water_max),
                        "{:7.2f}".format(flow_sum / n),
                        "{:7.2f}".format(flow_min),
                        "{:7.2f}".format(flow_max)
                        # , poly
                    ),
                )

            # Insert attributes in buildings_stats:
            self.gutils.con.commit()

            QApplication.restoreOverrideCursor()
            return True, (building_name, ID_field, elev_field, water_field, flow_field, adjust)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 080618.0456: Uniformization of field values failed!", e)
            lyr.rollBack()
            return False, ""
