# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import traceback
from collections import OrderedDict
from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import QApplication, QComboBox, QCheckBox, QDoubleSpinBox, QInputDialog, QFileDialog
from qgis.PyQt.QtGui import QColor
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY
from .ui_utils import load_ui, try_disconnect, set_icon
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..flo2d_ie.swmm_io import StormDrainProject
from ..flo2d_tools.schema2user_tools import remove_features
from ..flo2dobjects import InletRatingTable
from ..utils import is_number, m_fdata, is_true
from .table_editor_widget import StandardItemModel, StandardItem, CommandItemEdit
from math import isnan

from ..gui.dlg_outfalls import OutfallNodesDialog
from ..gui.dlg_inlets import InletNodesDialog
from ..gui.dlg_conduits import ConduitsDialog
from ..gui.dlg_stormdrain_shapefile import StormDrainShapefile

uiDialog, qtBaseClass = load_ui('storm_drain_editor')


class StormDrainEditorWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.tables = table
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.gutils = None
        self.grid_lyr = None
        self.user_swmm_nodes_lyr = None
        self.user_swmm_conduits_lyr = None
        self.schema_inlets = None
        self.schema_outlets = None
        self.all_schema = []
        self.swmm_idx = 0
        self.INP_groups = OrderedDict() # ".INP_groups" will contain all groups [xxxx] in .INP file,
                                        # ordered as entered.
        self.swmm_columns = [
            'sd_type', 'intype', 'swmm_length', 'swmm_width', 'swmm_height', 'swmm_coeff', 'flapgate', 'curbheight',
            'max_depth', 'invert_elev', 'rt_fid', 'outf_flo'
        ]

        self.inlet_columns = ['intype', 'swmm_length', 'swmm_width', 'swmm_height', 'swmm_coeff', 'swmm_feature', 'flapgate', 'curbheight']
        self.outlet_columns = ['outf_flo']

        self.inletRT = None
        self.plot = plot
        self.table = table
        self.inlet_data_model = StandardItemModel()
        self.inlet_series_data = None
        self.plot_item_name = None
        self.d1, self.d2 = [[], []]

        set_icon(self.create_point_btn, 'mActionCapturePoint.svg')
        set_icon(self.save_changes_btn, 'mActionSaveAllEdits.svg')
        set_icon(self.revert_changes_btn, 'mActionUndo.svg')
        set_icon(self.delete_btn, 'mActionDeleteSelected.svg')
        set_icon(self.schema_btn, 'schematize_res.svg')

        self.create_point_btn.clicked.connect(self.create_swmm_point)
        self.save_changes_btn.clicked.connect(self.save_swmm_edits)
        self.revert_changes_btn.clicked.connect(self.revert_swmm_lyr_edits)
        self.delete_btn.clicked.connect(self.delete_cur_swmm)
        self.schema_btn.clicked.connect(self.schematize_swmm)
        # self.change_name_btn.clicked.connect(self.rename_swmm)
        #
        # self.recalculate_btn.clicked.connect(self.recalculate_max_depth)
        # self.inlet_grp.toggled.connect(self.inlet_checked)
        # self.outlet_grp.toggled.connect(self.outlet_checked)
        #
        # self.show_table_btn.clicked.connect(self.populate_rtables_data)
        # self.add_rtable_btn.clicked.connect(self.add_rtables)
        # self.remove_rtable_btn.clicked.connect(self.delete_rtables)
        # self.rename_rtable_btn.clicked.connect(self.rename_rtables)
        # self.inlet_data_model.dataChanged.connect(self.save_rtables_data)
        # self.table.before_paste.connect(self.block_saving)
        # self.table.after_paste.connect(self.unblock_saving)
        # self.inlet_data_model.itemDataChanged.connect(self.itemDataChangedSlot)

    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

            self.inletRT = InletRatingTable(self.con, self.iface)
            self.grid_lyr = self.lyrs.data['grid']['qlyr']
            self.user_swmm_nodes_lyr = self.lyrs.data['user_swmm_nodes']['qlyr']
            self.user_swmm_conduits_lyr = self.lyrs.data['user_swmm_conduits']['qlyr']
            self.schema_inlets = self.lyrs.data['swmmflo']['qlyr']
            self.schema_outlets = self.lyrs.data['swmmoutf']['qlyr']
            self.all_schema += [self.schema_inlets, self.schema_outlets]

            self.simulate_stormdrain_chbox.clicked.connect(self.simulate_stormdrain)
            self.import_shapefile_btn.clicked.connect(self.import_hydraulics)
            self.import_inp_btn.clicked.connect(self.import_storm_drain_INP_file)
