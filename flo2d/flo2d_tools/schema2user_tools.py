# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

import os
from qgis.core import QgsFeature, QgsGeometry
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QApplication

from ..flo2d_tools.grid_tools import clustered_features

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
from ..geopackage_utils import GeoPackageUtils


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
            "point": self.point_geom,
            "polyline": self.polyline_geom,
            "polygon": self.polygon_geom,
            "centroid": self.centroid_geom,
        }

    @staticmethod
    def point_geom(geom):
        geom_point = geom.asPoint()
        new_geom = QgsGeometry.fromPointXY(geom_point)
        return new_geom

    @staticmethod
    def polyline_geom(geom):
        geom_line = geom.asPolyline()
        new_geom = QgsGeometry.fromPolylineXY(geom_line)
        return new_geom

    @staticmethod
    def polygon_geom(geom):
        geom_polygon = geom.asPolygon()
        new_geom = QgsGeometry.fromPolygonXY(geom_polygon)
        return new_geom

    @staticmethod
    def centroid_geom(geom):
        geom_centroid = geom.centroid().asPoint()
        new_geom = QgsGeometry.fromPointXY(geom_centroid)
        return new_geom

    @staticmethod
    def set_feature(schema_feat, user_fields, common_fnames, geom_function):
        user_feat = QgsFeature()
        geom = schema_feat.geometry()
        new_geom = geom_function(geom)
        user_feat.setGeometry(new_geom)
        user_feat.setFields(user_fields)
        for user_fname, schema_fname in list(common_fnames.items()):
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


class Schema1DConverter(SchemaConverter):
    def __init__(self, con, iface, lyrs):
        super(Schema1DConverter, self).__init__(con, iface, lyrs)

        self.schema_lbank_tab = "chan"
        self.user_lbank_tab = "user_left_bank"
        self.schema_xs_tab = "chan_elems"
        self.user_xs_tab = "user_xsections"

        self.xsecnames = dict(self.execute("SELECT elem_fid, xsecname FROM chan_n;"))
        self.schema_lbank_lyr = lyrs.data[self.schema_lbank_tab]["qlyr"]
        self.user_lbank_lyr = lyrs.data[self.user_lbank_tab]["qlyr"]
        self.schematized_xsections_lyr = lyrs.data[self.schema_xs_tab]["qlyr"]
        self.user_xs_lyr = lyrs.data[self.user_xs_tab]["qlyr"]

        self.xs_tables = {
            "user_chan_n": "chan_n",
            "user_chan_r": "chan_r",
            "user_chan_t": "chan_t",
            "user_chan_v": "chan_v",
            "user_xsec_n_data": "xsec_n_data",
        }

    def copy_xs_tables(self):
        self.clear_tables(*list(self.xs_tables.keys()))
        for user_tab, schema_tab in list(self.xs_tables.items()):
            if user_tab == "user_chan_n":
                self.execute(
                    """INSERT INTO user_chan_n (fid, user_xs_fid, nxsecnum, xsecname) SELECT fid, fid, nxsecnum, xsecname FROM chan_n;"""
                )
            else:
                self.execute("""INSERT INTO {0} SELECT * FROM {1};""".format(user_tab, schema_tab))

    def set_geomless_xs(self, feat):
        fid = feat["fid"]
        wkt_pnt = self.single_centroid(fid)
        point_geom = QgsGeometry().fromWkt(wkt_pnt)
        point = point_geom.asPoint()
        new_geom = QgsGeometry().fromPolylineXY([point, point])
        feat.setGeometry(new_geom)

    def create_user_lbank(self):
        remove_features(self.user_lbank_lyr)
        self.schema2user(self.schema_lbank_lyr, self.user_lbank_lyr, "polyline")

    def create_user_xs(self):
        self.user_xs_lyr.blockSignals(True)
        self.copy_xs_tables()
        remove_features(self.user_xs_lyr)
        fields = self.user_xs_lyr.fields()
        common_fnames = {"fid": "id", "type": "type", "fcn": "fcn"}
        geom_fn = self.geom_functions["polyline"]
        new_features = []
        for i, feat in enumerate(self.schematized_xsections_lyr.getFeatures(), start=1):
            if feat.geometry() is None:
                self.set_geomless_xs(feat)

            new_feat = self.set_feature(feat, fields, common_fnames, geom_fn)
            new_feat["name"] = "Cross-section-{}".format(i)
            new_feat["name"] = "Cross-section-{}".format(i) if feat["type"] != "N" else self.xsecnames[feat["fid"]]
            new_features.append(new_feat)
        self.user_xs_lyr.startEditing()
        self.user_xs_lyr.addFeatures(new_features)
        self.user_xs_lyr.commitChanges()
        self.user_xs_lyr.updateExtents()
        self.user_xs_lyr.triggerRepaint()
        self.user_xs_lyr.removeSelection()
        self.user_xs_lyr.blockSignals(False)


