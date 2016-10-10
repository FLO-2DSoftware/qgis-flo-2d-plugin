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

    def __init__(self, con, iface, old_gpkg, parent=None):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self, parent)
        self.iface = iface
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = con
        self.old_gpkg_fpath = old_gpkg
#        self.gpkg = None
#        self.gutils = GeoPackageUtils(self.con, self.iface)
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
            # "PROJ": self.projectionSelector,
            # "MANNING": self.manningEdit,
            "SWMM": self.swmmChBox,
            "CELLSIZE": self.cellSizeEdit
        }
        self.setup()

        # connection
        self.gpkgCreateBtn.clicked.connect(self.create_db)
        self.gpkgOpenBtn.clicked.connect(self.connect)

    def setup(self):
        if self.old_gpkg_fpath:
            self.gpkgPathEdit.setText(self.old_gpkg_fpath)
            self.gutils = GeoPackageUtils(self.con, self.iface)
        else:
            pass
#        if not self.con:
#            self.gutils = GeoPackageUtils(self.con, self.iface)
#        else:
#            pass
#        self.gpkgPathEdit.setText()
#        self.read()

    def create_db(self):
        """Create FLO-2D model database (GeoPackage)"""
        database_disconnect(self.con)
        self.gpkg_fpath = None
        # CRS
        self.projectionSelector.selectCrs()
        if self.projectionSelector.crs().isValid():
            self.crs = self.projectionSelector.crs()
            auth, crsid = self.crs.authid().split(':')
            proj = 'PROJCS["{}"]'.format(self.crs.toProj4())
        else:
            msg = 'Choose a valid CRS!'
            self.uc.show_warn(msg)
            return
        s = QSettings()
        last_gpkg_dir = s.value('FLO-2D/lastGpkgDir', '')
        self.gpkg_fpath = QFileDialog.getSaveFileName(None,
                         'Create GeoPackage As...',
                         directory=last_gpkg_dir, filter='*.gpkg')
        if not self.gpkg_fpath:
            return
        s.setValue('FLO-2D/lastGpkgDir', os.path.dirname(self.gpkg_fpath))
        self.con = database_create(self.gpkg_fpath)
        if not self.con:
            self.uc.show_warn("Couldn't create new database {}".format(self.gpkg_fpath))
        else:
            self.uc.log_info("Connected to {}".format(self.gpkg_fpath))
        self.gpkg = Flo2dGeoPackage(self.con, self.iface)
        if self.gpkg.check_gpkg():
            self.uc.bar_info("GeoPackage {} is OK".format(self.gpkg_fpath))
        else:
            self.uc.bar_error("{} is NOT a GeoPackage!".format(self.gpkg_fpath))

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

    def connect(self):
        """Connect to FLO-2D model database (GeoPackage)"""
        database_disconnect(self.con)
        self.gpkg_fpath = None
        s = QSettings()
        last_gpkg_dir = s.value('FLO-2D/lastGpkgDir', '')
        self.gpkg_fpath = QFileDialog.getOpenFileName(None,
                         'Select GeoPackage to connect',
                         directory=last_gpkg_dir)
        if self.gpkg_fpath:
            s.setValue('FLO-2D/lastGpkgDir', os.path.dirname(self.gpkg_fpath))
            self.con = database_connect(self.gpkg_fpath)
            self.uc.log_info("Connected to {}".format(self.gpkg_fpath))
            self.gpkg = Flo2dGeoPackage(self.con, self.iface)
            if self.gpkg.check_gpkg():
                self.uc.bar_info("GeoPackage {} is OK".format(self.gpkg_fpath))
                sql = '''SELECT srs_id FROM gpkg_contents WHERE table_name='grid';'''
                rc = self.gpkg.execute(sql)
                rt = rc.fetchone()[0]
                self.srs_id = rt
                self.load_layers()
            else:
                self.uc.bar_error("{} is NOT a GeoPackage!".format(self.gpkg_fpath))
        else:
            pass
        self.gutils = GeoPackageUtils(self.con, self.iface)
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
                coord = QgsCoordinateReferenceSystem()
                coord.createFromWkt(value)
                wid.setCrs(coord)
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
                pass
            else:
                pass
            self.gutils.execute(qry, (name, value))

    def browse_gpkg(self):
        s = QSettings()
        last_gpkg_dir = s.value('FLO-2D/lastGpkgDir', '')
        self.gpkg_fpath = QFileDialog.getOpenFileName(None,
                         'Open GeoPackage',
                         directory=last_gpkg_dir, filter='*.gpkg')
