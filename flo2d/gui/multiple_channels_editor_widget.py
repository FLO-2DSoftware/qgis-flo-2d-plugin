#  -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..gui.dlg_individual_multiple_channels import IndividualMultipleChannelsDialog
from ..utils import float_or_zero, int_or_zero

uiDialog, qtBaseClass = load_ui("multiple_channels_editor")


class MultipleChannelsEditorWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.con = None
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.grid_lyr = None

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            self.individual_multiple_channels_data_btn.clicked.connect(self.show_individual_multiple_channels_dialog)

            self.populate_multiple_channels_widget()

            self.mc_incremental_dbox.valueChanged.connect(self.update_global_multiple_channels_data)
            self.mc_width_dbox.valueChanged.connect(self.update_global_multiple_channels_data)
            self.mc_depth_dbox.valueChanged.connect(self.update_global_multiple_channels_data)
            self.mc_number_sbox.valueChanged.connect(self.update_global_multiple_channels_data)
            self.mc_manning_dbox.valueChanged.connect(self.update_global_multiple_channels_data)
            self.mc_min_slope_dbox.valueChanged.connect(self.update_global_multiple_channels_data)
            self.mc_max_slope_dbox.valueChanged.connect(self.update_global_multiple_channels_data)
            self.mc_d50_dbox.valueChanged.connect(self.update_global_multiple_channels_data)

    #             self.initial_breach_width_depth_ratio_dbox.valueChanged.connect(self.update_general_breach_data)
    #             self.weir_coefficient_dbox.editingFinished.connect(self.update_general_breach_data)
    #             self.time_to_initial_failure_dbox.valueChanged.connect(self.update_general_breach_data)

    def populate_multiple_channels_widget(self):
        qry = "SELECT wmc, wdrall, dmall, nodchansall, xnmultall, sslopemin, sslopemax, avuld50 FROM mult"

        row = self.gutils.execute(qry).fetchone()
        if not row:
            return

        self.mc_incremental_dbox.setValue(float_or_zero(row[0]))
        self.mc_width_dbox.setValue(float_or_zero(row[1]))
        self.mc_depth_dbox.setValue(float_or_zero(row[2]))
        self.mc_number_sbox.setValue(int_or_zero(row[3]))
        self.mc_manning_dbox.setValue(float_or_zero(row[4]))
        self.mc_min_slope_dbox.setValue(float_or_zero(row[5]))
        self.mc_max_slope_dbox.setValue(float_or_zero(row[6]))
        self.mc_d50_dbox.setValue(float_or_zero(row[7]))

    def update_global_multiple_channels_data(self):
        self.fill_global_multiple_channels_with_defauts_if_empty()
        qry = """UPDATE mult SET wmc = ?, wdrall = ?, dmall = ?, nodchansall = ?, xnmultall = ?, sslopemin = ?, sslopemax = ?, avuld50 = ?; """

        wmc = self.mc_incremental_dbox.value()
        wdrall = self.mc_width_dbox.value()
        dmall = self.mc_depth_dbox.value()
        nodchansall = self.mc_number_sbox.value()
        xnmultall = self.mc_manning_dbox.value()
        sslopemin = self.mc_min_slope_dbox.value()
        sslopemax = self.mc_max_slope_dbox.value()
        avuld50 = self.mc_d50_dbox.value()

        self.gutils.execute(qry, (wmc, wdrall, dmall, nodchansall, xnmultall, sslopemin, sslopemax, avuld50))

    def show_individual_multiple_channels_dialog(self):
        """
        Shows individual multiple channels dialog.

        """
        if self.gutils.is_table_empty("mult_cells"):
            self.uc.bar_warn("There are no Multiple Channel Cells defined!.")
            return

        dlg_individual_multiple_channels = IndividualMultipleChannelsDialog(self.iface, self.lyrs)
        save = dlg_individual_multiple_channels.exec_()
        if save:
            try:
                if dlg_individual_multiple_channels.save_individual_multiple_chennels_data():
                    self.uc.bar_info("Individual Multiple Channels Data saved.")
                else:
                    self.uc.bar_info("Saving of Individual Multiple Channels Data failed!.")
            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error(
                    "ERROR 100219.0646: assignment of Individual Multiple Channels Data failed!"
                    + "\n__________________________________________________",
                    e,
                )

    def fill_global_multiple_channels_with_defauts_if_empty(self):
        if self.gutils.is_table_empty("mult"):
            sql = """INSERT INTO mult DEFAULT VALUES;"""
            self.gutils.execute(
                sql,
            )


#     def update_levee_failure_mode(self):
#         self.fill_levee_general_with_defauts_if_empty()
#         qry = '''UPDATE levee_general SET ilevfail = ?;'''
#         value = 0 if self.no_failure_radio.isChecked() else 1 if self.prescribed_failure_radio.isChecked() else 2 if self.breach_failure_radio.isChecked() else 0
#         self.gutils.execute(qry, (value,))
#
#     def update_crest_increment(self):
#         self.fill_levee_general_with_defauts_if_empty()
#         qry = '''UPDATE levee_general SET raiselev = ?;'''
#         value = self.crest_increment_dbox.value()
#         self.gutils.execute(qry, (value,))
#
#     def fill_breach_global_with_defauts_if_empty(self):
#          if self.gutils.is_table_empty('breach_global'):
#             sql = '''INSERT INTO breach_global DEFAULT VALUES;'''
#             self.gutils.execute(sql,)
#
#
#
#     def update_general_breach_data(self):
#         self.fill_breach_global_with_defauts_if_empty()
#         qry = '''UPDATE breach_global SET ibreachsedeqn = ?,  gbratio = ?, gweircoef = ?, gbreachtime = ?; '''
#         equation = self.transport_eq_cbo.currentIndex() + 1
#         ratio = self.initial_breach_width_depth_ratio_dbox.value()
#         weird = self.weir_coefficient_dbox.value()
#         time = self.time_to_initial_failure_dbox.value()
#         self.gutils.execute(qry, (equation, ratio, weird, time))
#
#
#     def update_transport_eq(self):
#         self.fill_breach_global_with_defauts_if_empty()
#         qry = '''UPDATE breach_global SET ibreachsedeqn = ?;'''
#         value = self.transport_eq_cbo.currentIndex() + 1
#         self.gutils.execute(qry, (value,))
#
#     def update_initial_breach_width_depth_ratio(self):
#         self.fill_breach_global_with_defauts_if_empty()
#         qry = '''UPDATE breach_global SET gbratio = ?;'''
#         value = self.initial_breach_width_depth_ratio_dbox.value()
#         self.gutils.execute(qry, (value,))
#
#     def update_weird_coefficient(self):
#         self.fill_breach_global_with_defauts_if_empty()
#         qry = '''UPDATE breach_global SET gweircoef = ?;'''
#         value = self.weir_coefficient_dbox.value()
#         self.gutils.execute(qry, (value,))
#
#     def update_time_to_initial_failure(self):
#         self.fill_breach_global_with_defauts_if_empty()
#         qry = '''UPDATE breach_global SET gbreachtime = ?;'''
#         value = self.time_to_initial_failure_dbox.value()
#         self.gutils.execute(qry, (value,))
