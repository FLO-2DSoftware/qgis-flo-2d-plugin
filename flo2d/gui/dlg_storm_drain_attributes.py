# -*- coding: utf-8 -*-
from qgis._core import QgsFeatureRequest

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


from .ui_utils import load_ui, set_icon, center_canvas, zoom
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..utils import TimeSeriesDelegate, is_true, FloatDelegate
import csv
import io
import os

from PyQt5.QtCore import Qt, QSettings, pyqtSignal
from PyQt5.QtGui import QColor, QKeySequence, QDoubleValidator
from PyQt5.QtWidgets import QDockWidget, QComboBox, QSpinBox, QDoubleSpinBox, QTableWidgetItem, QApplication, \
    QFileDialog, QUndoStack
from qgis._gui import QgsDockWidget

uiDialog, qtBaseClass = load_ui("inlet_attributes")


class InletAttributes(qtBaseClass, uiDialog):
    def __init__(self, con, iface, layers):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = layers
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = con
        self.gutils = GeoPackageUtils(con, iface)

        # Create a dock widget
        self.dock_widget = QgsDockWidget("Inlets/Junctions", self.iface.mainWindow())
        self.dock_widget.setObjectName("Inlets/Junctions")
        self.dock_widget.setWidget(self)

        self.current_node = None
        self.previous_node = None
        self.next_node = None

        # Connections
        self.name.editingFinished.connect(self.save_inlets_junctions)
        self.junction_invert_elev.editingFinished.connect(self.save_inlets_junctions)
        self.max_depth.editingFinished.connect(self.save_inlets_junctions)
        self.init_depth.editingFinished.connect(self.save_inlets_junctions)
        self.surcharge_depth.editingFinished.connect(self.save_inlets_junctions)
        self.intype.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_length.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_width.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_height.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_coeff.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_feature.editingFinished.connect(self.save_inlets_junctions)
        self.curbheight.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_clogging_factor.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_time_for_clogging.editingFinished.connect(self.save_inlets_junctions)
        self.drboxarea.editingFinished.connect(self.save_inlets_junctions)

        self.user_swmm_inlets_junctions_lyr = self.lyrs.data["user_swmm_inlets_junctions"]["qlyr"]

        # self.dock_widget.visibilityChanged.connect(self.clear_rubber)

        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)

        self.next_btn.clicked.connect(self.populate_next_node)
        self.previous_btn.clicked.connect(self.populate_previous_node)
        self.external_btn.clicked.connect(self.show_external_inflow_dlg)

        self.eye_btn.clicked.connect(self.find_junction_inlet)

        self.inlets_junctions = {
            self.label_4: self.junction_invert_elev,
            self.label_5: self.max_depth,
            self.label_10: self.init_depth,
            self.label_11: self.surcharge_depth,
            self.label_19: self.intype,
            self.label_7: self.swmm_length,
            self.label_8: self.swmm_width,
            self.label_9: self.swmm_height,
            self.label_12: self.swmm_coeff,
            self.label_13: self.swmm_feature,
            self.label_14: self.curbheight,
            self.label_15: self.swmm_clogging_factor,
            self.label_16: self.swmm_time_for_clogging,
            self.label_17: self.drboxarea,
        }
        if self.sd_type.count() == 0:
            self.sd_type.addItem("Inlet")
            self.sd_type.addItem("Junction")

        if self.external_inflow.count() == 0:
            self.external_inflow.addItem("NO")
            self.external_inflow.addItem("YES")

        self.sd_type.currentIndexChanged.connect(self.save_inlets_junctions)
        self.external_inflow.currentIndexChanged.connect(self.external_inflow_btn_chk)

    def populate_attributes(self, fid):
        """
        Function to populate the attributes
        """
        if not fid:
            return

        self.clear_rubber()

        self.current_node = fid
        self.lyrs.show_feat_rubber(self.user_swmm_inlets_junctions_lyr.id(), fid, QColor(Qt.red))

        # Get the attributes
        attributes = self.gutils.execute(
            f"""SELECT 
                    grid,
                    name, 
                    sd_type,
                    external_inflow, 
                    junction_invert_elev, 
                    max_depth,
                    init_depth,
                    surcharge_depth,
                    intype,
                    swmm_length, 
                    swmm_width, 
                    swmm_height, 
                    swmm_coeff, 
                    swmm_feature,
                    curbheight,
                    swmm_clogging_factor, 
                    swmm_time_for_clogging,
                    drboxarea                                     
                FROM
                    user_swmm_inlets_junctions
                WHERE
                    fid = {fid};"""
        ).fetchall()[0]

        self.disconnect_signals()

        # Assign attributes to the dialog
        self.grid.setText(str(attributes[0]))
        self.name.setText(str(attributes[1]))
        if attributes[2].lower().startswith('i'):
            self.sd_type.setCurrentIndex(0)
        else:
            self.sd_type.setCurrentIndex(1)
        if attributes[3] == 1:
            external_inflow = 'YES'
        else:
            external_inflow = 'NO'
        self.external_inflow.setCurrentText(external_inflow)
        idx = 4
        for key, value in self.inlets_junctions.items():
            if attributes[idx] is not None:
                if isinstance(value, QSpinBox) or isinstance(value, QDoubleSpinBox):
                    value.setValue(attributes[idx])
                elif isinstance(value, QComboBox):
                    value.setCurrentText(attributes[idx])
            idx += 1

        self.connect_signals()

        self.previous_btn.setEnabled(False)
        self.next_btn.setEnabled(False)

        self.next_node = self.gutils.execute(
            f"""
            SELECT 
                conduit_inlet
            FROM 
                user_swmm_conduits
            WHERE 
                conduit_outlet = '{str(attributes[1])}' LIMIT 1;
            """
        ).fetchall()

        if self.next_node:
            self.next_btn.setEnabled(True)
            self.next_lbl.setText(self.next_node[0][0])

        self.previous_node = self.gutils.execute(
            f"""
            SELECT 
                conduit_outlet
            FROM 
                user_swmm_conduits
            WHERE 
                conduit_inlet = '{str(attributes[1])}' LIMIT 1;
            """
        ).fetchall()

        if self.previous_node:
            self.previous_btn.setEnabled(True)
            self.previous_lbl.setText(self.previous_node[0][0])

    def save_inlets_junctions(self):
        """
        Function to save the inlets everytime an attribute is changed
        """

        old_name_qry = self.gutils.execute(
            f"""SELECT name FROM user_swmm_inlets_junctions WHERE fid = '{self.current_node}';""").fetchall()
        old_name = ""
        if old_name_qry:
            old_name = old_name_qry[0][0]

        name = self.name.text()
        junction_invert_elev = self.junction_invert_elev.value()
        max_depth = self.max_depth.value()
        init_depth = self.init_depth.value()
        surcharge_depth = self.surcharge_depth.value()
        sd_type = self.sd_type.currentText()[0]
        intype = self.intype.value()
        swmm_length = self.swmm_length.value()
        swmm_width = self.swmm_width.value()
        swmm_height = self.swmm_height.value()
        swmm_coeff = self.swmm_coeff.value()
        swmm_feature = self.swmm_feature.value()
        curbheight = self.curbheight.value()
        swmm_clogging_factor = self.swmm_clogging_factor.value()
        swmm_time_for_clogging = self.swmm_time_for_clogging.value()
        drboxarea = self.drboxarea.value()

        self.gutils.execute(f"""
                                UPDATE 
                                    user_swmm_inlets_junctions
                                SET 
                                    name = '{name}',
                                    junction_invert_elev = '{junction_invert_elev}',
                                    max_depth = '{max_depth}',
                                    init_depth = '{init_depth}',
                                    surcharge_depth = '{surcharge_depth}',
                                    sd_type = '{sd_type}',
                                    intype = '{intype}',
                                    swmm_length = '{swmm_length}', 
                                    swmm_width = '{swmm_width}', 
                                    swmm_height = '{swmm_height}', 
                                    swmm_coeff = '{swmm_coeff}', 
                                    swmm_feature = '{swmm_feature}',
                                    curbheight = '{curbheight}',
                                    swmm_clogging_factor = '{swmm_clogging_factor}', 
                                    swmm_time_for_clogging = '{swmm_time_for_clogging}',
                                    drboxarea = '{drboxarea}'
                                WHERE 
                                    fid = '{self.current_node}';
                            """)

        self.user_swmm_inlets_junctions_lyr.triggerRepaint()

        # update the name on the user_swmm_conduits, user_swmm_weirs, user_swmm_pumps, and user_swmm_orifices
        if old_name != name:
            # Updating Conduits
            update_conduits_inlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_conduits
                WHERE 
                    conduit_inlet = '{old_name}';
                """
            ).fetchall()
            if update_conduits_inlets_qry:
                for inlet in update_conduits_inlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_conduits
                        SET 
                            conduit_inlet = '{name}'
                        WHERE 
                            fid = '{inlet[0]}';
                    """)

            update_conduits_outlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_conduits
                WHERE 
                    conduit_outlet = '{old_name}';
                """
            ).fetchall()
            if update_conduits_outlets_qry:
                for outlet in update_conduits_outlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_conduits
                        SET 
                            conduit_outlet = '{name}'
                        WHERE 
                            fid = '{outlet[0]}';
                    """)

            # Updating Pumps
            update_pumps_inlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_pumps
                WHERE 
                    pump_inlet = '{old_name}';
                """
            ).fetchall()
            if update_pumps_inlets_qry:
                for inlet in update_pumps_inlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_pumps
                        SET 
                            pump_inlet = '{name}'
                        WHERE 
                            fid = '{inlet[0]}';
                    """)

            update_pumps_outlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_pumps
                WHERE 
                    pump_outlet = '{old_name}';
                """
            ).fetchall()
            if update_pumps_outlets_qry:
                for outlet in update_pumps_outlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_pumps
                        SET 
                            pump_outlet = '{name}'
                        WHERE 
                            fid = '{outlet[0]}';
                    """)

            # Updating Weirs
            update_weirs_inlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_weirs
                WHERE 
                    weir_inlet = '{old_name}';
                """
            ).fetchall()
            if update_weirs_inlets_qry:
                for inlet in update_weirs_inlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_weirs
                        SET 
                            weir_inlet = '{name}'
                        WHERE 
                            fid = '{inlet[0]}';
                    """)

            update_weirs_outlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_weirs
                WHERE 
                    weir_outlet = '{old_name}';
                """
            ).fetchall()
            if update_weirs_outlets_qry:
                for outlet in update_weirs_outlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_weirs
                        SET 
                            weir_outlet = '{name}'
                        WHERE 
                            fid = '{outlet[0]}';
                    """)

            # Updating Orifices
            update_orifices_inlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_orifices
                WHERE 
                    orifice_inlet = '{old_name}';
                """
            ).fetchall()
            if update_orifices_inlets_qry:
                for inlet in update_orifices_inlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_orifices
                        SET 
                            orifice_inlet = '{name}'
                        WHERE 
                            fid = '{inlet[0]}';
                    """)

            update_orifices_outlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_orifices
                WHERE 
                    orifice_outlet = '{old_name}';
                """
            ).fetchall()
            if update_orifices_outlets_qry:
                for outlet in update_orifices_outlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_orifices
                        SET 
                            orifice_outlet = '{name}'
                        WHERE 
                            fid = '{outlet[0]}';
                    """)

        self.populate_attributes(self.current_node)

    def dock_widget(self):
        """ Close and delete the dock widget. """
        if self.dock_widget:
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget.close()
            self.dock_widget.deleteLater()
            self.dock_widget = None

    def clear_rubber(self):
        """
        Function to clear the rubber when closing the widget
        """
        self.lyrs.clear_rubber()

    def populate_next_node(self):
        """
        Function to populate data when the user clicks on the next btn
        """
        next_node_name = self.next_lbl.text()

        fid = self.gutils.execute(
            f"""
            SELECT
                fid
            FROM
                user_swmm_inlets_junctions
            WHERE
                name = '{next_node_name}'
            """
        ).fetchone()

        if fid:
            self.populate_attributes(fid[0])

    def populate_previous_node(self):
        """
        Function to populate data when the user clicks on the previous btn
        """
        previous_node_name = self.previous_lbl.text()

        fid = self.gutils.execute(
            f"""
            SELECT
                fid
            FROM
                user_swmm_inlets_junctions
            WHERE
                name = '{previous_node_name}'
            """
        ).fetchone()

        if fid:
            self.populate_attributes(fid[0])

    def show_external_inflow_dlg(self):
        """
        Function to show the external inflow in the Inlets/Junctions
        """
        name = self.name.text()
        if name == "":
            return

        dlg_external_inflow = ExternalInflowsDialog(self.iface, name)
        dlg_external_inflow.setWindowTitle("Inlet/Junction " + name)
        save = dlg_external_inflow.exec_()
        if save:
            inflow_sql = "SELECT baseline, pattern_name, time_series_name FROM swmm_inflows WHERE node_name = ?;"
            inflow = self.gutils.execute(inflow_sql, (name,)).fetchone()
            if inflow:
                baseline = inflow[0]
                pattern_name = inflow[1]
                time_series_name = inflow[2]
                if baseline == 0.0 and time_series_name == "":
                    self.external_inflow.setCurrentIndex(0)
                else:
                    self.external_inflow.setCurrentIndex(1)

            self.uc.bar_info("Storm Drain external inflow saved for inlet " + name)
            self.uc.log_info("Storm Drain external inflow saved for inlet " + name)

    def external_inflow_btn_chk(self):
        """
        Function to enable/disable the external inflow btn
        """
        external_inflow = self.external_inflow.currentText()

        if external_inflow == 'YES':
            self.external_btn.setEnabled(True)
            external_inflow_bool = 1
        else:
            self.external_btn.setEnabled(False)
            external_inflow_bool = 0

        self.gutils.execute(f"""
                                UPDATE 
                                    user_swmm_inlets_junctions
                                SET 
                                    external_inflow = '{external_inflow_bool}'
                                WHERE 
                                    fid = '{self.current_node}';
                            """)

    def zoom_in(self):
        """
        Function to zoom in
        """
        currentCell = next(self.user_swmm_inlets_junctions_lyr.getFeatures(QgsFeatureRequest(self.current_node)))
        if currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, 0.4)
            QApplication.restoreOverrideCursor()

    def zoom_out(self):
        """
        Function to zoom out
        """
        currentCell = next(self.user_swmm_inlets_junctions_lyr.getFeatures(QgsFeatureRequest(self.current_node)))
        if currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, -0.4)
            QApplication.restoreOverrideCursor()

    def find_junction_inlet(self):
        """
        Function to find a junction and populate the data
        """
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                return

            name = self.search_le.text()
            grid_qry = self.gutils.execute(f"SELECT fid, grid FROM user_swmm_inlets_junctions WHERE name = '{name}'").fetchone()
            if grid_qry:
                self.current_node = grid_qry[0]
                cell = grid_qry[1]
            else:
                self.uc.bar_error("Inlet/Junction not found!")
                self.uc.log_info("Inlet/Junction not found!")
                return

            grid = self.lyrs.data["grid"]["qlyr"]
            if grid is not None:
                if grid:
                    self.lyrs.show_feat_rubber(self.user_swmm_inlets_junctions_lyr.id(), self.current_node, QColor(Qt.red))
                    feat = next(grid.getFeatures(QgsFeatureRequest(cell)))
                    x, y = feat.geometry().centroid().asPoint()
                    center_canvas(self.iface, x, y)
                    zoom(self.iface, 0.4)
                    self.populate_attributes(self.current_node)

        except Exception:
            self.uc.bar_warn("Cell is not valid.")
            self.lyrs.clear_rubber()
            pass

        finally:
            QApplication.restoreOverrideCursor()

    def disconnect_signals(self):
        """
        Disconnect signals to avoid triggering save_conduits during attribute population.
        """
        self.name.editingFinished.disconnect(self.save_inlets_junctions)
        self.junction_invert_elev.editingFinished.disconnect(self.save_inlets_junctions)
        self.max_depth.editingFinished.disconnect(self.save_inlets_junctions)
        self.init_depth.editingFinished.disconnect(self.save_inlets_junctions)
        self.surcharge_depth.editingFinished.disconnect(self.save_inlets_junctions)
        self.intype.editingFinished.disconnect(self.save_inlets_junctions)
        self.swmm_length.editingFinished.disconnect(self.save_inlets_junctions)
        self.swmm_width.editingFinished.disconnect(self.save_inlets_junctions)
        self.swmm_height.editingFinished.disconnect(self.save_inlets_junctions)
        self.swmm_coeff.editingFinished.disconnect(self.save_inlets_junctions)
        self.swmm_feature.editingFinished.disconnect(self.save_inlets_junctions)
        self.curbheight.editingFinished.disconnect(self.save_inlets_junctions)
        self.swmm_clogging_factor.editingFinished.disconnect(self.save_inlets_junctions)
        self.swmm_time_for_clogging.editingFinished.disconnect(self.save_inlets_junctions)
        self.drboxarea.editingFinished.disconnect(self.save_inlets_junctions)
        self.sd_type.currentIndexChanged.disconnect(self.save_inlets_junctions)

    def connect_signals(self):
        """
        Reconnect signals after attribute population.
        """
        self.name.editingFinished.connect(self.save_inlets_junctions)
        self.junction_invert_elev.editingFinished.connect(self.save_inlets_junctions)
        self.max_depth.editingFinished.connect(self.save_inlets_junctions)
        self.init_depth.editingFinished.connect(self.save_inlets_junctions)
        self.surcharge_depth.editingFinished.connect(self.save_inlets_junctions)
        self.intype.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_length.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_width.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_height.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_coeff.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_feature.editingFinished.connect(self.save_inlets_junctions)
        self.curbheight.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_clogging_factor.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_time_for_clogging.editingFinished.connect(self.save_inlets_junctions)
        self.drboxarea.editingFinished.connect(self.save_inlets_junctions)
        self.sd_type.currentIndexChanged.connect(self.save_inlets_junctions)


