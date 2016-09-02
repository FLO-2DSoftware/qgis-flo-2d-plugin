# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Flo2D
                                 A QGIS plugin
 FLO-2D tools for QGIS
                             -------------------
        begin                : 2016-08-28
        copyright            : (C) 2016 by Lutra Consulting for FLO-2D
        email                : info@lutraconsulting.co.uk
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.gui import *
from qgis.core import *
import processing
import logging

from .utils import *
import os.path
import pyspatialite.dbapi2 as db
from .user_communication import UserCommunication


class Flo2dGeoPackage(object):
    """GeoPackage object class for storing FLO-2D model data"""

    def __init__(self, path, iface):
        self.path = path
        self.iface = iface
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.cell_size = None
        
        
    def database_connect(self):
        """Connect database with sqlite3"""
        try:
            self.conn = db.connect(self.path)
            return True
        except:
            self.msg = "Couldn't connect to GeoPackage"
            return False
        

    def check_gpkg(self):
        """Check if file is GeoPackage """
        try:
            c = self.conn.cursor()
            c.execute('SELECT * FROM gpkg_contents;')
            c.fetchone()
            return True
        except:
            return False
        
        
    def execute(self, statement, inputs=None):
        """Execute a prepared SQL statement on this geopackage database."""
        with self.conn as db_con:
            cursor = db_con.cursor()
            if inputs is not None:
                result_cursor = cursor.execute(statement, inputs)
            else:
                result_cursor = cursor.execute(statement)
            return result_cursor
        
        
    def import_fplain(self, fname):
        fp = open(fname, "r").readlines()
        # we also need CADPTS with actual coordinates of grid points (centroids)
        cp = open(os.path.join(os.path.dirname(fname),'CADPTS.DAT')).readlines()
        if not len(fp) == len(cp):
            self.uc.bar_error("Line numbers of FPLAIN and CADPTS are different! ({} and {})".format(len(fp), len(cp)))
            return
        data = []
        for i, cpl in enumerate(cp):
            d = fp[i].split()
            nr, x, y = cp[i].split()
            data.append(d + [x, y])
        # find cell size
        for side, n in enumerate(data[0][1:5]):
            # check if this side has a neighbour
            if not n == '0':
                # check if this is a neighbour along y axis
                if is_even(side):
                    cs = abs(float(data[0][-1]) - float(data[int(n)-1][-1]))

                # or along x axis
                else: 
                    cs = abs(float(data[0][-2]) - float(data[int(n)-1][-2]))
                break

        if cs == 0:
            self.uc.bar_error("Cell size is 0 - something went wrong!")
        else:
            pass
        self.cell_size = cs
        
        # check if a grid exists in the grid table
        if not self.is_table_empty('grid'):
            r = self.uc.question('There is a grid already defined in GeoPackage. Overwrite it?')
            if r == QMessageBox.Yes:
                # delete previous grid
                sql = 'DELETE FROM grid;'
                self.execute(sql)
            else:
                self.uc.bar_info('Import cancelled', dur=3)
                return
        else:
            pass
        
        # insert grid data into gpkg
        sql  = """INSERT INTO grid
(fid, cell_north, cell_east, cell_south, cell_west, n_value, elevation, geom)
VALUES\n"""
        inp = []
        for d in data:
            g = square_from_center_and_size(d[-2], d[-1], cs)
            inp.append('({0}, {1})'.format(','.join(d[:7]), g))
        sql += '\n{};'.format(',\n'.join(inp))
        self.uc.log_info(sql)
        self.execute(sql)
        self.uc.bar_info('Grid imported', dur=3)            
        
        
    def import_topo(self, fname):
        # in case FPLAIN is missing this require finding each grid cell neighbours
        pass
    
    
    def is_table_empty(self, table):
        r = self.execute("SELECT rowid FROM {};".format(table))
        if r.fetchone():
            return False
        else:
            return True

        
