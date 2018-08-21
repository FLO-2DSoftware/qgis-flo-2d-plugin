# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import traceback
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QFileDialog
from .ui_utils import load_ui
from ..flo2d_tools.elevation_correctors import LeveesElevation
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY

uiDialog, qtBaseClass = load_ui('levees_elevation')


class LeveesToolDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.gutils = GeoPackageUtils(con, iface)
        self.corrector = LeveesElevation(self.gutils, self.lyrs)
        self.corrector.setup_layers()
        self.methods = {}

        # connections
        self.elev_polygons_chbox.stateChanged.connect(self.polygons_checked)
        self.elev_points_chbox.stateChanged.connect(self.points_checked)
        self.elev_lines_chbox.stateChanged.connect(self.lines_checked)

        self.elev_polygons_chbox.setChecked(True)
        self.elev_points_chbox.setChecked(True)
        self.elev_lines_chbox.setChecked(True)

        self.browse_btn.clicked.connect(self.get_xyz_file)
        self.xyz_line.textChanged.connect(self.activate_import)
        self.import_btn.clicked.connect(self.run_import_z)

    def get_xyz_file(self):
        s = QSettings()
        last_dir = s.value('FLO-2D/lastXYZDir', '')
        xyz_file, __ = QFileDialog.getOpenFileName(
            None,
            'Select 3D levee lines file',
            directory=last_dir,
            filter='*.xyz')
        if not xyz_file:
            return
        self.xyz_line.setText(xyz_file)
        s.setValue('FLO-2D/lastXYZDir', os.path.dirname(xyz_file))

    def activate_import(self):
        if self.xyz_line.text():
            self.import_btn.setEnabled(True)
        else:
            self.import_btn.setDisabled(True)

    def run_import_z(self):
        try:
            self.import_z_data()
            self.uc.bar_info('3D levee lines data imported!')
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.bar_warn('Could not import 3D levee lines data!')

    def import_z_data(self):
        elev_points_lyr = self.lyrs.data['user_elevation_points']['qlyr']
        levee_line_lyr = self.lyrs.data['user_levee_lines']['qlyr']

        elev_fields = elev_points_lyr.fields()
        levee_fields = levee_line_lyr.fields()

        elev_points_lyr.startEditing()
        levee_line_lyr.startEditing()

        fpath = self.xyz_line.text()
        with open(fpath, 'r') as xyz_file:
            polyline = []
            while True:
                try:
                    row = next(xyz_file)
                    values = row.split()
                    x, y, z = [float(i) for i in values]
                    point_feat = QgsFeature()
                    pnt = QgsPointXY(x, y)
                    point_geom = QgsGeometry().fromPointXY(pnt)
                    point_feat.setGeometry(point_geom)
                    point_feat.setFields(elev_fields)
                    point_feat.setAttribute('elev', z)
                    point_feat.setAttribute('membership', 'levees')
                    elev_points_lyr.addFeature(point_feat)
                    polyline.append(pnt)
                except (ValueError, StopIteration) as e:
                    if not polyline:
                        break
                    line_feat = QgsFeature()
                    line_geom = QgsGeometry().fromPolylineXY(polyline)
                    line_feat.setGeometry(line_geom)
                    line_feat.setFields(levee_fields)
                    levee_line_lyr.addFeature(line_feat)
                    del polyline[:]
        elev_points_lyr.commitChanges()
        elev_points_lyr.updateExtents()
        elev_points_lyr.triggerRepaint()
        elev_points_lyr.removeSelection()

        levee_line_lyr.commitChanges()
        levee_line_lyr.updateExtents()
        levee_line_lyr.triggerRepaint()
        levee_line_lyr.removeSelection()

    def points_checked(self):
        if self.elev_points_chbox.isChecked():
            self.buffer_size.setEnabled(True)
            if self.buffer_size.value() == 0:
                val = float(self.gutils.get_cont_par('CELLSIZE'))
                self.buffer_size.setValue(val)
            else:
                pass
            self.methods[2] = self.elev_from_points
        else:
            self.buffer_size.setDisabled(True)
            self.methods.pop(2)

    def lines_checked(self):
        if self.elev_lines_chbox.isChecked():
            self.methods[1] = self.elev_from_lines
        else:
            self.methods.pop(1)

    def polygons_checked(self):
        if self.elev_polygons_chbox.isChecked():
            self.methods[3] = self.elev_from_polys
        else:
            self.methods.pop(3)

    def elev_from_points(self):
        try:
            self.corrector.set_filter()
            self.corrector.elevation_from_points(self.buffer_size.value())
        finally:
            self.corrector.clear_filter()

    def elev_from_lines(self):
        self.corrector.elevation_from_lines()

    def elev_from_polys(self):
        try:
            self.corrector.set_filter()
            self.corrector.elevation_from_polygons()
        finally:
            self.corrector.clear_filter()
