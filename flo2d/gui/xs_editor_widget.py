# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import traceback
import os
import sys
import subprocess
from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtGui import QStandardItem, QColor
from qgis.PyQt.QtWidgets import QInputDialog, QFileDialog, QApplication, QTableWidgetItem
from qgis.core import QgsFeatureRequest, QgsFeature, QgsGeometry
from .ui_utils import load_ui, center_canvas, try_disconnect, set_icon, switch_to_selected
from ..utils import m_fdata, is_number
from ..geopackage_utils import GeoPackageUtils
from ..flo2dobjects import UserCrossSection, ChannelSegment
from ..flo2d_tools.schematic_tools import ChannelsSchematizer, Confluences
from ..user_communication import UserCommunication
from ..gui.dlg_xsec_interpolation import XSecInterpolationDialog
from ..flo2d_tools.flopro_tools import XSECInterpolatorExecutor, ChanRightBankExecutor
from ..flo2d_ie.flo2d_parser import ParseDAT
from .table_editor_widget import StandardItemModel, StandardItem, CommandItemEdit
from .plot_widget import PlotWidget
from collections import OrderedDict
from math import isnan


uiDialog, qtBaseClass = load_ui('schematized_channels_info')


class ShematizedChannelsInfo(qtBaseClass, uiDialog):

    def __init__(self, iface):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.setupUi(self)
        self.con = self.iface.f2d['con']
        self.gutils = GeoPackageUtils(self.con, self.iface)
        self.schematized_summary_tblw.horizontalHeader().setStretchLastSection(True)
        self.populate_schematized_dialog()

    def populate_schematized_dialog(self):
        try:
            qry_chan_names = '''SELECT name FROM user_left_bank'''
            chan_names = self.gutils.execute(qry_chan_names).fetchall()

            qry_count_xs = '''SELECT COUNT(seg_fid) FROM chan_elems GROUP BY seg_fid;'''
            total_xs = self.gutils.execute(qry_count_xs).fetchall()

            qry_interpolated = '''SELECT COUNT(interpolated) FROM chan_elems WHERE interpolated = 1 GROUP BY seg_fid;'''
            interpolated_xs = self.gutils.execute(qry_interpolated).fetchall()

            self.schematized_summary_tblw.setRowCount(0)
            for row_number, name in enumerate(chan_names):
                self.schematized_summary_tblw.insertRow(row_number)
                item = QTableWidgetItem()
                n_interpolated_xs = interpolated_xs[row_number][0] if interpolated_xs else 0
                original_xs = total_xs[row_number][0] - n_interpolated_xs
                item.setData(Qt.DisplayRole, name[0] + " (" + str(original_xs) + " xsecs)")
                self.schematized_summary_tblw.setItem(row_number, 0, item)
                item = QTableWidgetItem()
                item.setData(Qt.DisplayRole, total_xs[row_number][0])
                self.schematized_summary_tblw.setItem(row_number, 1, item)
                item = QTableWidgetItem()
                item.setData(Qt.DisplayRole, str(total_xs[row_number][0]) + " (" + str(n_interpolated_xs) + " interpolated)")
                self.schematized_summary_tblw.setItem(row_number, 2, item)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 130718.0831: schematized dialog failed to show!", e)
            return


uiDialog, qtBaseClass = load_ui('xs_editor')


class XsecEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.plot = plot
        self.table = table
        self.tview = table.tview
        self.lyrs = lyrs
        self.con = None
        self.gutils = None
        self.user_xs_lyr = None
        self.xs = None
        self.cur_xs_fid = None
        self.project_dir = ''
        self.exe_dir = ''
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.setupUi(self)
        self.populate_xsec_type_cbo()
        self.xi, self.yi = [[], []]
        self.create_plot()
        self.xs_data_model = StandardItemModel()
        self.tview.setModel(self.xs_data_model)
        self.uc = UserCommunication(iface, 'FLO-2D')
        set_icon(self.digitize_btn, 'mActionCaptureLine.svg')
        set_icon(self.save_xs_changes_btn, 'mActionSaveAllEdits.svg')
        set_icon(self.delete_btn, 'mActionDeleteSelected.svg')
        set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        set_icon(self.schematize_xs_btn, 'schematize_xsec.svg')
        set_icon(self.schematize_right_bank_btn, 'schematize_right_bank.svg')
        set_icon(self.save_channel_DAT_files_btn, 'export_channels.svg')
        set_icon(self.reassign_rightbanks_btn, 'import_right_banks.svg')
        set_icon(self.import_HYCHAN_OUT_btn, 'import_channel_peaks.svg')
        set_icon(self.interpolate_xs_btn, 'interpolate_xsec.svg')
        set_icon(self.confluences_btn, 'schematize_confluence.svg')
        set_icon(self.rename_xs_btn, 'change_name.svg')
        # Connections:

        # Buttons connections:
        self.digitize_btn.clicked.connect(self.digitize_xsec)
        self.save_xs_changes_btn.clicked.connect(self.save_user_xsections_lyr_edits)
        self.revert_changes_btn.clicked.connect(self.cancel_user_lyr_edits)
        self.delete_btn.clicked.connect(self.delete_xs)
        self.schematize_xs_btn.clicked.connect(self.schematize_channels)
        self.schematize_right_bank_btn.clicked.connect(self.schematize_right_banks)
        self.save_channel_DAT_files_btn.clicked.connect(self.save_channel_DAT_files)
        self.interpolate_xs_btn.clicked.connect(self.interpolate_xs_values)
        self.reassign_rightbanks_btn.clicked.connect(self.reassign_rightbanks_from_CHANBANK_file)
        self.import_HYCHAN_OUT_btn.clicked.connect(self.import_channel_peaks_from_HYCHAN_OUT)
        # self.interpolate_xs_btn.clicked.connect(self.interpolate_xs_values_externally)
        self.confluences_btn.clicked.connect(self.schematize_confluences)
        self.rename_xs_btn.clicked.connect(self.change_xs_name)

        # More connections:
        self.xs_cbo.activated.connect(self.current_xsec_changed)
        self.xs_type_cbo.activated.connect(self.cur_xsec_type_changed)
        self.n_sbox.valueChanged.connect(self.save_n)
        self.xs_data_model.dataChanged.connect(self.save_xs_data)
        self.xs_data_model.itemDataChanged.connect(self.itemDataChangedSlot)
        self.table.before_paste.connect(self.block_saving)
        self.table.after_paste.connect(self.unblock_saving)

    def block_saving(self):
        try_disconnect(self.xs_data_model.dataChanged, self.save_xs_data)

    def unblock_saving(self):
        self.xs_data_model.dataChanged.connect(self.save_xs_data)

    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            self.user_xs_lyr = self.lyrs.data['user_xsections']['qlyr']
            self.user_xs_lyr.editingStopped.connect(self.populate_xsec_cbo)
            self.user_xs_lyr.selectionChanged.connect(self.switch2selected)

    def switch2selected(self):
        switch_to_selected(self.user_xs_lyr, self.xs_cbo, use_fid=True)
        self.current_xsec_changed(self.xs_cbo.currentIndex())

    def interp_bed_and_banks(self):
        qry = 'SELECT fid FROM chan;'
        fids = self.gutils.execute(qry).fetchall()
        for fid in fids:
            seg = ChannelSegment(int(fid[0]), self.con, self.iface)
            res, msg = seg.interpolate_bed()
            if not res:
                self.uc.log_info(msg)
                return False
        return True

    def itemDataChangedSlot(self, item, oldValue, newValue, role, save=True):
        """
        Slot used to push changes of existing items onto undoStack.
        """
        if role == Qt.EditRole:
            command = CommandItemEdit(self, item, oldValue, newValue,
                                      "Text changed from '{0}' to '{1}'".format(oldValue, newValue))
            self.tview.undoStack.push(command)
            return True

    def populate_xsec_type_cbo(self):
        """
        Get current xsection data, populate all relevant fields of the dialog and create xsection plot.
        """
        self.xs_type_cbo.clear()
        self.xs_types = OrderedDict()

        self.xs_types['R'] = {'name': 'Rectangular', 'cbo_idx': 0}
        self.xs_types['N'] = {'name': 'Natural', 'cbo_idx': 1}
        self.xs_types['T'] = {'name': 'Trapezoidal', 'cbo_idx': 2}
        self.xs_types['V'] = {'name': 'Variable Area', 'cbo_idx': 3}
        for typ, data in self.xs_types.items():
            self.xs_type_cbo.addItem(data['name'], typ)

    def setup_plot(self):
        self.plotWidget = PlotWidget()
        self.plotLayout.addWidget(self.plotWidget)

    def populate_xsec_cbo(self, fid=None, show_last_edited=False):
        """
        Populate xsection combo.
        """
        self.xs_cbo.clear()
        self.xs_type_cbo.setCurrentIndex(1)
        qry = 'SELECT fid, name FROM user_xsections ORDER BY fid COLLATE NOCASE;'
        rows = self.gutils.execute(qry).fetchall()
        if not rows:
            return
        cur_idx = 0 # Pointer to selected item in combo. See below. Depending on call of method,
                    # it could be the first, the last, or a given one.
        for i, row in enumerate(rows): # Cycles over pair (fid, name) of all user_xsections.
            row = [x if x is not None else '' for x in row]
            row_fid, name = row
            self.xs_cbo.addItem(name, str(row_fid))
            if fid:
                if row_fid == int(fid):
                    cur_idx = i
        if show_last_edited:
            cur_idx = i
        self.xs_cbo.setCurrentIndex(cur_idx)
        self.enable_widgets(False)
        if self.xs_cbo.count():
            self.enable_widgets()
            self.current_xsec_changed(cur_idx)

    def digitize_xsec(self, i):
        def_attr_exp = self.lyrs.data['user_xsections']['attrs_defaults']
        if not self.lyrs.enter_edit_mode('user_xsections', def_attr_exp):
            return
        self.enable_widgets(False)

    def enable_widgets(self, enable=True):
        self.xs_cbo.setEnabled(enable)
        self.rename_xs_btn.setEnabled(enable)
        self.xs_type_cbo.setEnabled(enable)
        self.xs_center_chbox.setEnabled(enable)
        self.n_sbox.setEnabled(enable)

    def cancel_user_lyr_edits(self, i):
        user_lyr_edited = self.lyrs.rollback_lyrs_edits('user_xsections')
        if user_lyr_edited:
            self.populate_xsec_cbo()

    def save_user_xsections_lyr_edits(self, i):
        if not self.gutils or not self.lyrs.any_lyr_in_edit('user_xsections'):
            return
        # try to save user bc layers (geometry additions/changes)
        user_lyr_edited = self.lyrs.save_lyrs_edits('user_xsections')  # Saves all user cross sections created in this opportunity into 'user_xsections'.
        # if user bc layers were edited
        # self.enable_widgets()
        if user_lyr_edited:
            self.gutils.fill_empty_user_xsec_names() # Sometimes (to be determined) the 'name' column of 'user_xsections' is not assigned. This does.
            self.gutils.set_def_n() # Assigns the default manning (from global MANNING) or 0.035 (at the time of writing this comment)
            self.populate_xsec_cbo(show_last_edited=True)
            # for i in range(self.xs_cbo.count()):
            #     self.current_xsec_changed(i)

    def repaint_xs(self):
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data['user_xsections']['qlyr']
        ]
        self.lyrs.repaint_layers()

    def current_xsec_changed(self, idx=0):
        """
        User changed current xsection in the xsections list.
        Populate xsection data fields and update the plot.
        """
        if not self.xs_cbo.count():
            return

        fid = self.xs_cbo.itemData(idx)
        self.xs = UserCrossSection(fid, self.con, self.iface)
        row = self.xs.get_row()
        self.lyrs.clear_rubber()
        if self.xs_center_chbox.isChecked():
            self.lyrs.show_feat_rubber(self.user_xs_lyr.id(), int(fid))
            feat = next(self.user_xs_lyr.getFeatures(QgsFeatureRequest(int(self.xs.fid))))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
        typ = row['type']
        fcn = float(row['fcn']) if is_number(row['fcn']) else float(self.gutils.get_cont_par('MANNING'))
        self.xs_type_cbo.setCurrentIndex(self.xs_types[typ]['cbo_idx'])
        self.n_sbox.setValue(fcn)
        chan_x_row = self.xs.get_chan_x_row()
        if typ == 'N':
            xy = self.xs.get_chan_natural_data()
        else:
            xy = None
        self.xs_data_model.clear()
        self.tview.undoStack.clear()
        if not xy:
            self.plot.clear()
            self.xs_data_model.setHorizontalHeaderLabels(['Value'])
            for val in chan_x_row.values():
                item = StandardItem(str(val))
                self.xs_data_model.appendRow(item)
            self.xs_data_model.setVerticalHeaderLabels(list(chan_x_row.keys()))
            self.xs_data_model.removeRows(0,2)
            self.tview.setModel(self.xs_data_model)
        else:
            self.xs_data_model.setHorizontalHeaderLabels(['Station', 'Elevation'])
            for i, pt in enumerate(xy):
                x, y = pt
                xi = QStandardItem(str(x))
                yi = QStandardItem(str(y))
                self.xs_data_model.appendRow([xi, yi])
            self.tview.setModel(self.xs_data_model)
            rc = self.xs_data_model.rowCount()
            if rc < 500:
                for row in range(rc, 500 + 1):
                    items = [StandardItem(x) for x in ('',) * 2]
                    self.xs_data_model.appendRow(items)
        for i in range(self.xs_data_model.rowCount()):
            self.tview.setRowHeight(i, 20)
        self.tview.horizontalHeader().setStretchLastSection(True)
        for i in range(2):
            self.tview.setColumnWidth(i, 100)

        if self.xs_type_cbo.currentText() == 'Natural':
            self.create_plot()
            self.update_plot()

        # highlight_selected_xsection_b(self.lyrs.data['user_xsections']['qlyr'], self.xs_cbo.currentIndex()+1)

    def cur_xsec_type_changed(self, idx):
        if not self.xs_cbo.count():
            return
        typ = self.xs_type_cbo.itemData(idx)
        self.xs.set_type(typ)
        xs_cbo_idx = self.xs_cbo.currentIndex()
        self.current_xsec_changed(xs_cbo_idx)

    def create_plot(self):
        """
        Create initial plot.
        """
        self.plot.clear()
        self.plot.add_item('Cross-section', [self.xi, self.yi], col=QColor("#0018d4"))

    def update_plot(self):
        """
        When time series data for plot change, update the plot.
        """
        self.xi, self.yi = [[], []]
        for i in range(self.xs_data_model.rowCount()):
            self.xi.append(m_fdata(self.xs_data_model, i, 0))
            self.yi.append(m_fdata(self.xs_data_model, i, 1))
        self.plot.update_item('Cross-section', [self.xi, self.yi])

    def save_n(self, n_val):
        if not self.xs_cbo.count():
            return
        self.xs.set_n(n_val)

    def change_xs_name(self, i):
        if not self.xs_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, 'Change name', 'New name:')
        if not ok or not new_name:
            return
        if not self.xs_cbo.findText(new_name) == -1:
            msg = 'Boundary condition with name {} already exists in the database. Please, choose another name.'.format(
                new_name)
            self.uc.show_warn(msg)
            return
        self.xs.name = new_name
        self.xs.set_name()
        self.populate_xsec_cbo(fid=self.xs.fid)

    def save_xs_data(self):
        if self.xs.type == 'N':
            xiyi = []
            for i in range(self.xs_data_model.rowCount()):
                # save only rows with a number in the first column
                if is_number(m_fdata(self.xs_data_model, i, 0)) and not isnan(m_fdata(self.xs_data_model, i, 0)):
                    xiyi.append(
                        (
                            self.xs.fid,
                            m_fdata(self.xs_data_model, i, 0),
                            m_fdata(self.xs_data_model, i, 1)
                        )
                    )
            self.xs.set_chan_natural_data(xiyi)
            self.update_plot()
        else:
            # parametric xsection
            data = []
            for i in range(self.xs_data_model.rowCount()):
                data.append(
                        (
                            m_fdata(self.xs_data_model, i, 0)
                        )
                    )
            self.xs.set_chan_data(data)

    def delete_xs(self, i):
        """
        Delete the current cross-section from user layer.
        """
        if not self.xs_cbo.count():
            return
        q = 'Are you sure, you want to delete current cross-section?'
        if not self.uc.question(q):
            return
        fid = None
        xs_idx = self.xs_cbo.currentIndex()
        cur_data = self.xs_cbo.itemData(xs_idx)
        if cur_data:
            fid = int(cur_data[0])
        else:
            return
        qry = '''DELETE FROM user_xsections WHERE fid = ?;'''
        self.gutils.execute(qry, (fid,))

        # try to set current xs to the last before the deleted one
        try:
            self.populate_xsec_cbo(fid=fid-1)
        except Exception as e:
            self.populate_xsec_cbo()
        self.repaint_xs()

    def schematize_channels(self):
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return
        if self.gutils.is_table_empty('user_left_bank'):
            if not self.gutils.is_table_empty('chan'):
                if not self.uc.question('There are no user left bank lines.\n\n' +
                                        'But there are schematized left banks and cross sections.\n' +
                                        'Would you like to delete them?'):
                    return
                else:
                    if self.uc.question('Are you sure you want to delete all channel data?'):
                        self.gutils.clear_tables('user_left_bank', 'user_right_bank', 'user_xsections',
                                                 'chan', 'rbank', 'chan_elems', 'chan_r', 'chan_v', 'chan_t', 'chan_n',
                                                 'chan_confluences', 'user_noexchange_chan_areas', 'noexchange_chan_cells', 'chan_wsel')
                    return
            else:
                self.uc.bar_warn('There are no User Left Bank lines! Please digitize them before running the tool.')
                return
        if self.gutils.is_table_empty('user_xsections'):
            self.uc.bar_warn('There are no User Cross Sections! Please digitize them before running the tool.')
            return
        if not self.gutils.is_table_empty('chan'):
            if not self.uc.question('There are already Schematised Channel Segments (Left Banks) and Cross Sections. Overwrite them?'):
                return

        # Get an instance of the ChannelsSchematizer class:
        cs = ChannelsSchematizer(self.con, self.iface, self.lyrs)

        # Create the Schematized Left Bank (Channel Segments), joining cells intersecting
        # the User Left Bank Line, with arrows from one cell centroid to the next:
        try:
            cs.create_schematized_channel_segments_aka_left_banks()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error('Schematizing left bank lines failed !\n'
                              'Please check your User Layers.\n\n'
                              'Check that:\n\n'
                              '   * For each User Left Bank line, the first cross section is\n'
                              '     defined starting in the first grid cell.\n\n'
                              '   * Each User Left Bank line has at least 2 cross sections\n'
                              '     crossing it.\n\n'
                              '   * All cross sections associated to a User Left Bank line\n'
                              '     intersects (crossover) it.'
                              '\n_________________________________________________', e)
            return

        # Create the Schematized Cross sections layer, with lines from schematized left bank cells.
        try:
            cs.create_schematized_xsections()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn('Schematizing failed while creating cross-sections! '
                              'Please check your User Layers.')
            return

        try:
            cs.copy_features_from_user_channel_layer_to_schematized_channel_layer()
            cs.copy_features_from_user_xsections_layer_to_schematized_xsections_layer()

