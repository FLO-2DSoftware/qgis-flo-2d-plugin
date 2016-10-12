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
from qgis.core import *
from .utils import load_ui
from ..flo2dgeopackage import *
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui('settings')


class SettingsDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs, gpkg, parent=None):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self, parent)
        self.iface = iface
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
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
            # "MANNING": self.manningEdit,
            "SWMM": self.swmmChBox,
            "CELLSIZE": self.cellSizeEdit
        }
        self.setup()

        # connection
        self.gpkgCreateBtn.clicked.connect(self.create_db)
        self.gpkgOpenBtn.clicked.connect(self.connect)

    def setup(self):
        if self.gpkg:
            self.gpkgPathEdit.setText(self.gpkg.path)
            self.gutils = GeoPackageUtils(self.con, self.iface)
            self.read()
        else:
            pass


    def create_db(self):
        """Create FLO-2D model database (GeoPackage)"""
        if self.con:
            database_disconnect(self.con)
        self.gpkg_path = None
        # CRS
        self.projectionSelector.selectCrs()
        if self.projectionSelector.crs().isValid():
            self.crs = self.projectionSelector.crs()
            auth, crsid = self.crs.authid().split(':')
#            proj = 'PROJCS["{}"]'.format(self.crs.toProj4())
            proj = self.crs.toProj4()
        else:
            msg = 'Choose a valid CRS!'
            self.uc.show_warn(msg)
            return
        s = QSettings()
        last_gpkg_dir = s.value('FLO-2D/lastGpkgDir', '')
        self.gpkg_path = QFileDialog.getSaveFileName(None,
                         'Create GeoPackage As...',
                         directory=last_gpkg_dir, filter='*.gpkg')
        if not self.gpkg_path:
            return
        s.setValue('FLO-2D/lastGpkgDir', os.path.dirname(self.gpkg_path))
        self.con = database_create(self.gpkg_path)
        if not self.con:
            self.uc.show_warn("Couldn't create new database {}".format(self.gpkg_path))
        else:
            self.uc.log_info("Connected to {}".format(self.gpkg_path))
        self.gpkg = Flo2dGeoPackage(self.con, self.iface)
        if self.gpkg.check_gpkg():
            self.uc.bar_info("GeoPackage {} is OK".format(self.gpkg_path))
            self.gpkg.path = self.gpkg_path
            self.gpkgPathEdit.setText(self.gpkg.path)
        else:
            self.uc.bar_error("{} is NOT a GeoPackage!".format(self.gpkg_path))

        # check if the CRS exist in the db
        sql = 'SELECT srs_id FROM gpkg_spatial_ref_sys WHERE organization=? AND organization_coordsys_id=?;'
        rc = self.gpkg.execute(sql, (auth, crsid))
        rt = rc.fetchone()
        if not rt:
            sql = '''INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)'''
            data = (self.crs.description(), crsid, auth, crsid, proj, '')
            rc = self.gpkg.execute(sql, data)
            del rc
            srsid = crsid
        else:
            srsid = rt[0]

        # assign the CRS to all geometry columns
        sql = "UPDATE gpkg_geometry_columns SET srs_id = ?"
        rc = self.gpkg.execute(sql, (srsid,))
        sql = "UPDATE gpkg_contents SET srs_id = ?"
        rc = self.gpkg.execute(sql, (srsid,))
        self.srs_id = srsid
        self.gutils = GeoPackageUtils(self.con, self.iface)
        self.lyrs.load_all_layers(self.gpkg)

    def connect(self):
        """Connect to FLO-2D model database (GeoPackage)"""
        database_disconnect(self.con)
        self.gpkg_path = None
        s = QSettings()
        last_gpkg_dir = s.value('FLO-2D/lastGpkgDir', '')
        self.gpkg_path = QFileDialog.getOpenFileName(None,
                         'Select GeoPackage to connect',
                         directory=last_gpkg_dir)
        if self.gpkg_path:
            s.setValue('FLO-2D/lastGpkgDir', os.path.dirname(self.gpkg_path))
            self.con = database_connect(self.gpkg_path)
            self.uc.log_info("Connected to {}".format(self.gpkg_path))
            self.gpkg = Flo2dGeoPackage(self.con, self.iface)
            if self.gpkg.check_gpkg():
                self.gpkg.path = self.gpkg_path
                self.uc.bar_info("GeoPackage {} is OK".format(self.gpkg.path))
                sql = '''SELECT srs_id FROM gpkg_contents WHERE table_name='grid';'''
                rc = self.gpkg.execute(sql)
                rt = rc.fetchone()[0]
                self.srs_id = rt
                self.lyrs.load_all_layers(self.gpkg)
            else:
                self.uc.bar_error("{} is NOT a GeoPackage!".format(self.gpkg.path))
        else:
            pass
        self.gutils = GeoPackageUtils(self.con, self.iface)
        self.gpkgPathEdit.setText(self.gpkg.path)
        self.read()

    def read(self):
        for name, wid in self.widget_map.iteritems():
            qry = '''SELECT value FROM cont WHERE name = ?;'''
            value = self.gutils.execute(qry, (name,)).fetchone()[0]
            if isinstance(wid, QLineEdit):
                wid.setText(str(value))
            elif isinstance(wid, QCheckBox):
                wid.setChecked(int(value))
            elif name == 'PROJ':
                cs = QgsCoordinateReferenceSystem()
                cs.createFromProj4(value)
                wid.setCrs(cs)
                self.crs = cs
            else:
                pass

    def write(self):
        for name, wid in self.widget_map.iteritems():
            qry = '''INSERT INTO cont (name, value) VALUES (?, ?);'''
            value = None
            if isinstance(wid, QLineEdit):
                value = wid.text()
            elif isinstance(wid, QCheckBox):
                value = 1 if wid.isChecked() else 0
            elif name == 'PROJ':
                value = self.crs.toProj4()
            else:
                pass
            self.gutils.execute(qry, (name, value))

