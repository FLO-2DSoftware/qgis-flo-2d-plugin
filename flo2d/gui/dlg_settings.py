# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os
from PyQt4.QtCore import Qt, QSettings
from PyQt4.QtGui import QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox, QFileDialog, QApplication
from qgis.core import QgsCoordinateReferenceSystem, QGis
from qgis.gui import QgsProjectionSelectionWidget

from .utils import load_ui
from ..utils import is_number
from ..geopackage_utils import GeoPackageUtils, database_disconnect, database_connect, database_create
from ..user_communication import UserCommunication
from ..errors import Flo2dQueryResultNull

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
        self.lyrs = lyrs
        self.gutils = gutils
        self.si_units = None
        self.crs = None
        self.projectionSelector = QgsProjectionSelectionWidget()
        self.projectionSelector.setCrs(self.iface.mapCanvas().mapRenderer().destinationCrs())
        self.widget_map = {
            "ICHANNEL": self.chanChBox,
            "IEVAP": self.evapChBox,
            "IHYDRSTRUCT": self.hystrucChBox,
            "IMULTC": self.multChBox,
            "IMODFLOW": self.modfloChBox,
            "INFIL": self.infilChBox,
            "IRAIN": self.rainChBox,
            "ISED": self.sedChBox,
            "IWRFS": self.redFactChBox,
            "LEVEE": self.leveesChBox,
            # "PROJ": self.projectionSelector,
            "MANNING": self.manningDSpinBox,
            "SWMM": self.swmmChBox,
            "CELLSIZE": self.cellSizeDSpinBox
        }

        self.setup()

        # connection
        self.gpkgCreateBtn.clicked.connect(self.create_db)
        self.gpkgOpenBtn.clicked.connect(self.connect)
        self.modSelectAllBtn.clicked.connect(self.select_all_modules)
        self.modDeselAllBtn.clicked.connect(self.deselect_all_modules)

    def read(self):
        for name, wid in self.widget_map.iteritems():
            qry = '''SELECT value FROM cont WHERE name = ?;'''
            row = self.gutils.execute(qry, (name,)).fetchone()
            if not row:
                msg = 'Database query for param {} from cont table return null. Check your DB.'.format(name)
                raise Flo2dQueryResultNull(msg)
            value = row[0]
            if isinstance(wid, QLineEdit):
                wid.setText(str(value))
            elif isinstance(wid, QCheckBox):
                wid.setChecked(int(value))
            elif isinstance(wid, QSpinBox):
                if value and is_number(value):
                    wid.setValue(int(value))
                else:
                    pass
            elif isinstance(wid, QDoubleSpinBox):
                if value and is_number(value):
                    wid.setValue(float(value))
                else:
                    pass
            else:
                pass
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
        """Create FLO-2D model database (GeoPackage)"""
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
        con = database_create(gpkg_path)
        if not con:
            self.uc.show_warn("Couldn't create new database {}".format(gpkg_path))
            return
        else:
            self.uc.log_info("Connected to {}".format(gpkg_path))
        gutils = GeoPackageUtils(con, self.iface)
        if gutils.check_gpkg():
            self.uc.bar_info("GeoPackage {} is OK".format(gpkg_path))
            gutils.path = gpkg_path
            self.gpkgPathEdit.setText(gutils.path)
        else:
            self.uc.bar_error("{} is NOT a GeoPackage!".format(gpkg_path))
        QApplication.restoreOverrideCursor()
        # CRS
        self.projectionSelector.selectCrs()
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
        self.srs_id = srsid
        self.lyrs.load_all_layers(self.gutils)
        self.lyrs.zoom_to_all()

        QApplication.restoreOverrideCursor()

    def connect(self, gpkg_path=None):
        """Connect to FLO-2D model database (GeoPackage)"""
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
        self.con = database_connect(self.gpkg_path)
        self.uc.log_info("Connected to {}".format(self.gpkg_path))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.gutils = GeoPackageUtils(self.con, self.iface)
        if self.gutils.check_gpkg():
            self.gutils.path = self.gpkg_path
            self.uc.bar_info("GeoPackage {} is OK".format(self.gutils.path))
            sql = '''SELECT srs_id FROM gpkg_contents WHERE table_name='grid';'''
            rc = self.gutils.execute(sql)
            rt = rc.fetchone()[0]
            self.srs_id = rt
            self.lyrs.load_all_layers(self.gutils)
            self.lyrs.zoom_to_all()
        else:
            self.uc.bar_error("{} is NOT a GeoPackage!".format(self.gutils.path))
        self.gpkgPathEdit.setText(self.gutils.path)
        self.read()
        QApplication.restoreOverrideCursor()

    def write(self):
        ins_qry = '''INSERT INTO cont (name, value) VALUES (?, ?);'''
        for name, wid in self.widget_map.iteritems():
            value = None
            if isinstance(wid, QLineEdit):
                value = wid.text()
            elif isinstance(wid, QSpinBox):
                value = wid.value()
            elif isinstance(wid, QDoubleSpinBox):
                value = str(wid.value())
            elif isinstance(wid, QCheckBox):
                value = 1 if wid.isChecked() else 0

            else:
                pass
            self.gutils.execute(ins_qry, (name, value))
        self.gutils.execute(ins_qry, ('PROJ', self.crs.toProj4(),))
        if self.crs.mapUnits() == QGis.Meters:
            metric = 1
        elif self.crs.mapUnits() == QGis.Feet:
            self.si_units = False
            metric = 0
        else:
            metric = 1
        self.gutils.execute(ins_qry, ('METRIC', metric,))


    def select_all_modules(self):
        for cbx in self.modulesGrp.findChildren(QCheckBox):
            cbx.setChecked(True)

    def deselect_all_modules(self):
        for cbx in self.modulesGrp.findChildren(QCheckBox):
            cbx.setChecked(False)