uiDialog, qtBaseClass = load_ui("outlet_attributes")


class OutletAttributes(qtBaseClass, uiDialog):
    def __init__(self, con, iface, layers):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = layers
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = con
        self.gutils = GeoPackageUtils(con, iface)

        # Create a dock widget
        self.dock_widget = QgsDockWidget("Outfalls", self.iface.mainWindow())
        self.dock_widget.setObjectName("Outfalls")
        self.dock_widget.setWidget(self)

        self.current_node = None
        self.previous_node = None
        self.next_node = None

        # Connections
        self.name.editingFinished.connect(self.save_outlets)
        self.outfall_invert_elev.editingFinished.connect(self.save_outlets)
        self.fixed_stage.editingFinished.connect(self.save_outlets)

        self.user_swmm_outlets_lyr = self.lyrs.data["user_swmm_outlets"]["qlyr"]

        self.next_btn.clicked.connect(self.populate_next_node)
        self.previous_btn.clicked.connect(self.populate_previous_node)

        if self.flapgate.count() == 0:
            self.flapgate.addItem("NO")
            self.flapgate.addItem("YES")

        if self.swmm_allow_discharge.count() == 0:
            self.swmm_allow_discharge.addItem("0. Discharge off the grid")
            self.swmm_allow_discharge.addItem("1. Allow discharge to the grid")
            self.swmm_allow_discharge.addItem("2. Allow discharge to the grid but ignore the underground depth")

        if self.outfall_type.count() == 0:
            outfalls = ["FIXED", "FREE", "NORMAL", "TIDAL", "TIMESERIES"]
            self.outfall_type.addItems(outfalls)

        tidal_curves = self.gutils.execute("SELECT tidal_curve_name FROM swmm_tidal_curve;").fetchall()
        self.tidal_curve.addItem('*')
        if tidal_curves:
            for tidal_curve in tidal_curves:
                self.tidal_curve.addItem(tidal_curve[0])
            self.tidal_curve.setCurrentIndex(0)

        time_series = self.gutils.execute("SELECT time_series_name FROM swmm_time_series;").fetchall()
        self.time_series.addItem('*')
        if time_series:
            for time_serie in time_series:
                self.time_series.addItem(time_serie[0])
            self.time_series.setCurrentIndex(0)

        self.flapgate.currentIndexChanged.connect(self.save_flapgate)
        self.outfall_type.currentIndexChanged.connect(self.save_outlets)
        self.swmm_allow_discharge.currentIndexChanged.connect(self.save_allow_discharge)
        self.tidal_curve.currentIndexChanged.connect(self.save_tidal)
        self.time_series.currentIndexChanged.connect(self.save_ts)

        self.tidal_btn.clicked.connect(self.open_tidal_curve)
        self.ts_btn.clicked.connect(self.open_time_series)

        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)

        self.eye_btn.clicked.connect(self.find_outlet)

    def populate_attributes(self, fid):
        """
        Function to populate the attributes
        """
        if not fid:
            return

        self.clear_rubber()

        self.current_node = fid
        self.lyrs.show_feat_rubber(self.user_swmm_outlets_lyr.id(), fid, QColor(Qt.red))

        # Get the attributes
        attributes = self.gutils.execute(
            f"""SELECT 
                    grid,
                    name, 
                    outfall_invert_elev,
                    flapgate, 
                    fixed_stage, 
                    tidal_curve,
                    time_series,
                    outfall_type,
                    swmm_allow_discharge                              
                FROM
                    user_swmm_outlets
                WHERE
                    fid = {fid};"""
        ).fetchall()[0]

        self.disconnect_signals()

        # Assign attributes to the dialog
        self.grid.setText(str(attributes[0]))
        self.name.setText(str(attributes[1]))
        self.outfall_invert_elev.setValue(float(attributes[2]))
        if attributes[3] == 'False':
            self.flapgate.setCurrentIndex(0)
        else:
            self.flapgate.setCurrentIndex(1)
        fixed_stage = 0 if attributes[4] == "*" else float(attributes[4])
        self.fixed_stage.setValue(fixed_stage)
        self.tidal_curve.setCurrentText(attributes[5])
        self.time_series.setCurrentText(attributes[6])
        self.outfall_type.setCurrentText(str(attributes[7]))
        swmm_allow_discharge = attributes[8]
        if swmm_allow_discharge not in ["0", "1", "2"]:
            swmm_allow_discharge = "0"
        self.swmm_allow_discharge.setCurrentIndex(int(swmm_allow_discharge))

        self.connect_signals()

        if str(attributes[7]) == 'FIXED':
            self.fixed_stage_lbl.setHidden(False)
            self.fixed_stage.setHidden(False)
            self.tidal_curve_lbl.setHidden(True)
            self.tidal_curve.setHidden(True)
            self.tidal_btn.setHidden(True)
            self.time_series_lbl.setHidden(True)
            self.time_series.setHidden(True)
            self.ts_btn.setHidden(True)
            self.sd_features_grpbox.setHidden(True)

        if str(attributes[7]) == 'FREE':
            self.fixed_stage_lbl.setHidden(True)
            self.fixed_stage.setHidden(True)
            self.tidal_curve_lbl.setHidden(True)
            self.tidal_curve.setHidden(True)
            self.tidal_btn.setHidden(True)
            self.time_series_lbl.setHidden(True)
            self.time_series.setHidden(True)
            self.ts_btn.setHidden(True)
            self.sd_features_grpbox.setHidden(False)

        if str(attributes[7]) == 'NORMAL':
            self.fixed_stage_lbl.setHidden(True)
            self.fixed_stage.setHidden(True)
            self.tidal_curve_lbl.setHidden(True)
            self.tidal_curve.setHidden(True)
            self.tidal_btn.setHidden(True)
            self.time_series_lbl.setHidden(True)
            self.time_series.setHidden(True)
            self.ts_btn.setHidden(True)
            self.sd_features_grpbox.setHidden(True)

        if str(attributes[7]) == 'TIDAL':
            self.fixed_stage_lbl.setHidden(True)
            self.fixed_stage.setHidden(True)
            self.tidal_curve_lbl.setHidden(False)
            self.tidal_curve.setHidden(False)
            self.tidal_btn.setHidden(False)
            self.time_series_lbl.setHidden(True)
            self.time_series.setHidden(True)
            self.ts_btn.setHidden(True)
            self.sd_features_grpbox.setHidden(True)

        if str(attributes[7]) == 'TIMESERIES':
            self.fixed_stage_lbl.setHidden(True)
            self.fixed_stage.setHidden(True)
            self.tidal_curve_lbl.setHidden(True)
            self.tidal_curve.setHidden(True)
            self.tidal_btn.setHidden(True)
            self.time_series_lbl.setHidden(False)
            self.time_series.setHidden(False)
            self.ts_btn.setHidden(False)
            self.sd_features_grpbox.setHidden(True)

        self.previous_btn.setEnabled(False)
        self.next_btn.setEnabled(False)

        self.next_node = self.gutils.execute(
            f"""
            SELECT 
                conduit_inlet
            FROM 
                user_swmm_conduits
            WHERE 
                conduit_outlet = '{str(attributes[1])}' LIMIT 1;
            """
        ).fetchall()

        if self.next_node:
            self.next_btn.setEnabled(True)
            self.next_lbl.setText(self.next_node[0][0])

        self.previous_node = self.gutils.execute(
            f"""
            SELECT 
                conduit_outlet
            FROM 
                user_swmm_conduits
            WHERE 
                conduit_inlet = '{str(attributes[1])}' LIMIT 1;
            """
        ).fetchall()

        if self.previous_node:
            self.previous_btn.setEnabled(True)
            self.previous_lbl.setText(self.previous_node[0][0])

    def save_outlets(self):
        """
        Function to save the outlets everytime an attribute is changed
        """

        old_name_qry = self.gutils.execute(
            f"""SELECT name FROM user_swmm_outlets WHERE fid = '{self.current_node}';""").fetchall()
        old_name = ""
        if old_name_qry:
            old_name = old_name_qry[0][0]

        name = self.name.text()
        outfall_invert_elev = self.outfall_invert_elev.value()
        if self.flapgate.currentIndex() == 0:
            flapgate = 'False'
        else:
            flapgate = 'True'
        swmm_allow_discharge = self.swmm_allow_discharge.currentIndex()
        outfall_type = self.outfall_type.currentText()
        if self.tidal_curve.count() == 0:
            tidal_curve = '*'
        else:
            tidal_curve = self.tidal_curve.currentText()
        if self.time_series.count() == 0:
            time_series = '*'
        else:
            time_series = self.time_series.currentText()
        fixed_stage = self.fixed_stage.value()

        self.gutils.execute(f"""
                                UPDATE 
                                    user_swmm_outlets
                                SET 
                                    name = '{name}',
                                    outfall_invert_elev = '{outfall_invert_elev}',
                                    flapgate = '{flapgate}',
                                    swmm_allow_discharge = '{swmm_allow_discharge}',
                                    outfall_type = '{outfall_type}',
                                    tidal_curve = '{tidal_curve}',
                                    time_series = '{time_series}',
                                    fixed_stage = '{fixed_stage}'
                                WHERE 
                                    fid = '{self.current_node}';
                            """)

        self.user_swmm_outlets_lyr.triggerRepaint()

        # update the name on the user_swmm_conduits
        if old_name != name:
            # Updating Conduits
            update_conduits_inlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_conduits
                WHERE 
                    conduit_inlet = '{old_name}';
                """
            ).fetchall()
            if update_conduits_inlets_qry:
                for inlet in update_conduits_inlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_conduits
                        SET 
                            conduit_inlet = '{name}'
                        WHERE 
                            fid = '{inlet[0]}';
                    """)

            update_conduits_outlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_conduits
                WHERE 
                    conduit_outlet = '{old_name}';
                """
            ).fetchall()
            if update_conduits_outlets_qry:
                for outlet in update_conduits_outlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_conduits
                        SET 
                            conduit_outlet = '{name}'
                        WHERE 
                            fid = '{outlet[0]}';
                    """)

            # Updating Pumps
            update_pumps_inlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_pumps
                WHERE 
                    pump_inlet = '{old_name}';
                """
            ).fetchall()
            if update_pumps_inlets_qry:
                for inlet in update_pumps_inlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_pumps
                        SET 
                            pump_inlet = '{name}'
                        WHERE 
                            fid = '{inlet[0]}';
                    """)

            update_pumps_outlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_pumps
                WHERE 
                    pump_outlet = '{old_name}';
                """
            ).fetchall()
            if update_pumps_outlets_qry:
                for outlet in update_pumps_outlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_pumps
                        SET 
                            pump_outlet = '{name}'
                        WHERE 
                            fid = '{outlet[0]}';
                    """)

            # Updating Weirs
            update_weirs_inlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_weirs
                WHERE 
                    weir_inlet = '{old_name}';
                """
            ).fetchall()
            if update_weirs_inlets_qry:
                for inlet in update_weirs_inlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_weirs
                        SET 
                            weir_inlet = '{name}'
                        WHERE 
                            fid = '{inlet[0]}';
                    """)

            update_weirs_outlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_weirs
                WHERE 
                    weir_outlet = '{old_name}';
                """
            ).fetchall()
            if update_weirs_outlets_qry:
                for outlet in update_weirs_outlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_weirs
                        SET 
                            weir_outlet = '{name}'
                        WHERE 
                            fid = '{outlet[0]}';
                    """)

            # Updating Orifices
            update_orifices_inlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_orifices
                WHERE 
                    orifice_inlet = '{old_name}';
                """
            ).fetchall()
            if update_orifices_inlets_qry:
                for inlet in update_orifices_inlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_orifices
                        SET 
                            orifice_inlet = '{name}'
                        WHERE 
                            fid = '{inlet[0]}';
                    """)

            update_orifices_outlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_orifices
                WHERE 
                    orifice_outlet = '{old_name}';
                """
            ).fetchall()
            if update_orifices_outlets_qry:
                for outlet in update_orifices_outlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_orifices
                        SET 
                            orifice_outlet = '{name}'
                        WHERE 
                            fid = '{outlet[0]}';
                    """)

        self.populate_attributes(self.current_node)

    def save_flapgate(self):
        """
        Function to save only flapgate to avoid signal errors
        """
        if self.flapgate.currentIndex() == 0:
            flapgate = 'False'
        else:
            flapgate = 'True'

        self.gutils.execute(f"""
                                UPDATE
                                    user_swmm_outlets
                                SET
                                    flapgate = '{flapgate}'
                                WHERE
                                    fid = '{self.current_node}';
                            """)

    def save_tidal(self):
        """
        Function to save only tidal to avoid signal errors
        """
        tidal_curve = self.tidal_curve.currentText()
        if tidal_curve not in ['*', '']:
            self.time_series.setCurrentIndex(0)

        self.gutils.execute(f"""
                                UPDATE
                                    user_swmm_outlets
                                SET
                                    tidal_curve = '{tidal_curve}'
                                WHERE
                                    fid = '{self.current_node}';
                            """)

        self.save_outlets()

    def save_ts(self):
        """
        Function to save only time_series to avoid signal errors
        """
        time_series = self.time_series.currentText()
        if time_series not in ['*', '']:
            self.tidal_curve.setCurrentIndex(0)

        self.gutils.execute(f"""
                                UPDATE
                                    user_swmm_outlets
                                SET
                                    time_series = '{time_series}'
                                WHERE
                                    fid = '{self.current_node}';
                            """)

        self.save_outlets()

    def save_allow_discharge(self):
        """
        Function to save only time_series to avoid signal errors
        """
        allow_discharge = self.swmm_allow_discharge.currentIndex()

        self.gutils.execute(f"""
                                UPDATE
                                    user_swmm_outlets
                                SET
                                    swmm_allow_discharge = '{allow_discharge}'
                                WHERE
                                    fid = '{self.current_node}';
                            """)

    def dock_widget(self):
        """ Close and delete the dock widget. """
        if self.dock_widget:
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget.close()
            self.dock_widget.deleteLater()
            self.dock_widget = None

    def clear_rubber(self):
        """
        Function to clear the rubber when closing the widget
        """
        self.lyrs.clear_rubber()

    def populate_next_node(self):
        """
        Function to populate data when the user clicks on the next btn
        """
        next_node_name = self.next_lbl.text()

        fid = self.gutils.execute(
            f"""
            SELECT
                fid
            FROM
                user_swmm_inlets_junctions
            WHERE
                name = '{next_node_name}'
            """
        ).fetchone()

        if fid:
            self.populate_attributes(fid[0])

    def populate_previous_node(self):
        """
        Function to populate data when the user clicks on the previous btn
        """
        previous_node_name = self.previous_lbl.text()

        fid = self.gutils.execute(
            f"""
            SELECT
                fid
            FROM
                user_swmm_inlets_junctions
            WHERE
                name = '{previous_node_name}'
            """
        ).fetchone()

        if fid:
            self.populate_attributes(fid[0])

    def open_tidal_curve(self):
        tidal_curve_name = self.tidal_curve.currentText()
        dlg = OutfallTidalCurveDialog(self.iface, tidal_curve_name)
        while True:
            ok = dlg.exec_()
            if ok:
                if dlg.values_ok:
                    dlg.save_curve()
                    tidal_curve_name = dlg.get_curve_name()
                    if tidal_curve_name != "":
                        # Reload tidal curve list and select the one saved:
                        time_curve_names_sql = (
                            "SELECT DISTINCT tidal_curve_name FROM swmm_tidal_curve GROUP BY tidal_curve_name"
                        )
                        names = self.gutils.execute(time_curve_names_sql).fetchall()
                        if names:
                            self.tidal_curve.clear()
                            self.tidal_curve.addItem("*")
                            for name in names:
                                self.tidal_curve.addItem(name[0])

                            idx = self.tidal_curve.findText(tidal_curve_name)
                            self.tidal_curve.setCurrentIndex(idx)

                        break
                    else:
                        break
            else:
                break

    def open_time_series(self):
        time_series_name = self.time_series.currentText()
        dlg = OutfallTimeSeriesDialog(self.iface, time_series_name)
        while True:
            save = dlg.exec_()
            if save:
                if dlg.values_ok:
                    dlg.save_time_series()
                    time_series_name = dlg.get_name()
                    if time_series_name != "":
                        # Reload time series list and select the one saved:
                        time_series_names_sql = (
                            "SELECT DISTINCT time_series_name FROM swmm_time_series GROUP BY time_series_name"
                        )
                        names = self.gutils.execute(time_series_names_sql).fetchall()
                        if names:
                            self.time_series.clear()
                            self.time_series.addItem("*")
                            for name in names:
                                self.time_series.addItem(name[0])

                            idx = self.time_series.findText(time_series_name)
                            self.time_series.setCurrentIndex(idx)

                        break
                    else:
                        break
            else:
                break

    def zoom_in(self):
        """
        Function to zoom in
        """
        currentCell = next(self.user_swmm_outlets_lyr.getFeatures(QgsFeatureRequest(self.current_node)))
        if currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, 0.4)
            QApplication.restoreOverrideCursor()

    def zoom_out(self):
        """
        Function to zoom out
        """
        currentCell = next(self.user_swmm_outlets_lyr.getFeatures(QgsFeatureRequest(self.current_node)))
        if currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, -0.4)
            QApplication.restoreOverrideCursor()

    def find_outlet(self):
        """
        Function to find a junction and populate the data
        """
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                return

            name = self.search_le.text()
            grid_qry = self.gutils.execute(f"SELECT fid, grid FROM user_swmm_outlets WHERE name = '{name}'").fetchone()
            if grid_qry:
                self.current_node = grid_qry[0]
                cell = grid_qry[1]
            else:
                self.uc.bar_error("Outfall not found!")
                self.uc.log_info("Outfall not found!")
                return

            grid = self.lyrs.data["grid"]["qlyr"]
            if grid is not None:
                if grid:
                    self.lyrs.show_feat_rubber(self.user_swmm_outlets_lyr.id(), self.current_node, QColor(Qt.red))
                    feat = next(grid.getFeatures(QgsFeatureRequest(cell)))
                    x, y = feat.geometry().centroid().asPoint()
                    center_canvas(self.iface, x, y)
                    zoom(self.iface, 0.4)
                    self.populate_attributes(self.current_node)

        except Exception:
            self.uc.bar_warn("Cell is not valid.")
            self.lyrs.clear_rubber()
            pass

        finally:
            QApplication.restoreOverrideCursor()

    def disconnect_signals(self):
        """
        Disconnect signals to avoid triggering save_conduits during attribute population.
        """
        self.name.editingFinished.disconnect(self.save_outlets)
        self.outfall_invert_elev.editingFinished.disconnect(self.save_outlets)
        self.fixed_stage.editingFinished.disconnect(self.save_outlets)
        self.flapgate.currentIndexChanged.disconnect(self.save_flapgate)
        self.outfall_type.currentIndexChanged.disconnect(self.save_outlets)
        self.swmm_allow_discharge.currentIndexChanged.disconnect(self.save_allow_discharge)
        self.tidal_curve.currentIndexChanged.disconnect(self.save_tidal)
        self.time_series.currentIndexChanged.disconnect(self.save_ts)

    def connect_signals(self):
        """
        Reconnect signals after attribute population.
        """
        self.name.editingFinished.connect(self.save_outlets)
        self.outfall_invert_elev.editingFinished.connect(self.save_outlets)
        self.fixed_stage.editingFinished.connect(self.save_outlets)
        self.flapgate.currentIndexChanged.connect(self.save_flapgate)
        self.outfall_type.currentIndexChanged.connect(self.save_outlets)
        self.swmm_allow_discharge.currentIndexChanged.connect(self.save_allow_discharge)
        self.tidal_curve.currentIndexChanged.connect(self.save_tidal)
        self.time_series.currentIndexChanged.connect(self.save_ts)


