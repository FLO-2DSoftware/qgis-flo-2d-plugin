# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsFeatureRequest
from ..user_communication import UserCommunication
from ..flo2dobjects import CrossSection
from .ui_utils import load_ui, center_canvas
import os


uiDialog, qtBaseClass = load_ui("schem_xs_info")


class SchemXsecEditorDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs, gutils, id):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = con
        self.lyrs = lyrs
        self.gutils = gutils
        self.id = id
        self.fid = None
        self.seg_fid = None
        self.setup()

        # set button icons
        self.set_icon(self.prev_btn, "arrow_1.svg")
        self.set_icon(self.next_btn, "arrow_3.svg")

        # connections
        self.prev_btn.clicked.connect(self.show_prev)
        self.next_btn.clicked.connect(self.show_next)

    @staticmethod
    def set_icon(btn, icon_file):
        idir = os.path.join(os.path.dirname(__file__), "..\\img")
        btn.setIcon(QIcon(os.path.join(idir, icon_file)))

    def setup(self, id=None):
        if not self.gutils:
            return
        self.xs_lyr = self.lyrs.data["chan_elems"]["qlyr"]
        self.id = id if id else self.id
        self.xs = CrossSection(self.id, self.con, self.iface)
        row = self.xs.get_row(by_id=True)
        typ = row["type"]
        self.seg_fid = row["seg_fid"]
        self.nr_in_seg = row["nr_in_seg"]

        # find prev and next xsec ids
        qry = "SELECT id FROM chan_elems WHERE seg_fid = ? AND nr_in_seg = ?"
        if self.nr_in_seg == 1:
            self.prev_id = None
        else:
            self.prev_id = self.gutils.execute(qry, (self.seg_fid, self.nr_in_seg - 1)).fetchone()[0]
        self.next_id = None
        try:
            self.next_id = self.gutils.execute(qry, (self.seg_fid, self.nr_in_seg + 1)).fetchone()[0]
        except Exception as e:
            pass
        del row["geom"]
        t = ""
        for col, val in row.items():
            t += "{}:\t{}\n".format(col, val)
        chan_x_row = self.xs.get_chan_table()
        if typ == "N":
            xy = self.xs.get_xsec_data()
        else:
            xy = None
        t += "\n"
        if not xy:
            for col, val in chan_x_row.items():
                t += "{}:\t{}\n".format(col, val)
        else:
            for i, pt in enumerate(xy):
                x, y = pt
                t += "{0:.2f}\t\t{1:.2f}\n".format(x, y)
        self.tedit.setText(t)

        self.show_xs_rb()
        if self.center_chbox.isChecked():
            feat = next(self.xs_lyr.getFeatures(QgsFeatureRequest(self.id)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def show_xs_rb(self):
        if not self.id:
            return
        self.lyrs.show_feat_rubber(self.xs_lyr.id(), self.id)

    def show_prev(self):
        self.setup(id=self.prev_id)

    def show_next(self):
        self.setup(id=self.next_id)
