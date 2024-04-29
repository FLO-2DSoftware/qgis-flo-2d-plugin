# -*- coding: utf-8 -*-
import csv

from PyQt5.QtCore import QVariant
from PyQt5.QtWidgets import QFileDialog, QProgressDialog, QApplication
from qgis._core import QgsVectorLayer, QgsProject, QgsField, QgsExpression, QgsExpressionContext, \
    QgsExpressionContextUtils, QgsWkbTypes
# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import processing

from qgis.core import QgsFeatureRequest
from qgis.PyQt.QtWidgets import QInputDialog

from ..flo2dobjects import Reservoir, Tailings
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..utils import is_number
from .ui_utils import center_canvas, load_ui, set_icon

uiDialog, qtBaseClass = load_ui("ic_editor")


class ICEditorWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.con = None
        self.gutils = None
        self.uc = UserCommunication(iface, "FLO-2D")

        self.res_lyr = self.lyrs.data["user_reservoirs"]["qlyr"]
        self.chan_lyr = self.lyrs.data["chan"]["qlyr"]
        self.tal_lyr = self.lyrs.data["user_tailings"]["qlyr"]

        # connections Reservoir
        self.add_user_res_btn.clicked.connect(self.create_user_res)
        self.revert_res_changes_btn.clicked.connect(self.revert_res_lyr_edits)
        self.schem_res_btn.clicked.connect(self.schematize_res)
        self.delete_schem_res_btn.clicked.connect(self.delete_schematize_res)
        self.rename_res_btn.clicked.connect(self.rename_res)
        self.delete_res_btn.clicked.connect(self.delete_cur_res)
        self.clear_res_rb_btn.clicked.connect(self.lyrs.clear_rubber)
        self.res_cbo.activated.connect(self.cur_res_changed)
        self.res_ini_sbox.editingFinished.connect(self.save_res)
        self.chan_seg_cbo.activated.connect(self.cur_seg_changed)
        self.seg_ini_sbox.editingFinished.connect(self.save_chan_seg)

        # connections Channels
        self.clear_chan_rb_btn.clicked.connect(self.lyrs.clear_rubber)

        # connections Tailings
        self.add_tailings_btn.clicked.connect(self.create_tailings)
        self.revert_tal_changes_btn.clicked.connect(self.revert_tal_lyr_edits)
        self.delete_tailings_btn.clicked.connect(self.delete_tailings)
        self.delete_schem_tal_btn.clicked.connect(self.delete_schematize_tal)
        self.schem_tal_btn.clicked.connect(self.schematize_tal)
        self.tailings_cbo.activated.connect(self.cur_tal_changed)
        self.rename_tal_btn.clicked.connect(self.rename_tal)
        self.clear_tal_rb_btn.clicked.connect(self.lyrs.clear_rubber)
        # self.export_tailings_btn.clicked.connect(self.export_tailings)
        # self.center_tal_chbox.clicked.connect(self. )
        # self.user_polygon_cb.stateChanged.connect(self.populate_tailings_cbo)

    def populate_cbos(self, fid=None, show_last_edited=False):
        if not self.iface.f2d["con"]:
            return

        self.gutils = GeoPackageUtils(self.iface.f2d["con"], self.iface)
        # reservoir
        self.res_cbo.clear()
        res_qry = """SELECT fid, name FROM user_reservoirs ORDER BY name COLLATE NOCASE"""
        rows = self.gutils.execute(res_qry).fetchall()
        max_fid = self.gutils.get_max("user_reservoirs")
        cur_res_idx = 0
        for i, row in enumerate(rows):
            self.res_cbo.addItem(row[1], row[0])
            if fid and row[0] == fid:
                cur_res_idx = i
            elif show_last_edited and row[0] == max_fid:
                cur_res_idx = i
        self.res_cbo.setCurrentIndex(cur_res_idx)
        self.cur_res_changed(cur_res_idx)
        # channel
        self.chan_seg_cbo.clear()
        seg_qry = """SELECT fid, name FROM chan ORDER BY name COLLATE NOCASE"""
        rows = self.gutils.execute(seg_qry).fetchall()
        for i, row in enumerate(rows):
            self.chan_seg_cbo.addItem(row[1], row[0])
        # tailings
        self.tailings_cbo.clear()
        tal_qry = """SELECT fid, name FROM user_tailings ORDER BY name COLLATE NOCASE"""
        rows = self.gutils.execute(tal_qry).fetchall()
        for i, row in enumerate(rows):
            self.tailings_cbo.addItem(row[1], row[0])
        self.cur_tal_changed(cur_res_idx)

    def cur_res_changed(self, cur_idx):
        wsel = -1.0
        self.res_fid = self.res_cbo.itemData(self.res_cbo.currentIndex())
        self.reservoir = Reservoir(self.res_fid, self.iface.f2d["con"], self.iface)
        self.reservoir.get_row()
        if is_number(self.reservoir.wsel):
            wsel = float(self.reservoir.wsel)
        self.res_ini_sbox.setValue(wsel)
        self.show_res_rb()
        if self.center_res_chbox.isChecked():
            feat = next(self.res_lyr.getFeatures(QgsFeatureRequest(self.reservoir.fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def cur_seg_changed(self, cur_idx):
        depini = -1.0
        self.seg_fid = self.chan_seg_cbo.itemData(self.chan_seg_cbo.currentIndex())
        qry = "SELECT depinitial FROM chan WHERE fid = ?;"
        di = self.gutils.execute(qry, (self.seg_fid,)).fetchone()
        if di and is_number(di[0]):
            depini = float(di[0])
        self.seg_ini_sbox.setValue(depini)
        self.show_chan_rb()
        if self.center_seg_chbox.isChecked():
            feat = next(self.chan_lyr.getFeatures(QgsFeatureRequest(self.seg_fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def cur_tal_changed(self, cur_idx):
        tailings_surf_elev = 0
        water_surf_elev = 0
        concentration = 0
        self.tal_fid = self.tailings_cbo.itemData(self.tailings_cbo.currentIndex())
        self.tailings = Tailings(self.tal_fid, self.iface.f2d["con"], self.iface)
        self.tailings.get_row()
        if is_number(self.tailings.tailings_surf_elev):
            tailings_surf_elev = float(self.tailings.tailings_surf_elev)
        if is_number(self.tailings.water_surf_elev):
            water_surf_elev = float(self.tailings.water_surf_elev)
        if is_number(self.tailings.concentration):
            concentration = float(self.tailings.concentration)
        self.tailings_elev_sb.setValue(tailings_surf_elev)
        self.wse_sb.setValue(water_surf_elev)
        self.concentration_sb.setValue(concentration)
        self.show_tal_rb()

        if self.center_res_chbox.isChecked():
            feat = next(self.tal_lyr.getFeatures(QgsFeatureRequest(self.tailings.fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def show_res_rb(self):
        if not self.reservoir.fid:
            return
        self.lyrs.show_feat_rubber(self.res_lyr.id(), self.reservoir.fid)

    def show_tal_rb(self):
        if not self.tailings.fid:
            return
        self.lyrs.show_feat_rubber(self.tal_lyr.id(), self.tailings.fid)

    def show_chan_rb(self):
        if not self.seg_fid:
            return
        self.lyrs.show_feat_rubber(self.chan_lyr.id(), self.seg_fid)

    def create_user_res(self):

        if self.lyrs.any_lyr_in_edit('user_reservoirs'):
            self.uc.bar_info(f"Reservoir saved!")
            self.uc.log_info(f"Reservoir saved!")
            self.lyrs.save_lyrs_edits('user_reservoirs')
            self.add_user_res_btn.setChecked(False)
            self.gutils.fill_empty_reservoir_names()
            self.populate_cbos()
            return
        else:
            self.lyrs.enter_edit_mode("user_reservoirs")

    def save_res_lyr_edits(self):
        if not self.gutils or not self.lyrs.any_lyr_in_edit("user_reservoirs"):
            return
        self.gutils.delete_imported_reservoirs()
        # try to save user bc layers (geometry additions/changes)
        user_res_edited = self.lyrs.save_lyrs_edits("user_reservoirs")
        # if user reservoirs layer was edited
        if user_res_edited:
            self.gutils.fill_empty_reservoir_names()
            # populate widgets and show last edited reservoir
            self.populate_cbos(show_last_edited=True)

    def rename_res(self):
        if not self.res_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, "Change name", "New name:")
        if not ok or not new_name:
            return
        if not self.res_cbo.findText(new_name) == -1:
            msg = "WARNING 060319.1722: Reservoir with name {} already exists in the database. Please, choose another name.".format(
                new_name
            )
            self.uc.show_warn(msg)
            return
        self.reservoir.name = new_name
        self.save_res()

    def rename_tal(self):
        if not self.tailings_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, "Change name", "New name:")
        if not ok or not new_name:
            return
        if not self.tailings_cbo.findText(new_name) == -1:
            msg = "WARNING 060319.1722: Tailings with name {} already exists in the database. Please, choose another name.".format(
                new_name
            )
            self.uc.show_warn(msg)
            return
        self.tailings.name = new_name
        self.save_tal()

    def repaint_reservoirs(self):
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data["reservoirs"]["qlyr"],
            self.lyrs.data["user_reservoirs"]["qlyr"],
        ]
        self.lyrs.repaint_layers()

    def repaint_tailings(self):
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data["user_tailings"]["qlyr"],
            self.lyrs.data["tailing_cells"]["qlyr"],
        ]
        self.lyrs.repaint_layers()

    def revert_res_lyr_edits(self):
        user_res_edited = self.lyrs.rollback_lyrs_edits("user_reservoirs")
        if user_res_edited:
            self.add_user_res_btn.setChecked(False)
            self.populate_cbos()

    def revert_tal_lyr_edits(self):
        user_tal_edited = self.lyrs.rollback_lyrs_edits("user_tailings")
        if user_tal_edited:
            self.add_tailings_btn.setChecked(False)
            self.populate_cbos()

    def delete_cur_res(self):
        if not self.res_cbo.count():
            return
        q = "Are you sure you want delete the current reservoir?"
        if not self.uc.question(q):
            return
        self.reservoir.del_row()
        self.repaint_reservoirs()
        self.lyrs.clear_rubber()
        self.populate_cbos()

    def delete_schematize_res(self):
        """
        Function to delete the schematic data related to reservoirs
        """
        user_rsvs = self.gutils.execute("SELECT Count(*) FROM reservoirs").fetchone()[0]
        if user_rsvs > 0:
            self.gutils.execute("DELETE FROM reservoirs;")
            self.repaint_reservoirs()
            self.lyrs.clear_rubber()
            self.uc.bar_info(f"{user_rsvs} schematized reservoirs deleted!")
            self.uc.log_info(f"{user_rsvs} schematized reservoirs deleted!")

    def delete_schematize_tal(self):
        """
        Function to delete the schematic data related to tailings
        """
        user_tal = self.gutils.execute("SELECT Count(*) FROM tailing_cells").fetchone()[0]
        if user_tal > 0:
            self.gutils.execute("DELETE FROM tailing_cells;")
            self.repaint_tailings()
            self.lyrs.clear_rubber()
            self.uc.bar_info(f"{user_tal} schematized tailings deleted!")
            self.uc.log_info(f"{user_tal} schematized tailings deleted!")

    def schematize_res(self):
        user_rsvs = self.gutils.execute("SELECT Count(*) FROM user_reservoirs").fetchone()[0]
        if user_rsvs > 0:
            ins_qry = """INSERT INTO reservoirs (user_res_fid, name, grid_fid, wsel, n_value, use_n_value, tailings, geom)
                        SELECT
                            ur.fid, ur.name, g.fid, ur.wsel, ur.n_value, ur.use_n_value, ur.tailings, g.geom
                        FROM
                            grid AS g, user_reservoirs AS ur
                        WHERE
                            ST_Intersects(CastAutomagic(g.geom), CastAutomagic(ur.geom));"""

            self.gutils.execute("DELETE FROM reservoirs;")
            self.gutils.execute(ins_qry)
            self.repaint_reservoirs()
            self.uc.bar_info(str(user_rsvs) + " user reservoirs schematized!")
            self.uc.log_info(str(user_rsvs) + " user reservoirs schematized!")
        else:
            sch_rsvs = self.gutils.execute("SELECT Count(*) FROM reservoirs").fetchone()[0]
            if sch_rsvs > 0:
                if self.uc.question(
                        "There aren't any user reservoirs."
                        + "\nBut there are "
                        + str(sch_rsvs)
                        + " schematic reservoirs."
                        + "\n\nDo you want to delete them?"
                ):
                    self.gutils.execute("DELETE FROM reservoirs;")
                    self.repaint_reservoirs()
            else:
                self.uc.bar_warn("There aren't any user reservoirs!")

    def schematize_tal(self):
        """
        Function to schematize the tailings
        """
        user_tal = self.gutils.execute("SELECT Count(*) FROM user_tailings").fetchone()[0]
        if user_tal > 0:
            ins_qry = """INSERT INTO tailing_cells (user_tal_fid, name, grid, tailings_surf_elev, water_surf_elev, concentration, geom)
                        SELECT
                            ut.fid, ut.name, g.fid, ut.tailings_surf_elev, ut.water_surf_elev, ut.concentration, g.geom
                        FROM
                            grid AS g, user_tailings AS ut
                        WHERE
                            ST_Intersects(CastAutomagic(g.geom), CastAutomagic(ut.geom));
                        """

            self.gutils.execute("DELETE FROM tailing_cells;")
            self.gutils.execute(ins_qry)
            self.repaint_tailings()
            self.uc.bar_info(str(user_tal) + " user tailings schematized!")
            self.uc.log_info(str(user_tal) + " user tailings schematized!")
        else:
            sch_tal = self.gutils.execute("SELECT Count(*) FROM tailing_cells").fetchone()[0]
            if sch_tal > 0:
                if self.uc.question(
                        "There aren't any user tailings."
                        + "\nBut there are "
                        + str(sch_tal)
                        + " schematic tailings."
                        + "\n\nDo you want to delete them?"
                ):
                    self.gutils.execute("DELETE FROM tailing_cells;")
                    self.repaint_tailings()
            else:
                self.uc.bar_warn("There aren't any user tailings!")
                self.uc.log_info("There aren't any user tailings!")

    def save_res(self):
        self.reservoir.wsel = self.res_ini_sbox.value()
        self.reservoir.set_row()
        self.populate_cbos(fid=self.reservoir.fid)

    def save_tal(self):
        self.tailings.tailings_surf_elev = self.tailings_elev_sb.value()
        self.tailings.water_surf_elev = self.wse_sb.value()
        self.tailings.concentration = self.concentration_sb.value()
        self.tailings.set_row()
        self.populate_cbos(fid=self.tailings.fid)

    def save_chan_seg(self):
        fid = self.chan_seg_cbo.itemData(self.chan_seg_cbo.currentIndex())
        dini = self.seg_ini_sbox.value()
        qry = "UPDATE chan SET depinitial = ? WHERE fid = ?;"
        if fid:
            if fid > 0:
                self.gutils.execute(
                    qry,
                    (
                        dini,
                        fid,
                    ),
                )

    def save_seg_init_depth(self):
        pass

    def create_tailings(self):
        """
        Start editing tailings
        """
        if self.lyrs.any_lyr_in_edit('user_tailings'):
            self.uc.bar_info(f"Tailings saved!")
            self.uc.log_info(f"Tailings saved!")
            self.lyrs.save_lyrs_edits('user_tailings')
            self.add_tailings_btn.setChecked(False)
            self.gutils.fill_empty_tailings_names()
            self.populate_cbos()
            return
        else:
            self.lyrs.enter_edit_mode("user_tailings")

    def save_tailings_edits(self):
        """
        Save the tailings shapefile
        """
        self.tal_lyr.commitChanges()
        self.tailings_cbo.clear()
        self.tailings_cbo.addItem(self.tal_lyr.name(), self.tal_lyr.dataProvider().dataSourceUri())

        # enable the elevations
        self.tailings_elev_sb.setEnabled(True)
        self.wse_sb.setEnabled(True)
        self.export_tailings_btn.setEnabled(True)
        self.concentration_sb.setEnabled(True)
        self.label_3.setEnabled(True)
        self.label_4.setEnabled(True)
        self.label_5.setEnabled(True)

    def delete_tailings(self):
        """
        Delete tailings
        """
        if not self.tailings_cbo.count():
            return
        q = "Are you sure you want delete the current tailings?"
        if not self.uc.question(q):
            return
        self.tailings.del_row()
        self.repaint_tailings()
        self.lyrs.clear_rubber()
        self.populate_cbos()

    def populate_tailings_cbo(self):
        """
        Function to populate the tailings cbo once the saving is finished
        """
        self.tailings_cbo.clear()
        if self.user_polygon_cb.isChecked():
            for layer_id, layer in QgsProject.instance().mapLayers().items():
                if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                   if layer.featureCount() > 0: 
                       self.tailings_cbo.addItem(layer.name())
            self.tailings_cbo.setCurrentIndex(0)
            self.tailings_cbo.setEnabled(True)
            self.tailings_elev_sb.setEnabled(True)
            self.wse_sb.setEnabled(True)
            self.export_tailings_btn.setEnabled(True)
            self.concentration_sb.setEnabled(True)
            self.label_5.setEnabled(True)
            self.label_3.setEnabled(True)
            self.label_4.setEnabled(True)
            self.tailings_cbo.setEnabled(True)
            self.add_tailings_btn.setEnabled(False)
            self.save_tailings_btn.setEnabled(False)
            self.delete_tailings_btn.setEnabled(False)

        else:
            self.tailings_elev_sb.setEnabled(False)
            self.wse_sb.setEnabled(False)
            self.export_tailings_btn.setEnabled(False)
            self.concentration_sb.setEnabled(False)
            self.label_5.setEnabled(False)
            self.label_3.setEnabled(False)
            self.label_4.setEnabled(False)
            self.tailings_cbo.setEnabled(False)
            self.add_tailings_btn.setEnabled(True)
            self.save_tailings_btn.setEnabled(True)
            self.delete_tailings_btn.setEnabled(True)

    def export_tailings(self):
        """
        Function to export the TAILINGS_STACK_DEPTH.DAT
        """
        tailings_elevation = self.tailings_elev_sb.value()
        wse = self.wse_sb.value()
        cv = self.concentration_sb.value()

        # check the elevations
        if wse != 0 and tailings_elevation > wse:
            self.uc.show_warn("Water Surface Elevation should be greater than Tailings elevations. ")
            return

        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.Directory)
        file_dialog.setOption(QFileDialog.ShowDirsOnly, True)
        file_dialog.setWindowTitle("Select export folder")

        if file_dialog.exec_():
            folder_path = file_dialog.selectedFiles()[0]

            pd = QProgressDialog("Processing Tailings files...", None, 0, 1)
            pd.setModal(True)
            pd.setValue(0)
            pd.show()
            QApplication.processEvents()

            exported_data = self.create_tailings_table(tailings_elevation, wse)

            pd.setValue(1)

            # Two-phase
            if wse != 0:
                export_tsd_path = f"{folder_path}/TAILINGS_STACK_DEPTH.DAT"
                with open(export_tsd_path, 'w') as txt_file:
                    for row in exported_data:
                        id_value = str(row[0]).rjust(10)
                        formatted_values = [f"{value:.3f}".rjust(10) for value in row[1:]]
                        line = f"{id_value}{' '.join(formatted_values)}"
                        txt_file.write(line + '\n')

            # pd.setValue(2)
            # export_t_path = f"{folder_path}/TAILINGS.DAT"
            # with open(export_t_path, 'w') as txt_file:
            #     for row in exported_data:
            #         id_value = str(row[0]).rjust(10)
            #         formatted_values = [f"{row[2]:.3f}".rjust(10)]
            #         line = f"{id_value}{' '.join(formatted_values)}"
            #         txt_file.write(line + '\n')

            else:
                if cv == 0:
                    self.uc.show_warn("For dry stack, concentration must be defined.")
                    return
                else:
                    export_tcv_path = f"{folder_path}/TAILINGS_CV.DAT"
                    with open(export_tcv_path, 'w') as txt_file:
                        for row in exported_data:
                            id_value = str(row[0]).rjust(10)
                            formatted_values = [f"{row[2]:.3f}".rjust(10)]
                            formatted_cv = f"{cv:.3f}".rjust(10)
                            line = f"{id_value}{' '.join(formatted_values)}{formatted_cv}"
                            txt_file.write(line + '\n')

            self.uc.log_info("Export complete!")
            self.uc.bar_info("Export complete!")
            if self.uc.question(f"Would you like to remove the intermediate calculation shapefiles?"):
                QgsProject.instance().removeMapLayers([self.tal_lyr.id()])
                self.tailings_cbo.clear()
                self.iface.mapCanvas().refreshAllLayers()
                return
            return
        else:
            self.uc.show_warn("Save canceled.")
            return

    def create_tailings_table(self, tailings_elevation, wse):
        """
        Function to create the TAILINGS_STACK_DEPTH.DAT
        """
        if self.user_polygon_cb.isChecked():
            selected_layer_name = self.tailings_cbo.currentText()
            self.tal_lyr = QgsProject.instance().mapLayersByName(selected_layer_name)[0]

        grid = self.lyrs.get_layer_by_name("Grid", self.lyrs.group).layer()

        intersection = processing.run("native:intersection", {'INPUT': grid,
                                                              'OVERLAY': self.tal_lyr,
                                                              'INPUT_FIELDS': ['fid', 'elevation'],
                                                              'OVERLAY_FIELDS': [],
                                                              'OVERLAY_FIELDS_PREFIX': '',
                                                              'OUTPUT': 'TEMPORARY_OUTPUT',
                                                              'GRID_SIZE': None})['OUTPUT']

        intersection_pv = intersection.dataProvider()
        intersection_pv.addAttributes([QgsField("tailings_depth", QVariant.Double)])
        intersection_pv.addAttributes([QgsField("water_depth", QVariant.Double)])
        intersection.updateFields()

        intersection.startEditing()
        elev_field_index = intersection.fields().indexFromName("tailings_depth")
        water_field_index = intersection.fields().indexFromName("water_depth")

        elev_expression = QgsExpression(
            f'IF({tailings_elevation} - "elevation" > 0, {tailings_elevation} - "elevation", 0)')
        water_expression = QgsExpression(
            f'IF({wse} - "elevation" > 0, IF({tailings_elevation} - "elevation" > 0,{wse} - {tailings_elevation}, {wse} - "elevation"), 0)')

        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(intersection))

        for feature in intersection.getFeatures():
            context.setFeature(feature)
            feature[elev_field_index] = round(elev_expression.evaluate(context), 2)
            feature[water_field_index] = round(water_expression.evaluate(context), 2)
            intersection.updateFeature(feature)

        intersection.commitChanges()

        # delete features that does not have water and tailings depth
        features_to_delete = []

        for feature in intersection.getFeatures():
            if feature["tailings_depth"] == 0 and feature["water_depth"] == 0:
                features_to_delete.append(feature.id())

        intersection.startEditing()
        intersection.deleteFeatures(features_to_delete)
        intersection.commitChanges()

        # join layer with grid
        joined_grid = processing.run("native:joinattributestable", {'INPUT': grid,
                                                                    'FIELD': 'fid',
                                                                    'INPUT_2': intersection,
                                                                    'FIELD_2': 'fid',
                                                                    'FIELDS_TO_COPY': [],
                                                                    'METHOD': 1,
                                                                    'DISCARD_NONMATCHING': False,
                                                                    'PREFIX': '',
                                                                    'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        fields_to_export = ['fid', 'water_depth', 'tailings_depth']

        exported_data = []

        for feature in joined_grid.getFeatures():
            feature_data = []
            for field_name in fields_to_export:
                field_value = feature[field_name]
                if str(field_value) == "NULL":
                    field_value = 0
                feature_data.append(field_value)
            exported_data.append(feature_data)

        return exported_data
