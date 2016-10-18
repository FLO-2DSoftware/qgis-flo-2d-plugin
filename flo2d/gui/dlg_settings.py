# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Flo2D
                                 A QGIS plugin
 FLO-2D tools for QGIS
                              -------------------
        begin                : 2016-08-28
        git sha              : $Format:%H$
        copyright            : (C) 2016 by Lutra Consulting for FLO-2D
        email                : info@lutraconsulting.co.uk
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import QgsCoordinateReferenceSystem
from .utils import load_ui
from ..flo2dgeopackage import *
from ..user_communication import UserCommunication
import os

uiDialog, qtBaseClass = load_ui('settings')


class SettingsDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs, gpkg):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.setModal(True)
        self.con = con
        self.lyrs = lyrs
        self.gpkg = gpkg
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
            # "MUD": self.???,
             "PROJ": self.projectionSelector,
            # "MANNING": self.manningDSpinBox,
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
            value = self.gutils.execute(qry, (name,)).fetchone()[0]
            if isinstance(wid, QLineEdit):
                wid.setText(str(value))
            elif isinstance(wid, QCheckBox):
                wid.setChecked(int(value))
            elif isinstance(wid, QSpinBox):
                wid.setValue(int(value))
            elif isinstance(wid, QDoubleSpinBox):
                wid.setValue(float(value))
            elif name == 'PROJ':
                cs = QgsCoordinateReferenceSystem()
                cs.createFromProj4(value)
                wid.setCrs(cs)
                self.crs = cs
            else:
                pass

    def setup(self):
        if self.gpkg:
            self.gpkg.path = self.gpkg.get_gpkg_path()
            self.gpkgPathEdit.setText(self.gpkg.path)
            self.gutils = GeoPackageUtils(self.con, self.iface)
            self.read()
        else:
            pass

    def create_db(self):
        """Create FLO-2D model database (GeoPackage)"""

        gpkg_path = None

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

        con = database_create(gpkg_path)
        if not con:
            self.uc.show_warn("Couldn't create new database {}".format(gpkg_path))
            return
        else:
            self.uc.log_info("Connected to {}".format(gpkg_path))
        gpkg = Flo2dGeoPackage(con, self.iface)
        if gpkg.check_gpkg():
            self.uc.bar_info("GeoPackage {} is OK".format(gpkg_path))
            gpkg.path = gpkg_path
            self.gpkgPathEdit.setText(gpkg.path)
        else:
            self.uc.bar_error("{} is NOT a GeoPackage!".format(gpkg_path))

        # CRS
        self.projectionSelector.selectCrs()
        if self.projectionSelector.crs().isValid():
            self.crs = self.projectionSelector.crs()
            auth, crsid = self.crs.authid().split(':')
            proj4 = self.crs.toProj4()

            # check if the CRS exist in the db
            sql = 'SELECT * FROM gpkg_spatial_ref_sys WHERE srs_id=?;'
            rc = gpkg.execute(sql, (crsid,))
            rt = rc.fetchone()
            if not rt:
                sql = '''INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)'''
                data = (self.crs.description(), crsid, auth, crsid, proj4, '')
                rc = gpkg.execute(sql, data)
                del rc
                srsid = crsid
            else:
                txt = 'There is a coordinate system defined in the GeoPackage.\n'
                txt += 'Would you like to use it?\n\nDetails:\n'
                txt += 'Name: {}\n'.format(rt[0])
                txt += 'SRS id: {}\n'.format(rt[1])
                txt += 'Organization: {}\n'.format(rt[2])
                txt += 'Organization id: {}\n'.format(rt[3])
                txt += 'Definition: {}'.format(rt[4])
                reply = QMessageBox.question(self, 'Use existing SRS?',
                    txt,
                    QMessageBox.No | QMessageBox.Yes)
                if reply == QMessageBox.Yes:
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
        self.gpkg = gpkg

        QApplication.setOverrideCursor(Qt.WaitCursor)

        # assign the CRS to all geometry columns
        sql = "UPDATE gpkg_geometry_columns SET srs_id = ?"
        rc = self.gpkg.execute(sql, (srsid,))
        sql = "UPDATE gpkg_contents SET srs_id = ?"
        rc = self.gpkg.execute(sql, (srsid,))
        self.srs_id = srsid
        self.gutils = GeoPackageUtils(self.con, self.iface)
        self.lyrs.load_all_layers(self.gpkg)

        QApplication.restoreOverrideCursor()

    def connect(self):
        """Connect to FLO-2D model database (GeoPackage)"""
        gpkg_path = None
        s = QSettings()
        last_gpkg_dir = s.value('FLO-2D/lastGpkgDir', '')
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
        self.gpkg = Flo2dGeoPackage(self.con, self.iface)
        if self.gpkg.check_gpkg():
            self.gpkg.path = self.gpkg_path
            self.uc.bar_info("GeoPackage {} is OK".format(self.gpkg.path))
            sql = '''SELECT srs_id FROM gpkg_contents WHERE table_name='grid';'''
            rc = self.gpkg.execute(sql)
            rt = rc.fetchone()[0]
            self.srs_id = rt
            self.lyrs.load_all_layers(self.gpkg)
            self.lyrs.zoom_to_all()
        else:
            self.uc.bar_error("{} is NOT a GeoPackage!".format(self.gpkg.path))
        self.gutils = GeoPackageUtils(self.con, self.iface)
        self.gpkgPathEdit.setText(self.gpkg.path)
        self.read()
        QApplication.restoreOverrideCursor()

    def write(self):
        for name, wid in self.widget_map.iteritems():
            ins_qry = '''INSERT INTO cont (name, value) VALUES (?, ?);'''
            updt_qry = '''UPDATE cont SET value = ? WHERE name = ?;'''
            value = None
            if isinstance(wid, QLineEdit):
                value = wid.text()
            elif isinstance(wid, QCheckBox):
                value = 1 if wid.isChecked() else 0
            elif name == 'PROJ':
                value = self.crs.toProj4()
            else:
                pass
            self.gutils.execute(ins_qry, (name, value))
            # in case the name exists in the table, update its value
            self.gutils.execute(updt_qry, (value, name))

    def select_all_modules(self):
        for cbx in self.modulesGrp.findChildren(QCheckBox):
            cbx.setChecked(True)

    def deselect_all_modules(self):
        for cbx in self.modulesGrp.findChildren(QCheckBox):
            cbx.setChecked(False)