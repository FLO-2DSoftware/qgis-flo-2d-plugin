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
from itertools import izip
from qgis.core import QgsFeatureRequest, QgsRaster, QgsMapLayerRegistry
from PyQt4.QtGui import QStandardItemModel, QStandardItem


uiDialog, qtBaseClass = load_ui('profile_tool')


class ProfileTool(qtBaseClass, uiDialog):
    """
    Tool for creating profile from schematized and user data.
    """

    USER_SCHEMA = {
        'user_levee_lines': {
            'user_name': 'Levee Lines',
            'schema_tab': 'levee_data',
            'schema_fid': 'user_line_fid'
        },
        'user_streets': {
            'user_name': 'Street Lines',
            'schema_tab': 'street_seg',
            'schema_fid': 'str_fid'
        },
        'user_centerline': {
            'user_name': 'River Centerline',
            'schema_tab': 'chan_elems',
            'schema_fid': 'seg_fid'
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

        self.fid = None
        self.user_tab = None
        self.user_lyr = None
        self.user_name = None
        self.schema_lyr = None
        self.schema_fid = None
        self.schema_data = None

        self.user_feat = None
        self.feats_stations = None
        self.raster_layers = None

        self.plot_data = None
        self.table_dock = table
        self.tview = table.tview
        self.data_model = None

        self.rprofile_radio.setChecked(True)
        self.field_combo.setDisabled(True)
        self.rprofile_radio.toggled.connect(self.check_mode)
        self.raster_combo.currentIndexChanged.connect(self.plot_raster_data)
        self.field_combo.currentIndexChanged.connect(self.plot_schema_data)

    def setup_connection(self):
        """
        Initial settings after connection to GeoPackage.
        """
        self.plot.plot.enableAutoRange()
        self.populate_rasters()
        QgsMapLayerRegistry.instance().legendLayersAdded.connect(self.populate_rasters)
        QgsMapLayerRegistry.instance().layersRemoved.connect(self.populate_rasters)

    def identify_feature(self, user_table, fid):
        """
        Setting instance attributes based on user layer table name and fid.
        """
        self.user_tab = user_table
        self.fid = fid
        self.user_lyr = self.lyrs.data[self.user_tab]['qlyr']
        self.schema_lyr = self.lyrs.data[self.USER_SCHEMA[self.user_tab]['schema_tab']]['qlyr']
        self.schema_fid = self.USER_SCHEMA[self.user_tab]['schema_fid']
        self.user_name = self.USER_SCHEMA[self.user_tab]['user_name']
        self.lyr_label.setText('{0} ({1})'.format(self.user_name, fid))
        self.populate_fields()
        self.calculate_stations()

    def check_mode(self):
        """
        Checking plotting mode.
        """
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
        """
        Get loaded rasters into combobox.
        """
        self.raster_combo.clear()
        rasters = self.lyrs.list_group_rlayers()
        for r in rasters:
            self.raster_combo.addItem(r.name(), r)

    def populate_fields(self):
        """
        Get schematic layer field into combobox.
        """
        self.field_combo.clear()
        for field in self.schema_lyr.fields():
            if field.isNumeric():
                self.field_combo.addItem(field.name(), field)
            else:
                continue

    def calculate_stations(self):
        """
        Calculating stations based on combined user and schematic layers.
        """
        user_request = QgsFeatureRequest().setFilterExpression('"fid" = {0}'.format(self.fid))
        schema_request = QgsFeatureRequest().setFilterExpression('"{0}" = {1}'.format(self.schema_fid, self.fid))
        user_feats = self.user_lyr.getFeatures(user_request)
        schema_feats = self.schema_lyr.getFeatures(schema_request)
        user_feat = next(user_feats)
        geom = user_feat.geometry()
        self.user_feat = user_feat
        if self.user_tab == 'user_centerline':
            self.feats_stations = [(f, geom.lineLocatePoint(f.geometry().nearestPoint(geom))) for f in schema_feats]
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
        if self.vprofile_radio.isChecked():
            return
        if idx == -1 or self.fid is None or self.feats_stations is None:
            self.plot.clear()
            return
        probe_raster = self.raster_combo.itemData(idx)
        if not probe_raster.isValid():
            return
        user_geom = self.user_feat.geometry()
        axis_x, axis_y = [], []
        for feat, station in self.feats_stations:
            point = user_geom.interpolate(station).asPoint()
            ident = probe_raster.dataProvider().identify(point, QgsRaster.IdentifyFormatValue)
            if ident.isValid():
                if is_number(ident.results()[1]):
                    val = round(ident.results()[1], 3)
                else:
                    val = None
                axis_x.append(station)
                axis_y.append(val)
        self.plot_data = [axis_x, axis_y]
        self.plot.clear()
        self.plot.add_item(self.user_tab, self.plot_data)
        self.plot.plot.setTitle(title='"{0}" profile'.format(self.user_name))
        self.plot.plot.setLabel('bottom', text='Distance along feature ({0})'.format(self.fid))
        self.plot.plot.setLabel('left', text='Raster value')
        self.insert_to_table(name_x='Distance', name_y='Raster value')

    def plot_schema_data(self):
        """
        Displaying schematic data on the plot.
        """
        if self.rprofile_radio.isChecked():
            return
        idx = self.field_combo.currentIndex()
        if idx == -1 or self.fid is None or self.feats_stations is None:
            self.plot.clear()
            return
        self.schema_data = self.field_combo.currentText()
        axis_x, axis_y = [], []
        for feat, pos in self.feats_stations:
            schema_data = feat[self.schema_data]
            if is_number(schema_data) is False:
                continue
            axis_x.append(pos)
            axis_y.append(schema_data)
        self.plot_data = [axis_x, axis_y]
        self.plot.clear()
        self.plot.add_item(self.user_tab, self.plot_data)
        self.plot.plot.setTitle(title='"{0}" profile'.format(self.user_name))
        self.plot.plot.setLabel('bottom', text='Distance along feature ({0})'.format(self.fid))
        self.plot.plot.setLabel('left', text=self.schema_data)
        self.insert_to_table(name_x='Distance', name_y=self.schema_data)

    def insert_to_table(self, name_x='axis_x', name_y='axis_y'):
        """
        Inserting data into table view.
        """
        self.data_model = QStandardItemModel()
        self.data_model.setHorizontalHeaderLabels([name_x, name_y])
        axis_x, axis_y = self.plot_data
        for x, y in izip(axis_x, axis_y):
            qx = QStandardItem(str(round(x, 3)))
            qy = QStandardItem(str(y))
            items = [qx, qy]
            self.data_model.appendRow(items)
        self.tview.setModel(self.data_model)
        self.tview.resizeColumnsToContents()