uiDialog, qtBaseClass = load_ui("pump_attributes")


class PumpAttributes(qtBaseClass, uiDialog):
    def __init__(self, con, iface, layers):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = layers
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = con
        self.gutils = GeoPackageUtils(con, iface)

        # Create a dock widget
        self.dock_widget = QgsDockWidget("Pumps", self.iface.mainWindow())
        self.dock_widget.setObjectName("Pumps")
        self.dock_widget.setWidget(self)

        self.user_swmm_pumps_lyr = self.lyrs.data["user_swmm_pumps"]["qlyr"]
        self.user_swmm_inlets_junctions_lyr = self.lyrs.data["user_swmm_inlets_junctions"]["qlyr"]

        if self.pump_init_status.count() == 0:
            init_status = ["OFF", "ON"]
            self.pump_init_status.addItems(init_status)

        pump_curves = self.gutils.execute("SELECT DISTINCT pump_curve_name FROM swmm_pumps_curve_data;").fetchall()
        if pump_curves:
            for pump_curve in pump_curves:
                self.pump_curve.addItem(pump_curve[0])
            self.pump_curve.addItem('Ideal')
            self.pump_curve.setCurrentIndex(-1)

        self.pump_name.editingFinished.connect(self.save_pumps)
        self.pump_curve.currentIndexChanged.connect(self.save_pumps)
        self.pump_init_status.currentIndexChanged.connect(self.save_pumps)
        self.pump_startup_depth.editingFinished.connect(self.save_pumps)
        self.pump_shutoff_depth.editingFinished.connect(self.save_pumps)

        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)

        self.eye_btn.clicked.connect(self.find_pump)

    def populate_attributes(self, fid):
        """
        Function to populate the attributes
        """
        if not fid:
            return

        self.clear_rubber()

        self.current_node = fid
        self.lyrs.show_feat_rubber(self.user_swmm_pumps_lyr.id(), fid, QColor(Qt.red))

        # Get the attributes
        attributes = self.gutils.execute(
            f"""SELECT 
                    pump_name,
                    pump_inlet, 
                    pump_outlet,
                    pump_curve, 
                    pump_init_status, 
                    pump_startup_depth,
                    pump_shutoff_depth                      
                FROM
                    user_swmm_pumps
                WHERE
                    fid = {fid};"""
        ).fetchall()[0]

        self.disconnect_signals()

        self.pump_name.setText(attributes[0])
        self.pump_inlet.setText(attributes[1])
        self.pump_outlet.setText(attributes[2])
        if not attributes[3] or attributes[3] == '*':
            self.pump_curve.setCurrentText('Ideal')
        else:
            self.pump_curve.setCurrentText(attributes[3])
        self.pump_init_status.setCurrentText(attributes[4])
        self.pump_startup_depth.setValue(attributes[5])
        self.pump_shutoff_depth.setValue(attributes[6])

        self.connect_signals()

    def save_pumps(self):
        """
        Function to save the pumps everytime an attribute is changed
        """

        pump_name = self.pump_name.text()
        pump_inlet = self.pump_inlet.text()
        pump_outlet = self.pump_outlet.text()
        pump_curve = self.pump_curve.currentText()
        pump_init_status = self.pump_init_status.currentText()
        pump_startup_depth = self.pump_startup_depth.value()
        pump_shutoff_depth = self.pump_shutoff_depth.value()

        self.gutils.execute(f"""
                                UPDATE 
                                    user_swmm_pumps
                                SET 
                                    pump_name = '{pump_name}',
                                    pump_inlet = '{pump_inlet}',
                                    pump_outlet = '{pump_outlet}',
                                    pump_curve = '{pump_curve}',
                                    pump_init_status = '{pump_init_status}',
                                    pump_startup_depth = '{pump_startup_depth}',
                                    pump_shutoff_depth = '{pump_shutoff_depth}'                               
                                WHERE 
                                    fid = '{self.current_node}';
                            """)

        self.populate_attributes(self.current_node)
        self.user_swmm_pumps_lyr.triggerRepaint()

    def clear_rubber(self):
        """
        Function to clear the rubber when closing the widget
        """
        self.lyrs.clear_rubber()

    def zoom_in(self):
        """
        Function to zoom in
        """
        currentCell = next(self.user_swmm_pumps_lyr.getFeatures(QgsFeatureRequest(self.current_node)))
        if currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, 0.4)
            QApplication.restoreOverrideCursor()

    def zoom_out(self):
        """
        Function to zoom out
        """
        currentCell = next(self.user_swmm_pumps_lyr.getFeatures(QgsFeatureRequest(self.current_node)))
        if currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, -0.4)
            QApplication.restoreOverrideCursor()

    def find_pump(self):
        """
        Function to find a pump and populate the data
        """
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                return

            name = self.search_le.text()
            fid_qry = self.gutils.execute(f"SELECT fid FROM user_swmm_pumps WHERE pump_name = '{name}'").fetchone()
            if fid_qry:
                fid = fid_qry[0]
            else:
                self.uc.bar_error("Pump not found!")
                self.uc.log_info("Pump not found!")
                return

            self.lyrs.show_feat_rubber(self.user_swmm_pumps_lyr.id(), fid, QColor(Qt.red))
            feat = next(self.user_swmm_pumps_lyr.getFeatures(QgsFeatureRequest(fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, 0.4)
            self.populate_attributes(fid)

        except Exception:
            self.uc.bar_error("Error finding the pump.")
            self.uc.log_info("Error finding the pump.")
            self.lyrs.clear_rubber()
            pass

        finally:
            QApplication.restoreOverrideCursor()

    def disconnect_signals(self):
        """
        Disconnect signals to avoid triggering save_conduits during attribute population.
        """
        self.pump_name.editingFinished.disconnect(self.save_pumps)
        self.pump_curve.currentIndexChanged.disconnect(self.save_pumps)
        self.pump_init_status.currentIndexChanged.disconnect(self.save_pumps)
        self.pump_startup_depth.editingFinished.disconnect(self.save_pumps)
        self.pump_shutoff_depth.editingFinished.disconnect(self.save_pumps)

    def connect_signals(self):
        """
        Reconnect signals after attribute population.
        """
        self.pump_name.editingFinished.connect(self.save_pumps)
        self.pump_curve.currentIndexChanged.connect(self.save_pumps)
        self.pump_init_status.currentIndexChanged.connect(self.save_pumps)
        self.pump_startup_depth.editingFinished.connect(self.save_pumps)
        self.pump_shutoff_depth.editingFinished.connect(self.save_pumps)


uiDialog, qtBaseClass = load_ui("orifice_attributes")


class OrificeAttributes(qtBaseClass, uiDialog):
    def __init__(self, con, iface, layers):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = layers
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = con
        self.gutils = GeoPackageUtils(con, iface)

        # Create a dock widget
        self.dock_widget = QgsDockWidget("Orifices", self.iface.mainWindow())
        self.dock_widget.setObjectName("Orifices")
        self.dock_widget.setWidget(self)

        self.user_swmm_orifices_lyr = self.lyrs.data["user_swmm_orifices"]["qlyr"]
        self.user_swmm_inlets_junctions_lyr = self.lyrs.data["user_swmm_inlets_junctions"]["qlyr"]

        if self.orifice_type.count() == 0:
            init_status = ["SIDE", "BOTTOM"]
            self.orifice_type.addItems(init_status)

        if self.orifice_flap_gate.count() == 0:
            self.orifice_flap_gate.addItem("NO")
            self.orifice_flap_gate.addItem("YES")

        if self.orifice_shape.count() == 0:
            self.orifice_shape.addItem("CIRCULAR")
            self.orifice_shape.addItem("RECT_CLOSED")

        self.orifice_name.editingFinished.connect(self.save_orifices)
        self.orifice_type.currentIndexChanged.connect(self.save_orifices)
        self.orifice_flap_gate.currentIndexChanged.connect(self.save_orifices)
        self.orifice_shape.currentIndexChanged.connect(self.save_orifices)
        self.orifice_crest_height.editingFinished.connect(self.save_orifices)
        self.orifice_disch_coeff.editingFinished.connect(self.save_orifices)
        self.orifice_open_close_time.editingFinished.connect(self.save_orifices)
        self.orifice_height.editingFinished.connect(self.save_orifices)
        self.orifice_width.editingFinished.connect(self.save_orifices)

        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)

        self.eye_btn.clicked.connect(self.find_orifice)

    def populate_attributes(self, fid):
        """
        Function to populate the attributes
        """
        if not fid:
            return

        self.clear_rubber()

        self.current_node = fid
        self.lyrs.show_feat_rubber(self.user_swmm_orifices_lyr.id(), fid, QColor(Qt.red))

        # Get the attributes
        attributes = self.gutils.execute(
            f"""SELECT
                    orifice_name,
                    orifice_inlet,
                    orifice_outlet,
                    orifice_type,
                    orifice_crest_height,
                    orifice_disch_coeff,
                    orifice_flap_gate,
                    orifice_open_close_time,
                    orifice_shape,
                    orifice_height,
                    orifice_width
                FROM
                    user_swmm_orifices
                WHERE
                    fid = {fid};"""
        ).fetchall()[0]

        self.disconnect_signals()

        self.orifice_name.setText(attributes[0])
        self.orifice_inlet.setText(attributes[1])
        self.orifice_outlet.setText(attributes[2])
        self.orifice_type.setCurrentText(attributes[3])
        self.orifice_crest_height.setValue(attributes[4])
        self.orifice_disch_coeff.setValue(attributes[5])
        self.orifice_flap_gate.setCurrentText(attributes[6])
        self.orifice_open_close_time.setValue(attributes[7])
        self.orifice_shape.setCurrentText(attributes[8])
        self.orifice_height.setValue(attributes[9])
        self.orifice_width.setValue(attributes[10])

        self.connect_signals()

    def save_orifices(self):
        """
        Function to save the orifices everytime an attribute is changed
        """

        orifice_name = self.orifice_name.text()
        orifice_inlet = self.orifice_inlet.text()
        orifice_outlet = self.orifice_outlet.text()
        orifice_type = self.orifice_type.currentText()
        orifice_crest_height = self.orifice_crest_height.value()
        orifice_disch_coeff = self.orifice_disch_coeff.value()
        orifice_flap_gate = self.orifice_flap_gate.currentText()
        orifice_open_close_time = self.orifice_open_close_time.value()
        orifice_shape = self.orifice_shape.currentText()
        orifice_height = self.orifice_height.value()
        orifice_width = self.orifice_width.value()

        self.gutils.execute(f"""
                                UPDATE
                                    user_swmm_orifices
                                SET
                                    orifice_name = '{orifice_name}',
                                    orifice_inlet = '{orifice_inlet}',
                                    orifice_outlet = '{orifice_outlet}',
                                    orifice_type = '{orifice_type}',
                                    orifice_crest_height = '{orifice_crest_height}',
                                    orifice_disch_coeff = '{orifice_disch_coeff}',
                                    orifice_flap_gate = '{orifice_flap_gate}',
                                    orifice_open_close_time = '{orifice_open_close_time}',
                                    orifice_shape = '{orifice_shape}',
                                    orifice_height = '{orifice_height}',
                                    orifice_width = '{orifice_width}'
                                WHERE
                                    fid = '{self.current_node}';
                            """)

        self.populate_attributes(self.current_node)
        self.user_swmm_orifices_lyr.triggerRepaint()

    def clear_rubber(self):
        """
        Function to clear the rubber when closing the widget
        """
        self.lyrs.clear_rubber()

    def zoom_in(self):
        """
        Function to zoom in
        """
        currentCell = next(self.user_swmm_orifices_lyr.getFeatures(QgsFeatureRequest(self.current_node)))
        if currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, 0.4)
            QApplication.restoreOverrideCursor()

    def zoom_out(self):
        """
        Function to zoom out
        """
        currentCell = next(self.user_swmm_orifices_lyr.getFeatures(QgsFeatureRequest(self.current_node)))
        if currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, -0.4)
            QApplication.restoreOverrideCursor()

    def find_orifice(self):
        """
        Function to find an orifice and populate the data
        """
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                return

            name = self.search_le.text()
            fid_qry = self.gutils.execute(f"SELECT fid FROM user_swmm_orifices WHERE orifice_name = '{name}'").fetchone()
            if fid_qry:
                fid = fid_qry[0]
            else:
                self.uc.bar_error("Orifice not found!")
                self.uc.log_info("Orifice not found!")
                return

            self.lyrs.show_feat_rubber(self.user_swmm_orifices_lyr.id(), fid, QColor(Qt.red))
            feat = next(self.user_swmm_orifices_lyr.getFeatures(QgsFeatureRequest(fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, 0.4)
            self.populate_attributes(fid)

        except Exception:
            self.uc.bar_error("Error finding the orifice.")
            self.uc.log_info("Error finding the orifice.")
            self.lyrs.clear_rubber()
            pass

        finally:
            QApplication.restoreOverrideCursor()

    def disconnect_signals(self):
        """
        Disconnect signals to avoid triggering save_conduits during attribute population.
        """
        self.orifice_name.editingFinished.disconnect(self.save_orifices)
        self.orifice_type.currentIndexChanged.disconnect(self.save_orifices)
        self.orifice_flap_gate.currentIndexChanged.disconnect(self.save_orifices)
        self.orifice_shape.currentIndexChanged.disconnect(self.save_orifices)
        self.orifice_crest_height.editingFinished.disconnect(self.save_orifices)
        self.orifice_disch_coeff.editingFinished.disconnect(self.save_orifices)
        self.orifice_open_close_time.editingFinished.disconnect(self.save_orifices)
        self.orifice_height.editingFinished.disconnect(self.save_orifices)
        self.orifice_width.editingFinished.disconnect(self.save_orifices)

    def connect_signals(self):
        """
        Reconnect signals after attribute population.
        """
        self.orifice_name.editingFinished.connect(self.save_orifices)
        self.orifice_type.currentIndexChanged.connect(self.save_orifices)
        self.orifice_flap_gate.currentIndexChanged.connect(self.save_orifices)
        self.orifice_shape.currentIndexChanged.connect(self.save_orifices)
        self.orifice_crest_height.editingFinished.connect(self.save_orifices)
        self.orifice_disch_coeff.editingFinished.connect(self.save_orifices)
        self.orifice_open_close_time.editingFinished.connect(self.save_orifices)
        self.orifice_height.editingFinished.connect(self.save_orifices)
        self.orifice_width.editingFinished.connect(self.save_orifices)


uiDialog, qtBaseClass = load_ui("weir_attributes")


class WeirAttributes(qtBaseClass, uiDialog):
    def __init__(self, con, iface, layers):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = layers
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = con
        self.gutils = GeoPackageUtils(con, iface)

        # Create a dock widget
        self.dock_widget = QgsDockWidget("Weirs", self.iface.mainWindow())
        self.dock_widget.setObjectName("Weirs")
        self.dock_widget.setWidget(self)

        self.user_swmm_weirs_lyr = self.lyrs.data["user_swmm_weirs"]["qlyr"]
        self.user_swmm_inlets_junctions_lyr = self.lyrs.data["user_swmm_inlets_junctions"]["qlyr"]

        if self.weir_type.count() == 0:
            weir_type = ["TRANSVERSE", "SIDEFLOW", "V-NOTCH", "TRAPEZOIDAL"]
            self.weir_type.addItems(weir_type)

        if self.weir_flap_gate.count() == 0:
            self.weir_flap_gate.addItem("NO")
            self.weir_flap_gate.addItem("YES")

        if self.weir_shape.count() == 0:
            self.weir_shape.addItem("CIRCULAR")
            self.weir_shape.addItem("RECT_CLOSED")

        self.weir_name.editingFinished.connect(self.save_weirs)
        self.weir_type.currentIndexChanged.connect(self.save_weirs)
        self.weir_flap_gate.currentIndexChanged.connect(self.save_weirs)
        self.weir_crest_height.editingFinished.connect(self.save_weirs)
        self.weir_disch_coeff.editingFinished.connect(self.save_weirs)
        self.weir_end_contrac.editingFinished.connect(self.save_weirs)
        self.weir_end_coeff.editingFinished.connect(self.save_weirs)
        self.weir_shape.currentIndexChanged.connect(self.save_weirs)
        self.weir_height.editingFinished.connect(self.save_weirs)
        self.weir_length.editingFinished.connect(self.save_weirs)
        self.weir_side_slope.editingFinished.connect(self.save_weirs)

        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)

        self.eye_btn.clicked.connect(self.find_weir)

    def populate_attributes(self, fid):
        """
        Function to populate the attributes
        """
        if not fid:
            return

        self.clear_rubber()

        self.current_node = fid
        self.lyrs.show_feat_rubber(self.user_swmm_weirs_lyr.id(), fid, QColor(Qt.red))

        # Get the attributes
        attributes = self.gutils.execute(
            f"""SELECT
                    weir_name,
                    weir_inlet,
                    weir_outlet,
                    weir_type,
                    weir_crest_height,
                    weir_disch_coeff,
                    weir_flap_gate,
                    weir_end_contrac,
                    weir_end_coeff,
                    weir_height,
                    weir_length,
                    weir_side_slope
                FROM
                    user_swmm_weirs
                WHERE
                    fid = {fid};"""
        ).fetchall()[0]

        self.disconnect_signals()

        self.weir_name.setText(attributes[0])
        self.weir_inlet.setText(attributes[1])
        self.weir_outlet.setText(attributes[2])
        self.weir_type.setCurrentText(attributes[3])
        self.weir_crest_height.setValue(attributes[4])
        self.weir_disch_coeff.setValue(attributes[5])
        self.weir_flap_gate.setCurrentText(attributes[6])
        self.weir_end_contrac.setValue(int(attributes[7]))
        self.weir_end_coeff.setValue(attributes[8])
        self.weir_height.setValue(attributes[9])
        self.weir_length.setValue(attributes[10])
        self.weir_side_slope.setValue(attributes[11])

        self.connect_signals()

    def save_weirs(self):
        """
        Function to save the weirs everytime an attribute is changed
        """

        weir_name = self.weir_name.text()
        weir_inlet = self.weir_inlet.text()
        weir_outlet = self.weir_outlet.text()
        weir_type = self.weir_type.currentText()
        weir_crest_height = self.weir_crest_height.value()
        weir_disch_coeff = self.weir_disch_coeff.value()
        weir_flap_gate = self.weir_flap_gate.currentText()
        weir_end_contrac = self.weir_end_contrac.value()
        weir_end_coeff = self.weir_end_coeff.value()
        weir_shape = self.weir_shape.currentText()
        weir_height = self.weir_height.value()
        weir_length = self.weir_length.value()
        weir_side_slope = self.weir_side_slope.value()

        self.gutils.execute(f"""
                                UPDATE
                                    user_swmm_weirs
                                SET
                                    weir_name = '{weir_name}',
                                    weir_inlet = '{weir_inlet}',
                                    weir_outlet = '{weir_outlet}',
                                    weir_type = '{weir_type}',
                                    weir_crest_height = '{weir_crest_height}',
                                    weir_disch_coeff = '{weir_disch_coeff}',
                                    weir_flap_gate = '{weir_flap_gate}',
                                    weir_end_contrac = '{weir_end_contrac}',
                                    weir_end_coeff = '{weir_end_coeff}',
                                    weir_shape = '{weir_shape}',
                                    weir_height = '{weir_height}',
                                    weir_length = '{weir_length}',
                                    weir_side_slope = '{weir_side_slope}'
                                WHERE
                                    fid = '{self.current_node}';
                            """)

        self.populate_attributes(self.current_node)
        self.user_swmm_weirs_lyr.triggerRepaint()

    def clear_rubber(self):
        """
        Function to clear the rubber when closing the widget
        """
        self.lyrs.clear_rubber()

    def zoom_in(self):
        """
        Function to zoom in
        """
        currentCell = next(self.user_swmm_weirs_lyr.getFeatures(QgsFeatureRequest(self.current_node)))
        if currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, 0.4)
            QApplication.restoreOverrideCursor()

    def zoom_out(self):
        """
        Function to zoom out
        """
        currentCell = next(self.user_swmm_weirs_lyr.getFeatures(QgsFeatureRequest(self.current_node)))
        if currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, -0.4)
            QApplication.restoreOverrideCursor()

    def find_weir(self):
        """
        Function to find a weir and populate the data
        """
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                return

            name = self.search_le.text()
            fid_qry = self.gutils.execute(f"SELECT fid FROM user_swmm_weirs WHERE weir_name = '{name}'").fetchone()
            if fid_qry:
                fid = fid_qry[0]
            else:
                self.uc.bar_error("Weir not found!")
                self.uc.log_info("Weir not found!")
                return

            self.lyrs.show_feat_rubber(self.user_swmm_weirs_lyr.id(), fid, QColor(Qt.red))
            feat = next(self.user_swmm_weirs_lyr.getFeatures(QgsFeatureRequest(fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, 0.4)
            self.populate_attributes(fid)

        except Exception:
            self.uc.bar_error("Error finding the weir.")
            self.uc.log_info("Error finding the weir.")
            self.lyrs.clear_rubber()
            pass

        finally:
            QApplication.restoreOverrideCursor()

    def disconnect_signals(self):
        """
        Disconnect signals to avoid triggering save_conduits during attribute population.
        """
        self.weir_name.editingFinished.disconnect(self.save_weirs)
        self.weir_type.currentIndexChanged.disconnect(self.save_weirs)
        self.weir_flap_gate.currentIndexChanged.disconnect(self.save_weirs)
        self.weir_crest_height.editingFinished.disconnect(self.save_weirs)
        self.weir_disch_coeff.editingFinished.disconnect(self.save_weirs)
        self.weir_end_contrac.editingFinished.disconnect(self.save_weirs)
        self.weir_end_coeff.editingFinished.disconnect(self.save_weirs)
        self.weir_shape.currentIndexChanged.disconnect(self.save_weirs)
        self.weir_height.editingFinished.disconnect(self.save_weirs)
        self.weir_length.editingFinished.disconnect(self.save_weirs)
        self.weir_side_slope.editingFinished.disconnect(self.save_weirs)

    def connect_signals(self):
        """
        Reconnect signals after attribute population.
        """
        self.weir_name.editingFinished.connect(self.save_weirs)
        self.weir_type.currentIndexChanged.connect(self.save_weirs)
        self.weir_flap_gate.currentIndexChanged.connect(self.save_weirs)
        self.weir_crest_height.editingFinished.connect(self.save_weirs)
        self.weir_disch_coeff.editingFinished.connect(self.save_weirs)
        self.weir_end_contrac.editingFinished.connect(self.save_weirs)
        self.weir_end_coeff.editingFinished.connect(self.save_weirs)
        self.weir_shape.currentIndexChanged.connect(self.save_weirs)
        self.weir_height.editingFinished.connect(self.save_weirs)
        self.weir_length.editingFinished.connect(self.save_weirs)
        self.weir_side_slope.editingFinished.connect(self.save_weirs)


uiDialog, qtBaseClass = load_ui("conduit_attributes")


class ConduitAttributes(qtBaseClass, uiDialog):
    def __init__(self, con, iface, layers):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)

        self.iface = iface
        self.lyrs = layers
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = con
        self.gutils = GeoPackageUtils(con, iface)

        # Create a dock widget
        self.dock_widget = QgsDockWidget("Conduits", self.iface.mainWindow())
        self.dock_widget.setObjectName("Conduits")
        self.dock_widget.setWidget(self)

        self.user_swmm_conduits_lyr = self.lyrs.data["user_swmm_conduits"]["qlyr"]
        self.user_swmm_inlets_junctions_lyr = self.lyrs.data["user_swmm_inlets_junctions"]["qlyr"]

        if self.losses_flapgate.count() == 0:
            self.losses_flapgate.addItem("True")
            self.losses_flapgate.addItem("False")

        if self.xsections_shape.count() == 0:
            xsections = [
                "CIRCULAR",
                "FORCE_MAIN",
                "FILLED_CIRCULAR",
                "RECT_CLOSED",
                "RECT_OPEN",
                "TRAPEZOIDAL",
                "TRIANGULAR",
                "HORIZ_ELLIPSE",
                "VERT_ELLIPSE",
                "ARCH",
                "PARABOLIC",
                "POWER",
                "RECT_TRIANGULAR",
                "RECT_ROUND",
                "MODBASKETHANDLE",
                "EGG",
                "HORSESHOE",
                "GOTHIC",
                "CATENARY",
                "SEMIELLIPTICAL",
                "BASKETHANDLE",
                "SEMICIRCULAR"
            ]
            self.xsections_shape.addItems(xsections)

        self.conduit_name.editingFinished.connect(self.save_conduits)
        self.conduit_length.editingFinished.connect(self.save_conduits)
        self.conduit_manning.editingFinished.connect(self.save_conduits)
        self.conduit_inlet_offset.editingFinished.connect(self.save_conduits)
        self.conduit_outlet_offset.editingFinished.connect(self.save_conduits)
        self.conduit_init_flow.editingFinished.connect(self.save_conduits)
        self.conduit_max_flow.editingFinished.connect(self.save_conduits)
        self.losses_inlet.editingFinished.connect(self.save_conduits)
        self.losses_outlet.editingFinished.connect(self.save_conduits)
        self.losses_average.editingFinished.connect(self.save_conduits)
        self.losses_flapgate.currentIndexChanged.connect(self.save_conduits)
        self.xsections_shape.currentIndexChanged.connect(self.save_conduits)
        self.xsections_max_depth.editingFinished.connect(self.save_conduits)
        self.xsections_geom2.editingFinished.connect(self.save_conduits)
        self.xsections_geom3.editingFinished.connect(self.save_conduits)
        self.xsections_geom4.editingFinished.connect(self.save_conduits)
        self.xsections_barrels.editingFinished.connect(self.save_conduits)

        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)

        self.eye_btn.clicked.connect(self.find_conduit)

    def populate_attributes(self, fid):
        """
        Function to populate the attributes
        """
        if not fid:
            return

        self.clear_rubber()

        self.current_node = fid
        self.lyrs.show_feat_rubber(self.user_swmm_conduits_lyr.id(), fid, QColor(Qt.red))

        # Get the attributes
        attributes = self.gutils.execute(
            f"""SELECT 
                    conduit_name,
                    conduit_inlet, 
                    conduit_outlet,
                    conduit_length, 
                    conduit_manning, 
                    conduit_inlet_offset,
                    conduit_outlet_offset,
                    conduit_init_flow,
                    conduit_max_flow,
                    losses_inlet, 
                    losses_outlet, 
                    losses_average, 
                    losses_flapgate, 
                    xsections_shape,
                    xsections_max_depth,
                    xsections_geom2, 
                    xsections_geom3,
                    xsections_geom4,
                    xsections_barrels                          
                FROM
                    user_swmm_conduits
                WHERE
                    fid = {fid};"""
        ).fetchall()[0]

        self.disconnect_signals()

        self.conduit_name.setText(str(attributes[0]))
        self.conduit_inlet.setText(str(attributes[1]))
        self.conduit_outlet.setText(str(attributes[2]))
        self.conduit_length.setValue(attributes[3])
        self.conduit_manning.setValue(attributes[4])
        self.conduit_inlet_offset.setValue(attributes[5])
        self.conduit_outlet_offset.setValue(attributes[6])
        self.conduit_init_flow.setValue(attributes[7])
        self.conduit_max_flow.setValue(attributes[8])
        self.losses_inlet.setValue(attributes[9])
        self.losses_outlet.setValue(attributes[10])
        self.losses_average.setValue(attributes[11])
        if attributes[12] == 'False':
            self.losses_flapgate.setCurrentIndex(1)
        else:
            self.losses_flapgate.setCurrentIndex(0)
        self.xsections_shape.setCurrentText(attributes[13])
        self.xsections_max_depth.setValue(attributes[14])
        self.xsections_geom2.setValue(attributes[15])
        self.xsections_geom3.setValue(attributes[16])
        self.xsections_geom4.setValue(attributes[17])
        self.xsections_barrels.setValue(attributes[18])

        self.connect_signals()

    def save_conduits(self):
        """
        Function to save the conduits everytime an attribute is changed
        """

        conduit_name = self.conduit_name.text()
        conduit_length = self.conduit_length.value()
        conduit_manning = self.conduit_manning.value()
        conduit_inlet_offset = self.conduit_inlet_offset.value()
        conduit_outlet_offset = self.conduit_outlet_offset.value()
        conduit_init_flow = self.conduit_init_flow.value()
        conduit_max_flow = self.conduit_max_flow.value()
        losses_inlet = self.losses_inlet.value()
        losses_outlet = self.losses_outlet.value()
        losses_average = self.losses_average.value()
        losses_flapgate = self.losses_flapgate.currentText()
        xsections_shape = self.xsections_shape.currentText()
        xsections_max_depth = self.xsections_max_depth.value()
        xsections_geom2 = self.xsections_geom2.value()
        xsections_geom3 = self.xsections_geom3.value()
        xsections_geom4 = self.xsections_geom4.value()
        xsections_barrels = self.xsections_barrels.value()

        self.gutils.execute(f"""
                                UPDATE 
                                    user_swmm_conduits
                                SET 
                                    conduit_name = '{conduit_name}',
                                    conduit_length = '{conduit_length}',
                                    conduit_manning = '{conduit_manning}',
                                    conduit_inlet_offset = '{conduit_inlet_offset}',
                                    conduit_outlet_offset = '{conduit_outlet_offset}',
                                    conduit_init_flow = '{conduit_init_flow}',
                                    conduit_max_flow = '{conduit_max_flow}',
                                    losses_inlet = '{losses_inlet}',
                                    losses_outlet = '{losses_outlet}',
                                    losses_average = '{losses_average}',
                                    losses_flapgate = '{losses_flapgate}',
                                    xsections_shape = '{xsections_shape}',
                                    xsections_max_depth = '{xsections_max_depth}',
                                    xsections_geom2 = '{xsections_geom2}',
                                    xsections_geom3 = '{xsections_geom3}',
                                    xsections_geom4 = '{xsections_geom4}',
                                    xsections_barrels = '{xsections_barrels}'                                    
                                WHERE 
                                    fid = '{self.current_node}';
                            """)

        self.populate_attributes(self.current_node)
        self.user_swmm_conduits_lyr.triggerRepaint()

    def clear_rubber(self):
        """
        Function to clear the rubber when closing the widget
        """
        self.lyrs.clear_rubber()

    def zoom_in(self):
        """
        Function to zoom in
        """
        currentCell = next(self.user_swmm_conduits_lyr.getFeatures(QgsFeatureRequest(self.current_node)))
        if currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, 0.4)
            QApplication.restoreOverrideCursor()

    def zoom_out(self):
        """
        Function to zoom out
        """
        currentCell = next(self.user_swmm_conduits_lyr.getFeatures(QgsFeatureRequest(self.current_node)))
        if currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, -0.4)
            QApplication.restoreOverrideCursor()

    def find_conduit(self):
        """
        Function to find a conduit and populate the data
        """
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                return

            name = self.search_le.text()
            fid_qry = self.gutils.execute(f"SELECT fid FROM user_swmm_conduits WHERE conduit_name = '{name}'").fetchone()
            if fid_qry:
                fid = fid_qry[0]
            else:
                self.uc.bar_error("Conduit not found!")
                self.uc.log_info("Conduit not found!")
                return

            self.lyrs.show_feat_rubber(self.user_swmm_conduits_lyr.id(), fid, QColor(Qt.red))
            feat = next(self.user_swmm_conduits_lyr.getFeatures(QgsFeatureRequest(fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, 0.4)
            self.populate_attributes(fid)

        except Exception:
            self.uc.bar_error("Error finding the conduit.")
            self.uc.log_info("Error finding the conduit.")
            self.lyrs.clear_rubber()
            pass

        finally:
            QApplication.restoreOverrideCursor()

    def disconnect_signals(self):
        """
        Disconnect signals to avoid triggering save_conduits during attribute population.
        """
        self.conduit_name.editingFinished.disconnect(self.save_conduits)
        self.conduit_length.editingFinished.disconnect(self.save_conduits)
        self.conduit_manning.editingFinished.disconnect(self.save_conduits)
        self.conduit_inlet_offset.editingFinished.disconnect(self.save_conduits)
        self.conduit_outlet_offset.editingFinished.disconnect(self.save_conduits)
        self.conduit_init_flow.editingFinished.disconnect(self.save_conduits)
        self.conduit_max_flow.editingFinished.disconnect(self.save_conduits)
        self.losses_inlet.editingFinished.disconnect(self.save_conduits)
        self.losses_outlet.editingFinished.disconnect(self.save_conduits)
        self.losses_average.editingFinished.disconnect(self.save_conduits)
        self.losses_flapgate.currentIndexChanged.disconnect(self.save_conduits)
        self.xsections_shape.currentIndexChanged.disconnect(self.save_conduits)
        self.xsections_max_depth.editingFinished.disconnect(self.save_conduits)
        self.xsections_geom2.editingFinished.disconnect(self.save_conduits)
        self.xsections_geom3.editingFinished.disconnect(self.save_conduits)
        self.xsections_geom4.editingFinished.disconnect(self.save_conduits)
        self.xsections_barrels.editingFinished.disconnect(self.save_conduits)

    def connect_signals(self):
        """
        Reconnect signals after attribute population.
        """
        self.conduit_name.editingFinished.connect(self.save_conduits)
        self.conduit_length.editingFinished.connect(self.save_conduits)
        self.conduit_manning.editingFinished.connect(self.save_conduits)
        self.conduit_inlet_offset.editingFinished.connect(self.save_conduits)
        self.conduit_outlet_offset.editingFinished.connect(self.save_conduits)
        self.conduit_init_flow.editingFinished.connect(self.save_conduits)
        self.conduit_max_flow.editingFinished.connect(self.save_conduits)
        self.losses_inlet.editingFinished.connect(self.save_conduits)
        self.losses_outlet.editingFinished.connect(self.save_conduits)
        self.losses_average.editingFinished.connect(self.save_conduits)
        self.losses_flapgate.currentIndexChanged.connect(self.save_conduits)
        self.xsections_shape.currentIndexChanged.connect(self.save_conduits)
        self.xsections_max_depth.editingFinished.connect(self.save_conduits)
        self.xsections_geom2.editingFinished.connect(self.save_conduits)
        self.xsections_geom3.editingFinished.connect(self.save_conduits)
        self.xsections_geom4.editingFinished.connect(self.save_conduits)
        self.xsections_barrels.editingFinished.connect(self.save_conduits)


uiDialog, qtBaseClass = load_ui("storage_unit_attributes")


class StorageUnitAttributes(qtBaseClass, uiDialog):
    def __init__(self, con, iface, layers):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = layers
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = con
        self.gutils = GeoPackageUtils(con, iface)

        # Create a dock widget
        self.dock_widget = QgsDockWidget("Storage Units", self.iface.mainWindow())
        self.dock_widget.setObjectName("Storage Units")
        self.dock_widget.setWidget(self)

        if self.external_inflow.count() == 0:
            self.external_inflow.addItem("NO")
            self.external_inflow.addItem("YES")

        if self.treatment.count() == 0:
            self.treatment.addItem("NO")
            self.treatment.addItem("YES")

        if self.infil_method.count() == 0:
            self.infil_method.addItem("GREEN_AMPT")

        tabular_curves = self.gutils.execute("SELECT DISTINCT name FROM swmm_other_curves;").fetchall()
        self.curve_name.addItem('*')
        if tabular_curves:
            for tabular_curve in tabular_curves:
                self.curve_name.addItem(tabular_curve[0])
            self.curve_name.setCurrentIndex(0)

        # Connections
        self.name.editingFinished.connect(self.save_storage_units)
        self.max_depth.editingFinished.connect(self.save_storage_units)
        self.init_depth.editingFinished.connect(self.save_storage_units)
        self.invert_elev.editingFinished.connect(self.save_storage_units)
        self.external_inflow.currentIndexChanged.connect(self.save_storage_units)
        self.treatment.currentIndexChanged.connect(self.save_storage_units)
        self.evap_factor.editingFinished.connect(self.save_storage_units)
        self.infiltration_grpbox.toggled.connect(self.save_storage_units)
        self.infil_method.currentIndexChanged.connect(self.save_storage_units)
        self.suction_head.editingFinished.connect(self.save_storage_units)
        self.conductivity.editingFinished.connect(self.save_storage_units)
        self.initial_deficit.editingFinished.connect(self.save_storage_units)
        self.functional_grpbox.toggled.connect(self.check_functional)
        self.coefficient.editingFinished.connect(self.save_storage_units)
        self.exponent.editingFinished.connect(self.save_storage_units)
        self.constant.editingFinished.connect(self.save_storage_units)
        self.tabular_grpbox.toggled.connect(self.check_tabular)
        self.curve_name.currentIndexChanged.connect(self.save_storage_units)

        self.external_btn.clicked.connect(self.show_external_inflow_dlg)
        self.external_inflow.currentIndexChanged.connect(self.external_inflow_btn_chk)

        self.tabular_curve_btn.clicked.connect(self.open_tabular_curve)

        self.user_swmm_storage_units_lyr = self.lyrs.data["user_swmm_storage_units"]["qlyr"]

        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)

        self.eye_btn.clicked.connect(self.find_storage_unit)

    def populate_attributes(self, fid):
        """
        Function to populate the attributes
        """

        if not fid:
            return

        self.clear_rubber()

        self.current_node = fid
        self.lyrs.show_feat_rubber(self.user_swmm_storage_units_lyr.id(), fid, QColor(Qt.red))

        # Get the attributes
        attributes = self.gutils.execute(
            f"""SELECT
                    grid,
                    name,
                    max_depth,
                    init_depth,
                    invert_elev,
                    external_inflow,
                    treatment,
                    evap_factor,
                    infiltration,
                    infil_method,
                    suction_head,
                    conductivity,
                    initial_deficit,
                    storage_curve,
                    coefficient,
                    exponent,
                    constant,
                    curve_name
                FROM
                    user_swmm_storage_units
                WHERE
                    fid = {fid};"""
        ).fetchall()[0]

        self.disconnect_signals()

        # Assign attributes to the dialog
        self.grid.setText(str(attributes[0]))
        self.name.setText(str(attributes[1]))
        self.max_depth.setValue(attributes[2])
        self.init_depth.setValue(attributes[3])
        self.invert_elev.setValue(attributes[4])
        self.external_inflow.setCurrentText(attributes[5])
        self.treatment.setCurrentText(attributes[6])
        self.evap_factor.setValue(attributes[7])
        self.infiltration_grpbox.setChecked(True) if attributes[8] == 'True' else self.infiltration_grpbox.setChecked(False)
        self.infil_method.setCurrentText(attributes[9])
        self.suction_head.setValue(attributes[10])
        self.conductivity.setValue(attributes[11])
        self.initial_deficit.setValue(attributes[12])
        if attributes[13] == 'TABULAR':
            self.tabular_grpbox.setChecked(True)
            self.functional_grpbox.setChecked(False)
        else:
            self.tabular_grpbox.setChecked(False)
            self.functional_grpbox.setChecked(True)
        self.coefficient.setValue(attributes[14])
        self.exponent.setValue(attributes[15])
        self.constant.setValue(attributes[16])

        if attributes[17]:
            self.curve_name.setCurrentText(attributes[17])

        self.connect_signals()

    def save_storage_units(self):
        """
        Function to save the storage units everytime an attribute is changed
        """

        old_name_qry = self.gutils.execute(
            f"""SELECT name FROM user_swmm_storage_units WHERE fid = '{self.current_node}';""").fetchall()
        old_name = ""
        if old_name_qry:
            old_name = old_name_qry[0][0]

        name = self.name.text()
        max_depth = self.max_depth.value()
        init_depth = self.init_depth.value()
        invert_elev = self.invert_elev.value()
        external_inflow = self.external_inflow.currentText()
        treatment = self.treatment.currentText()
        evap_factor = self.evap_factor.value()
        infiltration = self.infiltration_grpbox.isChecked()
        infil_method = self.infil_method.currentText()
        suction_head = self.suction_head.value()
        conductivity = self.conductivity.value()
        initial_deficit = self.initial_deficit.value()

        storage_curve = ''
        if self.functional_grpbox.isChecked():
            storage_curve = 'FUNCTIONAL'
        if self.tabular_grpbox.isChecked():
            storage_curve = 'TABULAR'

        coefficient = self.coefficient.value()
        exponent = self.exponent.value()
        constant = self.constant.value()
        curve_name = self.curve_name.currentText()

        self.gutils.execute(f"""
                                UPDATE
                                    user_swmm_storage_units
                                SET
                                    name = '{name}',
                                    max_depth = '{max_depth}',
                                    init_depth = '{init_depth}',
                                    invert_elev = '{invert_elev}',
                                    external_inflow = '{external_inflow}',
                                    treatment = '{treatment}',
                                    evap_factor = '{evap_factor}',
                                    infiltration = '{infiltration}',
                                    infil_method = '{infil_method}',
                                    suction_head = '{suction_head}',
                                    conductivity = '{conductivity}',
                                    initial_deficit = '{initial_deficit}',
                                    storage_curve = '{storage_curve}',
                                    coefficient = '{coefficient}',
                                    exponent = '{exponent}',
                                    constant = '{constant}',
                                    curve_name = '{curve_name}'
                                WHERE
                                    fid = '{self.current_node}';
                            """)

        self.user_swmm_storage_units_lyr.triggerRepaint()

        # update the name on the user_swmm_conduits
        if old_name != name:
            # Updating Conduits
            update_conduits_inlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_conduits
                WHERE 
                    conduit_inlet = '{old_name}';
                """
            ).fetchall()
            if update_conduits_inlets_qry:
                for inlet in update_conduits_inlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_conduits
                        SET 
                            conduit_inlet = '{name}'
                        WHERE 
                            fid = '{inlet[0]}';
                    """)

            update_conduits_outlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_conduits
                WHERE 
                    conduit_outlet = '{old_name}';
                """
            ).fetchall()
            if update_conduits_outlets_qry:
                for outlet in update_conduits_outlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_conduits
                        SET 
                            conduit_outlet = '{name}'
                        WHERE 
                            fid = '{outlet[0]}';
                    """)

            # Updating Pumps
            update_pumps_inlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_pumps
                WHERE 
                    pump_inlet = '{old_name}';
                """
            ).fetchall()
            if update_pumps_inlets_qry:
                for inlet in update_pumps_inlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_pumps
                        SET 
                            pump_inlet = '{name}'
                        WHERE 
                            fid = '{inlet[0]}';
                    """)

            update_pumps_outlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_pumps
                WHERE 
                    pump_outlet = '{old_name}';
                """
            ).fetchall()
            if update_pumps_outlets_qry:
                for outlet in update_pumps_outlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_pumps
                        SET 
                            pump_outlet = '{name}'
                        WHERE 
                            fid = '{outlet[0]}';
                    """)

            # Updating Weirs
            update_weirs_inlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_weirs
                WHERE 
                    weir_inlet = '{old_name}';
                """
            ).fetchall()
            if update_weirs_inlets_qry:
                for inlet in update_weirs_inlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_weirs
                        SET 
                            weir_inlet = '{name}'
                        WHERE 
                            fid = '{inlet[0]}';
                    """)

            update_weirs_outlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_weirs
                WHERE 
                    weir_outlet = '{old_name}';
                """
            ).fetchall()
            if update_weirs_outlets_qry:
                for outlet in update_weirs_outlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_weirs
                        SET 
                            weir_outlet = '{name}'
                        WHERE 
                            fid = '{outlet[0]}';
                    """)

            # Updating Orifices
            update_orifices_inlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_orifices
                WHERE 
                    orifice_inlet = '{old_name}';
                """
            ).fetchall()
            if update_orifices_inlets_qry:
                for inlet in update_orifices_inlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_orifices
                        SET 
                            orifice_inlet = '{name}'
                        WHERE 
                            fid = '{inlet[0]}';
                    """)

            update_orifices_outlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_orifices
                WHERE 
                    orifice_outlet = '{old_name}';
                """
            ).fetchall()
            if update_orifices_outlets_qry:
                for outlet in update_orifices_outlets_qry:
                    self.gutils.execute(f"""
                        UPDATE 
                            user_swmm_orifices
                        SET 
                            orifice_outlet = '{name}'
                        WHERE 
                            fid = '{outlet[0]}';
                    """)

        self.populate_attributes(self.current_node)

    def show_external_inflow_dlg(self):
        """
        Function to show the external inflow in the Storage Units
        """
        name = self.name.text()
        if name == "":
            return

        dlg_external_inflow = ExternalInflowsDialog(self.iface, name)
        dlg_external_inflow.setWindowTitle("Storage Units " + name)
        save = dlg_external_inflow.exec_()
        if save:
            inflow_sql = "SELECT baseline, pattern_name, time_series_name FROM swmm_inflows WHERE node_name = ?;"
            inflow = self.gutils.execute(inflow_sql, (name,)).fetchone()
            if inflow:
                baseline = inflow[0]
                pattern_name = inflow[1]
                time_series_name = inflow[2]
                if baseline == 0.0 and time_series_name == "":
                    self.external_inflow.setCurrentIndex(0)
                else:
                    self.external_inflow.setCurrentIndex(1)

            self.uc.bar_info("Storm Drain external inflow saved for storage unit " + name)
            self.uc.log_info("Storm Drain external inflow saved for storage unit " + name)

    def external_inflow_btn_chk(self):
        """
        Function to enable/disable the external inflow btn
        """
        external_inflow = self.external_inflow.currentText()

        if external_inflow == 'YES':
            self.external_btn.setEnabled(True)
            external_inflow_bool = 1
        else:
            self.external_btn.setEnabled(False)
            external_inflow_bool = 0

        self.gutils.execute(f"""
                                UPDATE 
                                    user_swmm_storage_units
                                SET 
                                    external_inflow = '{external_inflow_bool}'
                                WHERE 
                                    fid = '{self.current_node}';
                            """)

    def dock_widget(self):
        """ Close and delete the dock widget. """
        if self.dock_widget:
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget.close()
            self.dock_widget.deleteLater()
            self.dock_widget = None

    def clear_rubber(self):
        """
        Function to clear the rubber when closing the widget
        """
        self.lyrs.clear_rubber()

    def check_tabular(self, checked):
        """
        Function to check the tabular group box
        """
        if checked:
            self.functional_grpbox.setChecked(False)

        self.save_storage_units()

    def check_functional(self, checked):
        """
        Function to check the functional group box
        """
        if checked:
            self.tabular_grpbox.setChecked(False)

        self.save_storage_units()

    def open_tabular_curve(self):
        tabular_curve_name = self.curve_name.currentText()
        dlg = StorageUnitTabularCurveDialog(self.iface, tabular_curve_name)
        while True:
            ok = dlg.exec_()
            if ok:
                if dlg.values_ok:
                    dlg.save_curve()
                    tabular_curve_name = dlg.get_curve_name()
                    if tabular_curve_name != "" or tabular_curve_name != "*":
                        # Reload tabular curve list and select the one saved:
                        curves_sql = (
                            "SELECT DISTINCT name FROM swmm_other_curves WHERE type = 'Storage' GROUP BY name"
                        )
                        names = self.gutils.execute(curves_sql).fetchall()
                        if names:
                            self.curve_name.clear()
                            for name in names:
                                self.curve_name.addItem(name[0])
                            self.curve_name.addItem("*")

                            idx = self.curve_name.findText(tabular_curve_name)
                            self.curve_name.setCurrentIndex(idx)
                        break
                    else:
                        break
            else:
                break

    def zoom_in(self):
        """
        Function to zoom in
        """
        currentCell = next(self.user_swmm_storage_units_lyr.getFeatures(QgsFeatureRequest(self.current_node)))
        if currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, 0.4)
            QApplication.restoreOverrideCursor()

    def zoom_out(self):
        """
        Function to zoom out
        """
        currentCell = next(self.user_swmm_storage_units_lyr.getFeatures(QgsFeatureRequest(self.current_node)))
        if currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, -0.4)
            QApplication.restoreOverrideCursor()

    def find_storage_unit(self):
        """
        Function to find a storage unit and populate the data
        """
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                return

            name = self.search_le.text()
            grid_qry = self.gutils.execute(f"SELECT fid, grid FROM user_swmm_storage_units WHERE name = '{name}'").fetchone()
            if grid_qry:
                self.current_node = grid_qry[0]
                cell = grid_qry[1]
            else:
                self.uc.bar_error("Storage Unit not found!")
                self.uc.log_info("Storage Unit not found!")
                return

            grid = self.lyrs.data["grid"]["qlyr"]
            if grid is not None:
                if grid:
                    self.lyrs.show_feat_rubber(self.user_swmm_storage_units_lyr.id(), self.current_node, QColor(Qt.red))
                    feat = next(grid.getFeatures(QgsFeatureRequest(cell)))
                    x, y = feat.geometry().centroid().asPoint()
                    center_canvas(self.iface, x, y)
                    zoom(self.iface, 0.4)
                    self.populate_attributes(self.current_node)

        except Exception:
            self.uc.bar_warn("Cell is not valid.")
            self.lyrs.clear_rubber()
            pass

        finally:
            QApplication.restoreOverrideCursor()

    def disconnect_signals(self):
        """
        Disconnect signals to avoid triggering save_conduits during attribute population.
        """
        self.name.editingFinished.disconnect(self.save_storage_units)
        self.max_depth.editingFinished.disconnect(self.save_storage_units)
        self.init_depth.editingFinished.disconnect(self.save_storage_units)
        self.invert_elev.editingFinished.disconnect(self.save_storage_units)
        self.external_inflow.currentIndexChanged.disconnect(self.save_storage_units)
        self.treatment.currentIndexChanged.disconnect(self.save_storage_units)
        self.evap_factor.editingFinished.disconnect(self.save_storage_units)
        self.infiltration_grpbox.toggled.disconnect(self.save_storage_units)
        self.infil_method.currentIndexChanged.disconnect(self.save_storage_units)
        self.suction_head.editingFinished.disconnect(self.save_storage_units)
        self.conductivity.editingFinished.disconnect(self.save_storage_units)
        self.initial_deficit.editingFinished.disconnect(self.save_storage_units)
        self.functional_grpbox.toggled.disconnect(self.check_functional)
        self.coefficient.editingFinished.disconnect(self.save_storage_units)
        self.exponent.editingFinished.disconnect(self.save_storage_units)
        self.constant.editingFinished.disconnect(self.save_storage_units)
        self.tabular_grpbox.toggled.disconnect(self.check_tabular)
        self.curve_name.currentIndexChanged.disconnect(self.save_storage_units)

    def connect_signals(self):
        """
        Reconnect signals after attribute population.
        """
        self.name.editingFinished.connect(self.save_storage_units)
        self.max_depth.editingFinished.connect(self.save_storage_units)
        self.init_depth.editingFinished.connect(self.save_storage_units)
        self.invert_elev.editingFinished.connect(self.save_storage_units)
        self.external_inflow.currentIndexChanged.connect(self.save_storage_units)
        self.treatment.currentIndexChanged.connect(self.save_storage_units)
        self.evap_factor.editingFinished.connect(self.save_storage_units)
        self.infiltration_grpbox.toggled.connect(self.save_storage_units)
        self.infil_method.currentIndexChanged.connect(self.save_storage_units)
        self.suction_head.editingFinished.connect(self.save_storage_units)
        self.conductivity.editingFinished.connect(self.save_storage_units)
        self.initial_deficit.editingFinished.connect(self.save_storage_units)
        self.functional_grpbox.toggled.connect(self.check_functional)
        self.coefficient.editingFinished.connect(self.save_storage_units)
        self.exponent.editingFinished.connect(self.save_storage_units)
        self.constant.editingFinished.connect(self.save_storage_units)
        self.tabular_grpbox.toggled.connect(self.check_tabular)
        self.curve_name.currentIndexChanged.connect(self.save_storage_units)


uiDialog, qtBaseClass = load_ui("storm_drain_external_inflows")


class ExternalInflowsDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, node):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.node = node
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None

        self.swmm_select_pattern_btn.clicked.connect(self.select_inflow_pattern)
        self.swmm_select_time_series_btn.clicked.connect(self.select_time_series)
        self.external_inflows_buttonBox.accepted.connect(self.save_external_inflow_variables)
        self.swmm_inflow_baseline_le.setValidator(QDoubleValidator(0, 100, 2))

        self.setup_connection()
        self.populate_external_inflows()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_external_inflows(self):
        baseline_names_sql = "SELECT DISTINCT pattern_name FROM swmm_inflow_patterns GROUP BY pattern_name"
        names = self.gutils.execute(baseline_names_sql).fetchall()
        if names:
            for name in names:
                self.swmm_inflow_pattern_cbo.addItem(name[0].strip())
        self.swmm_inflow_pattern_cbo.addItem("")

        time_names_sql = "SELECT DISTINCT time_series_name FROM swmm_time_series GROUP BY time_series_name"
        names = self.gutils.execute(time_names_sql).fetchall()
        if names:
            for name in names:
                self.swmm_time_series_cbo.addItem(name[0].strip())
        self.swmm_time_series_cbo.addItem("")

        inflow_sql = "SELECT constituent, baseline, pattern_name, time_series_name, scale_factor FROM swmm_inflows WHERE node_name = ?;"
        inflow = self.gutils.execute(inflow_sql, (self.node,)).fetchone()
        if inflow:
            baseline = inflow[1]
            pattern_name = inflow[2]
            time_series_name = inflow[3]
            scale_factor = inflow[4]
            self.swmm_inflow_baseline_le.setText(str(baseline))
            if pattern_name != "" and pattern_name is not None:
                idx = self.swmm_inflow_pattern_cbo.findText(pattern_name.strip())
                if idx == -1:
                    self.uc.bar_warn(
                        '"' + pattern_name + '"' + " baseline pattern is not of HOURLY type!",
                        5,
                    )
                    self.swmm_inflow_pattern_cbo.setCurrentIndex(self.swmm_inflow_pattern_cbo.count() - 1)
                else:
                    self.swmm_inflow_pattern_cbo.setCurrentIndex(idx)
            else:
                self.swmm_inflow_pattern_cbo.setCurrentIndex(self.swmm_inflow_pattern_cbo.count() - 1)

            if time_series_name == '""':
                time_series_name = ""

            idx = self.swmm_time_series_cbo.findText(time_series_name)
            if idx == -1:
                time_series_name = ""
                idx = self.swmm_time_series_cbo.findText(time_series_name)
            self.swmm_time_series_cbo.setCurrentIndex(idx)

            self.swmm_inflow_scale_factor_dbox.setValue(scale_factor)

    def select_inflow_pattern(self):
        pattern_name = self.swmm_inflow_pattern_cbo.currentText()
        dlg_inflow_pattern = InflowPatternDialog(self.iface, pattern_name)
        save = dlg_inflow_pattern.exec_()

        pattern_name = dlg_inflow_pattern.get_name()
        if pattern_name != "":
            # Reload baseline list and select the one saved:

            baseline_names_sql = "SELECT DISTINCT pattern_name FROM swmm_inflow_patterns GROUP BY pattern_name"
            names = self.gutils.execute(baseline_names_sql).fetchall()
            if names:
                self.swmm_inflow_pattern_cbo.clear()
                for name in names:
                    self.swmm_inflow_pattern_cbo.addItem(name[0])
                self.swmm_inflow_pattern_cbo.addItem("")

                idx = self.swmm_inflow_pattern_cbo.findText(pattern_name)
                self.swmm_inflow_pattern_cbo.setCurrentIndex(idx)

    def select_time_series(self):
        time_series_name = self.swmm_time_series_cbo.currentText()
        dlg = InflowTimeSeriesDialog(self.iface, time_series_name)
        while True:
            save = dlg.exec_()
            if save:
                if dlg.values_ok:
                    dlg.save_time_series()
                    time_series_name = dlg.get_name()
                    if time_series_name != "":
                        # Reload time series list and select the one saved:
                        time_series_names_sql = (
                            "SELECT DISTINCT time_series_name FROM swmm_time_series GROUP BY time_series_name"
                        )
                        names = self.gutils.execute(time_series_names_sql).fetchall()
                        if names:
                            self.swmm_time_series_cbo.clear()
                            for name in names:
                                self.swmm_time_series_cbo.addItem(name[0])
                            self.swmm_time_series_cbo.addItem("")

                            idx = self.swmm_time_series_cbo.findText(time_series_name)
                            self.swmm_time_series_cbo.setCurrentIndex(idx)

                        # self.uc.bar_info("Storm Drain external time series saved for inlet " + "?????")
                        break
                    else:
                        break
            else:
                break

    def save_external_inflow_variables(self):
        """
        Save changes to external inflows variables.
        """

        baseline = float(self.swmm_inflow_baseline_le.text()) if self.swmm_inflow_baseline_le.text() != "" else 0.0
        pattern = self.swmm_inflow_pattern_cbo.currentText()
        file = self.swmm_time_series_cbo.currentText()
        scale = self.swmm_inflow_scale_factor_dbox.value()

        exists_sql = "SELECT fid FROM swmm_inflows WHERE node_name = ?;"
        exists = self.gutils.execute(exists_sql, (self.node,)).fetchone()
        if exists:
            update_sql = """UPDATE swmm_inflows
                        SET
                            constituent = ?,
                            baseline = ?, 
                            pattern_name = ?, 
                            time_series_name = ?,
                            scale_factor = ?
                        WHERE
                            node_name = ?;"""

            self.gutils.execute(update_sql, ("FLOW", baseline, pattern, file, scale, self.node))
        else:
            insert_sql = """INSERT INTO swmm_inflows 
                            (   node_name, 
                                constituent, 
                                baseline, 
                                pattern_name, 
                                time_series_name, 
                                scale_factor
                            ) 
                            VALUES (?,?,?,?,?,?); """
            self.gutils.execute(insert_sql, (self.node, "FLOW", baseline, pattern, file, scale))


uiDialog, qtBaseClass = load_ui("storm_drain_inflow_time_series")


class InflowTimeSeriesDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, time_series_name):
        qtBaseClass.__init__(self)

        uiDialog.__init__(self)
        self.iface = iface
        self.time_series_name = time_series_name
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None

        self.values_ok = False
        self.loading = True
        set_icon(self.add_time_data_btn, "add.svg")
        set_icon(self.delete_time_data_btn, "remove.svg")

        self.setup_connection()

        delegate = TimeSeriesDelegate(self.inflow_time_series_tblw)
        self.inflow_time_series_tblw.setItemDelegate(delegate)

        self.time_series_buttonBox.accepted.connect(self.is_ok_to_save)
        self.select_time_series_btn.clicked.connect(self.select_time_series_file)
        self.inflow_time_series_tblw.itemChanged.connect(self.ts_tblw_changed)
        self.add_time_data_btn.clicked.connect(self.add_time)
        self.delete_time_data_btn.clicked.connect(self.delete_time)
        self.copy_btn.clicked.connect(self.copy_selection)
        self.paste_btn.clicked.connect(self.paste)
        self.clear_btn.clicked.connect(self.clear)

        self.populate_time_series_dialog()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_time_series_dialog(self):
        self.loading = True
        if self.time_series_name == "":
            self.use_table_radio.setChecked(True)
            self.add_time()
            pass
        else:
            series_sql = "SELECT * FROM swmm_time_series WHERE time_series_name = ?"
            row = self.gutils.execute(series_sql, (self.time_series_name,)).fetchone()
            if row:
                self.name_le.setText(row[1])
                self.description_le.setText(row[2])
                self.file_le.setText(row[3])
                external = True if is_true(row[4]) else False

                if external:
                    self.use_table_radio.setChecked(True)
                    self.external_radio.setChecked(False)
                else:
                    self.external_radio.setChecked(True)
                    self.use_table_radio.setChecked(False)

                data_qry = """SELECT
                                date, 
                                time, 
                                value
                        FROM swmm_time_series_data WHERE time_series_name = ?;"""
                rows = self.gutils.execute(data_qry, (self.time_series_name,)).fetchall()
                if rows:
                    self.inflow_time_series_tblw.setRowCount(0)
                    for row_number, row_data in enumerate(rows):
                        self.inflow_time_series_tblw.insertRow(row_number)
                        for col, data in enumerate(row_data):
                            if col == 0:
                                if data:
                                    try:
                                        a, b, c = data.split("/")
                                        if len(a) < 2:
                                            a = "0" * (2 - len(a)) + a
                                        if len(b) < 2:
                                            b = "0" * (2 - len(b)) + b
                                        if len(c) < 4:
                                            c = "0" * (4 - len(c)) + c
                                        data = a + "/" + b + "/" + c
                                    except:
                                        data = ""
                                else:
                                    data = ""
                            if col == 1:
                                if data:
                                    try:
                                        a, b = data.split(":")
                                        if len(a) == 1:
                                            a = "0" + a
                                        data = a + ":" + b
                                    except:
                                        data = "00:00"
                                else:
                                    data = "00:00"
                            if col == 2:
                                data = str(data)
                            item = QTableWidgetItem()
                            item.setData(Qt.DisplayRole, data)
                            self.inflow_time_series_tblw.setItem(row_number, col, item)

                    self.inflow_time_series_tblw.sortItems(0, Qt.AscendingOrder)
            else:
                self.name_le.setText(self.time_series_name)
                self.external_radio.setChecked(True)
                self.use_table_radio.setChecked(False)

        QApplication.restoreOverrideCursor()
        self.loading = False

    def select_time_series_file(self):
        self.uc.clear_bar_messages()

        s = QSettings()
        last_dir = s.value("FLO-2D/lastSWMMDir", "")
        time_series_file, __ = QFileDialog.getOpenFileName(None, "Select time series data file", directory=last_dir)
        if not time_series_file:
            return
        s.setValue("FLO-2D/lastSWMMDir", os.path.dirname(time_series_file))
        self.file_le.setText(os.path.normpath(time_series_file))

        # For future use
        try:
            pass
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 140220.0807: reading time series data file failed!", e)
            return

    def is_ok_to_save(self):
        if self.name_le.text() == "":
            self.uc.bar_warn("Time Series name required!", 2)
            self.time_series_name = ""
            self.values_ok = False

        elif " " in self.name_le.text():
            self.uc.bar_warn("Spaces not allowed in Time Series name!", 2)
            self.time_series_name = ""
            self.values_ok = False

        elif self.description_le.text() == "":
            self.uc.bar_warn("Time Series description required!", 2)
            self.values_ok = False

        elif self.use_table_radio.isChecked() and self.inflow_time_series_tblw.rowCount() == 0:
            self.uc.bar_warn("Time Series table can't be empty!", 2)
            self.values_ok = False

        elif self.external_radio.isChecked() and self.file_le.text() == "":
            self.uc.bar_warn("Data file name required!", 2)
            self.values_ok = False
        else:
            self.values_ok = True

    def save_time_series(self):
        delete_sql = "DELETE FROM swmm_time_series WHERE time_series_name = ?"
        self.gutils.execute(delete_sql, (self.name_le.text(),))
        insert_sql = "INSERT INTO swmm_time_series (time_series_name, time_series_description, time_series_file, time_series_data) VALUES (?, ?, ?, ?);"
        self.gutils.execute(
            insert_sql,
            (
                self.name_le.text(),
                self.description_le.text(),
                self.file_le.text(),
                "True" if self.use_table_radio.isChecked() else "False",
            ),
        )

        delete_data_sql = "DELETE FROM swmm_time_series_data WHERE time_series_name = ?"
        self.gutils.execute(delete_data_sql, (self.name_le.text(),))

        insert_data_sql = [
            """INSERT INTO swmm_time_series_data (time_series_name, date, time, value) VALUES""",
            4,
        ]
        for row in range(0, self.inflow_time_series_tblw.rowCount()):
            date = self.inflow_time_series_tblw.item(row, 0)
            if date:
                date = date.text()

            time = self.inflow_time_series_tblw.item(row, 1)
            if time:
                time = time.text()

            value = self.inflow_time_series_tblw.item(row, 2)
            if value:
                value = value.text()

            insert_data_sql += [(self.name_le.text(), date, time, value)]
        self.gutils.batch_execute(insert_data_sql)

        self.uc.bar_info("Inflow time series " + self.name_le.text() + " saved.", 2)
        self.uc.log_info("Inflow time series " + self.name_le.text() + " saved.")
        self.time_series_name = self.name_le.text()
        self.close()

    def get_name(self):
        return self.time_series_name

    def inflow_time_series_tblw_clicked(self):
        self.uc.show_info("Clicked")

    def time_series_model_changed(self, i, j):
        self.uc.show_info("Changed")

    def ts_tblw_changed(self, Qitem):

        if not self.loading:
            column = Qitem.column()
            text = Qitem.text()

            if column == 0:  # First column (Date)
                if "/" in text:
                    a, b, c = text.split("/")
                    if len(a) < 2:
                        a = "0" * (2 - len(a)) + a
                    if len(b) < 2:
                        b = "0" * (2 - len(b)) + b
                    if len(c) < 4:
                        c = "0" * (4 - len(c)) + c
                    text = a + "/" + b + "/" + c

            elif column == 1:  # Second column (Time)
                if text == "":
                    text = "00:00"
                if ":" in text:
                    a, b = text.split(":")
                    if len(a) == 1:
                        a = "0" + a
                    text = a + ":" + b

            elif column == 2:  # Third column (value)
                if text == "":
                    text = "0.0"

            Qitem.setText(text)

    def add_time(self):
        self.inflow_time_series_tblw.insertRow(self.inflow_time_series_tblw.rowCount())
        row_number = self.inflow_time_series_tblw.rowCount() - 1

        item = QTableWidgetItem()

        # Code for current date
        # d = QDate.currentDate()
        # d = str(d.month()) + "/" + str(d.day()) + "/" + str(d.year())
        # item.setData(Qt.DisplayRole, d)

        # Code for empty item
        item.setData(Qt.DisplayRole, "")

        self.inflow_time_series_tblw.setItem(row_number, 0, item)

        item = QTableWidgetItem()

        # Code for current time
        # t = QTime.currentTime()
        # t = str(t.hour()) + ":" + str(t.minute())
        # item.setData(Qt.DisplayRole, t)

        # Code for starting time equal 00:00
        t = "00:00"
        item.setData(Qt.DisplayRole, t)
        self.inflow_time_series_tblw.setItem(row_number, 1, item)

        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, "0.0")
        self.inflow_time_series_tblw.setItem(row_number, 2, item)

        self.inflow_time_series_tblw.selectRow(row_number)
        self.inflow_time_series_tblw.setFocus()

    def delete_time(self):
        self.inflow_time_series_tblw.removeRow(self.inflow_time_series_tblw.currentRow())
        self.inflow_time_series_tblw.selectRow(0)
        self.inflow_time_series_tblw.setFocus()

    def copy_selection(self):
        selection = self.inflow_time_series_tblw.selectedIndexes()
        if selection:
            rows = sorted(index.row() for index in selection)
            columns = sorted(index.column() for index in selection)
            rowcount = rows[-1] - rows[0] + 1
            colcount = columns[-1] - columns[0] + 1
            table = [[""] * colcount for _ in range(rowcount)]
            for index in selection:
                row = index.row() - rows[0]
                column = index.column() - columns[0]
                table[row][column] = str(index.data())
            stream = io.StringIO()
            csv.writer(stream, delimiter="\t").writerows(table)
            QApplication.clipboard().setText(stream.getvalue())

    def paste(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)

        # Get the clipboard text
        clipboard_text = QApplication.clipboard().text()
        if not clipboard_text:
            QApplication.restoreOverrideCursor()
            return

        # Split clipboard data into rows and columns
        rows = clipboard_text.split("\n")
        if rows[-1] == '':  # Remove the extra empty line at the end if present
            rows = rows[:-1]
        num_rows = len(rows)
        if num_rows == 0:
            QApplication.restoreOverrideCursor()
            return

        # Get the top-left selected cell
        selection = self.inflow_time_series_tblw.selectionModel().selection()
        if not selection:
            QApplication.restoreOverrideCursor()
            return

        top_left_idx = selection[0].topLeft()
        sel_row = top_left_idx.row()
        sel_col = top_left_idx.column()

        # Insert rows if necessary
        if sel_row + num_rows > self.inflow_time_series_tblw.rowCount():
            self.inflow_time_series_tblw.setRowCount(sel_row + num_rows)

        # Insert columns if necessary (adjust table columns if paste exceeds current column count)
        num_cols = rows[0].count("\t") + 1
        if sel_col + num_cols > self.inflow_time_series_tblw.columnCount():
            self.inflow_time_series_tblw.setColumnCount(sel_col + num_cols)

        # Paste data into the table
        for row_idx, row in enumerate(rows):
            columns = row.split("\t")
            for col_idx, col in enumerate(columns):
                item = QTableWidgetItem(col.strip())
                self.inflow_time_series_tblw.setItem(sel_row + row_idx, sel_col + col_idx, item)

        QApplication.restoreOverrideCursor()

    def clear(self):
        self.inflow_time_series_tblw.setRowCount(0)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy_selection()
        elif event.matches(QKeySequence.Paste):
            self.paste()
        else:
            super().keyPressEvent(event)


uiDialog, qtBaseClass = load_ui("storm_drain_inflow_pattern")


class InflowPatternDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, pattern_name):
        qtBaseClass.__init__(self)

        uiDialog.__init__(self)
        self.iface = iface
        self.pattern_name = pattern_name
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None

        self.multipliers_tblw.undoStack = QUndoStack(self)

        self.setup_connection()

        self.pattern_buttonBox.accepted.connect(self.save_pattern)

        self.populate_pattern_dialog()

        self.copy_btn.clicked.connect(self.copy_selection)
        self.paste_btn.clicked.connect(self.paste)
        self.delete_btn.clicked.connect(self.delete)

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_pattern_dialog(self):
        if self.pattern_name == "":
            SIMUL = 24
            self.multipliers_tblw.setRowCount(SIMUL)
            for i in range(SIMUL):
                itm = QTableWidgetItem()
                itm.setData(Qt.EditRole, "1.0")
                self.multipliers_tblw.setItem(i, 0, itm)
        else:
            select_sql = "SELECT * FROM swmm_inflow_patterns WHERE pattern_name = ?"
            rows = self.gutils.execute(select_sql, (self.pattern_name,)).fetchall()
            if rows:
                for i, row in enumerate(rows):
                    self.name_le.setText(row[1])
                    self.description_le.setText(row[2])
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, row[4])
                    self.multipliers_tblw.setItem(i, 0, itm)
            else:
                self.name_le.setText(self.pattern_name)
                SIMUL = 24
                self.multipliers_tblw.setRowCount(SIMUL)
                for i in range(SIMUL):
                    itm = QTableWidgetItem()
                    itm.setData(Qt.EditRole, "1.0")
                    self.multipliers_tblw.setItem(i, 0, itm)

    def save_pattern(self):
        if self.name_le.text() == "":
            self.uc.bar_warn("Pattern name required!", 2)
            self.pattern_name = ""
        elif self.description_le.text() == "":
            self.uc.bar_warn("Pattern description required!", 2)
            self.pattern_name = ""
        else:
            delete_sql = "DELETE FROM swmm_inflow_patterns WHERE pattern_name = ?"
            self.gutils.execute(delete_sql, (self.name_le.text(),))
            insert_sql = "INSERT INTO swmm_inflow_patterns (pattern_name, pattern_description, hour, multiplier) VALUES (?, ?, ? ,?);"
            for i in range(1, 25):
                if self.multipliers_tblw.item(i - 1, 0):
                    item = self.multipliers_tblw.item(i - 1, 0).text()
                else:
                    item = 1
                self.gutils.execute(
                    insert_sql,
                    (
                        self.name_le.text(),
                        self.description_le.text(),
                        str(i),
                        item,
                    ),
                )

            self.uc.bar_info("Inflow Pattern " + self.name_le.text() + " saved.", 2)
            self.uc.log_info("Inflow Pattern " + self.name_le.text() + " saved.")
            self.pattern_name = self.name_le.text()
            self.close()

    def get_name(self):
        return self.pattern_name

    def copy_selection(self):
        selection = self.multipliers_tblw.selectedIndexes()
        if selection:
            rows = sorted(index.row() for index in selection)
            columns = sorted(index.column() for index in selection)
            rowcount = rows[-1] - rows[0] + 1
            colcount = columns[-1] - columns[0] + 1
            table = [[""] * colcount for _ in range(rowcount)]
            for index in selection:
                row = index.row() - rows[0]
                column = index.column() - columns[0]
                table[row][column] = str(index.data())

            stream = io.StringIO()
            csv.writer(stream, delimiter='\t').writerows(table)
            clipboard_text = stream.getvalue()
            clipboard_text = clipboard_text.replace("\t", "\n")  # To fix the tabulation issue
            QApplication.clipboard().setText(clipboard_text)

    def paste(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)

        # Get the clipboard text
        clipboard_text = QApplication.clipboard().text()
        if not clipboard_text:
            QApplication.restoreOverrideCursor()
            return

        # Split clipboard data into rows and columns
        rows = clipboard_text.split("\n")
        if rows[-1] == '':  # Remove the extra empty line at the end if present
            rows = rows[:-1]
        num_rows = len(rows)
        if num_rows == 0:
            QApplication.restoreOverrideCursor()
            return

        # Get the top-left selected cell
        selection = self.multipliers_tblw.selectionModel().selection()
        if not selection:
            QApplication.restoreOverrideCursor()
            return

        top_left_idx = selection[0].topLeft()
        sel_row = top_left_idx.row()
        sel_col = top_left_idx.column()

        # Insert rows if necessary
        if sel_row + num_rows > self.multipliers_tblw.rowCount():
            self.multipliers_tblw.setRowCount(sel_row + num_rows)

        # Insert columns if necessary (adjust table columns if paste exceeds current column count)
        num_cols = rows[0].count("\t") + 1
        if sel_col + num_cols > self.multipliers_tblw.columnCount():
            self.multipliers_tblw.setColumnCount(sel_col + num_cols)

        # Paste data into the table
        for row_idx, row in enumerate(rows):
            columns = row.split("\t")
            for col_idx, col in enumerate(columns):
                item = QTableWidgetItem(col.strip())
                self.multipliers_tblw.setItem(sel_row + row_idx, sel_col + col_idx, item)

        QApplication.restoreOverrideCursor()

    def delete(self):
        selected_rows = []
        table_widget = self.multipliers_tblw

        # Get selected row indices
        for item in table_widget.selectedItems():
            if item.row() not in selected_rows:
                selected_rows.append(item.row())

        # Sort selected row indices in descending order to avoid issues with row removal
        selected_rows.sort(reverse=True)

        # Remove selected rows
        for row in selected_rows:
            table_widget.removeRow(row)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy_selection()
        elif event.matches(QKeySequence.Paste):
            self.paste()
        else:
            super().keyPressEvent(event)


uiDialog, qtBaseClass = load_ui("storm_drain_outfall_time_series")


class OutfallTimeSeriesDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, time_series_name):
        qtBaseClass.__init__(self)

        uiDialog.__init__(self)
        self.iface = iface
        self.time_series_name = time_series_name
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None

        self.values_ok = False
        self.loading = True
        set_icon(self.add_time_data_btn, "add.svg")
        set_icon(self.delete_time_data_btn, "remove.svg")

        self.setup_connection()

        delegate = TimeSeriesDelegate(self.outfall_time_series_tblw)
        self.outfall_time_series_tblw.setItemDelegate(delegate)

        self.time_series_buttonBox.accepted.connect(self.is_ok_to_save)
        self.select_time_series_btn.clicked.connect(self.select_time_series_file)
        self.outfall_time_series_tblw.itemChanged.connect(self.ts_tblw_changed)
        self.add_time_data_btn.clicked.connect(self.add_time)
        self.delete_time_data_btn.clicked.connect(self.delete_time)
        self.copy_btn.clicked.connect(self.copy_selection)
        self.paste_btn.clicked.connect(self.paste)
        self.clear_btn.clicked.connect(self.clear)

        self.populate_time_series_dialog()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_time_series_dialog(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.loading = True
        if self.time_series_name == "":
            self.use_table_radio.setChecked(True)
            self.add_time()
            pass
        else:
            series_sql = "SELECT * FROM swmm_time_series WHERE time_series_name = ?;"
            row = self.gutils.execute(series_sql, (self.time_series_name,)).fetchone()
            if row:
                self.name_le.setText(row[1])
                self.description_le.setText(row[2])
                self.file_le.setText(row[3])
                external = True if is_true(row[4]) else False

                if external:
                    self.use_table_radio.setChecked(True)
                    self.external_radio.setChecked(False)
                else:
                    self.external_radio.setChecked(True)
                    self.use_table_radio.setChecked(False)

                data_qry = """SELECT
                                date, 
                                time, 
                                value
                        FROM swmm_time_series_data WHERE time_series_name = ?"""
                rows = self.gutils.execute(data_qry, (self.time_series_name,)).fetchall()
                if rows:
                    self.outfall_time_series_tblw.setRowCount(0)
                    for row_number, row_data in enumerate(rows):
                        self.outfall_time_series_tblw.insertRow(row_number)
                        for col, data in enumerate(row_data):
                            if col == 0: # Date
                                if data:
                                    try:
                                        a, b, c = data.split("/")
                                        if len(a) < 2:
                                            a = "0" * (2 - len(a)) + a
                                        if len(b) < 2:
                                            b = "0" * (2 - len(b)) + b
                                        if len(c) < 4:
                                            c = "0" * (4 - len(c)) + c
                                        data = a + "/" + b + "/" + c
                                    except:
                                        data = ""
                                else:
                                    data = ""
                            if col == 1: # Time
                                if data:
                                    try:
                                        a, b = data.split(":")
                                        if len(a) == 1:
                                            a = "0" + a
                                        data = a + ":" + b
                                    except:
                                        data = "00:00"
                                else:
                                    data = "00:00"
                            if col == 2: # Value
                                data = str(data)
                            item = QTableWidgetItem()
                            item.setData(Qt.DisplayRole, data)
                            self.outfall_time_series_tblw.setItem(row_number, col, item)

                    # self.outfall_time_series_tblw.sortItems(0, Qt.AscendingOrder)
            else:
                self.name_le.setText(self.time_series_name)
                self.external_radio.setChecked(True)
                self.use_table_radio.setChecked(False)

        QApplication.restoreOverrideCursor()
        self.loading = False

    def select_time_series_file(self):
        self.uc.clear_bar_messages()

        s = QSettings()
        last_dir = s.value("FLO-2D/lastSWMMDir", "")
        time_series_file, __ = QFileDialog.getOpenFileName(None, "Select time series data file", directory=last_dir)
        if not time_series_file:
            return
        s.setValue("FLO-2D/lastSWMMDir", os.path.dirname(time_series_file))
        self.file_le.setText(os.path.normpath(time_series_file))
        # For future use
        try:
            pass
        except Exception as e:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.uc.show_error("ERROR 140220.0807: reading time series data file failed!", e)
            QApplication.restoreOverrideCursor()
            return

    def is_ok_to_save(self):
        if self.name_le.text() == "":
            self.uc.bar_warn("Time Series name required!", 2)
            self.time_series_name = ""
            self.values_ok = False

        elif " " in self.name_le.text():
            self.uc.bar_warn("Time Series name with spaces not allowed!", 2)
            self.time_series_name = ""
            self.values_ok = False

        elif self.description_le.text() == "":
            self.uc.bar_warn("Time Series description required!", 2)
            self.values_ok = False

        elif self.use_table_radio.isChecked() and self.outfall_time_series_tblw.rowCount() == 0:
            self.uc.bar_warn("Time Series table can't be empty!", 2)
            self.values_ok = False

        elif self.external_radio.isChecked() and self.file_le.text() == "":
            self.uc.bar_warn("Data file name required!", 2)
            self.values_ok = False
        else:
            self.values_ok = True

    def save_time_series(self):
        delete_sql = "DELETE FROM swmm_time_series WHERE time_series_name = ?"
        self.gutils.execute(delete_sql, (self.name_le.text(),))
        insert_sql = "INSERT INTO swmm_time_series (time_series_name, time_series_description, time_series_file, time_series_data) VALUES (?, ?, ?, ?);"
        self.gutils.execute(
            insert_sql,
            (
                self.name_le.text(),
                self.description_le.text(),
                self.file_le.text(),
                "True" if self.use_table_radio.isChecked() else "False",
            ),
        )

        delete_data_sql = "DELETE FROM swmm_time_series_data WHERE time_series_name = ?"
        self.gutils.execute(delete_data_sql, (self.name_le.text(),))

        insert_data_sql = [
            """INSERT INTO swmm_time_series_data (time_series_name, date, time, value) VALUES""",
            4,
        ]
        for row in range(0, self.outfall_time_series_tblw.rowCount()):
            date = self.outfall_time_series_tblw.item(row, 0)
            if date:
                date = date.text()

            time = self.outfall_time_series_tblw.item(row, 1)
            if time:
                time = time.text()

            value = self.outfall_time_series_tblw.item(row, 2)
            if value:
                value = value.text()

            insert_data_sql += [(self.name_le.text(), date, time, value)]
        self.gutils.batch_execute(insert_data_sql)

        self.uc.bar_info("Inflow time series " + self.name_le.text() + " saved.", 2)
        self.uc.log_info("Inflow time series " + self.name_le.text() + " saved.")
        self.time_series_name = self.name_le.text()
        self.close()

    def get_name(self):
        return self.time_series_name

    def ts_tblw_changed(self, Qitem):
        if not self.loading:
            column = Qitem.column()
            text = Qitem.text()

            if column == 0:  # First column (Date)
                if "/" in text:
                    a, b, c = text.split("/")
                    if len(a) < 2:
                        a = "0" * (2 - len(a)) + a
                    if len(b) < 2:
                        b = "0" * (2 - len(b)) + b
                    if len(c) < 4:
                        c = "0" * (4 - len(c)) + c
                    text = a + "/" + b + "/" + c

            elif column == 1:  # Second column (Time)
                if text == "":
                    text = "00:00"
                if ":" in text:
                    a, b = text.split(":")
                    if len(a) == 1:
                        a = "0" + a
                    text = a + ":" + b

            elif column == 2:  # Third column (value)
                if text == "":
                    text = "0.0"

            Qitem.setText(text)

    def add_time(self):
        self.outfall_time_series_tblw.insertRow(self.outfall_time_series_tblw.rowCount())
        row_number = self.outfall_time_series_tblw.rowCount() - 1

        item = QTableWidgetItem()

        # Code for current date
        # d = QDate.currentDate()
        # d = str(d.month()) + "/" + str(d.day()) + "/" + str(d.year())
        # item.setData(Qt.DisplayRole, d)

        # Code for empty item
        item.setData(Qt.DisplayRole, "")

        self.outfall_time_series_tblw.setItem(row_number, 0, item)

        item = QTableWidgetItem()

        # Code for current time
        # t = QTime.currentTime()
        # t = str(t.hour()) + ":" + str(t.minute())
        # item.setData(Qt.DisplayRole, t)

        # Code for starting time equal 00:00
        t = "00:00"
        item.setData(Qt.DisplayRole, t)
        self.outfall_time_series_tblw.setItem(row_number, 1, item)

        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, "0.0")
        self.outfall_time_series_tblw.setItem(row_number, 2, item)

        self.outfall_time_series_tblw.selectRow(row_number)
        self.outfall_time_series_tblw.setFocus()

    def delete_time(self):
        self.outfall_time_series_tblw.removeRow(self.outfall_time_series_tblw.currentRow())
        self.outfall_time_series_tblw.selectRow(0)
        self.outfall_time_series_tblw.setFocus()

    def copy_selection(self):
        selection = self.outfall_time_series_tblw.selectedIndexes()
        if selection:
            rows = sorted(index.row() for index in selection)
            columns = sorted(index.column() for index in selection)
            rowcount = rows[-1] - rows[0] + 1
            colcount = columns[-1] - columns[0] + 1
            table = [[""] * colcount for _ in range(rowcount)]
            for index in selection:
                row = index.row() - rows[0]
                column = index.column() - columns[0]
                table[row][column] = str(index.data())
            stream = io.StringIO()
            csv.writer(stream, delimiter="\t").writerows(table)
            QApplication.clipboard().setText(stream.getvalue())

    def paste(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)

        # Get the clipboard text
        clipboard_text = QApplication.clipboard().text()
        if not clipboard_text:
            QApplication.restoreOverrideCursor()
            return

        # Split clipboard data into rows and columns
        rows = clipboard_text.split("\n")
        if rows[-1] == '':  # Remove the extra empty line at the end if present
            rows = rows[:-1]
        num_rows = len(rows)
        if num_rows == 0:
            QApplication.restoreOverrideCursor()
            return

        # Get the top-left selected cell
        selection = self.outfall_time_series_tblw.selectionModel().selection()
        if not selection:
            QApplication.restoreOverrideCursor()
            return

        top_left_idx = selection[0].topLeft()
        sel_row = top_left_idx.row()
        sel_col = top_left_idx.column()

        # Insert rows if necessary
        if sel_row + num_rows > self.outfall_time_series_tblw.rowCount():
            self.outfall_time_series_tblw.setRowCount(sel_row + num_rows)

        # Insert columns if necessary (adjust table columns if paste exceeds current column count)
        num_cols = rows[0].count("\t") + 1
        if sel_col + num_cols > self.outfall_time_series_tblw.columnCount():
            self.outfall_time_series_tblw.setColumnCount(sel_col + num_cols)

        # Paste data into the table
        for row_idx, row in enumerate(rows):
            columns = row.split("\t")
            for col_idx, col in enumerate(columns):
                item = QTableWidgetItem(col.strip())
                self.outfall_time_series_tblw.setItem(sel_row + row_idx, sel_col + col_idx, item)

        QApplication.restoreOverrideCursor()

    def clear(self):
        self.outfall_time_series_tblw.setRowCount(0)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy_selection()
        elif event.matches(QKeySequence.Paste):
            self.paste()
        else:
            super().keyPressEvent(event)


uiDialog, qtBaseClass = load_ui("xy_curve_editor")


class CurveEditorDialog(qtBaseClass, uiDialog):
    before_paste = pyqtSignal()
    after_paste = pyqtSignal()
    after_delete = pyqtSignal()

    def __init__(self, iface, curve_name):
        qtBaseClass.__init__(self)

        uiDialog.__init__(self)
        self.iface = iface
        self.curve_name = curve_name
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None

        self.values_ok = False
        self.loading = True
        set_icon(self.add_data_btn, "add.svg")
        set_icon(self.delete_data_btn, "remove.svg")

        self.setup_connection()

        self.curve_tblw.setItemDelegate(FloatDelegate(3, self.curve_tblw))

        self.curve_buttonBox.accepted.connect(self.is_ok_to_save_curve)
        self.curve_tblw.itemChanged.connect(self.otc_tblw_changed)
        self.add_data_btn.clicked.connect(self.add_curve)
        self.delete_data_btn.clicked.connect(self.delete_data)
        self.load_curve_btn.clicked.connect(self.load_curve_file)
        self.save_curve_btn.clicked.connect(self.save_curve_file)
        self.copy_btn.clicked.connect(self.copy_selection)
        self.paste_btn.clicked.connect(self.paste)
        self.clear_btn.clicked.connect(self.clear)

        self.populate_curve_dialog()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_curve_dialog(self):
        self.add_curve()
        pass

    def is_ok_to_save_curve(self):
        if self.name_le.text() == "" or self.name_le.text() == "...":
            self.uc.bar_warn("Curve name required!", 2)
            self.curve_name = ""
            self.values_ok = False

        elif " " in self.name_le.text():
            self.uc.bar_warn("Curve Name with spaces not allowed!", 2)
            self.curve_name = ""
            self.values_ok = False

        elif self.description_le.text() == "":
            self.uc.bar_warn("Curve description required!", 2)
            self.values_ok = False

        elif self.curve_tblw.rowCount() == 0:
            self.uc.bar_warn("Curve table can't be empty!", 2)
            self.values_ok = False

        else:
            self.values_ok = True

    def save_curve(self):
        # Empty polymorphic method to be overwritten by a child derived class.
        pass

    def get_curve_name(self):
        return self.curve_name

    def otc_tblw_changed(self, Qitem):
        try:
            text = float(Qitem.text())
            Qitem.setText(str(text))
        except ValueError:
            Qitem.setText("0.0")

    def add_curve(self):
        self.curve_tblw.insertRow(self.curve_tblw.rowCount())
        row_number = self.curve_tblw.rowCount() - 1

        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, "0.0")
        self.curve_tblw.setItem(row_number, 0, item)

        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, "0.0")
        self.curve_tblw.setItem(row_number, 1, item)

        self.curve_tblw.selectRow(row_number)
        self.curve_tblw.setFocus()

    def delete_data(self):
        self.curve_tblw.removeRow(self.curve_tblw.currentRow())
        self.curve_tblw.selectRow(0)
        self.curve_tblw.setFocus()

    def load_curve_file(self):
        self.uc.clear_bar_messages()

        s = QSettings()
        last_dir = s.value("FLO-2D/lastSWMMDir", "")
        curve_file, __ = QFileDialog.getOpenFileName(
            None,
            "Select file with curve data to load",
            directory=last_dir,
            filter="Text files (*.txt *.TXT*);;All files(*.*)",
        )
        if not curve_file:
            return
        s.setValue("FLO-2D/lastSWMMDir", os.path.dirname(curve_file))

        # Load file into table:
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            with open(curve_file, "r") as f1:
                lines = f1.readlines()
            if len(lines) > 0:
                self.curve_tblw.setRowCount(0)
                j = -1
                for i in range(1, len(lines)):
                    if i == 1:
                        desc = lines[i]
                    else:
                        if lines[i].strip() != "":
                            nxt = lines[i].split()
                            if len(nxt) == 2:
                                j += 1
                                self.curve_tblw.insertRow(j)
                                x, y = nxt[0], nxt[1]
                                self.curve_tblw.setItem(j, 0, QTableWidgetItem(x))
                                self.curve_tblw.setItem(j, 1, QTableWidgetItem(y))
                            else:
                                self.uc.bar_warn("Wrong data in line " + str(j + 4) + " of curve file!")
                        else:
                            self.uc.bar_warn("Wrong data in line " + str(j + 4) + " of curve file!")
                self.description_le.setText(desc)

            QApplication.restoreOverrideCursor()

        except Exception as e:
            QApplication.setOverrideCursor(Qt.ArrowCursor)
            self.uc.show_error("ERROR 090422.0435: importing curve file failed!.\n", e)
            QApplication.restoreOverrideCursor()

    def save_curve_file(self):
        self.uc.clear_bar_messages()

        if self.curve_tblw.rowCount() == 0:
            self.uc.bar_warn("Curve table is empty. There is nothing to save!", 2)
            return
        elif self.description_le.text() == "":
            self.uc.bar_warn("Curve description required!", 2)
            return

        s = QSettings()
        last_dir = s.value("FLO-2D/lastSWMMDir", "")

        curve_file, __ = QFileDialog.getSaveFileName(
            None,
            "Save curve table as file...",
            directory=last_dir,
            filter="Text files (*.txt *.TXT*);;All files(*.*)",
        )

        if not curve_file:
            return

        s.setValue("FLO-2D/lastSWMMDir", os.path.dirname(curve_file))

        QApplication.setOverrideCursor(Qt.WaitCursor)
        with open(curve_file, "w") as tfile:
            tfile.write("EPASWMM Curve Data")
            tfile.write("\n" + self.description_le.text())

            for row in range(0, self.curve_tblw.rowCount()):
                hour = self.curve_tblw.item(row, 0)
                if hour:
                    hour = hour.text()
                else:
                    hour = "0.0"
                stage = self.curve_tblw.item(row, 1)
                if stage:
                    stage = stage.text()
                else:
                    stage = "0.0"
                tfile.write("\n" + hour + "    " + stage)

        QApplication.restoreOverrideCursor()
        self.uc.bar_info("Curve data saved as " + curve_file, 4)

    def copy_selection(self):
        selection = self.curve_tblw.selectedIndexes()
        if selection:
            rows = sorted(index.row() for index in selection)
            columns = sorted(index.column() for index in selection)
            rowcount = rows[-1] - rows[0] + 1
            colcount = columns[-1] - columns[0] + 1
            table = [[""] * colcount for _ in range(rowcount)]
            for index in selection:
                row = index.row() - rows[0]
                column = index.column() - columns[0]
                table[row][column] = str(index.data())
            stream = io.StringIO()
            csv.writer(stream, delimiter="\t").writerows(table)
            QApplication.clipboard().setText(stream.getvalue())

    def paste(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)

        # Get the clipboard text
        clipboard_text = QApplication.clipboard().text()
        if not clipboard_text:
            QApplication.restoreOverrideCursor()
            return

        # Split clipboard data into rows and columns
        rows = clipboard_text.split("\n")
        if rows[-1] == '':  # Remove the extra empty line at the end if present
            rows = rows[:-1]
        num_rows = len(rows)
        if num_rows == 0:
            QApplication.restoreOverrideCursor()
            return

        # Get the top-left selected cell
        selection = self.curve_tblw.selectionModel().selection()
        if not selection:
            QApplication.restoreOverrideCursor()
            return

        top_left_idx = selection[0].topLeft()
        sel_row = top_left_idx.row()
        sel_col = top_left_idx.column()

        # Insert rows if necessary
        if sel_row + num_rows > self.curve_tblw.rowCount():
            self.curve_tblw.setRowCount(sel_row + num_rows)

        # Insert columns if necessary (adjust table columns if paste exceeds current column count)
        num_cols = rows[0].count("\t") + 1
        if sel_col + num_cols > self.curve_tblw.columnCount():
            self.curve_tblw.setColumnCount(sel_col + num_cols)

        # Paste data into the table
        for row_idx, row in enumerate(rows):
            columns = row.split("\t")
            for col_idx, col in enumerate(columns):
                item = QTableWidgetItem(col.strip())
                self.curve_tblw.setItem(sel_row + row_idx, sel_col + col_idx, item)

        QApplication.restoreOverrideCursor()

    def clear(self):
        self.curve_tblw.setRowCount(0)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy_selection()
        elif event.matches(QKeySequence.Paste):
            self.paste()
        else:
            super().keyPressEvent(event)


class OutfallTidalCurveDialog(CurveEditorDialog):
    def populate_curve_dialog(self):
        self.loading = True
        if self.curve_name == "":
            pass
        else:
            self.setWindowTitle("Outfall Tidal Curve Editor")
            self.label_2.setText("Tidal Curve Name")
            self.curve_tblw.setHorizontalHeaderLabels(["Hour", "Stage"])
            tidal_sql = "SELECT * FROM swmm_tidal_curve WHERE tidal_curve_name = ?"
            row = self.gutils.execute(tidal_sql, (self.curve_name,)).fetchone()
            if row:
                self.name_le.setText(row[1])
                self.description_le.setText(row[2])

                data_qry = """SELECT
                                hour, 
                                stage
                        FROM swmm_tidal_curve_data WHERE tidal_curve_name = ? ORDER BY hour;"""
                rows = self.gutils.execute(data_qry, (self.curve_name,)).fetchall()
                if rows:
                    # Convert items of first column to float to sort them in ascending order:
                    rws = []
                    for row in rows:
                        rws.append([float(row[0]), row[1]])
                    rws.sort()
                    # Restore items of first column to string:
                    rows = []
                    for row in rws:
                        rows.append([str(row[0]), row[1]])

                    self.curve_tblw.setRowCount(0)

                    for row_number, row_data in enumerate(rows):
                        self.curve_tblw.insertRow(row_number)
                        for cell, data in enumerate(row_data):
                            # if cell == 0:
                            #     if ":" in data:
                            #         a, b = data.split(":")
                            #         b = float(b)/60
                            #         data = float(a) + b
                            #     else:
                            #         data = float(data)
                            self.curve_tblw.setItem(row_number, cell, QTableWidgetItem(str(data)))

            else:
                self.name_le.setText(self.curve_name)

        QApplication.restoreOverrideCursor()
        self.loading = False

    def save_curve(self):
        delete_sql = "DELETE FROM swmm_tidal_curve WHERE tidal_curve_name = ?"
        self.gutils.execute(delete_sql, (self.name_le.text(),))
        insert_sql = "INSERT INTO swmm_tidal_curve (tidal_curve_name, tidal_curve_description) VALUES (?, ?);"
        self.gutils.execute(
            insert_sql,
            (self.name_le.text(), self.description_le.text()),
        )

        delete_data_sql = "DELETE FROM swmm_tidal_curve_data WHERE tidal_curve_name = ?"
        self.gutils.execute(delete_data_sql, (self.name_le.text(),))

        insert_data_sql = [
            """INSERT INTO swmm_tidal_curve_data (tidal_curve_name, hour, stage) VALUES""",
            3,
        ]
        for row in range(0, self.curve_tblw.rowCount()):
            hour = self.curve_tblw.item(row, 0)
            if hour:
                hour = hour.text()

            stage = self.curve_tblw.item(row, 1)
            if stage:
                stage = stage.text()

            insert_data_sql += [(self.name_le.text(), hour, stage)]
        self.gutils.batch_execute(insert_data_sql)

        self.uc.bar_info("Curve " + self.name_le.text() + " saved.", 2)
        self.curve_name = self.name_le.text()
        self.close()


class StorageUnitTabularCurveDialog(CurveEditorDialog):
    def populate_curve_dialog(self):
        self.loading = True
        if self.curve_name == "":
            pass
        else:
            self.setWindowTitle("Storage Unit Tabular Curve Editor")
            self.label_2.setText("Tabular Curve Name")
            self.curve_tblw.setHorizontalHeaderLabels(["Depth", "Area"])
            curve_sql = "SELECT * FROM swmm_other_curves WHERE name = ? AND type = 'Storage'"
            row = self.gutils.execute(curve_sql, (self.curve_name,)).fetchone()
            if row:
                self.name_le.setText(row[1])
                self.description_le.setText(row[3])

                data_qry = """SELECT
                                x_value, 
                                y_value
                        FROM swmm_other_curves WHERE name = ? and type = 'Storage' ORDER BY x_value;"""
                rows = self.gutils.execute(data_qry, (self.curve_name,)).fetchall()
                if rows:
                    # Convert items of first column to float to sort them in ascending order:
                    rws = []
                    for row in rows:
                        rws.append([float(row[0]), row[1]])
                    rws.sort()
                    # Restore items of first column to string:
                    rows = []
                    for row in rws:
                        rows.append([str(row[0]), row[1]])

                    self.curve_tblw.setRowCount(0)

                    for row_number, row_data in enumerate(rows):
                        self.curve_tblw.insertRow(row_number)
                        for cell, data in enumerate(row_data):
                            self.curve_tblw.setItem(row_number, cell, QTableWidgetItem(str(data)))
            else:
                self.name_le.setText(self.curve_name)

        QApplication.restoreOverrideCursor()
        self.loading = False

    def save_curve(self):
        delete_data_sql = "DELETE FROM swmm_other_curves WHERE name = ? and type = 'Storage'"
        self.gutils.execute(delete_data_sql, (self.name_le.text(),))

        insert_data_sql = [
            """INSERT INTO swmm_other_curves (name, type,  description, x_value, y_value) VALUES""",
            5,
        ]
        for row in range(0, self.curve_tblw.rowCount()):
            x = self.curve_tblw.item(row, 0)
            if x:
                x = x.text()

            y = self.curve_tblw.item(row, 1)
            if y:
                y = y.text()

            insert_data_sql += [(self.name_le.text(), 'Storage', self.description_le.text(), x, y)]
        self.gutils.batch_execute(insert_data_sql)

        self.uc.bar_info("Curve " + self.name_le.text() + " saved.", 2)
        self.curve_name = self.name_le.text()
        self.close()
