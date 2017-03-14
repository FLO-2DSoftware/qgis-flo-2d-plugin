# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
from subprocess import Popen, PIPE, STDOUT

from PyQt4.QtCore import QSettings
from PyQt4.QtGui import QFileDialog
from qgis.core import QgsRasterLayer

from flo2d.flo2d_tools.grid_tools import raster2grid, grid_has_empty_elev
from ui_utils import load_ui
from flo2d.geopackage_utils import GeoPackageUtils
from flo2d.user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui('sampling_elev')


class SamplingElevDialog(qtBaseClass, uiDialog):

    RTYPE = ['Byte', 'Int16', 'UInt16', 'UInt32', 'Int32', 'Float32', 'Float64']

    def __init__(self, con, iface, lyrs, cell_size, parent=None):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self, parent)
        self.con = con
        self.iface = iface
        self.lyrs = lyrs
        self.grid = None
        self.cell_size = float(cell_size)
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)
        self.gpkg_path = self.gutils.get_gpkg_path()
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.populate_raster_cbo()
        self.populate_alg_cbo()
        self.src_nodata = -9999
        self.probe_raster = None
        self.radiusSBox.setHidden(True)
        self.max_radius_lab.setHidden(True)
        # connections
        self.browseSrcBtn.clicked.connect(self.browse_src_raster)

    def populate_raster_cbo(self):
        """
        Get loaded rasters into combobox.
        """
        rasters = self.lyrs.list_group_rlayers()
        for r in rasters:
            self.srcRasterCbo.addItem(r.name(), r.dataProvider().dataSourceUri())

    def browse_src_raster(self):
        """
        Users pick a source raster not loaded into project.
        """
        s = QSettings()
        last_elev_raster_dir = s.value('FLO-2D/lastElevRasterDir', '')
        self.src = QFileDialog.getOpenFileName(None,
                                               'Choose elevation raster...',
                                               directory=last_elev_raster_dir)
        if not self.src:
            return
        s.setValue('FLO-2D/lastElevRasterDir', os.path.dirname(self.src))
        if not self.srcRasterCbo.findData(self.src):
            bname = os.path.basename(self.src)
            self.srcRasterCbo.addItem(bname, self.src)
            self.srcRasterCbo.setCurrentIndex(len(self.srcRasterCbo)-1)

    def populate_alg_cbo(self):
        """
        Populate resample algorithm combobox.
        """
        met = {
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
        for m in sorted(met.iterkeys()):
            self.algCbo.addItem(met[m], m)
            self.algCbo.setCurrentIndex(0)

    def get_worp_opts_data(self):
        """
        Get all data needed for GDAL Warp.
        """
        # grid extents
        self.grid = self.lyrs.get_layer_by_name('Grid', self.lyrs.group).layer()
        self.lyrs.update_layer_extents(self.grid)
        grid_ext = self.grid.extent()
        xmin = grid_ext.xMinimum()
        xmax = grid_ext.xMaximum()
        ymin = grid_ext.yMinimum()
        ymax = grid_ext.yMaximum()
        self.output_bounds = (xmin, ymin, xmax, ymax)
        # CRS
        self.out_srs = self.grid.dataProvider().crs().toProj4()
        # data type
        src_raster_lyr = QgsRasterLayer(self.src_raster)
        self.raster_type = src_raster_lyr.dataProvider().dataType(1)
        self.src_srs = src_raster_lyr.dataProvider().crs().toProj4()
        # NODATA
        und = self.srcNoDataEdit.text()
        if und:
            self.src_nodata = int(und)

    def probe_elevation(self):
        """
        Resample raster to be aligned with the grid, then probe values and update elements elevation attr.
        """
        self.src_raster = self.srcRasterCbo.itemData(self.srcRasterCbo.currentIndex())
        self.out_raster = '{}_interp.tif'.format(self.src_raster[:-4])
        try:
            if os.path.isfile(self.out_raster):
                os.remove(self.out_raster)
        except OSError:
            msg = 'Couldn\'t remove existing raster:\n{}\nChoose another filename.'.format(self.out_raster)
            self.uc.show_warn(msg)
            return False
        self.get_worp_opts_data()
        opts = [
            '-of GTiff',
            '-ot {}'.format(self.RTYPE[self.raster_type]),
            '-tr {0} {0}'.format(self.cell_size),
            '-te {}'.format(' '.join([str(c) for c in self.output_bounds])),
            '-te_srs "{}"'.format(self.out_srs),
            '-s_srs "{}"'.format(self.src_srs),
            '-dstnodata {}'.format(self.src_nodata),
            '-r {}'.format(self.algCbo.itemData(self.algCbo.currentIndex())),
            '-co COMPRESS=LZW',
            '-wo OPTIMIZE_SIZE=TRUE'
        ]
        if self.multiThreadChBox.isChecked():
            opts.append('-multi -wo NUM_THREADS=ALL_CPUS')
        else:
            pass
        cmd = 'gdalwarp {} "{}" "{}"'.format(' '.join([opt for opt in opts]), self.src_raster, self.out_raster)
        proc = Popen(cmd, shell=True, stdin=open(os.devnull), stdout=PIPE, stderr=STDOUT, universal_newlines=True)
        out = proc.communicate()
        for line in out:
            self.uc.log_info(line)
        # Fill NODATA raster cells if desired
        if self.fillNoDataChBox.isChecked():
            self.fill_nodata()
        else:
            pass
        sampler = raster2grid(self.grid, self.out_raster)
        qry = 'UPDATE grid SET elevation=? WHERE fid=?;'
        self.con.executemany(qry, sampler)
        self.con.commit()
        return True

    def fill_nodata(self):
        opts = [
            '-md {}'.format(self.radiusSBox.value())
        ]
        cmd = 'gdal_fillnodata {} "{}"'.format(' '.join([opt for opt in opts]), self.out_raster)
        proc = Popen(cmd, shell=True, stdin=open(os.devnull), stdout=PIPE, stderr=STDOUT, universal_newlines=True)
        out = proc.communicate()
        for line in out:
            self.uc.log_info(line)

    def show_probing_result_info(self):
        null_nr = grid_has_empty_elev(self.gutils)
        if null_nr:
            msg ='Sampling done.\n'
            msg += 'Warning: There are {} grid elements that have no elevation value.'.format(null_nr)
            self.uc.show_info(msg)
        else:
            self.uc.show_info("Sampling done.")