class SchemaLeveesConverter(SchemaConverter):
    def __init__(self, con, iface, lyrs):
        super(SchemaLeveesConverter, self).__init__(con, iface, lyrs)

        self.schema_levee_tab = "levee_data"
        self.user_levee_tab = "user_levee_lines"
        self.schema_levee_lyr = lyrs.data[self.schema_levee_tab]["qlyr"]
        self.user_levee_lyr = lyrs.data[self.user_levee_tab]["qlyr"]

    def set_user_fids(self):
        self.execute("UPDATE levee_data SET user_line_fid = fid;")

    def create_user_levees(self):
        remove_features(self.user_levee_lyr)
        self.set_user_fids()
        self.schema2user(self.schema_levee_lyr, self.user_levee_lyr, "polyline", levcrest="elev")


class SchemaBCConverter(SchemaConverter):
    def __init__(self, con, iface, lyrs):
        super(SchemaBCConverter, self).__init__(con, iface, lyrs)

        self.schema_bc_tab = "all_schem_bc"
        self.user_bc_tab = "user_bc_points"
        self.schema_bc_lyr = lyrs.data[self.schema_bc_tab]["qlyr"]
        self.user_bc_lyr = lyrs.data[self.user_bc_tab]["qlyr"]

        self.user_bc_lines = "user_bc_lines"
        self.user_bc_polygons = "user_bc_polygons"

        self.user_bc_lines_lyr = lyrs.data[self.user_bc_lines]["qlyr"]
        self.user_bc_polygons_lyr = lyrs.data[self.user_bc_polygons]["qlyr"]

    def update_bc_fids(self, bc_updates):
        cur = self.con.cursor()
        for table, fid, tab_bc_fid in bc_updates:
            qry = """UPDATE {0} SET bc_fid = ?, geom_type = ? WHERE fid = ?;""".format(table)
            cur.execute(qry, (fid, "point", tab_bc_fid))
        #             cur.execute(qry, (tab_bc_fid, "point", tab_bc_fid))
        self.con.commit()

    def create_user_bc(self):
        try:
            self.disable_geom_triggers()
            remove_features(self.user_bc_lyr)

            remove_features(self.user_bc_lines_lyr)
            remove_features(self.user_bc_polygons_lyr)

            fields = self.user_bc_lyr.fields()
            common_fnames = {"fid": "fid", "type": "type"}
            geom_fn = self.geom_functions["centroid"]
            new_features = []
            bc_updates = []
            for feat in self.schema_bc_lyr.getFeatures():
                if feat is None:
                    continue
                if feat.geometry().isNull():
                    continue
                new_feat = self.set_feature(feat, fields, common_fnames, geom_fn)
                new_features.append(new_feat)
                bc_updates.append((feat["type"], feat["fid"], feat["tab_bc_fid"]))
            #             bc_updates.append((new_feat['type'], new_feat['fid'], new_feat['tab_bc_fid']))
            self.user_bc_lyr.startEditing()
            self.user_bc_lyr.addFeatures(new_features)
            self.user_bc_lyr.commitChanges()
            self.user_bc_lyr.updateExtents()
            self.user_bc_lyr.triggerRepaint()
            self.user_bc_lyr.removeSelection()
            self.update_bc_fids(bc_updates)
            self.enable_geom_triggers()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 100321.1010:\nConversion of Boundary Conditions to User Layer failed!"
                + "\n_______________________________________________________________",
                e,
            )