#             cs.create_xs_type_n_r_t_v_tables()
#             cs.create_schematized_rbank_lines_from_xs_tips()

            self.gutils.create_xs_type_n_r_t_v_tables()
            self.gutils.create_schematized_rbank_lines_from_xs_tips()

            cs.copy_user_xs_data_to_schem()

        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn('Schematizing failed while processing attributes! '
                              'Please check your User Layers.')
            return

        if not self.gutils.is_table_empty('chan_elems'):
            try:
                cs.make_distance_table()
            except Exception as e:
                self.uc.log_info(traceback.format_exc())
                self.uc.show_warn('Schematizing failed while preparing interpolation table!\n\n'
                                  'Please check your User Layers.')
                return
        else:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn('Schematizing failed while preparing interpolation table!\n\n'
                              'Schematic Channel Cross Sections layer is empty!')
            return

        chan_schem = self.lyrs.data['chan']['qlyr']
        chan_elems = self.lyrs.data['chan_elems']['qlyr']
        rbank = self.lyrs.data['rbank']['qlyr']
        confluences = self.lyrs.data['chan_confluences']['qlyr']
        self.lyrs.lyrs_to_repaint = [chan_schem, chan_elems, rbank, confluences]
        self.lyrs.repaint_layers()
        idx = self.xs_cbo.currentIndex()
        self.current_xsec_changed(idx)
        # self.uc.show_info('Left Banks, Right Banks, and Cross Sections schematized!')
