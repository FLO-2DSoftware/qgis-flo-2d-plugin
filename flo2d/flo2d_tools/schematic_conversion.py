# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from flo2d.geopackage_utils import GeoPackageUtils
from qgis.core import QgsFeature, QgsGeometry


def remove_features(lyr):
    ids = lyr.allFeatureIds()
    lyr.startEditing()
    lyr.deleteFeatures(ids)
    lyr.commitChanges()


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
        new_geom = geom_function(geom)
        user_feat.setGeometry(new_geom)
        user_feat.setFields(user_fields)
        for user_fname, schema_fname in common_fnames.items():
            user_feat.setAttribute(user_fname, schema_feat[schema_fname])
        return user_feat

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

        fn = self.geom_functions[geometry_type]
        new_features = []
        for feat in schema_lyr.getFeatures():
            if feat.geometry() is None:
                continue
            new_feat = self.set_feature(feat, user_fields, common_fnames, fn)
            new_features.append(new_feat)
        remove_features(user_lyr)
        user_lyr.startEditing()
        user_lyr.addFeatures(new_features)
        user_lyr.commitChanges()
        user_lyr.updateExtents()
        user_lyr.triggerRepaint()
        user_lyr.removeSelection()


class SchemaDomainConverter(SchemaConverter):

    def __init__(self, con, iface, lyrs):
        super(SchemaDomainConverter, self).__init__(con, iface, lyrs)

        self.schema_lbank_tab = 'chan'
        self.user_lbank_tab = 'user_left_bank'
        self.schema_xs_tab = 'chan_elems'
        self.user_xs_tab = 'user_xsections'

        self.schema_lbank_lyr = lyrs.data[self.schema_lbank_tab]['qlyr']
        self.user_lbank_lyr = lyrs.data[self.user_lbank_tab]['qlyr']
        self.schema_xs_lyr = lyrs.data[self.schema_xs_tab]['qlyr']
        self.user_xs_lyr = lyrs.data[self.user_xs_tab]['qlyr']

        self.xs_tables = {
            'user_chan_n': 'chan_n',
            'user_chan_r': 'chan_r',
            'user_chan_t': 'chan_t',
            'user_chan_v': 'chan_v',
            'user_xsec_n_data': 'xsec_n_data'
        }

    def copy_xs_tables(self):
        self.clear_tables(*self.xs_tables.keys())
        for user_tab, schema_tab in self.xs_tables.items():
            self.execute('''INSERT INTO {0} SELECT * FROM {1};'''.format(user_tab, schema_tab))

    def set_geomless_xs(self, feat):
        fid = feat['fid']
        wkt_pnt = self.single_centroid(fid)
        point_geom = QgsGeometry().fromWkt(wkt_pnt)
        point = point_geom.asPoint()
        new_geom = QgsGeometry().fromPolyline([point, point])
        feat.setGeometry(new_geom)

    def create_user_lbank(self):
        remove_features(self.user_lbank_lyr)
        self.schema2user(self.schema_lbank_lyr, self.user_lbank_lyr, 'polyline')

    def create_user_xs(self):
        remove_features(self.user_xs_lyr)
        fields = self.user_xs_lyr.fields()
        common_fnames = {'fid': 'fid', 'type': 'type', 'fcn': 'fcn'}
        geom_fn = self.geom_functions['polyline']
        new_features = []
        for i, feat in enumerate(self.schema_xs_lyr.getFeatures(), start=1):

            if feat.geometry() is None:
                self.set_geomless_xs(feat)

            new_feat = self.set_feature(feat, fields, common_fnames, geom_fn)
            new_feat['name'] = 'Cross-section {}'.format(i)
            new_features.append(new_feat)
        self.user_xs_lyr.startEditing()
        self.user_xs_lyr.addFeatures(new_features)
        self.user_xs_lyr.commitChanges()
        self.user_xs_lyr.updateExtents()
        self.user_xs_lyr.triggerRepaint()
        self.user_xs_lyr.removeSelection()
        self.copy_xs_tables()


