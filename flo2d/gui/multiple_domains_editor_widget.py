#  -*- coding: utf-8 -*-
import math
import os

from PyQt5.QtCore import QSettings, QVariant
from PyQt5.QtWidgets import QApplication, QProgressDialog, QInputDialog
from qgis.PyQt.QtCore import NULL
from qgis._core import QgsGeometry, QgsFeatureRequest, QgsPointXY, QgsField, QgsSpatialIndex, QgsFeature

from ..flo2d_tools.grid_tools import square_grid, build_grid, number_of_elements, grid_compas_neighbors, \
    adjacent_grid_elevations, adjacent_grids, domain_tendency
from ..geopackage_utils import GeoPackageUtils
# FLO-2D Preprocessor tools for QGIS

from ..user_communication import UserCommunication
from .ui_utils import load_ui, center_canvas

uiDialog, qtBaseClass = load_ui("multiple_domains_editor")


class MultipleDomainsEditorWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.con = None
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.grid_lyr = None
        self.gutils = None

        self.setup_connection()
        self.populate_md_cbos()
        self.populate_connect_cbos()

        # Domain Creation - Connections
        self.create_md_polygon_btn.clicked.connect(self.create_md_polygon)
        self.rollback_md_btn.clicked.connect(self.cancel_mult_domains_edits)
        self.delete_md_schema_btn.clicked.connect(self.delete_schema_md)
        # self.md_help_btn.clicked.connect()
        self.change_md_name_btn.clicked.connect(self.change_md_name)
        self.delete_md_btn.clicked.connect(self.delete_md)
        self.md_center_btn.clicked.connect(self.md_center)
        #
        # # Connectivity Creation - Connections
        self.create_connect_line_btn.clicked.connect(self.create_connectivity_line)
        self.rollback_connect_btn.clicked.connect(self.cancel_user_md_connect_lines_edits)
        self.change_connect_name_btn.clicked.connect(self.change_connect_name)
        self.delete_connect_btn.clicked.connect(self.delete_connect)
        self.connect_center_btn.clicked.connect(self.connect_center)

        self.schematize_md_btn.clicked.connect(self.schematize_md)
        self.export_md_gpkg.clicked.connect(self.export_multi_domain)
        self.create_subdomains_btn.clicked.connect(self.create_subdomains)

        self.mult_domains = self.lyrs.data["mult_domains"]["qlyr"]
        self.mult_domains.afterCommitChanges.connect(self.populate_md_cbos)
        self.md_name_cbo.currentIndexChanged.connect(self.md_index_changed)

        self.user_md_connect_lines = self.lyrs.data["user_md_connect_lines"]["qlyr"]
        self.user_md_connect_lines.afterCommitChanges.connect(self.populate_connect_cbos)
        self.connect_name_cbo.currentIndexChanged.connect(self.connect_index_changed)

    def setup_connection(self):
        """
        Function to set up connection
        """
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_md_cbos(self, fid=None):
        """
        Function to populate the multi domain comboboxes
        """
        self.md_name_cbo.clear()
        self.cellsize_le.clear()

        qry = "SELECT fid, name FROM mult_domains;"
        rows = self.gutils.execute(qry).fetchall()
        if rows:
            cur_idx = 0
            for i, row in enumerate(rows):
                md_name = row[1]
                self.md_name_cbo.addItem(md_name)
                if fid and row[0] == fid:
                    cur_idx = i
            self.md_name_cbo.setCurrentIndex(cur_idx)
            cellsize = self.gutils.execute(f"SELECT domain_cellsize FROM mult_domains WHERE fid = {cur_idx + 1};").fetchone()
            if cellsize:
                cellsize = cellsize[0]
                self.cellsize_le.setText(str(cellsize))

        self.uncheck_md_btns()

    def md_index_changed(self):
        """
        Function to update the multi domain comboxes when the index changes
        """
        domain_name = self.md_name_cbo.currentText()
        cellsize = self.gutils.execute(f"SELECT domain_cellsize FROM mult_domains WHERE name = '{domain_name}';").fetchone()
        if cellsize:
            self.cellsize_le.setText(str(cellsize[0]))

        if self.md_center_btn.isChecked():
            fid_qry = self.gutils.execute(
                f"SELECT fid FROM mult_domains WHERE name = '{self.md_name_cbo.currentText()}';").fetchone()
            if fid_qry:
                fid = fid_qry[0]
            else:
                return
            self.lyrs.show_feat_rubber(self.mult_domains.id(), fid)
            feat = next(self.mult_domains.getFeatures(QgsFeatureRequest(fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def populate_connect_cbos(self, fid=None):
        """
        Function to populate the connectivity comboboxes
        """
        self.connect_name_cbo.clear()
        self.connect_domain_cbo.clear()

        qry = "SELECT fid FROM mult_domains;"
        rows = self.gutils.execute(qry).fetchall()
        if rows:
            for fid in rows:
                self.connect_domain_cbo.addItem(str(fid[0]))

        qry = "SELECT fid, name FROM user_md_connect_lines;"
        rows = self.gutils.execute(qry).fetchall()
        if rows:
            cur_idx = 0
            for i, row in enumerate(rows):
                connect_name = row[1]
                self.connect_name_cbo.addItem(connect_name)
                if fid and row[0] == fid:
                    cur_idx = i
            self.connect_name_cbo.setCurrentIndex(cur_idx)
            domain_id = self.gutils.execute(f"SELECT domain_fid FROM user_md_connect_lines WHERE fid = {cur_idx + 1};").fetchone()
            if domain_id:
                domain_id = domain_id[0]
                self.connect_domain_cbo.setCurrentIndex(self.connect_domain_cbo.findText(str(domain_id)))

        self.uncheck_connectivity_btns()

    def connect_index_changed(self):
        """
        Function to update the connecvitity comboxes when the index changes
        """
        connect_name = self.connect_name_cbo.currentText()
        domain_id = self.gutils.execute(f"SELECT domain_fid FROM user_md_connect_lines WHERE name = '{connect_name}';").fetchone()
        if domain_id:
            self.connect_domain_cbo.setCurrentIndex(self.connect_domain_cbo.findText(str(domain_id[0])))
        if self.connect_center_btn.isChecked():
            fid_qry = self.gutils.execute(
                f"SELECT fid FROM user_md_connect_lines WHERE name = '{self.connect_name_cbo.currentText()}';").fetchone()
            if fid_qry:
                fid = fid_qry[0]
            else:
                return
            self.lyrs.show_feat_rubber(self.user_md_connect_lines.id(), fid)
            feat = next(self.user_md_connect_lines.getFeatures(QgsFeatureRequest(fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)

    def create_md_polygon(self):
        """
        Function to start editing and finish editing the connectivity
        """
        if self.lyrs.any_lyr_in_edit("mult_domains"):
            self.uc.bar_info(f"Domains saved!")
            self.uc.log_info(f"Domains saved!")
            self.save_md_changes()
            return

        self.create_md_polygon_btn.setCheckable(True)
        self.create_md_polygon_btn.setChecked(True)

        if not self.lyrs.enter_edit_mode("mult_domains"):
            return

    def save_md_changes(self):
        """
        Function to save multiple domain changes
        """
        mult_domains_edited = self.lyrs.save_lyrs_edits("mult_domains")
        if mult_domains_edited:
            pass
        self.uncheck_md_btns()

    def uncheck_md_btns(self):
        """
        Function to uncheck the checked buttons
        """
        self.create_md_polygon_btn.setChecked(False)

    def cancel_mult_domains_edits(self):
        """
        Function to rollback user edits on the mult_domains layers
        """
        user_lyr_edited = self.lyrs.rollback_lyrs_edits("mult_domains")
        if user_lyr_edited:
            self.uncheck_md_btns()
            pass

    def create_connectivity_line(self):
        """
        Function to start editing and finish editing the connectivity line
        """
        if self.lyrs.any_lyr_in_edit("user_md_connect_lines"):
            self.uc.bar_info(f"Connectivity Lines saved!")
            self.uc.log_info(f"Connectivity Lines saved!")
            self.save_connectivity_changes()
            return

        self.create_connect_line_btn.setCheckable(True)
        self.create_connect_line_btn.setChecked(True)

        if not self.lyrs.enter_edit_mode("user_md_connect_lines"):
            return

    def uncheck_connectivity_btns(self):
        """
        Function to uncheck the checked buttons
        """
        self.create_connect_line_btn.setChecked(False)

    def save_connectivity_changes(self):
        """
        Function to save connectivity lines changes
        """
        connectivity_lines_edited = self.lyrs.save_lyrs_edits("user_md_connect_lines")
        if connectivity_lines_edited:
            pass
        self.uncheck_connectivity_btns()

    def cancel_user_md_connect_lines_edits(self):
        """
        Function to rollback user edits on the mult_domains layers
        """
        user_lyr_edited = self.lyrs.rollback_lyrs_edits("user_md_connect_lines")
        if user_lyr_edited:
            self.uncheck_connectivity_btns()
            pass

    def schematize_md(self):
        """
        Function to schematize the multiple domains
        1. Create the Subdomain grids
        2. Create the connectivity
        """

        pass

        # if self.gutils.is_table_empty("mult_domains"):
        #     self.uc.bar_info(f"There is no domain on the User Layers!")
        #     self.uc.log_info(f"There is no domain on the User Layers!")
        #     return
        #
        # # I'll need to iterate over all domains
        # domain_boundary = self.lyrs.data["mult_domains"]["qlyr"]
        #
        # for feat in domain_boundary.getFeatures():
        #
        #     # Create the grid
        #     self.square_grid(feat)
        #     self.update_domain_cells(feat)


    # def update_domain_cells(self, feature):
    #     """
    #     Function to update the domain cells
    #     """
    #     fid = feature["fid"]
    #     cellsize = self.gutils.execute(f"SELECT domain_cellsize FROM mult_domains WHERE fid = {fid};").fetchone()[0]
    #     cellsize_grid = self.gutils.get_cont_par("CELLSIZE")
    #
    #     cellsize_ratio = float(cellsize_grid) / float(cellsize)
    #
    #     # Intersect the connectivity line to the grid
    #     connectivity_lines = self.lyrs.data["user_md_connect_lines"]["qlyr"]
    #     connect_cells = self.lyrs.data["schema_md_connect_cells"]["qlyr"]
    #
    #     for line in connectivity_lines.getFeatures():
    #         line_fid = line['fid']
    #         int_grid_ids = self.gutils.execute(f"""
    #                             SELECT
    #                                 g.fid AS FID
    #                             FROM
    #                                 grid AS g, user_md_connect_lines AS cl
    #                             WHERE
    #                                 cl.domain_fid = "{line_fid}" AND cl.domain_fid = {fid} AND
    #                                 ST_Intersects(CastAutomagic(g.geom), CastAutomagic(cl.geom));
    #                             """).fetchall()
    #
    #         for int_grid_id in int_grid_ids:
    #             int_grid_id = int_grid_id[0]
    #             query = f"""
    #                         SELECT
    #                             g.fid AS grid_id,
    #                             smc.fid AS smc_id,
    #                             ST_Centroid(CastAutomagic(smc.geom)) AS smc_centroid,
    #                             ST_Distance(ST_Centroid(CastAutomagic(g.geom)), ST_Centroid(CastAutomagic(smc.geom))) AS distance
    #                         FROM
    #                             grid AS g
    #                         JOIN
    #                             schema_md_cells AS smc
    #                         ON
    #                             ST_Distance(ST_Centroid(CastAutomagic(g.geom)), ST_Centroid(CastAutomagic(smc.geom))) IS NOT NULL
    #                         WHERE
    #                             g.fid = {int_grid_id}
    #                         ORDER BY
    #                             g.fid, distance
    #                         LIMIT {cellsize_ratio};
    #                     """
    #             closest_domain_cells = self.gutils.execute(query).fetchall()
    #             for closest_domain_cell in closest_domain_cells:
    #                 grid_id, smc_id, smc_centroid, _ = closest_domain_cell
    #                 data = [(fid, grid_id, smc_id, smc_centroid)]  # Wrap the tuple in a list
    #                 qry = """INSERT INTO schema_md_connect_cells (domain_fid, grid_fid, domain_cell, geom) VALUES (?,?,?,?);"""
    #                 self.con.executemany(qry, data)
    #
    #     # Update the layers
    #     self.lyrs.update_layer_extents(domain_cells)
    #     if domain_cells:
    #         domain_cells.triggerRepaint()
    #
    #     self.lyrs.update_layer_extents(connect_cells)
    #     if connect_cells:
    #         connect_cells.triggerRepaint()
    #
    # def square_grid(self, feature):
    #     """
    #     Function for calculating and writing square grid into 'schema_md_cells' table.
    #     """
    #     fid = feature["fid"]
    #     cellsize_domain = self.gutils.execute(f"SELECT domain_cellsize FROM mult_domains WHERE fid = {fid};").fetchone()[0]
    #     cellsize_grid = self.gutils.get_cont_par("CELLSIZE")
    #
    #     cellsize_modulo = float(cellsize_grid) % float(cellsize_domain)
    #     if cellsize_modulo != 0:
    #         domain_name = self.gutils.execute(f"SELECT name FROM mult_domains WHERE fid = {fid};").fetchone()[0]
    #         self.uc.bar_error(f"The cell size of {domain_name} is not compatible with the grid cell size!")
    #         self.uc.log_info(f"The cell size of {domain_name} is not compatible with the grid cell size!")
    #         return
    #
    #     polygons = list(self.build_grid(feature, cellsize_domain))
    #     total_polygons = len(polygons)
    #
    #     progDialog = QProgressDialog(f"Creating Grid for domain {fid}. Please wait...", None, 0, total_polygons)
    #     progDialog.setModal(True)
    #     progDialog.setValue(0)
    #     progDialog.show()
    #     QApplication.processEvents()
    #     i = 0
    #
    #     polygons = ((self.gutils.build_square_from_polygon(poly),) for poly in
    #                 self.build_grid(feature, cellsize_domain))
    #     sql = ["""INSERT INTO schema_md_cells (geom) VALUES""", 1]
    #     for g_tuple in polygons:
    #         sql.append(g_tuple)
    #         progDialog.setValue(i)
    #         i += 1
    #     if len(sql) > 2:
    #         self.gutils.batch_execute(sql)
    #     else:
    #         pass

    # def build_grid(self, feature, cell_size, upper_left_coords=None):
    #     """
    #     Generator which creates grid with given cell size and inside given boundary layer.
    #     """
    #     half_size = cell_size * 0.5
    #     geom = feature.geometry()
    #     bbox = geom.boundingBox()
    #     xmin = bbox.xMinimum()
    #     xmax = bbox.xMaximum()
    #     ymax = bbox.yMaximum()
    #     ymin = bbox.yMinimum()
    #     if upper_left_coords:
    #         xmin, ymax = upper_left_coords
    #     cols = int(math.ceil(abs(xmax - xmin) / cell_size))
    #     rows = int(math.ceil(abs(ymax - ymin) / cell_size))
    #     x = xmin + half_size
    #     y = ymax - half_size
    #     geos_geom_engine = QgsGeometry.createGeometryEngine(geom.constGet())
    #     geos_geom_engine.prepareGeometry()
    #     for col in range(cols):
    #         y_tmp = y
    #         for row in range(rows):
    #             pnt = QgsGeometry.fromPointXY(QgsPointXY(x, y_tmp))
    #             if geos_geom_engine.intersects(pnt.constGet()):
    #                 poly = (
    #                     x - half_size,
    #                     y_tmp - half_size,
    #                     x + half_size,
    #                     y_tmp - half_size,
    #                     x + half_size,
    #                     y_tmp + half_size,
    #                     x - half_size,
    #                     y_tmp + half_size,
    #                     x - half_size,
    #                     y_tmp - half_size,
    #                 )
    #                 yield poly
    #             else:
    #                 pass
    #             y_tmp -= cell_size
    #         x += cell_size

    def delete_schema_md(self):
        """
        Function to delete the multiple domains schematized data
        """
        if self.gutils.is_table_empty("schema_md_connect_cells"):
            self.uc.bar_warn("There is no schematized multiple domains data!")
            self.uc.log_info("There is no schematized multiple domains data!")
            return

        self.gutils.clear_tables("schema_md_connect_cells")

        self.uc.bar_info("Schematized multiple domains deleted!")
        self.uc.log_info("Schematized multiple domains deleted!")

        self.lyrs.clear_rubber()
        self.lyrs.data["schema_md_connect_cells"]["qlyr"].triggerRepaint()

    def change_md_name(self):
        """
        Function to change the domain name
        """
        if not self.md_name_cbo.count():
            return
        fid_qry = self.gutils.execute(f"SELECT fid FROM mult_domains WHERE name = '{self.md_name_cbo.currentText()}';").fetchone()
        if fid_qry:
            fid = fid_qry[0]
        else:
            return
        new_name, ok = QInputDialog.getText(None, "Change name", "New name:")
        if not ok or not new_name:
            return
        if not self.md_name_cbo.findText(new_name) == -1:
            msg = "Domain with name {} already exists in the database. Please, choose another name.".format(
                new_name
            )
            self.uc.show_warn(msg)
            self.uc.log_info(msg)
            return

        self.gutils.execute(f"UPDATE mult_domains SET name = '{new_name}' WHERE fid = {fid};")
        self.populate_md_cbos()
        self.uc.bar_info("Domain name changed!")
        self.uc.log_info("Domain name changed!")

    def delete_md(self):
        """
        Function to delete the domain
        """
        if not self.md_name_cbo.count():
            return
        fid_qry = self.gutils.execute(f"SELECT fid FROM mult_domains WHERE name = '{self.md_name_cbo.currentText()}';").fetchone()
        if fid_qry:
            fid = fid_qry[0]
        else:
            return
        q = "Are you sure, you want delete the current domain?"
        if not self.uc.question(q):
            return
        self.gutils.execute(f"DELETE FROM mult_domains WHERE fid = {fid};")
        self.populate_md_cbos()
        self.mult_domains.triggerRepaint()
        self.uc.bar_info("Domain deleted!")
        self.uc.log_info("Domain deleted!")

    def md_center(self):
        """
        Function to check the md eye button
        """
        if self.md_center_btn.isChecked():
            self.md_center_btn.setChecked(True)
            fid_qry = self.gutils.execute(
                f"SELECT fid FROM mult_domains WHERE name = '{self.md_name_cbo.currentText()}';").fetchone()
            if fid_qry:
                fid = fid_qry[0]
            else:
                return
            self.lyrs.show_feat_rubber(self.mult_domains.id(), fid)
            feat = next(self.mult_domains.getFeatures(QgsFeatureRequest(fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            return
        else:
            self.md_center_btn.setChecked(False)
            self.lyrs.clear_rubber()
            return

    def change_connect_name(self):
        """
        Function to change the connectivity name
        """
        if not self.connect_name_cbo.count():
            return
        fid_qry = self.gutils.execute(f"SELECT fid FROM user_md_connect_lines WHERE name = '{self.connect_name_cbo.currentText()}';").fetchone()
        if fid_qry:
            fid = fid_qry[0]
        else:
            return
        new_name, ok = QInputDialog.getText(None, "Change name", "New name:")
        if not ok or not new_name:
            return
        if not self.connect_name_cbo.findText(new_name) == -1:
            msg = "Connectivity with name {} already exists in the database. Please, choose another name.".format(
                new_name
            )
            self.uc.show_warn(msg)
            self.uc.log_info(msg)
            return

        self.gutils.execute(f"UPDATE user_md_connect_lines SET name = '{new_name}' WHERE fid = {fid};")
        self.populate_connect_cbos()
        self.uc.bar_info("Connectivity name changed!")
        self.uc.log_info("Connectivity name changed!")

    def delete_connect(self):
        """
        Function to delete the connectivity
        """
        if not self.connect_name_cbo.count():
            return
        fid_qry = self.gutils.execute(f"SELECT fid FROM user_md_connect_lines WHERE name = '{self.connect_name_cbo.currentText()}';").fetchone()
        if fid_qry:
            fid = fid_qry[0]
        else:
            return
        q = "Are you sure, you want delete the current connectivity?"
        if not self.uc.question(q):
            return
        self.gutils.execute(f"DELETE FROM user_md_connect_lines WHERE fid = {fid};")
        self.populate_connect_cbos()
        self.user_md_connect_lines.triggerRepaint()
        self.uc.bar_info("Connectivity deleted!")
        self.uc.log_info("Connectivity deleted!")

    def connect_center(self):
        """
        Function to check the connectivity eye button
        """
        if self.connect_center_btn.isChecked():
            self.connect_center_btn.setChecked(True)
            fid_qry = self.gutils.execute(
                f"SELECT fid FROM user_md_connect_lines WHERE name = '{self.connect_name_cbo.currentText()}';").fetchone()
            if fid_qry:
                fid = fid_qry[0]
            else:
                return
            self.lyrs.show_feat_rubber(self.user_md_connect_lines.id(), fid)
            feat = next(self.user_md_connect_lines.getFeatures(QgsFeatureRequest(fid)))
            x, y = feat.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            return
        else:
            self.connect_center_btn.setChecked(False)
            self.lyrs.clear_rubber()
            return

    def export_multi_domain(self):
        """
        Function to export the multi domain dat file
        """
        # n_line = "N   {}"
        # o_line = "O" + "  {}" + "  {}" * 5 + "\n"

        s = QSettings()
        outdir = s.value("FLO-2D/lastGdsDir", "")
        multidomain = os.path.join(outdir, "MULTIDOMAIN.DAT")
        multidomain_lines = []

        domain_fid_qry = self.gutils.execute("SELECT DISTINCT domain_fid FROM schema_md_connect_cells;").fetchall()
        if domain_fid_qry:
            for domain in domain_fid_qry:
                domain_fid = domain[0]
                grid_fid_qry = self.gutils.execute(f"SELECT DISTINCT grid_fid FROM schema_md_connect_cells WHERE domain_fid = {domain_fid};").fetchall()
                if grid_fid_qry:
                    multidomain_lines.append(f"N {domain_fid}")
                    for grid in grid_fid_qry:
                        grid_fid = grid[0]
                        cells_str = ""
                        cells_fid_qry = self.gutils.execute(f"SELECT domain_cell FROM schema_md_connect_cells WHERE grid_fid = {grid_fid};").fetchall()
                        if cells_fid_qry:
                            for cell in cells_fid_qry:
                                cells_str += f"{cell[0]} "

                        multidomain_lines.append(f"O {grid_fid} {cells_str}")

                with open(multidomain, "w") as inf:
                    for line in multidomain_lines:
                        if line:
                            inf.write(line + "\n")

    def create_subdomains(self):
        """
        Function to create the subdomains
        """
        grid_layer = self.lyrs.data["grid"]["qlyr"]
        point_layer = self.lyrs.data["user_elevation_points"]["qlyr"]
        line_layer = self.lyrs.data["user_md_connect_lines"]["qlyr"]
        cell_size = int(float(self.gutils.get_cont_par("CELLSIZE")))

        QgsSpatialIndex(grid_layer)

        directions = {
            "N": 1,
            "NE": 2,
            "E": 3,
            "SE": 4,
            "S": 5,
            "SW": 6,
            "W": 7,
            "NW": 8
        }

        parallel_directions = {
            1: [3, 7],
            2: [8, 4],
            3: [1, 5],
            4: [2, 6],
            5: [3, 5],
            6: [8, 4],
            7: [1, 5],
            8: [2, 4],
        }

        # Get the first feature TODO Evaluate for multiple points
        feature = next(point_layer.getFeatures())
        geom = feature.geometry()
        # Get the geometry as a point
        point = geom.asPoint()
        # Get the starting cell
        start_cell = self.gutils.grid_on_point(point.x(), point.y())
        # List of the grid already evaluated
        evaluated_grids = [start_cell]
        # Tendency direction -> Use to avoid getting back close to the start point
        tendency_direction = domain_tendency(self.gutils, grid_layer, start_cell, cell_size)

        # Here is the main code to get the grid that are the boundary of the subdomain
        current_cell = start_cell
        while current_cell:
            elevs = adjacent_grid_elevations(self.gutils, grid_layer, current_cell, cell_size)
            previous_elev = 9999
            minimum_elev = None

            # Find the lowest elevation cell
            for elev in elevs:
                if elev != -999 and elev < previous_elev:
                    previous_elev = elev
                    minimum_elev = previous_elev

            # Determine flow direction
            if minimum_elev is None:
                break  # No valid flow direction

            direction = elevs.index(minimum_elev) + 1
            potential_dirs = parallel_directions[direction]
            current_cell_feature = next(grid_layer.getFeatures(QgsFeatureRequest(current_cell)))
            adjacent_cells = adjacent_grids(self.gutils, current_cell_feature, cell_size)
            if current_cell != start_cell:
                if None in adjacent_cells:
                    break

            # Try selecting from tendency direction first
            next_cell = None
            for potential_dir in potential_dirs:
                if potential_dir in tendency_direction:
                    cell = adjacent_cells[potential_dir - 1]
                    if cell and cell not in evaluated_grids:
                        next_cell = cell
                        evaluated_grids.append(next_cell)
                        break  # Move to the next cell

            # If no cell found in tendency direction, use any available direction
            if next_cell is None:
                for potential_dir in potential_dirs:
                    cell = adjacent_cells[potential_dir - 1]
                    if cell and cell not in evaluated_grids:
                        next_cell = cell
                        evaluated_grids.append(next_cell)
                        break  # Move to the next cell

            current_cell = next_cell  # Update for the next iteration

        # Create the line
        centroids = []
        for fid in evaluated_grids:
            feature = grid_layer.getFeature(fid)
            if feature and feature.geometry():
                centroid = feature.geometry().centroid().asPoint()
                centroids.append(QgsPointXY(centroid.x(), centroid.y()))

        if len(centroids) < 2:
            self.uc.log_info("Not enough centroids to create a line.")
            self.uc.bar_error("Not enough centroids to create a line.")
            return

        # Create line geometry from centroids
        line_geom = QgsGeometry.fromPolylineXY(centroids)

        # Create a new feature for the line
        line_feature = QgsFeature(line_layer.fields())
        line_feature.setGeometry(line_geom)

        # Start editing and add the feature to the line layer
        line_layer.startEditing()
        line_layer.addFeature(line_feature)
        line_layer.commitChanges()
        line_layer.updateExtents()
        line_layer.triggerRepaint()

        # self.uc.log_info(evaluated_grids)