import math
import os.path
import time
from itertools import combinations

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QFileDialog, QApplication, QProgressDialog
from qgis.PyQt.QtCore import NULL

from .dlg_multidomain_connectivity import MultipleDomainsConnectivityDialog
from .ui_utils import load_ui
from ..flo2d_ie.flo2d_parser import ParseDAT
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui("import_multiple_domains")


class ImportMultipleDomainsDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = GeoPackageUtils(con, iface)

        self.parser = ParseDAT()
        self.chunksize = float("inf")

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

        self.sub1_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub1_le, 1))
        self.sub2_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub2_le, 2))
        self.sub3_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub3_le, 3))
        self.sub4_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub4_le, 4))
        self.sub5_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub5_le, 5))
        self.sub6_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub6_le, 6))
        self.sub7_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub7_le, 7))
        self.sub8_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub8_le, 8))
        self.sub9_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub9_le, 9))
        self.sub10_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub10_le, 10))
        self.sub11_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub11_le, 11))
        self.sub12_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub12_le, 12))
        self.sub13_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub13_le, 13))
        self.sub14_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub14_le, 14))
        self.sub15_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub15_le, 15))

        self.cancel_btn.clicked.connect(self.close_dlg)

        self.add_subdomain_btn.clicked.connect(self.add_subdomain)
        self.remove_subdomain_btn.clicked.connect(self.remove_subdomain)

        self.connect_btn.clicked.connect(self.open_multiple_domains_connectivity_dialog)

        self.ok_btn.clicked.connect(self.import_global_domain)

        self.populate_subdomains()

    def add_subdomain(self):
        """
        Function to set one more subdomain visible
        """
        sub_paths = self.gutils.execute("SELECT fid, subdomain_path FROM mult_domains_methods;").fetchall()
        if sub_paths:
            self.hide_subdomains(len(sub_paths) + 1)
        else:
            self.hide_subdomains(1)

    def remove_subdomain(self):
        """
        Function to remove one subdomain and clear the tables
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
        Function to open the multiple domains connectivity and fill out the data
        """
        dlg = MultipleDomainsConnectivityDialog(self.iface, self.con, self.lyrs)
        ok = dlg.exec_()
        if not ok:
            return
        else:
            pass

    def populate_subdomains(self):
        """
        Function to populate the subdomains on the line edits
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
        Function to select the subdomain folder
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
                for line in f:
                    data = line.strip().split()

                    if not data:
                        continue

                    if data[0] == "N":
                        # New subdomain identifier
                        n_subdomains.append(int(data[1]))

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

        self.uc.log_info(f"Subdomain {domain_n} data saved to geopackage.")
        self.uc.bar_info(f"Subdomain {domain_n} data saved to geopackage.")

    def close_dlg(self):
        """
        Function to close the dialog
        """
        self.close()

    def import_global_domain(self):
        """
        Function to import the global domain
        """

        sub1_path = self.sub1_le.text()
        sub2_path = self.sub2_le.text()
        sub3_path = self.sub3_le.text()
        sub4_path = self.sub4_le.text()
        sub5_path = self.sub5_le.text()
        sub6_path = self.sub6_le.text()
        sub7_path = self.sub7_le.text()
        sub8_path = self.sub8_le.text()
        sub9_path = self.sub9_le.text()
        sub10_path = self.sub10_le.text()
        sub11_path = self.sub11_le.text()
        sub12_path = self.sub12_le.text()
        sub13_path = self.sub13_le.text()
        sub14_path = self.sub14_le.text()
        sub15_path = self.sub15_le.text()

        subdomains_paths = [
            sub1_path,
            sub2_path,
            sub3_path,
            sub4_path,
            sub5_path,
            sub6_path,
            sub7_path,
            sub8_path,
            sub9_path,
            sub10_path,
            sub11_path,
            sub12_path,
            sub13_path,
            sub14_path,
            sub15_path
        ]

        n_projects = sum(1 for item in subdomains_paths if item != "")

        i = 1

        pd = QProgressDialog(f"Importing Subdomain {i}...", None, i, n_projects + 1)
        pd.setWindowTitle("FLO-2D Import")
        pd.setModal(True)
        pd.forceShow()
        pd.setValue(i)

        # First import the whole grid and subdomains
        for subdomain in subdomains_paths:
            if subdomain:
                start_time = time.time()

                # Import mannings and topo and add to grid
                self.import_subdomains_mannings_n_topo_dat(subdomain, i)

                end_time = time.time()
                hours, rem = divmod(end_time - start_time, 3600)
                minutes, seconds = divmod(rem, 60)
                time_passed = "{:0>2}:{:0>2}:{:0>2}".format(int(hours), int(minutes), int(seconds))
                self.uc.log_info(f"Time Elapsed to import Subdomain {i}: {time_passed}")
                i += 1
                pd.setLabelText(f"Importing Subdomain {i}...")
                pd.setValue(i)

        pd.close()

        grid_lyr = self.lyrs.data["grid"]["qlyr"]
        grid_lyr.triggerRepaint()
        self.lyrs.zoom_to_all()

        self.uc.log_info("Import of Multiple Domains finished successfully")
        self.uc.bar_info("Import of Multiple Domains finished successfully")
        self.close_dlg()

    def import_subdomains_mannings_n_topo_dat(self, subdomain, subdomain_n):
        """
        Function to import multiple subdomains into one project
        """

        QApplication.setOverrideCursor(Qt.WaitCursor)

        self.gutils.execute("CREATE INDEX IF NOT EXISTS idx_grid_domain_fid_cell ON grid(domain_fid, domain_cell);")
        connect_cells = []
        cell_size = None

        # Step 1: Clear tables if this is the first subdomain
        if subdomain_n == 1:
            self.gutils.clear_tables("grid")
            fid = 1
        else:
            fid = self.gutils.execute("SELECT MAX(fid) FROM grid;").fetchone()[0] or 0
            fid += 1  # Ensures unique fid values
            connect_cells = [row[0] for row in self.gutils.execute(
                f"SELECT down_domain_cell FROM schema_md_connect_cells WHERE down_domain_fid = {subdomain_n};").fetchall()]

        sql_grid = []

        topo_dat = f"{subdomain}/TOPO.DAT"
        mannings_dat = f"{subdomain}/MANNINGS_N.DAT"
        cadpts_dat = f"{subdomain}/CADPTS.DAT"
        fplain_dat = f"{subdomain}/FPLAIN.DAT"

        # Check for TOPO and MANNINGS_N first # TODO CHECK THIS
        if os.path.isfile(topo_dat) and os.path.isfile(mannings_dat):

            # Read and parse TOPO & MANNINGS_N data efficiently
            data = self.parser.pandas_double_parser(mannings_dat, topo_dat)

            domain_cell_fid = 1

            man = slice(1, 2)
            coords = slice(2, 4)
            elev = slice(4, None)

            # Batch processing for better performance
            batch_size = self.chunksize  # Set batch size from existing chunksize variable

            # Calculate the cell_size for this cadpts
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

                if subdomain_n != 1 and domain_cell_fid in connect_cells:
                    connectivity_data = self.gutils.execute(
                        "SELECT fid, up_domain_fid, up_domain_cell FROM schema_md_connect_cells WHERE down_domain_fid = ? AND down_domain_cell = ?;",
                        (subdomain_n, domain_cell_fid)
                    ).fetchone()

                    # Check if we found a match
                    if connectivity_data:
                        # Update the grid table
                        self.gutils.execute(
                            "UPDATE grid SET connectivity_fid = ? WHERE domain_fid = ? AND domain_cell = ?;",
                            (connectivity_data[0], connectivity_data[1], connectivity_data[2])
                        )
                        domain_cell_fid += 1
                        continue

                geom = " ".join(list(map(str, row[coords])))
                g = self.gutils.build_square(geom, cell_size)  # Avoid redundant processing

                sql_grid.append((fid, *row[man], *row[elev], subdomain_n, domain_cell_fid, g))

                fid += 1
                domain_cell_fid += 1

                # Execute in batches for better efficiency
                if len(sql_grid) >= batch_size:
                    self.gutils.execute_many(
                        "INSERT INTO grid (fid, n_value, elevation, domain_fid, domain_cell, geom) VALUES (?, ?, ?, ?, ?, ?);",
                        sql_grid
                    )
                    sql_grid.clear()

            # Insert remaining data if any
            if sql_grid:
                self.gutils.execute_many(
                    "INSERT INTO grid (fid, n_value, elevation, domain_fid, domain_cell, geom) VALUES (?, ?, ?, ?, ?, ?);",
                    sql_grid
                )

            self.uc.bar_info(f"Subdomain {subdomain_n} grid created from TOPO.DAT and MANNINGS_N.DAT!")
            self.uc.log_info(f"Subdomain {subdomain_n} grid created from TOPO.DAT and MANNINGS_N.DAT!")

        # Import TOPO and MANNINGS from CADPTS and FPLAIN # TODO TEST THIS APPROACH
        elif os.path.isfile(cadpts_dat) and os.path.isfile(fplain_dat):

            # Read and parse CADPTS data efficiently
            data = self.parser.double_parser(fplain_dat, cadpts_dat)

            domain_cell_fid = 1

            man = slice(5, 6)
            elev = slice(6, 7)
            coords = slice(8, None)

            # Batch processing for better performance
            batch_size = self.chunksize  # Set batch size from existing chunksize variable

            # Calculate the cell_size for this cadpts
            if not cell_size:
                data_points = []
                with open(cadpts_dat, "r") as file:
                    for _ in range(10):  # Read only the first 10 lines
                        line = file.readline()
                        parts = line.split()
                        if len(parts) == 3:  # Ensure the line contains three elements
                            index, x, y = parts
                            data_points.append((float(x), float(y)))

                cell_size = min(math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2) for p1, p2 in combinations(data_points, 2))

            for i, row in enumerate(data, start=1):

                if subdomain_n != 1 and domain_cell_fid in connect_cells:
                    connectivity_data = self.gutils.execute(
                        "SELECT fid, up_domain_fid, up_domain_cell FROM schema_md_connect_cells WHERE down_domain_fid = ? AND down_domain_cell = ?;",
                        (subdomain_n, domain_cell_fid)
                    ).fetchone()

                    # Check if we found a match
                    if connectivity_data:
                        # Update the grid table
                        self.gutils.execute(
                            "UPDATE grid SET connectivity_fid = ? WHERE domain_fid = ? AND domain_cell = ?;",
                            (connectivity_data[0], connectivity_data[1], connectivity_data[2])
                        )
                        domain_cell_fid += 1
                        continue

                geom = " ".join(list(map(str, row[coords])))
                g = self.gutils.build_square(geom, cell_size)  # Avoid redundant processing

                sql_grid.append((fid, *row[man], *row[elev], subdomain_n, domain_cell_fid, g))

                fid += 1
                domain_cell_fid += 1

                # Execute in batches for better efficiency
                if len(sql_grid) >= batch_size:
                    self.gutils.execute_many(
                        "INSERT INTO grid (fid, n_value, elevation, domain_fid, domain_cell, geom) VALUES (?, ?, ?, ?, ?, ?);",
                        sql_grid
                    )
                    sql_grid.clear()

            # Insert remaining data if any
            if sql_grid:
                self.gutils.execute_many(
                    "INSERT INTO grid (fid, n_value, elevation, domain_fid, domain_cell, geom) VALUES (?, ?, ?, ?, ?, ?);",
                    sql_grid
                )

            self.uc.bar_info(f"Subdomain {subdomain_n} grid created from CADPTS.DAT and FPLAIN.DAT!")
            self.uc.log_info(f"Subdomain {subdomain_n} grid created from CADPTS.DAT and FPLAIN.DAT!")

        # Import grid from CADPTS and set default mannings and topo
        elif os.path.isfile(cadpts_dat):

            mann = self.gutils.get_cont_par("MANNING")
            elev = -9999

            # Calculate the cell_size for this cadpts
            if not cell_size:
                data_points = []
                with open(cadpts_dat, "r") as file:
                    for _ in range(10):  # Read only the first 10 lines
                        line = file.readline()
                        parts = line.split()
                        if len(parts) == 3:  # Ensure the line contains three elements
                            index, x, y = parts
                            data_points.append((float(x), float(y)))

                cell_size = min(math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2) for p1, p2 in combinations(data_points, 2))

            # Read and parse CADPTS data efficiently
            data = self.parser.pandas_single_parser(cadpts_dat)

            domain_cell_fid = 1

            coords = slice(1, None)

            # Batch processing for better performance
            batch_size = self.chunksize  # Set batch size from existing chunksize variable

            for i, row in enumerate(data, start=1):

                if subdomain_n != 1 and domain_cell_fid in connect_cells:
                    connectivity_data = self.gutils.execute(
                        "SELECT fid, up_domain_fid, up_domain_cell FROM schema_md_connect_cells WHERE down_domain_fid = ? AND down_domain_cell = ?;",
                        (subdomain_n, domain_cell_fid)
                    ).fetchone()

                    # Check if we found a match
                    if connectivity_data:
                        # Update the grid table
                        self.gutils.execute(
                            "UPDATE grid SET connectivity_fid = ? WHERE domain_fid = ? AND domain_cell = ?;",
                            (connectivity_data[0], connectivity_data[1], connectivity_data[2])
                        )
                        domain_cell_fid += 1
                        continue

                geom = " ".join(list(map(str, row[coords])))
                g = self.gutils.build_square(geom, cell_size)  # Avoid redundant processing

                sql_grid.append((fid, mann, elev, subdomain_n, domain_cell_fid, g))

                fid += 1
                domain_cell_fid += 1

                # Execute in batches for better efficiency
                if len(sql_grid) >= batch_size:
                    self.gutils.execute_many(
                        "INSERT INTO grid (fid, n_value, elevation, domain_fid, domain_cell, geom) VALUES (?, ?, ?, ?, ?, ?);",
                        sql_grid
                    )
                    sql_grid.clear()

            # Insert remaining data if any
            if sql_grid:
                self.gutils.execute_many(
                    "INSERT INTO grid (fid, n_value, elevation, domain_fid, domain_cell, geom) VALUES (?, ?, ?, ?, ?, ?);",
                    sql_grid
                )

            self.uc.bar_info(f"Subdomain {subdomain_n} grid created from CADPTS.DAT and default topo & mannings value!")
            self.uc.log_info(f"Subdomain {subdomain_n} grid created from CADPTS.DAT and default topo & mannings value!")

        else:
            self.uc.bar_error("Failed to import topo and manning's data. Please check the input files!")
            self.uc.log_info("Failed to import topo and manning's data. Please check the input files!")


        QApplication.restoreOverrideCursor()

    # def extract_ups_downs_cells(self, subdomains_paths):
    #     """
    #     Function to extract the boundary cells between two subdomains
    #     """
    #     dissolved_domains = []
    #     buffered_domains = []
    #     intersected_cells_layers = []
    #     i = 1
    #
    #     n_subdomains = len([x for x in subdomains_paths if x != ""])
    #
    #     progDialog = QProgressDialog(f"Getting the intersection between the domains. Please wait...", None, 0, n_subdomains)
    #     progDialog.setModal(True)
    #     progDialog.setValue(0)
    #     progDialog.show()
    #     QApplication.processEvents()
    #
    #     for subdomain in subdomains_paths:
    #
    #         if subdomain != "":
    #             # Create a virtual layer that filters only domain=1
    #             filtered_layer = processing.run("native:extractbyexpression", {
    #                 'INPUT': schema_md_cells_lyr,
    #                 'EXPRESSION': f'"domain_fid"={i}',
    #                 'OUTPUT': 'TEMPORARY_OUTPUT'
    #             })['OUTPUT']
    #
    #             # Run dissolve on the filtered layer
    #             dissolved_layer = processing.run("native:dissolve", {
    #                 'INPUT': filtered_layer,
    #                 'FIELD': [],
    #                 'SEPARATE_DISJOINT': False,
    #                 'OUTPUT': 'TEMPORARY_OUTPUT'
    #             })['OUTPUT']
    #
    #             dissolved_domains.append(dissolved_layer)
    #
    #             buffered_layer = processing.run("native:buffer", {
    #                 'INPUT': dissolved_layer,
    #                 'DISTANCE': (self.cell_size / 10), 'SEGMENTS': 5, 'END_CAP_STYLE': 0, 'JOIN_STYLE': 0, 'MITER_LIMIT': 2,
    #                 'DISSOLVE': False, 'SEPARATE_DISJOINT': False, 'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']
    #
    #             buffered_domains.append(buffered_layer)
    #
    #             progDialog.setValue(i)
    #             i += 1
    #
    #     progDialog.close()
    #
    #     progDialog = QProgressDialog(f"Extracting the connectivity cells. Please wait...", None, 0, len(buffered_domains))
    #     progDialog.setModal(True)
    #     progDialog.setValue(0)
    #     progDialog.show()
    #     QApplication.processEvents()
    #
    #     intersect_results = []
    #     for i in range(len(buffered_domains)):
    #         for j in range(i + 1, len(buffered_domains)):  # Avoid redundant comparisons
    #             layer1 = buffered_domains[i]
    #             layer2 = buffered_domains[j]
    #
    #             # Check if the layers intersect
    #             intersecting_features = processing.run("native:extractbylocation", {
    #                 'INPUT': layer1,
    #                 'PREDICATE': [0],  # "intersects"
    #                 'INTERSECT': layer2,
    #                 'OUTPUT': 'TEMPORARY_OUTPUT'
    #             })['OUTPUT']
    #
    #             if intersecting_features:  # Proceed only if an intersection is found
    #                 # Compute the intersection
    #                 intersection_layer = processing.run("native:intersection", {
    #                     'INPUT': layer1,
    #                     'OVERLAY': layer2,
    #                     'INPUT_FIELDS': [],
    #                     'OVERLAY_FIELDS': [],
    #                     'OUTPUT': 'TEMPORARY_OUTPUT'
    #                 })['OUTPUT']
    #
    #                 if intersection_layer:
    #
    #                     # QgsProject.instance().addMapLayer(intersection_layer)
    #                     intersect_results.append(intersection_layer)
    #
    #                     intersecting_grid_polygons = processing.run("native:extractbylocation", {
    #                         'INPUT': schema_md_cells_lyr,
    #                         'PREDICATE': [0],  # "intersects"
    #                         'INTERSECT': intersection_layer,
    #                         'OUTPUT': 'TEMPORARY_OUTPUT'
    #                     })['OUTPUT']
    #
    #                     # QgsProject.instance().addMapLayer(intersecting_grid_polygons)
    #                     if intersecting_grid_polygons.featureCount() > 0:
    #                         intersected_cells_layers.append(intersecting_grid_polygons)
    #
    #         progDialog.setValue(i)
    #     progDialog.close()
    #
    #     return intersected_cells_layers

    # def import_connectivity_cells(self):
    #     """
    #     Function to import the connectivity cells based on the UPS-DOWS-CELLS
    #     """
    #
    #     self.gutils.clear_tables("schema_md_connect_cells")
    #
    #     subdomain_connectivities = self.gutils.execute("""
    #                    SELECT
    #                        md.fid,
    #                        md.subdomain_path,
    #                        im.fid_subdomain_1, im.mult_domains_1, im.ds_file_1,
    #                        im.fid_subdomain_2, im.mult_domains_2, im.ds_file_2,
    #                        im.fid_subdomain_3, im.mult_domains_3, im.ds_file_3,
    #                        im.fid_subdomain_4, im.mult_domains_4, im.ds_file_4,
    #                        im.fid_subdomain_5, im.mult_domains_5, im.ds_file_5,
    #                        im.fid_subdomain_6, im.mult_domains_6, im.ds_file_6,
    #                        im.fid_subdomain_7, im.mult_domains_7, im.ds_file_7,
    #                        im.fid_subdomain_8, im.mult_domains_8, im.ds_file_8,
    #                        im.fid_subdomain_9, im.mult_domains_9, im.ds_file_9
    #                    FROM
    #                        mult_domains_methods AS md
    #                    JOIN mult_domains_con AS im ON md.fid_method = im.fid;
    #                                """).fetchall()
    #     if subdomain_connectivities:
    #         bulk_insert_data = []  # Collect all insert statements in a list
    #
    #         j = 1
    #         qpd = QProgressDialog(f"Importing Connectivity for Subdomain {j}...", None, 0, 9)
    #         qpd.setWindowTitle("FLO-2D Import")
    #         qpd.setModal(True)
    #         qpd.forceShow()
    #         qpd.setValue(0)
    #
    #         for subdomain_connectivity in subdomain_connectivities:
    #             start_time = time.time()
    #             md_fid = subdomain_connectivity[0]  # md.fid
    #             subdomain_path = subdomain_connectivity[1]  # md.subdomain_path
    #
    #             for i in range(9):  # Loop through fid_subdomain_x and ups_downs_x pairs
    #                 subdomain_fid_index = 2 + (i - 1) * 3  # Get index for subdomain fid
    #                 mult_domain_index = subdomain_fid_index + 1  # Get index for mult_domain
    #                 ds_file_index = subdomain_fid_index + 2  # Get index for ds_file
    #
    #                 fid_subdomain = subdomain_connectivity[subdomain_fid_index]
    #
    #                 if not fid_subdomain or fid_subdomain == 0:
    #                     continue
    #
    #                 mult_domain = subdomain_connectivity[mult_domain_index]
    #                 ds_file = subdomain_connectivity[ds_file_index]
    #
    #                 if fid_subdomain and mult_domain:
    #                     pass
    #                 elif fid_subdomain and ds_file:
    #                     cadpts = f"{subdomain_path}/CADPTS.DAT"
    #                     cadpts_ds = f"{subdomain_path}/{ds_file}"
    #
    #                     # Using pandas to speed up
    #                     import pandas as pd
    #
    #                     # Define column names (since files have no headers)
    #                     column_names = ["id", "x", "y"]
    #
    #                     # Read the CSV files without headers and assign column names
    #                     df1 = pd.read_csv(cadpts, names=column_names, sep=r'\s+',
    #                                       dtype={"id": int, "x": float, "y": float})
    #                     df2 = pd.read_csv(cadpts_ds, names=column_names, sep=r'\s+',
    #                                       dtype={"id": int, "x": float, "y": float})
    #
    #                     # Perform an inner join on x and y to find matching coordinates
    #                     matches = df1.merge(df2, on=["x", "y"], suffixes=('_file1', '_file2'))
    #
    #                     # Select only the matching IDs
    #                     result = matches[["id_file1", "id_file2"]]
    #
    #                     # Extract upstream and downstream cells
    #                     upstream_cells, downstream_cells = result["id_file1"].tolist(), result["id_file2"].tolist()  # Efficient unpacking
    #
    #                     # Collect bulk insert data
    #                     for upstream, downstream in zip(upstream_cells, downstream_cells):
    #                         # if upstream in cell_centroids:
    #                         bulk_insert_data.append(
    #                             (md_fid, upstream, fid_subdomain, downstream))
    #
    #                 qpd.setValue(i + 1)
    #
    #             end_time = time.time()
    #             hours, rem = divmod(end_time - start_time, 3600)
    #             minutes, seconds = divmod(rem, 60)
    #             time_passed = "{:0>2}:{:0>2}:{:0>2}".format(int(hours), int(minutes), int(seconds))
    #             self.uc.log_info(f"Time Elapsed to import connectivity for Subdomain {j}: {time_passed}")
    #             j += 1
    #             qpd.setLabelText(f"Importing Connectivity for Subdomain {j}...")
    #
    #         # Execute bulk insert
    #         if bulk_insert_data:
    #             self.gutils.execute_many("""
    #                                           INSERT INTO schema_md_connect_cells
    #                                           (up_domain_fid, up_domain_cell, down_domain_fid, down_domain_cell)
    #                                           VALUES (?, ?, ?, ?);
    #                                       """, bulk_insert_data)






