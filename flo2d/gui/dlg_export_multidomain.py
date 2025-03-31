import os
import shutil

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QFileDialog, QApplication, QCheckBox
from qgis.PyQt.QtCore import NULL

from .ui_utils import load_ui
from ..flo2d_ie.flo2dgeopackage import Flo2dGeoPackage
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui("export_multiple_domains")


class ExportMultipleDomainsDialog(qtBaseClass, uiDialog):
    """
    Manages the dialog interface for exporting multiple domains. Includes methods to
    populate subdomains, specify directories, validate configurations, and handle exports.
    """
    def __init__(self, con, iface, lyrs):
        """
        Initialize the ExportMultipleDomainsDialog with required dependencies.
        """
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = GeoPackageUtils(con, iface)
        self.f2g = Flo2dGeoPackage(con, iface)

        self.ok_btn.clicked.connect(self.export_subdomains)
        self.ok2_btn.clicked.connect(self.export_selected_subdomains)
        self.cancel_btn.clicked.connect(self.close_dlg)

        self.export_method_cbo.currentIndexChanged.connect(self.block_export_selected_subdomains)

        self.select_dir_tb.clicked.connect(self.select_dir)

        self.populate_subdomains()

    def populate_subdomains(self):
        """
        Populates the dialog with available subdomains from the database.
        Displays them as options for user selection and configuration for export.
        """
        # Get the number of subdomains
        n_subdomains_qry = self.gutils.execute("""SELECT COUNT(subdomain_name) FROM mult_domains_methods;""").fetchone()
        n_subdomains = n_subdomains_qry[0] if n_subdomains_qry else 0

        # Get the actual subdomain names
        subdomains_name_qry = self.gutils.execute("""SELECT subdomain_name FROM mult_domains_methods;""").fetchall()
        subdomains_name = [row[0] for row in subdomains_name_qry]

        # Loop over checkboxes in order
        for i in range(1, 16):
            checkbox = self.findChild(QCheckBox, f"checkBox_{i}")  # Find checkbox by name
            if checkbox:
                if i <= n_subdomains:  # If there's a corresponding subdomain
                    checkbox.setText(subdomains_name[i - 1])  # Assign name
                    checkbox.setVisible(True)  # Show it
                else:
                    checkbox.setVisible(False)  # Hide extra checkboxes

    def block_export_selected_subdomains(self):
        """
        Block all checkboxes and disable the Export All if the export_method_cbo's index is 2 or 3 (CADPTS.DAT).
        """
        if self.export_method_cbo.currentIndex() in [2, 3]:
            # Disable all checkboxes related to subdomains
            # Loop over checkboxes in order
            for i in range(1, 16):
                checkbox = self.findChild(QCheckBox, f"checkBox_{i}")  # Find checkbox by name
                if checkbox:
                    checkbox.setEnabled(False)
            # Disable the ok button
            self.ok2_btn.setEnabled(False)
        else:
            for i in range(1, 16):
                checkbox = self.findChild(QCheckBox, f"checkBox_{i}")  # Find checkbox by name
                if checkbox:
                    checkbox.setEnabled(True)
            # Disable the ok button
            self.ok2_btn.setEnabled(True)


    def close_dlg(self):
        """
        Function to close the dialog
        """
        self.close()

    def select_dir(self):
        """
        Opens a directory selection dialog for the user to specify a target
        folder for exporting subdomain data. Assigns the chosen directory
        to the respective field for further processing.
        """
        s = QSettings()
        project_dir = s.value("FLO-2D/lastGdsDir")
        domain_dir = QFileDialog.getExistingDirectory(
            None, "Select Export Domain folder", directory=project_dir
        )
        if not domain_dir:
            return

        self.export_directory_le.setText(domain_dir)

    def export_selected_subdomains(self):
        """
        Export the selected subdomains to the specified directory.

        The method retrieves the list of selected subdomains from the UI,
        fetches data from the database, and writes it to specific files
        based on the export method selected by the user.

        Export Methods:
            - 0: MULTIDOMAIN.DAT
            - 1: ONLY MULTIDOMAIN.DAT
            - 2: CADPTS.DAT
            - 3: ONLY CADPTS.DAT
            - 4: NO CONNECTIVITY
        """
        QApplication.setOverrideCursor(Qt.WaitCursor)

        # Figure out the export method
        # 0 -> MULTIDOMAIN.DAT
        # 2 -> CADPTS.DAT
        # 3 -> ONLY CADPTS.DAT
        # 4 -> NO CONNECTIVITY
        export_method = self.export_method_cbo.currentIndex()

        export_subdomains = []

        # Loop over checkboxes in order
        for i in range(1, 16):
            checkbox = self.findChild(QCheckBox, f"checkBox_{i}")  # Find checkbox by name
            if checkbox.isChecked():
                 export_subdomains.append(checkbox.text())

        if len(export_subdomains) == 0:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(f"No subdomains were selected!")
            self.uc.bar_warn(f"No subdomains were selected!")
            return

        for subdomain_name in export_subdomains:

            subdomains = self.gutils.execute(f"SELECT fid, subdomain_name FROM mult_domains_methods WHERE subdomain_name = '{subdomain_name}';").fetchone()

            if subdomains:
                # Figure out the downstream domains
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

                export_folder = os.path.join(self.export_directory_le.text(), subdomains[1])
                if not os.path.exists(export_folder):
                    os.makedirs(export_folder)

                sub_grid_cells = self.gutils.execute(f"""SELECT DISTINCT md.domain_cell, 
                                                                g.n_value, 
                                                                g.elevation,
                                                                ST_AsText(ST_Centroid(GeomFromGPB(g.geom)))
                                                            FROM grid g
                                                            JOIN schema_md_cells md ON g.fid = md.grid_fid
                                                            WHERE 
                                                                md.domain_fid = {subdomains[0]};""").fetchall()

                records = sorted(sub_grid_cells, key=lambda x: x[0])

                self.f2g.export_cont_toler_dat(export_folder)

                mannings = os.path.join(str(export_folder), "MANNINGS_N.DAT")
                topo = os.path.join(str(export_folder), "TOPO.DAT")
                cadpts = os.path.join(str(export_folder), "CADPTS.DAT")
                multidomain = os.path.join(str(export_folder), "MULTIDOMAIN.DAT")

                nulls = 0

                mline = "{0: >10} {1: >10}\n"
                tline = "{0: >15} {1: >15} {2: >10}\n"
                cline = "{0: >9} {1: >14} {2: >14}\n"
                mdline_n = "N {0}\n"
                mdline_d = "D {0} {1}\n"

                # MULTIDOMAIN.DAT
                if export_method == 0:
                    with open(mannings, "w") as m, open(topo, "w") as t:
                        for row in records:
                            fid, man, elev, geom = row
                            if man == None or elev == None:
                                nulls += 1
                                if man == None:
                                    man = 0.04
                                if elev == None:
                                    elev = -9999
                            x, y = geom.strip("POINT()").split()
                            m.write(mline.format(fid, "{0:.3f}".format(man)))
                            t.write(
                                tline.format(
                                    "{0:.4f}".format(float(x)),
                                    "{0:.4f}".format(float(y)),
                                    "{0:.4f}".format(elev),
                                )
                            )

                    connected_subdomains = downstream_domains[subdomains[0]]
                    if connected_subdomains:
                        with open(multidomain, "w") as md:
                            for connected_subdomain in connected_subdomains:
                                md.write(mdline_n.format(connected_subdomain))
                                up_cell_qry = f"""SELECT grid_fid, domain_cell FROM schema_md_cells WHERE domain_fid = {subdomains[0]} and down_domain_fid = {connected_subdomain};"""
                                for grid_fid, up_cell in  self.gutils.execute(up_cell_qry).fetchall():
                                    down_cells_qry = f"""SELECT domain_cell FROM schema_md_cells WHERE domain_fid = {connected_subdomain} and grid_fid = {grid_fid};"""
                                    down_cells = self.gutils.execute(down_cells_qry).fetchall()
                                    if down_cells:
                                        md.write(mdline_d.format(str(up_cell), str(down_cells[0][0])))

                # ONLY MULTIDOMAIN.DAT
                elif export_method == 1:
                    connected_subdomains = downstream_domains[subdomains[0]]
                    if connected_subdomains:
                        with open(multidomain, "w") as md:
                            for connected_subdomain in connected_subdomains:
                                md.write(mdline_n.format(connected_subdomain))
                                up_cell_qry = f"""SELECT grid_fid, domain_cell FROM schema_md_cells WHERE domain_fid = {subdomains[0]} and down_domain_fid = {connected_subdomain};"""
                                for grid_fid, up_cell in self.gutils.execute(up_cell_qry).fetchall():
                                    down_cells_qry = f"""SELECT domain_cell FROM schema_md_cells WHERE domain_fid = {connected_subdomain} and grid_fid = {grid_fid};"""
                                    down_cells = self.gutils.execute(down_cells_qry).fetchall()
                                    if down_cells:
                                        md.write(mdline_d.format(str(up_cell), str(down_cells[0][0])))

                # NO CONNECTIVITY
                elif export_method == 2:
                    with open(mannings, "w") as m, open(topo, "w") as t:
                        for row in records:
                            fid, man, elev, geom = row
                            if man == None or elev == None:
                                nulls += 1
                                if man == None:
                                    man = 0.04
                                if elev == None:
                                    elev = -9999
                            x, y = geom.strip("POINT()").split()
                            m.write(mline.format(fid, "{0:.3f}".format(man)))
                            t.write(
                                tline.format(
                                    "{0:.4f}".format(float(x)),
                                    "{0:.4f}".format(float(y)),
                                    "{0:.4f}".format(elev),
                                )
                            )
                            c.write(
                                cline.format(
                                    fid,
                                    "{0:.3f}".format(float(x)),
                                    "{0:.3f}".format(float(y))
                                )
                            )

                # ONLY CADPTS_DSx.DAT
                elif export_method == 3:
                    with open(cadpts, "w") as c:
                        for row in records:
                            fid, _, _, geom = row
                            x, y = geom.strip("POINT()").split()
                            c.write(
                                cline.format(
                                    fid,
                                    "{0:.3f}".format(float(x)),
                                    "{0:.3f}".format(float(y))
                                )
                            )

                # NO CONNECTIVITY
                elif export_method == 4:
                    with open(mannings, "w") as m, open(topo, "w") as t:
                        for row in records:
                            fid, man, elev, geom = row
                            if man == None or elev == None:
                                nulls += 1
                                if man == None:
                                    man = 0.04
                                if elev == None:
                                    elev = -9999
                            x, y = geom.strip("POINT()").split()
                            m.write(mline.format(fid, "{0:.3f}".format(man)))
                            t.write(
                                tline.format(
                                    "{0:.4f}".format(float(x)),
                                    "{0:.4f}".format(float(y)),
                                    "{0:.4f}".format(elev),
                                )
                            )

                if nulls > 0:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_warn(
                        "WARNING 281122.0541: there are "
                        + str(nulls)
                        + " NULL values in the Grid layer's elevation or n_value fields.\n\n"
                        + "Default values where written to the exported files.\n\n"
                        + "Please check the source layer coverage or use Fill Nodata."
                    )
                    QApplication.setOverrideCursor(Qt.WaitCursor)

                # except Exception as e:
                #     QApplication.restoreOverrideCursor()
                #     self.uc.show_error("ERROR 101218.1541: exporting MANNINGS_N.DAT or TOPO.DAT failed!.\n", e)
                #     QApplication.setOverrideCursor(Qt.WaitCursor)

            # Copy and rename the CADPTS to CADPTS_DSx to the correct folders
            if export_method in [2, 3]:
                subdomain_connectivities_names = self.gutils.execute(f"""
                                                   SELECT
                                                       im.subdomain_name,
                                                       im.subdomain_name_1,
                                                       im.subdomain_name_2,
                                                       im.subdomain_name_3,
                                                       im.subdomain_name_4,
                                                       im.subdomain_name_5,
                                                       im.subdomain_name_6,
                                                       im.subdomain_name_7,
                                                       im.subdomain_name_8,
                                                       im.subdomain_name_9
                                                   FROM
                                                       mult_domains_con AS im;
                                                               """).fetchall()
                if subdomain_connectivities_names:
                    for subdomain_connectivity_name in subdomain_connectivities_names:
                        current_subdomain = subdomain_connectivity_name[0]
                        current_subdomain_folder = os.path.join(self.export_directory_le.text(), current_subdomain)
                        for i in range(1, 10):
                            downstream_subdomains_folder = os.path.join(self.export_directory_le.text(),
                                                                        subdomain_connectivity_name[i])
                            if not os.path.exists(downstream_subdomains_folder) or subdomain_connectivity_name[
                                i] == "":
                                continue
                            else:
                                shutil.copy2(os.path.join(str(downstream_subdomains_folder), "CADPTS.DAT"),
                                             os.path.join(str(current_subdomain_folder), f"CADPTS_DS{i}.DAT"))

        QApplication.restoreOverrideCursor()
        self.uc.log_info(f"Subdomains exported correctly!")
        self.uc.bar_info(f"Subdomains exported correctly!")
        self.close_dlg()
        QApplication.restoreOverrideCursor()

    def export_subdomains(self):
        """
        Export all subdomains to the specified directories.

        This method retrieves all subdomain data, calculates connectivity
        details if required, and writes the results to appropriate folders
        as multiple files.
        """
        QApplication.setOverrideCursor(Qt.WaitCursor)

        # Figure out the export method
        # 0 -> MULTIDOMAIN.DAT
        # 1 -> ONLY MULTIDOMAIN.DAT
        # 2 -> CADPTS.DAT
        # 3 -> ONLY CADPTS.DAT
        # 4 -> NO CONNECTIVITY
        export_method = self.export_method_cbo.currentIndex()

        subdomains = self.gutils.execute("SELECT fid, subdomain_name FROM mult_domains_methods;").fetchall()

        if subdomains:
            # Figure out the upstream domains
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

            for subdomain in subdomains:

                export_folder = os.path.join(self.export_directory_le.text(), subdomain[1])
                if not os.path.exists(export_folder):
                    os.makedirs(export_folder)

                sub_grid_cells = self.gutils.execute(f"""SELECT DISTINCT md.domain_cell, 
                                                                g.n_value, 
                                                                g.elevation,
                                                                ST_AsText(ST_Centroid(GeomFromGPB(g.geom)))
                                                            FROM grid g
                                                            JOIN schema_md_cells md ON g.fid = md.grid_fid
                                                            WHERE 
                                                                md.domain_fid = {subdomain[0]};""").fetchall()

                records = sorted(sub_grid_cells, key=lambda x: x[0])

                self.f2g.export_cont_toler_dat(export_folder)

                mannings = os.path.join(str(export_folder), "MANNINGS_N.DAT")
                topo = os.path.join(str(export_folder), "TOPO.DAT")
                cadpts = os.path.join(str(export_folder), "CADPTS.DAT")
                multidomain = os.path.join(str(export_folder), "MULTIDOMAIN.DAT")

                nulls = 0

                mline = "{0: >10} {1: >10}\n"
                tline = "{0: >15} {1: >15} {2: >10}\n"
                cline = "{0: >9} {1: >14} {2: >14}\n"
                mdline_n = "N {0}\n"
                mdline_d = "D {0} {1}\n"

                # MULTIDOMAIN.DAT
                if export_method == 0:
                    with open(mannings, "w") as m, open(topo, "w") as t:
                        for row in records:
                            fid, man, elev, geom = row
                            if man == None or elev == None:
                                nulls += 1
                                if man == None:
                                    man = 0.04
                                if elev == None:
                                    elev = -9999
                            x, y = geom.strip("POINT()").split()
                            m.write(mline.format(fid, "{0:.3f}".format(man)))
                            t.write(
                                tline.format(
                                    "{0:.4f}".format(float(x)),
                                    "{0:.4f}".format(float(y)),
                                    "{0:.4f}".format(elev),
                                )
                            )

                    connected_subdomains = downstream_domains[subdomain[0]]
                    if connected_subdomains:
                        with open(multidomain, "w") as md:
                            for connected_subdomain in connected_subdomains:
                                md.write(mdline_n.format(connected_subdomain))
                                up_cell_qry = f"""SELECT grid_fid, domain_cell FROM schema_md_cells WHERE domain_fid = {subdomain[0]} and down_domain_fid = {connected_subdomain};"""
                                for grid_fid, up_cell in  self.gutils.execute(up_cell_qry).fetchall():
                                    down_cells_qry = f"""SELECT domain_cell FROM schema_md_cells WHERE domain_fid = {connected_subdomain} and grid_fid = {grid_fid};"""
                                    down_cells = self.gutils.execute(down_cells_qry).fetchall()
                                    if down_cells:
                                        md.write(mdline_d.format(str(up_cell), str(down_cells[0][0])))

                # ONLY MULTIDOMAIN.DAT
                elif export_method == 1:
                    connected_subdomains = downstream_domains[subdomain[0]]
                    if connected_subdomains:
                        with open(multidomain, "w") as md:
                            for connected_subdomain in connected_subdomains:
                                md.write(mdline_n.format(connected_subdomain))
                                up_cell_qry = f"""SELECT grid_fid, domain_cell FROM schema_md_cells WHERE domain_fid = {subdomain[0]} and down_domain_fid = {connected_subdomain};"""
                                for grid_fid, up_cell in self.gutils.execute(up_cell_qry).fetchall():
                                    down_cells_qry = f"""SELECT domain_cell FROM schema_md_cells WHERE domain_fid = {connected_subdomain} and grid_fid = {grid_fid};"""
                                    down_cells = self.gutils.execute(down_cells_qry).fetchall()
                                    if down_cells:
                                        md.write(mdline_d.format(str(up_cell), str(down_cells[0][0])))

                # CADPTS_DSx.DAT
                elif export_method == 2:
                    with open(mannings, "w") as m, open(topo, "w") as t, open(cadpts, "w") as c:
                        for row in records:
                            fid, man, elev, geom = row
                            if man == None or elev == None:
                                nulls += 1
                                if man == None:
                                    man = 0.04
                                if elev == None:
                                    elev = -9999
                            x, y = geom.strip("POINT()").split()
                            m.write(mline.format(fid, "{0:.3f}".format(man)))
                            t.write(
                                tline.format(
                                    "{0:.4f}".format(float(x)),
                                    "{0:.4f}".format(float(y)),
                                    "{0:.4f}".format(elev),
                                )
                            )
                            c.write(
                                cline.format(
                                    fid,
                                    "{0:.3f}".format(float(x)),
                                    "{0:.3f}".format(float(y))
                                )
                            )

                # ONLY CADPTS_DSx.DAT
                elif export_method == 3:
                    with open(cadpts, "w") as c:
                        for row in records:
                            fid, _, _, geom = row
                            x, y = geom.strip("POINT()").split()
                            c.write(
                                cline.format(
                                    fid,
                                    "{0:.3f}".format(float(x)),
                                    "{0:.3f}".format(float(y))
                                )
                            )

                # NO CONNECTIVITY
                elif export_method == 4:
                    with open(mannings, "w") as m, open(topo, "w") as t:
                        for row in records:
                            fid, man, elev, geom = row
                            if man == None or elev == None:
                                nulls += 1
                                if man == None:
                                    man = 0.04
                                if elev == None:
                                    elev = -9999
                            x, y = geom.strip("POINT()").split()
                            m.write(mline.format(fid, "{0:.3f}".format(man)))
                            t.write(
                                tline.format(
                                    "{0:.4f}".format(float(x)),
                                    "{0:.4f}".format(float(y)),
                                    "{0:.4f}".format(elev),
                                )
                            )

                if nulls > 0:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_warn(
                        "WARNING 281122.0541: there are "
                        + str(nulls)
                        + " NULL values in the Grid layer's elevation or n_value fields.\n\n"
                        + "Default values where written to the exported files.\n\n"
                        + "Please check the source layer coverage or use Fill Nodata."
                    )
                    self.uc.log_info(
                        "WARNING 281122.0541: there are "
                        + str(nulls)
                        + " NULL values in the Grid layer's elevation or n_value fields.\n\n"
                        + "Default values where written to the exported files.\n\n"
                        + "Please check the source layer coverage or use Fill Nodata."
                    )
                    QApplication.setOverrideCursor(Qt.WaitCursor)

                # try:
                # except Exception as e:
                #     QApplication.restoreOverrideCursor()
                #     self.uc.show_error("ERROR 101218.1541: exporting MANNINGS_N.DAT or TOPO.DAT failed!.\n", e)
                #     QApplication.setOverrideCursor(Qt.WaitCursor)

            # Copy and rename the CADPTS to CADPTS_DSx to the correct folders
            if export_method in [2, 3]:
                subdomain_connectivities_names = self.gutils.execute(f"""
                                                   SELECT
                                                       im.subdomain_name,
                                                       im.subdomain_name_1,
                                                       im.subdomain_name_2,
                                                       im.subdomain_name_3,
                                                       im.subdomain_name_4,
                                                       im.subdomain_name_5,
                                                       im.subdomain_name_6,
                                                       im.subdomain_name_7,
                                                       im.subdomain_name_8,
                                                       im.subdomain_name_9
                                                   FROM
                                                       mult_domains_con AS im;
                                                               """).fetchall()
                if subdomain_connectivities_names:
                    for subdomain_connectivity_name in subdomain_connectivities_names:
                        current_subdomain = subdomain_connectivity_name[0]
                        current_subdomain_folder = os.path.join(self.export_directory_le.text(), current_subdomain)
                        for i in range(1, 10):
                            downstream_subdomains_folder = os.path.join(self.export_directory_le.text(), subdomain_connectivity_name[i])
                            if not os.path.exists(downstream_subdomains_folder) or subdomain_connectivity_name[i] == "":
                                continue
                            else:
                                shutil.copy2(os.path.join(str(downstream_subdomains_folder), "CADPTS.DAT"), os.path.join(str(current_subdomain_folder), f"CADPTS_DS{i}.DAT"))

        else:
            self.uc.log_info(f"This project has no subdomains!")
            self.uc.bar_warn(f"This project has no subdomains!")

        QApplication.restoreOverrideCursor()
        self.uc.log_info(f"Subdomains exported correctly!")
        self.uc.bar_info(f"Subdomains exported correctly!")
        self.close_dlg()
        QApplication.restoreOverrideCursor()
