# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright ? 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os

from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import QApplication, QMessageBox, QPushButton

from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("components")


class ComponentsDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs, in_or_out):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)

        QApplication.setOverrideCursor(Qt.WaitCursor)

        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = GeoPackageUtils(con, iface)
        self.current_lyr = None
        self.components = []
        self.export_overrides = {}
        self.in_or_out = in_or_out

        self.components_buttonBox.accepted.connect(self.select_components)
        self.select_all_chbox.clicked.connect(self.unselect_all)

        self.setFixedSize(self.size())

        self.populate_components_dialog()

        QApplication.restoreOverrideCursor()

    def _pre_check_decision(self, chb, has_data, switch_on=None, *, default_when_no_switch=True):
        if not has_data:
            chb.setEnabled(False)
            chb.setChecked(False)
            return
        chb.setEnabled(True)
        if switch_on is None:
            chb.setChecked(bool(default_when_no_switch))
        else:
            chb.setChecked(bool(switch_on))

    def _ask_export_decision(self, title, body):
        # QApplication.restoreOverrideCursor()
        # try:
            m = QMessageBox(self)
            m.setIcon(QMessageBox.Question)
            m.setWindowTitle(title)
            m.setText(body)
            btn_on = QPushButton("Switch ON and Export")
            btn_keep_off = QPushButton("Export but Keep OFF")
            btn_cancel = QPushButton("Cancel")
            m.addButton(btn_on, QMessageBox.AcceptRole)
            m.addButton(btn_keep_off, QMessageBox.DestructiveRole)
            m.addButton(btn_cancel, QMessageBox.RejectRole)
            m.setDefaultButton(btn_keep_off)
            clicked = m.exec_()
            b = m.clickedButton()
            if b is btn_on:
                return "on_and_export"
            elif b is btn_keep_off:
                return "export_only"
            return "cancel"
        # finally:
            # Reinstate Wait cursor for the rest of the processing
            # QApplication.setOverrideCursor(Qt.WaitCursor)

    def _ask_mudsed_decision(self):
        # QApplication.restoreOverrideCursor()
        # try:
            m = QMessageBox(self)
            m.setIcon(QMessageBox.Question)
            m.setWindowTitle("Component switch is OFF")
            m.setText(
                f"The CONT.DAT switch for <b>Mud/Debris/Sediment</b> is currently <b>OFF</b>."
                "<br><br>Which physical process do you want to enable?"
            )
            btn_mud = QPushButton("Mud/Debris")
            btn_sed = QPushButton("Sediment Transport")
            btn_two = QPushButton("Two phase")
            btn_cancel = QPushButton("None (Cancel)")
            m.addButton(btn_mud, QMessageBox.AcceptRole)
            m.addButton(btn_sed, QMessageBox.AcceptRole)
            m.addButton(btn_two, QMessageBox.AcceptRole)
            m.addButton(btn_cancel, QMessageBox.RejectRole)
            m.setDefaultButton(btn_mud)

            m.exec_()
            b = m.clickedButton()
            if b is btn_mud:
                return "mud"
            if b is btn_sed:
                return "sed"
            if b is btn_two:
                return "two_phase"
            return "cancel"
        # finally:
            # Reinstate Wait cursor for the rest of the processing
            # QApplication.setOverrideCursor(Qt.WaitCursor)

    def populate_components_dialog(self):
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGdsDir", "")
        self.file_lbl.setText(last_dir)

        self.data_rb.setVisible(False)
        self.hdf5_rb.setVisible(False)

        if self.in_or_out == "in":
            self.setWindowTitle("FLO-2D Components to Import")
            self.components_note_lbl.setVisible(False)
            self.mannings_n_and_Topo_chbox.setVisible(False)

            if os.path.isfile(last_dir + r"\CHAN.DAT"):
                if os.path.getsize(last_dir + r"\CHAN.DAT") > 0:
                    self.channels_chbox.setChecked(True)
                    self.channels_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\ARF.DAT"):
                if os.path.getsize(last_dir + r"\ARF.DAT") > 0:
                    self.reduction_factors_chbox.setChecked(True)
                    self.reduction_factors_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\STREET.DAT"):
                if os.path.getsize(last_dir + r"\STREET.DAT") > 0:
                    self.streets_chbox.setChecked(True)
                    self.streets_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\OUTFLOW.DAT"):
                if os.path.getsize(last_dir + r"\OUTFLOW.DAT") > 0:
                    self.outflow_elements_chbox.setChecked(True)
                    self.outflow_elements_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\INFLOW.DAT"):
                if os.path.getsize(last_dir + r"\INFLOW.DAT") > 0:
                    self.inflow_elements_chbox.setChecked(True)
                    self.inflow_elements_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\LEVEE.DAT"):
                if os.path.getsize(last_dir + r"\LEVEE.DAT") > 0:
                    self.levees_chbox.setChecked(True)
                    self.levees_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\MULT.DAT"):
                if os.path.getsize(last_dir + r"\MULT.DAT") > 0:
                    self.multiple_channels_chbox.setChecked(True)
                    self.multiple_channels_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\SIMPLE_MULT.DAT"):
                if os.path.getsize(last_dir + r"\SIMPLE_MULT.DAT") > 0:
                    self.multiple_channels_chbox.setChecked(True)
                    self.multiple_channels_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\BREACH.DAT"):
                if os.path.getsize(last_dir + r"\BREACH.DAT") > 0:
                    self.breach_chbox.setChecked(True)
                    self.breach_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\GUTTER.DAT"):
                if os.path.getsize(last_dir + r"\GUTTER.DAT") > 0:
                    self.gutters_chbox.setChecked(True)
                    self.gutters_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\INFIL.DAT"):
                if os.path.getsize(last_dir + r"\INFIL.DAT") > 0:
                    self.infiltration_chbox.setChecked(True)
                    self.infiltration_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\FPXSEC.DAT"):
                if os.path.getsize(last_dir + r"\FPXSEC.DAT") > 0:
                    self.floodplain_xs_chbox.setChecked(True)
                    self.floodplain_xs_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\SED.DAT"):
                if os.path.getsize(last_dir + r"\SED.DAT") > 0:
                    self.mud_and_sed_chbox.setChecked(True)
                    self.mud_and_sed_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\EVAPOR.DAT"):
                if os.path.getsize(last_dir + r"\EVAPOR.DAT") > 0:
                    self.evaporation_chbox.setChecked(True)
                    self.evaporation_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\HYSTRUC.DAT"):
                if os.path.getsize(last_dir + r"\HYSTRUC.DAT") > 0:
                    self.hydr_struct_chbox.setChecked(True)
                    self.hydr_struct_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\RAIN.DAT"):
                if os.path.getsize(last_dir + r"\RAIN.DAT") > 0:
                    self.rain_chbox.setChecked(True)
                    self.rain_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\SWMMFLO.DAT") or os.path.isfile(last_dir + r"\SWMMOUTF.DAT") or os.path.isfile(last_dir + r"\SWMM.INP"):
                if os.path.getsize(last_dir + r"\SWMMFLO.DAT") > 0 or os.path.getsize(
                        last_dir + r"\SWMMOUTF.DAT") > 0 or os.path.getsize(last_dir + r"\SWMM.INP") > 0:
                    self.storm_drain_chbox.setEnabled(True)
                    self.storm_drain_chbox.setChecked(True)

            if os.path.isfile(last_dir + r"\TOLSPATIAL.DAT"):
                if os.path.getsize(last_dir + r"\TOLSPATIAL.DAT") > 0:
                    self.spatial_tolerance_chbox.setChecked(True)
                    self.spatial_tolerance_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\FPFROUDE.DAT"):
                if os.path.getsize(last_dir + r"\FPFROUDE.DAT") > 0:
                    self.spatial_froude_chbox.setChecked(True)
                    self.spatial_froude_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\STEEP_SLOPEN.DAT"):
                if os.path.getsize(last_dir + r"\STEEP_SLOPEN.DAT") > 0:
                    self.spatial_steep_slopen_chbox.setChecked(True)
                    self.spatial_steep_slopen_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\LID_VOLUME.DAT"):
                if os.path.getsize(last_dir + r"\LID_VOLUME.DAT") > 0:
                    self.spatial_lid_volume_chbox.setChecked(True)
                    self.spatial_lid_volume_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\SHALLOWN_SPATIAL.DAT"):
                if os.path.getsize(last_dir + r"\SHALLOWN_SPATIAL.DAT") > 0:
                    self.spatial_shallow_n_chbox.setChecked(True)
                    self.spatial_shallow_n_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\TAILINGS.DAT"):
                if os.path.getsize(last_dir + r"\TAILINGS.DAT") > 0:
                    self.tailings_chbox.setChecked(True)
                    self.tailings_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\TAILINGS_CV.DAT"):
                if os.path.getsize(last_dir + r"\TAILINGS_CV.DAT") > 0:
                    self.tailings_chbox.setChecked(True)
                    self.tailings_chbox.setEnabled(True)

            if os.path.isfile(last_dir + r"\TAILINGS_STACK_DEPTH.DAT"):
                if os.path.getsize(last_dir + r"\TAILINGS_STACK_DEPTH.DAT") > 0:
                    self.tailings_chbox.setChecked(True)
                    self.tailings_chbox.setEnabled(True)

        elif self.in_or_out == "out":
            self.setWindowTitle("FLO-2D Components to Export")
            show_note = False

            sql = """SELECT name, value FROM cont;"""
            options = {o: v if v is not None else "" for o, v in self.gutils.execute(sql).fetchall()}

            if options["ICHANNEL"] == "0" and not self.gutils.is_table_empty("chan"):
                self.channels_chbox.setText("*" + self.channels_chbox.text() + "*")
                show_note = True

            if options["IEVAP"] == "0" and not self.gutils.is_table_empty("evapor"):
                self.evaporation_chbox.setText("*" + self.evaporation_chbox.text() + "*")
                show_note = True

            if options["IHYDRSTRUCT"] == "0" and not self.gutils.is_table_empty("struct"):
                self.hydr_struct_chbox.setText("*" + self.hydr_struct_chbox.text() + "*")
                show_note = True

            if options["IMULTC"] == "0" and not (
                self.gutils.is_table_empty("mult_cells") and self.gutils.is_table_empty("simple_mult_cells")
            ):
                self.multiple_channels_chbox.setText("*" + self.multiple_channels_chbox.text() + "*")
                show_note = True

            if options["INFIL"] == "0" and not self.gutils.is_table_empty("infil"):
                self.infiltration_chbox.setText("*" + self.infiltration_chbox.text() + "*")
                show_note = True

            if options["IRAIN"] == "0" and not self.gutils.is_table_empty("rain"):
                self.rain_chbox.setText("*" + self.rain_chbox.text() + "*")
                show_note = True

            if (options["ISED"] == "0" and not self.gutils.is_table_empty("sed")) and (
                options["MUD"] == "0" and not self.gutils.is_table_empty("mud")
            ):
                self.mud_and_sed_chbox.setText("*" + self.mud_and_sed_chbox.text() + "*")
                show_note = True

            if options["IWRFS"] == "0" and not self.gutils.is_table_empty("blocked_cells"):
                self.reduction_factors_chbox.setText("*" + self.reduction_factors_chbox.text() + "*")
                show_note = True

            if options["LEVEE"] == "0" and not self.gutils.is_table_empty("levee_data"):
                self.levees_chbox.setText("*" + self.levees_chbox.text() + "*")
                show_note = True

            if options["MSTREET"] == "0" and not self.gutils.is_table_empty("streets"):
                self.streets_chbox.setText("*" + self.streets_chbox.text() + "*")
                show_note = True

            if options["SWMM"] == "0" and not self.gutils.is_table_empty("swmmflo"):
                self.storm_drain_chbox.setText("*" + self.storm_drain_chbox.text() + "*")
                show_note = True

            self.components_note_lbl.setVisible(show_note)

            has = lambda t: not self.gutils.is_table_empty(t)
            opt = lambda k: options.get(k, "")

            self._pre_check_decision(self.channels_chbox, has("chan"), opt("ICHANNEL") == "1")
            self._pre_check_decision(self.evaporation_chbox, has("evapor"), opt("IEVAP") == "1")
            self._pre_check_decision(self.infiltration_chbox, has("infil"), opt("INFIL") == "1")
            self._pre_check_decision(self.hydr_struct_chbox, has("struct"), opt("IHYDRSTRUCT") == "1")
            self._pre_check_decision(self.rain_chbox, has("rain"), opt("IRAIN") == "1")
            self._pre_check_decision(self.reduction_factors_chbox, has("blocked_cells"), opt("IWRFS") == "1")
            self._pre_check_decision(self.levees_chbox, has("levee_data"), opt("LEVEE") == "1")
            self._pre_check_decision(self.streets_chbox, has("streets"), opt("MSTREET") == "1")
            self._pre_check_decision(self.storm_drain_chbox, has("swmmflo"), opt("SWMM") == "1")

            mudsed_has = has("mud") or has("sed")
            mudsed_on = (opt("ISED") == "1") or (opt("MUD") in ("1", "2"))
            self._pre_check_decision(self.mud_and_sed_chbox, mudsed_has, mudsed_on)

            mult_has = has("mult_cells") or has("simple_mult_cells")
            if opt("IMULTC") == "1":
                if not mult_has:
                    self.gutils.set_cont_par("IMULTC", 0)
                    self._pre_check_decision(self.multiple_channels_chbox, False, False)
                else:
                    if self.gutils.is_table_empty("mult"):
                        self.gutils.fill_empty_mult_globals()
                    self._pre_check_decision(self.multiple_channels_chbox, True, True)
            else:
                self._pre_check_decision(self.multiple_channels_chbox, mult_has, False)

            if has("breach"):
                row = self.gutils.execute("SELECT ilevfail FROM levee_general").fetchone()
                if row and row[0] == 2:
                    self.breach_chbox.setEnabled(True)
                    self.breach_chbox.setChecked(True)
                else:
                    self.breach_chbox.setEnabled(False)
                    self.breach_chbox.setChecked(False)
            else:
                self.breach_chbox.setEnabled(False)
                self.breach_chbox.setChecked(False)

            self._pre_check_decision(self.outflow_elements_chbox, has("outflow_cells"), None, default_when_no_switch=True)
            self._pre_check_decision(self.inflow_elements_chbox,
                                   has("inflow") or has("reservoirs") or has("tailing_reservoirs"), None,
                                   default_when_no_switch=True)
            self._pre_check_decision(self.gutters_chbox, has("gutter_cells"), None, default_when_no_switch=True)
            self._pre_check_decision(self.floodplain_xs_chbox, has("fpxsec"), None, default_when_no_switch=True)

            self._pre_check_decision(self.spatial_shallow_n_chbox, has("spatialshallow_cells"),
                                   None, default_when_no_switch=True)
            self._pre_check_decision(self.spatial_tolerance_chbox, has("tolspatial_cells"), None, default_when_no_switch=True)
            self._pre_check_decision(self.spatial_froude_chbox, has("fpfroude_cells"), None, default_when_no_switch=True)
            self._pre_check_decision(self.spatial_steep_slopen_chbox, has("steep_slope_n_cells"), None,
                                   default_when_no_switch=True)

            self._pre_check_decision(self.spatial_lid_volume_chbox, has("lid_volume_cells"), None,
                                   default_when_no_switch=True)
            self._pre_check_decision(self.mannings_n_and_Topo_chbox, has("grid"), None, default_when_no_switch=True)
            self._pre_check_decision(self.tailings_chbox, has("tailing_cells"), None, default_when_no_switch=True)
            self._pre_check_decision(self.outrc_chbox, has("outrc"), None, default_when_no_switch=True)

        else:
            QApplication.restoreOverrideCursor()
            self.uc.show_info("ERROR 240619.0704: Wrong components in/out selection!")

    _SWITCH_KEYS = {
        "Channels": "ICHANNEL",
        "Evaporation": "IEVAP",
        "Infiltration": "INFIL",
        "Hydraulic Structures": "IHYDRSTRUCT",
        "Rain": "IRAIN",
        "Reduction Factors": "IWRFS",
        "Levees": "LEVEE",
        "Streets": "MSTREET",
        "Storm Drain": "SWMM",
        "Multiple Channels": "IMULTC",
        "Mudflow and Sediment Transport": ("MUD", "ISED"),
    }

    def _has(self, table_name):
        return not self.gutils.is_table_empty(table_name)

    def select_components(self):
        self.components = []
        self.export_overrides = {}

        sql = "SELECT name, value FROM cont;"
        options = {o: (v if v is not None else "0") for o, v in self.gutils.execute(sql).fetchall()}

        def switch_is_on(k):
            return options.get(k, "0") == "1"

        def guard_and_record(comp_label, *, data_has, switch_keys):
            if not data_has:
                for k in ((switch_keys,) if isinstance(switch_keys, str) else switch_keys):
                    self.export_overrides.pop(k, None)
                return True

            keys = (switch_keys,) if isinstance(switch_keys, str) else tuple(switch_keys)

            any_off = any(not switch_is_on(k) for k in keys)

            if any_off:
                title = "Component switch is OFF"
                body = (
                    f"The CONT.DAT switch for <b>{comp_label}</b> is currently <b>OFF</b>."
                    "<br><br>How would you like to proceed?"
                )
                decision = self._ask_export_decision(title, body)

                if decision == "cancel":
                    for k in keys:
                        self.export_overrides.pop(k, None)
                    return False

                for k in keys:
                    self.export_overrides[k] = decision
                return True
            for k in keys:
                self.export_overrides[k] = "on_and_export"
            return True

        if self.channels_chbox.isChecked():
            chan_has = self._has("chan") or self._has("xsec")
            if guard_and_record("Channels", data_has=chan_has, switch_keys=self._SWITCH_KEYS["Channels"]):
                self.components.append("Channels")

        if self.evaporation_chbox.isChecked():
            if guard_and_record("Evaporation", data_has=self._has("evapor"), switch_keys=self._SWITCH_KEYS["Evaporation"]):
                self.components.append("Evaporation")

        if self.hydr_struct_chbox.isChecked():
            if guard_and_record("Hydraulic Structures", data_has=self._has("struct"),
                                switch_keys=self._SWITCH_KEYS["Hydraulic Structures"]):
                self.components.append("Hydraulic Structures")

        if self.infiltration_chbox.isChecked():
            if guard_and_record("Infiltration", data_has=self._has("infil"), switch_keys=self._SWITCH_KEYS["Infiltration"]):
                self.components.append("Infiltration")

        if self.rain_chbox.isChecked():
            if guard_and_record("Rain", data_has=self._has("rain"), switch_keys=self._SWITCH_KEYS["Rain"]):
                self.components.append("Rain")

        if self.reduction_factors_chbox.isChecked():
            if guard_and_record("Reduction Factors", data_has=self._has("blocked_cells"),
                                switch_keys=self._SWITCH_KEYS["Reduction Factors"]):
                self.components.append("Reduction Factors")

        if self.levees_chbox.isChecked():
            levee_has = self._has("levee_data") or self._has("levee") or self._has("levee_lines")
            if guard_and_record("Levees", data_has=levee_has, switch_keys=self._SWITCH_KEYS["Levees"]):
                self.components.append("Levees")

        if self.streets_chbox.isChecked():
            if guard_and_record("Streets", data_has=self._has("streets"), switch_keys=self._SWITCH_KEYS["Streets"]):
                self.components.append("Streets")

        if self.storm_drain_chbox.isChecked():
            sd_has = self._has("swmmflo") or self._has("swmmoutf")
            if guard_and_record("Storm Drain", data_has=sd_has, switch_keys=self._SWITCH_KEYS["Storm Drain"]):
                self.components.append("Storm Drain")

        if self.multiple_channels_chbox.isChecked():
            mult_has = self._has("mult_cells") or self._has("simple_mult_cells")
            if guard_and_record("Multiple Channels", data_has=mult_has, switch_keys=self._SWITCH_KEYS["Multiple Channels"]):
                self.components.append("Multiple Channels")

        if self.mud_and_sed_chbox.isChecked():
            # Data presence
            mud_has = self._has("mud")
            sed_has = self._has("sed")
            has_any = mud_has or sed_has

            keys = self._SWITCH_KEYS["Mudflow and Sediment Transport"]  # ("MUD", "ISED")

            # Read current switch states
            MUD = options.get("MUD", "0")
            ISED = options.get("ISED", "0")
            mud_on = MUD in ("1", "2")          # 1 = Mud/Debris, 2 = Two-phase
            sed_on = ISED == "1"
            both_off = (not mud_on) and (not sed_on)

            # No data: nothing to ask; just include component (no overrides)
            if not has_any:
                for k in (keys if isinstance(keys, (list, tuple)) else (keys,)):
                    self.export_overrides.pop(k, None)
                self.components.append("Mudflow and Sediment Transport")

            else:
                # If *both* switches are OFF, show the first window (export decision)
                if both_off:
                    title = "Component switch is OFF"
                    body = (
                        "The CONT.DAT switch for <b>Mud/Debris/Sediment</b> is currently <b>OFF</b>."
                        "<br><br>How would you like to proceed?"
                    )
                    decision = self._ask_export_decision(title, body)

                    if decision == "cancel":
                        for k in (keys if isinstance(keys, (list, tuple)) else (keys,)):
                            self.export_overrides.pop(k, None)
                        # Do not add component
                    elif decision == "export_only":
                        # Export only -> do NOT ask for physical process
                        self.export_overrides["MUD"] = "export_only"
                        self.export_overrides["ISED"] = "export_only"
                        self.export_overrides["_MUD_MODE"] = "none"
                        self.components.append("Mudflow and Sediment Transport")
                    else:
                        # decision == "on_and_export": NOW ask which physical process to enable
                        choice = self._ask_mudsed_decision()
                        if choice == "cancel":
                            for k in (keys if isinstance(keys, (list, tuple)) else (keys,)):
                                self.export_overrides.pop(k, None)
                            # Do not add component
                        elif choice == "mud":
                            self.export_overrides["MUD"] = "on_and_export"
                            self.export_overrides["ISED"] = "export_only"
                            self.export_overrides["_MUD_MODE"] = "mud"
                            self.components.append("Mudflow and Sediment Transport")
                        elif choice == "sed":
                            self.export_overrides["ISED"] = "on_and_export"
                            self.export_overrides["MUD"] = "export_only"
                            self.export_overrides["_MUD_MODE"] = "sed"
                            self.components.append("Mudflow and Sediment Transport")
                        elif choice == "two_phase":
                            self.export_overrides["MUD"] = "on_and_export"   # 2-phase is encoded in MUD==2 downstream
                            self.export_overrides["ISED"] = "export_only"
                            self.export_overrides["_MUD_MODE"] = "two_phase"
                            self.components.append("Mudflow and Sediment Transport")

                else:
                    # At least one is already ON -> do not show either dialog; mirror current state
                    if mud_on:
                        self.export_overrides["MUD"] = "on_and_export"
                        self.export_overrides["ISED"] = "export_only"
                        self.export_overrides["_MUD_MODE"] = "two_phase" if MUD == "2" else "mud"
                    else:
                        self.export_overrides["ISED"] = "on_and_export"
                        self.export_overrides["MUD"] = "export_only"
                        self.export_overrides["_MUD_MODE"] = "sed"
                    self.components.append("Mudflow and Sediment Transport")


        if self.outflow_elements_chbox.isChecked():
            self.components.append("Outflow Elements")
        if self.inflow_elements_chbox.isChecked():
            self.components.append("Inflow Elements")
        if self.gutters_chbox.isChecked():
            self.components.append("Gutters")
        if self.floodplain_xs_chbox.isChecked():
            self.components.append("Floodplain Cross Sections")
        if self.spatial_shallow_n_chbox.isChecked():
            self.components.append("Spatial Shallow-n")
        if self.spatial_tolerance_chbox.isChecked():
            self.components.append("Spatial Tolerance")
        if self.spatial_froude_chbox.isChecked():
            self.components.append("Spatial Froude")
        if self.spatial_steep_slopen_chbox.isChecked():
            self.components.append("Spatial Steep Slope-n")
        if self.spatial_lid_volume_chbox.isChecked():
            self.components.append("LID Volume")
        if self.mannings_n_and_Topo_chbox.isChecked():
            self.components.append("Manning's n and Topography")
        if self.tailings_chbox.isChecked():
            self.components.append("Tailings")
        if self.outrc_chbox.isChecked():
            self.components.append("OUTrc")

        self.accept()

    def unselect_all(self):
        self.check_components(self.select_all_chbox.isChecked())

    def check_components(self, select=True):
        for chb in [
            self.channels_chbox, self.reduction_factors_chbox, self.streets_chbox,
            self.outflow_elements_chbox, self.inflow_elements_chbox, self.levees_chbox,
            self.multiple_channels_chbox, self.breach_chbox, self.gutters_chbox,
            self.infiltration_chbox, self.floodplain_xs_chbox, self.mud_and_sed_chbox,
            self.evaporation_chbox, self.hydr_struct_chbox, self.mudflo_chbox,
            self.rain_chbox, self.storm_drain_chbox, self.spatial_shallow_n_chbox,
            self.spatial_tolerance_chbox, self.spatial_froude_chbox,
            self.spatial_steep_slopen_chbox, self.spatial_lid_volume_chbox,
            self.mannings_n_and_Topo_chbox,
        ]:
            if chb.isEnabled():
                chb.setChecked(select)
