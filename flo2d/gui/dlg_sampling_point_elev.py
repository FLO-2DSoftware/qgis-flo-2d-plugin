# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import sys
from subprocess import Popen, PIPE, STDOUT
import traceback
import time
import multiprocessing

from qgis.PyQt.QtCore import QSettings,pyqtSignal
from qgis.PyQt.QtWidgets import QFileDialog
from qgis.core import QgsRasterLayer
from PyQt5.QtGui import QTextCursor

from ..flo2d_tools.grid_tools import raster2grid, grid_has_empty_elev
from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..misc import point_elev

uiDialog, qtBaseClass = load_ui("sampling_point_elev")

url_about_resampling_algorithm = r"https://gdal.org/programs/gdal_grid.html#interpolation-algorithms"
url_about_resampling_algorithm_alt = r"https://gdal.org/tutorials/gdal_grid_tut.html"
        
class SamplingPointElevDialog(qtBaseClass, uiDialog):
    logMessage = pyqtSignal(str,bool,name='logMessage')

    def __init__(self, con, iface, lyrs, cell_size):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.con = con
        self.iface = iface
        self.lyrs = lyrs
        self.grid = None
        self.cell_size = float(cell_size)
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)
        self.gpkg_path = self.gutils.get_gpkg_path()
        self.uc = UserCommunication(iface, "FLO-2D")
        self.src_nodata = -9999
        self.probe_raster = None
        self.radiusSBox.setHidden(True)
        self.max_radius_lab.setHidden(True)
        self.populate_alg_cbo()
        self.resampling_url_id = 0
        self.configure_gdal_sliders()

        # Redirects gdal prints to GUI
        point_elev.GUI_STDIO = self

        # connections
        self.logMessage.connect(self.log_message)
        self.browseSrcBtn.clicked.connect(self.browse_src_file)
        self.algCbo.currentIndexChanged.connect(self.resampling_method_changed)
        self.algInfoBtn.clicked.connect(self.open_resampling_url)
        self.runBtn.clicked.connect(self.compute)
        self.closeBtn.clicked.connect(lambda x: self.reject())
        self.thread_count_slider.valueChanged.connect(self.slider_changed)
        self.cache_slider.valueChanged.connect(self.slider_changed)

    def browse_src_file(self):
        """
        Users pick a source raster or CSV file from file explorer.
        """
        s = QSettings()
        last_elev_file_dir = s.value("FLO-2D/lastElevFileDir", "")
        self.src_file, __ = QFileDialog.getOpenFileName(None, "Choose elevation CSV file or raster...",
                                                   directory=last_elev_file_dir,
                                                   filter='Elev (*.tif *.csv)')
        if not self.src_file:
            return
        s.setValue("FLO-2D/lastElevFileDir", os.path.dirname(self.src_file))
        self.elev_file_lab.setText(self.src_file)
        self.elev_file_lab.setToolTip(self.src_file)

    def populate_alg_cbo(self):
        """
        Populate resample algorithm combobox.
        """
        for m in point_elev.GDALGRID_METHOD_DESC:
            self.algCbo.addItem(m)
        self.algCbo.addItem('Average GDS') # additional method not using GDAL_Grid
        self.algCbo.setCurrentIndex(0)
        self.resampling_method_changed(0) 
        self.default_resampling_options()   
    
    def configure_gdal_sliders(self):
        thread_count = multiprocessing.cpu_count()
        cachemax_min = int(point_elev.gdal_default_cachemax/(1024*1024.0)) # MB
        cachemax_max = min(cachemax_min*2,max(2000,cachemax_min)) # not more than 2 GB or inital cachemax

        self.thread_count_slider.setRange(1,thread_count)
        self.thread_count_slider.setSingleStep(1)
        self.thread_count_slider.setPageStep(1)
        self.thread_count_slider.setTickInterval(1)
        self.thread_count_slider.setValue(thread_count - 2) # assuming 2 hyper threads per core

        cache_step = int((cachemax_max - cachemax_min)/4.0) 
        self.cache_slider.setRange(cachemax_min, cachemax_max)
        self.cache_slider.setTickInterval(cache_step)
        self.cache_slider.setSingleStep(cache_step)

        thread_count = '{0:.0f}'.format(self.thread_count_slider.value()) 
        cache_value = '{0:.0f} Mb'.format(self.cache_slider.value()) 
        self.thread_count_slider.setToolTip(thread_count)
        self.cache_slider.setToolTip(cache_value)
    
    def slider_changed(self,value=None):
        thread_count = '{0:.0f}'.format(self.thread_count_slider.value()) 
        cache_value = '{0:.0f} Mb'.format(self.cache_slider.value()) 
        self.log_message('CPU thread count = %s'%thread_count)
        self.log_message('cache max = %s'%cache_value)
        self.thread_count_slider.setToolTip(thread_count)
        self.cache_slider.setToolTip(cache_value)

    def open_resampling_url(self):
        if self.resampling_url_id == 0:
            self.resampling_url_id = 1
            self.algInfoBtn.setText('??')
            os.startfile(url_about_resampling_algorithm)
        else:    
            self.resampling_url_id = 0
            self.algInfoBtn.setText('?')
            os.startfile(url_about_resampling_algorithm_alt)

    def resampling_method_changed(self,i):
        method = self.algCbo.currentText()
        params = point_elev.GDALGRID_METHOD_PARAM_DICT.get(method,[])
        for param in point_elev.GDALGRID_METHOD_PARAMS:
            _param =  param.replace(' ','_')
            widget = getattr(self,_param)
            if method == 'Average GDS':
                if param == 'nodata':
                    widget.setEnabled(True)
                else:    
                    widget.setEnabled(False)
            elif param in params:
                widget.setEnabled(True)
            else:    
                widget.setEnabled(False)

    def default_resampling_options(self):            
        for param in point_elev.GDALGRID_METHOD_PARAMS:
            _param =  param.replace(' ','_')
            widget = getattr(self,_param)
            if _param == 'power':
                widget.setValue(2)
            elif _param == 'smoothing':
                widget.setValue(0)
            elif _param == 'angle':
                widget.setValue(0)
            elif _param in ('radius','radius1','radius2'):
                widget.setValue(self.cell_size/2.0)
            elif _param == 'min_points':
                widget.setValue(1)
            elif _param == 'max_points':
                widget.setValue(0)
            elif _param == 'nodata':
                widget.setPlainText(str(self.src_nodata))
    
    def get_resampling_options(self):
        #
        method = self.algCbo.currentText()
        params = {}
        for param in point_elev.GDALGRID_METHOD_PARAMS:
            _param =  param.replace(' ','_')
            if _param == 'nodata':
                value = (getattr(self,_param)).toPlainText()
            else:    
                value = (getattr(self,_param)).value()
            self.uc.log_info('%s = %r'%(_param,value))    
            #if param in ['min_points', 'max_points']:
            params[_param] = value
        option = point_elev.ResamplingOption(method,**params)
        self.uc.log_info('Point sampling resample info = %r'%option.string())
        return option

    def get_raster_info(self):
        """
        Get all data needed for GDAL Warp.
        """
        result = {}
        # grid extents
        self.grid = self.lyrs.get_layer_by_name("Grid", self.lyrs.group).layer()
        self.lyrs.update_layer_extents(self.grid)
        grid_ext = self.grid.extent()
        xmin = grid_ext.xMinimum()
        xmax = grid_ext.xMaximum()
        ymin = grid_ext.yMinimum()
        ymax = grid_ext.yMaximum()
        output_bounds = (xmin, ymin, xmax, ymax)
        # Verify following two lines are correct assumptions
        rows = int((ymax - ymin)/self.cell_size) 
        cols = int((xmax - xmin)/self.cell_size)
        shape = (rows,cols)
        crs_proj4 = self.grid.crs().toProj4()
        try:
            src_nodata = float(self.srcNoDataEdit.text())
        except:
            src_nodata = float(self.src_nodata)
        
        result.update([('extents', output_bounds), 
                       ('shape', shape),
                       ('srs', crs_proj4),
                       ('nodata', src_nodata),
                     ])
        self.uc.log_info('Point sampling raster info = %r'%result)
        return result

    def compute_average_gds(self,csv_file,nodata=None):
        return self.log_message('Average method similar to GDS NOT implemented')

    @point_elev.timer
    def probe_elevation(self):
        """
        Resample raster to be aligned with the grid, then probe values and update elements elevation attr.
        """
        src_file = self.src_file
        if os.path.exists(src_file):
            profile = self.get_raster_info()
            src_point_file = src_file

            if src_file.endswith('.tif') and self.algCbo.currentText() == 'Average GDS':
                self.log_message('The data source must be CSV for Average GDS method')
                return

            # GDS Average Approach
            if self.algCbo.currentText() == 'Average GDS':
                self.log_message('>>> Running Average GDS method')
                result = self.compute_average_gds(src_point_file, nodata = profile['nodata'])
                raise NotImplementedError(result)

            # GDAL_Grid applied for following
            if src_file.endswith('.tif'):
                base_path, ext = os.path.splitext(src_file)
                src_point_file = base_path + '_xyz.csv'
                dest_clip_raster = base_path + '_clipped.tif'

                # clip raster to boundary
                if os.path.exists(dest_clip_raster):
                    os.unlink(dest_clip_raster)
                point_elev.clip_raster_aligned(src_file, dest_clip_raster, profile['extents'])

                # convert to point file
                if os.path.exists(src_point_file):
                    os.unlink(src_point_file)
                point_elev.raster_to_xyz(dest_clip_raster, 
                                         src_point_file, 
                                         False,
                                         remove_nodata = self.fillNoDataChBox.isChecked())
            
            # process the XYZ point file
            resample = self.get_resampling_options()
            raster_outpath = point_elev.xyz_to_raster(src_point_file,
                                                      extents = profile['extents'],
                                                      shape = profile['shape'],
                                                      resampling_option = resample,
                                                      srs = profile['srs'])

            # Fill NODATA raster cells if desired
            if self.fillNoDataChBox.isChecked():
                self.fill_nodata(raster_outpath)
            else:
                pass
            self.log_message('>>> Sampling Raster-to-Grid')
            sampler = raster2grid(self.grid, raster_outpath)
            qry = "UPDATE grid SET elevation=? WHERE fid=?;"
            self.con.executemany(qry, sampler)
            self.con.commit()
            self.log_message('Ok.')
            self.show_probing_result_info()

    @point_elev.timer
    def fill_nodata(self,raster_file):
        self.log_message('>>> Filling nodata values')
        opts = ["-md {}".format(self.radiusSBox.value())]
        cmd = 'gdal_fillnodata {} "{}"'.format(" ".join([opt for opt in opts]), raster_file)
        proc = Popen(cmd, shell=True, stdin=open(os.devnull), stdout=PIPE, stderr=STDOUT, universal_newlines=True)
        out = proc.communicate()
        for line in out:
            self.uc.log_info(line)
        self.log_message('Ok.')

    @point_elev.timer
    def show_probing_result_info(self):
        self.log_message('>>> Showing Probing Info')
        null_nr = grid_has_empty_elev(self.gutils)
        if null_nr:
            msg = "Sampling done.\n"
            msg += "Warning: There are {} grid elements that have no elevation value.".format(null_nr)
            #self.uc.show_info(msg)
            self.log_message(msg)
        else:
            self.log_message("Sampling done.")
    
    def log_message(self,mesg,new_line=True,progress_percent=None):
        self.uc.log_info(mesg)
        editor = self.console_edit
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        if new_line:
            cursor.insertText(mesg+'\n')
        else:
            cursor.insertText(mesg)
        editor.setTextCursor(cursor)
        editor.ensureCursorVisible()
        editor.repaint()
 
    def compute(self):
        self.console_edit.clear()
        starttime = time.asctime()
        self.log_message('Performing Computation ...')
        self.log_message(starttime)
        try:
            self.slider_changed()
            point_elev.gdal.SetConfigOption('GDAL_CACHEMAX','{0:.2f}'.format(self.cache_slider.value()))
            point_elev.gdal.SetConfigOption('GDAL_NUM_THREADS','{0:.2f}'.format(self.thread_count_slider.value()))
            self.probe_elevation()
        except:
            self.log_message(traceback.format_exc())
            self.log_message('Computation Failed.')
        else:    
            endtime = time.asctime()
            self.log_message(endtime)
            self.log_message('Finished Computation.')

        finally:    
            point_elev.gdal.SetConfigOption('GDAL_CACHEMAX', '{0:.2f}'.format(point_elev.gdal_default_cachemax/(1024.0*1024))) # Mb
            point_elev.gdal.SetConfigOption('GDAL_NUM_THREADS',None)

