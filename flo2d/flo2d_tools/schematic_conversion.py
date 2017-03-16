# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import traceback
from flo2d.geopackage_utils import GeoPackageUtils
from qgis.core import QgsFeature, QgsGeometry


class SchemaConverter(GeoPackageUtils):

    def __init__(self, con, iface, lyrs):
        super(SchemaConverter, self).__init__(con, iface)
        self.lyrs = lyrs
        self.geom_functions = {
            'point': self.point_geom,
            'polyline': self.polyline_geom,
            'polygon': self.polygon_geom,
            'centroid': self.centroid_geom
        }

    @staticmethod
    def point_geom(geom):
        geom_point = geom.asPoint()
        new_geom = QgsGeometry.fromPoint(geom_point)
        return new_geom

    @staticmethod
    def polyline_geom(geom):
        geom_line = geom.asPolyline()
        new_geom = QgsGeometry.fromPolyline(geom_line)
        return new_geom

    @staticmethod
    def polygon_geom(geom):
        geom_polygon = geom.asPolygon()
        new_geom = QgsGeometry.fromPolygon(geom_polygon)
        return new_geom

    @staticmethod
    def centroid_geom(geom):
        geom_centroid = geom.centroid().asPoint()
        new_geom = QgsGeometry.fromPoint(geom_centroid)
        return new_geom

    @staticmethod
    def set_feature(schema_feat, user_fields, common_fnames, geom_function):
        user_feat = QgsFeature()
        geom = schema_feat.geometry()
        if geom is not None:
            new_geom = geom_function(geom)
            user_feat.setGeometry(new_geom)
        user_feat.setFields(user_fields)
        for user_fname, schema_fname in common_fnames.items():
            user_feat.setAttribute(user_fname, schema_feat[schema_fname])
        return user_feat

    @staticmethod
    def remove_features(lyr):
        ids = lyr.allFeatureIds()
        lyr.startEditing()
        lyr.deleteFeatures(ids)
        lyr.commitChanges()

    def schema2user(self, schema_lyr, user_lyr, geometry_type, **name_map):
        schema_fields = schema_lyr.fields()
        user_fields = user_lyr.fields()
        schema_fnames = {f.name() for f in schema_fields}
        user_fnames = {f.name() for f in user_fields}
        common_fnames = {}
        for schema_fname in schema_fnames:
            if schema_fname in name_map:
                user_fname = name_map[schema_fname]
            else:
                user_fname = schema_fname
            if user_fname in user_fnames:
                common_fnames[user_fname] = schema_fname
        self.remove_features(user_lyr)
        user_lyr.startEditing()
        fn = self.geom_functions[geometry_type]
        for feat in schema_lyr.getFeatures():
            new_feat = self.set_feature(feat, user_fields, common_fnames, fn)
            user_lyr.addFeature(new_feat)
        user_lyr.commitChanges()
        user_lyr.updateExtents()
        user_lyr.triggerRepaint()


class SchemaDomainConverter(SchemaConverter):

    def __init__(self, con, iface, lyrs):
        super(SchemaDomainConverter, self).__init__(con, iface, lyrs)

        self.left_bank_lyr = lyrs.data['chan']['qlyr']
        self.user_lbank_lyr = lyrs.data['user_left_bank']['qlyr']

        self.schema_xs_lyr = lyrs.data['chan_elems']['qlyr']
        self.xsections_lyr = lyrs.data['user_xsections']['qlyr']

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
        self.schema2user(self.left_bank_lyr, self.user_lbank_lyr, 'polyline')

    def create_user_xs(self):
        self.schema2user(self.schema_xs_lyr, self.xsections_lyr, 'polyline', xlen='name')


class SchemaLeveesConverter(SchemaConverter):

    def __init__(self, con, iface, lyrs):
        super(SchemaLeveesConverter, self).__init__(con, iface, lyrs)

        self.schema_levee_lyr = lyrs.data['levee_data']['qlyr']
        self.user_levee_lyr = lyrs.data['user_levee_lines']['qlyr']

    def create_user_levees(self):
        self.schema2user(self.schema_levee_lyr, self.user_levee_lyr, 'polyline', levcrest='elev')


class SchemaBCConverter(SchemaConverter):

    def __init__(self, con, iface, lyrs):
        super(SchemaBCConverter, self).__init__(con, iface, lyrs)

        self.schema_bc_lyr = lyrs.data['all_schem_bc']['qlyr']
        self.user_bc_lyr = lyrs.data['user_bc_points']['qlyr']

    def create_user_bc(self):
        fields = self.user_bc_lyr.fields()
        common_fnames = {'fid': 'fid', 'type': 'type'}
        geom_fn = self.geom_functions['centroid']
        self.remove_features(self.user_bc_lyr)
        self.user_bc_lyr.startEditing()
        for feat in self.schema_bc_lyr.getFeatures():
            new_feat = self.set_feature(feat, fields, common_fnames, geom_fn)
            self.user_bc_lyr.addFeature(new_feat)
        self.user_bc_lyr.commitChanges()
        self.user_bc_lyr.updateExtents()
        self.user_bc_lyr.triggerRepaint()

