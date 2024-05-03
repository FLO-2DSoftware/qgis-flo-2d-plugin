# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import tempfile
from subprocess import PIPE, STDOUT, Popen

from qgis._core import QgsWkbTypes, QgsGeometry, QgsFeatureRequest
from qgis.core import QgsRasterLayer
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QFileDialog

from ..flo2d_tools.grid_tools import grid_has_empty_elev, raster2grid, spatial_index
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("sampling_rc")


class SamplingRCDialog(qtBaseClass, uiDialog):

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

        self.current_lyr = None
        self.points_index = None
        self.points_feats = None
        self.min_dtm_sb = 20
        self.populate_point_shape_cbo()
        self.grid_lyr = self.lyrs.data["grid"]["qlyr"]

        # connections
        self.point_lyr_cbo.currentIndexChanged.connect(self.populate_fields_cbo)
        self.browseSrcBtn.clicked.connect(self.browse_src_pointshape)

    def populate_point_shape_cbo(self):
        """
        Get loaded point shapes into combobox.
        """
        try:
            lyrs = self.lyrs.list_group_vlayers()
            for l in lyrs:
                if l.geometryType() == QgsWkbTypes.PointGeometry:
                    if l.featureCount() != 0:
                        self.point_lyr_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                else:
                    pass
            self.populate_fields_cbo(self.point_lyr_cbo.currentIndex())
        except Exception as e:
            pass

    def populate_fields_cbo(self, idx):
        """
        Populate the field based on the selected point shape
        """
        uri = self.point_lyr_cbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri)
        self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()
        self.point_lyr_field_cbo.setLayer(self.current_lyr)
        self.point_lyr_field_cbo.setCurrentIndex(0)

    def browse_src_pointshape(self):
        """
        Users pick a source point shape not loaded into project.
        """
        s = QSettings()
        last_dtm_shape_dir = s.value("FLO-2D/lastGdsDir", "")
        self.src, __ = QFileDialog.getOpenFileName(None, "Choose elevation point shape...", directory=last_dtm_shape_dir)
        if not self.src:
            return
        if self.point_lyr_cbo.findData(self.src) == -1:
            bname = os.path.basename(self.src)
            self.point_lyr_cbo.addItem(bname, self.src)
            self.point_lyr_cbo.setCurrentIndex(len(self.point_lyr_cbo) - 1)

    def create_elev_rc(self, cell_size):
        """
        Function to create the outrc
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        grid_elems = self.grid_lyr.getFeatures()
        self.points_feats, self.points_index = spatial_index(self.current_lyr)

        for feat in grid_elems:
            geom = feat.geometry()
            geos_geom = QgsGeometry.createGeometryEngine(geom.constGet())
            geos_geom.prepareGeometry()
            fids = self.points_index.intersects(geom.boundingBox())
            for fid in fids:
                point_feat = self.points_feats[fid]
                self.uc.log_info(str(feat["fid"]))
                self.uc.log_info(str(point_feat['ELEVATION']))
                # other_geom = point_feat.geometry()
                # isin = geos_geom.intersects(other_geom.constGet())
                # if isin is True:
                #     points.append(point_feat[self.field])
                # else:
                #     pass
            break

            # self.uc.log_info(str(feat["fid"]))



    # def probe_elevation(self):
    #     """
    #     Resample raster to be aligned with the grid, then probe values and update elements elevation attr.
    #     """
    #     self.src_raster = self.srcRasterCbo.itemData(self.srcRasterCbo.currentIndex())
    #     self.get_worp_opts_data()
    #     opts = [
    #         "-of GTiff",
    #         "-ot {}".format(self.RTYPE[self.raster_type]),
    #         "-tr {0} {0}".format(self.cell_size),
    #         '-s_srs "{}"'.format(self.src_srs),
    #         '-t_srs "{}"'.format(self.out_srs),
    #         "-te {}".format(" ".join([str(c) for c in self.output_bounds])),
    #         '-te_srs "{}"'.format(self.out_srs),
    #         "-ovr {}".format(self.ovrCbo.itemData(self.ovrCbo.currentIndex())),
    #         "-dstnodata {}".format(self.src_nodata),
    #         "-r {}".format(self.algCbo.itemData(self.algCbo.currentIndex())),
    #         "-co COMPRESS=LZW",
    #         "-wo OPTIMIZE_SIZE=TRUE",
    #     ]
    #     if self.multiThreadChBox.isChecked():
    #         opts.append("-multi -wo NUM_THREADS=ALL_CPUS")
    #     else:
    #         pass
    #     temp_dir = tempfile.gettempdir()
    #     temp_file_path = os.path.join(temp_dir, "elevation_interpolated.tif")
    #     cmd = 'gdalwarp {} "{}" "{}"'.format(" ".join([opt for opt in opts]), self.src_raster, temp_file_path)
    #     print(cmd)
    #     with open(os.devnull, 'r') as devnull:
    #         proc = Popen(
    #             cmd,
    #             shell=True,
    #             stdin=devnull,
    #             stdout=PIPE,
    #             stderr=STDOUT,
    #             universal_newlines=True,
    #         )
    #     out = proc.communicate()
    #     for line in out:
    #         self.uc.log_info(line)
    #     # Fill NODATA raster cells if desired
    #     if self.fillNoDataChBox.isChecked():
    #         self.fill_nodata()
    #     else:
    #         pass
    #     sampler = raster2grid(self.grid, temp_file_path)
    #
    #     qry = "UPDATE grid SET elevation=? WHERE fid=?;"
    #     self.con.executemany(qry, sampler)
    #     self.con.commit()
    #
    #     os.remove(temp_file_path)
    #
    #     return True
    #
    # def fill_nodata(self):
    #     opts = ["-md {}".format(self.radiusSBox.value())]
    #     cmd = 'gdal_fillnodata {} "{}"'.format(" ".join([opt for opt in opts]), self.out_raster)
    #     with open(os.devnull, 'r') as devnull:
    #         proc = Popen(
    #             cmd,
    #             shell=True,
    #             stdin=devnull,
    #             stdout=PIPE,
    #             stderr=STDOUT,
    #             universal_newlines=True,
    #         )
    #     out = proc.communicate()
    #     for line in out:
    #         self.uc.log_info(line)
    #
    # def show_probing_result_info(self):
    #     null_nr = grid_has_empty_elev(self.gutils)
    #     if null_nr:
    #         msg = "Sampling done.\n"
    #         msg += "Warning: There are {} grid elements that have no elevation value.".format(null_nr)
    #         self.uc.show_info(msg)
    #     else:
    #         self.uc.show_info("Sampling done.")
