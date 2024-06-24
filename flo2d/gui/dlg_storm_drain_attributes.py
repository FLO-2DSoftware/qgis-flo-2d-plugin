# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QDockWidget, QComboBox, QSpinBox, QDoubleSpinBox
from qgis._gui import QgsDockWidget

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

        self.dock_widget.visibilityChanged.connect(self.clear_rubber)

        self.next_btn.clicked.connect(self.populate_next_node)
        self.previous_btn.clicked.connect(self.populate_previous_node)
        self.external_btn.clicked.connect(self.show_external_inflow_dlg)

        self.inlets_junctions = {
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
        self.dock_widget = QgsDockWidget("Outlets", self.iface.mainWindow())
        self.dock_widget.setObjectName("Outlets")
        self.dock_widget.setWidget(self)

        self.current_node = None
        self.previous_node = None
        self.next_node = None

        # Connections
        self.name.editingFinished.connect(self.save_outlets)
        self.outfall_invert_elev.editingFinished.connect(self.save_outlets)
        self.fixed_stage.editingFinished.connect(self.save_outlets)

        self.user_swmm_outlets_lyr = self.lyrs.data["user_swmm_outlets"]["qlyr"]

        self.dock_widget.visibilityChanged.connect(self.clear_rubber)

        self.next_btn.clicked.connect(self.populate_next_node)
        self.previous_btn.clicked.connect(self.populate_previous_node)

        self.outlets = {
            self.label_21: self.outfall_invert_elev,
            self.label_20: self.flapgate,
            self.label_23: self.fixed_stage,
            self.label_22: self.tidal_curve,
            self.label_24: self.time_series,
            self.label_25: self.outfall_type,
            self.label_6: self.swmm_allow_discharge,
        }

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

        # Assign attributes to the dialog
        self.grid.setText(str(attributes[0]))
        self.name.setText(str(attributes[1]))
        idx = 2
        for key, value in self.outlets.items():
            if attributes[idx] is not None:
                if isinstance(value, QSpinBox) or isinstance(value, QDoubleSpinBox):
                    value.setValue(attributes[idx])
                elif isinstance(value, QComboBox):
                    # Flapgate
                    if idx == 3:
                        if attributes[idx] == 'False':
                            value.setCurrentIndex(0)
                        else:
                            value.setCurrentIndex(1)
                    else:
                        value.setCurrentText(attributes[idx])
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
        swmm_allow_discharge = self.swmm_allow_discharge.currentText()
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
        allow_discharge = self.swmm_allow_discharge.currentText()

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

        inlets_junctions = self.gutils.execute("SELECT name FROM user_swmm_inlets_junctions;").fetchall()
        if inlets_junctions:
            for inlets_junction in inlets_junctions:
                self.pump_inlet.addItem(inlets_junction[0])
                self.pump_outlet.addItem(inlets_junction[0])
            self.pump_inlet.setCurrentIndex(-1)
            self.pump_outlet.setCurrentIndex(-1)

        pump_curves = self.gutils.execute("SELECT DISTINCT pump_curve_name FROM swmm_pumps_curve_data;").fetchall()
        if pump_curves:
            for pump_curve in pump_curves:
                self.pump_curve.addItem(pump_curve[0])
            self.pump_curve.setCurrentIndex(-1)

        self.pump_name.editingFinished.connect(self.save_pumps)
        self.pump_inlet.currentIndexChanged.connect(self.save_pumps)
        self.pump_outlet.currentIndexChanged.connect(self.save_pumps)
        self.pump_curve.currentIndexChanged.connect(self.save_pumps)
        self.pump_init_status.currentIndexChanged.connect(self.save_pumps)
        self.pump_startup_depth.editingFinished.connect(self.save_pumps)
        self.pump_shutoff_depth.editingFinished.connect(self.save_pumps)

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

        self.pump_name.setText(attributes[0])
        self.pump_inlet.setCurrentText(attributes[1])
        self.pump_outlet.setCurrentText(attributes[2])
        self.pump_curve.setCurrentText(attributes[3])
        self.pump_init_status.setCurrentText(attributes[4])
        self.pump_startup_depth.setValue(attributes[5])
        self.pump_shutoff_depth.setValue(attributes[6])

    def save_pumps(self):
        """
        Function to save the pumps everytime an attribute is changed
        """

        pump_name = self.pump_name.text()
        pump_inlet = self.pump_inlet.currentText()
        pump_outlet = self.pump_outlet.currentText()
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

        # # Green rubber the inlet
        # if pump_inlet != '':
        #     inlet_fid = self.gutils.execute(f"SELECT fid FROM user_swmm_inlets_junctions WHERE name = '{pump_inlet}'").fetchone()[0]
        #     self.lyrs.show_feat_rubber(self.user_swmm_inlets_junctions_lyr.id(), inlet_fid, QColor(Qt.green), clear=False)
        #
        # # Blue rubber the outlet
        # if pump_outlet != '':
        #     outlet_fid = self.gutils.execute(f"SELECT fid FROM user_swmm_inlets_junctions WHERE name = '{pump_outlet}'").fetchone()[0]
        #     self.lyrs.show_feat_rubber(self.user_swmm_inlets_junctions_lyr.id(), outlet_fid, QColor(Qt.blue), clear=False)
        #
        # self.user_swmm_inlets_junctions_lyr.triggerRepaint()
        self.user_swmm_pumps_lyr.triggerRepaint()

    def clear_rubber(self):
        """
        Function to clear the rubber when closing the widget
        """
        self.lyrs.clear_rubber()


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

        # Add junctions to the comboboxes
        inlets_junctions = self.gutils.execute("SELECT name FROM user_swmm_inlets_junctions;").fetchall()
        if inlets_junctions:
            for inlets_junction in inlets_junctions:
                self.orifice_inlet.addItem(inlets_junction[0])
                self.orifice_outlet.addItem(inlets_junction[0])

        if self.orifice_type.count() == 0:
            init_status = ["SIDE", "BOTTOM"]
            self.orifice_type.addItems(init_status)

        if self.orifice_flap_gate.count() == 0:
            self.orifice_flap_gate.addItem("NO")
            self.orifice_flap_gate.addItem("YES")

        if self.orifice_shape.count() == 0:
            self.orifice_shape.addItem("CIRCULAR")
            self.orifice_shape.addItem("RECT_CLOSED")

        self.orifice_type.currentIndexChanged.connect(self.save_orifices)
        self.orifice_flap_gate.currentIndexChanged.connect(self.save_orifices)
        self.orifice_shape.currentIndexChanged.connect(self.save_orifices)
        self.orifice_crest_height.editingFinished.connect(self.save_orifices)
        self.orifice_disch_coeff.editingFinished.connect(self.save_orifices)
        self.orifice_open_close_time.editingFinished.connect(self.save_orifices)
        self.orifice_height.editingFinished.connect(self.save_orifices)
        self.orifice_width.editingFinished.connect(self.save_orifices)

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

        self.orifice_name.setText(attributes[0])
        self.orifice_inlet.setCurrentText(attributes[1])
        self.orifice_outlet.setCurrentText(attributes[2])
        self.orifice_type.setCurrentText(attributes[3])
        self.orifice_crest_height.setValue(attributes[4])
        self.orifice_disch_coeff.setValue(attributes[5])
        self.orifice_flap_gate.setCurrentText(attributes[6])
        self.orifice_open_close_time.setValue(attributes[7])
        self.orifice_shape.setCurrentText(attributes[8])
        self.orifice_height.setValue(attributes[9])
        self.orifice_width.setValue(attributes[10])

    def save_orifices(self):
        """
        Function to save the orifices everytime an attribute is changed
        """

        orifice_name = self.orifice_name.text()
        orifice_inlet = self.orifice_inlet.currentText()
        orifice_outlet = self.orifice_outlet.currentText()
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

        # # Green rubber the inlet
        # if pump_inlet != '':
        #     inlet_fid = self.gutils.execute(f"SELECT fid FROM user_swmm_inlets_junctions WHERE name = '{pump_inlet}'").fetchone()[0]
        #     self.lyrs.show_feat_rubber(self.user_swmm_inlets_junctions_lyr.id(), inlet_fid, QColor(Qt.green), clear=False)
        #
        # # Blue rubber the outlet
        # if pump_outlet != '':
        #     outlet_fid = self.gutils.execute(f"SELECT fid FROM user_swmm_inlets_junctions WHERE name = '{pump_outlet}'").fetchone()[0]
        #     self.lyrs.show_feat_rubber(self.user_swmm_inlets_junctions_lyr.id(), outlet_fid, QColor(Qt.blue), clear=False)
        #
        # self.user_swmm_inlets_junctions_lyr.triggerRepaint()
        self.user_swmm_orifices_lyr.triggerRepaint()

    def clear_rubber(self):
        """
        Function to clear the rubber when closing the widget
        """
        self.lyrs.clear_rubber()


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

        # # Green rubber the inlet
        # if self.conduit_inlet.text() != '':
        #     conduit_fid = self.gutils.execute(f"SELECT fid FROM user_swmm_inlets_junctions WHERE name = '{self.conduit_inlet.text()}'").fetchone()[0]
        #     self.lyrs.show_feat_rubber(self.user_swmm_inlets_junctions_lyr.id(), conduit_fid, QColor(Qt.green), clear=False)
        #
        # # Blue rubber the outlet
        # if self.conduit_outlet.text() != '':
        #     conduit_fid = self.gutils.execute(f"SELECT fid FROM user_swmm_inlets_junctions WHERE name = '{self.conduit_outlet.text()}'").fetchone()[0]
        #     self.lyrs.show_feat_rubber(self.user_swmm_inlets_junctions_lyr.id(), conduit_fid, QColor(Qt.blue), clear=False)
        #
        # self.user_swmm_inlets_junctions_lyr.triggerRepaint()
        self.user_swmm_conduits_lyr.triggerRepaint()

    def clear_rubber(self):
        """
        Function to clear the rubber when closing the widget
        """
        self.lyrs.clear_rubber()