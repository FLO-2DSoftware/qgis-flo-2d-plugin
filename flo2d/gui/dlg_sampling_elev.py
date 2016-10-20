# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Flo2D
                                 A QGIS plugin
 FLO-2D tools for QGIS
                             -------------------
        begin                : 2016-08-28
        copyright            : (C) 2016 by Lutra Consulting for FLO-2D
        email                : info@lutraconsulting.co.uk
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 FLO-2D Preprocessor tools for QGIS.
"""
import os
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from osgeo import gdal
from .utils import load_ui
from ..geopackage_utils import GeoPackageUtils

uiDialog, qtBaseClass = load_ui('sampling_elev')


class SamplingElevDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs, gpkg, cell_size, parent=None):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self, parent)
        self.con = con
        self.iface = iface
        self.lyrs = lyrs
        self.gpkg = gpkg
        self.gpkg_path = gpkg.get_gpkg_path()
        self.grid = None
        self.cell_size = float(cell_size)
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)
        self.populate_raster_cbo()
        self.populate_alg_cbo()
        self.src_nodata = -9999
        # connections
        self.browseSrcBtn.clicked.connect(self.browse_src_raster)

    def populate_raster_cbo(self):
        """Get loaded rasters into combobox"""
        rasters = self.lyrs.list_group_rlayers()
        for r in rasters:
            self.srcRasterCbo.addItem(r.name(), r.dataProvider().dataSourceUri())

    def browse_src_raster(self):
        """Users pick a source raster not loaded into project"""
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
            self.srcRasterCbo.setCurrentInsex(len(self.srcRasterCbo)-1)

    def populate_alg_cbo(self):
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

    def get_worp_options(self):
        self.get_worp_opts_data()
        self.wo = gdal.WarpOptions(
            options=[],
            format='GTiff',
            outputBounds=self.output_bounds,
            outputBoundsSRS=self.out_srs,
            xRes=self.cell_size,
            yRes=self.cell_size,
            targetAlignedPixels=False,
            width=0,
            height=0,
            srcSRS=self.src_srs,
            dstSRS=self.out_srs,
            srcAlpha=False,
            dstAlpha=False,
            warpOptions=None,
            errorThreshold=None,
            warpMemoryLimit=None,
            creationOptions=['COMPRESS=LZW'],
            outputType=self.raster_type,
            workingType=self.raster_type,
            resampleAlg=self.algCbo.itemData(self.algCbo.currentIndex()),
            srcNodata=self.src_nodata,
            dstNodata=self.src_nodata,
            multithread=self.multiThreadChBox.isChecked(),
            tps=False,
            rpc=False,
            geoloc=False,
            polynomialOrder=None,
            transformerOptions=None,
            cutlineDSName=self.gpkg_path,
            cutlineLayer=None,
            cutlineWhere=None,
            cutlineSQL="SELECT * FROM user_model_boundary",
            cutlineBlend=None,
            cropToCutline=False,
            copyMetadata=True,
            metadataConflictValue=None,
            setColorInterpretation=False,
            callback=None,
            callback_data=None
        )

    def get_worp_opts_data(self):
        # grid extents
        self.grid = self.lyrs.get_layer_by_name('Grid', self.lyrs.group).layer()
        grid_ext = self.grid.extent()
        xmin = grid_ext.xMinimum()
        xmax = grid_ext.xMaximum()
        ymin = grid_ext.yMinimum()
        ymax = grid_ext.yMaximum()
        self.output_bounds = (xmin, xmax, ymin, ymax)
        # CRS
        self.out_srs = self.grid.dataProvider().crs().toProj4()
        # data type
        src_raster_lyr = QgsRasterLayer(self.src_raster)
        self.raster_type = src_raster_lyr.dataProvider().dataType(0)
        self.src_srs = src_raster_lyr.dataProvider().crs().toProj4()
        # NODATA
        und = self.srcNoDataEdit.text()
        if und:
            self.src_nodata = int(und)

    def resample(self):
        """Resampling raster aligned with the grid"""
        self.src_raster = self.srcRasterCbo.itemData(self.srcRasterCbo.currentIndex())
        self.out_raster = '{}_interp.tif'.format(self.src_raster[:-4])
        try:
            os.remove(self.out_raster)
        except:
            pass
        self.get_worp_options()
        new = gdal.Warp(self.out_raster, self.src_raster, options=self.wo)
        del new
        probe_raster = QgsRasterLayer(self.out_raster)
        self.update_grid_elev()
        del probe_raster

    def update_grid_elev(self):
        """Probe resampled raster in each grid element"""
        qry = 'UPDATE grid SET elevation=? WHERE fid=?;'
        qry_data = []
        feats = self.grid.getFeatures()
        for f in feats:
            c = f.geometry().centroid().asPoint()
            ident = self.probe_raster.dataProvider().identify(c, QgsRaster.IdentifyFormatValue)
            if ident.isValid():
                qry_data.append((round(ident.results()[1], 3), f.id()))
        self.gpkg.execute_many(qry, qry_data)
