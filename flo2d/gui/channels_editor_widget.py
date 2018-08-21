#  -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

from ..gui.dlg_channel_geometry import ChannelGeometryDialog

uiDialog, qtBaseClass = load_ui('channels_editor')


class ChannelsEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.con = None
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.grid_lyr = None

    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

            self.initial_flow_for_all_dbox.valueChanged.connect(self.update_initial_flow_for_all)
            self.max_froude_number_dbox.valueChanged.connect(self.update_froude)
            self.roughness_adjust_coeff_dbox.valueChanged.connect(self.update_roughness)
            self.transport_eq_cbo.currentIndexChanged.connect(self.update_transport_eq)
            self.initial_flow_elements_grp.toggled.connect(self.fill_starting_and_ending_water_elevations)
            self.view_channel_geometry_btn.clicked.connect(self.show_channel_segments_dialog)
            self.channel_segment_cbo.currentIndexChanged.connect(self.show_channel_segment_dependencies)
            self.first_element_box.valueChanged.connect(self.update_first)
            self.starting_water_elev_dbox.valueChanged.connect(self.update_starting)
            self.last_element_box.valueChanged.connect(self.update_last)
            self.ending_water_elev_dbox.valueChanged.connect(self.update_ending)

            self.populate_channels_widget()

    def populate_channels_widget(self):
        qry_chan = '''SELECT fid, name, depinitial, froudc, roughadj, isedn FROM chan ORDER BY fid;'''
        rows_chan = self.gutils.execute(qry_chan).fetchall()
        if not rows_chan:
            return
        self.channel_segment_cbo.clear()
        for row in rows_chan:
            self.channel_segment_cbo.addItem(str(row[1]))
            if row[0] == 1:
                self.roughness_adjust_coeff_dbox.setValue(row[4])
                self.max_froude_number_dbox.setValue(row[3])
                equation = row[5]-1 if row[5] is not None else 0
                self.transport_eq_cbo.setCurrentIndex(equation)

        qry_chan_wsel = 'SELECT seg_fid, istart, wselstart, iend, wselend FROM chan_wsel'
        rows_chan_wsel = self.gutils.execute(qry_chan_wsel).fetchall()
        if not rows_chan_wsel:
            return
        for row in rows_chan_wsel:
            if row[0] == 1:
                self.initial_flow_elements_grp.setChecked(True)
                self.first_element_box.setValue(row[1])
                self.starting_water_elev_dbox.setValue(row[2])
                self.last_element_box.setValue(row[3])
                self.ending_water_elev_dbox.setValue(row[4])
                break

        self.uc.bar_warn('Schematized Channel Editor populated!.')

    def show_channel_segment_dependencies(self):
        if self.gutils.is_table_empty('chan'):
            self.uc.bar_warn('Schematized Channel Segments (left bank) Layer is empty!.')
            return

        idx = self.channel_segment_cbo.currentIndex() + 1

        qry_wsel = '''SELECT istart, wselstart, iend, wselend FROM chan_wsel WHERE seg_fid = ?;'''
        data_wsel = self.gutils.execute(qry_wsel, (idx,)).fetchone()
        if data_wsel is None:
            self.initial_flow_elements_grp.setChecked(False)
        else:
            # Set fields:
            self.first_element_box.setValue(data_wsel[0])
            self.starting_water_elev_dbox.setValue(data_wsel[1]),
            self.last_element_box.setValue(data_wsel[2]),
            self.ending_water_elev_dbox.setValue(data_wsel[3])
            self.initial_flow_elements_grp.setChecked(True)

        qry_chan = '''SELECT isedn, depinitial, froudc, roughadj, isedn FROM chan WHERE fid = ?;'''
        data_chan = self.gutils.execute(qry_chan, (idx,)).fetchone()
        self.initial_flow_for_all_dbox.setValue(data_chan[1])
        self.max_froude_number_dbox.setValue(data_chan[2])
        self.roughness_adjust_coeff_dbox.setValue(data_chan[3])
        equation = data_chan[4]-1  if data_chan[4] is not None else 0
        self.transport_eq_cbo.setCurrentIndex(equation)

    def show_channel_segments_dialog(self):
        """
        Shows channel segments dialog.

        """
        # See if there are channels:
        if self.gutils.is_table_empty('chan'):
            self.uc.bar_warn('Schematized Channel Segments (left bank) Layer is empty!.')
            return

        dlg_channels = ChannelGeometryDialog(self.iface, self.lyrs)
        close = dlg_channels.exec_()
        # if close:
        #     try:
        #         self.uc.bar_info('Channel data saved!', dur=3)
        #     except Exception as e:
        #         self.uc.bar_warn('Could not save Channels data! Please check it')
        #         return

    def fill_starting_and_ending_water_elevations(self):
        sql_in = '''INSERT INTO chan_wsel (seg_fid, istart, wselstart, iend, wselend) VALUES (?,?,?,?,?);'''
        sql_out= '''DELETE from chan_wsel WHERE seg_fid = ?;'''
        idx = self.channel_segment_cbo.currentIndex() + 1
        if self.initial_flow_elements_grp.isChecked():
            self.initial_flow_for_all_dbox.setEnabled(False)
            self.gutils.execute(sql_in, (idx,
                                      self.first_element_box.value(),
                                      self.starting_water_elev_dbox.value(),
                                      self.last_element_box.value(),
                                      self.ending_water_elev_dbox.value()
                                     )
                                )
        else:
            self.initial_flow_for_all_dbox.setEnabled(True)
            self.gutils.execute(sql_out, (idx,))

    def update_transport_eq(self):
        qry = '''UPDATE chan SET isedn = ? WHERE fid = ?;'''
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.transport_eq_cbo.currentIndex() + 1
        self.gutils.execute(qry, (value, idx))

    def update_initial_flow_for_all(self):
        qry = '''UPDATE chan SET depinitial = ? WHERE fid = ?;'''
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.initial_flow_for_all_dbox.value()
        self.gutils.execute(qry, (value, idx))

    def update_froude(self):
        qry = '''UPDATE chan SET froudc = ? WHERE fid = ?;'''
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.max_froude_number_dbox.value()
        self.gutils.execute(qry, (value, idx))

    def update_roughness(self):
        qry = '''UPDATE chan SET roughadj = ? WHERE fid = ?;'''
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.roughness_adjust_coeff_dbox.value()
        self.gutils.execute(qry, (value, idx))

    def update_first(self):
        qry = '''UPDATE chan_wsel SET istart = ? WHERE seg_fid = ?;'''
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.first_element_box.value()
        self.gutils.execute(qry, (value, idx))

    def update_last(self):
        qry = '''UPDATE chan_wsel SET iend = ? WHERE seg_fid = ?;'''
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.last_element_box.value()
        self.gutils.execute(qry, (value, idx))

    def update_starting(self):
        qry = '''UPDATE chan_wsel SET wselstart = ? WHERE seg_fid = ?;'''
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.starting_water_elev_dbox.value()
        self.gutils.execute(qry, (value, idx))

    def update_ending(self):
        qry = '''UPDATE chan_wsel SET wselend = ? WHERE seg_fid = ?;'''
        idx = self.channel_segment_cbo.currentIndex() + 1
        value = self.ending_water_elev_dbox.value()
        self.gutils.execute(qry, (value, idx))
