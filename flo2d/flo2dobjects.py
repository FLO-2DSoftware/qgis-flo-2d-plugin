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

    def __init__(self, fid, path, iface):
        super(CrossSection, self).__init__(path, iface)
        self.fid = fid
        self.row = None
        self.type = None
        self.chan = None
        self.chan_tab = None
        self.xsec = None

    def __enter__(self):
        self.database_connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.database_disconnect()

    def get_row(self):
        qry = 'SELECT * FROM chan_elems WHERE fid = {0};'
        values = self.execute(qry.format(self.fid)).fetchone()
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
        qry = 'SELECT {0} FROM chan WHERE fid = {1};'.format(columns, seg_fid)
        values = self.execute(qry).fetchone()
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
        qry = 'SELECT {0} FROM {1} WHERE elem_fid = {2};'.format(columns, tab, self.fid)
        values = self.execute(qry).fetchone()
        self.chan_tab = OrderedDict(zip(args, values))
        return self.chan_tab

    def xsec_data(self):
        if self.row is not None and self.type == 'N':
            pass
        else:
            return
        nxsecnum = self.chan_tab['nxsecnum']
        qry = 'SELECT xi, yi FROM xsec_n_data WHERE chan_n_nxsecnum = {0} ORDER BY fid;'.format(nxsecnum)
        self.xsec = self.execute(qry).fetchall()
        return self.xsec

if __name__ == '__main__':
    gpkg = r'D:\GIS_DATA\GPKG\alawai.gpkg'
    with CrossSection(1232, gpkg, None) as xs:
        row = xs.get_row()
        chan = xs.chan_segment()
        chan_tab = xs.chan_table()
        data = xs.xsec_data()
    print(row)
    print(chan)
    print(chan_tab)
    print(data)
