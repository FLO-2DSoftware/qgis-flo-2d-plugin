# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from operator import itemgetter

from PyQt5.QtCore import QSettings, QUrl
from qgis._core import QgsMessageLog
from qgis.core import QgsFeatureRequest, QgsProject, QgsRaster
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QStandardItem, QStandardItemModel
from PyQt5.QtGui import QDesktopServices

from .table_editor_widget import StandardItemModel, StandardItem
from ..flo2dobjects import ChannelSegment
from ..user_communication import UserCommunication
from ..utils import Msge, is_number
from .ui_utils import load_ui
from .xs_editor_widget import XsecEditorWidget

uiDialog, qtBaseClass = load_ui("profile_tool")


class ProfileTool(qtBaseClass, uiDialog):
    """
    Tool for creating profile from schematized and user data.
    """

    USER_SCHEMA = {
        "user_levee_lines": {
            "user_name": "Levee Lines",
            "schema_tab": "levee_data",
            "schema_fid": "user_line_fid",
        },
        "user_streets": {
            "user_name": "Street Lines",
            "schema_tab": "street_seg",
            "schema_fid": "str_fid",
        },
        "user_left_bank": {
            "user_name": "Left Bank Line",
            "schema_tab": "chan_elems",
            "schema_fid": "seg_fid",
        },
        "user_right_bank": {
            "user_name": "Right Bank Line",
            "schema_tab": "chan_elems",
            "schema_fid": "seg_fid",
        },
    }

    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.lyrs = lyrs

        self.plot = plot

        self.uc = UserCommunication(iface, "FLO-2D")

        self.system_units = {
            "CMS": ["m", "mps", "cms", "sq. m", "Pa"],
            "CFS": ["ft", "fps", "cfs", "sq. ft", "lb/sq. ft"]
        }

        self.fid = None
        self.user_tab = None
        self.user_lyr = None
        self.user_name = None
        self.schema_lyr = None
        self.schema_fid = None
        self.schema_data = None

        self.user_feat = None
        self.chan_seg = None
        self.feats_stations = None
        self.raster_layers = None

        self.plot_data = None
        self.table_dock = table
        self.tview = table.tview
        self.data_model = None

        self.rprofile_radio.setChecked(True)
        self.field_combo.setDisabled(True)
        self.rprofile_radio.toggled.connect(self.check_mode)
        self.profile_help_btn.clicked.connect(self.profile_help)
        self.raster_combo.currentIndexChanged.connect(self.plot_raster_data)
        self.field_combo.currentIndexChanged.connect(self.plot_schema_data)

    def setup_connection(self):
        """
        Initial settings after connection to GeoPackage.
        """
        self.plot.plot.enableAutoRange()
        self.populate_rasters()
        QgsProject.instance().legendLayersAdded.connect(self.populate_rasters)
        QgsProject.instance().layersRemoved.connect(self.populate_rasters)

    def identify_feature(self, user_table, fid):
        """
        Setting instance attributes based on user layer table name and fid.
        """
        self.user_tab = user_table
        self.fid = fid
        self.user_lyr = self.lyrs.data[self.user_tab]["qlyr"]
        self.schema_lyr = self.lyrs.data[self.USER_SCHEMA[self.user_tab]["schema_tab"]]["qlyr"]
        self.schema_fid = self.USER_SCHEMA[self.user_tab]["schema_fid"]
        self.user_name = self.USER_SCHEMA[self.user_tab]["user_name"]
        self.lyr_label.setText("{0} ({1})".format(self.user_name, fid))
        self.populate_fields()
        self.calculate_stations()

    def show_channel(self, table, fid):
        """
        Assign field values to schematized channels for Profile Tool.
        """
        self.chan_seg = ChannelSegment(fid, self.iface.f2d["con"], self.iface)
        self.chan_seg.get_row()  # Assigns to self.chan_seg all field values of the selected schematized channel:
        # 'name', 'depinitial',  'froudc',  'roughadj', 'isedn', 'notes', 'user_lbank_fid', 'rank'
        if self.chan_seg.get_profiles():
            self.plot_channel_data()

    def plot_channel_data(self):
        """
        Plot the Schema Data from channel data in the FLO-2D Plot.
        """
        if not self.chan_seg:
            return
        self.plot.clear()
        sta, lb, rb, bed, water, peak = [], [], [], [], [], []
        velocity = []
        froude = []
        flow_area = []
        w_perim = []
        hyd_radius = []
        top_w = []
        width_depth = []
        energy_slope = []
        shear_stress = []
        surf_area = []

        units = "CMS" if self.gutils.get_cont_par("METRIC") == "1" else "CFS"

        for st, data in self.chan_seg.profiles.items():
            sta.append(data["station"])
            lb.append(data["lbank_elev"])
            rb.append(data["rbank_elev"])
            bed.append(data["bed_elev"])
            if data["water"] == 0:
                water.append(data["bed_elev"])
            else:
                water.append(data["water"])
            peak.append(data["peak"] + data["bed_elev"])
            velocity.append(data["velocity"])
            froude.append(data["froude"])
            flow_area.append(data["flow_area"])
            w_perim.append(data["w_perim"])
            hyd_radius.append(data["hyd_radius"])
            top_w.append(data["top_w"])
            width_depth.append(data["width_depth"])
            energy_slope.append(data["energy_slope"])
            shear_stress.append(data["shear_stress"])
            surf_area.append(data["surf_area"])

        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)

        if data["water"] is not None:
            self.plot.plot.legend = None
            self.plot.plot.addLegend(offset=(0, 30))
            self.plot.plot.setTitle(title="Channel Profile - {}".format(self.chan_seg.name))
            self.plot.plot.setLabel("bottom", text="Channel length")
            self.plot.plot.setLabel("left", text="")
            self.plot.add_item(f"Bed elevation ({self.system_units[units][0]})", [sta, bed], col=QColor(Qt.black), sty=Qt.SolidLine)
            self.plot.add_item(f"Left bank ({self.system_units[units][0]})", [sta, lb], col=QColor(Qt.darkGreen), sty=Qt.SolidLine)
            self.plot.add_item(f"Right bank ({self.system_units[units][0]})", [sta, rb], col=QColor(Qt.darkYellow), sty=Qt.SolidLine)
            self.plot.add_item(f"Max. Water ({self.system_units[units][0]})", [sta, water], col=QColor(Qt.blue), sty=Qt.SolidLine, hide=True)
            self.plot.add_item(f"Velocity ({self.system_units[units][1]})", [sta, velocity], col=QColor(Qt.green), sty=Qt.SolidLine, hide=True)
            self.plot.add_item(f"Froude", [sta, froude], col=QColor(Qt.gray), sty=Qt.SolidLine, hide=True)
            self.plot.add_item(f"Flow area ({self.system_units[units][3]})", [sta, flow_area], col=QColor(Qt.red), sty=Qt.SolidLine, hide=True)
            self.plot.add_item(f"Wetted perimeter ({self.system_units[units][0]})", [sta, w_perim], col=QColor(Qt.yellow), sty=Qt.SolidLine, hide=True)
            self.plot.add_item(f"Hydraulic radius ({self.system_units[units][0]})", [sta, hyd_radius], col=QColor(Qt.darkBlue), sty=Qt.SolidLine, hide=True)
            self.plot.add_item(f"Top width ({self.system_units[units][0]})", [sta, top_w], col=QColor(Qt.darkRed), sty=Qt.SolidLine, hide=True)
            self.plot.add_item(f"Width/Depth", [sta, width_depth], col=QColor(Qt.darkCyan), sty=Qt.SolidLine, hide=True)
            self.plot.add_item(f"Energy slope", [sta, energy_slope], col=QColor(Qt.magenta), sty=Qt.SolidLine, hide=True)
            self.plot.add_item(f"Shear stress ({self.system_units[units][4]})", [sta, shear_stress], col=QColor(Qt.darkYellow), hide=True)
            self.plot.add_item(f"Surface area ({self.system_units[units][3]})", [sta, surf_area], col=QColor(Qt.darkMagenta), hide=True)

            try:  # Build table.
                data_model = StandardItemModel()
                self.tview.undoStack.clear()
                self.tview.setModel(data_model)
                data_model.clear()
                data_model.setHorizontalHeaderLabels([f"Station ({self.system_units[units][0]})",
                                                      f"Bed elevation ({self.system_units[units][0]})",
                                                      f"Left bank ({self.system_units[units][0]})",
                                                      f"Max. Water ({self.system_units[units][0]})",
                                                      f"Velocity ({self.system_units[units][1]})",
                                                      f"Froude",
                                                      f"Flow area ({self.system_units[units][3]})",
                                                      f"Wetted perimeter ({self.system_units[units][0]})",
                                                      f"Hydraulic radius ({self.system_units[units][0]})",
                                                      f"Top width ({self.system_units[units][0]})",
                                                      f"Width/Depth",
                                                      f"Energy slope",
                                                      f"Shear stress ({self.system_units[units][4]})",
                                                      f"Surface area ({self.system_units[units][3]})"])

                data = zip(sta, bed, lb, rb, water, velocity, froude, flow_area, w_perim, hyd_radius, top_w, width_depth, energy_slope, shear_stress, surf_area)
                for station, bed_elev, left_bank, right_bank, mw, vel, fr, fa, wp, hr, tw, wd, es, ss, sa in data:
                    station_item = StandardItem("{:.2f}".format(station)) if station is not None else StandardItem("")
                    bed_item = StandardItem("{:.2f}".format(bed_elev)) if bed_elev is not None else StandardItem("")
                    left_bank_item = StandardItem("{:.2f}".format(left_bank)) if left_bank is not None else StandardItem("")
                    right_bank_item = StandardItem("{:.2f}".format(right_bank)) if right_bank is not None else StandardItem("")
                    max_water_item = StandardItem("{:.2f}".format(mw)) if mw is not None else StandardItem("")
                    velocity_item = StandardItem("{:.2f}".format(vel)) if vel is not None else StandardItem("")
                    froude_item = StandardItem("{:.2f}".format(fr)) if fr is not None else StandardItem("")
                    flow_area_item = StandardItem("{:.2f}".format(fa)) if fa is not None else StandardItem("")
                    wet_perim_item = StandardItem("{:.2f}".format(wp)) if wp is not None else StandardItem("")
                    h_radius_item = StandardItem("{:.2f}".format(hr)) if hr is not None else StandardItem("")
                    top_width_item = StandardItem("{:.2f}".format(tw)) if tw is not None else StandardItem("")
                    widthdepth_item = StandardItem("{:.2f}".format(wd)) if wd is not None else StandardItem("")
                    ener_slo_item = StandardItem("{:.2f}".format(es)) if es is not None else StandardItem("")
                    shearstress_item = StandardItem("{:.2f}".format(ss)) if ss is not None else StandardItem("")
                    surfacearea_item = StandardItem("{:.2f}".format(sa)) if sa is not None else StandardItem("")
                    data_model.appendRow([station_item,
                                          bed_item,
                                          left_bank_item,
                                          right_bank_item,
                                          max_water_item,
                                          velocity_item,
                                          froude_item,
                                          flow_area_item,
                                          wet_perim_item,
                                          h_radius_item,
                                          top_width_item,
                                          widthdepth_item,
                                          ener_slo_item,
                                          shearstress_item,
                                          surfacearea_item,
                                          ])

                self.tview.horizontalHeader().setStretchLastSection(True)
                for col in range(3):
                    self.tview.setColumnWidth(col, 100)
                for i in range(data_model.rowCount()):
                    self.tview.setRowHeight(i, 20)
                return
            except:
                self.uc.bar_warn("Error while building table for channel!")
                self.uc.log_info("Error while building table for channel!")
                return

        else:
            self.plot.plot.addLegend()
            self.plot.add_item(f"Bed elevation ({self.system_units[units][0]})", [sta, bed], col=QColor(Qt.black), sty=Qt.SolidLine)
            self.plot.add_item(f"Left bank ({self.system_units[units][0]})", [sta, lb], col=QColor(Qt.darkGreen), sty=Qt.SolidLine)
            self.plot.add_item(f"Right bank ({self.system_units[units][0]})", [sta, rb], col=QColor(Qt.darkYellow), sty=Qt.SolidLine)
            self.plot.plot.setTitle(title="Channel Profile - {}".format(self.chan_seg.name))
            self.plot.plot.setLabel("bottom", text="Channel length")
            self.plot.plot.setLabel("left", text="Elevation")

            try:  # Build table.
                data_model = StandardItemModel()
                self.tview.undoStack.clear()
                self.tview.setModel(data_model)
                data_model.clear()
                data_model.setHorizontalHeaderLabels([f"Station ({self.system_units[units][0]})",
                                                      f"Bed elevation ({self.system_units[units][0]})",
                                                      f"Left bank ({self.system_units[units][0]})",
                                                      f"Right bank ({self.system_units[units][0]})"])

                data = zip(sta, bed, lb, rb)
                for station, bed_elev, left_bank, right_bank in data:
                    station_item = StandardItem("{:.2f}".format(station)) if station is not None else StandardItem("")
                    bed_item = StandardItem("{:.2f}".format(bed_elev)) if bed_elev is not None else StandardItem("")
                    left_bank_item = StandardItem("{:.2f}".format(left_bank)) if left_bank is not None else StandardItem("")
                    right_bank_item = StandardItem("{:.2f}".format(right_bank)) if right_bank is not None else StandardItem("")
                    data_model.appendRow([station_item, bed_item, left_bank_item, right_bank_item])

                self.tview.horizontalHeader().setStretchLastSection(True)
                for col in range(3):
                    self.tview.setColumnWidth(col, 100)
                for i in range(data_model.rowCount()):
                    self.tview.setRowHeight(i, 20)
                return
            except:
                self.uc.bar_warn("Error while building table for channel!")
                return

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

    def profile_help(self):
        QDesktopServices.openUrl(QUrl("https://flo-2dsoftware.github.io/FLO-2D-Documentation/Plugin1000/widgets/profile-tool/Profile%20Tool.html"))        

    def populate_rasters(self):
        """
        Get loaded rasters into combobox.
        """
        self.raster_combo.clear()
        try:
            rasters = self.lyrs.list_group_rlayers()
        except AttributeError:
            return
        for r in rasters:
            self.raster_combo.addItem(r.name(), r)

    def populate_fields(self):
        """
        Get schematic layer field into combobox.
        """
        self.field_combo.clear()
        for field in self.schema_lyr.fields():
            if field.isNumeric():
                fname = field.name()
                if fname != "id":
                    self.field_combo.addItem(fname, field)
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
        if self.user_tab == "user_left_bank":
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
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)
        self.plot.plot.addLegend()

        self.plot.add_item(self.user_tab, self.plot_data)
        self.plot.plot.setTitle(title='"{0}" profile'.format(self.user_name))
        self.plot.plot.setLabel("bottom", text="Distance along feature ({0})".format(self.fid))
        self.plot.plot.setLabel("left", text="Raster value")
        self.insert_to_table(name_x="Distance", name_y="Raster value")

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
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)
        self.plot.plot.addLegend()

        self.plot.add_item(self.user_tab, self.plot_data)
        self.plot.plot.setTitle(title='"{0}" profile'.format(self.user_name))
        self.plot.plot.setLabel("bottom", text="Distance along feature ({0})".format(self.fid))
        self.plot.plot.setLabel("left", text=self.schema_data)
        self.insert_to_table(name_x="Distance", name_y=self.schema_data)

    def insert_to_table(self, name_x="axis_x", name_y="axis_y"):
        """
        Inserting data into table view.
        """
        self.data_model = QStandardItemModel()
        self.data_model.setHorizontalHeaderLabels([name_x, name_y])
        axis_x, axis_y = self.plot_data
        for x, y in zip(axis_x, axis_y):
            qx = QStandardItem(str(round(x, 3)))
            qy = QStandardItem(str(y))
            items = [qx, qy]
            self.data_model.appendRow(items)
        self.tview.setModel(self.data_model)
        self.tview.resizeColumnsToContents()
        for i in range(self.data_model.rowCount()):
            self.tview.setRowHeight(i, 20)
