# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import traceback
from ui_utils import load_ui, set_icon
from flo2d.geopackage_utils import GeoPackageUtils
from flo2d.user_communication import UserCommunication
from PyQt4.QtCore import Qt
from PyQt4.QtGui import QApplication, QInputDialog
from flo2d.flo2d_tools.grid_tools import square_grid, update_roughness, evaluate_arfwrf, ZonalStatistics
from flo2d.gui.dlg_grid_elev import GridCorrectionDialog
from flo2d.gui.dlg_sampling_elev import SamplingElevDialog
from flo2d.gui.dlg_sampling_mann import SamplingManningDialog
from flo2d.gui.dlg_sampling_xyz import SamplingXYZDialog

uiDialog, qtBaseClass = load_ui('grid_tools_widget')


class GridToolsWidget(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = None
        self.gutils = None

        set_icon(self.create_grid_btn, 'create_grid.svg')
        set_icon(self.raster_elevation_btn, 'sample_elev.svg')
        set_icon(self.xyz_elevation_btn, 'sample_elev_xyz.svg')
        set_icon(self.polygon_elevation_btn, 'sample_elev_polygon.svg')
        set_icon(self.roughness_btn, 'sample_manning.svg')
        set_icon(self.arfwrf_btn, 'eval_arfwrf.svg')

        self.create_grid_btn.clicked.connect(self.create_grid)
        self.raster_elevation_btn.clicked.connect(self.raster_elevation)
        self.xyz_elevation_btn.clicked.connect(self.xyz_elevation)
        self.polygon_elevation_btn.clicked.connect(self.correct_elevation)
        self.roughness_btn.clicked.connect(self.get_roughness)
        self.arfwrf_btn.clicked.connect(self.eval_arfwrf)

    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def get_cell_size(self):
        """
        Get cell size from:
            - Computational Domain attr table (if defined, will be written to cont table)
            - cont table
            - ask user
        """
        bl = self.lyrs.data['user_model_boundary']['qlyr']
        bfeat = bl.getFeatures().next()
        if bfeat['cell_size']:
            cs = bfeat['cell_size']
            if cs <= 0:
                self.uc.show_warn('Cell size must be positive. Change the feature attribute value in Computational Domain layer.')
                return None
            self.gutils.set_cont_par('CELLSIZE', cs)
        else:
            cs = self.gutils.get_cont_par('CELLSIZE')
            cs = None if cs == '' else cs
        if cs:
            if cs <= 0:
                self.uc.show_warn('Cell size must be positive. Change the feature attribute value in Computational Domain layer or default cell size in the project settings.')
                return None
            return cs
        else:
            r, ok = QInputDialog.getDouble(None, 'Grid Cell Size', 'Enter grid element cell size',
                                           value=100, min=0.1, max=99999)
            if ok:
                cs = r
                self.gutils.set_cont_par('CELLSIZE', cs)
            else:
                return None

    def create_grid(self):
        if not self.lyrs.save_edits_and_proceed('Computational Domain'):
            return
        if self.gutils.is_table_empty('user_model_boundary'):
            self.uc.bar_warn('There is no Computational Domain! Please digitize it before running tool.')
            return
        if self.gutils.count('user_model_boundary') > 1:
            warn = 'There are multiple features created on Computational Domain layer.\n'
            warn += 'Only ONE will be used with the lowest fid (first created).'
            self.uc.show_warn(warn)
        if not self.gutils.is_table_empty('grid'):
            if not self.uc.question('There is a grid already saved in the database. Overwrite it?'):
                return
        if not self.get_cell_size():
            return
        try:
            self.uc.progress_bar('Creating grid...')
            QApplication.setOverrideCursor(Qt.WaitCursor)
            bl = self.lyrs.data['user_model_boundary']['qlyr']
            square_grid(self.gutils, bl)
            grid_lyr = self.lyrs.data['grid']['qlyr']
            self.lyrs.update_layer_extents(grid_lyr)
            if grid_lyr:
                grid_lyr.triggerRepaint()
            self.uc.clear_bar_messages()
            QApplication.restoreOverrideCursor()
            self.uc.show_info('Grid created!')
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.show_warn('Creating grid aborted! Please check Computational Domain layer.')

    def raster_elevation(self):
        if self.gutils.is_table_empty('user_model_boundary'):
            self.uc.bar_warn('There is no computational domain! Please digitize it before running tool.')
            return
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return
        cell_size = self.get_cell_size()
        dlg = SamplingElevDialog(self.con, self.iface, self.lyrs, cell_size)
        ok = dlg.exec_()
        if ok:
            pass
        else:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            res = dlg.probe_elevation()
            if res:
                dlg.show_probing_result_info()
            QApplication.restoreOverrideCursor()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn('Probing grid elevation failed! Please check your raster layer.')

    def xyz_elevation(self):
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return
        dlg = SamplingXYZDialog(self.con, self.iface, self.lyrs)
        ok = dlg.exec_()
        if ok:
            pass
        else:
            return
        points_lyr = dlg.current_lyr
        zfield = dlg.fields_cbo.currentText()
        calc_type = dlg.calc_cbo.currentText()
        search_distance = dlg.search_spin_box.value()

        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            grid_lyr = self.lyrs.data['grid']['qlyr']
            zs = ZonalStatistics(self.gutils, grid_lyr, points_lyr, zfield, calc_type, search_distance)
            points_elevation = zs.points_elevation()
            zs.set_elevation(points_elevation)
            cmd, out = zs.rasterize_grid()
            self.uc.log_info(cmd)
            self.uc.log_info(out)
            cmd, out = zs.fill_nodata()
            self.uc.log_info(cmd)
            self.uc.log_info(out)
            null_elevation = zs.null_elevation()
            zs.set_elevation(null_elevation)
            zs.remove_rasters()
            QApplication.restoreOverrideCursor()
            self.uc.show_info('Calculating elevation finished!')
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn('Calculating grid elevation aborted! Please check elevation points layer.')

    def correct_elevation(self):
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return
        lyrs = ['Elevation Points', 'Elevation Polygons', 'Blocked areas']
        for lyr in lyrs:
            if not self.lyrs.save_edits_and_proceed(lyr):
                return
        correct_dlg = GridCorrectionDialog(self.con, self.iface, self.lyrs)
        ok = correct_dlg.exec_()
        if not ok:
            return
        tab = correct_dlg.correction_tab.currentIndex()
        if tab == 0:
            if not correct_dlg.internal_methods:
                self.uc.show_warn('Please choose at least one elevation source!')
                return
            method = correct_dlg.run_internal
        else:
            correct_dlg.setup_external_method()
            if correct_dlg.external_method is None:
                self.uc.show_warn('Please choose at least one elevation source!')
                return
            method = correct_dlg.run_external
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            method()
            QApplication.restoreOverrideCursor()
            self.uc.show_info('Assigning grid elevation finished!')
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn('Assigning grid elevation aborted! Please check your input layers.')

    def get_roughness(self):
        if not self.lyrs.save_edits_and_proceed('Roughness'):
            return
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return
        mann_dlg = SamplingManningDialog(self.con, self.iface, self.lyrs)
        ok = mann_dlg.exec_()
        if ok:
            pass
        else:
            return
        if mann_dlg.allGridElemsRadio.isChecked():
            rough_lyr = mann_dlg.current_lyr
            nfield = mann_dlg.srcFieldCbo.currentText()
            flag = True
        else:
            rough_name = 'Roughness'
            rough_lyr = self.lyrs.get_layer_by_name(rough_name, group=self.lyrs.group).layer()
            nfield = 'n'
            flag = False
            if self.gutils.is_table_empty('user_roughness'):
                self.uc.show_warn('There is no roughness polygons! Please digitize them before running tool.')
                return
            else:
                pass
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            grid_lyr = self.lyrs.data['grid']['qlyr']
            update_roughness(self.gutils, grid_lyr, rough_lyr, nfield, reset=flag)
            QApplication.restoreOverrideCursor()
            self.uc.show_info('Assigning roughness finished!')
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.uc.show_warn('Assigning roughness aborted! Please check roughness layer.')

    def eval_arfwrf(self):
        grid_empty = self.gutils.is_table_empty('grid')
        if grid_empty:
            self.uc.bar_warn('There is no grid. Please, create it before evaluating the reduction factors.')
            return
        else:
            pass
        if not self.gutils.is_table_empty('arfwrf'):
            q = 'There are some ARFs and WRFs already defined in the database. Overwrite it?\n\n'
            q += 'Please, note that the new reduction factors will be evaluated for existing blocked ares ONLY.'
            if not self.uc.question(q):
                return
        if not self.lyrs.save_edits_and_proceed('Blocked areas'):
            return
        if self.gutils.is_table_empty('blocked_areas'):
            self.uc.bar_warn('There is no any blocking polygons! Please digitize them before running tool.')
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            grid_lyr = self.lyrs.data['grid']['qlyr']
            user_arf_lyr = self.lyrs.data['blocked_areas']['qlyr']
            evaluate_arfwrf(self.gutils, grid_lyr, user_arf_lyr)
            arf_lyr = self.lyrs.data['blocked_cells']['qlyr']
            arf_lyr.reload()
            self.lyrs.update_layer_extents(arf_lyr)

            self.lyrs.update_style_blocked(arf_lyr.id())
            self.iface.mapCanvas().clearCache()
            user_arf_lyr.triggerRepaint()
            QApplication.restoreOverrideCursor()
            self.uc.show_info('ARF and WRF values calculated!')
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn('Evaluation of ARFs and WRFs failed! Please check your blocked areas user layer.')
            QApplication.restoreOverrideCursor()