class SchemaLeveesConverter(SchemaConverter):

    def __init__(self, con, iface, lyrs):
        super(SchemaLeveesConverter, self).__init__(con, iface, lyrs)

        self.schema_levee_tab = 'levee_data'
        self.user_levee_tab = 'user_levee_lines'
        self.schema_levee_lyr = lyrs.data[self.schema_levee_tab]['qlyr']
        self.user_levee_lyr = lyrs.data[self.user_levee_tab]['qlyr']

    def set_user_fids(self):
        self.execute('UPDATE levee_data SET user_line_fid = fid;')

    def create_user_levees(self):
        remove_features(self.user_levee_lyr)
        self.set_user_fids()
        self.schema2user(self.schema_levee_lyr, self.user_levee_lyr, 'polyline', levcrest='elev')


class SchemaBCConverter(SchemaConverter):

    def __init__(self, con, iface, lyrs):
        super(SchemaBCConverter, self).__init__(con, iface, lyrs)

        self.schema_bc_tab = 'all_schem_bc'
        self.user_bc_tab = 'user_bc_points'
        self.schema_bc_lyr = lyrs.data[self.schema_bc_tab]['qlyr']
        self.user_bc_lyr = lyrs.data[self.user_bc_tab]['qlyr']

    def update_bc_fids(self, bc_updates):
        cur = self.con.cursor()
        for table, fid, tab_bc_fid in bc_updates:
            qry = '''UPDATE {0} SET bc_fid = ?, geom_type = ? WHERE fid = ?;'''.format(table)
            cur.execute(qry, (fid, 'point', tab_bc_fid))
        self.con.commit()

    def create_user_bc(self):
        self.disable_geom_triggers()
        remove_features(self.user_bc_lyr)
        fields = self.user_bc_lyr.fields()
        common_fnames = {'fid': 'fid', 'type': 'type'}
        geom_fn = self.geom_functions['centroid']
        new_features = []
        bc_updates = []
        for feat in self.schema_bc_lyr.getFeatures():
            new_feat = self.set_feature(feat, fields, common_fnames, geom_fn)
            new_features.append(new_feat)
            bc_updates.append((feat['type'], feat['fid'], feat['tab_bc_fid']))
        self.user_bc_lyr.startEditing()
        self.user_bc_lyr.addFeatures(new_features)
        self.user_bc_lyr.commitChanges()
        self.user_bc_lyr.updateExtents()
        self.user_bc_lyr.triggerRepaint()
        self.user_bc_lyr.removeSelection()
        self.update_bc_fids(bc_updates)
        self.enable_geom_triggers()


class SchemaFPXSECConverter(SchemaConverter):

    def __init__(self, con, iface, lyrs):
        super(SchemaFPXSECConverter, self).__init__(con, iface, lyrs)

        self.schema_fpxsec_tab = 'fpxsec'
        self.user_fpxsec_tab = 'user_fpxsec'

        self.schema_fpxsec_lyr = lyrs.data[self.schema_fpxsec_tab]['qlyr']
        self.user_fpxsec_lyr = lyrs.data[self.user_fpxsec_tab]['qlyr']

    def create_user_fpxsec(self):
        remove_features(self.user_fpxsec_lyr)
        self.schema2user(self.schema_fpxsec_lyr, self.user_fpxsec_lyr, 'polyline')


class ModelBoundaryConverter(SchemaConverter):

    def __init__(self, con, iface, lyrs):
        super(ModelBoundaryConverter, self).__init__(con, iface, lyrs)

        self.schema_grid_tab = 'grid'
        self.user_boundary_tab = 'user_model_boundary'

        self.schema_grid_lyr = lyrs.data[self.schema_grid_tab]['qlyr']
        self.user_boundary_lyr = lyrs.data[self.user_boundary_tab]['qlyr']

    def boundary_from_grid(self):
        remove_features(self.user_boundary_lyr)
        cellsize = self.get_cont_par('CELLSIZE')
        fields = self.user_boundary_lyr.fields()
        geom_list = []
        for feat in self.schema_grid_lyr.getFeatures():
            geom_poly = feat.geometry().asPolygon()
            geom_list.append(QgsGeometry.fromPolygon(geom_poly))
        bfeat = QgsFeature()
        bgeom = QgsGeometry.unaryUnion(geom_list)
        bfeat.setGeometry(bgeom)
        bfeat.setFields(fields)
        bfeat.setAttribute('cell_size', cellsize)
        self.user_boundary_lyr.startEditing()
        self.user_boundary_lyr.addFeature(bfeat)
        self.user_boundary_lyr.commitChanges()
        self.user_boundary_lyr.updateExtents()
        self.user_boundary_lyr.triggerRepaint()