#             self.export_inp_btn.clicked.connect(self.export_swmm_INP_file)
            self.export_inp_btn.clicked.connect(self.export_storm_drain_INP_file)
            self.outfalls_btn.clicked.connect(self.show_outfalls)
            self.inlets_btn.clicked.connect(self.show_inlets)
            self.conduits_btn.clicked.connect(self.show_conduits)

            qry = '''SELECT value FROM cont WHERE name = 'SWMM';'''
            row = self.gutils.execute(qry).fetchone()
            if is_number(row[0]):
                if row[0] == '0':
                    self.simulate_stormdrain_chbox.setChecked(False)
                else:
                    self.simulate_stormdrain_chbox.setChecked(True)

    def split_INP_into_groups_dictionary_by_tags_to_export(self, inp_file):
        """
        Creates an ordered dictionary INP_groups with all groups in [xxxx] .INP file.

        At the end, INP_groups will be a dictionary of lists of strings, with keys like
            ...
            SUBCATCHMENTS
            SUBAREAS
            INFILTRATION
            JUNCTIONS
            OUTFALLS
            CONDUITS
            etc.

        """
        INP_groups = OrderedDict() # ".INP_groups" will contain all groups [xxxx] in .INP file,
                                        # ordered as entered.

        with open(inp_file) as swmm_inp:  # open(file, mode='r',...) defaults to mode 'r' read.
            for chunk in swmm_inp.read().split('['):  #  chunk gets all text (including newlines) until next '[' (may be empty)
                try:
                    key, value = chunk.split(']')  # divide chunk into:
                                                   # key = name of group (e.g. JUNCTIONS) and
                                                   # value = rest of text until ']'
                    INP_groups[key] = value.split('\n') # add new item {key, value.split('\n')} to dictionary INP_groups.
                                                             # E.g.:
                                                             #   key:
                                                             #     JUNCTIONS
                                                             #   value.split('\n') is list of strings:
                                                             #    I1  4685.00    6.00000    0.00       0.00       0.00
                                                             #    I2  4684.95    6.00000    0.00       0.00       0.00
                                                             #    I3  4688.87    6.00000    0.00       0.00       0.00
                except ValueError:
                    continue

            return INP_groups

    def select_this_INP_group(self, INP_groups,  chars):
        """ Returns the whole .INP group [´chars'xxx]

        ´chars' is the  beginning of the string. Only the first 4 or 5 lower case letters are used in all calls.
        Returns a list of strings of the whole group, one list item for each line of the original .INP file.

        """
        part = None
        if INP_groups is None:
            return part
        else:
            for tag in list(INP_groups.keys()):
                low_tag = tag.lower()
                if low_tag.startswith(chars):
                    part = INP_groups[tag]
                    break
                else:
                    continue
            return part   # List of strings in .INT_groups dictionary item keyed by 'chars' (e.e.´junc', 'cond', 'outf',...)

    def repaint_schema(self):
        for lyr in self.all_schema:
            lyr.triggerRepaint()

    def create_swmm_point(self):
        self.uc.clear_bar_messages()

        if self.gutils.is_table_empty('user_model_boundary'):
            self.uc.bar_warn('There is no computational domain! Please digitize it before running tool.')
            return
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return

        if not self.lyrs.enter_edit_mode('user_swmm_nodes'):
            return

    def save_swmm_edits(self):
        self.uc.clear_bar_messages()

        if self.gutils.is_table_empty('user_model_boundary'):
            self.uc.bar_warn('There is no computational domain! Please digitize it before running tool.')
            return
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return

        before = self.gutils.count('user_swmm_nodes')
        self.lyrs.save_lyrs_edits('user_swmm_nodes')
        after = self.gutils.count('user_swmm_nodes')
        if after > before:
            self.swmm_idx = after - 1
        # elif self.swmm_idx >= 0:
        #     self.save_attrs()
        # else:
        #     return
        # self.populate_swmm()

    def revert_swmm_lyr_edits(self):
        user_swmm_nodes_edited = self.lyrs.rollback_lyrs_edits('user_swmm_nodes')
        # if user_swmm_nodes_edited:
        #     self.populate_swmm()

    def delete_cur_swmm(self):
        if not self.swmm_name_cbo.count():
            return
        q = 'Are you sure, you want delete the current Storm Drain point?'
        if not self.uc.question(q):
            return
        swmm_fid = self.swmm_name_cbo.itemData(self.swmm_idx)['fid']
        self.gutils.execute('DELETE FROM user_swmm_nodes WHERE fid = ?;', (swmm_fid,))
        self.swmm_lyr.triggerRepaint()
        # self.populate_swmm()

    def save_attrs(self):
        swmm_dict = self.swmm_name_cbo.itemData(self.swmm_idx)
        fid = swmm_dict['fid']
        name = self.swmm_name_cbo.currentText()
        swmm_dict['name'] = name
        if self.inlet_grp.isChecked():
            swmm_dict['sd_type'] = 'I'
            grp = self.inlet_grp
        elif self.outlet_grp.isChecked():
            swmm_dict['sd_type'] = 'O'
            grp = self.outlet_grp
        else:
            return
        for obj in self.flatten(grp):
            obj_name = obj.objectName().split('_', 1)[-1]
            if isinstance(obj, QDoubleSpinBox):
                swmm_dict[obj_name] = obj.value()
            elif isinstance(obj, QComboBox):
                val = obj.currentIndex()
                if obj_name == 'intype':
                    val += 1
                swmm_dict[obj_name] = val
            elif isinstance(obj, QCheckBox):
                swmm_dict[obj_name] = int(obj.isChecked())
            else:
                continue

        sd_type = swmm_dict['sd_type']
        intype = swmm_dict['intype']
        if sd_type == 'I' and intype != 4:
            if swmm_dict['flapgate'] == 1:
                inlet_type = self.cbo_intype.currentText()
                self.uc.bar_warn('Vertical inlet opening is not allowed for {}!'.format(inlet_type))
                return
            swmm_dict['rt_fid'] = None
        elif sd_type == 'I' and intype == 4:
            swmm_dict['rt_fid'] = self.cbo_rating_tables.itemData(self.cbo_rating_tables.currentIndex())
        else:
            pass

        col_gen = ('{}=?'.format(c) for c in list(swmm_dict.keys()))
        col_names = ', '.join(col_gen)
        vals = list(swmm_dict.values()) + [fid]
        update_qry = '''UPDATE user_swmm_nodes SET {0} WHERE fid = ?;'''.format(col_names)
        self.gutils.execute(update_qry, vals)

    def schematize_swmm(self):
        self.uc.clear_bar_messages()

        if self.gutils.is_table_empty('user_model_boundary'):
            self.uc.bar_warn('There is no computational domain! Please digitize it before running tool.')
            return
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return

        qry_inlet = '''
        INSERT INTO swmmflo
        (geom, swmmchar, swmm_jt, swmm_iden, intype, swmm_length, swmm_width, swmm_height, swmm_coeff, swmm_feature, flapgate, curbheight)
        VALUES ((SELECT AsGPB(ST_Centroid(GeomFromGPB(geom))) FROM grid WHERE fid=?),?,?,?,?,?,?,?,?,?,?,?);'''
        qry_outlet = '''
        INSERT INTO swmmoutf
        (geom, grid_fid, name, outf_flo)
        VALUES ((SELECT AsGPB(ST_Centroid(GeomFromGPB(geom))) FROM grid WHERE fid=?),?,?,?);'''
        qry_rt_update = '''UPDATE swmmflort SET grid_fid = ? WHERE fid = ?;'''
        try:

            if self.gutils.is_table_empty('user_swmm_nodes'):
                self.uc.bar_warn("There are no storm drain components (inlets/outfalls) defined in layer Storm Drain Nodes (User Layers)")
                return

            QApplication.setOverrideCursor(Qt.WaitCursor)

            inlets = []
            outlets = []
            rt_updates = []
            feats = self.user_swmm_nodes_lyr.getFeatures()
            for feat in feats:
                geom = feat.geometry()
                if geom is None:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_critical("Schematizing of Storm Drains failed!\n\n" +
                               "Geometry (inlet or outlet) missing.\n\n" +
                               "Please check user Storm Drain Nodes layer.")
                    return
                point = geom.asPoint()
                grid_fid = self.gutils.grid_on_point(point.x(), point.y())
                sd_type = feat['sd_type']
                name = feat['name']
                rt_fid = feat['rt_fid']
                if sd_type == 'I':
                    intype = feat['intype']
                    if intype == 4 and rt_fid is not None:
                        rt_updates.append((grid_fid, rt_fid))
                    row = [grid_fid, 'D', grid_fid, name] + [feat[col] for col in self.inlet_columns]
                    row[10] = int('0' if row[9] == 'False' else '1')
                    inlets.append(row)
                elif sd_type == 'O':
                    row = [grid_fid, grid_fid, name] + [feat[col] for col in self.outlet_columns]
                    outlets.append(row)
                else:
                    raise ValueError
            self.gutils.clear_tables('swmmflo', 'swmmoutf')
            cur = self.con.cursor()
            cur.executemany(qry_inlet, inlets)
            cur.executemany(qry_outlet, outlets)
            cur.executemany(qry_rt_update, rt_updates)
            self.con.commit()
            self.repaint_schema()
            QApplication.restoreOverrideCursor()
            self.uc.show_info("Schematizing of Storm Drains finished!\n\n" +
                             "The 'Storm Drain-SD Inlets' and 'Storm Drain-SD Outfalls' layers were updated.\n\n" +
                             "(NOTE: the 'Export GDS files' tool will write those layer atributes into the SWMMFLO.DAT and SWMMOUTF.DAT files)")
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.show_critical("Schematizing of Storm Drains failed!\n\n" +
                               "Atrribute (inlet or outlet) missing.\n\n" +
                               "Please check user Storm Drain Nodes layer.")

    def simulate_stormdrain(self):
        if self.simulate_stormdrain_chbox.isChecked():
            self.gutils.set_cont_par('SWMM', 1)
        else:
            self.gutils.set_cont_par('SWMM', 0)

    def import_storm_drain_INP_file(self):
        """
        Reads a Storm Water Management Model (SWMM) .INP file.

        Reads an .INP file and creates the "user_swmm_nodes" and "user_swmm_conduits" layers with
        attributes taken from the [COORDINATES], [SUBCATCHMENTS], [JUNCTIONS], [OUTFALLS], [CONDUITS],
        [LOSSES], [XSECTIONS] groups of the .INP file.
        Also includes additional attributes used by the FLO-2D model.

        The following dictionaries from the StormDrainProject class are used:
            self.INP_groups = OrderedDict()    :will contain all groups [xxxx] from .INP file
            self.INP_nodes = {}
            self.INP_conduits = {}

        """

        self.uc.clear_bar_messages()

        if self.gutils.is_table_empty('user_model_boundary'):
            self.uc.bar_warn('There is no computational domain! Please digitize it before running tool.')
            return
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return

        s = QSettings()
        last_dir = s.value('FLO-2D/lastGpkgDir', '')
        # last_dir = s.value('FLO-2D/lastSWMMDir', '')
        swmm_file, __ = QFileDialog.getOpenFileName(
            None,
            'Select SWMM input file to import data',
            directory=last_dir,
            filter='(*.inp *.INP*)')
        if not swmm_file:
            return
        s.setValue('FLO-2D/lastSWMMDir', os.path.dirname(swmm_file))

        try:
            """
            Create an ordered dictionary "storm_drain.INP_groups".
            
            storm_drain.split_INP_groups_dictionary_by_tags():
            'The dictionary 'INP_groups' will have as key the name of the groups [xxxx] like 'OUTFALLS', 'JUNCTIONS', etc.
            Each element of the dictionary is a list of all the lines following the group name [xxxx] in the .INP file.
            
            """

            QApplication.setOverrideCursor(Qt.WaitCursor)
            storm_drain = StormDrainProject(self.iface, swmm_file)

            if storm_drain.split_INP_groups_dictionary_by_tags() <= 1:
                # No coordinates in INP file
                QApplication.restoreOverrideCursor()
                self.uc.show_warn("SWMM input file\n\n " + swmm_file + "\n\n has no coordinates defined!")
                return

            # Build Nodes:
            if storm_drain.create_INP_nodes_dictionary_with_coordinates() == 0:
                QApplication.restoreOverrideCursor()
                self.uc.show_warn("SWMM input file\n\n " + swmm_file + "\n\n has no coordinates defined!")
                return
            else:
                storm_drain.add_SUBCATCHMENTS_to_INP_nodes_dictionary()
                storm_drain.add_OUTFALLS_to_INP_nodes_dictionary()
                storm_drain.add_JUNCTIONS_to_INP_nodes_dictionary()

                # Conduits:
                storm_drain.create_INP_conduits_dictionary_with_conduits()
                storm_drain.add_LOSSES_to_INP_conduits_dictionary()
                storm_drain.add_XSECTIONS_to_INP_conduits_dictionary()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 080618.0448: reading SWMM input file failed!", e)
            return

        try:
            """
            Creates Storm Drain Nodes layer.
            
            Creates "user_swmm_nodes" layer with attributes taken from
            the [COORDINATES], [JUNCTIONS], and [OUTFALLS] groups.
            
            """

            # Transfer data from "storm_drain.INP_dict" to "user_swmm_user" layer:
            remove_features(self.user_swmm_nodes_lyr)
            fields = self.user_swmm_nodes_lyr.fields()
            new_nodes = []
            for name, values in list(storm_drain.INP_nodes.items()):  # "INP_nodes dictionary contains attributes names and
                                                                # values taken from the .INP file.
                feat = QgsFeature()
                feat.setFields(fields)

                if 'subcatchment' in values:
                    sd_type = 'I'
                elif 'out_type' in values:
                    sd_type = 'O'
                # else:
                #     sd_type = 'J'
                else:
                    continue

                max_depth = float(values['max_depth']) if 'max_depth' in values else 0
                junction_invert_elev = float(values['junction_invert_elev']) if 'junction_invert_elev' in values else 0
                outfall_invert_elev =  float(values['outfall_invert_elev']) if 'outfall_invert_elev' in values else 0
                rim_elev = junction_invert_elev + max_depth if junction_invert_elev and max_depth else 0
                # outfall_type = values['outfall_type'] if 'outfall_type' in values else 'Normal'
                outfall_type = values['out_type'] if 'out_type' in values else 'Normal'
                tidal_curve = values['tidal_curve'] if 'tidal_curve' in values else '...'
                time_series = values['time_series'] if 'time_series' in values else '...'

                flap_gate = values['flapgate'] if 'flapgate' in values else 'False'
                flap_gate = 'True' if is_true(flap_gate) else 'False'

                allow_discharge = values['swmm_allow_discharge'] if 'swmm_allow_discharge' in values else 'False'
                allow_discharge = 'True' if is_true(allow_discharge) else 'False'

                intype = int(values['intype']) if 'intype' in values else 1

                x = float(values['x'])
                y = float(values['y'])
                grid = self.gutils.grid_on_point(x, y)
                if grid is None:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_warn("Storm Drain point '" + name + "' outside domain!")
                    return
                elev = self.gutils.grid_value(grid, 'elevation')
                geom = QgsGeometry.fromPointXY(QgsPointXY(x, y))
                feat.setGeometry(geom)

                feat.setAttribute('grid', grid)
                feat.setAttribute('sd_type', sd_type)
                feat.setAttribute('name', name)
                feat.setAttribute("intype", intype)
                feat.setAttribute('junction_invert_elev', junction_invert_elev)
                feat.setAttribute('max_depth', max_depth)
                feat.setAttribute('init_depth', float(values['init_depth']) if 'init_depth' in values else 0)
                feat.setAttribute('surcharge_depth', float(values['surcharge_depth']) if 'surcharge_depth' in values else 0)
                feat.setAttribute('ponded_area', float(values['ponded_area']) if 'ponded_area' in values else 0)
                feat.setAttribute('outfall_type', outfall_type)
                feat.setAttribute('outfall_invert_elev', outfall_invert_elev)
                feat.setAttribute('tidal_curve', tidal_curve)
                feat.setAttribute('time_series', time_series)
                feat.setAttribute('flapgate', flap_gate)
                feat.setAttribute('swmm_length', 0)
                feat.setAttribute('swmm_width', 0)
                feat.setAttribute('swmm_height', 0)
                feat.setAttribute('swmm_coeff', 0)
                feat.setAttribute('swmm_feature', 0)
                feat.setAttribute('curbheight', 0)
                feat.setAttribute('swmm_clogging_factor', 0)
                feat.setAttribute('swmm_time_for_clogging', 0)
                feat.setAttribute('swmm_allow_discharge', allow_discharge)
                feat.setAttribute('water_depth', 0)
                feat.setAttribute('rt_fid', 0)
                feat.setAttribute('outf_flo', 0)
                feat.setAttribute('invert_elev_inp', junction_invert_elev)
                feat.setAttribute('max_depth_inp', max_depth)
                feat.setAttribute('rim_elev_inp', rim_elev)
                feat.setAttribute('rim_elev', rim_elev)
                feat.setAttribute('ge_elev', elev)
                difference = elev - rim_elev if elev and rim_elev else None
                feat.setAttribute('difference', difference)

                new_nodes.append(feat)

            if new_nodes is not None:
                self.user_swmm_nodes_lyr.startEditing()
                self.user_swmm_nodes_lyr.addFeatures(new_nodes)
                self.user_swmm_nodes_lyr.commitChanges()
                self.user_swmm_nodes_lyr.updateExtents()
                self.user_swmm_nodes_lyr.triggerRepaint()
                self.user_swmm_nodes_lyr.removeSelection()

            QApplication.restoreOverrideCursor()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("Creating Storm Drain Nodes layer failed!\n\n" + "Please check your SWMM input data.\nAre the nodes coordinates inside the computational domain?", e)
            return

        try:
            """
            Creates Storm Drain Conduits layer.
             
            Creates "user_swmm_conduits" layer with attributes taken from
            the [CONDUITS], [LOSSES], and [XSECTIONS] groups.
             
            """

            # Transfer data from "storm_drain.INP_dict" to "user_swmm_conduits" layer:
            remove_features(self.user_swmm_conduits_lyr)
            fields = self.user_swmm_conduits_lyr.fields()
            new_conduits = []
            for name, values in list(storm_drain.INP_conduits.items()):

                conduit_inlet = values['conduit_inlet'] if  'conduit_inlet' in values else ''
                conduit_outlet = values['conduit_outlet'] if  'conduit_outlet' in values else ''
                conduit_length  = float(values['conduit_length']) if  'conduit_length' in values else 0
                conduit_manning  = float(values['conduit_manning']) if  'conduit_manning' in values else 0
                conduit_inlet_offset = float(values['conduit_inlet_offset']) if  'conduit_inlet_offset' in values else 0
                conduit_outlet_offset = float(values['conduit_outlet_offset'])  if  'conduit_outlet_offset' in values else 0
                conduit_init_flow = float(values['conduit_init_flow'])   if  'conduit_init_flow' in values else 0
                conduit_max_flow = float(values['conduit_max_flow']) if  'conduit_max_flow' in values else 0

                conduit_losses_inlet = float(values['losses_inlet']) if  'losses_inlet' in values else 0
                conduit_losses_outlet = float(values['losses_outlet']) if  'losses_outlet' in values else 0
                conduit_losses_average = float(values['losses_average']) if  'losses_average' in values else 0

                conduit_losses_flapgate = values['losses_flapgate'] if 'losses_flapgate' in values else 'False'
                conduit_losses_flapgate = 'True' if is_true(conduit_losses_flapgate) else 'False'

                conduit_xsections_shape = values['xsections_shape'] if 'xsections_shape' in values else 'CIRCULAR'
                conduit_xsections_barrels = float(values['xsections_barrels']) if  'xsections_barrels' in values else 0
                conduit_xsections_max_depth = float(values['xsections_max_depth']) if  'xsections_max_depth' in values else 0
                conduit_xsections_geom2 = float(values['xsections_geom2']) if  'xsections_geom2' in values else 0
                conduit_xsections_geom3 = float(values['xsections_geom3']) if  'xsections_geom3' in values else 0
                conduit_xsections_geom4 = float(values['xsections_geom4']) if  'xsections_geom4' in values else 0

                feat = QgsFeature()
                feat.setFields(fields)

                x1 = float(storm_drain.INP_nodes[conduit_inlet]['x'])
                y1 = float(storm_drain.INP_nodes[conduit_inlet]['y'])
                x2 = float(storm_drain.INP_nodes[conduit_outlet]['x'])
                y2 = float(storm_drain.INP_nodes[conduit_outlet]['y'])
                geom = QgsGeometry.fromPolylineXY([QgsPointXY(x1,y1),QgsPointXY(x2,y2)])
                feat.setGeometry(geom)

                # elev = 0
                #
                # if 'x' in values:
                #     x = float(values['x'])
                #     y = float(values['y'])
                #     gid = self.gutils.grid_on_point(x, y)
                #     elev = self.gutils.grid_value(gid, 'elevation')
                #     geom = QgsGeometry.fromPointXY(QgsPointXY(x, y))
                #     feat.setAttribute('grid', gid)
                #
                #     feat.setAttribute('ge_elev', elev)

                feat.setAttribute('conduit_name', name)
                feat.setAttribute('conduit_inlet', conduit_inlet)
                feat.setAttribute('conduit_outlet', conduit_outlet)
                feat.setAttribute('conduit_length', conduit_length)
                feat.setAttribute('conduit_manning', conduit_manning)
                feat.setAttribute('conduit_inlet_offset', conduit_inlet_offset)
                feat.setAttribute('conduit_outlet_offset', conduit_outlet_offset)
                feat.setAttribute('conduit_init_flow', conduit_init_flow)
                feat.setAttribute('conduit_max_flow', conduit_max_flow)

                feat.setAttribute('losses_inlet', conduit_losses_inlet)
                feat.setAttribute('losses_outlet', conduit_losses_outlet)
                feat.setAttribute('losses_average', conduit_losses_average)
                feat.setAttribute('losses_flapgate', conduit_losses_flapgate)

                feat.setAttribute('xsections_shape', conduit_xsections_shape)
                feat.setAttribute('xsections_barrels', conduit_xsections_barrels)
                feat.setAttribute('xsections_max_depth', conduit_xsections_max_depth)
                feat.setAttribute('xsections_geom2', conduit_xsections_geom2)
                feat.setAttribute('xsections_geom3', conduit_xsections_geom3)
                feat.setAttribute('xsections_geom4', conduit_xsections_geom4)

                new_conduits.append(feat)

                if new_conduits is not None:
                    self.user_swmm_conduits_lyr.startEditing()
                    self.user_swmm_conduits_lyr.addFeatures(new_conduits)
                    self.user_swmm_conduits_lyr.commitChanges()
                    self.user_swmm_conduits_lyr.updateExtents()
                    self.user_swmm_conduits_lyr.triggerRepaint()
                    self.user_swmm_conduits_lyr.removeSelection()

            QApplication.restoreOverrideCursor()

            if len(new_nodes) == 0 and len(new_conduits) == 0:
                self.uc.show_info("No nodes or conduits were defined in file\n\n" + swmm_file)
            else:
                self.uc.show_info("Importing SWMM input data finished!\n\n" +
                                  "The 'Storm Drain Nodes' and 'Storm Drain Conduits' layers were created in the 'User Layers' group.\n\n"
                                  "Use the 'Inlets', 'Outlets', and 'Conduits' buttons in the Storm Drain Editor widget to see/edit their attributes.\n\n"
                                  "NOTE: the 'Schematize Storm Drain Components' button will update the 'Storm Drain' layer group.")

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error('ERROR 050618.1804: creation of Storm Drain Conduits layer failed!', e)

    def export_storm_drain_INP_file(self):
        """
        Writes <name>.INP file
        (<name> exists or is given by user in nitial file dialog).

        The following groups are are always written with the data of the current project:
            [JUNCTIONS] [OUTFALLS] [CONDUITS] [XSECTIONS] [LOSSES] [COORDINATES]
        All other groups are written from data of .INP file if they exists.
        """

        try:
            self.uc.clear_bar_messages()

            INP_groups = OrderedDict()

            s = QSettings()
            last_dir = s.value('FLO-2D/lastSWMMDir', '')
            swmm_file, __ = QFileDialog.getSaveFileName(
                None,
                'Select SWMM input file to update',
                directory=last_dir,
                filter='(*.inp *.INP*)')

            if not swmm_file:
                return

            s.setValue('FLO-2D/lastSWMMDir', os.path.dirname(swmm_file))

            if os.path.isfile(swmm_file):
                # File exists.Import groups:
                INP_groups= self.split_INP_into_groups_dictionary_by_tags_to_export(swmm_file)
            else:
                # File doen't exists.Create groups.
                pass

            with open(swmm_file, 'w') as swmm_inp_file:

                # TITLE ##################################################
                items = self.select_this_INP_group(INP_groups, 'title')
                swmm_inp_file.write('[TITLE]')
                if items is not None:
                    for line in items[1:]:
                        swmm_inp_file.write("\n" + line)
                else:
                    swmm_inp_file.write('\nINP file created by FLO-2D')

                # OPTIONS ##################################################
                items = self.select_this_INP_group(INP_groups, 'options')
                swmm_inp_file.write('\n[OPTIONS]')
                if items is not None:
                    for line in items[1:]:
                        swmm_inp_file.write("\n" + line)
                else:
                    swmm_inp_file.write('\n')

                # JUNCTIONS ##################################################
                try:
                    swmm_inp_file.write('\n')
                    swmm_inp_file.write('\n[JUNCTIONS]')
                    swmm_inp_file.write('\n;;               Invert     Max.       Init.      Surcharge  Ponded')
                    swmm_inp_file.write('\n;;Name           Elev.      Depth      Depth      Depth      Area')
                    swmm_inp_file.write('\n;;-------------- ---------- ---------- ---------- ---------- ----------')

                    SD_junctions_sql = '''SELECT name, junction_invert_elev, max_depth, init_depth, surcharge_depth, ponded_area
                                      FROM user_swmm_nodes WHERE sd_type = "I" ORDER BY fid;'''
                    line = '\n{0:16} {1:<10.2f} {2:<10.2f} {3:<10.2f} {4:<10.2f} {5:<10.2f}'
                    junctions_rows = self.gutils.execute(SD_junctions_sql).fetchall()
                    if not junctions_rows:
                        pass
                    else:
                        for row in junctions_rows:
                            swmm_inp_file.write(line.format(*row))
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 070618.0851: error while exporting [JUNCTIONS] to .INP file!", e)
                    return

                # OUTFALLS ###################################################
                try:
                    swmm_inp_file.write('\n')
                    swmm_inp_file.write('\n[OUTFALLS]')
                    swmm_inp_file.write('\n;;               Invert     Outfall    Stage/Table      Tide')
                    swmm_inp_file.write('\n;;Name           Elev.      Type       Time Series      Gate')
                    swmm_inp_file.write('\n;;-------------- ---------- ---------- ---------------- ----')

                    SD_outfalls_sql =  '''SELECT name, outfall_invert_elev, outfall_type, time_series, tidal_curve
                                      FROM user_swmm_nodes  WHERE sd_type = "O"  ORDER BY fid;'''

                    line = '\n{0:16} {1:<10.2f} {2:<10} {3:<10} {4:<10}'
                    outfalls_rows = self.gutils.execute(SD_outfalls_sql).fetchall()
                    if not outfalls_rows:
                        pass
                    else:
                        for row in outfalls_rows:
                            swmm_inp_file.write(line.format(*row))
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 070618.1619: error while exporting [OUTFALLS] to .INP file!", e)
                    return

                # CONDUITS ###################################################
                try:
                    swmm_inp_file.write('\n')
                    swmm_inp_file.write('\n[CONDUITS]')
                    swmm_inp_file.write('\n;;               Inlet            Outlet                      Manning    Inlet      Outlet     Init.      Max.')
                    swmm_inp_file.write('\n;;Name           Node             Node             Length     N          Offset     Offset     Flow       Flow')
                    swmm_inp_file.write('\n;;-------------- ---------------- ---------------- ---------- ---------- ---------- ---------- ---------- ----------')

                    SD_conduits_sql =  '''SELECT conduit_name, conduit_inlet, conduit_outlet, conduit_length, conduit_manning, conduit_inlet_offset, 
                                            conduit_outlet_offset, conduit_init_flow, conduit_max_flow 
                                      FROM user_swmm_conduits ORDER BY fid;'''

                    line = '\n{0:16} {1:<16} {2:<16} {3:<10.2f} {4:<10.3f} {5:<10.2f} {6:<10.2f} {7:<10.2f} {8:<10.2f}'
                    conduits_rows = self.gutils.execute(SD_conduits_sql).fetchall()
                    if not conduits_rows:
                        pass
                    else:
                        for row in conduits_rows:
                            swmm_inp_file.write(line.format(*row))
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 070618.1620: error while exporting [CONDUITS] to .INP file!", e)
                    return

                # XSECTIONS ###################################################
                try:
                    swmm_inp_file.write('\n')
                    swmm_inp_file.write('\n[XSECTIONS]')
                    swmm_inp_file.write('\n;;Link           Shape        Geom1      Geom2      Geom3      Geom4      Barrels')
                    swmm_inp_file.write('\n;;-------------- ------------ ---------- ---------- ---------- ---------- ----------')

                    SD_xsections_sql =  '''SELECT conduit_name, xsections_shape, xsections_max_depth, xsections_geom2, xsections_geom3, xsections_geom4, xsections_barrels
                                      FROM user_swmm_conduits ORDER BY fid;'''

                    line = '\n{0:16} {1:<13} {2:<10.2f} {3:<10.2f} {4:<10.3f} {5:<10.2f} {6:<10}'
                    xsections_rows = self.gutils.execute(SD_xsections_sql).fetchall()
                    if not xsections_rows:
                        pass
                    else:
                        for row in xsections_rows:
                            swmm_inp_file.write(line.format(*row))
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 070618.1621: error while exporting [XSECTIONS] to .INP file!", e)
                    return

                # LOSSES ###################################################
                try:
                    swmm_inp_file.write('\n')
                    swmm_inp_file.write('\n[LOSSES]')
                    swmm_inp_file.write('\n;;Link           Inlet      Outlet     Average    Flap Gate')
                    swmm_inp_file.write('\n;;-------------- ---------- ---------- ---------- ----------')

                    SD_losses_sql =  '''SELECT conduit_name, losses_inlet, losses_outlet, losses_average, losses_flapgate
                                      FROM user_swmm_conduits ORDER BY fid;'''

                    line = '\n{0:16} {1:<10} {2:<10} {3:<10.2f} {4:<10}'
                    losses_rows = self.gutils.execute(SD_losses_sql).fetchall()
                    if not losses_rows:
                        pass
                    else:
                        for row in losses_rows:
                            swmm_inp_file.write(line.format(*row))
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 070618.1622: error while exporting [LOSSES] to .INP file!", e)
                    return

                # REPORT ##################################################
                items = self.select_this_INP_group(INP_groups, 'report')
                swmm_inp_file.write('\n\n[REPORT]')
                if items is not None:
                    for line in items[1:]:
                        swmm_inp_file.write("\n" + line)
                else:
                    swmm_inp_file.write('\n')


                # COORDINATES ###################################################
                try:
                    swmm_inp_file.write('\n')
                    swmm_inp_file.write('\n[COORDINATES]')
                    swmm_inp_file.write('\n;;Node           X-Coord            Y-Coord ')
                    swmm_inp_file.write('\n;;-------------- ------------------ ------------------')

                    SD_coordinates_sql = '''SELECT name, ST_AsText(ST_Centroid(GeomFromGPB(geom)))
                                      FROM user_swmm_nodes ORDER BY fid;'''

                    line = '\n{0:16} {1:<18} {2:<18}'
                    coordinates_rows = self.gutils.execute(SD_coordinates_sql).fetchall()
                    if not coordinates_rows:
                        pass
                    else:
                        for row in coordinates_rows:
                            # swmm_inp_file.write(line.format(*row))
                            x = row[:2][1].strip('POINT()').split()[0]
                            y = row[:2][1].strip('POINT()').split()[1]
                            swmm_inp_file.write(line.format(row[0], x, y))
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 070618.16323: error while exporting [COORDINATES] to .INP file!", e)
                    return

                # CONTROLS ##################################################
                items = self.select_this_INP_group(INP_groups, 'controls')
                swmm_inp_file.write('\n\n[CONTROLS]')
                if items is not None:
                    for line in items[1:]:
                        swmm_inp_file.write("\n" + line)
                else:
                    swmm_inp_file.write('\n')

                future_groups = ["FILES", "RAINGAGES", "HYDROGRAPHS", "PROFILES", "EVAPORATION", "TEMPERATURE", "SUBCATCHMENTS",
                                  "SUBAREAS", "INFILTRATION", "AQUIFERS", "GROUNDWATER", "SNOWPACKS", "DIVIDERS",
                                  "STORAGE", "PUMPS", "ORIFICES", "WEIRS", "OUTLETS", "TRANSECTS", "POLLUTANTS",
                                  "LANDUSES", "COVERAGES", "BUILDUP", "WASHOFF", "TREATMENT", "INFLOWS", "DWF",
                                   "PATTERNS", "RDII", "LOADINGS",  "CURVES", "TIMESERIES"]

                for group in future_groups:
                    items = self.select_this_INP_group(INP_groups, group.lower())
                    if items is not None:
                        swmm_inp_file.write("\n[" + group + "]")
                        for line in items[1:]:
                            swmm_inp_file.write("\n" + line)

            self.uc.show_info(swmm_file + "\n\nfile saved with:\n\n" +
                              str(len(junctions_rows)) +   "\t[JUNCTIONS]\n" +
                              str(len(outfalls_rows)) +    "\t[OUTFALLS]\n" +
                              str(len(conduits_rows)) +    "\t[CONDUITS]\n" +
                              str(len(xsections_rows)) +   "\t[XSECTIONS]\n" +
                              str(len(losses_rows)) +      "\t[LOSSES]\n" +
                              str(len(coordinates_rows)) + "\t[COORDINATES]"
                              )
        except Exception as e:
            self.uc.show_error("ERROR 160618.0634: couldn't export .INP file!", e)

    def show_outfalls(self):
        """
        Shows outfalls dialog.

        """
        # See if there are inlets:
        if self.gutils.is_table_empty('user_swmm_nodes'):
            self.uc.bar_warn('User Layer "Storm Drain Nodes" is empty!. Import components from .INP file or shapefile.')
            return

        #  See if there are any Outlet nodes:
        qry = '''SELECT * FROM user_swmm_nodes WHERE sd_type = 'O';'''
        rows = self.gutils.execute(qry).fetchall()
        if not rows:
            self.uc.bar_warn("No oulets defined in 'Storm Drain Nodes' User Layer!")
            return

        dlg_outfalls = OutfallNodesDialog(self.iface, self.lyrs)
        save = dlg_outfalls.exec_()
        if save:
            try:
                dlg_outfalls.save_outfalls()
                self.uc.bar_info("Outfalls saved to 'Storm Drain-Outfalls' User Layer!\n\nSchematize it before saving into SWMMOUTF.DAT.")
            except Exception as e:
                self.uc.bar_warn('Could not save outfalls! Please check if they are correct.')
                return

    def show_inlets(self):
        """
        Shows inlets dialog.

        """
        # See if table is empy:
        if self.gutils.is_table_empty('user_swmm_nodes'):
            self.uc.bar_warn('User Layer "Storm Drain Nodes" is empty!. Import components from .INP file or shapefile.')
            return

        #  See if there are any Inlet nodes:
        qry = '''SELECT * FROM user_swmm_nodes WHERE sd_type = 'I';'''
        rows = self.gutils.execute(qry).fetchall()
        if not rows:
            self.uc.bar_warn("No inlets defined in 'Storm Drain Nodes' User Layer!")
            return

        dlg_inlets = InletNodesDialog(self.iface, self.plot, self.table, self.lyrs)
        save = dlg_inlets.exec_()
        if save:
            try:
                self.uc.show_info("Inlets saved to 'Storm Drain-Inlets' User Layer!\n\nSchematize it before saving into SWMMFLO.DAT.")
            except Exception as e:
                self.uc.bar_warn('Could not save Inlets! Please check if they are correct.')
                return

    def show_conduits(self):
        """
        Shows conduits dialog.

        """
        # See if there are conduits:
        if self.gutils.is_table_empty('user_swmm_conduits'):
            self.uc.bar_warn('User Layer "Storm Drain Conduits" is empty!. Import components from .INP file or shapefile.')
            return

        dlg_conduits = ConduitsDialog(self.iface, self.lyrs)
        save = dlg_conduits.exec_()
        if save:
            try:
                dlg_conduits.save_conduits()
                self.uc.bar_info("Conduits saved to 'Storm Drain-Conduits' User Layer!\n\nSchematize it before saving into SWMMOUTF.DAT.")
            except Exception as e:
                self.uc.bar_warn('Could not save conduits! Please check if they are correct.')
                return

    def import_hydraulics(self):
        """
        Shows import shapefile dialog.

        """
        # # See if there are inlets:
        # if self.gutils.is_table_empty('user_swmm_conduits'):
        #     self.uc.bar_warn('User Layer "Storm Drain Conduits" is empty!.')
        #     return
        # self.uc.clear_bar_messages()
        #
        # if self.gutils.is_table_empty('user_model_boundary'):
        #     self.uc.bar_warn('There is no computational domain! Please digitize it before running tool.')
        #     return
        # if self.gutils.is_table_empty('grid'):
        #     self.uc.bar_warn('There is no grid! Please create it before running tool.')
        #     return

        dlg_shapefile = StormDrainShapefile(self.con, self.iface, self.lyrs, self.tables)
        dlg_shapefile.components_tabWidget.setCurrentPage = 0
        save = dlg_shapefile.exec_()
        if save:
            try:
                if dlg_shapefile.saveSelected:
                    self.uc.bar_info("Storm drain components (inlets, outfall, and/or conduits) from hydraulic layers saved.")

            except Exception as e:
                self.uc.bar_error("ERROR while saving storm drain components from hydraulic layers!.")
        # else:
        #     self.uc.bar_warn("Storm drain components not saved!")

    def block_saving(self):
        try_disconnect(self.inlet_data_model.dataChanged, self.save_rtables_data)

    def unblock_saving(self):
        self.inlet_data_model.dataChanged.connect(self.save_rtables_data)

    def itemDataChangedSlot(self, item, old_value, new_value, role, save=True):
        """
        Slot used to push changes of existing items onto undoStack.
        """
        if role == Qt.EditRole:
            command = CommandItemEdit(self, item, old_value, new_value,
                                      "Text changed from '{0}' to '{1}'".format(old_value, new_value))
            self.tview.undoStack.push(command)
            return True

    def populate_rtables(self):
        self.cbo_rating_tables.clear()
        for row in self.inletRT.get_rating_tables():
            rt_fid, name = [x if x is not None else '' for x in row]
            self.cbo_rating_tables.addItem(name, rt_fid)

    def add_rtables(self):
        if not self.inletRT:
            return
        self.inletRT.add_rating_table()
        self.populate_rtables()

    def delete_rtables(self):
        if not self.inletRT:
            return
        idx = self.cbo_rating_tables.currentIndex()
        rt_fid = self.cbo_rating_tables.itemData(idx)
        self.inletRT.del_rating_table(rt_fid)
        self.populate_rtables()

    def rename_rtables(self):
        if not self.inletRT:
            return
        new_name, ok = QInputDialog.getText(None, 'Change rating table name', 'New name:')
        if not ok or not new_name:
            return
        if not self.cbo_rating_tables.findText(new_name) == -1:
            msg = 'Rating table with name {} already exists in the database. Please, choose another name.'.format(
                new_name)
            self.uc.show_warn(msg)
            return
        idx = self.cbo_rating_tables.currentIndex()
        rt_fid = self.cbo_rating_tables.itemData(idx)
        self.inletRT.set_rating_table_data_name(rt_fid, new_name)
        self.populate_rtables()

    def populate_rtables_data(self):
        idx = self.cbo_rating_tables.currentIndex()
        rt_fid = self.cbo_rating_tables.itemData(idx)
        self.inlet_series_data = self.inletRT.get_rating_tables_data(rt_fid)
        if not self.inlet_series_data:
            return
        self.create_plot()
        self.tview.undoStack.clear()
        self.tview.setModel(self.inlet_data_model)
        self.inlet_data_model.clear()
        self.inlet_data_model.setHorizontalHeaderLabels(['Depth', 'Q'])
        self.d1, self.d1 = [[], []]
        for row in self.inlet_series_data:
            items = [StandardItem('{:.4f}'.format(x)) if x is not None else StandardItem('') for x in row]
            self.inlet_data_model.appendRow(items)
            self.d1.append(row[0] if not row[0] is None else float('NaN'))
            self.d2.append(row[1] if not row[1] is None else float('NaN'))
        rc = self.inlet_data_model.rowCount()
        if rc < 500:
            for row in range(rc, 500 + 1):
                items = [StandardItem(x) for x in ('',) * 2]
                self.inlet_data_model.appendRow(items)
        self.tview.horizontalHeader().setStretchLastSection(True)
        for col in range(2):
            self.tview.setColumnWidth(col, 100)
        for i in range(self.inlet_data_model.rowCount()):
            self.tview.setRowHeight(i, 20)
        self.update_plot()

    def save_rtables_data(self):
        idx = self.cbo_rating_tables.currentIndex()
        rt_fid = self.cbo_rating_tables.itemData(idx)
        self.update_plot()
        rt_data = []

        for i in range(self.inlet_data_model.rowCount()):
            # save only rows with a number in the first column
            if is_number(m_fdata(self.inlet_data_model, i, 0)) and not isnan(m_fdata(self.inlet_data_model, i, 0)):
                rt_data.append(
                    (
                        rt_fid,
                        m_fdata(self.inlet_data_model, i, 0),
                        m_fdata(self.inlet_data_model, i, 1)
                    )
                )
            else:
                pass
        data_name = self.cbo_rating_tables.currentText()
        self.inletRT.set_rating_table_data(rt_fid, data_name, rt_data)

    def create_plot(self):
        self.plot.clear()
        self.plot_item_name = 'Rating tables'
        self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))

    def update_plot(self):
        if not self.plot_item_name:
            return
        self.d1, self.d2 = [[], []]
        for i in range(self.inlet_data_model.rowCount()):
            self.d1.append(m_fdata(self.inlet_data_model, i, 0))
            self.d2.append(m_fdata(self.inlet_data_model, i, 1))
        self.plot.update_item(self.plot_item_name, [self.d1, self.d2])
