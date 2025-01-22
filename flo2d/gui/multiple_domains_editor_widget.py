#  -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QApplication, QProgressDialog
from qgis._core import QgsGeometry

from ..flo2d_tools.grid_tools import square_grid, build_grid, number_of_elements, grid_compas_neighbors
from ..geopackage_utils import GeoPackageUtils
# FLO-2D Preprocessor tools for QGIS

from ..user_communication import UserCommunication
from .ui_utils import load_ui

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

        # Domain Creation - Connections
        self.create_md_polygon_btn.clicked.connect(self.create_md_polygon)
        self.rollback_md_btn.clicked.connect(self.cancel_mult_domains_edits)
        self.delete_md_schema_btn.clicked.connect(self.delete_schema_md)
        # self.md_help_btn.clicked.connect()
        # self.change_md_name_btn.clicked.connect()
        # self.delete_md_btn.clicked.connect()
        # self.md_center_btn.clicked.connect()
        #
        # # Connectivity Creation - Connections
        self.create_connect_line_btn.clicked.connect(self.create_connectivity_line)
        self.rollback_connect_btn.clicked.connect(self.cancel_user_md_connect_lines_edits)
        # self.change_connect_name_btn.clicked.connect()
        # self.delete_connect_btn.clicked.connect()
        # self.connect_center_btn.clicked.connect()

        self.schematize_md_btn.clicked.connect(self.schematize_md)
        # self.export_md_gpkg.clicked.connect()

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

    def create_md_polygon(self):
        """
        Function to start editing and finish editing the multiple domain polygons
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

        if self.gutils.is_table_empty("mult_domains"):
            self.uc.bar_info(f"There is no domain on the User Layers!")
            self.uc.log_info(f"There is no domain on the User Layers!")
            return

        # I'll need to iterate over all domains
        domain_boundary = self.lyrs.data["mult_domains"]["qlyr"]

        # Create the grid
        self.square_grid(domain_boundary)

        # TODO Assign the mannings and elevation from the GRID
        # Assign Mannings and Elevation
        # self.gutils.execute(f"""
        #                     SELECT
        #                         g.n_value AS n,
        #                         g.elevation AS e
        #                     FROM
        #                         grid AS g, schema_md_cells AS smc
        #                     WHERE
        #                         ST_Intersects(CastAutomagic(g.geom), CastAutomagic(smc.geom));
        #                     """).fetchall()

        self.update_domain_cells()


        # Get the grid centroids


        # Find out the closest subdomain cells -> remember to calculate the number of closer cells based on cell size


        # """
        # SELECT
        #     g.fid AS grid_id,
        #     smc.fid AS smc_id,
        #     ST_Distance(ST_Centroid(g.geom), ST_Centroid(smc.geom)) AS distance
        # FROM
        #     grid AS g
        # JOIN
        #     schema_md_cells AS smc
        # ON
        #     ST_Distance(ST_Centroid(g.geom), ST_Centroid(smc.geom)) IS NOT NULL
        # WHERE
        #     g.fid = 32449
        # ORDER BY
        #     g.fid, distance
        # LIMIT 3;
        # """

        # Fill the connectivity cells table



    def update_domain_cells(self):
        """
        Function to update the domain cells
        """
        # Intersect the connectivity line to the grid
        connectivity_lines = self.lyrs.data["user_md_connect_lines"]["qlyr"]
        domain_cells = self.lyrs.data["schema_md_cells"]["qlyr"]
        connect_cells = self.lyrs.data["schema_md_connect_cells"]["qlyr"]
        grid = self.lyrs.data["grid"]["qlyr"]

        for line in connectivity_lines.getFeatures():
            line_fid = line['fid']
            int_grid_ids = self.gutils.execute(f"""
                                SELECT
                                    g.fid AS FID
                                FROM
                                    grid AS g, user_md_connect_lines AS cl
                                WHERE
                                    cl.domain_fid = "{line_fid}" AND
                                    ST_Intersects(CastAutomagic(g.geom), CastAutomagic(cl.geom));
                                """).fetchall()

            for int_grid_id in int_grid_ids:
                int_grid_id = int_grid_id[0]
                # # TODO the limit must be the ration between the current grid size and the domain cell size
                query = f"""
                            SELECT
                                g.fid AS grid_id,
                                smc.fid AS smc_id,
                                ST_Centroid(CastAutomagic(smc.geom)) AS smc_centroid,
                                ST_Distance(ST_Centroid(CastAutomagic(g.geom)), ST_Centroid(CastAutomagic(smc.geom))) AS distance
                            FROM
                                grid AS g
                            JOIN
                                schema_md_cells AS smc
                            ON
                                ST_Distance(ST_Centroid(CastAutomagic(g.geom)), ST_Centroid(CastAutomagic(smc.geom))) IS NOT NULL
                            WHERE
                                g.fid = {int_grid_id}
                            ORDER BY
                                g.fid, distance
                            LIMIT 3;
                        """
                closest_domain_cells = self.gutils.execute(query).fetchall()
                for closest_domain_cell in closest_domain_cells:
                    grid_id, smc_id, smc_centroid, _ = closest_domain_cell
                    data = [(1, grid_id, smc_id, smc_centroid)]  # Wrap the tuple in a list
                    qry = """INSERT INTO schema_md_connect_cells (domain_fid, grid_fid, domain_cell, geom) VALUES (?,?,?,?);"""
                    self.con.executemany(qry, data)

        # Update the layers
        self.lyrs.update_layer_extents(domain_cells)
        if domain_cells:
            domain_cells.triggerRepaint()

        self.lyrs.update_layer_extents(connect_cells)
        if connect_cells:
            connect_cells.triggerRepaint()

    def square_grid(self, domain_boundary):
        """
        Function for calculating and writing square grid into 'schema_md_cells' table.
        """
        cellsize = self.gutils.execute(f"SELECT domain_cellsize FROM mult_domains WHERE fid = 1;").fetchone()[0]

        polygons = list(build_grid(domain_boundary, cellsize))
        total_polygons = len(polygons)

        progDialog = QProgressDialog("Creating Grid. Please wait...", None, 0, total_polygons)
        progDialog.setModal(True)
        progDialog.setValue(0)
        progDialog.show()
        QApplication.processEvents()
        i = 0

        polygons = ((self.gutils.build_square_from_polygon(poly),) for poly in
                    build_grid(domain_boundary, cellsize))
        sql = ["""INSERT INTO schema_md_cells (geom) VALUES""", 1]
        for g_tuple in polygons:
            sql.append(g_tuple)
            progDialog.setValue(i)
            i += 1
        if len(sql) > 2:
            self.gutils.batch_execute(sql)
        else:
            pass

        return total_polygons

    def delete_schema_md(self):
        """
        Function to delete the multiple domains schematized data
        """
        if self.gutils.is_table_empty("schema_md_cells") and self.gutils.is_table_empty("schema_md_connect_cells"):
            self.uc.bar_warn("There is no schematized multiple domains data!")
            self.uc.log_info("There is no schematized multiple domains data!")
            return

        self.gutils.clear_tables("schema_md_cells", "schema_md_connect_cells")

        self.uc.bar_info("Schematized multiple domains deleted!")
        self.uc.log_info("Schematized multiple domains deleted!")

        self.lyrs.clear_rubber()
        self.lyrs.data["schema_md_cells"]["qlyr"].triggerRepaint()
        self.lyrs.data["schema_md_connect_cells"]["qlyr"].triggerRepaint()
