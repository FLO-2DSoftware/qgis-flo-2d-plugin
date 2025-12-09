import math
import os.path
import time
from itertools import combinations

from ..deps import safe_h5py as h5py
import numpy as np
from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QFileDialog, QApplication, QProgressDialog, QMessageBox
from qgis.PyQt.QtCore import NULL

from .dlg_components import ComponentsDialog
from .dlg_multidomain_connectivity import MultipleDomainsConnectivityDialog
from .multiple_domains_editor_widget import MultipleDomainsEditorWidget
from .ui_utils import load_ui
from ..flo2d_ie.flo2d_parser import ParseDAT
from ..flo2d_ie.flo2dgeopackage import Flo2dGeoPackage
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

MAX_SUBDOMAINS = 15

uiDialog, qtBaseClass = load_ui("import_multiple_domains")


class ImportMultipleDomainsDialog(qtBaseClass, uiDialog):
    """
    This class manages the dialog for importing multiple domains. It provides
    functionality for adding/removing subdomains, selecting folders, handling
    connectivity, and importing global and subdomain-specific data files.
    """

    def __init__(self, con, iface, lyrs):
        """
        Initializes the ImportMultipleDomainsDialog class.

        Sets up the dialog components, initializes attributes, and prepares the
        dialog for interaction with the user.
        """

        # Call parent class initializers
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)

        # Initialize attributes
        self.f2g = None
        self.iface = iface
        self.con = con
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = GeoPackageUtils(con, iface)
        self.parser = ParseDAT()
        self.chunksize = float("inf")

        # Setup the UI
        self.setupUi(self)

        # Initialize subdomain dialog elements
        self.initialize_subdomain_elements()

        # Setup button signal associations
        self.setup_signals()

        # Populate subdomains into the dialog
        self.populate_subdomains()

    def initialize_subdomain_elements(self):
        """
        Initializes the subdomains dialog elements.

        Creates a list of subdomain-related UI elements such as labels, line edits,
        and buttons for easy management.
        """
        # Group related UI elements as subdomains
        self.subdomains_dlg_elements = [
            [self.label_1, self.sub1_le, self.sub1_tb],
            [self.label_2, self.sub2_le, self.sub2_tb],
            [self.label_3, self.sub3_le, self.sub3_tb],
            [self.label_4, self.sub4_le, self.sub4_tb],
            [self.label_5, self.sub5_le, self.sub5_tb],
            [self.label_6, self.sub6_le, self.sub6_tb],
            [self.label_7, self.sub7_le, self.sub7_tb],
            [self.label_8, self.sub8_le, self.sub8_tb],
            [self.label_9, self.sub9_le, self.sub9_tb],
            [self.label_10, self.sub10_le, self.sub10_tb],
            [self.label_11, self.sub11_le, self.sub11_tb],
            [self.label_12, self.sub12_le, self.sub12_tb],
            [self.label_13, self.sub13_le, self.sub13_tb],
            [self.label_14, self.sub14_le, self.sub14_tb],
            [self.label_15, self.sub15_le, self.sub15_tb],
        ]

    def setup_signals(self):
        """
        Sets up signals for all UI elements (e.g., buttons).

        Connects button clicks with their corresponding event-handling functions
        to enable user interaction.
        """

        # Connect subdomain file selection buttons
        for index, (_, line_edit, button) in enumerate(self.subdomains_dlg_elements, start=1):
            button.clicked.connect(lambda _, le=line_edit, i=index: self.select_subdomain_folder(le, i))

        # Connect cancel, add, remove, and OK buttons
        self.add_subdomain_btn.clicked.connect(self.add_subdomain)
        self.remove_subdomain_btn.clicked.connect(self.remove_subdomain)

        # Manage domain connectivity
        self.connect_btn.clicked.connect(self.open_multiple_domains_connectivity_dialog)

    def add_subdomain(self):
        """
        Adds a new subdomain.

        Handles the user input for creating a new subdomain entry, and updates
        the dialog as well as the internal database or project structure.
        """
        sub_paths = self.gutils.execute("SELECT fid, subdomain_path FROM mult_domains_methods;").fetchall()
        if sub_paths:
            self.hide_subdomains(len(sub_paths) + 1)
        else:
            self.hide_subdomains(1)

    def remove_subdomain(self):
        """
        Removes an existing subdomain.

        Deletes a subdomain based on user selection and cleans up relevant data
        from the database or UI components.
        """

        # Get last visible element
        last_visible_element_idx = None
        for counter, elements in enumerate(self.subdomains_dlg_elements):
            if elements[0].isVisible():
                last_visible_element_idx = counter

        if not last_visible_element_idx:
            self.subdomains_dlg_elements[0][0].setVisible(True)
            self.subdomains_dlg_elements[0][1].setVisible(True)
            self.subdomains_dlg_elements[0][2].setVisible(True)

        for sub_element in self.subdomains_dlg_elements[last_visible_element_idx]:
            sub_element.setVisible(False)

        if self.subdomains_dlg_elements[last_visible_element_idx][1].text() != "":
            sub_path = self.subdomains_dlg_elements[last_visible_element_idx][1].text()
            fid = self.gutils.execute(f"SELECT fid FROM mult_domains_methods WHERE subdomain_path = '{sub_path}';").fetchone()
            if fid:
                self.gutils.execute(f"DELETE FROM mult_domains_methods WHERE fid = {fid[0]};")
                self.gutils.execute(f"DELETE FROM mult_domains_con WHERE fid = {fid[0]};")
            self.subdomains_dlg_elements[last_visible_element_idx][1].setText("")

    def open_multiple_domains_connectivity_dialog(self):
        """
        Opens the dialog for managing domain connectivity.

        Launches an interface allowing the user to define the relationships
        between domains such as upstream and downstream connections.
        """
        dlg = MultipleDomainsConnectivityDialog(self.iface, self.con, self.lyrs)
        ok = dlg.exec_()
        if not ok:
            return
        else:
            pass

    def populate_subdomains(self):
        """
        Populates the dialog with existing subdomain data.

        Retrieves data associated with subdomains (e.g., from the database or loaded
        project files) and displays it on the user interface for review or editing.
        """

        sub_paths = self.gutils.execute("SELECT fid, subdomain_path FROM mult_domains_methods;").fetchall()
        if sub_paths:
            self.hide_subdomains(len(sub_paths))
            for sub_path in sub_paths:
                fid = sub_path[0]
                path = sub_path[1]
                self.subdomains_dlg_elements[fid - 1][1].setText(path)
        else:
            self.hide_subdomains(0)

    def hide_subdomains(self, n_subdomains):
        """
        Function to hide the subdomains
        """
        for i, elements in enumerate(self.subdomains_dlg_elements):
            for sub_element in elements:
                if i >= n_subdomains:
                    sub_element.setVisible(False)
                else:
                    sub_element.setVisible(True)


    def select_subdomain_folder(self, domain_le, domain_n):
        """
        Allows the user to select a folder containing subdomain data.
        """
        s = QSettings()
        project_dir = s.value("FLO-2D/lastGdsDir")
        domain_dir = QFileDialog.getExistingDirectory(
            None, "Select Domain folder", directory=project_dir
        )
        if not domain_dir:
            return

        check_subdomains_path = self.gutils.execute(f"""SELECT subdomain_path FROM mult_domains_methods;""").fetchall()
        if check_subdomains_path:
            for subdomains_path in check_subdomains_path:
                if domain_dir == subdomains_path[0]:
                    self.uc.log_info(f"This subdomain is already selected. Please, select another subdomain project.")
                    self.uc.bar_warn(f"This subdomain is already selected. Please, select another subdomain project.")
                    return

        domain_le.setText(domain_dir)

        files = os.listdir(domain_dir)
        hdf_file = any(f.startswith("Input.hdf5") for f in files)
        multdomain_dat = any(f.startswith("MULTIDOMAIN.DAT") for f in files)
        cadpts_ds = any(f.startswith("CADPTS_DS") for f in files)

        subdomain_name = os.path.basename(domain_dir)

        # Insert into mult_domains_methods
        qry = f"""INSERT INTO mult_domains_methods (subdomain_name, subdomain_path) 
                VALUES ('{subdomain_name}', '{domain_dir}');"""
        self.gutils.execute(qry)

        # Add a line to the method
        qry_method = f"""INSERT INTO mult_domains_con (subdomain_name) VALUES ('{subdomain_name}');"""
        self.gutils.execute(qry_method)

        # Get the recent added fid
        qry_method_fid = f"""SELECT fid FROM mult_domains_con WHERE subdomain_name = '{subdomain_name}';"""
        method_fid = self.gutils.execute(qry_method_fid).fetchone()[0]

        # Project has MULTIDOMAIN.DAT
        if hdf_file:

            n_subdomains = []

            hdf5_file = os.path.join(domain_dir, "Input.hdf5")

            # Read the HDF5 dataset
            with h5py.File(hdf5_file, "r") as hdf:
                try:
                    arr = hdf["/Input/Multiple Domains/MULTIDOMAIN"][()]  # shape (N, 3), ints
                    if arr.ndim != 2 or arr.shape[1] < 1:
                        raise ValueError("MULTIDOMAIN must be a 2D array with at least 1 column")
                    cs = np.asarray(arr[:, 0])  # connected_subdomain column as 1D
                except:
                    cs = None

            # Mirror the ASCII logic: every time subdomain id changes, that is a new block
            if cs is not None and cs.size > 0:
                i = 1
                prev = None
                for sub in cs:
                    if prev is None:
                        n_subdomains.append(i)
                        i += 1
                        prev = sub
                    elif sub != prev:
                        n_subdomains.append(i)
                        i += 1
                        prev = sub

                for idx in n_subdomains:
                    qry_method = f"""
                        UPDATE mult_domains_con 
                        SET mult_domains_{idx} = 2
                        WHERE fid = {method_fid};
                    """
                    self.gutils.execute(qry_method)

            qry = f"""
                UPDATE mult_domains_methods 
                SET fid_method = {method_fid}
                WHERE subdomain_name = '{subdomain_name}';
            """
            self.gutils.execute(qry)

        elif multdomain_dat:

            n_subdomains = []

            multidomain_file = os.path.join(domain_dir, "MULTIDOMAIN.DAT")

            with open(multidomain_file, "r") as f:

                i = 1

                for line in f:
                    data = line.strip().split()

                    if not data:
                        continue

                    if data[0] == "N":
                        # New subdomain identifier
                        n_subdomains.append(i)
                        i += 1

            for i in n_subdomains:
                qry_method = f"""
                                UPDATE mult_domains_con 
                                SET mult_domains_{i} = 1
                                WHERE fid = {method_fid}; 
                                """
                self.gutils.execute(qry_method)

            # Insert into mult_domains_methods
            qry = f"""
                        UPDATE mult_domains_methods 
                        SET fid_method = {method_fid}
                        WHERE subdomain_name = '{subdomain_name}'; 
                    """
            self.gutils.execute(qry)

        # CADPTS
        elif cadpts_ds:
            cadpts_files = []

            for f in files:
                if f.startswith("CADPTS_DS"):
                    cadpts_files.append(f)

            # CADPTS_DS and Ups-Dows-Connectivity_D always have the same size
            n_connected_subdomains = len(cadpts_files)

            for i in range(1, n_connected_subdomains + 1):
                qry_method = f"""
                                   UPDATE mult_domains_con 
                                   SET ds_file_{i} = 1
                                   WHERE fid = {method_fid}; 
                               """
                self.gutils.execute(qry_method)

            # Insert into mult_domains_methods
            qry = f"""
                       UPDATE mult_domains_methods 
                       SET fid_method = {method_fid}
                       WHERE subdomain_name = '{subdomain_name}'; 
                   """
            self.gutils.execute(qry)

        # No connection file
        else:

            # Insert into mult_domains_methods
            qry = f"""
                       UPDATE mult_domains_methods 
                       SET fid_method = {method_fid}
                       WHERE subdomain_name = '{subdomain_name}'; 
                   """
            self.gutils.execute(qry)

        self.uc.log_info(f"Subdomain {domain_n} data saved to geopackage.")
        self.uc.bar_info(f"Subdomain {domain_n} data saved to geopackage.")

    def import_global_domain(self):
        """
        Imports the global domain data. Handles the parsing and importing
        of global domain details from files into the geopackage.
        """
        subdomains_paths = self.fetch_subdomain_paths()
        total_subdomains = sum(1 for path in subdomains_paths if path)

        md_editor = MultipleDomainsEditorWidget(self.iface, self.lyrs)
        common_coords = md_editor.find_common_coordinates(subdomains_paths)

        self.import_global_grid(total_subdomains, subdomains_paths, common_coords)

        self.import_components(total_subdomains, subdomains_paths)

        self.finalize_import()


    def create_support_tables(self):
        """
        Function to create tables that will be used as support during the import process
        :return:
        """

        # Drop prior tables and any stale registrations
        for t in ("stage_cells", "stage_schema_md"):
            self.gutils.execute("DELETE FROM gpkg_contents WHERE table_name = ?;", (t,))
            self.gutils.execute(f"DROP TABLE IF EXISTS {t};")

        # Create fresh tables
        self.gutils.execute("""
                CREATE TABLE stage_cells (
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    n_value REAL,
                    elevation REAL,
                    PRIMARY KEY(x, y)
                );
            """)
        self.gutils.execute("""
                CREATE TABLE stage_schema_md (
                    domain_fid  INTEGER NOT NULL,
                    domain_cell INTEGER NOT NULL,
                    x REAL NOT NULL,
                    y REAL NOT NULL
                );
            """)

        # Register both as aspatial so QGIS exposes them
        # identifier uses the same name for clarity in the Browser and Layer properties
        now_sql = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
        self.gutils.execute(f"""
                INSERT INTO gpkg_contents (
                    table_name, data_type, identifier, description, last_change,
                    min_x, min_y, max_x, max_y, srs_id
                )
                VALUES ('stage_cells', 'aspatial', 'stage_cells', '',
                        {now_sql}, NULL, NULL, NULL, NULL, NULL);
            """)
        self.gutils.execute(f"""
                INSERT INTO gpkg_contents (
                    table_name, data_type, identifier, description, last_change,
                    min_x, min_y, max_x, max_y, srs_id
                )
                VALUES ('stage_schema_md', 'aspatial', 'stage_schema_md', '',
                        {now_sql}, NULL, NULL, NULL, NULL, NULL);
            """)

        # Helpful index for the join during finalize
        self.gutils.execute("CREATE INDEX IF NOT EXISTS idx_stage_schema_xy ON stage_schema_md(x, y);")\

    def import_global_grid(self, total_subdomains, subdomains_paths, common_coords):
        """
        Function to import the global grid without reassigning grid fids

        :return:
        """
        cell_size = None

        progress_dialog = QProgressDialog(f"Importing Subdomain 1...", None, 1, total_subdomains + 1)
        progress_dialog.setWindowTitle("FLO-2D Multiple Domains Import")
        progress_dialog.setModal(True)
        progress_dialog.forceShow()
        progress_dialog.setValue(1)
        QApplication.processEvents()

        # Create support tables to avoid filling the grid fid
        self.create_support_tables()

        # import the subdomains one by one
        for subdomain, subdomain_path in enumerate(subdomains_paths, start=1):
            if subdomain_path:
                hdf5_file = f"{subdomain_path}/Input.hdf5"
                if os.path.isfile(hdf5_file):
                    self.f2g = Flo2dGeoPackage(self.con, self.iface, parsed_format=Flo2dGeoPackage.FORMAT_HDF5)
                else:
                    self.f2g = Flo2dGeoPackage(self.con, self.iface)
                    fname = subdomain_path + "/CONT.DAT"
                    if not self.f2g.set_parser(fname):
                        return

                start_time = time.time()
                cell_size = self.import_subdomains_mannings_n_topo(subdomain_path, subdomain, common_coords)
                time_elapsed = self.calculate_time_elapsed(start_time)
                self.uc.log_info(f"Time Elapsed to import Subdomain {subdomain}: {time_elapsed}")
                progress_dialog.setLabelText(f"Importing Subdomain {subdomain + 1}...")
                progress_dialog.setValue(subdomain + 1)

        progress_dialog.close()

        # Get the min x and min y
        row = self.gutils.execute("""
            SELECT MIN(x), MAX(y)
            FROM stage_cells
            LIMIT 1;
        """).fetchone()
        if not row or row[0] is None or row[1] is None:
            self.uc.bar_warn("Global domain boundary is not defined properly.")
            self.uc.log_info("Global domain boundary is not defined properly.")
            return
        else:
            min_x, max_y = float(row[0]), float(row[1])
            self.reassing_grid_fids(min_x, max_y, cell_size)

    def reassing_grid_fids(self, xmin, ymax, cell_size):
        """
        Function to reassing the grids fid to match the original global domain
        """
        # Build the fid map as a regular table
        self.gutils.execute("DROP TABLE IF EXISTS grid_fid_map;")
        self.gutils.execute("""
            CREATE TABLE grid_fid_map AS
            WITH params AS (
              SELECT CAST(:xmin AS REAL) AS xmin,
                     CAST(:ymax AS REAL) AS ymax,
                     CAST(:cs   AS REAL) AS cs
            ),
            idx AS (
              SELECT
                c.x, c.y, c.n_value, c.elevation,
                CAST(FLOOR((c.x - (SELECT xmin FROM params)) / (SELECT cs FROM params)) AS INTEGER) AS col_idx,
                CAST(FLOOR(((SELECT ymax FROM params) - c.y) / (SELECT cs FROM params)) AS INTEGER) AS row_idx
              FROM stage_cells c
            )
            SELECT
              ROW_NUMBER() OVER (ORDER BY col_idx, row_idx) AS fid,
              x, y, n_value, elevation
            FROM idx;
        """, {"xmin": float(xmin), "ymax": float(ymax), "cs": float(cell_size)})

        # Clear targets
        self.gutils.clear_tables("grid")

        # Fast path A: build polygon in Python batches using your existing builder
        # This avoids relying on Spatialite functions and matches your current storage.
        B = self.chunksize or 50000
        cur = self.gutils.execute("SELECT fid, x, y, n_value, elevation FROM grid_fid_map ORDER BY fid;")
        total = self.gutils.execute("SELECT COUNT(*) FROM grid_fid_map;").fetchone()[0]
        progress_dialog = QProgressDialog(f"Reassigning grid fids...", None, 0, total)
        progress_dialog.setWindowTitle("FLO-2D Multiple Domains Import")
        progress_dialog.setModal(True)
        progress_dialog.forceShow()
        progress_dialog.setValue(0)
        QApplication.processEvents()

        batch = []
        for i, (fid, x, y, nval, elev) in enumerate(cur, start=1):
            poly_wkt = self.gutils.build_square(f"{x} {y}", float(cell_size))
            batch.append((int(fid), float(nval), float(elev), poly_wkt))
            progress_dialog.setValue(i)
            if len(batch) >= B:
                self.gutils.execute_many(
                    "INSERT INTO grid(fid, n_value, elevation, geom) VALUES(?, ?, ?, ?);",
                    batch
                )
                batch.clear()

        if batch:
            self.gutils.execute_many(
                "INSERT INTO grid(fid, n_value, elevation, geom) VALUES(?, ?, ?, ?);",
                batch
            )

        # Schema links in one SQL
        self.gutils.execute("""
            INSERT OR IGNORE INTO schema_md_cells(grid_fid, domain_fid, domain_cell)
            SELECT m.fid, s.domain_fid, s.domain_cell
            FROM stage_schema_md s
            JOIN grid_fid_map m ON m.x = s.x AND m.y = s.y;
        """)

        shared_grids = self.gutils.execute("""SELECT fid, ST_AsText(geom) FROM schema_md_cells WHERE grid_fid IS NULL;""").fetchall()
        update_grids = []
        for sg in shared_grids:
            geom_wkt = sg[1]
            x_str, y_str = geom_wkt.strip("POINT()").split()
            x, y = float(x_str), float(y_str)
            grid = self.gutils.grid_on_point(x, y)
            update_grids.append((grid, sg[0]))

        self.gutils.execute_many("""UPDATE schema_md_cells SET grid_fid = ? WHERE fid = ?;""", update_grids)

        # Drop staging and map tables to keep the GeoPackage clean
        self.gutils.execute("DROP TABLE IF EXISTS stage_cells;")
        self.gutils.execute("DROP TABLE IF EXISTS stage_schema_md;")
        self.gutils.execute("DROP TABLE IF EXISTS grid_fid_map;")

        progress_dialog.close()

    def fetch_subdomain_paths(self):
        """Fetch and return all subdomain paths from the UI."""
        return [getattr(self, f'sub{i}_le').text() for i in range(1, MAX_SUBDOMAINS + 1)]

    def calculate_time_elapsed(self, start_time):
        """Calculate and format elapsed time."""
        elapsed_time = time.time() - start_time
        hours, remainder = divmod(elapsed_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        return "{:02}:{:02}:{:02}".format(int(hours), int(minutes), int(seconds))

    def finalize_import(self):
        """Finalize the import process by refreshing the UI and showing success messages."""
        # check the hydraulic structures - this is a workaround
        if not self.gutils.is_table_empty("struct"):
            self.gutils.set_cont_par("IHYDRSTRUCT", 1)
        self.gutils.path = self.gutils.get_gpkg_path()
        self.lyrs.load_all_layers(self.gutils)
        self.lyrs.zoom_to_all()
        self.uc.log_info("Import of Multiple Domains finished successfully")
        self.uc.bar_info("Import of Multiple Domains finished successfully")

    def import_subdomains_mannings_n_topo(self, subdomain_path, subdomain, common_coords):
        """
        Imports subdomain-specific Manning's N and TOPO data.

        This function is responsible for parsing Manning's N roughness coefficient
        and TOPO (geometry, elevation) data for respective subdomains, validating
        them, and saving/updating them in the project database or corresponding tables.
        """

        # try:
        #     QApplication.setOverrideCursor(Qt.WaitCursor)

        data, cell_size, man, coords, elev, hdf5_used, f1_used, f2_used = self.get_subdomain_data(subdomain_path)
        default_n = float(self.gutils.get_cont_par("MANNING"))
        batch_cells, batch_schema = [], []

        # Update CELLSIZE
        self.gutils.set_cont_par("CELLSIZE", int(cell_size))

        # Batch processing for better performance
        batch_size = self.chunksize  # Set batch size from existing chunksize variable

        for i, row in enumerate(data, start=1):

            x, y = map(float, row[coords])

            if man and elev:
                n_val = float(row[man][0] if isinstance(row[man], (list, tuple)) else row[man])
                z_val = float(row[elev][0] if isinstance(row[elev], (list, tuple)) else row[elev])
            else:
                n_val, z_val = default_n, -9999.0

            if (x, y) in common_coords:
                # Insert only once thanks to PK(x,y); duplicates from other subdomains are ignored
                batch_cells.append((x, y, n_val, z_val))
            else:
                # Unique to this subdomain – insert
                batch_cells.append((x, y, n_val, z_val))

            batch_schema.append((int(subdomain), int(i), x, y))

            if len(batch_cells) >= batch_size:
                self.gutils.execute_many(
                    "INSERT OR IGNORE INTO stage_cells(x, y, n_value, elevation) VALUES(?, ?, ?, ?);",
                    batch_cells
                )
                batch_cells.clear()

            if len(batch_schema) >= batch_size:
                self.gutils.execute_many(
                    "INSERT INTO stage_schema_md(domain_fid, domain_cell, x, y) VALUES(?, ?, ?, ?);",
                    batch_schema
                )
                batch_schema.clear()

        if batch_cells:
            self.gutils.execute_many(
                "INSERT OR IGNORE INTO stage_cells(x, y, n_value, elevation) VALUES(?, ?, ?, ?);",
                batch_cells
            )
        if batch_schema:
            self.gutils.execute_many(
                "INSERT INTO stage_schema_md(domain_fid, domain_cell, x, y) VALUES(?, ?, ?, ?);",
                batch_schema
            )

        return int(cell_size)

    def get_subdomain_data(self, subdomain):
        """Function to get the subdomain data"""
        hdf5_file = f"{subdomain}/Input.hdf5"
        hdf5_coor = "/Input/Grid/COORDINATES"
        hdf5_elev = "/Input/Grid/ELEVATION"
        hdf5_mann = "/Input/Grid/MANNING"
        topo_dat = f"{subdomain}/TOPO.DAT"
        mannings_dat = f"{subdomain}/MANNINGS_N.DAT"
        cadpts_dat = f"{subdomain}/CADPTS.DAT"
        fplain_dat = f"{subdomain}/FPLAIN.DAT"

        data = None
        cell_size = None
        man = None
        coords = None
        elev = None

        hdf5_used = None
        f1_used = None
        f2_used = None

        # Check for hdf5 first
        if os.path.isfile(hdf5_file):
            hdf5_used = "Input.hdf5"

            data = []

            with h5py.File(hdf5_file, "r") as hdf:
                coor = hdf[hdf5_coor]
                elev = hdf[hdf5_elev]
                mann = hdf[hdf5_mann]

                n = coor.shape[0]

                elev_is_1d = elev.ndim == 1
                for i in range(n):
                    x, y = coor[i]
                    m = float(mann[i]) if mann.ndim == 1 else float(mann[i][0])
                    elev_values = [float(elev[i])] if elev_is_1d else list(map(float, elev[i]))
                    data.append([i + 1, m, float(x), float(y)] + elev_values)

            man = slice(1, 2)
            coords = slice(2, 4)
            elev = slice(4, None)

            # Calculate the cell_size for this Input.hdf5
            points = [row[coords] for row in data[:10]]

            cell_size = min(
                math.hypot(p1[0] - p2[0], p1[1] - p2[1])
                for p1, p2 in combinations(points, 2)
            )

        # Check for TOPO and MANNINGS_N
        elif os.path.isfile(topo_dat) and os.path.isfile(mannings_dat):

            # Read and parse TOPO & MANNINGS_N data efficiently
            data = self.parser.pandas_double_parser(mannings_dat, topo_dat)

            man = slice(1, 2)
            coords = slice(2, 4)
            elev = slice(4, None)

            f1_used = "TOPO.DAT"
            f2_used = "MANNINGS_N.DAT"

            # Calculate the cell_size for this topo.dat
            data_points = []
            with open(topo_dat, "r") as file:
                for _ in range(10):  # Read only the first 10 lines
                    line = file.readline()
                    parts = line.split()
                    if len(parts) == 3:  # Ensure the line contains three elements
                        x, y, _ = parts
                        data_points.append((float(x), float(y)))

            cell_size = min(
                math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) for p1, p2 in combinations(data_points, 2))

        # Import TOPO and MANNINGS from CADPTS and FPLAIN
        elif os.path.isfile(cadpts_dat) and os.path.isfile(fplain_dat):

            # Read and parse CADPTS data efficiently
            data = self.parser.double_parser(fplain_dat, cadpts_dat)

            man = slice(5, 6)
            elev = slice(6, 7)
            coords = slice(8, None)

            f1_used = "CADPTS.DAT"
            f2_used = "FPLAIN.DAT"

            # Calculate the cell_size for this cadpts
            data_points = []
            with open(cadpts_dat, "r") as file:
                for _ in range(10):  # Read only the first 10 lines
                    line = file.readline()
                    parts = line.split()
                    if len(parts) == 3:  # Ensure the line contains three elements
                        index, x, y = parts
                        data_points.append((float(x), float(y)))

            cell_size = min(
                math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) for p1, p2 in combinations(data_points, 2))

        # Import grid from CADPTS and set default mannings and topo
        elif os.path.isfile(cadpts_dat):

            # Read and parse CADPTS data efficiently
            data = self.parser.pandas_single_parser(cadpts_dat)

            coords = slice(1, None)

            f1_used = "CADPTS.DAT"
            f2_used = "default mannings and elevation"

            # Calculate the cell_size for this cadpts
            data_points = []
            with open(cadpts_dat, "r") as file:
                for _ in range(10):  # Read only the first 10 lines
                    line = file.readline()
                    parts = line.split()
                    if len(parts) == 3:  # Ensure the line contains three elements
                        index, x, y = parts
                        data_points.append((float(x), float(y)))

            cell_size = min(
                math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) for p1, p2 in combinations(data_points, 2))

        else:
            self.uc.bar_warn("Failed to import grid data. Please check the input files!")
            self.uc.log_info("Failed to import grid data. Please check the input files!")

        return data, cell_size, man, coords, elev, hdf5_used, f1_used, f2_used

    def import_components(self, total_subdomains, subdomains_paths):
        """Function to import multiple domains into one global domain"""

        import_calls = [
            "import_cont_toler", # data
            # "import_inflow", # data
            # "import_tailings",
            # "import_outrc",  Add back when the OUTRC process is completed
            # "import_outflow",
            "import_rain",
            "import_raincell",
            # "import_raincellraw",
            # "import_evapor",
            "import_infil",
            "import_chan",
            "import_xsec",
            "import_hystruc", # data
            # "import_hystruc_bridge_xs",
            # "import_street",
            "import_arf",
            # "import_mult",
            # "import_sed", # data
            "import_levee",
            # "import_fpxsec", # data
            # "import_breach",
            # "import_gutter",
            "import_fpfroude",
            "import_steep_slopen",
            "import_lid_volume",
            "import_shallowNSpatial",
            "import_swmminp",
            "import_swmmflo",
            "import_swmmflort",
            "import_swmmoutf",
            "import_swmmflodropbox",
            # "import_sdclogging", # data
            "import_tolspatial", # data
            # "import_wsurf",
            # "import_wstime",
        ]

        # empty = self.f2g.is_table_empty("grid")
        # # check if a grid exists in the grid table
        # if not empty:
        #     q = "There is a grid already defined in GeoPackage. Overwrite it?"
        #     if self.uc.question(q):
        #         pass
        #     else:
        #         self.uc.bar_info("Import cancelled!", dur=3)
        #         self.uc.log_info("Import cancelled!")
        #         return
        #
        # # Check if TOLER.DAT exist:
        # if not os.path.isfile(subdomain_path + r"\TOLER.DAT") or os.path.getsize(subdomain_path + r"\TOLER.DAT") == 0:
        #     self.uc.bar_error("ERROR 200322.0911: file TOLER.DAT is missing or empty!")
        #     self.uc.log_info("ERROR 200322.0911: file TOLER.DAT is missing or empty!")
        #     self.gutils.enable_geom_triggers()
        #     return

        progress_dialog = QProgressDialog(f"Importing components for Subdomain 1...", None, 0, total_subdomains + 1)
        progress_dialog.setWindowTitle("FLO-2D Multiple Domains Import")
        progress_dialog.setModal(True)
        progress_dialog.forceShow()
        progress_dialog.setValue(1)
        QApplication.processEvents()

        # import the subdomains components one by one
        for subdomain, subdomain_path in enumerate(subdomains_paths, start=1):
            if subdomain_path:

                progress_dialog.setLabelText(f"Importing components for Subdomain {subdomain + 1}...")
                progress_dialog.setValue(subdomain + 1)

                hdf5_file = f"{subdomain_path}/Input.hdf5"
                if os.path.isfile(hdf5_file):
                    self.f2g = Flo2dGeoPackage(self.con, self.iface, parsed_format=Flo2dGeoPackage.FORMAT_HDF5)
                    if not self.f2g.set_parser(hdf5_file):
                        return
                else:
                    self.f2g = Flo2dGeoPackage(self.con, self.iface)
                    fname = subdomain_path + "/CONT.DAT"
                    if not self.f2g.set_parser(fname):
                        return

                start_time = time.time()

                map_qry = """
                            SELECT DISTINCT(domain_cell), grid_fid
                            FROM schema_md_cells
                            WHERE domain_fid = ?
                			ORDER BY domain_cell
                        """
                mapped_rows = self.gutils.execute(map_qry, (subdomain,)).fetchall()
                grid_to_domain = {int(domain_grid): int(global_grid) for (domain_grid, global_grid) in mapped_rows}

                if self.f2g.parsed_format == Flo2dGeoPackage.FORMAT_DAT:
                    self.call_IO_methods_dat(import_calls, True, grid_to_domain)
                elif self.f2g.parsed_format == Flo2dGeoPackage.FORMAT_HDF5:
                    self.call_IO_methods_hdf5(import_calls, True, grid_to_domain)

                time_elapsed = self.calculate_time_elapsed(start_time)
                self.uc.log_info(f"Time Elapsed to import Subdomain {subdomain}: {time_elapsed}")
        progress_dialog.close()

    def call_IO_methods_hdf5(self, calls, debug, *args):

        self.f2g.parser.write_mode = "w"

        for call in calls:

            local_args = args

            if call == "import_swmminp":
                local_args = ("SWMM.INP", False)
            # add the subdomain path
            if call == "import_raincell":
                if self.f2g.parsed_format == Flo2dGeoPackage.FORMAT_HDF5:
                    dirname = os.path.dirname(self.f2g.parser.hdf5_filepath)
                    raincell_hdf5_path = os.path.join(dirname, "RAINCELL.HDF5")
                    local_args += (raincell_hdf5_path,)


            start_time = time.time()

            method = getattr(self.f2g, call)
            if method(*local_args):
                pass

            self.uc.log_info('{0:.3f} seconds => "{1}"'.format(time.time() - start_time, call))

    def call_IO_methods_dat(self, calls, debug, *args):

        for call in calls:
            local_args = args

            if call == "import_swmminp":
                local_args = ("SWMM.INP", False)

            start_time = time.time()

            method = getattr(self.f2g, call)
            if method(*local_args):
                pass

            self.uc.log_info('{0:.3f} seconds => "{1}"'.format(time.time() - start_time, call))


