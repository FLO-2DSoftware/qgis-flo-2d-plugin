# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from .utils import load_ui
from ..utils import is_number
from ..user_communication import UserCommunication
from operator import itemgetter
from qgis.core import QgsFeatureRequest, QgsRaster, QgsMapLayerRegistry
from table_editor_widget import StandardItemModel, StandardItem


uiDialog, qtBaseClass = load_ui('profile_tool')


class ProfileTool(qtBaseClass, uiDialog):
    """Tool for creating profile from schematized and user data."""

    USER_SCHEMA = {
        'user_levee_lines': {
            'user_name': 'Levee Lines',
            'schema_tab': 'levee_data',
            'schema_fid': 'user_line_fid',
            'schema_data': 'levcrest'
        },
        'user_streets': {
            'user_name': 'Street Lines',
            'schema_tab': 'street_seg',
            'schema_fid': 'str_fid',
            'schema_data': 'stman'
        },
        'user_centerline': {
            'user_name': 'River Centerline',
            'schema_tab': 'chan_elems',
            'schema_fid': 'seg_fid',
            'schema_data': 'depinitial'
        }
    }

    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.lyrs = lyrs
        self.plot = plot
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = None
        self.gutils = None

        self.fid = None
        self.user_tab = None
        self.user_lyr = None
        self.schema_lyr = None
        self.schema_fid = None
        self.schema_data = None

        self.user_feat = None
        self.feats_stations = None
        self.raster_layers = None

        self.table_dock = table
        self.tview = table.tview
        self.data_model = StandardItemModel()
        self.tview.setModel(self.data_model)
        self.rprofile_radio.setChecked(True)
        self.field_combo.setDisabled(True)
        self.rprofile_radio.toggled.connect(self.check_mode)
        self.raster_combo.currentIndexChanged.connect(self.plot_raster_data)
        self.field_combo.currentIndexChanged.connect(self.plot_schema_data)

    def setup_connection(self):
        self.plot.plot.enableAutoRange()
        self.populate_rasters()
        QgsMapLayerRegistry.instance().legendLayersAdded.connect(self.populate_rasters)
        QgsMapLayerRegistry.instance().layersRemoved.connect(self.populate_rasters)

    def identify_feature(self, user_table, fid):
        self.user_tab = user_table
        self.fid = fid
        self.user_lyr = self.lyrs.data[self.user_tab]['qlyr']
        self.schema_lyr = self.lyrs.data[self.USER_SCHEMA[self.user_tab]['schema_tab']]['qlyr']
        self.schema_fid = self.USER_SCHEMA[self.user_tab]['schema_fid']
        self.schema_data = self.USER_SCHEMA[self.user_tab]['schema_data']
        name = self.USER_SCHEMA[self.user_tab]['user_name']
        self.lyr_label.setText('{0} ({1})'.format(name, fid))
        self.populate_fields()
        self.calculate_stations()

    def check_mode(self):
        if self.rprofile_radio.isChecked():
            self.raster_combo.setEnabled(True)
            self.field_combo.setDisabled(True)
            self.populate_rasters()
            if self.fid is None:
                return
            self.plot_raster_data()
        else:
            self.raster_combo.setDisabled(True)
            self.field_combo.setEnabled(True)
            if self.fid is None:
                return
            self.populate_fields()
            self.plot_schema_data()

    def populate_rasters(self):
        """Get loaded rasters into combobox"""
        self.raster_combo.clear()
        rasters = self.lyrs.list_group_rlayers()
        for r in rasters:
            self.raster_combo.addItem(r.name(), r)

    def populate_fields(self):
        self.field_combo.clear()
        for field in self.schema_lyr.fields():
            if field.isNumeric():
                self.field_combo.addItem(field.name(), field)
            else:
                continue

    def calculate_stations(self):
        user_request = QgsFeatureRequest().setFilterExpression('"fid" = {0}'.format(self.fid))
        schema_request = QgsFeatureRequest().setFilterExpression('"{0}" = {1}'.format(self.schema_fid, self.fid))
        user_feats = self.user_lyr.getFeatures(user_request)
        schema_feats = self.schema_lyr.getFeatures(schema_request)
        user_feat = next(user_feats)
        geom = user_feat.geometry()
        self.user_feat = user_feat
        if self.user_tab == 'user_centerline':
            self.feats_stations = [(f, geom.lineLocatePoint(geom.intersection(f.geometry()))) for f in schema_feats]
        else:
            self.feats_stations = [(f, geom.lineLocatePoint(f.geometry().centroid())) for f in schema_feats]
        self.feats_stations.sort(key=itemgetter(1))
        if self.rprofile_radio.isChecked():
            self.plot_raster_data()
        else:
            self.plot_schema_data()

    def plot_raster_data(self):
        """
        Probing raster data and displaying on the plot.
        """
        idx = self.raster_combo.currentIndex()
        if idx == -1 or self.fid is None or self.feats_stations is None:
            self.plot.clear()
            return
        probe_raster = self.raster_combo.itemData(idx)
        if not probe_raster.isValid():
            return
        user_geom = self.user_feat.geometry()
        x, y = [], []
        for feat, station in self.feats_stations:
            point = user_geom.interpolate(station).asPoint()
            ident = probe_raster.dataProvider().identify(point, QgsRaster.IdentifyFormatValue)
            if ident.isValid():
                if is_number(ident.results()[1]):
                    val = round(ident.results()[1], 3)
                else:
                    val = None
                x.append(station)
                y.append(val)
        plot_data = [x, y]
        self.plot.clear()
        self.plot.add_item(self.user_tab, plot_data)

    def plot_schema_data(self):
        idx = self.field_combo.currentIndex()
        if idx == -1 or self.fid is None or self.feats_stations is None:
            self.plot.clear()
            return
        schema_data = self.field_combo.currentText()
        x, y = [], []
        for feat, pos in self.feats_stations:
            x.append(pos)
            y.append(feat[schema_data])
        plot_data = [x, y]
        self.plot.clear()
        self.plot.add_item(self.user_tab, plot_data)
