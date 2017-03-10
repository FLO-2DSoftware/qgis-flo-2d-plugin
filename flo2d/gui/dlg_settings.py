# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os
import time
from itertools import chain
from PyQt4.QtCore import Qt, QSettings
from PyQt4.QtGui import QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox, QFileDialog, QApplication
from qgis.core import QgsCoordinateReferenceSystem, QGis
from qgis.gui import QgsProjectionSelectionWidget

from .utils import load_ui
from ..flo2d_parser import ParseDAT
from ..geopackage_utils import GeoPackageUtils, database_disconnect, database_connect, database_create
from ..user_communication import UserCommunication


uiDialog, qtBaseClass = load_ui('settings')


class SettingsDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs, gutils):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.setModal(True)
        self.con = con
        self.parser = ParseDAT()
        self.lyrs = lyrs
        self.gutils = gutils
        self.si_units = None
        self.crs = None
        self.projectionSelector = QgsProjectionSelectionWidget()
        self.projectionSelector.setCrs(self.iface.mapCanvas().mapRenderer().destinationCrs())
        self.setup()

        # connection
        self.gpkgCreateBtn.clicked.connect(self.create_db)
        self.gpkgOpenBtn.clicked.connect(self.connect)

    def set_default_controls(self, con):
        qry = '''INSERT INTO cont (name, note) VALUES (?,?);'''
        cont_rows = self.parser.cont_rows
        toler_rows = self.parser.toler_rows
        parameters = chain(chain.from_iterable(cont_rows), chain.from_iterable(toler_rows))
        values = ((param, GeoPackageUtils.PARAMETER_DESCRIPTION[param]) for param in parameters)
        con.executemany(qry, values)

    def read(self):
        proj = self.gutils.get_cont_par('PROJ')
        cs = QgsCoordinateReferenceSystem()
        cs.createFromProj4(proj)
        self.projectionSelector.setCrs(cs)
        self.crs = self.projectionSelector.crs()
        if self.gutils.get_cont_par('METRIC') == '1':
            self.si_units = True
        elif self.gutils.get_cont_par('METRIC') == '0':
            self.si_units = False
        else:
            pass
        if self.crs:
            pd = self.crs.description()
        else:
            pd = '----'
        self.proj_lab.setText(pd)
        if self.si_units == True:
            mu = 'meters'
        elif self.si_units == False:
            mu = 'feet'
        else:
            mu = '----'
        self.unit_lab.setText(mu)

    def setup(self):
        if not self.gutils:
            return
        self.gutils.path = self.gutils.get_gpkg_path()
        self.gpkgPathEdit.setText(self.gutils.path)
        self.gutils = GeoPackageUtils(self.con, self.iface)
        self.read()

    def create_db(self):
        """
        Create FLO-2D model database (GeoPackage).
        """
        s = QSettings()
        last_gpkg_dir = s.value('FLO-2D/lastGpkgDir', '')
        gpkg_path = QFileDialog.getSaveFileName(None,
                                                'Create GeoPackage As...',
                                                directory=last_gpkg_dir, filter='*.gpkg')
        if not gpkg_path:
            return
        else:
            pass

        s.setValue('FLO-2D/lastGpkgDir', os.path.dirname(gpkg_path))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        start_time = time.time()
        con = database_create(gpkg_path)
        self.uc.log_info('{0:.3f} seconds => database create'.format(time.time() - start_time))
        if not con:
            self.uc.show_warn("Couldn't create new database {}".format(gpkg_path))
            return
        else:
            self.uc.log_info("Connected to {}".format(gpkg_path))
        # Inserting default values into the 'cont' table.
        self.set_default_controls(con)

        start_time = time.time()
        gutils = GeoPackageUtils(con, self.iface)
        if gutils.check_gpkg():
            self.uc.bar_info("GeoPackage {} is OK".format(gpkg_path))
            gutils.path = gpkg_path
            self.gpkgPathEdit.setText(gutils.path)
        else:
            self.uc.bar_error("{} is NOT a GeoPackage!".format(gpkg_path))
        QApplication.restoreOverrideCursor()
        self.uc.log_info('{0:.3f} seconds => create gutils '.format(time.time() - start_time))
        # CRS
        self.projectionSelector.selectCrs()
        start_time = time.time()
        if self.projectionSelector.crs().isValid():
            self.crs = self.projectionSelector.crs()
            auth, crsid = self.crs.authid().split(':')
            self.proj_lab.setText(self.crs.description())
            if self.crs.mapUnits() == QGis.Meters:
                self.si_units = True
                mu = 'meters'
            elif self.crs.mapUnits() == QGis.Feet:
                self.si_units = False
                mu = 'feet'
            else:
                msg = 'Unknown map units. Choose a different projection!'
                self.uc.show_warn(msg)
                return
            self.unit_lab.setText(mu)
            proj4 = self.crs.toProj4()

            # check if the CRS exist in the db
            sql = 'SELECT * FROM gpkg_spatial_ref_sys WHERE srs_id=?;'
            rc = gutils.execute(sql, (crsid,))
            rt = rc.fetchone()
            if not rt:
                sql = '''INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)'''
                data = (self.crs.description(), crsid, auth, crsid, proj4, '')
                rc = gutils.execute(sql, data)
                del rc
                srsid = crsid
            else:
                q = 'There is a coordinate system defined in the GeoPackage.\n'
                q += 'Would you like to use it?\n\nDetails:\n'
                q += 'Name: {}\n'.format(rt[0])
                q += 'SRS id: {}\n'.format(rt[1])
                q += 'Organization: {}\n'.format(rt[2])
                q += 'Organization id: {}\n'.format(rt[3])
                q += 'Definition: {}'.format(rt[4])
                if self.uc.question(q):
                    srsid = rt[1]
                else:
                    return
        else:
            msg = 'Choose a valid CRS!'
            self.uc.show_warn(msg)
            return
        if self.con:
            database_disconnect(self.con)
        self.gpkg_path = gpkg_path
        self.con = con
        self.gutils = gutils
        if self.si_units:
            self.gutils.set_cont_par('METRIC', 1)
        else:
            self.gutils.set_cont_par('METRIC', 0)

        QApplication.setOverrideCursor(Qt.WaitCursor)
        # assign the CRS to all geometry columns
        sql = "UPDATE gpkg_geometry_columns SET srs_id = ?"
        self.gutils.execute(sql, (srsid,))
        sql = "UPDATE gpkg_contents SET srs_id = ?"
        self.gutils.execute(sql, (srsid,))
        self.uc.log_info('{0:.3f} seconds => spatial ref of tables'.format(time.time() - start_time))
        self.srs_id = srsid

        start_time = time.time()
        self.lyrs.load_all_layers(self.gutils)
        self.lyrs.zoom_to_all()
        QApplication.restoreOverrideCursor()
        self.uc.log_info('{0:.3f} seconds => loading layers'.format(time.time() - start_time))

    def connect(self, gpkg_path=None):
        """
        Connect to FLO-2D model database (GeoPackage).
        """
        s = QSettings()
        last_gpkg_dir = s.value('FLO-2D/lastGpkgDir', '')
        if not gpkg_path:
            gpkg_path = QFileDialog.getOpenFileName(None,
                                                    'Select GeoPackage to connect',
                                                    directory=last_gpkg_dir, filter='*.gpkg')
        if not gpkg_path:
            return
        else:
            pass
        if self.con:
            database_disconnect(self.con)
        self.gpkg_path = gpkg_path
        s.setValue('FLO-2D/lastGpkgDir', os.path.dirname(self.gpkg_path))
        start_time = time.time()
        self.con = database_connect(self.gpkg_path)
        self.uc.log_info("Connected to {}".format(self.gpkg_path))
        self.uc.log_info('{0:.3f} seconds => connecting'.format(time.time() - start_time))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.gutils = GeoPackageUtils(self.con, self.iface)
        if self.gutils.check_gpkg():
            self.gutils.path = self.gpkg_path
            self.uc.bar_info("GeoPackage {} is OK".format(self.gutils.path))
            sql = '''SELECT srs_id FROM gpkg_contents WHERE table_name='grid';'''
            rc = self.gutils.execute(sql)
            rt = rc.fetchone()[0]
            self.srs_id = rt
            start_time = time.time()
            self.lyrs.load_all_layers(self.gutils)
            self.uc.log_info('{0:.3f} seconds => loading layers'.format(time.time() - start_time))
            self.lyrs.zoom_to_all()
        else:
            self.uc.bar_error("{} is NOT a GeoPackage!".format(self.gutils.path))
        self.gpkgPathEdit.setText(self.gutils.path)
        self.read()
        QApplication.restoreOverrideCursor()

    def write(self):
        self.gutils.set_cont_par('PROJ', self.crs.toProj4())
        if self.crs.mapUnits() == QGis.Meters:
            metric = 1
        elif self.crs.mapUnits() == QGis.Feet:
            self.si_units = False
            metric = 0
        else:
            metric = 1
        self.gutils.set_cont_par('METRIC', metric)

    def select_all_modules(self):
        for cbx in self.modulesGrp.findChildren(QCheckBox):
            cbx.setChecked(True)

    def deselect_all_modules(self):
        for cbx in self.modulesGrp.findChildren(QCheckBox):
            cbx.setChecked(False)
