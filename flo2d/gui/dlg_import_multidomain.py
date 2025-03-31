import math
import os.path
import time
from itertools import combinations

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QFileDialog, QApplication, QProgressDialog
from qgis.PyQt.QtCore import NULL

from .dlg_multidomain_connectivity import MultipleDomainsConnectivityDialog
from .multiple_domains_editor_widget import MultipleDomainsEditorWidget
from .ui_utils import load_ui
from ..flo2d_ie.flo2d_parser import ParseDAT
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
        self.cancel_btn.clicked.connect(self.close_dlg)
        self.add_subdomain_btn.clicked.connect(self.add_subdomain)
        self.remove_subdomain_btn.clicked.connect(self.remove_subdomain)

        # Manage domain connectivity
        self.connect_btn.clicked.connect(self.open_multiple_domains_connectivity_dialog)

        # Trigger global domain import
        self.ok_btn.clicked.connect(self.import_global_domain)

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
        multdomain_dat = any(f.startswith("MULTIDOMAIN.DAT") for f in files)
        cadpts_ds = any(f.startswith("CADPTS_DS") for f in files)

        subdomain_name = os.path.basename(domain_dir)

        # Insert into mult_domains_methods
        qry = f"""INSERT INTO mult_domains_methods (subdomain_name, subdomain_path) 
                VALUES ('{subdomain_name}', '{domain_dir}');"""
        self.gutils.execute(qry)

        # Project has MULTIDOMAIN.DAT
        if multdomain_dat:
            # Add a line to the method
            qry_method = f"""INSERT INTO mult_domains_con (subdomain_name) VALUES ('{subdomain_name}');"""
            self.gutils.execute(qry_method)

            # Get the recent added fid
            qry_method_fid = f"""SELECT fid FROM mult_domains_con WHERE subdomain_name = '{subdomain_name}';"""
            method_fid = self.gutils.execute(qry_method_fid).fetchone()[0]

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

            # Add a line to the method
            qry_method = f"""INSERT INTO mult_domains_con (subdomain_name) VALUES ('{subdomain_name}');"""
            self.gutils.execute(qry_method)

            # Get the recent added fid
            qry_method_fid = f"""SELECT fid FROM mult_domains_con WHERE subdomain_name = '{subdomain_name}';"""
            method_fid = self.gutils.execute(qry_method_fid).fetchone()[0]

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
            # Add a line to the method
            qry_method = f"""INSERT INTO mult_domains_con (subdomain_name) VALUES ('{subdomain_name}');"""
            self.gutils.execute(qry_method)

            # Get the recent added fid
            qry_method_fid = f"""SELECT fid FROM mult_domains_con WHERE subdomain_name = '{subdomain_name}';"""
            method_fid = self.gutils.execute(qry_method_fid).fetchone()[0]

            # Insert into mult_domains_methods
            qry = f"""
                       UPDATE mult_domains_methods 
                       SET fid_method = {method_fid}
                       WHERE subdomain_name = '{subdomain_name}'; 
                   """
            self.gutils.execute(qry)

        self.uc.log_info(f"Subdomain {domain_n} data saved to geopackage.")
        self.uc.bar_info(f"Subdomain {domain_n} data saved to geopackage.")

    def close_dlg(self):
        """
        Closes the dialog.
        """
        self.close()

    def import_global_domain(self):
        """
        Imports the global domain data. Handles the parsing and importing
        of global domain details from files into the geopackage.
        """
        subdomains_paths = self.fetch_subdomain_paths()
        total_subdomains = sum(1 for path in subdomains_paths if path)

        progress_dialog = QProgressDialog(f"Importing Subdomain 1...", None, 1, total_subdomains + 1)
        progress_dialog.setWindowTitle("FLO-2D Import")
        progress_dialog.setModal(True)
        progress_dialog.forceShow()
        progress_dialog.setValue(1)

        md_editor = MultipleDomainsEditorWidget(self.iface, self.lyrs)
        common_coords = md_editor.find_common_coordinates(subdomains_paths)

        for current_progress, subdomain_path in enumerate(subdomains_paths, start=1):
            if subdomain_path:
                start_time = time.time()
                self.import_subdomains_mannings_n_topo_dat(subdomain_path, common_coords, current_progress)
                time_elapsed = self.calculate_time_elapsed(start_time)
                self.uc.log_info(f"Time Elapsed to import Subdomain {current_progress}: {time_elapsed}")

                progress_dialog.setLabelText(f"Importing Subdomain {current_progress + 1}...")
                progress_dialog.setValue(current_progress + 1)

        progress_dialog.close()
        self.finalize_import()

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
        grid_layer = self.lyrs.data["grid"]["qlyr"]
        grid_layer.triggerRepaint()
        self.lyrs.zoom_to_all()
        self.uc.log_info("Import of Multiple Domains finished successfully")
        self.uc.bar_info("Import of Multiple Domains finished successfully")
        self.close_dlg()

    def import_subdomains_mannings_n_topo_dat(self, subdomain, common_coords, subdomain_n):
        """
        Imports subdomain-specific Manning's N and TOPO.DAT data.

        This function is responsible for parsing Manning's N roughness coefficient
        and TOPO.DAT (geometry, elevation) data for respective subdomains, validating
        them, and saving/updating them in the project database or corresponding tables.
        """

        QApplication.setOverrideCursor(Qt.WaitCursor)

        # connect_cells = [" ".join(map(str, row)) for row in self.gutils.execute(
        #     f"SELECT ST_X(geom) as x, ST_Y(geom) as y FROM schema_md_cells;").fetchall()]

        cell_size = None

        # Step 1: Clear tables if this is the first subdomain
        if subdomain_n == 1:
            self.gutils.clear_tables("grid")
            fid = 1
        else:
            fid = self.gutils.execute("SELECT MAX(fid) FROM grid;").fetchone()[0] or 0
            fid += 1  # Ensures unique fid values

        sql_grid = []
        sql_schema = []

        topo_dat = f"{subdomain}/TOPO.DAT"
        mannings_dat = f"{subdomain}/MANNINGS_N.DAT"
        # cadpts_dat = f"{subdomain}/CADPTS.DAT"
        # fplain_dat = f"{subdomain}/FPLAIN.DAT"

        # Check for TOPO and MANNINGS_N first # TODO CHECK THIS
        if os.path.isfile(topo_dat) and os.path.isfile(mannings_dat):

            # Read and parse TOPO & MANNINGS_N data efficiently
            data = self.parser.pandas_double_parser(mannings_dat, topo_dat)

            man = slice(1, 2)
            coords = slice(2, 4)
            elev = slice(4, None)

            # Batch processing for better performance
            batch_size = self.chunksize  # Set batch size from existing chunksize variable

            # Calculate the cell_size for this topo.dat
            if not cell_size:
                data_points = []
                with open(topo_dat, "r") as file:
                    for _ in range(10):  # Read only the first 10 lines
                        line = file.readline()
                        parts = line.split()
                        if len(parts) == 3:  # Ensure the line contains three elements
                            x, y, _ = parts
                            data_points.append((float(x), float(y)))

                cell_size = min(math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2) for p1, p2 in combinations(data_points, 2))

            for i, row in enumerate(data, start=1):

                geom = " ".join(list(map(str, row[coords])))

                # Check if the geometry is in the common coords between all subdomains
                if geom in common_coords:

                    # Check if it is not constructed on the GRID table
                    g = self.gutils.build_square(geom, cell_size)
                    check_grid_qry = f"""SELECT fid FROM grid WHERE geom = ?;"""
                    check_grid = self.gutils.execute(check_grid_qry, (g,)).fetchall()

                    # It does not exist
                    if not check_grid:
                        sql_grid.append((fid, *row[man], *row[elev], g))

                        # Check if it is not constructed on the SCHEMA_MD_CELLS table
                        check_con_qry = f"""SELECT fid, domain_cell FROM schema_md_cells WHERE geom = ST_GeomFromText('POINT({geom})');"""
                        check_con = self.gutils.execute(check_con_qry).fetchall()

                        # It exists - Update
                        if check_con:
                            self.gutils.execute(f"""UPDATE
                                                        schema_md_cells
                                                    SET
                                                        grid_fid = {fid},
                                                        domain_cell = {i}
                                                    WHERE
                                                        geom = ST_GeomFromText('POINT({geom})')
                                                    AND
                                                        domain_fid = {subdomain_n};""")
                            sql_schema.append((fid, subdomain_n, i))
                        # It does not exist - Create
                        else:
                            sql_schema.append((fid, subdomain_n, i))

                        fid += 1

                    # It exists
                    else:

                        # Check if it is not constructed on the SCHEMA_MD_CELLS table
                        check_con_qry = f"""SELECT fid, domain_cell FROM schema_md_cells WHERE geom = ST_GeomFromText('POINT({geom})');"""
                        check_con = self.gutils.execute(check_con_qry).fetchall()

                        # It exists - Update
                        if check_con:
                            self.gutils.execute(f"""UPDATE
                                                       schema_md_cells
                                                   SET
                                                       grid_fid = {check_grid[0][0]},
                                                       domain_cell = {i}
                                                   WHERE
                                                       geom = ST_GeomFromText('POINT({geom})')
                                                   AND
                                                       domain_fid = {subdomain_n};""")
                            sql_schema.append((check_grid[0][0], subdomain_n, i))
                        else:
                            sql_schema.append((check_grid[0][0], subdomain_n, i))

                # If the grid is not on the grid table, construct the grid and add to schema_md_cells
                else:
                    g = self.gutils.build_square(geom, cell_size)
                    sql_grid.append((fid, *row[man], *row[elev], g))

                    sql_schema.append((fid, subdomain_n, i))

                    fid += 1

                # Execute in batches for better efficiency
                if len(sql_grid) >= batch_size:
                    self.gutils.execute_many(
                        "INSERT INTO grid (fid, n_value, elevation, geom) VALUES (?, ?, ?, ?);",
                        sql_grid
                    )
                    sql_grid.clear()

                if len(sql_schema) >= batch_size:
                    self.gutils.execute_many(
                        f"""
                           INSERT INTO schema_md_cells 
                           (grid_fid, domain_fid, domain_cell) 
                           VALUES (?, ?, ?);
                        """,
                        sql_schema
                    )
                    sql_schema.clear()

            # Insert remaining data if any
            if sql_grid:
                self.gutils.execute_many(
                    "INSERT INTO grid (fid, n_value, elevation, geom) VALUES (?, ?, ?, ?);",
                    sql_grid
                )

            if sql_schema:
                self.gutils.execute_many(
                    f"""
                       INSERT INTO schema_md_cells 
                       (grid_fid, domain_fid, domain_cell) 
                       VALUES (?, ?, ?);
                    """,
                    sql_schema
                )

            self.uc.bar_info(f"Subdomain {subdomain_n} grid created from TOPO.DAT and MANNINGS_N.DAT!")
            self.uc.log_info(f"Subdomain {subdomain_n} grid created from TOPO.DAT and MANNINGS_N.DAT!")

        # # Import TOPO and MANNINGS from CADPTS and FPLAIN
        # elif os.path.isfile(cadpts_dat) and os.path.isfile(fplain_dat):
        #
        #     # Read and parse CADPTS data efficiently
        #     data = self.parser.double_parser(fplain_dat, cadpts_dat)
        #
        #     domain_cell_fid = 1
        #
        #     man = slice(5, 6)
        #     elev = slice(6, 7)
        #     coords = slice(8, None)
        #
        #     # Batch processing for better performance
        #     batch_size = self.chunksize  # Set batch size from existing chunksize variable
        #
        #     # Calculate the cell_size for this cadpts
        #     if not cell_size:
        #         data_points = []
        #         with open(cadpts_dat, "r") as file:
        #             for _ in range(10):  # Read only the first 10 lines
        #                 line = file.readline()
        #                 parts = line.split()
        #                 if len(parts) == 3:  # Ensure the line contains three elements
        #                     index, x, y = parts
        #                     data_points.append((float(x), float(y)))
        #
        #         cell_size = min(math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2) for p1, p2 in combinations(data_points, 2))
        #
        #     for i, row in enumerate(data, start=1):
        #
        #         if subdomain_n != 1 and domain_cell_fid in connect_cells:
        #             connectivity_data = self.gutils.execute(
        #                 "SELECT fid, up_domain_fid, up_domain_cell FROM schema_md_connect_cells WHERE down_domain_fid = ? AND down_domain_cell = ?;",
        #                 (subdomain_n, domain_cell_fid)
        #             ).fetchone()
        #
        #             # Check if we found a match
        #             if connectivity_data:
        #                 # Update the grid table
        #                 self.gutils.execute(
        #                     "UPDATE grid SET connectivity_fid = ? WHERE domain_fid = ? AND domain_cell = ?;",
        #                     (connectivity_data[0], connectivity_data[1], connectivity_data[2])
        #                 )
        #                 domain_cell_fid += 1
        #                 continue
        #
        #         geom = " ".join(list(map(str, row[coords])))
        #         g = self.gutils.build_square(geom, cell_size)  # Avoid redundant processing
        #
        #         sql_grid.append((fid, *row[man], *row[elev], subdomain_n, domain_cell_fid, g))
        #
        #         fid += 1
        #         domain_cell_fid += 1
        #
        #         # Execute in batches for better efficiency
        #         if len(sql_grid) >= batch_size:
        #             self.gutils.execute_many(
        #                 "INSERT INTO grid (fid, n_value, elevation, domain_fid, domain_cell, geom) VALUES (?, ?, ?, ?, ?, ?);",
        #                 sql_grid
        #             )
        #             sql_grid.clear()
        #
        #     # Insert remaining data if any
        #     if sql_grid:
        #         self.gutils.execute_many(
        #             "INSERT INTO grid (fid, n_value, elevation, domain_fid, domain_cell, geom) VALUES (?, ?, ?, ?, ?, ?);",
        #             sql_grid
        #         )
        #
        #     self.uc.bar_info(f"Subdomain {subdomain_n} grid created from CADPTS.DAT and FPLAIN.DAT!")
        #     self.uc.log_info(f"Subdomain {subdomain_n} grid created from CADPTS.DAT and FPLAIN.DAT!")
        #
        # # Import grid from CADPTS and set default mannings and topo
        # elif os.path.isfile(cadpts_dat):
        #
        #     mann = self.gutils.get_cont_par("MANNING")
        #     elev = -9999
        #
        #     # Calculate the cell_size for this cadpts
        #     if not cell_size:
        #         data_points = []
        #         with open(cadpts_dat, "r") as file:
        #             for _ in range(10):  # Read only the first 10 lines
        #                 line = file.readline()
        #                 parts = line.split()
        #                 if len(parts) == 3:  # Ensure the line contains three elements
        #                     index, x, y = parts
        #                     data_points.append((float(x), float(y)))
        #
        #         cell_size = min(math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2) for p1, p2 in combinations(data_points, 2))
        #
        #     # Read and parse CADPTS data efficiently
        #     data = self.parser.pandas_single_parser(cadpts_dat)
        #
        #     domain_cell_fid = 1
        #
        #     coords = slice(1, None)
        #
        #     # Batch processing for better performance
        #     batch_size = self.chunksize  # Set batch size from existing chunksize variable
        #
        #     for i, row in enumerate(data, start=1):
        #
        #         if subdomain_n != 1 and domain_cell_fid in connect_cells:
        #             connectivity_data = self.gutils.execute(
        #                 "SELECT fid, up_domain_fid, up_domain_cell FROM schema_md_connect_cells WHERE down_domain_fid = ? AND down_domain_cell = ?;",
        #                 (subdomain_n, domain_cell_fid)
        #             ).fetchone()
        #
        #             # Check if we found a match
        #             if connectivity_data:
        #                 # Update the grid table
        #                 self.gutils.execute(
        #                     "UPDATE grid SET connectivity_fid = ? WHERE domain_fid = ? AND domain_cell = ?;",
        #                     (connectivity_data[0], connectivity_data[1], connectivity_data[2])
        #                 )
        #                 domain_cell_fid += 1
        #                 continue
        #
        #         geom = " ".join(list(map(str, row[coords])))
        #         g = self.gutils.build_square(geom, cell_size)  # Avoid redundant processing
        #
        #         sql_grid.append((fid, mann, elev, subdomain_n, domain_cell_fid, g))
        #
        #         fid += 1
        #         domain_cell_fid += 1
        #
        #         # Execute in batches for better efficiency
        #         if len(sql_grid) >= batch_size:
        #             self.gutils.execute_many(
        #                 "INSERT INTO grid (fid, n_value, elevation, domain_fid, domain_cell, geom) VALUES (?, ?, ?, ?, ?, ?);",
        #                 sql_grid
        #             )
        #             sql_grid.clear()
        #
        #     # Insert remaining data if any
        #     if sql_grid:
        #         self.gutils.execute_many(
        #             "INSERT INTO grid (fid, n_value, elevation, domain_fid, domain_cell, geom) VALUES (?, ?, ?, ?, ?, ?);",
        #             sql_grid
        #         )
        #
        #     self.uc.bar_info(f"Subdomain {subdomain_n} grid created from CADPTS.DAT and default topo & mannings value!")
        #     self.uc.log_info(f"Subdomain {subdomain_n} grid created from CADPTS.DAT and default topo & mannings value!")

        else:
            self.uc.bar_error("Failed to import topo and manning's data. Please check the input files!")
            self.uc.log_info("Failed to import topo and manning's data. Please check the input files!")

        QApplication.restoreOverrideCursor()