class SchemaFPXSECConverter(SchemaConverter):
    def __init__(self, con, iface, lyrs):
        super(SchemaFPXSECConverter, self).__init__(con, iface, lyrs)

        self.schema_fpxsec_tab = "fpxsec"
        self.user_fpxsec_tab = "user_fpxsec"

        self.schema_fpxsec_lyr = lyrs.data[self.schema_fpxsec_tab]["qlyr"]
        self.user_fpxsec_lyr = lyrs.data[self.user_fpxsec_tab]["qlyr"]

    def create_user_fpxsec(self):
        remove_features(self.user_fpxsec_lyr)
        self.schema2user(self.schema_fpxsec_lyr, self.user_fpxsec_lyr, "polyline")


class SchemaGridConverter(SchemaConverter):
    def __init__(self, con, iface, lyrs):
        super(SchemaGridConverter, self).__init__(con, iface, lyrs)

        self.schema_grid_tab = "grid"
        self.user_boundary_tab = "user_model_boundary"
        self.user_roughness_tab = "user_roughness"
        self.user_elevation_tab = "user_elevation_polygons"

        self.schema_grid_lyr = lyrs.data[self.schema_grid_tab]["qlyr"]
        self.user_boundary_lyr = lyrs.data[self.user_boundary_tab]["qlyr"]
        self.user_roughness_lyr = lyrs.data[self.user_roughness_tab]["qlyr"]
        self.user_elevation_lyr = lyrs.data[self.user_elevation_tab]["qlyr"]

    def boundary_from_grid(self):
        remove_features(self.user_boundary_lyr)
        cellsize = self.get_cont_par("CELLSIZE")
        fields = self.user_boundary_lyr.fields()
        biter = clustered_features(self.schema_grid_lyr, fields)
        bfeat = next(biter)
        bfeat.setAttribute("cell_size", cellsize)
        self.user_boundary_lyr.startEditing()
        self.user_boundary_lyr.addFeature(bfeat)
        self.user_boundary_lyr.commitChanges()
        self.user_boundary_lyr.updateExtents()
        self.user_boundary_lyr.triggerRepaint()
        self.user_boundary_lyr.removeSelection()

    def roughness_from_grid(self):
        remove_features(self.user_roughness_lyr)
        new_features = []
        fields = self.user_roughness_lyr.fields()
        for feat in clustered_features(self.schema_grid_lyr, fields, "n_value", n_value="n"):
            new_features.append(feat)
        self.user_roughness_lyr.startEditing()
        self.user_roughness_lyr.addFeatures(new_features)
        self.user_roughness_lyr.commitChanges()
        self.user_roughness_lyr.updateExtents()
        self.user_roughness_lyr.triggerRepaint()
        self.user_roughness_lyr.removeSelection()

    def elevation_from_grid(self):
        remove_features(self.user_elevation_lyr)
        new_features = []
        fields = self.user_elevation_lyr.fields()
        for feat in clustered_features(self.schema_grid_lyr, fields, "elevation", elevation="elev"):
            feat.setAttribute("membership", "grid")
            new_features.append(feat)
        self.user_elevation_lyr.startEditing()
        self.user_elevation_lyr.addFeatures(new_features)
        self.user_elevation_lyr.commitChanges()
        self.user_elevation_lyr.updateExtents()
        self.user_elevation_lyr.triggerRepaint()
        self.user_elevation_lyr.removeSelection()


