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
from collections import OrderedDict
from flo2dgeopackage import GeoPackageUtils


class CrossSection(GeoPackageUtils):
    columns = ['fid', 'seg_fid', 'nr_in_seg', 'rbankgrid', 'fcn', 'xlen', 'type', 'notes', 'geom']

    def __init__(self, fid, con, iface):
        super(CrossSection, self).__init__(con, iface)
        self.fid = fid
        self.row = None
        self.type = None
        self.chan = None
        self.chan_tab = None
        self.xsec = None

    def get_row(self):
        qry = 'SELECT * FROM chan_elems WHERE fid = ?;'
        values = [x if x is not None else '' for x in self.execute(qry, (self.fid,)).fetchone()]
        self.row = OrderedDict(zip(self.columns, values))
        self.type = self.row['type']
        return self.row

    def chan_segment(self, *args):
        if self.row is not None:
            pass
        else:
            return
        seg_fid = self.row['seg_fid']
        if args:
            columns = ','.join(args)
        else:
            columns = '*'
            args = self.table_info('chan', only_columns=True)
        qry = 'SELECT {0} FROM chan WHERE fid = ?;'.format(columns)
        values = [x if x is not None else '' for x in self.execute(qry, (seg_fid,)).fetchone()]
        self.chan = OrderedDict(zip(args, values))
        return self.chan

    def chan_table(self, *args):
        if self.row is not None:
            pass
        else:
            return
        tables = {'N': 'chan_n', 'R': 'chan_r', 'T': 'chan_t', 'V': 'chan_v'}
        tab = tables[self.type]
        if args:
            columns = ','.join(args)
        else:
            columns = '*'
            args = self.table_info(tab, only_columns=True)
        qry = 'SELECT {0} FROM {1} WHERE elem_fid = ?;'.format(columns, tab)
        values = [x if x is not None else '' for x in self.execute(qry, (self.fid,)).fetchone()]
        self.chan_tab = OrderedDict(zip(args, values))
        return self.chan_tab

    def xsec_data(self):
        if self.row is not None and self.type == 'N':
            pass
        else:
            return None
        nxsecnum = self.chan_tab['nxsecnum']
        qry = 'SELECT xi, yi FROM xsec_n_data WHERE chan_n_nxsecnum = ? ORDER BY fid;'
        self.xsec = self.execute(qry, (nxsecnum,)).fetchall()
        return self.xsec

if __name__ == '__main__':
    from flo2dgeopackage import database_connect
    gpkg = r'D:\GIS_DATA\GPKG\alawai.gpkg'
    con = database_connect(gpkg)
    xs = CrossSection(1232, con, None)
    row = xs.get_row()
    chan = xs.chan_segment()
    chan_tab = xs.chan_table()
    data = xs.xsec_data()
    con.close()
    print(row)
    print(chan)
    print(chan_tab)
    print(data)
