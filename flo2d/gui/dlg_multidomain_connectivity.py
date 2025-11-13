import os
import time

try:
    import h5py
except ImportError:
    pass
from PyQt5.QtWidgets import QProgressDialog
from qgis.PyQt.QtCore import NULL

from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui("multiple_domains_connectivity")


class MultipleDomainsConnectivityDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, con, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = GeoPackageUtils(con, iface)

        self.hide_elements = [
            [self.line_1, self.sub1_cbo, self.toolButton_1],
            [self.line_2, self.sub2_cbo, self.toolButton_2],
            [self.line_3, self.sub3_cbo, self.toolButton_3],
            [self.line_4, self.sub4_cbo, self.toolButton_4],
            [self.line_5, self.sub5_cbo, self.toolButton_5],
            [self.line_6, self.sub6_cbo, self.toolButton_6],
            [self.line_7, self.sub7_cbo, self.toolButton_7],
            [self.line_8, self.sub8_cbo, self.toolButton_8],
            [self.line_9, self.sub9_cbo, self.toolButton_9]
        ]

        self.subdomains_connectivity_cbos = [
            self.sub1_cbo,
            self.sub2_cbo,
            self.sub3_cbo,
            self.sub4_cbo,
            self.sub5_cbo,
            self.sub6_cbo,
            self.sub7_cbo,
            self.sub8_cbo,
            self.sub9_cbo
        ]

        self.populate_current_subdomains()

        self.cancel_btn.clicked.connect(self.close_dlg)
        self.ok_btn.clicked.connect(self.save_connectivity)

        self.current_subdomain_cbo.currentIndexChanged.connect(self.repopulate_cbos)

        self.toolButton_1.clicked.connect(lambda: self.remove_subdomain(self.sub1_cbo))
        self.toolButton_2.clicked.connect(lambda: self.remove_subdomain(self.sub2_cbo))
        self.toolButton_3.clicked.connect(lambda: self.remove_subdomain(self.sub3_cbo))
        self.toolButton_4.clicked.connect(lambda: self.remove_subdomain(self.sub4_cbo))
        self.toolButton_5.clicked.connect(lambda: self.remove_subdomain(self.sub5_cbo))
        self.toolButton_6.clicked.connect(lambda: self.remove_subdomain(self.sub6_cbo))
        self.toolButton_7.clicked.connect(lambda: self.remove_subdomain(self.sub7_cbo))
        self.toolButton_8.clicked.connect(lambda: self.remove_subdomain(self.sub8_cbo))
        self.toolButton_9.clicked.connect(lambda: self.remove_subdomain(self.sub9_cbo))

        self.sub1_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.sub2_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.sub3_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.sub4_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.sub5_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.sub6_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.sub7_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.sub8_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.sub9_cbo.currentIndexChanged.connect(self.save_cbo_data)

        self.schema_md_cells = self.lyrs.data["schema_md_cells"]["qlyr"]

    def remove_subdomain(self, subdomain_cbo):
        """
        Function to set the current index to -1 on the removed subdomain
        """
        subdomain_cbo.setCurrentIndex(-1)

    def fill_cbo_data(self):
        """
        Function to fill the combo boxes with data from the 'md_method_x' table in the GeoPackage.
        """
        current_subdomain = self.current_subdomain_cbo.currentText()

        selected_data = self.gutils.execute(
            f"SELECT * FROM mult_domains_con WHERE subdomain_name = ?;", (current_subdomain,)
        ).fetchone()

        if selected_data:
            for i in range(1, 10):  # Loop through subdomains 1 to 9
                subdomain_name_index = 3 + (i - 1) * 4  # Get index for subdomain name
                subdomain_name = selected_data[subdomain_name_index] if selected_data[subdomain_name_index] else ""
                sub_cbo = getattr(self, f"sub{i}_cbo", None)

                if sub_cbo:
                    sub_cbo.setCurrentIndex(sub_cbo.findText(subdomain_name))

    def save_cbo_data(self):
        """
        Function to save the connections defined on the cbos to the geopackage.
        """
        current_subdomain = self.current_subdomain_cbo.currentText()

        # Get the selected fid for the current subdomain
        selected_fid = self.gutils.execute(
            f"SELECT fid FROM mult_domains_con WHERE subdomain_name = ?", (current_subdomain,)
        ).fetchone()

        if not selected_fid:
            return

        selected_fid = selected_fid[0]

        # Prepare data for update
        update_data = {}

        for i in range(1, 10):  # Loop through 1 to 9 (matching subdomain fields)
            subdomain_cbo = getattr(self, f"sub{i}_cbo").currentText()

            if subdomain_cbo:
                fid_query = self.gutils.execute(
                    "SELECT fid_method FROM mult_domains_methods WHERE subdomain_name = ?", (subdomain_cbo,)
                ).fetchone()
                fid_value = fid_query[0] if fid_query else "NULL"
            else:
                fid_value = "NULL"

            update_data[f"fid_subdomain_{i}"] = fid_value
            update_data[f"subdomain_name_{i}"] = subdomain_cbo

        # Construct the SQL UPDATE query dynamically
        set_clause = ", ".join([f"{col} = ?" for col in update_data.keys()])
        values = list(update_data.values()) + [selected_fid]

        sql_query = f"UPDATE mult_domains_con SET {set_clause} WHERE fid = ?"

        # Execute update query
        self.gutils.execute(sql_query, values)

    def repopulate_cbos(self):
        """
        Function to repopulate cbos
        """
        self.blockSignals(True)
        self.populate_subdomains()
        # self.populate_ds_cbos()
        self.fill_cbo_data()
        self.hide_cbos()
        self.blockSignals(False)

    def populate_current_subdomains(self):
        """
        Function to populate the subdomains
        """
        self.current_subdomain_cbo.clear()
        subdomain_names = self.gutils.execute(f"""SELECT subdomain_name FROM mult_domains_methods;""").fetchall()
        if subdomain_names:
            for subdomain_name in subdomain_names:
                self.current_subdomain_cbo.addItem(subdomain_name[0])

        self.populate_subdomains()
        self.fill_cbo_data()
        self.hide_cbos()

    def populate_subdomains(self):
        """
        Function to populate the subdomains
        """
        current_subdomain = self.current_subdomain_cbo.currentText()
        subdomain_names = self.gutils.execute(f"""SELECT subdomain_name FROM mult_domains_methods WHERE NOT subdomain_name = '{current_subdomain}';""").fetchall()
        if subdomain_names:
            for connect_subdomain in self.subdomains_connectivity_cbos:
                connect_subdomain.clear()
                connect_subdomain.addItems([s[0] for s in subdomain_names])
                connect_subdomain.setCurrentIndex(-1)

    def hide_cbos(self):
        """
        This function hides the cbos that do not contain information related to the number of subdomains
        """
        # Number of DS files
        n_ds = self.sub1_cbo.count()
        i = 0
        for elements in self.hide_elements:
            if i >= n_ds:
                elements[0].setVisible(False)
                elements[1].setVisible(False)
                elements[2].setVisible(False)
            else:
                elements[0].setVisible(True)
                elements[1].setVisible(True)
                elements[2].setVisible(True)
            i += 1

    def save_connectivity(self):
        """Function to save the connectivity data into the schema_md_connect_cells"""

        self.gutils.clear_tables("schema_md_cells")

        subdomain_connectivities = self.gutils.execute("""
                               SELECT 
                                   md.fid, 
                                   md.subdomain_path, 
                                   im.fid_subdomain_1, im.subdomain_name_1, im.mult_domains_1, im.ds_file_1, 
                                   im.fid_subdomain_2, im.subdomain_name_2, im.mult_domains_2, im.ds_file_2, 
                                   im.fid_subdomain_3, im.subdomain_name_3, im.mult_domains_3, im.ds_file_3, 
                                   im.fid_subdomain_4, im.subdomain_name_4, im.mult_domains_4, im.ds_file_4, 
                                   im.fid_subdomain_5, im.subdomain_name_5, im.mult_domains_5, im.ds_file_5, 
                                   im.fid_subdomain_6, im.subdomain_name_6, im.mult_domains_6, im.ds_file_6, 
                                   im.fid_subdomain_7, im.subdomain_name_7, im.mult_domains_7, im.ds_file_7, 
                                   im.fid_subdomain_8, im.subdomain_name_8, im.mult_domains_8, im.ds_file_8, 
                                   im.fid_subdomain_9, im.subdomain_name_9, im.mult_domains_9, im.ds_file_9 
                               FROM 
                                   mult_domains_methods AS md
                               JOIN mult_domains_con AS im ON md.fid_method = im.fid;
                                           """).fetchall()
        if subdomain_connectivities:
            bulk_insert_data = []  # Collect all insert statements in a list

            j = 1
            qpd = QProgressDialog(f"Creating Connectivity for Subdomain {j}...", None, 0, 9)
            qpd.setWindowTitle("FLO-2D Import")
            qpd.setModal(True)
            qpd.forceShow()
            qpd.setValue(0)

            for subdomain_connectivity in subdomain_connectivities:
                # Create the connectivity
                if subdomain_connectivity[1] in [NULL, "", None]:
                    pass

                # Import the connectivity
                else:
                    start_time = time.time()
                    md_fid = subdomain_connectivity[0]  # md.fid
                    current_subdomain_path = subdomain_connectivity[1]  # md.subdomain_path

                    used_multidomain_file = False
                    multidomain_data = {}

                    for i in range(9):  # Loop through fid_subdomain_x and ups_downs_x pairs
                        subdomain_fid_index = 2 + (i - 1) * 4  # Get index for subdomain fid
                        mult_domain_index = subdomain_fid_index + 2  # Get index for mult_domain
                        ds_file_index = subdomain_fid_index + 3  # Get index for ds_file

                        fid_subdomain = subdomain_connectivity[subdomain_fid_index]

                        if not fid_subdomain or fid_subdomain == 0:
                            continue

                        mult_domain = subdomain_connectivity[mult_domain_index]
                        ds_file = subdomain_connectivity[ds_file_index]

                        # Get the connectivity through the MULTIDOMAIN.DAT
                        if fid_subdomain and mult_domain == 2:

                            if used_multidomain_file:
                                continue

                            hdf5_file = f"{current_subdomain_path}/Input.hdf5"
                            hdf5_coor = "/Input/Grid/COORDINATES"
                            hdf5_mult = "/Input/Multiple Domains/MULTIDOMAIN"

                            multidomain_data = {}
                            used_multidomain_file = False

                            if os.path.isfile(hdf5_file):
                                with h5py.File(hdf5_file, "r") as hdf:
                                    mult = hdf[hdf5_mult][()]  # shape (N, 3): [connected_subdomain, up_cell, down_cell]
                                    coords = hdf[hdf5_coor]  # shape (Ncells, 2): [x, y]

                                    current_subdomain = None
                                    prev_subdomain = None

                                    # Iterate rows in order; start a new list when the connected_subdomain changes
                                    for row in mult:
                                        subdomain = int(row[0])  # connected_subdomain
                                        up_domain_cell = int(row[1])  # up cell id (1-based)

                                        if subdomain != prev_subdomain:
                                            current_subdomain = subdomain
                                            multidomain_data[current_subdomain] = []
                                            prev_subdomain = subdomain

                                        # Get coordinates for the up cell (convert to 0-based index)
                                        x, y = coords[up_domain_cell - 1]
                                        up_domain_coords = f"POINT({float(x)} {float(y)})"

                                        # Append same tuple structure you used before
                                        multidomain_data[current_subdomain].append((up_domain_cell, up_domain_coords))

                                # Preserve your post-processing block
                                j = 2 + (i - 1) * 4
                                for subdomain, connections in multidomain_data.items():
                                    for up_domain_cell, up_domain_coords in connections:
                                        bulk_insert_data.append((md_fid, up_domain_cell, subdomain, up_domain_coords))
                                        bulk_insert_data.append((subdomain, "", "", up_domain_coords))
                                    j += 4

                                used_multidomain_file = True

                        elif fid_subdomain and mult_domain == 1:

                            if used_multidomain_file:
                                continue

                            multidomain = f"{current_subdomain_path}/MULTIDOMAIN.DAT"
                            topo = f"{current_subdomain_path}/TOPO.DAT"

                            if not os.path.isfile(topo):
                                self.uc.log_info("TOPO.DAT not found!")
                                self.uc.bar_error("TOPO.DAT not found!")
                                return

                            current_subdomain = None

                            with open(multidomain, "r") as md, open(topo, "r") as tp:

                                topo_lines = tp.readlines()

                                for line in md:
                                    data = line.strip().split()

                                    if not data:
                                        continue

                                    if data[0] == "N":
                                        current_subdomain = int(data[1])
                                        multidomain_data[current_subdomain] = []

                                    elif data[0] == "D" and current_subdomain is not None:
                                        up_domain_cell = int(data[1])
                                        # down_domain_cells = list(map(int, data[2:]))
                                        topo_data = topo_lines[up_domain_cell - 1].split()
                                        up_domain_coords = f"POINT({topo_data[0]} {topo_data[1]})"
                                        multidomain_data[current_subdomain].append((up_domain_cell, up_domain_coords))

                            j = 2 + (i - 1) * 4
                            for subdomain, connections in multidomain_data.items():
                                for up_domain_cell, up_domain_coords in connections:
                                    # self.uc.log_info("1 " + str((md_fid, up_domain_cell, subdomain, up_domain_coords)))
                                    # self.uc.log_info("2 " + str((subdomain, "", "", up_domain_coords)))
                                    bulk_insert_data.append((md_fid, up_domain_cell, subdomain, up_domain_coords))
                                    # bulk_insert_data.append((subdomain, "", "", up_domain_coords))
                                j +=  4

                            used_multidomain_file = True

                        # Get the connectivity through the CADPTSs
                        elif fid_subdomain and ds_file:
                            cadpts = f"{current_subdomain_path}/CADPTS.DAT"

                            connect_subdomain_path_qry = self.gutils.execute(f"SELECT subdomain_path FROM mult_domains_methods WHERE fid = {fid_subdomain}").fetchone()
                            if connect_subdomain_path_qry:
                                connect_subdomain_path = connect_subdomain_path_qry[0]
                                cadpts_ds = f"{connect_subdomain_path}/CADPTS.DAT"
                            else:
                                continue

                            # Using pandas to speed up
                            import pandas as pd

                            # Define column names (since files have no headers)
                            column_names = ["id", "x", "y"]

                            # Read the CSV files without headers and assign column names
                            df1 = pd.read_csv(cadpts, names=column_names, sep=r'\s+',
                                              dtype={"id": int, "x": float, "y": float})
                            df2 = pd.read_csv(cadpts_ds, names=column_names, sep=r'\s+',
                                              dtype={"id": int, "x": float, "y": float})

                            # Perform an inner join on x and y to find matching coordinates
                            matches = df1.merge(df2, on=["x", "y"], suffixes=('_file1', '_file2'))

                            # Select only the matching IDs
                            result = matches[["id_file1", "id_file2", "x", "y"]]

                            # Extract upstream and downstream cells
                            upstream_cells = result["id_file1"].tolist()
                            downstream_cells = result["id_file2"].tolist()
                            coordinates = result[["x", "y"]].values.tolist()

                            # Collect bulk insert data
                            for (upstream, downstream, coord) in zip(upstream_cells, downstream_cells, coordinates):
                                coords = f"POINT({coord[0]} {coord[1]})"
                                bulk_insert_data.append((md_fid, upstream, fid_subdomain, coords))
                                bulk_insert_data.append((fid_subdomain, "", "", coords))

                        qpd.setValue(i + 1)

                    end_time = time.time()
                    hours, rem = divmod(end_time - start_time, 3600)
                    minutes, seconds = divmod(rem, 60)
                    time_passed = "{:0>2}:{:0>2}:{:0>2}".format(int(hours), int(minutes), int(seconds))
                    self.uc.log_info(f"Time Elapsed to import connectivity for Subdomain {j}: {time_passed}")
                    j += 1
                    qpd.setLabelText(f"Importing Connectivity for Subdomain {j}...")

            # Execute bulk insert
            if bulk_insert_data:
                self.gutils.execute_many("""
                                          INSERT INTO schema_md_cells 
                                          (domain_fid, domain_cell, down_domain_fid, geom) 
                                          VALUES (?, ?, ?, GeomFromText(?));
                                      """, bulk_insert_data)

        self.schema_md_cells.triggerRepaint()
        schema_md_cells_layer = self.lyrs.get_layer_by_name("Multiple Domain Cells", group=self.lyrs.group)
        extent = schema_md_cells_layer.layer().extent()
        self.iface.mapCanvas().setExtent(extent)
        self.iface.mapCanvas().refresh()

        self.uc.log_info("Connectivity saved!")
        self.uc.bar_info("Connectivity saved!")

        self.close_dlg()

    def blockSignals(self, true_false):
        """
        Function to block cbo signals
        """
        for cbo in self.subdomains_connectivity_cbos:
            cbo.blockSignals(true_false)

    def close_dlg(self):
        """
        Function to close the dialog
        """
        self.close()