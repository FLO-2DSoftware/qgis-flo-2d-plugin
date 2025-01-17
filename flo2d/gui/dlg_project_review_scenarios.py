# -*- coding: utf-8 -*-
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QFileDialog

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from .ui_utils import load_ui
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui("project_review_scenarios")


class ProjectReviewScenariosDialog(qtBaseClass, uiDialog):
    def __init__(self, iface):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.setupUi(self)
        self.iface = iface

        self.uc = UserCommunication(iface, "FLO-2D")
        self.s = QSettings()

        self.populate_scenarios()

        # connections
        self.ok_btn.clicked.connect(self.save_scenarios)
        self.cancel_btn.clicked.connect(self.close_dlg)
        self.scenario1_btn.clicked.connect(lambda: self.select_scenario(1))
        self.scenario2_btn.clicked.connect(lambda: self.select_scenario(2))
        self.scenario3_btn.clicked.connect(lambda: self.select_scenario(3))
        self.scenario4_btn.clicked.connect(lambda: self.select_scenario(4))
        self.scenario5_btn.clicked.connect(lambda: self.select_scenario(5))

    def populate_scenarios(self):
        """
        Function to populate the scenarios on the Project Review - Scenarios
        """
        use_prs = self.s.value("FLO-2D/use_prs", "")
        if use_prs:
            self.use_scenarios_grpbox.setChecked(True)
        else:
            self.use_scenarios_grpbox.setChecked(False)

        scenario1 = self.s.value("FLO-2D/scenario1")
        self.scenario1_le.setText(scenario1)
        scenario2 = self.s.value("FLO-2D/scenario2")
        self.scenario2_le.setText(scenario2)
        scenario3 = self.s.value("FLO-2D/scenario3")
        self.scenario3_le.setText(scenario3)
        scenario4 = self.s.value("FLO-2D/scenario4")
        self.scenario4_le.setText(scenario4)
        scenario5 = self.s.value("FLO-2D/scenario5")
        self.scenario5_le.setText(scenario5)

    def select_scenario(self, scenario_n):
        """
        Function to select the scenario using the QToolButton
        """
        project_dir = self.s.value("FLO-2D/lastGdsDir")
        outdir = QFileDialog.getExistingDirectory(
            None,
            "Select scenario directory",
            directory=project_dir,
        )
        if outdir:
            if scenario_n == 1:
                self.scenario1_le.setText(outdir)
            if scenario_n == 2:
                self.scenario2_le.setText(outdir)
            if scenario_n == 3:
                self.scenario3_le.setText(outdir)
            if scenario_n == 4:
                self.scenario4_le.setText(outdir)
            if scenario_n == 5:
                self.scenario5_le.setText(outdir)

            self.uc.bar_info("Scenario saved!")
            self.uc.log_info("Scenario saved!")

    def save_scenarios(self):
        """
        Function to save the scenarios to the QGIS settings
        """
        use_prs = self.use_scenarios_grpbox.isChecked()
        self.s.setValue("FLO-2D/use_prs", use_prs)

        scenario1 = self.scenario1_le.text()
        scenario2 = self.scenario2_le.text()
        scenario3 = self.scenario3_le.text()
        scenario4 = self.scenario4_le.text()
        scenario5 = self.scenario5_le.text()

        self.s.setValue("FLO-2D/scenario1", scenario1)
        self.s.setValue("FLO-2D/scenario2", scenario2)
        self.s.setValue("FLO-2D/scenario3", scenario3)
        self.s.setValue("FLO-2D/scenario4", scenario4)
        self.s.setValue("FLO-2D/scenario5", scenario5)

        self.uc.bar_info("Scenarios saved!")
        self.uc.log_info("Scenarios saved!")

        self.close()

    def close_dlg(self):
        """
        Function to close the dialog
        """
        self.close()