#
        info = ShematizedChannelsInfo(self.iface)
        close = info.exec_()

    def schematize_right_banks(self):
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return
        if self.gutils.is_table_empty('user_right_bank'):
            self.uc.bar_warn('There are no User Right Bank lines! Please digitize them before running the tool.')
            return

        # Get an instance of the ChannelsSchematizer class:
        cs = ChannelsSchematizer(self.con, self.iface, self.lyrs)

        # Create the Schematized Right Bank, joining cells intersecting
        # the User Right Bank Line, with arrows from one cell centroid to the next:
        try:
            cs.create_schematized_rbank_lines_from_user_rbanks_banks()

            if self.uc.question("Would you like to join left banks with right banks?"):
                # chan_schem = self.lyrs.data['chan']['qlyr']
                # rbank_schem = self.lyrs.data['rbank']['qlyr']

                pairs = [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7)]
                for xs_seg_fid, right_bank_fid in pairs:
                    self.reassign_xs_rightbanks_grid_id_from_schematized_rbanks(xs_seg_fid, right_bank_fid)

            self.gutils.create_schematized_rbank_lines_from_xs_tips()
            rbank = self.lyrs.data['rbank']['qlyr']
            rbank.updateExtents()
            rbank.triggerRepaint()
            rbank.removeSelection()

        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error('ERROR 280718.1054: Schematizing right bank lines failed !', e)
            return

        rbank = self.lyrs.data['rbank']['qlyr']
        self.lyrs.lyrs_to_repaint = [rbank]
        self.lyrs.repaint_layers()

    def save_channel_DAT_files(self):
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return
        if self.gutils.is_table_empty('user_left_bank'):
            self.uc.bar_warn('There are no User left Bank Lines! Please digitize them before running the tool.')
            return
        if self.gutils.is_table_empty('user_xsections'):
            self.uc.bar_warn('There are no User Cross Sections! Please digitize them before running the tool.')
            return
        if self.gutils.is_table_empty('chan'):
            self.uc.bar_warn('There are no Schematized Channel Segments (Left Banks)')
            return
        if self.gutils.is_table_empty('chan'):
            self.uc.bar_warn('There are no Schematized Channel Cross Sections')
            return

        xs_survey = self.save_chan_dot_dat_with_zero_natural_cross_sections()
        if xs_survey:
            if self.save_xsec_dot_dat_with_only_user_cross_sections():
                if self.run_INTERPOLATE(xs_survey) == 0:
                    s = QSettings()
                    outdir = s.value('FLO-2D/lastGdsDir', '')
                    q = 'Cross sections interpolation performed!.\n\n'
                    q += '(in Directory: ' + outdir + ")\n\n"
                    q += 'CHAN.DAT and XSEC.DAT updated with the interpolated cross section data.\n\n'
                    q += 'Would you like to run the CHANNRIGHTBANK.EXE program to identify the right bank cells?\n\n'
                    q += '(It requires the CHAN.DAT, XSEC.DAT, and TOPO.DAT files)'
                    if self.uc.question(q):
                        self.run_CHANRIGHTBANK()

        QApplication.restoreOverrideCursor()

    def save_chan_dot_dat_with_zero_natural_cross_sections(self):
        # check if there are any channels defined
        if self.gutils.is_table_empty('chan'):
            return []
        chan_sql = '''SELECT fid, depinitial, froudc, roughadj, isedn FROM chan ORDER BY fid;'''
        chan_elems_sql = '''SELECT fid, rbankgrid, fcn, xlen, type, user_xs_fid FROM chan_elems WHERE seg_fid = ? ORDER BY nr_in_seg;'''

        chan_r_sql = '''SELECT elem_fid, bankell, bankelr, fcw, fcd FROM chan_r WHERE elem_fid = ?;'''
        chan_v_sql = '''SELECT elem_fid, bankell, bankelr, fcd, a1, a2, b1, b2, c1, c2,
                               excdep, a11, a22, b11, b22, c11, c22 FROM chan_v WHERE elem_fid = ?;'''
        chan_t_sql = '''SELECT elem_fid, bankell, bankelr, fcw, fcd, zl, zr FROM chan_t WHERE elem_fid = ?;'''
        chan_n_sql = '''SELECT elem_fid, nxsecnum FROM chan_n WHERE elem_fid = ?;'''

        chan_wsel_sql = '''SELECT istart, wselstart, iend, wselend FROM chan_wsel ORDER BY fid;'''
        chan_conf_sql = '''SELECT chan_elem_fid FROM chan_confluences ORDER BY fid;'''
        chan_e_sql = '''SELECT grid_fid FROM noexchange_chan_cells ORDER BY fid;'''

        segment = '   {0:.2f}   {1:.2f}   {2:.2f}   {3}\n'
        chan_r = 'R' + '  {}' * 7 + '\n'
        chan_v = 'V' + '  {}' * 19 + '\n'
        chan_t = 'T' + '  {}' * 9 + '\n'
        chan_n = 'N' + '  {}' * 4 + '\n'
        chanbank = ' {0: <10} {1}\n'
        wsel = '{0} {1:.2f}\n'
        conf = ' C {0}  {1}\n'
        chan_e = ' E {0}\n'

        sqls = {
            'R': [chan_r_sql, chan_r, 3, 6],
            'V': [chan_v_sql, chan_v, 3, 5],
            'T': [chan_t_sql, chan_t, 3, 6],
            'N': [chan_n_sql, chan_n, 1, 2]
        }

        chan_rows = self.gutils.execute(chan_sql).fetchall()
        if not chan_rows:
            return []
        else:
            pass

        s = QSettings()
        last_dir = s.value('FLO-2D/lastGdsDir', '')
        outdir = QFileDialog.getExistingDirectory(None,
                                    'Select directory where CHAN.DAT and XSEC.DAT files will be exported',
                                    directory=last_dir)
        if outdir:
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                s.setValue('FLO-2D/lastGdsDir', outdir)
                chan = os.path.join(outdir, 'CHAN.DAT')

                with open(chan, 'w') as c:
                    surveyed = 0
                    non_surveyed = 0
                    for row in chan_rows:
                        row = [x if x is not None else '0' for x in row]
                        fid = row[0]
                        c.write(segment.format(*row[1:5]))  # Writes depinitial, froudc, roughadj, isedn from 'chan' table (schematic layer).
                                                            # A single line for each channel segment. The next lines will be the grid elements of
                                                            # this channel segment.
                        previous_xs = -999
                        for elems in self.gutils.execute(chan_elems_sql, (fid,)):  # each 'elems' is a list [(fid, rbankgrid, fcn, xlen, type)] from
                                                                            # 'chan_elems' table (the cross sections in the schematic layer),
                                                                            #  that has the 'fid' value indicated (the channel segment id).

                            elems = [x if x is not None else '' for x in elems] # If 'elems' has a None in any of above values of list, replace it by ''
                            eid, rbank, fcn, xlen, typ, user_xs_fid  = elems  # Separates values of list into individual variables.
                            sql, line, fcn_idx, xlen_idx = sqls[typ]    # depending on 'typ' (R,V,T, or N) select sql (the SQLite SELECT statement to execute),
                                                                        # line (format to write), fcn_idx (?), and xlen_idx (?)
                            res = [x if x is not None else '' for x in self.gutils.execute(sql, (eid,)).fetchone()]    # 'res' is a list of values depending on 'typ' (R,V,T, or N).

                            if typ == "N":
                                res.insert(1, fcn)    # Add 'fcn' (comming from table ´chan_elems' (cross sections) to 'res' list) in position 'fcn_idx'.
                                res.insert(2, xlen)  # Add ´xlen' (comming from table ´chan_elems' (cross sections) to 'res' list in position 'xlen_idx'.
                                if user_xs_fid == previous_xs:
                                    res.insert(3, 0)
                                    non_surveyed += 1
                                else:
                                    res.insert(3, user_xs_fid)
                                    surveyed += 1
                                    previous_xs = user_xs_fid
                            else:
                                res.insert(fcn_idx, fcn)    # Add 'fcn' (comming from table ´chan_elems' (cross sections) to 'res' list) in position 'fcn_idx'.
                                res.insert(xlen_idx, xlen)  # Add ´xlen' (comming from table ´chan_elems' (cross sections) to 'res' list in position 'xlen_idx'.

                            c.write(line.format(*res))

                    # # Write starting water elevations:
                    # # Pairs (fist cell, water elevation) followed by (end cell, water elevation).
                    # if not self.gutils.is_table_empty('chan_wsel'):
                    #     for row in self.execute(chan_wsel_sql):
                    #         c.write(wsel.format(*row[:2]))
                    #         c.write(wsel.format(*row[2:]))
                    #
                    # # Write channel confluences.
                    # if not self.gutils.is_table_empty('chan_confluences'):
                    #     pairs = []
                    #     for row in self.gutils.execute(chan_conf_sql):
                    #         chan_elem = row[0]
                    #         if not pairs:
                    #             pairs.append(chan_elem)
                    #         else:
                    #             pairs.append(chan_elem)
                    #             c.write(conf.format(*pairs))
                    #             del pairs[:]
                    #
                    # # Write no-exchange cells.
                    # if not self.gutils.is_table_empty('noexchange_chan_cells'):
                    #     for row in self.gutils.execute(chan_e_sql):
                    #         c.write(chan_e.format(row[0]))

                self.uc.bar_info('CHAN.DAT file exported to ' + outdir, dur = 5)
                QApplication.restoreOverrideCursor()
                return [surveyed, non_surveyed]

            except Exception as e:
                self.uc.log_info(traceback.format_exc())
                QApplication.restoreOverrideCursor()
                self.uc.show_warn('Saving file CHAN.DAT failed!\n\n'  + repr(e))
                return []
        else:
            return []

    def save_xsec_dot_dat_with_only_user_cross_sections(self):
        chan_n_sql = '''SELECT user_xs_fid, nxsecnum, xsecname FROM user_chan_n ORDER BY nxsecnum;'''
        xsec_sql = '''SELECT xi, yi FROM user_xsec_n_data WHERE chan_n_nxsecnum = ? ORDER BY fid;'''

        user_xsections_sql = '''SELECT fid, name FROM user_xsections ORDER BY fid;'''

        xsec_line = '''X     {0}  {1}\n'''
        pkt_line = ''' {0:<10} {1: >10}\n'''
        nr = '{0:.2f}'

        chan_n = self.gutils.execute(chan_n_sql).fetchall()
        if not chan_n:
            return False
        else:
            pass

        user_xsections = self.gutils.execute(user_xsections_sql).fetchall()
        if not user_xsections:
            return False
        else:
            pass

        s = QSettings()
        outdir = s.value('FLO-2D/lastGdsDir', '')
        if outdir:
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                s.setValue('FLO-2D/lastGdsDir', outdir)
                xsec = os.path.join(outdir, 'XSEC.DAT')
                with open(xsec, 'w') as x:
                    for fid, name in user_xsections:
                        x.write(xsec_line.format(fid, name))
                        for xi, yi in self.gutils.execute(xsec_sql, (fid,)):
                            x.write(pkt_line.format(nr.format(xi), nr.format(yi)))
                QApplication.restoreOverrideCursor()
                self.uc.bar_info('XSEC.DAT model exported to ' + outdir, dur=5)
                return True
            except Exception as e:
                QApplication.restoreOverrideCursor()
                return False
        else:
            return False

    def run_INTERPOLATE(self, xs_survey):
        if sys.platform != 'win32':
            self.uc.bar_warn('Could not run interpolation under current operation system!')
            return -1

        try: # Show dialog to interpolate
            dlg = XSecInterpolationDialog(self.iface, xs_survey)
            ok = dlg.exec_()
            if not ok:
                return -1
        except Exception as e:
            self.uc.log_info(repr(e))
            self.uc.bar_error('ERROR 280318.0530: Cross sections interpolation dialog could not be loaded!')
            return -1

        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.exe_dir , self.project_dir = dlg.get_parameters()
            if os.path.isfile(self.exe_dir + '\INTERPOLATE.EXE'):
                interpolate = XSECInterpolatorExecutor(self.exe_dir, self.project_dir )
                return_code = interpolate.run()
                QApplication.restoreOverrideCursor()
                if return_code != 0:
                    self.uc.show_warn('Cross sections interpolation failed!\n\n' +
                                      'Program finished with return code ' + str(return_code) + '.' +
                                      '\n\nCheck content and format of CHAN.DAT and XSEC.DAT.' +
                                      '\n\n For natural cross sections:'  +
                                      '\n\n      -Cross section numbers sequence in CHAN.DAT must be consecutive.'
                                      '\n\n      -Total number of cross sections in CHAN.DAT and XSEC.DAT must be equal.'
                                      '\n\n      -Each cross section must have at least 6 station pairs (distance, elevation).'


                                      )

                return return_code
            else:
                QApplication.restoreOverrideCursor()
                self.uc.show_warn('Program INTERPOLATE.EXE is not in directory\n\n' + self.exe_dir )
                return -1
        except Exception as e:
            self.uc.log_info(repr(e))
            self.uc.bar_error('ERROR 280318.0528: Cross sections interpolation failed!')
            return -1

    def run_CHANRIGHTBANK(self):
        if sys.platform != 'win32':
            self.uc.bar_warn('Could not run CHANRIGHTBANK.EXE under current operation system!')
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if os.path.isfile(self.exe_dir + '\CHANRIGHTBANK.EXE'):
                chanrightbank = ChanRightBankExecutor(self.exe_dir, self.project_dir)
                return_code = chanrightbank.run()
                if (return_code != 0):
                    QApplication.restoreOverrideCursor()
                    self.uc.show_warn('Right bank cells selection failed!\n\n' +
                                      'Program finished with return code ' + str(return_code) + '.' +
                                      '\n\nCheck content and format of CHAN.DAT, XSEC.DAT, and TOPO.DAT files.' +
                                      '\n\nHave you assigned elevations to cells?')
                else:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_warn('Right bank cells calculated!\n\n' +
                                      'CHANBANK.DAT written as pairs (left bank cell, right bank cell)\n' +
                                      'in directory\n\n' + self.project_dir)
            else:
                QApplication.restoreOverrideCursor()
                self.uc.show_warn('Program CHANRIGHTBANK.EXE is not in directory!.\n\n' + self.exe_dir)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(repr(e))
            self.uc.bar_warn('CHANRIGHTBANK.EXE failed!')

    def interpolate_xs_values(self):
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return
        if self.gutils.is_table_empty('chan'):
            self.uc.bar_warn('There are no cross-sections! Please create them before running tool.')
            return        
        if not self.interp_bed_and_banks():
            QApplication.restoreOverrideCursor()
            self.uc.show_warn('Interpolation of cross-sections values failed! '
                              'Please check your User Layers.')
            return
        else:
            idx = self.xs_cbo.currentIndex()
            self.current_xsec_changed(idx)
            QApplication.restoreOverrideCursor()
            self.uc.show_info('Interpolation of cross-sections values finished!')

    def interpolate_xs_values_externally(self):
        os.chdir("C:/Users/Juan Jose Rodriguez/Desktop/XSEC Interpolated")
        subprocess.call("INTERPOLATE.EXE")

    def reassign_rightbanks_from_CHANBANK_file(self):
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return
        s = QSettings()
        last_dir = s.value('FLO-2D/lastGdsDir', '')
        chanbank_file, __ = QFileDialog.getOpenFileName(None, "Select CHANBANK.DAT file to read", directory=last_dir, filter='CHANBANK.DAT')
        if not chanbank_file:
            return

        s.setValue('FLO-2D/lastGdsDir', os.path.dirname(chanbank_file))

        try:
            new_feats = []
            xs_lyr = self.lyrs.data['chan_elems']['qlyr']

            # Create a dictionary of pairs (left bank cell, right bank cell) read from CHANBANK.DAT file:
            pd = ParseDAT()
            pairs = {left: right for left, right in pd.single_parser(chanbank_file)}

            # Create a list of features taken from cham_elems layer (schematized cross sections), modifying their geometry
            # by changing the point of the coordinates of the right bank cell:
            for f in xs_lyr.getFeatures():
                xs_feat = QgsFeature()
                # Copy the next complete feature of chan_elems layer.
                xs_feat = f
                left = str(f['fid'])

                # Only change the geometry of the right bank cell (if it is not null or zero):
                if left in pairs:
                    right = pairs.get(left)
                    if int(right) > 0 and right is not None and int(left) > 0 and left is not None:
                        pnt0 = self.gutils.single_centroid(left)
                        qgsPoint0 = QgsGeometry().fromWkt(pnt0).asPoint()
                        pnt1 = self.gutils.single_centroid(right)
                        qgsPoint1 = QgsGeometry().fromWkt(pnt1).asPoint()
                        new_xs = QgsGeometry.fromPolylineXY([qgsPoint0, qgsPoint1])

                        xs_feat.setGeometry(new_xs)
                        xs_feat.setAttribute('rbankgrid', right)

                new_feats.append(xs_feat)

            # Replace all features of chan_elems with the new calculated features:
            xs_lyr.startEditing()
            for feat in xs_lyr.getFeatures():
                xs_lyr.deleteFeature(feat.id())
            for feat in new_feats:
                xs_lyr.addFeature(feat)
            xs_lyr.commitChanges()
            xs_lyr.updateExtents()
            xs_lyr.triggerRepaint()
            xs_lyr.removeSelection()

            self.gutils.create_schematized_rbank_lines_from_xs_tips()
            rbank = self.lyrs.data['rbank']['qlyr']
            rbank.updateExtents()
            rbank.triggerRepaint()
            rbank.removeSelection()

        except Exception as e:
            self.uc.show_error("ERROR 260618.0416: couln't read CHANBANK.DAT or reassign right bank coordinates !", e)

    def import_channel_peaks_from_HYCHAN_OUT(self):
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return
        s = QSettings()
        last_dir = s.value('FLO-2D/lastGdsDir', '')
        hychan_file, __ = QFileDialog.getOpenFileName(None, "Select HYCHAN.OUT to read", directory=last_dir, filter='HYCHAN.OUT')
        if not hychan_file:
            return
        try:
            # Read HYCHAN.OUT and create a dictionary of grid: [max_water_elev, peak_discharge].
            peaks_dict = {}
            peaks_list = []
            with open(hychan_file, "r") as myfile:
                try:
                    while True:
                        line = next(myfile)
                        if "CHANNEL HYDROGRAPH FOR ELEMENT NO:" in line:
                            grid = line.split("CHANNEL HYDROGRAPH FOR ELEMENT NO:")[1].rstrip()
                            line = next(myfile)
                            line = next(myfile)
                            peak_discharge = line.split("MAXIMUM DISCHARGE (CFS) =")[1].split()[0]
                            line = next(myfile)
                            max_water_elev = line.split("MAXIMUM STAGE = ")[1].split()[0]
                            peaks_dict[grid] = [max_water_elev, peak_discharge]
                            peaks_list.append((grid, max_water_elev, peak_discharge))

                        else:
                            pass
                except Exception as e:
                    pass

            # Assign max_water_elev and peak_discharge to features of chan_elems table (schematized layer).
            qry = 'UPDATE chan_elems SET max_water_elev = ?, peak_discharge = ? WHERE fid = ?;'
            for peak in peaks_list:
                self.gutils.execute(qry, (peak[1], peak[2], peak[0]))

            self.uc.bar_info("HYCHAN.OUT file imported. Channel Cross Sections updated with max. surface water elevations and peak discharge data.")
            
        except Exception as e:
            self.uc.show_error("ERROR 050818.0618: couln't process HYCHAN.OUT !", e)

    def reassign_xs_rightbanks_grid_id_from_schematized_rbanks(self, xs_seg_fid, right_bank_fid):
        """ Takes all schematized left bank cross sections (from 'cham_elems' layer) identified by 'xs_seg_fid', and
            changes
            1) their end point to a centroid (see below) of the schematized right bank identified by 'right_bank_fid'and,
            2) their ´rbank´ field (a cell number) to the schematized right bank identified by 'right_bank_fid'.

            Centroids belong to the points of a polyline defined by the ´right_bank_fid' feature. They are taken in order using
            an iterator, from the first to the last.

        """
        try:
            new_feats = []
            xs_lyr = self.lyrs.data['chan_elems']['qlyr']
            rbank = self.lyrs.data['rbank']['qlyr']
            rbank_feats= iter(rbank.getFeatures())

            while True:
                # Find if there is a schematized right bank with 'fid' equal to 'right_bank_fid'.
                # Otherwise do nothing, and return.
                r = next(rbank_feats, None)
                if r is None:
                    return
                elif  r['fid'] == right_bank_fid:
                    break

            r_poly = r.geometry().asPolyline() # Polyline of schematized right bank identified by right_bank_fid: list of pairs (x,y) of its points.
            r_points = iter(r_poly)

            # Create a list of features taken from cham_elems layer (schematized cross sections), modifying their geometry
            # by changing the point of the coordinates of the right bank cell:
            for xs_f in xs_lyr.getFeatures():
                if not xs_f['seg_fid'] == xs_seg_fid:
                    continue
                # xs_f is the next schematized cross section (a single line) identified by xs_seg_fid (from cham_elems layer):
                # All xs with id xs_seg_fid belong to the same left bank.
                xs_feat = QgsFeature()
                xs_feat = xs_f # Copy schematized polyline with id xs_seg_fid.
                left = str(xs_f['fid']) # Cell number of start of this xs.
                pnt0 = self.gutils.single_centroid(left) # Center point of cell 'left'.
                qgsPoint0 = QgsGeometry().fromWkt(pnt0).asPoint()
                qgsPoint1 =  next(r_points, None) # Get next point of schematized right bank 'right_bank_fid'.
                if qgsPoint1 is None:
                    break
                else:
                    right = self.gutils.grid_on_point(qgsPoint1.x(), qgsPoint1.y()) # Get cell number of next schematized right bank cell.
                    new_xs = QgsGeometry.fromPolylineXY([qgsPoint0, qgsPoint1]) # Define line  between left bank and right bank.
                    xs_feat.setGeometry(new_xs) # Assign new line geometry to current xs.
                    xs_feat.setAttribute('rbankgrid', right)# Assign new cell id for right bank cell of current xs.

                    new_feats.append(xs_feat)

            # Replace all features of chan_elems with the new calculated features:
            xs_lyr.startEditing()
            for feat in xs_lyr.getFeatures():
                if feat['seg_fid'] == xs_seg_fid:
                    xs_lyr.deleteFeature(feat.id())
            for feat in new_feats:
                xs_lyr.addFeature(feat)
            xs_lyr.commitChanges()
            xs_lyr.updateExtents()
            xs_lyr.triggerRepaint()
            xs_lyr.removeSelection()

            # self.gutils.create_schematized_rbank_lines_from_xs_tips()
            # rbank.updateExtents()
            # rbank.triggerRepaint()
            # rbank.removeSelection()

        except Exception as e:
            self.uc.show_error("ERROR 240718.0359: couln't join left and right banks !", e)

    # def reassign_xs_rightbanks_grid_id_from_schematized_rbank(self, pairs_left_right):
    #     try:
    #         new_feats = []
    #         xs_lyr = self.lyrs.data['chan_elems']['qlyr']
    #         right_lyr = self.lyrs.data['rbank']['qlyr']
    #         rbank_feats= iter(right_lyr.getFeatures())
    #
    #         for xs_seg_fid, rb_fid in pairs_left_right:
    #             while True:
    #                 r = next(rbank_feats, None)
    #                 if r is None:
    #                     return
    #                 elif  r['fid'] == rb_fid:
    #                     break
    #
    #             r_poly = r.geometry().asPolyline()
    #             r_points = iter(r_poly)
    #
    #             # Create a list of features taken from cham_elems layer (schematized cross sections), modifying their geometry
    #             # by changing the point of the coordinates of the right bank cell:
    #             for xs_f in xs_lyr.getFeatures():
    #                 if not xs_f['seg_fid'] == xs_seg_fid:
    #                     continue
    #                 xs_feat = QgsFeature()
    #                 # Copy the next complete feature of chan_elems layer.
    #                 xs_feat = xs_f
    #                 left = str(xs_f['fid'])
    #                 pnt0 = self.gutils.single_centroid(left)
    #                 qgsPoint0 = QgsGeometry().fromWkt(pnt0).asPoint() # Start point of XS in schematized left bank.
    #                 qgsPoint1 =  next(r_points, None)                 # End point of XS in schematized right bank.
    #                 if qgsPoint1 is None:
    #                     break
    #                 else:
    #                     right = self.gutils.grid_on_point(qgsPoint1.x(), qgsPoint1.y()) # Cell number of next schematized right bank.
    #                     new_xs = QgsGeometry.fromPolylineXY([qgsPoint0, qgsPoint1])
    #                     xs_feat.setGeometry(new_xs)
    #                     xs_feat.setAttribute('rbankgrid', right)
    #
    #                     new_feats.append(xs_feat)
    #
    #         # Replace all features of chan_elems with the new calculated features:
    #         xs_lyr.startEditing()
    #         for feat in xs_lyr.getFeatures():
    #             xs_lyr.deleteFeature(feat.id())
    #         for feat in new_feats:
    #             xs_lyr.addFeature(feat)
    #         xs_lyr.commitChanges()
    #         xs_lyr.updateExtents()
    #         xs_lyr.triggerRepaint()
    #         xs_lyr.removeSelection()
    #
    #         self.gutils.create_schematized_rbank_lines_from_xs_tips()
    #         rbank = self.lyrs.data['rbank']['qlyr']
    #         rbank.updateExtents()
    #         rbank.triggerRepaint()
    #         rbank.removeSelection()
    #
    #     except Exception as e:
    #         self.uc.show_error("ERROR 240718.0359: couln't join left and right banks !", e)

    def schematize_confluences(self):
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return
        if self.gutils.is_table_empty('user_left_bank'):
            self.uc.bar_warn('There are no any user left bank lines! Please digitize them before running the tool.')
            return
        if self.gutils.is_table_empty('user_xsections'):
            self.uc.bar_warn('There are no any user cross sections! Please digitize them before running the tool.')
            return
        try:
            conf = Confluences(self.con, self.iface, self.lyrs)
            conf.calculate_confluences()
            chan_schem = self.lyrs.data['chan']['qlyr']
            chan_elems = self.lyrs.data['chan_elems']['qlyr']
            rbank = self.lyrs.data['rbank']['qlyr']
            confluences = self.lyrs.data['chan_confluences']['qlyr']
            self.lyrs.lyrs_to_repaint = [chan_schem, chan_elems, rbank, confluences]
            self.lyrs.repaint_layers()
            self.uc.show_info('Confluences schematized!')
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn('Schematizing aborted! Please check your 1D User Layers.')
