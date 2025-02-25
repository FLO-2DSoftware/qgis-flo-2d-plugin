import itertools
import os
import re
import time

from PyQt5.QtCore import QSettings, QVariant
from PyQt5.QtWidgets import QProgressDialog
from qgis.PyQt.QtCore import NULL
from qgis._core import QgsProject, QgsVectorLayer, QgsField, QgsFeature

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
                    "SELECT fid FROM mult_domains_methods WHERE subdomain_name = ?", (subdomain_cbo,)
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

        self.gutils.clear_tables("schema_md_connect_cells")

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
                if subdomain_connectivity[1] is NULL or subdomain_connectivity[1] == "" or subdomain_connectivity[1] is None:

                    if self.gutils.is_table_empty("grid"):
                        self.uc.bar_warn("There is no grid! Please create it before running tool.")
                        self.uc.log_info("There is no grid! Please create it before running tool.")
                        return

                    # Create the intersected lines
                    polygon_layer = self.lyrs.data["mult_domains"]["qlyr"]

                    # Create a new memory layer for intersections with the same CRS as the polygon layer
                    intersection_layer = self.lyrs.data["user_md_connect_lines"]["qlyr"]
                    provider = intersection_layer.dataProvider()

                    # Collect all features from the polygon layer
                    features = list(polygon_layer.getFeatures())

                    # Initialize a counter for the intersection feature's fid
                    intersection_id = 1

                    # Iterate over all unique pairs of polygons using itertools.combinations
                    for feat1, feat2 in itertools.combinations(features, 2):
                        geom1 = feat1.geometry()
                        geom2 = feat2.geometry()

                        # Check if the two geometries touch (i.e., share a boundary)
                        if geom1.touches(geom2):
                            # Compute the shared border between the two geometries
                            intersect_geom = geom1.intersection(geom2)

                            # Create a new feature for the intersection layer
                            new_feat = QgsFeature()
                            new_feat.setGeometry(intersect_geom)
                            # Here we assume that the polygon layer's unique identifier is stored in the "fid" field.
                            new_feat.setAttributes([intersection_id, feat1["fid"], feat2["fid"], ""])
                            provider.addFeature(new_feat)

                            intersection_id += 1

                    self.uc.log_info("Connectivity saved!")
                    self.uc.bar_info("Connectivity saved!")

                    self.lyrs.data["user_md_connect_lines"]["qlyr"].triggerRepaint()

                    self.close_dlg()

                    return

                # Import the connectivity
                else:
                    start_time = time.time()
                    md_fid = subdomain_connectivity[0]  # md.fid
                    current_subdomain_path = subdomain_connectivity[1]  # md.subdomain_path

                    used_multidomain_file = False

                    for i in range(9):  # Loop through fid_subdomain_x and ups_downs_x pairs
                        subdomain_fid_index = 2 + (i - 1) * 4  # Get index for subdomain fid
                        subdomain_name_index = subdomain_fid_index + 1  # Get index for subdomain name
                        mult_domain_index = subdomain_fid_index + 2  # Get index for mult_domain
                        ds_file_index = subdomain_fid_index + 3  # Get index for ds_file

                        fid_subdomain = subdomain_connectivity[subdomain_fid_index]

                        if not fid_subdomain or fid_subdomain == 0:
                            continue

                        mult_domain = subdomain_connectivity[mult_domain_index]
                        ds_file = subdomain_connectivity[ds_file_index]

                        # Get the connectivity through the MULTIDOMAIN.DAT
                        if fid_subdomain and mult_domain:

                            if used_multidomain_file:
                                continue

                            multidomain = f"{current_subdomain_path}/MULTIDOMAIN.DAT"

                            multidomain_data = {}
                            current_subdomain = None

                            with open(multidomain, "r") as f:
                                for line in f:
                                    data = line.strip().split()

                                    if not data:
                                        continue

                                    if data[0] == "N":
                                        current_subdomain = int(data[1])
                                        multidomain_data[current_subdomain] = []

                                    elif data[0] == "D" and current_subdomain is not None:
                                        up_domain_cell = int(data[1])
                                        down_domain_cells = list(map(int, data[2:]))
                                        multidomain_data[current_subdomain].append((up_domain_cell, down_domain_cells))

                            j = 2 + (i - 1) * 4
                            for subdomain, connections in multidomain_data.items():
                                for up_domain_cell, down_domain_cells in connections:
                                    for down_domain_cell in down_domain_cells:
                                        bulk_insert_data.append((md_fid, up_domain_cell, subdomain_connectivity[j], down_domain_cell))
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
                            result = matches[["id_file1", "id_file2"]]

                            # Extract upstream and downstream cells
                            upstream_cells, downstream_cells = result["id_file1"].tolist(), result[
                                "id_file2"].tolist()  # Efficient unpacking

                            # Collect bulk insert data
                            for upstream, downstream in zip(upstream_cells, downstream_cells):
                                # if upstream in cell_centroids:
                                bulk_insert_data.append(
                                    (md_fid, upstream, fid_subdomain, downstream))

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
                                          INSERT INTO schema_md_connect_cells 
                                          (up_domain_fid, up_domain_cell, down_domain_fid, down_domain_cell) 
                                          VALUES (?, ?, ?, ?);
                                      """, bulk_insert_data)

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