class SchemaInfiltrationConverter(SchemaConverter):
    def __init__(self, con, iface, lyrs):
        super(SchemaInfiltrationConverter, self).__init__(con, iface, lyrs)

        self.user_infil_tab = "user_infiltration"
        self.schema_green_tab = "infil_areas_green"
        self.schema_scs_tab = "infil_areas_scs"
        self.schema_horton_tab = "infil_areas_horton"
        self.schema_chan_tab = "infil_areas_chan"

        self.user_infil_lyr = lyrs.data[self.user_infil_tab]["qlyr"]
        self.schema_green_lyr = lyrs.data[self.schema_green_tab]["qlyr"]
        self.schema_scs_lyr = lyrs.data[self.schema_scs_tab]["qlyr"]
        self.schema_horton_lyr = lyrs.data[self.schema_horton_tab]["qlyr"]
        self.schema_chan_lyr = lyrs.data[self.schema_chan_tab]["qlyr"]

        self.green_columns = [
            "hydc",
            "soils",
            "dthetan",
            "dthetad",
            "abstrinf",
            "rtimpf",
            "soil_depth",
        ]
        self.scs_columns = ["scsn"]
        self.horton_columns = ["fhorti", "fhortf", "deca", "fhorti"]
        self.chan_columns = ["hydconch"]

        self.lyrs_cols = [
            (self.schema_green_lyr, self.green_columns),
            (self.schema_scs_lyr, self.scs_columns),
            (self.schema_horton_lyr, self.horton_columns),
            (self.schema_chan_lyr, self.chan_columns),
        ]
        self.ui_fields = self.user_infil_lyr.fields()

    def user_infil_features(self, schema_lyr, columns):
        if "hydc" in columns:
            char = "F"
        elif "hydconch" in columns:
            char = "C"
        else:
            char = ""
        new_features = []
        fields = self.ui_fields
        for ifeat in clustered_features(schema_lyr, fields, *columns):
            ifeat.setAttribute("green_char", char)
            new_features.append(ifeat)
        return new_features

    def create_user_infiltration(self):
        remove_features(self.user_infil_lyr)
        self.user_infil_lyr.startEditing()
        for lyr, cols in self.lyrs_cols:
            new_features = self.user_infil_features(lyr, cols)
            self.user_infil_lyr.addFeatures(new_features)
        self.user_infil_lyr.commitChanges()
        self.user_infil_lyr.updateExtents()
        self.user_infil_lyr.triggerRepaint()
        self.user_infil_lyr.removeSelection()


