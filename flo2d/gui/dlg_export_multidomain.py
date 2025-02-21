import os

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QFileDialog, QApplication, QCheckBox
from qgis.PyQt.QtCore import NULL

from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui("export_multiple_domains")


class ExportMultipleDomainsDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = GeoPackageUtils(con, iface)

        self.ok_btn.clicked.connect(self.export_subdomains)
        self.ok2_btn.clicked.connect(self.export_selected_subdomains)
        self.cancel_btn.clicked.connect(self.close_dlg)

        self.select_dir_tb.clicked.connect(self.select_dir)

        self.populate_subdomains()

    def populate_subdomains(self):
        """
        Function to populate the checkboxes for the user to export the selected subdomains
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

    def close_dlg(self):
        """
        Function to close the dialog
        """
        self.close()

    def select_dir(self):
        """
        Function to select the export directory
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
        Function to export the subdomains to different folders
        """
        QApplication.setOverrideCursor(Qt.WaitCursor)

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
                # Figure out the upstream domains
                upstream_domains = {}
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
                        if subdomain_fid == NULL:
                            continue
                        for i in range(1, 10):
                            if subdomain_connectivity[i] != NULL:
                                if subdomain_connectivity[i] not in upstream_domains:
                                    upstream_domains[subdomain_connectivity[i]] = []
                                if subdomain_fid not in upstream_domains[subdomain_connectivity[i]]:
                                    upstream_domains[subdomain_connectivity[i]].append(subdomain_fid)

                export_folder = os.path.join(self.export_directory_le.text(), subdomains[1])
                if not os.path.exists(export_folder):
                    os.makedirs(export_folder)
                if subdomains[0] == 1:
                    sql = (
                        """SELECT fid, n_value, elevation, ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM grid WHERE domain_fid = 1 ORDER BY fid;"""
                    )
                    records = self.gutils.execute(sql).fetchall()
                else:
                    sub_grid_cells = self.gutils.execute(f"""SELECT 
                                                                g.domain_cell, 
                                                                g.n_value, 
                                                                g.elevation, 
                                                                ST_AsText(ST_Centroid(GeomFromGPB(g.geom)))
                                                            FROM 
                                                                grid g
                                                            WHERE 
                                                                g.domain_fid = {subdomains[0]};""").fetchall()

                    for upstream_domain in upstream_domains[subdomains[0]]:
                        sub_con_cells = self.gutils.execute(f"""
                                        SELECT c.down_domain_cell AS domain_cell, g.n_value, g.elevation, ST_AsText(ST_Centroid(GeomFromGPB(g.geom)))
                                        FROM grid g
                                        JOIN schema_md_connect_cells c ON g.domain_cell = c.up_domain_cell
                                        WHERE c.down_domain_fid = {subdomains[0]} AND g.domain_fid = {upstream_domain} AND c.up_domain_fid = {upstream_domain} AND g.connectivity_fid != 'NULL'""").fetchall()
                        sub_grid_cells.extend(sub_con_cells)

                    records = sorted(sub_grid_cells, key=lambda x: x[0])

                # try:
                mannings = os.path.join(str(export_folder), "MANNINGS_N.DAT")
                topo = os.path.join(str(export_folder), "TOPO.DAT")
                cadpts = os.path.join(str(export_folder), "CADPTS.DAT")

                mline = "{0: >10} {1: >10}\n"
                tline = "{0: >15} {1: >15} {2: >10}\n"
                cline = "{0: >9} {1: >14} {2: >14}\n"
                nulls = 0
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

        QApplication.restoreOverrideCursor()
        self.uc.log_info(f"Subdomains exported correctly!")
        self.uc.bar_info(f"Subdomains exported correctly!")
        self.close_dlg()
        QApplication.restoreOverrideCursor()

    def export_subdomains(self):
        """
        Function to export the subdomains to different folders
        """
        QApplication.setOverrideCursor(Qt.WaitCursor)

        subdomains = self.gutils.execute("SELECT fid, subdomain_name FROM mult_domains_methods;").fetchall()

        if subdomains:
            # Figure out the upstream domains
            upstream_domains = {}
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
                    if subdomain_fid == NULL:
                        continue
                    for i in range(1, 10):
                        if subdomain_connectivity[i] != NULL:
                            if subdomain_connectivity[i] not in upstream_domains:
                                upstream_domains[subdomain_connectivity[i]] = []
                            if subdomain_fid not in upstream_domains[subdomain_connectivity[i]]:
                                upstream_domains[subdomain_connectivity[i]].append(subdomain_fid)

            for subdomain in subdomains:
                export_folder = os.path.join(self.export_directory_le.text(), subdomain[1])
                if not os.path.exists(export_folder):
                    os.makedirs(export_folder)
                if subdomain[0] == 1:
                    sql = (
                        """SELECT fid, n_value, elevation, ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM grid WHERE domain_fid = 1 ORDER BY fid;"""
                    )
                    records = self.gutils.execute(sql).fetchall()
                else:
                    sub_grid_cells = self.gutils.execute(f"""SELECT 
                                                                g.domain_cell, 
                                                                g.n_value, 
                                                                g.elevation, 
                                                                ST_AsText(ST_Centroid(GeomFromGPB(g.geom)))
                                                            FROM 
                                                                grid g
                                                            WHERE 
                                                                g.domain_fid = {subdomain[0]};""").fetchall()

                    for upstream_domain in upstream_domains[subdomain[0]]:
                        sub_con_cells = self.gutils.execute(f"""
                                        SELECT c.down_domain_cell AS domain_cell, g.n_value, g.elevation, ST_AsText(ST_Centroid(GeomFromGPB(g.geom)))
                                        FROM grid g
                                        JOIN schema_md_connect_cells c ON g.domain_cell = c.up_domain_cell
                                        WHERE c.down_domain_fid = {subdomain[0]} AND g.domain_fid = {upstream_domain} AND c.up_domain_fid = {upstream_domain} AND g.connectivity_fid != 'NULL'""").fetchall()
                        sub_grid_cells.extend(sub_con_cells)

                    records = sorted(sub_grid_cells, key=lambda x: x[0])

                # try:
                mannings = os.path.join(str(export_folder), "MANNINGS_N.DAT")
                topo = os.path.join(str(export_folder), "TOPO.DAT")
                cadpts = os.path.join(str(export_folder), "CADPTS.DAT")

                mline = "{0: >10} {1: >10}\n"
                tline = "{0: >15} {1: >15} {2: >10}\n"
                cline = "{0: >9} {1: >14} {2: >14}\n"
                nulls = 0
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

        else:
            self.uc.log_info(f"This project has no subdomains!")
            self.uc.bar_warn(f"This project has no subdomains!")

        QApplication.restoreOverrideCursor()
        self.uc.log_info(f"Subdomains exported correctly!")
        self.uc.bar_info(f"Subdomains exported correctly!")
        self.close_dlg()
        QApplication.restoreOverrideCursor()
