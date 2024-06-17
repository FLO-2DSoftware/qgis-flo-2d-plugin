# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QDockWidget, QComboBox, QSpinBox, QDoubleSpinBox

from .dlg_inlets import ExternalInflowsDialog
from .dlg_outfalls import OutfallTimeSeriesDialog, OutfallTidalCurveDialog
# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

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
        self.dock_widget = QDockWidget("Storm Drain", self.iface.mainWindow())
        self.dock_widget.setObjectName("Inlets/Junctions")
        self.dock_widget.setWidget(self)

        self.current_node = None
        self.previous_node = None
        self.next_node = None

        # Connections
        self.name.editingFinished.connect(self.save_inlets_junctions)
        # self.external_inflow.editingFinished.connect(self.save_inlets_junctions)
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

        self.user_swmm_nodes_lyr = self.lyrs.data["user_swmm_nodes"]["qlyr"]

        self.dock_widget.visibilityChanged.connect(self.clear_rubber)

        self.next_btn.clicked.connect(self.populate_next_node)
        self.previous_btn.clicked.connect(self.populate_previous_node)
        self.external_btn.clicked.connect(self.show_external_inflow_dlg)
        self.tidal_btn.clicked.connect(self.open_tidal_curve)
        self.ts_btn.clicked.connect(self.open_time_series)

        self.inlets_junctions_outfalls = {
            self.label_4: self.junction_invert_elev, # Inlets
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
            self.label_21: self.outfall_invert_elev,  # Outfalls
            self.label_20: self.flapgate,
            self.label_6: self.swmm_allow_discharge,
            self.label_25: self.outfall_type,
            self.label_22: self.tidal_curve,
            self.label_24: self.time_series
        }
        if self.sd_type.count() == 0:
            self.sd_type.addItem("Inlet")
            self.sd_type.addItem("Outfall")

        if self.external_inflow.count() == 0:
            self.external_inflow.addItem("NO")
            self.external_inflow.addItem("YES")

        if self.flapgate.count() == 0:
            self.flapgate.addItem("NO")
            self.flapgate.addItem("YES")

        if self.swmm_allow_discharge.count() == 0:
            self.swmm_allow_discharge.addItem("True")
            self.swmm_allow_discharge.addItem("False")

        if self.outfall_type.count() == 0:
            outfalls = ["FIXED", "FREE", "NORMAL", "TIDAL", "TIMESERIES"]
            self.outfall_type.addItems(outfalls)

        tidal_curves = self.gutils.execute("SELECT tidal_curve_name FROM swmm_tidal_curve;").fetchall()
        if tidal_curves:
            self.tidal_curve.addItem('')
            for tidal_curve in tidal_curves:
                self.tidal_curve.addItem(tidal_curve[0])
            self.tidal_curve.setCurrentIndex(-1)

        time_series = self.gutils.execute("SELECT time_series_name FROM swmm_time_series;").fetchall()
        if time_series:
            self.time_series.addItem('')
            for time_serie in time_series:
                self.time_series.addItem(time_serie[0])
            self.time_series.setCurrentIndex(-1)

        self.sd_type.currentIndexChanged.connect(self.save_inlets_junctions)
        self.external_inflow.currentIndexChanged.connect(self.external_inflow_btn_chk)
        self.flapgate.currentIndexChanged.connect(self.save_flapgate)
        self.outfall_type.currentIndexChanged.connect(self.save_inlets_junctions)
        self.swmm_allow_discharge.currentIndexChanged.connect(self.save_allow_discharge)
        self.tidal_curve.currentIndexChanged.connect(self.save_tidal)
        self.time_series.currentIndexChanged.connect(self.save_ts)

    def populate_attributes(self, fid):
        """
        Function to populate the attributes
        """
        if not fid:
            return

        self.current_node = fid
        self.lyrs.show_feat_rubber(self.user_swmm_nodes_lyr.id(), fid, QColor(Qt.red))

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
                    drboxarea, 
                    outfall_invert_elev,
                    flapgate, 
                    swmm_allow_discharge,
                    outfall_type,
                    tidal_curve,
                    time_series                                         
                FROM
                    user_swmm_nodes
                WHERE
                    fid = {fid};"""
        ).fetchall()[0]

        # Assign attributes to the dialog
        self.grid.setText(str(attributes[0]))
        self.name.setText(str(attributes[1]))
        # Inlet
        if str(attributes[2]).lower().startswith("i"):
            self.sd_type.setCurrentIndex(0)
            self.external_btn.setHidden(False)
            self.external_inflow.setHidden(False)
            self.label_3.setHidden(False)
            self.tidal_btn.setHidden(True)
            self.ts_btn.setHidden(True)
            if attributes[3] == 1:
                external_inflow = 'YES'
            else:
                external_inflow = 'NO'
            self.external_inflow.setCurrentText(external_inflow)
            idx = 4
            for key, value in self.inlets_junctions_outfalls.items():
                if idx <= 17:
                    key.setHidden(False)
                    value.setHidden(False)
                    if attributes[idx] is not None:
                        if isinstance(value, QSpinBox) or isinstance(value, QDoubleSpinBox):
                            value.setValue(attributes[idx])
                        elif isinstance(value, QComboBox):
                            value.setCurrentText(attributes[idx])
                else:
                    key.setHidden(True)
                    value.setHidden(True)
                idx += 1
        # Outfall
        else:
            self.sd_type.setCurrentIndex(1)
            self.external_btn.setHidden(True)
            self.external_inflow.setHidden(True)
            self.label_3.setHidden(True)
            self.tidal_btn.setHidden(False)
            self.ts_btn.setHidden(False)
            idx = 3
            for key, value in self.inlets_junctions_outfalls.items():
                if idx > 17:
                    key.setHidden(False)
                    value.setHidden(False)
                    if attributes[idx] is not None:
                        if isinstance(value, QSpinBox) or isinstance(value, QDoubleSpinBox):
                            value.setValue(attributes[idx])
                        elif isinstance(value, QComboBox):
                            # Flapgate
                            if idx == 18:
                                if attributes[idx] == 'False':
                                    value.setCurrentIndex(0)
                                else:
                                    value.setCurrentIndex(1)
                            else:
                                value.setCurrentText(attributes[idx])
                else:
                    key.setHidden(True)
                    value.setHidden(True)
                idx += 1

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
            f"""SELECT name FROM user_swmm_nodes WHERE fid = '{self.current_node}';""").fetchall()
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
        outfall_invert_elev = self.outfall_invert_elev.value()
        if self.flapgate.currentIndex() == 0:
            flapgate = 'False'
        else:
            flapgate = 'True'
        swmm_allow_discharge = self.swmm_allow_discharge.currentText()
        outfall_type = self.outfall_type.currentText()
        if self.tidal_curve.count() > 0:
            tidal_curve = ''
        else:
            tidal_curve = self.tidal_curve.currentText()
        if self.time_series.count() > 0:
            time_series = ''
        else:
            time_series = self.time_series.currentText()

        self.gutils.execute(f"""
                                UPDATE 
                                    user_swmm_nodes
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
                                    drboxarea = '{drboxarea}',
                                    outfall_invert_elev = '{outfall_invert_elev}',
                                    flapgate = '{flapgate}', 
                                    swmm_allow_discharge = '{swmm_allow_discharge}',
                                    outfall_type = '{outfall_type}',
                                    tidal_curve = '{tidal_curve}',
                                    time_series = '{time_series}'       
                                WHERE 
                                    fid = '{self.current_node}';
                            """)

        self.user_swmm_nodes_lyr.triggerRepaint()

        # update the name on the user_swmm_conduits
        if old_name != name:
            update_inlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_conduits
                WHERE 
                    conduit_inlet = '{old_name}';
                """
            ).fetchall()
            if update_inlets_qry:
                for inlet in update_inlets_qry:
                    self.gutils.execute(f"""
                                            UPDATE 
                                                user_swmm_conduits
                                            SET 
                                                conduit_inlet = '{name}'
                                            WHERE 
                                                fid = '{inlet[0]}';
                                        """)

            update_outlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_conduits
                WHERE 
                    conduit_outlet = '{old_name}';
                """
            ).fetchall()
            if update_outlets_qry:
                for outlet in update_outlets_qry:
                    self.gutils.execute(f"""
                                            UPDATE 
                                                user_swmm_conduits
                                            SET 
                                                conduit_outlet = '{name}'
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
                                    user_swmm_nodes
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
        if tidal_curve != '':
            self.time_series.setCurrentIndex(-1)

        self.gutils.execute(f"""
                                UPDATE 
                                    user_swmm_nodes
                                SET 
                                    tidal_curve = '{tidal_curve}' 
                                WHERE 
                                    fid = '{self.current_node}';
                            """)

    def save_ts(self):
        """
        Function to save only time_series to avoid signal errors
        """
        time_series = self.time_series.currentText()
        if time_series != '':
            self.tidal_curve.setCurrentIndex(-1)

        self.gutils.execute(f"""
                                UPDATE 
                                    user_swmm_nodes
                                SET 
                                    time_series = '{time_series}' 
                                WHERE 
                                    fid = '{self.current_node}';
                            """)

    def save_allow_discharge(self):
        """
        Function to save only time_series to avoid signal errors
        """
        allow_discharge = self.swmm_allow_discharge.currentText()

        self.gutils.execute(f"""
                                UPDATE 
                                    user_swmm_nodes
                                SET 
                                    swmm_allow_discharge = '{allow_discharge}' 
                                WHERE 
                                    fid = '{self.current_node}';
                            """)

    def dock_widget(self):
        """ Close and delete the dock widget. """
        if self.dock_widget:
            self.uc.log_info("TTteste")
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
                user_swmm_nodes
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
                user_swmm_nodes
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
                            for name in names:
                                self.tidal_curve.addItem(name[0])
                            self.tidal_curve.addItem("")

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
                            for name in names:
                                self.time_series_cbo.addItem(name[0])
                            self.time_series.addItem("")

                            idx = self.time_series.findText(time_series_name)
                            self.time_series.setCurrentIndex(idx)

                        break
                    else:
                        break
            else:
                break

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
                                    user_swmm_nodes
                                SET 
                                    external_inflow = '{external_inflow_bool}'
                                WHERE 
                                    fid = '{self.current_node}';
                            """)
