# -*- coding: utf-8 -*-
# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from qgis._core import QgsFeatureRequest

from .ui_utils import load_ui, center_canvas
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui("areas_editor")


class AreasEditorWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.con = None
        self.setupUi(self)
        self.lyrs = lyrs
        self.gutils = None
        self.uc = UserCommunication(iface, "FLO-2D")

        self.setup_connection()

        self.areas_grps = {
            self.ne_channel_grp: 'user_noexchange_chan_areas',
            self.building_areas_grp: 'buildings_areas',
            self.shallown_grp: 'spatialshallow',
            self.froude_areas_grp: 'fpfroude',
            self.tolerance_areas_grp: 'tolspatial',
            self.blocked_areas_grp: 'user_blocked_areas',
            self.roughness_grp: 'user_roughness',
            self.steep_slopen_grp: 'user_steep_slope_n_areas'
        }

        self.areas_grp_cbo = {
            self.noexchange_cbo: 'user_noexchange_chan_areas',
            self.buildings_cbo: 'buildings_areas',
            self.shallown_cbo: 'spatialshallow',
            self.froude_cbo: 'fpfroude',
            self.tolerance_cbo: 'tolspatial',
            self.blocked_cbo: 'user_blocked_areas',
            self.roughness_cbo: 'user_roughness',
            self.steep_slopen_cbo: 'user_steep_slope_n_areas'
        }

        self.del_no_exchange_btn.clicked.connect(lambda: self.delete_area_fid(self.noexchange_cbo, 'user_noexchange_chan_areas'))
        self.del_building_btn.clicked.connect(lambda: self.delete_area_fid(self.buildings_cbo, 'buildings_areas'))
        self.del_shallown_btn.clicked.connect(lambda: self.delete_area_fid(self.shallown_cbo, 'spatialshallow'))
        self.del_froude_btn.clicked.connect(lambda: self.delete_area_fid(self.froude_cbo, 'fpfroude'))
        self.del_tolerance_btn.clicked.connect(lambda: self.delete_area_fid(self.tolerance_cbo, 'tolspatial'))
        self.del_blocked_btn.clicked.connect(lambda: self.delete_area_fid(self.blocked_cbo, 'user_blocked_areas'))
        self.del_roughness_btn.clicked.connect(lambda: self.delete_area_fid(self.roughness_cbo, 'user_roughness'))
        self.del_steep_slopen_btn.clicked.connect(lambda: self.delete_area_fid(self.steep_slopen_cbo, 'user_steep_slope_n_areas'))

        self.eye_no_exchange_btn.clicked.connect(lambda: self.center_area_fid(self.noexchange_cbo, self.eye_no_exchange_btn, 'user_noexchange_chan_areas'))
        self.eye_building_btn.clicked.connect(lambda: self.center_area_fid(self.buildings_cbo, self.eye_building_btn, 'buildings_areas'))
        self.eye_shallown_btn.clicked.connect(lambda: self.center_area_fid(self.shallown_cbo, self.eye_shallown_btn, 'spatialshallow'))
        self.eye_froude_btn.clicked.connect(lambda: self.center_area_fid(self.froude_cbo, self.eye_froude_btn, 'fpfroude'))
        self.eye_tolerance_btn.clicked.connect(lambda: self.center_area_fid(self.tolerance_cbo, self.eye_tolerance_btn, 'tolspatial'))
        self.eye_blocked_btn.clicked.connect(lambda: self.center_area_fid(self.blocked_cbo, self.eye_blocked_btn, 'user_blocked_areas'))
        self.eye_roughness_btn.clicked.connect(lambda: self.center_area_fid(self.roughness_cbo, self.eye_roughness_btn, 'user_roughness'))
        self.eye_steep_slopen_btn.clicked.connect(lambda: self.center_area_fid(self.steep_slopen_cbo, self.eye_steep_slopen_btn, 'user_steep_slope_n_areas'))

        self.noexchange_cbo.currentIndexChanged.connect(lambda: self.populate_cbo_areas(self.noexchange_cbo, self.eye_no_exchange_btn))
        self.buildings_cbo.currentIndexChanged.connect(lambda: self.populate_cbo_areas(self.buildings_cbo, self.eye_building_btn))
        self.shallown_cbo.currentIndexChanged.connect(lambda: self.populate_cbo_areas(self.shallown_cbo, self.eye_shallown_btn))
        self.froude_cbo.currentIndexChanged.connect(lambda: self.populate_cbo_areas(self.froude_cbo, self.eye_froude_btn))
        self.tolerance_cbo.currentIndexChanged.connect(lambda: self.populate_cbo_areas(self.tolerance_cbo, self.eye_tolerance_btn))
        self.blocked_cbo.currentIndexChanged.connect(lambda: self.populate_cbo_areas(self.blocked_cbo, self.eye_blocked_btn))
        self.roughness_cbo.currentIndexChanged.connect(lambda: self.populate_cbo_areas(self.roughness_cbo, self.eye_roughness_btn))
        self.steep_slopen_cbo.currentIndexChanged.connect(lambda: self.populate_cbo_areas(self.steep_slopen_cbo, self.eye_steep_slopen_btn))

        self.schema_btn.clicked.connect(self.schematize_areas)
        self.del_schema_btn.clicked.connect(self.delete_schematized_areas)

        # Building Areas
        self.adj_factor_dsp.editingFinished.connect(self.save_building_adj_factor)
        self.shallown_dsb.editingFinished.connect(self.save_shallown)
        self.froud_dsb.editingFinished.connect(self.save_froude)
        self.tolerance_dsb.editingFinished.connect(self.save_tolerance)
        self.collapse_chbox.stateChanged.connect(self.save_blocked_areas)
        self.arf_chbox.stateChanged.connect(self.save_blocked_areas)
        self.wrf_chbox.stateChanged.connect(self.save_blocked_areas)
        self.mannings_dsb.editingFinished.connect(self.save_mannings)
        self.steep_slopen_global_chbox.stateChanged.connect(self.save_global_steep_slopen)

        self.populate_grps()

        self.areas_cbo.currentIndexChanged.connect(self.populate_grps)
        self.create_polygon_btn.clicked.connect(self.create_areas_polygon)
        self.revert_changes_btn.clicked.connect(self.revert_changes)

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        self.con = con
        self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_grps(self):
        """
        This function populates the groups on the editor based on the areas_cbo
        """
        selected_areas_idx = self.areas_cbo.currentIndex()
        if selected_areas_idx != 0:
            self.enable_btns(True)
            for i, areas_grp in enumerate(self.areas_grps.keys(), start=1):
                if i == selected_areas_idx:
                    areas_grp.setVisible(True)
                    self.populate_cbos()
                else:
                    areas_grp.setVisible(False)
        else:
            self.enable_btns(False)
            for areas_grp in self.areas_grps.keys():
                areas_grp.setVisible(False)


    def enable_btns(self, enable):
        """
        Function to enable or disable the buttons based on the selected areas
        """
        self.create_polygon_btn.setEnabled(enable)
        self.revert_changes_btn.setEnabled(enable)
        self.schema_btn.setEnabled(enable)
        self.del_schema_btn.setEnabled(enable)

    def create_areas_polygon(self):

        selected_areas_idx = self.areas_cbo.currentIndex()
        selected_areas_name = self.areas_cbo.currentText()
        if selected_areas_idx != 0:
            for i, areas_lyr in enumerate(self.areas_grps.values(), start=1):
                if i == selected_areas_idx:
                    if self.lyrs.any_lyr_in_edit(areas_lyr):
                        self.uc.bar_info(f"{selected_areas_name} saved!")
                        self.uc.log_info(f"{selected_areas_name} saved!")
                        self.lyrs.save_lyrs_edits(areas_lyr)
                        self.create_polygon_btn.setChecked(False)
                        self.populate_cbos()
                        return
                    else:
                        self.create_polygon_btn.setChecked(True)
                        self.lyrs.enter_edit_mode(areas_lyr)

    def revert_changes(self):

        selected_areas_idx = self.areas_cbo.currentIndex()
        if selected_areas_idx != 0:
            for i, areas_lyr in enumerate(self.areas_grps.values(), start=1):
                if i == selected_areas_idx:
                    self.lyrs.rollback_lyrs_edits(areas_lyr)
                    self.populate_cbos()

    def populate_cbos(self):
        selected_areas_idx = self.areas_cbo.currentIndex()
        if selected_areas_idx != 0:
            for i, (area_cbo, areas_lyr) in enumerate(self.areas_grp_cbo.items(), start=1):
                if i == selected_areas_idx:
                    qry = f"""SELECT fid FROM {areas_lyr};"""
                    rows = self.gutils.execute(qry).fetchall()
                    area_cbo.clear()
                    if not rows:
                        return
                    for row in rows:
                        area_cbo.addItem(str(row[0]))
                    area_cbo.setCurrentIndex(0)

    def populate_cbo_areas(self, area_cbo, eye_btn):
        if area_cbo == self.buildings_cbo:
            fid = self.buildings_cbo.currentText()
            if fid:
                qry = f"""SELECT adjustment_factor FROM buildings_areas WHERE fid = {fid};"""
                rows = self.gutils.execute(qry).fetchall()
                if rows:
                    if rows[0][0] is not None:
                        self.adj_factor_dsp.setValue(rows[0][0])
                    else:
                        self.adj_factor_dsp.setValue(0)
                else:
                    self.adj_factor_dsp.setValue(0)
                if eye_btn.isChecked():
                    lyr = self.lyrs.data['buildings_areas']["qlyr"]
                    selected_areas_fid = int(area_cbo.currentText())
                    self.lyrs.show_feat_rubber(lyr.id(), selected_areas_fid, QColor(Qt.red))
                    feat = next(lyr.getFeatures(QgsFeatureRequest(int(area_cbo.currentText()))))
                    x, y = feat.geometry().centroid().asPoint()
                    center_canvas(self.iface, x, y)
        elif area_cbo == self.shallown_cbo:
            fid = self.shallown_cbo.currentText()
            if fid:
                qry = f"""SELECT shallow_n FROM spatialshallow WHERE fid = {fid};"""
                rows = self.gutils.execute(qry).fetchall()
                if rows:
                    if rows[0][0] is not None:
                        self.shallown_dsb.setValue(rows[0][0])
                    else:
                        self.shallown_dsb.setValue(0)
                else:
                    self.shallown_dsb.setValue(0)
                if eye_btn.isChecked():
                    lyr = self.lyrs.data['spatialshallow']["qlyr"]
                    selected_areas_fid = int(area_cbo.currentText())
                    self.lyrs.show_feat_rubber(lyr.id(), selected_areas_fid, QColor(Qt.red))
                    feat = next(lyr.getFeatures(QgsFeatureRequest(int(area_cbo.currentText()))))
                    x, y = feat.geometry().centroid().asPoint()
                    center_canvas(self.iface, x, y)
        elif area_cbo == self.froude_cbo:
            fid = self.froude_cbo.currentText()
            if fid:
                qry = f"""SELECT froudefp FROM fpfroude WHERE fid = {fid};"""
                rows = self.gutils.execute(qry).fetchall()
                if rows:
                    if rows[0][0] is not None:
                        self.froud_dsb.setValue(rows[0][0])
                    else:
                        self.froud_dsb.setValue(0)
                else:
                    self.froud_dsb.setValue(0)
                if eye_btn.isChecked():
                    lyr = self.lyrs.data['fpfroude']["qlyr"]
                    selected_areas_fid = int(area_cbo.currentText())
                    self.lyrs.show_feat_rubber(lyr.id(), selected_areas_fid, QColor(Qt.red))
                    feat = next(lyr.getFeatures(QgsFeatureRequest(int(area_cbo.currentText()))))
                    x, y = feat.geometry().centroid().asPoint()
                    center_canvas(self.iface, x, y)
        elif area_cbo == self.tolerance_cbo:
            fid = self.tolerance_cbo.currentText()
            if fid:
                qry = f"""SELECT tol FROM tolspatial WHERE fid = {fid};"""
                rows = self.gutils.execute(qry).fetchall()
                if rows:
                    if rows[0][0] is not None:
                        self.tolerance_dsb.setValue(rows[0][0])
                    else:
                        self.tolerance_dsb.setValue(0)
                else:
                    self.tolerance_dsb.setValue(0)
                if eye_btn.isChecked():
                    lyr = self.lyrs.data['tolspatial']["qlyr"]
                    selected_areas_fid = int(area_cbo.currentText())
                    self.lyrs.show_feat_rubber(lyr.id(), selected_areas_fid, QColor(Qt.red))
                    feat = next(lyr.getFeatures(QgsFeatureRequest(int(area_cbo.currentText()))))
                    x, y = feat.geometry().centroid().asPoint()
                    center_canvas(self.iface, x, y)
        elif area_cbo == self.roughness_cbo:
            fid = self.roughness_cbo.currentText()
            if fid:
                qry = f"""SELECT n FROM user_roughness WHERE fid = {fid};"""
                rows = self.gutils.execute(qry).fetchall()
                if rows:
                    if rows[0][0] is not None:
                        self.mannings_dsb.setValue(rows[0][0])
                    else:
                        self.mannings_dsb.setValue(0)
                else:
                    self.mannings_dsb.setValue(0)
                if eye_btn.isChecked():
                    lyr = self.lyrs.data['user_roughness']["qlyr"]
                    selected_areas_fid = int(area_cbo.currentText())
                    self.lyrs.show_feat_rubber(lyr.id(), selected_areas_fid, QColor(Qt.red))
                    feat = next(lyr.getFeatures(QgsFeatureRequest(int(area_cbo.currentText()))))
                    x, y = feat.geometry().centroid().asPoint()
                    center_canvas(self.iface, x, y)
        elif area_cbo == self.blocked_cbo:
            fid = self.blocked_cbo.currentText()
            if fid:
                qry = f"""SELECT collapse, calc_arf, calc_wrf FROM user_blocked_areas WHERE fid = {fid};"""
                rows = self.gutils.execute(qry).fetchall()
                if rows:
                    self.collapse_chbox.setChecked(rows[0][0] == 1)
                    self.arf_chbox.setChecked(rows[0][1] == 1)
                    self.wrf_chbox.setChecked(rows[0][2] == 1)
                else:
                    self.collapse_chbox.setChecked(False)
                    self.arf_chbox.setChecked(False)
                    self.wrf_chbox.setChecked(False)
                if eye_btn.isChecked():
                    lyr = self.lyrs.data['user_blocked_areas']["qlyr"]
                    selected_areas_fid = int(area_cbo.currentText())
                    self.lyrs.show_feat_rubber(lyr.id(), selected_areas_fid, QColor(Qt.red))
                    feat = next(lyr.getFeatures(QgsFeatureRequest(int(area_cbo.currentText()))))
                    x, y = feat.geometry().centroid().asPoint()
                    center_canvas(self.iface, x, y)
        elif area_cbo == self.steep_slopen_cbo:
            fid = self.steep_slopen_cbo.currentText()
            if fid:
                qry = """SELECT COUNT(*) FROM user_steep_slope_n_areas WHERE global = 1;"""
                result = self.gutils.execute(qry).fetchone()
                if result and result[0] > 0:
                    self.steep_slopen_global_chbox.setChecked(True)
                else:
                    self.steep_slopen_global_chbox.setChecked(False)
                if eye_btn.isChecked():
                    lyr = self.lyrs.data['user_steep_slope_n_areas']["qlyr"]
                    selected_areas_fid = int(fid)
                    self.lyrs.show_feat_rubber(lyr.id(), selected_areas_fid, QColor(Qt.red))
                    feat = next(lyr.getFeatures(QgsFeatureRequest(selected_areas_fid)))
                    x, y = feat.geometry().centroid().asPoint()
                    center_canvas(self.iface, x, y)
        elif area_cbo == self.noexchange_cbo:
            if eye_btn.isChecked():
                lyr = self.lyrs.data['user_noexchange_chan_areas']["qlyr"]
                selected_areas_fid = int(area_cbo.currentText())
                self.lyrs.show_feat_rubber(lyr.id(), selected_areas_fid, QColor(Qt.red))
                feat = next(lyr.getFeatures(QgsFeatureRequest(int(area_cbo.currentText()))))
                x, y = feat.geometry().centroid().asPoint()
                center_canvas(self.iface, x, y)

    def delete_area_fid(self, area_cbo, area_lyr):
        selected_areas_fid = int(area_cbo.currentText())
        try:
            qry = f"DELETE FROM {area_lyr} WHERE fid = ?"
            self.gutils.execute(qry, (selected_areas_fid,))  # Use parameterized query
            self.populate_cbos()

            self.lyrs.lyrs_to_repaint = [self.lyrs.data[area_lyr]["qlyr"]]
            self.lyrs.repaint_layers()

            self.uc.bar_info(f"Fid {selected_areas_fid} was deleted from {area_lyr}!")
            self.uc.log_info(f"Fid {selected_areas_fid} was deleted from {area_lyr}!")
        except Exception as e:
            self.uc.bar_error(f"Error while deleting fid {selected_areas_fid} from {area_lyr}!")
            self.uc.log_info(f"Error while deleting fid {selected_areas_fid} from {area_lyr}!")

    def center_area_fid(self, area_cbo, area_eye, area_lyr):
        if area_eye.isChecked():
            area_eye.setChecked(True)
            lyr = self.lyrs.data[area_lyr]["qlyr"]
            selected_areas_fid = int(area_cbo.currentText())
            self.lyrs.show_feat_rubber(lyr.id(), selected_areas_fid, QColor(Qt.red))
            feat = next(lyr.getFeatures(QgsFeatureRequest(int(area_cbo.currentText()))))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            return
        else:
            area_eye.setChecked(False)
            self.lyrs.clear_rubber()
            return

    def save_building_adj_factor(self):
        """
        Updates the adjustment factor for a selected building area in the database.
        """
        fid_text = self.buildings_cbo.currentText()
        if fid_text:
            fid = int(fid_text)
            adj_factor = self.adj_factor_dsp.value()
            update_qry = f"""UPDATE buildings_areas SET adjustment_factor = {adj_factor} WHERE fid = {fid};"""
            self.gutils.execute(update_qry)

    def save_shallown(self):
        """
        Updates the shallow_n value for a selected spatial shallow area in the database.
        """
        fid_text = self.shallown_cbo.currentText()
        if fid_text:
            fid = int(fid_text)
            shallown = self.shallown_dsb.value()
            update_qry = f"""UPDATE spatialshallow SET shallow_n = {shallown} WHERE fid = {fid};"""
            self.gutils.execute(update_qry)

    def save_froude(self):
        """
        Updates the froude value for a selected area in the database.
        """
        fid_text = self.froude_cbo.currentText()
        if fid_text:
            fid = int(fid_text)
            froude = self.froud_dsb.value()
            update_qry = f"""UPDATE fpfroude SET froudefp = {froude} WHERE fid = {fid};"""
            self.gutils.execute(update_qry)

    def save_tolerance(self):
        """
        Updates the tolerance value for a selected area in the database.
        """
        fid_text = self.tolerance_cbo.currentText()
        if fid_text:
            fid = int(fid_text)
            tolerance = self.tolerance_dsb.value()
            update_qry = f"""UPDATE tolspatial SET tol = {tolerance} WHERE fid = {fid};"""
            self.gutils.execute(update_qry)

    def save_mannings(self):
        """
        Updates the Manning's n value for a selected area in the database.
        """
        fid_text = self.roughness_cbo.currentText()
        if fid_text:
            fid = int(fid_text)
            mannings = self.mannings_dsb.value()
            update_qry = f"""UPDATE user_roughness SET n = {mannings} WHERE fid = {fid};"""
            self.gutils.execute(update_qry)

    def save_blocked_areas(self):
        """
        Updates the blocked area properties for a selected area in the database.
        """
        fid_text = self.blocked_cbo.currentText()
        if fid_text:
            fid = int(fid_text)

            if self.collapse_chbox.isChecked():
                collapse_chbox_state = 1
            else:
                collapse_chbox_state = 0

            if self.arf_chbox.isChecked():
                arf_chbox_state = 1
            else:
                arf_chbox_state = 0

            if self.wrf_chbox.isChecked():
                wrf_chbox_state = 1
            else:
                wrf_chbox_state = 0

            update_qry = f"""UPDATE user_blocked_areas SET collapse = {collapse_chbox_state}, calc_arf = {arf_chbox_state}, calc_wrf = {wrf_chbox_state} WHERE fid = {fid};"""
            self.gutils.execute(update_qry)

    def save_global_steep_slopen(self):
        """
        Updates the global steep slope n value for a selected area in the database.
        """
        try:
            global_value = 1 if self.steep_slopen_global_chbox.isChecked() else 0
            qry = """UPDATE user_steep_slope_n_areas SET global = ?;"""
            self.gutils.execute(qry, (global_value,))
        except Exception as e:
            self.uc.bar_error(f"Error updating global steep slope n value!")
            self.uc.log_info(f"Error updating global steep slope n value!")

    def schematize_areas(self):
        """
        Schematizes the selected areas in the database.
        """
        selected_areas_idx = self.areas_cbo.currentIndex()
        if selected_areas_idx != 0:
            for i, areas_lyr in enumerate(self.areas_grps.values(), start=1):
                if i == selected_areas_idx:
                    if areas_lyr == 'buildings_areas':
                        pass
                    elif areas_lyr == 'spatialshallow':
                        pass
                    elif areas_lyr == 'fpfroude':
                        pass
                    elif areas_lyr == 'tolspatial':
                        pass
                    elif areas_lyr == 'user_roughness':
                        pass
                    elif areas_lyr == 'user_blocked_areas':
                        pass
                    elif areas_lyr == 'user_steep_slope_n_areas':
                        try:
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
                            self.uc.bar_info(f"Schematizing Steep Slope n Areas completed!")
                            self.uc.log_info(f"Schematizing Steep Slope n Areas completed!")
                        except Exception as e:
                            self.uc.bar_error(f"Error schematizing Steep Slope n Areas!")
                            self.uc.log_info(f"Error schematizing Steep Slope n Areas!")
                    elif areas_lyr == 'user_noexchange_chan_areas':
                        pass

    def delete_schematized_areas(self):
        selected_areas_idx = self.areas_cbo.currentIndex()
        if selected_areas_idx != 0:
            for i, areas_lyr in enumerate(self.areas_grps.values(), start=1):
                if i == selected_areas_idx:
                    if areas_lyr == 'buildings_areas':
                        pass
                    elif areas_lyr == 'spatialshallow':
                        pass
                    elif areas_lyr == 'fpfroude':
                        pass
                    elif areas_lyr == 'tolspatial':
                        pass
                    elif areas_lyr == 'user_roughness':
                        pass
                    elif areas_lyr == 'user_blocked_areas':
                        pass
                    elif areas_lyr == 'user_steep_slope_n_areas':
                        del_qry = """DELETE FROM steep_slope_n_cells;"""
                        self.gutils.execute(del_qry)
                        self.uc.bar_info(f"Schematized Steep Slope n Areas deleted!")
                        self.uc.log_info(f"Schematized Steep Slope n Areas deleted!")
                    elif areas_lyr == 'user_noexchange_chan_areas':
                        pass







