# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import math
from subprocess import Popen, PIPE, STDOUT

import warnings
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QFileDialog
from qgis.core import QgsRasterLayer
from qgis.gui import QgsProjectionSelectionWidget
from ..flo2d_tools.grid_tools import raster2grid, grid_has_empty_elev
from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
uiDialog, qtBaseClass = load_ui('sampling_elev')

try:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        from osgeo import gdal
        gdal.UseExceptions()
        
    gdalAvailable = True
except:
    gdalAvailable = False

class SamplingElevDialog(qtBaseClass, uiDialog):

    RTYPE = {
        1: 'Byte',
        2: 'UInt16',
        3: 'Int16',
        4: 'UInt32',
        5: 'Int32',
        6: 'Float32',
        7: 'Float64'
    }

    def __init__(self, con, iface, lyrs, cell_size):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.con = con
        self.iface = iface
        self.lyrs = lyrs
        self.grid = None #self.lyrs.get_layer_by_name('Grid', self.lyrs.group).layer()
        self.cell_size = float(cell_size)
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)
        self.gpkg_path = self.gutils.get_gpkg_path()
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.grid_nodata = -9999
        self.src_nodata = -9999 #not used
        self.probe_raster = None
        self.radiusSBox.setHidden(True)
        self.max_radius_lab.setHidden(True)
        self.label_4.setHidden(True)
        self.srcNoDataEdit.setHidden(True)
        self.src_srs = None
        self.src_type = None
        self.browseSrcBtn.clicked.connect(self.browse_src_raster)
        self.browseSrcProjectionBtn.clicked.connect(self.browse_src_projection)
        self.srcRasterCbo.currentIndexChanged.connect(self.set_src_projection)
        self.engineCbo.currentIndexChanged.connect(self.populate_alg_cbo)
        self.populate_raster_cbo()
        self.populate_alg_cbo()

    def populate_raster_cbo(self):
        """
        Get loaded rasters into combobox.
        """
        rasters = self.lyrs.list_group_rlayers()
        self.srcRasterCbo.blockSignals(True)
        for r in rasters:
            self.srcRasterCbo.addItem(r.name(), r.dataProvider().dataSourceUri())
        self.srcRasterCbo.blockSignals(False)
        self.srcRasterCbo.currentIndexChanged.emit(0)
        
    def browse_src_raster(self):
        """
        Users pick a source raster not loaded into project.
        """
        s = QSettings()
        last_elev_raster_dir = s.value('FLO-2D/lastElevRasterDir', '')
        if self.engineCbo.currentText() == 'Gdalgrid':
            browse_filter = 'Topo (*.tif *.vrt *.csv)'
        else:
            browse_filter = 'Topo (*.tif *.vrt)'
        self.src, __ = QFileDialog.getOpenFileName(None,
                                                   'Choose elevation raster...',
                                                   directory=last_elev_raster_dir,
                                                   filter = browse_filter)
        if not self.src:
            return
        s.setValue('FLO-2D/lastElevRasterDir', os.path.dirname(self.src))
        if self.srcRasterCbo.findData(self.src) == -1:
            bname = os.path.basename(self.src)
            self.srcRasterCbo.addItem(bname, self.src)
            self.srcRasterCbo.setCurrentIndex(len(self.srcRasterCbo)-1)
        else:
            self.srcRasterCbo.setCurrentIndex(self.srcRasterCbo.findData(self.src))

    def browse_src_projection(self):
        self.set_src_projection(browse=True)

    def set_src_projection(self,browse=False):
        raster_path = self.srcRasterCbo.itemData(self.srcRasterCbo.currentIndex())
        if raster_path:
            if raster_path.endswith(('.csv','.CSV')):
                self.update_grid_info()
                self.src_srs = self.grid_srs
                self.src_type = 6 #dummy
            else:
                raster_lyr = QgsRasterLayer(raster_path)
                self.src_srs = raster_lyr.crs()
                self.src_type = raster_lyr.dataProvider().dataType(1)
            self.srcProjection.setText(self.src_srs.description())
            if browse is True:
                proj_selector = QgsProjectionSelectionWidget()
                proj_selector.setCrs(self.src_srs)
                proj_selector.selectCrs()
                if proj_selector.crs().isValid():
                    self.src_srs = proj_selector.crs()
                    self.srcProjection.setText(self.src_srs.description())
            self.update_resampling_engine()

    def populate_alg_cbo(self):
        """
        Populate resample algorithm combobox.
        """
        warp_methods = {
            "near": "Nearest neighbour",
            "bilinear": "Bilinear",
            "cubic": "Cubic",
            "cubicspline": "Cubic spline",
            "lanczos": "Lanczos",
            "average": "Average of all non-NODATA pixels",
            "mode": "Mode - Select the value which appears most often",
            "max": "Maximum value from all non-NODATA pixels",
            "min": "Minimum value from all non-NODATA pixels",
            "med": "Median value of all non-NODATA pixels",
            "q1": "q1 - First quartile value of all non-NODATA",
            "q3": "q1 - Third quartile value of all non-NODATA"
        }
        gdalgrid_methods = { 
                            "average": "Moving average",
                            "inverse distance": "Inverse distance to a power",
                            "inverse distance 2": "Inverse distance to power with nearest neighbor searching",
                            "nearest": "Nearest neighborhood",
                            "linear": "Linear Interpolation",
                            }
        if self.engineCbo.currentText() == 'Gdalgrid':
            met = gdalgrid_methods
        else:
            met = warp_methods
            
        self.algCbo.blockSignals(True)
        self.algCbo.clear()
        for m in sorted(met.keys()):
            self.algCbo.addItem(met[m], m)
            self.algCbo.setCurrentIndex(0)
        self.algCbo.blockSignals(False)
        self.algCbo.currentIndexChanged.emit(0)
        
    def update_resampling_engine(self):
        raster_path = self.srcRasterCbo.itemData(self.srcRasterCbo.currentIndex())
        if raster_path:
            warp_index = self.engineCbo.findText('Gdalwarp')
            warp_item = self.engineCbo.model().item(warp_index)
            if raster_path.endswith(('.csv','.CSV')):
                self.engineCbo.setCurrentText('Gdalgrid')
                warp_item.setEnabled(False)
            else:
                warp_item.setEnabled(True)
                
    def get_worp_opts_data(self):
        """
        Get all data needed for GDAL Warp.
        """
        self.update_grid_info()
        # NODATA
        # use -9999

    def probe_elevation(self):
        """
        Resample raster to be aligned with the grid, then probe values and update elements elevation attr.
        """
        self.update_grid_info()
        if self.engineCbo.currentText() == 'Gdalgrid':
            src_raster = self.create_gdalgrid()
            out_raster = src_raster
        elif self.engineCbo.currentText() == 'Gdalwarp':
            src_raster = self.srcRasterCbo.itemData(self.srcRasterCbo.currentIndex())
            out_raster = '{}_interp.tif'.format(src_raster[:-4]) # Raster name with suffix '_interp.tif'
            try:
                if os.path.isfile(out_raster):
                    os.remove(out_raster)
            except OSError:
                msg = 'WARNING 060319.1651: Couldn\'t remove existing raster:\n{}\nChoose another filename.'.format(out_raster)
                self.uc.show_warn(msg)
                return False
            self.get_worp_opts_data()
            opts = [
                '-of GTiff',
                '-ot {}'.format(self.RTYPE[self.src_type]),
                '-tr {0} {0}'.format(self.cell_size),
                '-te {}'.format(' '.join([str(c) for c in self.grid_bounds])),
                '-te_srs "{}"'.format(self.grid_srs.toProj4()),
                '-s_srs "{}"'.format(self.src_srs.toProj4()),
                '-t_srs "{}"'.format(self.grid_srs.toProj4()),
                '-dstnodata {}'.format(self.grid_nodata),
                '-r {}'.format(self.algCbo.itemData(self.algCbo.currentIndex())),
                '-co COMPRESS=LZW',
                '-wo OPTIMIZE_SIZE=TRUE'
            ]
            if self.multiThreadChBox.isChecked():
                opts.append('-multi -wo NUM_THREADS=ALL_CPUS')
            else:
                pass
            cmd = 'gdalwarp {} "{}" "{}"'.format(' '.join([opt for opt in opts]), src_raster, out_raster)
            proc = Popen(cmd, shell=True, stdin=open(os.devnull), stdout=PIPE, stderr=STDOUT, universal_newlines=True)
            out = proc.communicate()
            for line in out:
                self.uc.log_info(line)
            # Fill NODATA raster cells if desired
            
        if self.fillNoDataChBox.isChecked():
            self.fill_nodata(out_raster)
        else:
            pass
            
        if src_raster:
            sampler = raster2grid(self.grid, src_raster)
            qry = 'UPDATE grid SET elevation=? WHERE fid=?;'
            self.con.executemany(qry, sampler)
            self.con.commit()

        return True

    def fill_nodata(self,out_raster):
        opts = [
            '-md {}'.format(self.radiusSBox.value())
        ]
        cmd = 'gdal_fillnodata {} "{}"'.format(' '.join([opt for opt in opts]), out_raster)
        proc = Popen(cmd, shell=True, stdin=open(os.devnull), stdout=PIPE, stderr=STDOUT, universal_newlines=True)
        out = proc.communicate()
        for line in out:
            self.uc.log_info(line)

    def show_probing_result_info(self):
        null_nr = grid_has_empty_elev(self.gutils)
        if null_nr:
            msg = 'Sampling done.\n'
            msg += 'Warning: There are {} grid elements that have no elevation value.'.format(null_nr)
            self.uc.show_info(msg)
        else:
            self.uc.show_info('Sampling done.')

    def create_gdalgrid(self):
        self.uc.log_info('Running create_gdalgrid function')
        src_raster = self.srcRasterCbo.itemData(self.srcRasterCbo.currentIndex())
        
        if src_raster.endswith(('.csv','.CSV')):
            xyz_file = src_raster
        else:
            xyz_file = self._raster_to_xyz(src_raster)
        self.uc.log_info('xyz_file is %s'%xyz_file)
        if xyz_file:
            raster_out = self._xyz_to_grid(xyz_file)
            return raster_out
           
    def update_grid_info(self):
        self.grid = self.lyrs.get_layer_by_name('Grid', self.lyrs.group).layer()
        self.lyrs.update_layer_extents(self.grid)
        grid_ext = self.grid.extent()
        xmin = grid_ext.xMinimum()
        xmax = grid_ext.xMaximum()
        ymin = grid_ext.yMinimum()
        ymax = grid_ext.yMaximum()
        width = int(math.ceil(((xmax - xmin)/self.cell_size)))
        height = int(math.ceil(((ymax - ymin)/self.cell_size)))
        self.grid_bounds = (xmin,ymin,xmax,ymax)
        self.grid_shape = (height,width)
        self.grid_srs = self.grid.crs()
        self.uc.log_info('extent = %r, grid shape = %r'%(self.grid_bounds,self.grid_shape))
        
    def _colrow(self, transform, x, y):
        # returns column, row tuple corresponding to x,y coordinates
        ulX = transform[0]
        ulY = transform[3]
        xDist = transform[1]
        yDist = transform[5]
        col = int((x - ulX) / xDist)
        row = int((ulY - y) / xDist)
        return (col, row)
            
    def _create_vrt(self,xyz_in):
        xyz_name = os.path.basename(xyz_in).split('.')[0]
        vrt_out =  '{}.vrt'.format(xyz_in[:-4])
        vrt_string = '<OGRVRTDataSource>\n' \
                     '     <OGRVRTLayer name="TOPOXYZ">\n' \
                     '          <SrcDataSource>%s</SrcDataSource>\n' \
                     '          <SrcLayer>%s</SrcLayer>\n' \
                     '          <GeometryType>wkbPoint</GeometryType>\n' \
                     '          <GeometryField encoding="PointFromColumns" x="X" y="Y" z="Z"/>\n' \
                     '     </OGRVRTLayer>\n' \
                     '</OGRVRTDataSource>'
        vrt_string = vrt_string%(xyz_in,xyz_name)
        with open(vrt_out,'w') as fid:
            fid.write(vrt_string)
        return vrt_out

    def _clip_raster_aligned(self,raster_in,name_suffix='_clip_aligned'):
        raster_out = '{}{}.tif'.format(raster_in[:-4],name_suffix)
        ds = gdal.Open(raster_in)
        gtransform = ds.GetGeoTransform()
        src_rows, src_cols = ds.RasterYSize, ds.RasterXSize 
        xmin,ymin,xmax,ymax = self.grid_bounds
        ul_col, ul_row = self._colrow(gtransform, xmin, ymax)
        lr_col, lr_row = self._colrow(gtransform, xmax, ymin)
        # TODO: check the extents
        dst_rows = lr_row - ul_row + 1
        dst_cols = lr_col - ul_col + 1
        opt = gdal.TranslateOptions(srcWin=[ul_col,ul_row,dst_cols,dst_rows], format='GTiff')
        gdal.Translate(raster_out, ds, options = opt)
        ds = None
        return raster_out
        
    def _raster_to_xyz(self, raster_in):
        # clip raster and assign grid's nodata
        raster_in_temp = self._clip_raster_aligned(raster_in,'_clip_aligned_temp')
        raster_in = '{}{}.tif'.format(raster_in[:-4],'_clip_aligned')
        warp_opt = gdal.WarpOptions(dstNodata=self.grid_nodata)
        gdal.Warp(raster_in,raster_in_temp,options =  warp_opt)
        os.remove(raster_in_temp)
        # create X,Y,Z csv file
        xyz_temp = '{}_temp.csv'.format(raster_in[:-4])    
        ds = gdal.Open(raster_in)
        #Note: DECIMAL_PRECISION works with gdal >= 3.0.0. QGIS 3.4.12 is currently using gdal 2.4.1        
        trans_opt = gdal.TranslateOptions(creationOptions = ['DECIMAL_PRECISION=4', 'COLUMN_SEPARATOR=COMMA', 'ADD_HEADER_LINE=YES'],
                                    format='XYZ')
        gdal.Translate(xyz_temp, ds, options = trans_opt)
        # Remove nodata from xyz file
        xyz_out = '{}.csv'.format(raster_in[:-4])
        if os.path.exists(xyz_out):
            os.remove(xyz_out)
        band = ds.GetRasterBand(1)
        nodata = str(band.GetNoDataValue())
        # SQL inequality != or <> not working
        ogr_opt = ['-f CSV', '-overwrite',
                   '-sql "SELECT X,Y,CAST(Z as float) FROM {0:s} WHERE Z > \'{1:s}\'"'.format(os.path.basename(xyz_temp)[:-4], nodata), 
                   '"{}"'.format(xyz_out),
                   '"{}"'.format(xyz_temp),
                   '-lco SEPARATOR=COMMA',
                   '-lco STRING_QUOTING=IF_NEEDED']
        cmd = 'ogr2ogr {}'.format(' '.join([opt for opt in ogr_opt]))
        self.uc.log_info(cmd)
        proc = Popen(cmd, shell=True, stdin=open(os.devnull), stdout=PIPE, stderr=STDOUT, universal_newlines=True)
        out = proc.communicate()
        for line in out:
            self.uc.log_info(line)
        ds = None
        return xyz_out

    def _xyz_to_grid(self, xyz_in):
        self.uc.log_info('Running _xyz_to_grid function')
        vrt_file = self._create_vrt(xyz_in)
        raster_out = '{}_grid.tif'.format(xyz_in[:-4]) 
        if gdalAvailable:
            radius1 = self.cell_size/2.0
            radius2 = self.cell_size/2.0
            # TODO: Allow user to override parameters
            # Note: Linear method is very slow
            methods = {
                       "average": 'average:radius1=%s:radius2=%s:angle=%s:min_points=%s:nodata=%s'%(radius1,radius2,0,1, self.grid_nodata),
                       "inverse distance": 'invdist:power=%s:smoothing=%s:radius1=%s:radius2=%s:angle=%s:min_points=%s:max_points=%s:nodata=%s'%(2,0,radius1,radius2,0,1,0,self.grid_nodata),
                       "inverse distance 2": 'invdistnn:power=%s:smoothing=%s:radius=%s:min_points=%s:max_points=%s:nodata=%s'%(2,0,radius1,1,12,self.grid_nodata),
                       "nearest": 'nearest:radius1=%s:radius2=%s:angle=%s:nodata=%s'%(radius1,radius2,0,self.grid_nodata),
                       "linear": 'linear:radius=%s:nodata=%s'%(0,self.grid_nodata)
                       }
            method_selected = self.algCbo.itemData(self.algCbo.currentIndex())
            self.uc.log_info('gdalgrid method = %s'%method_selected)
            algorithm = methods[method_selected]
            self.uc.log_info('gdalgrid algorithm = %s'%algorithm)
            ulx,uly,lrx,lry = self.grid_bounds[0],self.grid_bounds[3],self.grid_bounds[2],self.grid_bounds[1]
            height,width = self.grid_shape
            opt = gdal.GridOptions(width=width, height=height,
                              outputBounds = [ulx,uly,lrx,lry],
                              layers=['TOPOXYZ'],
                              zfield='Z',
                              outputSRS = self.grid_srs.toProj4(),
                              algorithm = algorithm,
                              format='GTiff')        

            gdal.Grid(raster_out,vrt_file,options=opt)
            self.uc.log_info('gdalgrid complete.')
        else:
            self.uc.log_info('gdal library is needed for _xyz_to_grid function')
            self.uc.bar_error('gdal library is needed for _xyz_to_grid function')
            return
        return raster_out