class SchemaSWMMConverter(SchemaConverter):
    def __init__(self, con, iface, lyrs):
        super(SchemaSWMMConverter, self).__init__(con, iface, lyrs)

        self.user_swmm_inlets_junctions_tab = "user_swmm_inlets_junctions"
        self.user_swmm_outlets_tab = "user_swmm_outlets"
        self.schema_inlet_tab = "swmmflo"
        self.schema_outlet_tab = "swmmoutf"

        self.user_swmm_inlets_junctions_lyr = lyrs.data[self.user_swmm_inlets_junctions_tab]["qlyr"]
        self.user_swmm_outlets_lyr = lyrs.data[self.user_swmm_outlets_tab]["qlyr"]

        self.schema_inlet_lyr = lyrs.data[self.schema_inlet_tab]["qlyr"]
        self.schema_outlet_lyr = lyrs.data[self.schema_outlet_tab]["qlyr"]

        self.inlet_columns = [
            ("swmm_jt", "grid"),
            ("swmm_iden", "name"),
            ("intype", "intype"),
            ("swmm_length", "swmm_length"),
            ("swmm_width", "swmm_width"),
            ("swmm_height", "swmm_height"),
            ("swmm_coeff", "swmm_coeff"),
            ("curbheight", "curbheight"),
            ("swmm_feature", "swmm_feature"),
        ]

        self.outlet_columns = [
            ("grid_fid", "grid"),
            ("name", "name"),
            ("outf_flo", "swmm_allow_discharge"),
        ]

        self.lyrs_cols = [
            (self.schema_inlet_lyr, self.inlet_columns),
            (self.schema_outlet_lyr, self.outlet_columns),
        ]

        self.ui_fields = self.user_swmm_inlets_junctions_lyr.fields()
        self.uo_fields = self.user_swmm_outlets_lyr.fields()
        self.rt_grids, self.rt_names = self.check_rating_tables()

    def check_rating_tables(self):
        rt_grids = {}
        rt_names = {}
        qry = "SELECT fid, grid_fid, name FROM swmmflort;"
        for fid, grid_fid, name in self.execute(qry):
            if grid_fid is None:
                continue
            else:
                rt_grids[grid_fid] = fid
                rt_names[grid_fid] = name
        return rt_grids, rt_names

    def user_swmm_inlets_junctions_features(self, schema_lyr, columns):
        sd_type = "I"
        new_features = []
        fields = self.ui_fields
        for feat in schema_lyr.getFeatures():
            geom = feat.geometry()
            point = geom.asPoint()
            new_geom = QgsGeometry.fromPointXY(point)
            new_feat = QgsFeature()
            new_feat.setFields(fields)
            new_feat.setGeometry(new_geom)
            new_feat.setAttribute("sd_type", sd_type)
            for schema_col, user_col in columns:
                new_feat.setAttribute(user_col, feat[schema_col])
            # if sd_type == "I":
            #     grid_fid = feat["swmm_jt"]
            #     if grid_fid in self.rt_grids:
            #         new_feat.setAttribute("rt_fid", self.rt_grids[grid_fid])
            #         new_feat.setAttribute("rt_name", self.rt_names[grid_fid])

            new_features.append(new_feat)
        return new_features

    def create_user_swmm_inlets_junctions(self):
        try:
            remove_features(self.user_swmm_inlets_junctions_lyr)
            sd_feats = self.user_swmm_inlets_junctions_features(self.schema_inlet_lyr, self.inlet_columns)
            self.user_swmm_inlets_junctions_lyr.startEditing()
            self.user_swmm_inlets_junctions_lyr.addFeatures(sd_feats)
            self.user_swmm_inlets_junctions_lyr.commitChanges()
            self.user_swmm_inlets_junctions_lyr.updateExtents()
            self.user_swmm_inlets_junctions_lyr.triggerRepaint()
            self.user_swmm_inlets_junctions_lyr.removeSelection()      
            
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 040319.1921:\n\nAdding features to Storm Drain Inlets/Junctions failed!"
                + "\n_______________________________________________________________",
                e,
            )

    def user_swmm_outlets_features(self, schema_lyr, columns):
        new_features = []
        fields = self.uo_fields
        for feat in schema_lyr.getFeatures():
            geom = feat.geometry()
            point = geom.asPoint()
            new_geom = QgsGeometry.fromPointXY(point)
            new_feat = QgsFeature()
            new_feat.setFields(fields)
            new_feat.setGeometry(new_geom)
            new_feat.setAttribute("outfall_type", "NORMAL")
            for schema_col, user_col in columns:
                new_feat.setAttribute(user_col, feat[schema_col])

            new_features.append(new_feat)
        return new_features

    def create_user_swmm_outlets(self):
        try:
            remove_features(self.user_swmm_outlets_lyr)
            sd_feats = self.user_swmm_outlets_features(self.schema_outlet_lyr, self.outlet_columns)
            self.user_swmm_outlets_lyr.startEditing()
            self.user_swmm_outlets_lyr.addFeatures(sd_feats)
            self.user_swmm_outlets_lyr.commitChanges()
            self.user_swmm_outlets_lyr.updateExtents()
            self.user_swmm_outlets_lyr.triggerRepaint()
            self.user_swmm_outlets_lyr.removeSelection()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 040319.1921:\n\nAdding features to Storm Drain Outfalls failed!"
                + "\n_______________________________________________________________",
                e,
            )
            
class SchemaHydrStructsConverter(SchemaConverter):
    def __init__(self, con, iface, lyrs):
        super(SchemaHydrStructsConverter, self).__init__(con, iface, lyrs)

        self.schema_struct_tab = "struct"
        self.user_struct_tab = "user_struct"

        self.schema_struct_lyr = lyrs.data[self.schema_struct_tab]["qlyr"]
        self.user_struct_lyr = lyrs.data[self.user_struct_tab]["qlyr"]

    def create_user_structure_lines(self):
        remove_features(self.user_struct_lyr)
        self.schema2user(self.schema_struct_lyr, self.user_struct_lyr, "polyline")

