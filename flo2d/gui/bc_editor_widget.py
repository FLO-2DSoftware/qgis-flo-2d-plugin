# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import Qt
from PyQt4.QtGui import QColor, QComboBox, QSizePolicy, QInputDialog
from qgis.core import QgsFeatureRequest
from ui_utils import load_ui, center_canvas, try_disconnect, set_icon
from flo2d.geopackage_utils import GeoPackageUtils
from flo2d.flo2dobjects import Inflow, Outflow
from flo2d.user_communication import UserCommunication
from flo2d.utils import m_fdata, is_number
from table_editor_widget import StandardItemModel, StandardItem, CommandItemEdit
from math import isnan


uiDialog, qtBaseClass = load_ui('bc_editor')


class BCEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.plot = plot
        self.table_dock = table
        self.bc_tview = table.tview
        self.lyrs = lyrs
        self.setupUi(self)
        self.set_combos()
        self.outflow_frame.setHidden(True)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.inflow = None
        self.outflow = None
        self.define_outflow_types()
        self.populate_outflow_type_cbo()
        self.populate_hydrograph_cbo()
        self.gutils = None
        self.twidget = table
        self.bc_data_model = StandardItemModel()

        self.inflow_frame.setDisabled(True)
        self.outflow_frame.setDisabled(True)
        self.user_bc_tables = ['user_bc_points', 'user_bc_lines', 'user_bc_polygons']
        self.user_change = False
        # inflow plot data variables
        self.t, self.d, self.m = [[], [], []]
        self.ot, self.od, self.om = [[], [], []]
        # outflow plot data variables
        self.d1, self.d2 = [[], []]
        # set button icons
        set_icon(self.create_point_bc_btn, 'mActionCapturePoint.svg')
        set_icon(self.create_line_bc_btn, 'mActionCaptureLine.svg')
        set_icon(self.create_polygon_bc_btn, 'mActionCapturePolygon.svg')
        set_icon(self.save_changes_btn, 'mActionSaveAllEdits.svg')
        set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        set_icon(self.delete_bc_btn, 'mActionDeleteSelected.svg')
        set_icon(self.add_data_btn, 'add_bc_data.svg')
        set_icon(self.schem_bc_btn, 'schematize_bc.svg')
        set_icon(self.change_bc_name_btn, 'change_name.svg')
        set_icon(self.change_inflow_data_name_btn, 'change_name.svg')
        set_icon(self.change_outflow_data_name_btn, 'change_name.svg')

        # connections
        self.create_point_bc_btn.clicked.connect(self.create_point_bc)
        self.create_line_bc_btn.clicked.connect(self.create_line_bc)
        self.create_polygon_bc_btn.clicked.connect(self.create_polygon_bc)

        self.delete_bc_btn.clicked.connect(self.delete_bc)
        self.save_changes_btn.clicked.connect(self.save_bc_lyrs_edits)
        self.revert_changes_btn.clicked.connect(self.cancel_bc_lyrs_edits)
        self.add_data_btn.clicked.connect(self.add_data)
        self.schem_bc_btn.clicked.connect(self.schematize_bc)

        self.bc_name_cbo.activated.connect(self.inflow_changed)
        self.bc_type_inflow_radio.clicked.connect(self.change_bc_type)
        self.bc_type_outflow_radio.clicked.connect(self.change_bc_type)

        self.change_bc_name_btn.clicked.connect(self.change_bc_name)
        self.change_inflow_data_name_btn.clicked.connect(self.change_bc_data_name)
        self.change_outflow_data_name_btn.clicked.connect(self.change_bc_data_name)
        self.ifc_fplain_radio.clicked.connect(self.inflow_dest_changed)
        self.ifc_chan_radio.clicked.connect(self.inflow_dest_changed)
        self.inflow_type_cbo.activated.connect(self.inflow_type_changed)
        self.inflow_tseries_cbo.activated.connect(self.inflow_data_changed)

        self.outflow_type_cbo.activated.connect(self.outflow_type_changed)
        self.outflow_data_cbo.activated.connect(self.outflow_data_changed)
        self.outflow_hydro_cbo.activated.connect(self.outflow_hydrograph_changed)
        self.bc_data_model.dataChanged.connect(self.save_bc_data)
        self.twidget.before_paste.connect(self.block_saving)
        self.twidget.after_paste.connect(self.unblock_saving)
        self.bc_data_model.itemDataChanged.connect(self.itemDataChangedSlot)

    def block_saving(self):
        try_disconnect(self.bc_data_model.dataChanged, self.save_bc_data)

    def unblock_saving(self):
        self.bc_data_model.dataChanged.connect(self.save_bc_data)

    def itemDataChangedSlot(self, item, oldValue, newValue, role, save=True):
        """
        Slot used to push changes of existing items onto undoStack.
        """
        if role == Qt.EditRole:
            command = CommandItemEdit(self, item, oldValue, newValue,
                                      "Text changed from '{0}' to '{1}'".format(oldValue, newValue))
            self.bc_tview.undoStack.push(command)
            return True

    def schematize_bc(self):
        qry = 'SELECT * FROM all_schem_bc;'
        exist_bc = self.gutils.execute(qry).fetchone()
        if exist_bc:
            if not self.uc.question('There are some boundary conditions grid cells defined already. Overwrite them?'):
                return
        self.schematize_inflows()
        self.schematize_outflows()
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data['all_schem_bc']['qlyr']
        ]
        self.lyrs.repaint_layers()

    def set_combos(self):
        sp = QSizePolicy()
        sp.setHorizontalPolicy(QSizePolicy.MinimumExpanding)
        self.bc_name_cbo = QComboBox(self)
        self.inflow_tseries_cbo = QComboBox(self)
        self.outflow_data_cbo = QComboBox(self)
        combos = {
            self.bc_name_cbo: self.bc_name_cbo_layout,
            self.inflow_tseries_cbo: self.inflow_tseries_cbo_layout,
            self.outflow_data_cbo: self.outflow_data_cbo_layout
        }
        for combo, layout in combos.iteritems():
            combo.setEditable(False)
            combo.setSizePolicy(sp)
            layout.addWidget(combo)

    def show_editor(self, user_bc_table=None, bc_fid=None):
        typ = 'inflow'
        fid = None
        geom_type_map = {
            'user_bc_points': 'point',
            'user_bc_lines': 'line',
            'user_bc_polygons': 'polygon'
        }
        if user_bc_table:
            qry = '''SELECT
                        fid, type
                    FROM
                        in_and_outflows
                    WHERE
                        bc_fid = ? and
                        geom_type = ? and
                        type = (SELECT type FROM {} WHERE fid = ?);'''.format(user_bc_table)
            data = (bc_fid, geom_type_map[user_bc_table], bc_fid)
            fid, typ = self.gutils.execute(qry, data).fetchone()
        self.change_bc_type(typ, fid)

    def change_bc_type(self, typ=None, fid=None):
        if typ == 'inflow' and self.bc_type_outflow_radio.isChecked():
            self.bc_type_inflow_radio.setChecked(True)
            self.bc_type_outflow_radio.setChecked(False)
        elif typ == 'outflow' and self.bc_type_inflow_radio.isChecked():
            self.bc_type_inflow_radio.setChecked(False)
            self.bc_type_outflow_radio.setChecked(True)
        else:
            pass
        self.lyrs.clear_rubber()
        self.bc_data_model.clear()

        # inflow
        if self.bc_type_inflow_radio.isChecked():
            try_disconnect(self.bc_name_cbo.activated, self.outflow_changed)
            self.bc_name_cbo.activated.connect(self.inflow_changed)
            self.outflow_type_cbo.blockSignals(True)
            self.outflow_data_cbo.blockSignals(True)
            self.inflow_frame.setVisible(True)
            self.outflow_frame.setVisible(False)
        # outflow
        else:
            try_disconnect(self.bc_name_cbo.activated, self.inflow_changed)
            self.bc_name_cbo.activated.connect(self.outflow_changed)
            self.outflow_type_cbo.blockSignals(False)
            self.outflow_data_cbo.blockSignals(False)
            self.inflow_frame.setVisible(False)
            self.outflow_frame.setVisible(True)
        self.populate_bcs(fid)

    def change_bc_name(self):
        if not self.bc_name_cbo.count():
            return
        new_name, ok = QInputDialog.getText(None, 'Change name', 'New name:')
        if not ok or not new_name:
            return
        if not self.bc_name_cbo.findText(new_name) == -1:
            msg = 'Boundary condition with name {} already exists in the database. Please, choose another name.'.format(
                new_name)
            self.uc.show_warn(msg)
            return
        # inflow
        if self.bc_type_inflow_radio.isChecked():
            self.inflow.name = new_name
            self.inflow.set_row()
            self.populate_inflows(inflow_fid=self.inflow.fid)
        # outflow
        else:
            self.outflow.name = new_name
            self.outflow.set_row()
            self.populate_outflows(outflow_fid=self.outflow.fid)

    def change_bc_data_name(self):
        new_name, ok = QInputDialog.getText(None, 'Change data name', 'New name:')
        if not ok or not new_name:
            return
        # inflow
        if self.bc_type_inflow_radio.isChecked():
            if not self.inflow_tseries_cbo.findText(new_name) == -1:
                msg = 'Time series with name {} already exists in the database. Please, choose another name.'.format(
                    new_name)
                self.uc.show_warn(msg)
                return
            self.inflow.set_time_series_data_name(new_name)
            self.populate_inflows(inflow_fid=self.inflow.fid)
        # outflow
        else:
            if not self.outflow_data_cbo.findText(new_name) == -1:
                msg = 'Data series with name {} already exists in the database. Please, choose another name.'.format(
                    new_name)
                self.uc.show_warn(msg)
                return
            self.outflow.set_data_name(new_name)
            self.populate_outflows(outflow_fid=self.outflow.fid)

    # INFLOWS

    def reset_inflow_gui(self):
        self.bc_name_cbo.clear()
        self.inflow_tseries_cbo.clear()
        self.bc_data_model.clear()
        self.plot.clear()

    def populate_inflows(self, inflow_fid=None, show_last_edited=False):
        """
        Read inflow and inflow_time_series tables, populate proper combo boxes.
        """
        if not self.iface.f2d['con']:
            return
        self.reset_inflow_gui()
        self.gutils = GeoPackageUtils(self.iface.f2d['con'], self.iface)
        all_inflows = self.gutils.get_inflows_list()
        if not all_inflows:
            # self.uc.bar_info('There is no inflow defined in the database...')
            self.change_bc_name_btn.setDisabled(True)
            return
        else:
            self.change_bc_name_btn.setDisabled(False)
        self.enable_bc_type_change()
        cur_name_idx = 0
        inflows_skipped = 0
        for i, row in enumerate(all_inflows):
            row = [x if x is not None else '' for x in row]
            fid, name, geom_type, ts_fid = row
            if not geom_type:
                inflows_skipped += 1
                continue
            if not name:
                name = 'Inflow {}'.format(fid)
            self.bc_name_cbo.addItem(name, [fid, ts_fid])
            if inflow_fid and fid == inflow_fid:
                cur_name_idx = i - inflows_skipped
        if not self.bc_name_cbo.count():
            return
        if show_last_edited:
            cur_name_idx = i - inflows_skipped
        self.in_fid, self.ts_fid = self.bc_name_cbo.itemData(cur_name_idx)
        self.inflow = Inflow(self.in_fid, self.iface.f2d['con'], self.iface)
        self.inflow.get_row()
        self.bc_name_cbo.setCurrentIndex(cur_name_idx)
        self.inflow_changed()

    def inflow_changed(self):
        bc_idx = self.bc_name_cbo.currentIndex()
        cur_data = self.bc_name_cbo.itemData(bc_idx)
        self.bc_data_model.clear()
        if cur_data:
            self.in_fid, self.ts_fid = cur_data
        else:
            return
        self.inflow = Inflow(self.in_fid, self.iface.f2d['con'], self.iface)
        self.inflow.get_row()
        if not is_number(self.ts_fid) or self.ts_fid == -1:
            self.ts_fid = 0
        else:
            self.ts_fid = int(self.ts_fid)
        self.inflow_tseries_cbo.setCurrentIndex(self.ts_fid)

        if self.inflow.ident == 'F':
            self.ifc_fplain_radio.setChecked(1)
            self.ifc_chan_radio.setChecked(0)
        elif self.inflow.ident == 'C':
            self.ifc_fplain_radio.setChecked(0)
            self.ifc_chan_radio.setChecked(1)
        else:
            self.ifc_fplain_radio.setChecked(0)
            self.ifc_chan_radio.setChecked(0)
        if not self.inflow.inoutfc == '':
            self.inflow_type_cbo.setCurrentIndex(self.inflow.inoutfc)
        else:
            self.inflow_type_cbo.setCurrentIndex(0)
        if not self.inflow.geom_type:
            return
        self.bc_lyr = self.get_user_bc_lyr_for_geomtype(self.inflow.geom_type)
        self.show_inflow_rb()
        if self.bc_center_chbox.isChecked():
            feat = self.bc_lyr.getFeatures(QgsFeatureRequest(self.inflow.bc_fid)).next()
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
        self.populate_inflow_data_cbo()

    def populate_inflow_data_cbo(self):
        """
        Read and set inflow properties.
        """
        self.time_series = self.inflow.get_time_series()
        if not self.time_series:
            self.uc.bar_warn('No data series for this inflow.')
            return
        self.inflow_tseries_cbo.clear()
        cur_idx = 0
        for i, row in enumerate(self.time_series):
            row = [x if x is not None else '' for x in row]
            ts_fid, ts_name = row
            if not ts_name:
                ts_name = 'Time series {}'.format(ts_fid)
            self.inflow_tseries_cbo.addItem(ts_name, str(ts_fid))
            if ts_fid == self.inflow.time_series_fid:
                cur_idx = i
        self.inflow.time_series_fid = self.inflow_tseries_cbo.itemData(cur_idx)
        self.inflow_tseries_cbo.setCurrentIndex(cur_idx)
        self.inflow_data_changed()

    def inflow_dest_changed(self):
        if self.ifc_fplain_radio.isChecked():
            self.inflow.ident = 'F'
        else:
            self.inflow.ident = 'C'
        self.save_inflow()

    def inflow_type_changed(self):
        self.inflow.inoutfc = self.inflow_type_cbo.currentIndex()
        self.save_inflow()

    def inflow_data_changed(self):
        """
        Get current time series data, populate data table and create plot.
        """
        cur_ts_idx = self.inflow_tseries_cbo.currentIndex()
        cur_ts_fid = self.inflow_tseries_cbo.itemData(cur_ts_idx)
        self.create_inflow_plot()
        self.bc_tview.undoStack.clear()
        self.bc_tview.setModel(self.bc_data_model)
        self.inflow.time_series_fid = cur_ts_fid
        self.infow_tseries_data = self.inflow.get_time_series_data()
        self.bc_data_model.clear()
        self.bc_data_model.setHorizontalHeaderLabels(['Time', 'Discharge', 'Mud'])
        self.ot, self.od, self.om = [[], [], []]
        if not self.infow_tseries_data:
            self.uc.bar_warn('No time series data defined for that inflow.')
            return
        for row in self.infow_tseries_data:
            items = [StandardItem(str(x)) if x is not None else StandardItem('') for x in row]
            self.bc_data_model.appendRow(items)
            self.ot.append(row[0] if not row[0] is None else float('NaN'))
            self.od.append(row[1] if not row[1] is None else float('NaN'))
            self.om.append(row[2] if not row[2] is None else float('NaN'))
        rc = self.bc_data_model.rowCount()
        if rc < 500:
            for row in range(rc, 500+1):
                items = [StandardItem(x) for x in ('',) * 3]
                self.bc_data_model.appendRow(items)
        self.bc_tview.resizeColumnsToContents()
        for i in range(self.bc_data_model.rowCount()):
            self.bc_tview.setRowHeight(i, 20)
        self.bc_tview.horizontalHeader().setStretchLastSection(True)
        for i in range(3):
            self.bc_tview.setColumnWidth(i, 90)
        self.save_inflow()
        self.create_inflow_plot()

    def save_inflow(self):
        """
        Get inflow and time series data from table view and save them to gpkg.
        """
        new_name = self.bc_name_cbo.currentText()
        # check if the name was changed
        if not self.inflow.name == new_name:
            if new_name in self.gutils.get_inflow_names():
                msg = 'Inflow with name {} already exists in the database. Please, choose another name.'.format(self.inflow.name)
                self.uc.show_warn(msg)
                return False
            else:
                self.inflow.name = new_name
        # save current inflow parameters
        self.inflow.set_row()
        self.save_inflow_data()

    def save_inflow_data(self):
        ts_data = []
        for i in range(self.bc_data_model.rowCount()):
            # save only rows with a number in the first column
            if is_number(m_fdata(self.bc_data_model, i, 0)) and not isnan(m_fdata(self.bc_data_model, i, 0)):
                ts_data.append(
                    (
                        self.inflow.time_series_fid,
                        m_fdata(self.bc_data_model, i, 0),
                        m_fdata(self.bc_data_model, i, 1),
                        m_fdata(self.bc_data_model, i, 2)
                    )
                )
            else:
                pass
        data_name = self.inflow_tseries_cbo.currentText()
        self.inflow.set_time_series_data(data_name, ts_data)

    def schematize_inflows(self):
        del_qry = 'DELETE FROM inflow_cells;'
        ins_qry = '''INSERT INTO inflow_cells (inflow_fid, grid_fid)
            SELECT
                abc.bc_fid, g.fid
            FROM
                grid AS g, all_user_bc AS abc
            WHERE
                abc.type = 'inflow' AND
                ST_Intersects(CastAutomagic(g.geom), CastAutomagic(abc.geom));'''
        self.gutils.execute(del_qry)
        self.gutils.execute(ins_qry)

    def show_inflow_rb(self):
        self.lyrs.show_feat_rubber(self.bc_lyr.id(), self.inflow.bc_fid)

    def create_inflow_plot(self):
        """
        Create initial plot.
        """
        self.plot.clear()
        self.plot.add_item('Original Discharge', [self.ot, self.od], col=QColor("#7dc3ff"), sty=Qt.DotLine)
        self.plot.add_item('Current Discharge', [self.ot, self.od], col=QColor("#0018d4"))
        self.plot.add_item('Original Mud', [self.ot, self.om], col=QColor("#cd904b"), sty=Qt.DotLine)
        self.plot.add_item('Current Mud', [self.ot, self.om], col=QColor("#884800"))

    def update_inflow_plot(self):
        """
        When time series data for plot change, update the plot.
        """
        self.t, self.d, self.m = [[], [], []]
        for i in range(self.bc_data_model.rowCount()):
            self.t.append(m_fdata(self.bc_data_model, i, 0))
            self.d.append(m_fdata(self.bc_data_model, i, 1))
            self.m.append(m_fdata(self.bc_data_model, i, 2))
        self.plot.update_item('Current Discharge', [self.t, self.d])
        self.plot.update_item('Current Mud', [self.t, self.m])

    def add_inflow_data(self):
        if not self.inflow.time_series_fid:
            return
        self.inflow.add_time_series()
        self.populate_inflow_data_cbo()
        ts_nr = self.inflow_tseries_cbo.count()
        self.inflow_tseries_cbo.setCurrentIndex(ts_nr - 1)

    # OUTFLOWS

    def reset_outflow_gui(self):
        self.bc_name_cbo.clear()
        self.outflow_data_cbo.clear()
        self.outflow_type_cbo.setCurrentIndex(0)
        self.outflow_hydro_cbo.setCurrentIndex(0)
        self.outflow_hydro_cbo.setDisabled(True)
        self.outflow_data_cbo.setDisabled(True)
        self.change_outflow_data_name_btn.setDisabled(True)
        self.bc_data_model.clear()
        self.plot.clear()

    def set_outflow_widgets(self, outflow_type):
        self.outflow_data_cbo.clear()
        self.outflow_data_cbo.setDisabled(True)
        self.change_outflow_data_name_btn.setDisabled(True)
        if not outflow_type == 4:
            self.outflow_hydro_cbo.setCurrentIndex(0)
            self.outflow_hydro_cbo.setDisabled(True)
        self.bc_data_model.clear()
        self.plot.clear()
        if outflow_type == -1:
            outflow_type = 0
        out_par = self.outflow_types[outflow_type]
        for wid in out_par['wids']:
            wid.setEnabled(True)
        self.outflow_data_label.setText(out_par['data_label'])
        self.outflow_tab_head = out_par['tab_head']

    def populate_outflows(self, outflow_fid=None, show_last_edited=False):
        """
        Read outflow table, populate the cbo and set apropriate outflow.
        """
        if not self.iface.f2d['con']:
            return
        self.reset_outflow_gui()
        self.gutils = GeoPackageUtils(self.iface.f2d['con'], self.iface)
        all_outflows = self.gutils.get_outflows_list()
        if not all_outflows:
            # self.uc.bar_info('There is no outflow defined in the database...')
            self.change_bc_name_btn.setDisabled(True)
            return
        else:
            self.change_bc_name_btn.setDisabled(False)
        cur_out_idx = 0
        outflows_skipped = 0
        for i, row in enumerate(all_outflows):
            row = [x if x is not None else '' for x in row]
            fid, name, typ, geom_type = row
            if not geom_type:
                outflows_skipped += 1
                continue
            if not name:
                name = 'Outflow {}'.format(fid)
            self.bc_name_cbo.addItem(name, [fid, typ, geom_type])
            if fid == outflow_fid:
                cur_out_idx = i - outflows_skipped
        if not self.bc_name_cbo.count():
            return
        if show_last_edited:
            cur_out_idx = i - outflows_skipped
        self.out_fid, self.type_fid, self.geom_type = self.bc_name_cbo.itemData(cur_out_idx)
        self.outflow = Outflow(self.out_fid, self.iface.f2d['con'], self.iface)
        self.outflow.get_row()
        msg = '''In populate_outflows. Got current outflow row:
        name = {}
        chan_out = {}
        fp_out = {}
        hydro_out = {}
        chan_tser_fid = {}
        chan_qhpar_fid = {}
        chan_qhtab_fid = {}
        fp_tser_fid = {}
        typ = {}
        geom_type = {}
        bc_fid = {}
        '''.format(
            self.outflow.name,
            self.outflow.chan_out,
            self.outflow.fp_out,
            self.outflow.hydro_out,
            self.outflow.chan_tser_fid,
            self.outflow.chan_qhpar_fid,
            self.outflow.chan_qhtab_fid,
            self.outflow.fp_tser_fid,
            self.outflow.typ,
            self.outflow.geom_type,
            self.outflow.bc_fid
        )
        if not self.outflow.geom_type:
            return
        self.bc_lyr = self.get_user_bc_lyr_for_geomtype(self.outflow.geom_type)
        self.show_outflow_rb()
        if self.outflow.hydro_out:
            self.outflow_hydro_cbo.setCurrentIndex(self.outflow.hydro_out)
        self.bc_name_cbo.setCurrentIndex(cur_out_idx)
        self.outflow_changed()

    def outflow_changed(self):
        bc_idx = self.bc_name_cbo.currentIndex()
        cur_data = self.bc_name_cbo.itemData(bc_idx)
        self.bc_data_model.clear()
        if cur_data:
            self.out_fid, self.type_fid, self.geom_type = cur_data
        else:
            return
        self.outflow = Outflow(self.out_fid, self.iface.f2d['con'], self.iface)
        self.outflow.get_row()
        if not is_number(self.outflow.typ):
            self.type_fid = 0
        else:
            self.type_fid = int(self.outflow.typ)
        if not self.outflow.geom_type:
            return
        if not self.outflow.geom_type:
            return
        self.bc_lyr = self.get_user_bc_lyr_for_geomtype(self.outflow.geom_type)
        self.show_outflow_rb()
        if self.bc_center_chbox.isChecked():
            feat = self.bc_lyr.getFeatures(QgsFeatureRequest(self.outflow.bc_fid)).next()
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
        self.outflow_type_cbo.setCurrentIndex(self.type_fid)
        self.outflow_type_changed()

    def outflow_type_changed(self):
        self.bc_data_model.clear()
        typ_idx = self.outflow_type_cbo.currentIndex()
        self.set_outflow_widgets(typ_idx)
        self.outflow.set_type_data(typ_idx)
        self.outflow.set_row()
        self.populate_outflow_data_cbo()

    def outflow_hydrograph_changed(self):
        self.outflow.hydro_out = self.outflow_hydro_cbo.currentIndex()
        self.outflow.set_row()

    def populate_outflow_data_cbo(self):
        self.series = None
        if self.outflow.typ == 4:
            if self.outflow.hydro_out:
                self.outflow_hydro_cbo.setCurrentIndex(self.outflow.hydro_out)
            else:
                self.outflow_hydro_cbo.setCurrentIndex(1)
            return
        elif self.outflow.typ > 4:
            self.create_outflow_plot()
            self.series = self.outflow.get_data_fid_name()
        else:
            return
        if not self.series:
            self.uc.bar_warn('No data series for this type of outflow.')
            return
        self.outflow_data_cbo.clear()
        self.outflow_data_cbo.setEnabled(True)
        cur_idx = 0
        for i, row in enumerate(self.series):
            row = [x if x is not None else '' for x in row]
            s_fid, name = row
            if not name:
                name = self.outflow.get_new_data_name(s_fid)
            self.outflow_data_cbo.addItem(name, s_fid)
            if s_fid == self.outflow.get_cur_data_fid():
                cur_idx = i
        data_fid = self.outflow_data_cbo.itemData(cur_idx)
        self.outflow.set_new_data_fid(data_fid)
        self.outflow_data_cbo.setCurrentIndex(cur_idx)
        self.outflow_data_changed()

    def add_outflow_data(self):
        if not self.outflow:
            return
        self.outflow.add_data()
        self.populate_outflow_data_cbo()

    def outflow_data_changed(self):
        self.outflow.get_cur_data_fid()
        out_nr = self.outflow_data_cbo.count()
        if not out_nr:
            return
        data_idx = self.outflow_data_cbo.currentIndex()
        data_fid = self.outflow_data_cbo.itemData(data_idx)
        self.outflow.set_new_data_fid(data_fid)
        self.create_outflow_plot()
        self.bc_tview.undoStack.clear()
        self.bc_tview.setModel(self.bc_data_model)
        head = self.outflow_tab_head
        series_data = self.outflow.get_data()
        self.d1, self.d2 = [[], []]
        self.bc_data_model.clear()
        self.bc_data_model.setHorizontalHeaderLabels(head)
        for row in series_data:
            items = [StandardItem(str(x)) if x is not None else StandardItem('') for x in row]
            self.d1.append(row[0] if not row[0] is None else float('NaN'))
            self.d2.append(row[1] if not row[1] is None else float('NaN'))
            self.bc_data_model.appendRow(items)
        rc = self.bc_data_model.rowCount()
        if rc < 500:
            for row in range(rc, 500 + 1):
                items = [StandardItem(x) for x in ('',) * self.bc_data_model.columnCount()]
                self.bc_data_model.appendRow(items)
        self.bc_tview.setEnabled(True)
        cols = len(head)
        for col in range(cols):
            self.bc_tview.setColumnWidth(col, int(230/cols))
        self.bc_tview.horizontalHeader().setStretchLastSection(True)
        for i in range(self.bc_data_model.rowCount()):
            self.bc_tview.setRowHeight(i, 20)
        self.outflow.set_row()
        self.update_outflow_plot()

    def create_outflow_plot(self):
        """
        Create initial plot for the current outflow type.
        """
        self.plot.clear()
        self.plot_item_name = None
        if self.outflow.typ in [5, 6, 7, 8]:
            self.plot_item_name = 'Time'
        elif self.outflow.typ == 11:
            self.plot_item_name = 'Q(h) table'
        else:
            pass
        self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))

    def update_outflow_plot(self):
        """
        When time series data for plot change, update the plot.
        """
        if not self.plot_item_name:
            return
        self.d1, self.d2 = [[], []]
        for i in range(self.bc_data_model.rowCount()):
            self.d1.append(m_fdata(self.bc_data_model, i, 0))
            self.d2.append(m_fdata(self.bc_data_model, i, 1))
        self.plot.update_item(self.plot_item_name, [self.d1, self.d2])

    def populate_hydrograph_cbo(self):
        self.outflow_hydro_cbo.clear()
        self.outflow_hydro_cbo.addItem('', 0)
        for i in range(1, 10):
            h_name = 'O{}'.format(i)
            self.outflow_hydro_cbo.addItem(h_name, i)

    def populate_outflow_type_cbo(self):
        """
        Populate outflow types cbo and set current type.
        """
        self.outflow_type_cbo.clear()
        type_name = '{}. {}'
        for typnr in sorted(self.outflow_types.iterkeys()):
            outflow_type = type_name.format(typnr, self.outflow_types[typnr]['name']).strip()
            self.outflow_type_cbo.addItem(outflow_type, typnr)

    def save_outflow(self):
        """
        Get outflow data from widgets and save them to gpkg.
        """
        new_name = self.bc_name_cbo.currentText()
        # check if the name was changed
        if not self.outflow.name == new_name:
            if new_name in self.gutils.get_outflow_names():
                msg = 'Outflow data with name {} already exists in the database. Please, choose another name.'.format(
                    new_name)
                self.uc.show_warn(msg)
            return
        self.outflow.name = new_name
        self.outflow.set_row()
        self.save_outflow_data()
        self.populate_outflows(self.outflow.fid)

    def save_outflow_data(self):
        data = []
        for i in range(self.bc_data_model.rowCount()):
            # save only rows with a number in the first column
            if is_number(m_fdata(self.bc_data_model, i, 0)) and not isnan(m_fdata(self.bc_data_model, i, 0)):
                data.append(
                    [m_fdata(self.bc_data_model, i, j) for j in range(self.bc_data_model.columnCount())]
                )
            else:
                pass
        data_name = self.outflow_data_cbo.currentText()
        self.outflow.set_data(data_name, data)

    def schematize_outflows(self):
        del_qry = 'DELETE FROM outflow_cells;'
        ins_qry = '''
            INSERT INTO outflow_cells (outflow_fid, grid_fid)
            SELECT
                abc.bc_fid, g.fid
            FROM
                grid AS g, all_user_bc AS abc
            WHERE
                abc.type = 'outflow' AND
                ST_Intersects(CastAutomagic(g.geom), CastAutomagic(abc.geom));
                '''
        self.gutils.execute(del_qry)
        self.gutils.execute(ins_qry)

    def define_outflow_types(self):
        self.outflow_types = {
            0: {
                'name': 'No outflow',
                'wids': [],
                'data_label': '',
                'tab_head': None
            },
            1: {
                'name': 'Floodplain outflow (no hydrograph)',
                'wids': [],
                'data_label': '',
                'tab_head': None
            },
            2: {
                'name': 'Channel outflow (no hydrograph)',
                'wids': [],
                'data_label': '',
                'tab_head': None
            },
            3: {
                'name': 'Floodplain and channel outflow (no hydrograph)',
                'wids': [],
                'data_label': '',
                'tab_head': None
            },
            4: {
                'name': 'Outflow with hydrograph',
                'wids': [self.outflow_hydro_cbo],
                'data_label': '',
                'tab_head': None
            },
            5: {
                'name': 'Time-stage for floodplain',
                'wids': [self.outflow_data_cbo, self.change_outflow_data_name_btn, self.plot],
                'data_label': 'Time series',
                'tab_head': ["Time", "Stage"]
            },
            6: {
                'name': 'Time-stage for channel',
                'wids': [self.outflow_data_cbo, self.change_outflow_data_name_btn, self.plot],
                'data_label': 'Time series',
                'tab_head': ["Time", "Stage"]
            },
            7: {
                'name': 'Time-stage for floodplain and free floodplain and channel',
                'wids': [self.outflow_data_cbo, self.change_outflow_data_name_btn, self.plot],
                'data_label': 'Time series',
                'tab_head': ["Time", "Stage"]
            },
            8: {
                'name': 'Time-stage for channel and free floodplain and channel',
                'wids': [self.outflow_data_cbo, self.change_outflow_data_name_btn, self.plot],
                'data_label': 'Time series',
                'tab_head': ["Time", "Stage"]
            },
            9: {
                'name': 'Channel stage-discharge (Q(h) parameters)',
                'wids': [self.outflow_data_cbo, self.change_outflow_data_name_btn],
                'data_label': 'Q(h) parameters',
                'tab_head': ["Hmax", "Coef", "Exponent"]
            },
            10: {
                'name': 'Channel depth-discharge (Q(h) parameters)',
                'wids': [self.outflow_data_cbo, self.change_outflow_data_name_btn],
                'data_label': 'Q(h) parameters',
                'tab_head': ["Hmax", "Coef", "Exponent"]
            },
            11: {
                'name': 'Channel stage-discharge (Q(h) table)',
                'wids': [self.outflow_data_cbo, self.change_outflow_data_name_btn, self.plot],
                'data_label': 'Q(h) table',
                'tab_head': ["Depth", "Discharge"]
            }
        }

    # common methods

    def add_data(self):
        if not self.gutils:
            return
        if self.bc_type_inflow_radio.isChecked():
            self.add_inflow_data()
        elif self.bc_type_outflow_radio.isChecked():
            self.add_outflow_data()
        else:
            pass

    def delete_bc(self):
        """
        Delete the current boundary condition from user layer and schematic tables.
        """
        if not self.bc_name_cbo.count():
            return
        q = 'Are you sure, you want delete the current BC?'
        if not self.uc.question(q):
            return
        fid = None
        bc_idx = self.bc_name_cbo.currentIndex()
        cur_data = self.bc_name_cbo.itemData(bc_idx)
        if cur_data:
            fid = cur_data[0]
        else:
            return
        if fid and self.bc_type_inflow_radio.isChecked():
            self.inflow.del_row()
        elif fid and self.bc_type_outflow_radio.isChecked():
            self.outflow.del_row()
        else:
            pass
        self.repaint_bcs()
        # try to set current bc to the last before the deleted one
        try:
            self.populate_bcs(bc_fid=fid-1)
        except:
            self.populate_bcs()

    def show_outflow_rb(self):
        self.lyrs.show_feat_rubber(self.bc_lyr.id(), self.outflow.bc_fid)

    def outflow_clicked(self, fid):
        typ = self.gutils.execute('SELECT type FROM outflow WHERE fid={};'.format(fid)).fetchone()[0]
        idx = self.bc_name_cbo.findData([fid, typ])
        if not idx == -1:
            self.bc_name_cbo.setCurrentIndex(idx)
        else:
            self.uc.bar_warn('Couldn\'t find outflow fid={} and type={}'.format(fid, typ))

    def get_user_bc_lyr_for_geomtype(self, geom_type):
        table_name = 'user_bc_{}s'.format(geom_type)
        return self.lyrs.data[table_name]['qlyr']

    def get_bc_def_attrs(self):
        if self.bc_type_inflow_radio.isChecked():
            return {'type': "'inflow'"}
        else:
            return {'type': "'outflow'"}

    def create_point_bc(self):
        if not self.lyrs.enter_edit_mode('user_bc_points', self.get_bc_def_attrs()):
            return
        self.enable_bc_type_change(False)

    def create_line_bc(self):
        if not self.lyrs.enter_edit_mode('user_bc_lines', self.get_bc_def_attrs()):
            return
        self.enable_bc_type_change(False)

    def create_polygon_bc(self):
        if not self.lyrs.enter_edit_mode('user_bc_polygons', self.get_bc_def_attrs()):
            return
        self.enable_bc_type_change()

    def enable_bc_type_change(self, bool=True):
        if bool:
            self.bc_type_inflow_radio.setEnabled(True)
            self.bc_type_outflow_radio.setEnabled(True)
            self.bc_name_cbo.setEnabled(True)
            self.inflow_frame.setEnabled(True)
            self.outflow_frame.setEnabled(True)
        else:
            self.bc_type_inflow_radio.setEnabled(False)
            self.bc_type_outflow_radio.setEnabled(False)
            self.bc_name_cbo.setEnabled(False)
            self.inflow_frame.setEnabled(False)
            self.outflow_frame.setEnabled(False)

    def cancel_bc_lyrs_edits(self):
        self.enable_bc_type_change()
        # if user bc layers are edited
        if not self.gutils:
            return
        self.enable_bc_type_change()
        user_bc_edited = self.lyrs.rollback_lyrs_edits(*self.user_bc_tables)
        if user_bc_edited:
            self.populate_bcs()
        if self.bc_type_inflow_radio.isChecked():
            try:
                self.populate_bcs(self.inflow.fid)
            except AttributeError:
                self.populate_bcs()
        else:
            try:
                self.populate_bcs(self.outflow.fid)
            except AttributeError:
                self.populate_bcs()

    def save_bc_lyrs_edits(self):
        """
        Save changes of user bc layers.
        """
        if not self.gutils or not self.lyrs.any_lyr_in_edit(*self.user_bc_tables):
            return
        self.delete_imported_bcs()
        # try to save user bc layers (geometry additions/changes)
        user_bc_edited = self.lyrs.save_lyrs_edits(*self.user_bc_tables)
        # if user bc layers were edited
        if user_bc_edited:
            self.enable_bc_type_change()
            # update inflow names
            if self.bc_type_inflow_radio.isChecked():
                self.gutils.fill_empty_inflow_names()
            else:
                self.gutils.fill_empty_outflow_names()
            # populate widgets and show last edited bc
            self.populate_bcs(show_last_edited=True)
        self.repaint_bcs()

    def populate_bcs(self, bc_fid=None, show_last_edited=False):
        self.bc_tview.setModel(self.bc_data_model)
        self.lyrs.clear_rubber()
        if self.bc_type_inflow_radio.isChecked():
            self.populate_inflows(inflow_fid=bc_fid, show_last_edited=show_last_edited)
            if self.bc_name_cbo.count() == 0:
                self.inflow_frame.setDisabled(True)
            else:
                 self.inflow_frame.setEnabled(True)
        elif self.bc_type_outflow_radio.isChecked():
            self.populate_outflows(outflow_fid=bc_fid, show_last_edited=show_last_edited)
            if self.bc_name_cbo.count() == 0:
                self.outflow_frame.setDisabled(True)
            else:
                self.outflow_frame.setEnabled(True)
        else:
            pass

    def delete_imported_bcs(self):
        if self.bc_type_inflow_radio.isChecked():
            self.gutils.delete_all_imported_inflows()
        elif self.bc_type_outflow_radio.isChecked():
            self.gutils.delete_all_imported_outflows()
        else:
            pass

    def repaint_bcs(self):
        self.lyrs.lyrs_to_repaint = [
            self.lyrs.data['all_schem_bc']['qlyr'],
            self.lyrs.data['user_bc_points']['qlyr'],
            self.lyrs.data['user_bc_lines']['qlyr'],
            self.lyrs.data['user_bc_polygons']['qlyr']
        ]
        self.lyrs.repaint_layers()

    def create_plot(self):
        """
        Create initial plot.
        """
        if self.bc_type_inflow_radio.isChecked():
            self.create_inflow_plot()
        else:
            self.create_outflow_plot()

    def save_bc_data(self):
        self.update_plot()
        if self.bc_type_inflow_radio.isChecked():
            self.save_inflow_data()
        else:
            self.save_outflow_data()

    def update_plot(self):
        """
        When data model data change, update the plot.
        """
        if self.bc_type_inflow_radio.isChecked():
            self.update_inflow_plot()
        else:
            self.update_outflow_plot()
