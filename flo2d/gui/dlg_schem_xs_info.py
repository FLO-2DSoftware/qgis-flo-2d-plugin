# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from .utils import load_ui
from ..user_communication import UserCommunication
from ..flo2dobjects import CrossSection


uiDialog, qtBaseClass = load_ui('schem_xs_info')


class SchemXsecEditorDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs, gutils, fid):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = con
        self.lyrs = lyrs
        self.gutils = gutils
        self.fid = fid
        self.setup()

    def setup(self):
        if not self.gutils:
            return
        self.xs = CrossSection(self.fid, self.con, self.iface)
        row = self.xs.get_row()
        typ = row['type']
        t = ''
        for col, val in row.iteritems():
            t += '{}:\t{}\n'.format(col, val)
        chan_x_row = self.xs.get_chan_table()
        if typ == 'N':
            xy = self.xs.get_xsec_data()
        else:
            xy = None
        t += '\n'
        if not xy:
            for col, val in chan_x_row.iteritems():
                t += '{}:\t{}\n'.format(col, val)
        else:
            for i, pt in enumerate(xy):
                x, y = pt
                t += '{.2f}\t\t{.2f}'.format(x, y)
        self.tedit.setText(t)



