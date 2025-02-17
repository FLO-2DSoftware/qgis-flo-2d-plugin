import os

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QFileDialog, QApplication

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
        self.cancel_btn.clicked.connect(self.close_dlg)

        self.select_dir_tb.clicked.connect(self.select_dir)

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

    def export_subdomains(self):
        """
        Function to export the subdomains to different folders
        """
        QApplication.setOverrideCursor(Qt.WaitCursor)

        subdomains = self.gutils.execute("SELECT fid, subdomain_name FROM mult_domains_methods;").fetchall()

        if subdomains:
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
                    method = self.gutils.execute(f"""
                    SELECT fid, import_method, fid_method FROM mult_domains_methods WHERE subdomain_name = '{subdomain[1]}';
                    """).fetchone()
                    if method:
                        # Get the current cells on the grid layer
                        sub_grid_cells = self.gutils.execute(f"""SELECT 
                                                                    g.domain_cell, 
                                                                    g.n_value, 
                                                                    g.elevation, 
                                                                    ST_AsText(ST_Centroid(GeomFromGPB(g.geom)))
                                                                FROM 
                                                                    grid g
                                                                WHERE 
                                                                    g.domain_fid = {method[0]};""").fetchall()
                        # Get the connectivity cells
                        if method[1]:
                            subdomain_connectivities = self.gutils.execute(f"""
                                                                        SELECT 
                                                                           fid_subdomain_1,
                                                                           fid_subdomain_2,
                                                                           fid_subdomain_3,
                                                                           fid_subdomain_4,
                                                                           fid_subdomain_5,
                                                                           fid_subdomain_6,
                                                                           fid_subdomain_7,
                                                                           fid_subdomain_8,
                                                                           fid_subdomain_9
                                                                        FROM 
                                                                           md_method_{method[1]} WHERE fid = {method[2]};
                                                       """).fetchall()
                            if subdomain_connectivities:
                                for connectivity in subdomain_connectivities:
                                    if connectivity[0] != 0:
                                        sub_con_cells = self.gutils.execute(f"""
                                                                SELECT c.down_domain_cell AS domain_cell, g.n_value, g.elevation, ST_AsText(ST_Centroid(GeomFromGPB(g.geom)))
                                                                FROM grid g
                                                                JOIN schema_md_connect_cells c ON g.domain_cell = c.up_domain_cell
                                                                WHERE g.domain_fid = {method[2]} AND c.down_domain_fid = {connectivity[0]} AND g.connectivity_fid != 'NULL'""").fetchall()
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
        # SELECT g.domain_cell, g.domain_fid, g.n_value, g.elevation, g.connectivity_fid
        # FROM grid g
        # WHERE g.domain_fid = 2
        #
        # UNION
        #
        # SELECT c.down_domain_cell AS domain_cell, 2 AS domain_fid, g.n_value, g.elevation, g.connectivity_fid
        # FROM grid g
        # JOIN schema_md_connect_cells c ON g.domain_cell = c.up_domain_cell
        # WHERE g.domain_fid = 1 AND c.down_domain_fid = 2;
        QApplication.restoreOverrideCursor()
