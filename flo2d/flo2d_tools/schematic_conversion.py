# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import traceback
from flo2d.geopackage_utils import GeoPackageUtils


class SchemaDomainConverter(GeoPackageUtils):

    def __init__(self, con, iface, lyrs):
        super(SchemaDomainConverter, self).__init__(con, iface)
        self.lyrs = lyrs
        self.user_lbank_lyr = lyrs.data['user_left_bank']['qlyr']
        self.left_bank_lyr = lyrs.data['chan']['qlyr']

        self.xsections_lyr = lyrs.data['user_xsections']['qlyr']
        self.schema_xs_lyr = lyrs.data['chan_elems']['qlyr']
        self.xs_types = {
            'N': {'tab': 'chan_n'},
            'R': {'tab': 'chan_r'},
            'T': {'tab': 'chan_t'},
            'V': {'tab': 'chan_v'},
        }

    def populate_xs_lyrs(self):
        for typ in self.xs_types.keys():
            tab = self.xs_types[typ]['tab']
            self.xs_types[typ]['lyr'] = self.lyrs.data[tab]['qlyr']

    def create_user_lbank(self):
        self.user_lbank_lyr.startEditing()
        for feat in self.left_bank_lyr.getFeatures():
            self.user_lbank_lyr.addFeature(feat)
        self.user_lbank_lyr.commitChanges()
        self.user_lbank_lyr.updateExtents()
        self.user_lbank_lyr.triggerRepaint()


class SchemaLeveesConverter(GeoPackageUtils):

    def __init__(self, con, iface, lyrs):
        super(SchemaLeveesConverter, self).__init__(con, iface)
        self.lyrs = lyrs


class SchemaBCConverter(GeoPackageUtils):

    def __init__(self, con, iface, lyrs):
        super(SchemaBCConverter, self).__init__(con, iface)
        self.lyrs = lyrs
