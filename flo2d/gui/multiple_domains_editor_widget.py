#  -*- coding: utf-8 -*-
import itertools
import os
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QProgressDialog, QInputDialog, QMessageBox
from qgis.PyQt.QtCore import NULL
from qgis._core import QgsFeatureRequest, QgsFeature
from .dlg_multidomain_connectivity import MultipleDomainsConnectivityDialog
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from .ui_utils import load_ui, center_canvas
from ..deps import safe_h5py as h5py

uiDialog, qtBaseClass = load_ui("multiple_domains_editor")


class MultipleDomainsEditorWidget(qtBaseClass, uiDialog):
    """
    Class to handle editing and managing multiple domains.
    It provides functionalities for creating, deleting, and modifying domains,
    along with utility methods to handle domain-specific operations.
    """

    def __init__(self, iface, lyrs):
        """
        Initializes the MultipleDomainsEditorWidget instance.

        It sets up required attributes, initializes UI components, and
        ensures connections with other application modules.
        """
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.con = None
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = None

        if self.iface:
            self.setup_connection()
            self.populate_md_cbos()

            # Domain Creation - Connections
            self.create_md_polygon_btn.clicked.connect(self.create_md_polygon)
            self.rollback_md_btn.clicked.connect(self.cancel_mult_domains_edits)
            self.delete_md_schema_btn.clicked.connect(self.delete_schema_md)
            # self.md_help_btn.clicked.connect()
            self.change_md_name_btn.clicked.connect(self.change_md_name)
            self.delete_md_btn.clicked.connect(self.delete_md)
            self.md_center_btn.clicked.connect(self.md_center)

            self.schematize_md_btn.clicked.connect(self.schematize_md)
            self.create_connectivity_btn.clicked.connect(self.open_multiple_domains_connectivity_dialog)

            self.grid_lyr = self.lyrs.data["grid"]["qlyr"]
            self.mult_domains = self.lyrs.data["mult_domains"]["qlyr"]
            self.schema_md_cells = self.lyrs.data["schema_md_cells"]["qlyr"]
            self.user_md_connect_lines = self.lyrs.data["user_md_connect_lines"]["qlyr"]
            self.mult_domains.afterCommitChanges.connect(self.save_user_md)
            self.md_name_cbo.currentIndexChanged.connect(self.md_index_changed)

    def setup_connection(self):
        """
        Sets up required database connections for handling domain operations.

        Ensures smooth communication between the widget and the database, as well as
        connectivity with other components of the application.
        """
        if self.iface is None:
            return
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_md_cbos(self, fid=None):
        """
        Populates the ComboBoxes in the UI with data from the multiple domains.

        Retrieves necessary domain data from the database and adds it to the ComboBoxes
        for user selection and interaction.
        """
        self.md_name_cbo.clear()
        self.cellsize_le.clear()
        self.cellsize_le.setVisible(False)
        self.cellsize_lbl.setVisible(False)

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

        # cell_size = float(self.gutils.get_cont_par("CELLSIZE"))
        # self.cellsize_le.setText(str(cell_size))

        self.uncheck_md_btns()

    def md_index_changed(self):
        """
        Handles actions when the index of the domain ComboBox changes.

        Updates the UI and performs necessary operations to reflect changes based
        on the selected domain.
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

    def create_md_polygon(self):
        """
        Creates a polygon for a selected domain.

        This method allows the user to define or edit polygons representing domains
        directly within the application.
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
        Saves changes made to the multiple domains.

        This method ensures that all modifications to the domains are committed
        to the database or application environment.
        """
        mult_domains_edited = self.lyrs.save_lyrs_edits("mult_domains")
        if mult_domains_edited:
            pass
        self.uncheck_md_btns()

    def uncheck_md_btns(self):
        """
        Unchecks all toggle buttons related to multiple domains.

        A utility method to reset the toggle button states in the UI.
        """
        self.create_md_polygon_btn.setChecked(False)

    def cancel_mult_domains_edits(self):
        """
        Cancels all edits to the multiple domains.

        Reverts any unsaved changes and restores the domains to their previous
        state.
        """
        user_lyr_edited = self.lyrs.rollback_lyrs_edits("mult_domains")
        if user_lyr_edited:
            self.uncheck_md_btns()
            pass

    def schematize_md(self):
        """
        Function to schematize the multiple domains
        """

        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            self.uc.log_info("There is no grid! Please create it before running tool.")
            return

        # Check if there is data on the domain_cells and ask you if he wants to override

        QApplication.setOverrideCursor(Qt.WaitCursor)

        pd = QProgressDialog("Schematizing the subdomains...", "Cancel", 0, 0)
        pd.setWindowModality(Qt.WindowModal)
        pd.setMinimumDuration(0)
        pd.setRange(0, 0)
        pd.show()

        QApplication.processEvents()

        # Clear the schema_md_connect_cells
        self.gutils.clear_tables("schema_md_cells")

        # Clear the user_md_connect_lines
        self.gutils.clear_tables("user_md_connect_lines")

        domain_ids = self.gutils.execute("SELECT fid FROM mult_domains ORDER BY fid;").fetchall()

        for domain_id in domain_ids:
            self.gutils.execute(f"""
            INSERT INTO schema_md_cells (grid_fid, domain_fid, domain_cell)
            SELECT grid.fid, md.fid, ROW_NUMBER() OVER (ORDER BY grid.fid) AS domain_cell
            FROM mult_domains md
            JOIN grid ON ST_Intersects(CastAutomagic(md.geom), CastAutomagic(grid.geom)) 
            WHERE md.fid = {domain_id[0]};         
            """).fetchall()

        self.intersected_domains()

        self.lyrs.lyrs_to_repaint = [self.schema_md_cells, self.mult_domains, self.user_md_connect_lines]
        self.lyrs.repaint_layers()

        self.uc.bar_info("Schematizing multiple domains finished!")
        self.uc.log_info("Schematizing multiple domains finished!")

        QApplication.restoreOverrideCursor()

    def intersected_domains(self):
        """
        Identifies domains that intersect with each other.

        This method analyzes spatial relationships between domains and determines
        intersections, which are then used for further operations.
        """

        downstream_domains = {}
        subdomain_connectivities = self.gutils.execute(f"""
                                           SELECT
                                               im.fid, 
                                               im.fid_subdomain_1,
                                               im.fid_subdomain_2,
                                               im.fid_subdomain_3,
                                               im.fid_subdomain_4,
                                               im.fid_subdomain_5,
                                               im.fid_subdomain_6,
                                               im.fid_subdomain_7,
                                               im.fid_subdomain_8,
                                               im.fid_subdomain_9
                                           FROM
                                               mult_domains_con AS im;
                                                       """).fetchall()
        if subdomain_connectivities:
            for subdomain_connectivity in subdomain_connectivities:
                subdomain_fid = subdomain_connectivity[0]
                downstream_domains[subdomain_fid] = []
                for i in range(1, 10):
                    if subdomain_connectivity[i] not in [0, NULL, 'NULL', None]:
                        downstream_domains[subdomain_fid].append(subdomain_connectivity[i])

        # Create the intersected lines
        polygon_layer = self.lyrs.data["mult_domains"]["qlyr"]

        # Create a new memory layer for intersections with the same CRS as the polygon layer
        intersection_layer = self.lyrs.data["user_md_connect_lines"]["qlyr"]
        provider = intersection_layer.dataProvider()

        # Collect all features from the polygon layer
        features = list(polygon_layer.getFeatures())

        # Initialize a counter for the intersection feature's fid
        intersection_id = 1

        tolerance = 0.1

        # Iterate over all unique pairs of polygons using itertools.combinations
        for feat1, feat2 in itertools.permutations(features, 2):
            geom1_buff = feat1.geometry().buffer(tolerance, 5)  # Apply buffer with a segment count of 5
            geom2_buff = feat2.geometry().buffer(tolerance, 5)

            # Check if the two geometries touch (i.e., share a boundary)
            if geom1_buff.intersection(geom2_buff):
                # Compute the shared border between the two geometries
                original_geom1 = feat1.geometry()
                original_geom2 = feat2.geometry()
                intersect_geom = original_geom1.intersection(original_geom2)

                # Create a new feature for the intersection layer
                new_feat = QgsFeature()
                new_feat.setGeometry(intersect_geom)
                # Here we assume that the polygon layer's unique identifier is stored in the "fid" field.
                if feat2["fid"] in downstream_domains[feat1["fid"]]:
                    new_feat.setAttributes([intersection_id, feat1["fid"], feat2["fid"], ""])
                    provider.addFeature(new_feat)

                    intersection_id += 1

        intersected_cells = self.gutils.execute("""
            SELECT grid.fid, user_md_connect_lines.down_domain_fid, ST_AsText(ST_Centroid(GeomFromGPB(grid.geom)))
            FROM grid
            JOIN user_md_connect_lines ON ST_Intersects(CastAutomagic(grid.geom), CastAutomagic(user_md_connect_lines.geom))
        """).fetchall()

        # Remove connectivity grid inside channels
        channel_interior_nodes = self.gutils.execute("""SELECT grid_fid FROM chan_interior_nodes;""").fetchall()
        if channel_interior_nodes:
            channel_interior_nodes = [item[0] for item in channel_interior_nodes]

        # Iterate over selected grid cells and update schema_md_connect_cells
        for grid_fid, down_domain_fid, geom_text in intersected_cells:
            if grid_fid not in channel_interior_nodes:
                sql_qry = """
                    UPDATE schema_md_cells 
                    SET down_domain_fid = ?, geom = ST_GeomFromText(?)
                    WHERE grid_fid = ?;
                """
                # Execute the query with parameters
                self.gutils.execute(sql_qry, (down_domain_fid, geom_text, grid_fid))

    def delete_schema_md(self):
        """
        Deletes the schematic data of the domains.

        A utility method to clean up domain schematics when they are no longer
        needed.
        """

        QApplication.setOverrideCursor(Qt.WaitCursor)

        self.gutils.clear_tables("schema_md_cells")
        self.gutils.clear_tables("mult_domains_methods")
        self.gutils.clear_tables("mult_domains_con")

        self.save_user_md()

        self.uc.bar_info("Schematized multiple domains deleted!")
        self.uc.log_info("Schematized multiple domains deleted!")

        self.lyrs.clear_rubber()
        self.lyrs.lyrs_to_repaint = [self.schema_md_cells]
        self.lyrs.repaint_layers()

        QApplication.restoreOverrideCursor()

    def change_md_name(self):
        """
        Changes the name of a selected domain.

        Allows the user to rename a domain, ensuring that the change is
        reflected everywhere.
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
        self.gutils.execute(f"UPDATE mult_domains_methods SET subdomain_name = '{new_name}' WHERE fid = {fid};")
        self.gutils.execute(f"UPDATE mult_domains_con SET subdomain_name = '{new_name}' WHERE fid = {fid};")
        self.populate_md_cbos()
        self.uc.bar_info("Domain name changed!")
        self.uc.log_info("Domain name changed!")

    def delete_md(self):
        """
        Deletes a selected domain.

        Completely removes the domain's data from the application and database.
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
        self.gutils.execute(f"DELETE FROM mult_domains_methods WHERE fid = {fid};")
        self.gutils.execute(f"DELETE FROM mult_domains_con WHERE fid = {fid};")
        self.populate_md_cbos()
        self.mult_domains.triggerRepaint()
        self.uc.bar_info("Domain deleted!")
        self.uc.log_info("Domain deleted!")

    def delete_con(self):
        """
        Deletes connectivity information for a selected domain.

        Removes any network connections or relationships associated with the domain.
        """
        if not self.connect_line_cbo.count():
            return
        fid_qry = self.gutils.execute(f"SELECT fid FROM user_md_connect_lines WHERE fid = '{self.connect_line_cbo.currentText()}';").fetchone()
        if fid_qry:
            fid = fid_qry[0]
        else:
            return
        q = "Are you sure, you want delete the current connectivity line?"
        if not self.uc.question(q):
            return
        self.gutils.execute(f"DELETE FROM user_md_connect_lines WHERE fid = {fid};")
        self.populate_md_cbos()
        # self.populate_con_cbo()
        # self.connect_lines.triggerRepaint()
        self.uc.bar_info("Connectivity line deleted!")
        self.uc.log_info("Connectivity line deleted!")

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

    def open_multiple_domains_connectivity_dialog(self):
        """
        Opens the connectivity dialog for multiple domains.

        Allows the user to manage and define relationships between connected
        domains.
        """
        dlg = MultipleDomainsConnectivityDialog(self.iface, self.con, self.lyrs)
        ok = dlg.exec_()
        if not ok:
            return
        else:
            pass

    def save_user_md(self):
        """
        Saves the user-defined multiple domain data.

        Ensures that the custom domain data provided by the user is validated
        and stored in the application and database.
        """
        md_names = self.gutils.execute("""SELECT fid, name FROM mult_domains""").fetchall()
        if md_names:
            i = 0
            for name in md_names:
                # Adjust the name if none was provided
                name_adj = name[1]
                if name_adj is None:
                    new_name = f"Subdomain_{i}"
                    self.gutils.execute(f"""
                                        UPDATE mult_domains
                                        SET name = '{new_name}'
                                        WHERE fid = {name[0]};""")
                    name_adj = new_name
                    i += 1
                # Check if the name already exists in mult_domains_methods (subdomain_name field)
                name_exists = self.gutils.execute(f"SELECT COUNT(*) FROM mult_domains_methods WHERE subdomain_name = '{name_adj}';").fetchone()
                if name_exists:
                    if name_exists[0] > 0:
                        msg = f"Name '{name_adj}' already exists in the geopackage.\n\n"
                        msg += "Would you like to replace it?"
                        answer = self.uc.customized_question("FLO-2D", msg)
                        if answer == QMessageBox.Yes:
                            self.gutils.execute(f"DELETE FROM mult_domains_methods WHERE subdomain_name = '{name_adj}'")
                            self.gutils.execute(f"DELETE FROM mult_domains_con WHERE subdomain_name = '{name_adj}'")
                            self.gutils.execute(f"INSERT INTO mult_domains_methods (subdomain_name, fid_method) VALUES ('{name_adj}', {name[0]})")
                            self.gutils.execute(f"INSERT INTO mult_domains_con (subdomain_name, fid) VALUES ('{name_adj}', {name[0]});")
                    else:
                        # Insert the name into mult_domains_methods
                        self.gutils.execute(f"INSERT INTO mult_domains_methods (subdomain_name, fid_method) VALUES ('{name_adj}', {name[0]})")
                        self.gutils.execute(f"INSERT INTO mult_domains_con (subdomain_name, fid) VALUES ('{name_adj}', {name[0]});")
                        self.uc.log_info(f"Name '{name_adj}' added to mult_domains_methods.")

        self.populate_md_cbos()

    def find_common_coordinates(self, project_paths):
        """
        Finds and returns the common coordinates between multiple domains.

        A utility method to identify overlapping or shared spatial data between
        domains.
        """

        import pandas as pd
        from collections import defaultdict

        def h5_coord_reader(h5_path, dset="/Input/Grid/COORDINATES", chunksize=10000):
            """
            Yield pandas DataFrames with columns ['x','y'] from HDF5 in chunks.
            Keeps the rest of the code unchanged.
            """

            with h5py.File(h5_path, "r") as hdf:
                coords = hdf[dset]  # expected shape (N, 2)
                n = coords.shape[0]
                for start in range(0, n, chunksize):
                    end = min(start + chunksize, n)
                    chunk = coords[start:end]  # (m, 2)
                    # Build a DataFrame that looks like your CSV chunks
                    yield pd.DataFrame(
                        {"x": chunk[:, 0].astype(float), "y": chunk[:, 1].astype(float)}
                    )

        coords_count = defaultdict(int)  # Dictionary to count occurrences of each coordinate

        for path in project_paths:
            if path:
                # Read the file in chunks to manage memory usage
                chunksize = 10000  # Adjust based on your memory availability

                if os.path.isfile(os.path.join(path, "Input.hdf5")):
                    reader = h5_coord_reader(os.path.join(path, "Input.hdf5"),
                                             dset="/Input/Grid/COORDINATES",
                                             chunksize=chunksize)
                elif os.path.isfile(os.path.join(path, "TOPO.DAT")):
                    reader = pd.read_csv(os.path.join(path, "TOPO.DAT"),
                                         sep=r'\s+',
                                         header=None,
                                         names=['x', 'y', 'elevation'],
                                         chunksize=chunksize)
                elif os.path.isfile(os.path.join(path, "CADPTS.DAT")):
                    reader = pd.read_csv(os.path.join(path, "CADPTS.DAT"),
                                         sep=r'\s+',
                                         header=None,
                                         names=['id', 'x', 'y'],
                                         chunksize=chunksize)
                else:
                    self.uc.bar_error(
                        "No Input.hdf5, TOPO.DAT or CADPTS.DAT found in the project directory.")
                    self.uc.log_info(
                        "No Input.hdf5, TOPO.DAT or CADPTS.DAT found in the project directory.")
                    return

                seen_in_this_file = set()
                for chunk_index, chunk in enumerate(reader):
                    # Use tuple pairs for efficient comparison and storage
                    current_coords = set(zip(chunk['x'], chunk['y']))
                    seen_in_this_file.update(current_coords)

                # Update the global count only once per file to avoid double counting within the same file
                for coord in seen_in_this_file:
                    coords_count[coord] += 1

        # Filter coordinates that appear in at least two different files and convert them to "x y" format at the end
        common_coords = {(float(coord[0]), float(coord[1]))
                         for coord, count in coords_count.items() if count >= 2}

        return common_coords