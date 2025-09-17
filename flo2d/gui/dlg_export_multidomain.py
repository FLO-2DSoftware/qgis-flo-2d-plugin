import os
import shutil
import time
import traceback

try:
    import h5py
except ImportError:
    pass

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QFileDialog, QApplication, QCheckBox, QProgressDialog
from qgis.PyQt.QtCore import NULL

from .dlg_components import ComponentsDialog
from .ui_utils import load_ui
from ..flo2d_ie.flo2dgeopackage import Flo2dGeoPackage
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication, is_file_locked

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

        self.ok_btn.clicked.connect(self.export_selected_subdomains)
        self.cancel_btn.clicked.connect(self.close_dlg)

        self.export_method_cbo.currentIndexChanged.connect(self.block_export_selected_subdomains)

        self.select_dir_tb.clicked.connect(self.select_dir)

        self.populate_subdomains()

        self.select_all_chbox.stateChanged.connect(self.select_all_subdomains)

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

    def select_all_subdomains(self):
        """
        Selects or deselects all subdomain checkboxes based on the state of the 'Select All' checkbox.
        """
        select_all = self.select_all_chbox.isChecked()
        for i in range(1, 16):
            checkbox = self.findChild(QCheckBox, f"checkBox_{i}")
            if checkbox:
                checkbox.setChecked(select_all)

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
                    checkbox.setChecked(True)
        else:
            for i in range(1, 16):
                checkbox = self.findChild(QCheckBox, f"checkBox_{i}")  # Find checkbox by name
                if checkbox:
                    checkbox.setEnabled(True)
                    checkbox.setChecked(False)

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
        s = QSettings()
        QApplication.setOverrideCursor(Qt.WaitCursor)

        # Figure out the export method
        # 0 -> MULTIDOMAIN.DAT
        # 1 -> ONLY MULTIDOMAIN.DAT
        # 2 -> CADPTS.DAT
        # 3 -> ONLY CADPTS.DAT
        # 4 -> NO CONNECTIVITY
        export_method = self.export_method_cbo.currentIndex()

        export_subdomains = []

        # Subdomains that had the FID changed due to the maximum of 9 subdomains
        subdomains_fid_changed_msg = ""

        export_type = ""

        # Loop over checkboxes in order
        for i in range(1, 16):
            checkbox = self.findChild(QCheckBox, f"checkBox_{i}")  # Find checkbox by name
            if checkbox.isChecked() and checkbox.isVisible():
                export_subdomains.append(checkbox.text())

        if len(export_subdomains) == 0:
            QApplication.restoreOverrideCursor()
            self.uc.log_info(f"No subdomains were selected!")
            self.uc.bar_warn(f"No subdomains were selected!")
            return

        if export_method in [0, 2, 4]:

            sql = """SELECT name, value FROM cont;"""
            options = {o: v if v is not None else "" for o, v in self.f2g.execute(sql).fetchall()}
            export_calls = [
                "export_tolspatial",
                "export_inflow",
                # "export_tailings",
                # 'export_outrc',
                "export_chan",
                "export_xsec",
                "export_outflow",
                "export_rain",
                "export_raincell",
                "export_raincellraw",
                # "export_evapor",
                "export_infil",
                "export_hystruc",
                "export_bridge_xsec",
                "export_bridge_coeff_data",
                # "export_street",
                "export_arf",
                "export_mult",
                "export_sed",
                "export_levee",
                "export_fpxsec",
                # "export_breach",
                # "export_gutter",
                "export_fpfroude",
                "export_steep_slopen",
                "export_lid_volume",
                "export_swmminp",
                "export_swmmflo",
                "export_swmmflort",
                "export_swmmoutf",
                "export_swmmflodropbox",
                "export_sdclogging",
                # "export_wsurf",
                # "export_wstime",
                "export_shallowNSpatial",
                "export_mannings_n_topo",
                "export_cont_toler"
            ]

            # Add a dummy cell to the outflow cells to show the Outflow checkbox
            count = self.gutils.execute("SELECT COUNT(*) FROM outflow_cells;").fetchone()[0]
            dummy_added = False
            if count == 0:
                # Add a dummy row if the table is empty
                self.gutils.execute("INSERT INTO outflow_cells (fid) VALUES (1);")
                dummy_added = True

            dlg_components = ComponentsDialog(self.con, self.iface, self.lyrs, "out")

            dlg_components.data_rb.setVisible(True)
            dlg_components.hdf5_rb.setVisible(True)

            # True hdf5, False data
            user_preference = s.value("FLO-2D/quickRun")
            if user_preference == "hdf5":
                dlg_components.hdf5_rb.setChecked(True)
                dlg_components.data_rb.setChecked(False)
            elif user_preference == "data":
                dlg_components.hdf5_rb.setChecked(False)
                dlg_components.data_rb.setChecked(True)
            else:
                dlg_components.hdf5_rb.setChecked(True)
                dlg_components.data_rb.setChecked(False)

            QApplication.restoreOverrideCursor()

            ok = dlg_components.exec_()
            if ok:

                QApplication.setOverrideCursor(Qt.WaitCursor)
                s.setValue("FLO-2D/lastGdsDir", self.export_directory_le.text())

                if dlg_components.data_rb.isChecked():
                    export_type = "data"
                    s.setValue("FLO-2D/quickRun", "data")
                if dlg_components.hdf5_rb.isChecked():
                    export_type = "hdf5"
                    s.setValue("FLO-2D/quickRun", "hdf5")

                if "Channels" not in dlg_components.components:
                    export_calls.remove("export_chan")
                    export_calls.remove("export_xsec")

                if "Reduction Factors" not in dlg_components.components:
                    export_calls.remove("export_arf")

                # if "Streets" not in dlg_components.components:
                #     export_calls.remove("export_street")

                if "Outflow Elements" not in dlg_components.components:
                    export_calls.remove("export_outflow")

                if "Inflow Elements" not in dlg_components.components:
                    export_calls.remove("export_inflow")

                # if "Tailings" not in dlg_components.components:
                #     export_calls.remove("export_tailings")

                # if "Surface Water Rating Tables" not in dlg_components.components:
                #     export_calls.remove("export_outrc")

                if "Levees" not in dlg_components.components:
                    export_calls.remove("export_levee")

                if "Multiple Channels" not in dlg_components.components:
                    export_calls.remove("export_mult")

                # if "Breach" not in dlg_components.components:
                #     export_calls.remove("export_breach")

                # if "Gutters" not in dlg_components.components:
                #     export_calls.remove("export_gutter")

                if "Infiltration" not in dlg_components.components:
                    export_calls.remove("export_infil")

                if "Floodplain Cross Sections" not in dlg_components.components:
                    export_calls.remove("export_fpxsec")

                if "Mudflow and Sediment Transport" not in dlg_components.components:
                    export_calls.remove("export_sed")

                # if "Evaporation" not in dlg_components.components:
                #     export_calls.remove("export_evapor")

                if "Hydraulic  Structures" not in dlg_components.components:
                    export_calls.remove("export_hystruc")
                    export_calls.remove("export_bridge_xsec")
                    if "export_bridge_coeff_data" in export_calls:
                        export_calls.remove("export_bridge_coeff_data")
                else:
                    xsecs = self.gutils.execute("SELECT fid FROM struct WHERE icurvtable = 3").fetchone()
                    if not xsecs:
                        export_calls.remove("export_bridge_xsec")
                        if "export_bridge_coeff_data" in export_calls:
                            export_calls.remove("export_bridge_coeff_data")

                if "Rain" not in dlg_components.components:
                    export_calls.remove("export_rain")
                    if "export_raincell" in export_calls:
                        export_calls.remove("export_raincell")
                    if "export_raincellraw" in export_calls:
                        export_calls.remove("export_raincellraw")

                if "Storm Drain" not in dlg_components.components:
                    export_calls.remove("export_swmminp")
                    export_calls.remove("export_swmmflo")
                    export_calls.remove("export_swmmflort")
                    export_calls.remove("export_swmmoutf")
                    export_calls.remove("export_swmmflodropbox")
                    export_calls.remove("export_sdclogging")

                if "Spatial Shallow-n" not in dlg_components.components:
                    export_calls.remove("export_shallowNSpatial")

                if "Spatial Tolerance" not in dlg_components.components:
                    export_calls.remove("export_tolspatial")

                if "Spatial Froude" not in dlg_components.components:
                    export_calls.remove("export_fpfroude")

                if "Manning's n and Topo" not in dlg_components.components:
                    export_calls.remove("export_mannings_n_topo")

                if "Spatial Steep Slope-n" not in dlg_components.components:
                    export_calls.remove("export_steep_slopen")

                if "LID Volume" not in dlg_components.components:
                    export_calls.remove("export_lid_volume")

            else:
                return

        QApplication.processEvents()
        progDialog = QProgressDialog("Exporting subdomains...", None, 0, len(export_subdomains))
        progDialog.setModal(True)
        progDialog.setValue(0)
        progDialog.show()
        QApplication.processEvents()

        for j, subdomain_name in enumerate(export_subdomains, start=1):

            subdomains = self.gutils.execute(
                f"SELECT fid_method, subdomain_name FROM mult_domains_methods WHERE subdomain_name = '{subdomain_name}';").fetchone()

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

                if export_method in [0, 2, 4]:

                    if export_type == "data":
                        self.call_IO_methods_md_dat(export_calls, True, str(export_folder), subdomains[0])
                    if export_type == "hdf5":
                        output_hdf5 = os.path.join(str(export_folder), "Input.hdf5")
                        if is_file_locked(output_hdf5):
                            self.uc.bar_error(f"The file Input.hdf5 for subdomain {subdomain_name} is currently open or locked by another process!")
                            self.uc.log_info(f"The file Input.hdf5 for subdomain {subdomain_name} is currently open or locked by another process!")
                            continue
                        self.f2g = Flo2dGeoPackage(self.con, self.iface, parsed_format=Flo2dGeoPackage.FORMAT_HDF5)
                        self.f2g.set_parser(output_hdf5, get_cell_size=False)
                        self.f2g.parser.write_mode = "w"
                        self.call_IO_methods_md_hdf5(export_calls, True, subdomains[0])

                cadpts = os.path.join(str(export_folder), "CADPTS.DAT")
                multidomain = os.path.join(str(export_folder), "MULTIDOMAIN.DAT")

                cline = "{0: >9} {1: >14} {2: >14}\n"
                mdline_n = "N {0}\n"
                mdline_d = "D {0} {1}\n"

                # MULTIDOMAIN.DAT
                if export_method == 0:
                    connected_subdomains = downstream_domains[subdomains[0]]
                    if connected_subdomains:
                        if export_type == "data":
                            with open(multidomain, "w") as md:
                                for connected_subdomain in connected_subdomains:
                                    md.write(mdline_n.format(connected_subdomain))
                                    up_cell_qry = f"""SELECT grid_fid, domain_cell FROM schema_md_cells WHERE domain_fid = {subdomains[0]} and down_domain_fid = {connected_subdomain};"""
                                    for grid_fid, up_cell in self.gutils.execute(up_cell_qry).fetchall():
                                        down_cells_qry = f"""SELECT domain_cell FROM schema_md_cells WHERE domain_fid = {connected_subdomain} and grid_fid = {grid_fid};"""
                                        down_cells = self.gutils.execute(down_cells_qry).fetchall()
                                        if down_cells:
                                            md.write(mdline_d.format(str(up_cell), str(down_cells[0][0])))
                        if export_type == "hdf5":
                            self.f2g.parser.write_mode = "a"
                            multipledomain_group = self.f2g.parser.multipledomain_group
                            multipledomain_group.create_dataset('MULTIDOMAIN', [])
                            for connected_subdomain in connected_subdomains:
                                up_cell_qry = f"""SELECT grid_fid, domain_cell FROM schema_md_cells WHERE domain_fid = {subdomains[0]} and down_domain_fid = {connected_subdomain};"""
                                for grid_fid, up_cell in self.gutils.execute(up_cell_qry).fetchall():
                                    down_cells_qry = f"""SELECT domain_cell FROM schema_md_cells WHERE domain_fid = {connected_subdomain} and grid_fid = {grid_fid};"""
                                    down_cells = self.gutils.execute(down_cells_qry).fetchall()
                                    if down_cells:
                                        multipledomain_group.datasets["MULTIDOMAIN"].data.append(
                                            [connected_subdomain, up_cell, down_cells[0][0]])
                            self.f2g.parser.write_groups(multipledomain_group)

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

                # CADPTS_DSx.DAT
                elif export_method == 2:
                    sub_grid_cells = self.gutils.execute(f"""SELECT DISTINCT 
                                                                md.domain_cell, 
                                                                g.n_value, 
                                                                g.elevation,
                                                                ST_AsText(ST_Centroid(GeomFromGPB(g.geom)))
                                                             FROM 
                                                                grid g
                                                             JOIN 
                                                                schema_md_cells md ON g.fid = md.grid_fid
                                                             WHERE 
                                                                 md.domain_fid = {subdomains[0]};""").fetchall()

                    records = sorted(sub_grid_cells, key=lambda x: x[0])

                    if export_type == "data":
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

                    if export_type == "hdf5":
                        self.f2g.parser.write_mode = "a"
                        multipledomain_group = self.f2g.parser.multipledomain_group
                        multipledomain_group.create_dataset('CADPTS', [])
                        for row in records:
                            fid, _, _, geom = row
                            x, y = geom.strip("POINT()").split()
                            multipledomain_group.datasets["CADPTS"].data.append(
                                [float(fid), float(x), float(y)])
                        self.f2g.parser.write_groups(multipledomain_group)

                # ONLY CADPTS_DSx.DAT
                elif export_method == 3:
                    sub_grid_cells = self.gutils.execute(f"""SELECT DISTINCT 
                                                                                            md.domain_cell, 
                                                                                            g.n_value, 
                                                                                            g.elevation,
                                                                                            ST_AsText(ST_Centroid(GeomFromGPB(g.geom)))
                                                                                         FROM 
                                                                                            grid g
                                                                                         JOIN 
                                                                                            schema_md_cells md ON g.fid = md.grid_fid
                                                                                         WHERE 
                                                                                             md.domain_fid = {subdomains[0]};""").fetchall()

                    records = sorted(sub_grid_cells, key=lambda x: x[0])

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

                # Update progress dialog
                progDialog.setValue(j)
                QApplication.processEvents()

        # Remove the dummy cell on the outflow_cells
        if dummy_added:
            self.gutils.execute("DELETE FROM outflow_cells WHERE fid = 1;")

        if export_method in [2, 3]:
            subdomain_connectivities_names = self.gutils.execute(f"""
                                                               SELECT
                                                                   im.subdomain_name,
                                                                   im.subdomain_name_1, fid_subdomain_1,
                                                                   im.subdomain_name_2, fid_subdomain_2,
                                                                   im.subdomain_name_3, fid_subdomain_3,
                                                                   im.subdomain_name_4, fid_subdomain_4,
                                                                   im.subdomain_name_5, fid_subdomain_5,
                                                                   im.subdomain_name_6, fid_subdomain_6,
                                                                   im.subdomain_name_7, fid_subdomain_7,
                                                                   im.subdomain_name_8, fid_subdomain_8,
                                                                   im.subdomain_name_9, fid_subdomain_9
                                                               FROM
                                                                   mult_domains_con AS im;
                                                                           """).fetchall()
            if subdomain_connectivities_names:
                for subdomain_connectivity_name in subdomain_connectivities_names:
                    current_subdomain = subdomain_connectivity_name[0]
                    current_subdomain_folder = os.path.join(self.export_directory_le.text(),
                                                            current_subdomain)

                    # Collect all fid_subdomain_x values
                    fid_subdomains = [subdomain_connectivity_name[2 * i] for i in range(1, 10) if
                                      subdomain_connectivity_name[2 * i] not in (0, None, "NULL", "")]
                    fids_greater_than_9 = [fid for fid in fid_subdomains if fid > 9]

                    # Find available fids between 1 and 9
                    used_fids = set(fid_subdomains)
                    available_fids = [i for i in range(1, 10) if i not in used_fids]

                    # Create a mapping for fids greater than 9
                    fid_mapping = {}
                    for fid in fids_greater_than_9:
                        if available_fids:
                            new_fid = available_fids.pop(0)
                            fid_mapping[fid] = new_fid

                    for i in range(1, 10):
                        downstream_subdomains_folder = os.path.join(self.export_directory_le.text(),
                                                                    subdomain_connectivity_name[2 * i - 1])
                        fid_subdomain = subdomain_connectivity_name[2 * i]

                        # Remap fid_subdomain if it is greater than 9
                        if fid_subdomain in fid_mapping:
                            original_fid = fid_subdomain
                            fid_subdomain = fid_mapping[fid_subdomain]

                            adjustment_file_path = os.path.join(str(current_subdomain_folder), "qgis_multidomain_adjust.txt")
                            with open(adjustment_file_path, "a") as adjustment_file:
                                adjustment_file.write(
                                    f"{subdomain_connectivity_name[2 * i - 1]} ({original_fid}) -> {subdomain_connectivity_name[2 * i - 1]} ({fid_subdomain})\n")

                            msg = (
                                f"Subdomain '{current_subdomain}': The subdomain '{subdomain_connectivity_name[2 * i - 1]}' "
                                f"with FID {original_fid} has been renamed to FID {fid_subdomain}.\n"
                            )

                            subdomains_fid_changed_msg += msg

                        if not os.path.exists(downstream_subdomains_folder) or subdomain_connectivity_name[2 * i - 1] == "":
                            continue
                        else:
                            if export_type == "data":
                                shutil.copy2(os.path.join(str(downstream_subdomains_folder), "CADPTS.DAT"),
                                             os.path.join(str(current_subdomain_folder),
                                                          f"CADPTS_DS{fid_subdomain}.DAT"))
                            if export_type == "hdf5":
                                source_hdf5 = os.path.join(str(downstream_subdomains_folder), "Input.hdf5")
                                target_hdf5 = os.path.join(str(current_subdomain_folder), "Input.hdf5")
                                with h5py.File(source_hdf5, "r") as src:
                                    # Navigate to the dataset
                                    dataset_path = "Input/Multiple Domains/CADPTS"
                                    if dataset_path in src:
                                        with h5py.File(target_hdf5, "a") as dst:
                                            src.copy(dataset_path, dst,
                                                     name=f"Input/Multiple Domains/CADPTS_DS{fid_subdomain}")


                    # The strings list 'export_calls', contains the names of
                    # the methods in the class Flo2dGeoPackage to export (write) the
                    # FLO-2D .DAT files

                # finally:

                # if "export_tailings" in export_calls:
                #     MUD = self.gutils.get_cont_par("MUD")
                #     concentration_sql = """SELECT
                #                                     CASE WHEN COUNT(*) > 0 THEN True
                #                                          ELSE False
                #                                     END AS result
                #                                     FROM
                #                                         tailing_cells
                #                                     WHERE
                #                                         concentration <> 0 OR concentration IS NULL;"""
                #     cv = self.gutils.execute(concentration_sql).fetchone()[0]
                #     # TAILINGS.DAT and TAILINGS_CV.DAT
                #     if MUD == '1':
                #         # Export TAILINGS_CV.DAT
                #         if cv == 1:
                #             new_files_used = self.files_used.replace("TAILINGS.DAT\n", "TAILINGS_CV.DAT\n")
                #             self.files_used = new_files_used
                #     # TAILINGS_STACK_DEPTH.DAT
                #     elif MUD == '2':
                #         new_files_used = self.files_used.replace("TAILINGS.DAT\n", "TAILINGS_STACK_DEPTH.DAT\n")
                #         self.files_used = new_files_used
                #
                # if "export_swmmflo" in export_calls:
                #     self.f2d_widget.storm_drain_editor.export_storm_drain_INP_file()
                #
                # # Delete .DAT files the model will try to use if existing:
                # if "export_mult" in export_calls:
                #     if self.gutils.is_table_empty("simple_mult_cells"):
                #         new_files_used = self.files_used.replace("SIMPLE_MULT.DAT\n", "")
                #         self.files_used = new_files_used
                #         if os.path.isfile(outdir + r"\SIMPLE_MULT.DAT"):
                #             QApplication.setOverrideCursor(Qt.ArrowCursor)
                #             if self.uc.question(
                #                     "There are no simple multiple channel cells in the project but\n"
                #                     + "there is a SIMPLE_MULT.DAT file in the directory.\n"
                #                     + "If the file is not deleted it will be used by the model.\n\n"
                #                     + "Delete SIMPLE_MULT.DAT?"
                #             ):
                #                 os.remove(outdir + r"\SIMPLE_MULT.DAT")
                #             QApplication.restoreOverrideCursor()
                #     if self.gutils.is_table_empty("mult_cells"):
                #         new_files_used = self.files_used.replace("\nMULT.DAT\n", "\n")
                #         self.files_used = new_files_used
                #         if os.path.isfile(outdir + r"\MULT.DAT"):
                #             QApplication.setOverrideCursor(Qt.ArrowCursor)
                #             if self.uc.question(
                #                     "There are no multiple channel cells in the project but\n"
                #                     + "there is a MULT.DAT file in the directory.\n"
                #                     + "If the file is not deleted it will be used by the model.\n\n"
                #                     + "Delete MULT.DAT?"
                #             ):
                #                 os.remove(outdir + r"\MULT.DAT")
                #             QApplication.restoreOverrideCursor()

                # if self.files_used != "":
                #     QApplication.setOverrideCursor(Qt.ArrowCursor)
                #     info = "Files exported to\n" + str(export_folder) + "\n\n" + self.files_used
                #     self.uc.show_info(info)
                #     QApplication.restoreOverrideCursor()
                #
                # if self.f2g.export_messages != "":
                #     QApplication.setOverrideCursor(Qt.ArrowCursor)
                #     info = "WARNINGS 100424.0613:\n\n" + self.f2g.export_messages
                #     self.uc.show_info(info)
                #     QApplication.restoreOverrideCursor()

                # self.uc.bar_info("FLO-2D model exported to " + str(export_folder), dur=3)

        QApplication.restoreOverrideCursor()
        if subdomains_fid_changed_msg != "":
            header_msg = (
                "Some subdomain FIDs exceed the maximum allowed value of 9 in the FLO-2D engine. "
                "To comply with this restriction, the following subdomains have been updated. "
                "A file named qgis_multidomain_adjust.txt has been saved in the project directory to document these adjustments.\n\n"
            )
            self.uc.show_info(header_msg + subdomains_fid_changed_msg)
            self.uc.log_info(header_msg + subdomains_fid_changed_msg)
        self.uc.log_info(f"Subdomains exported correctly!")
        self.uc.bar_info(f"Subdomains exported correctly!")
        self.close_dlg()
        QApplication.restoreOverrideCursor()

    def call_IO_methods_md_hdf5(self, calls, debug, subdomain):

        progDialog = QProgressDialog("Exporting to HDF5...", None, 0, len(calls))
        progDialog.setModal(True)
        progDialog.setValue(0)
        progDialog.show()
        i = 0

        for call in calls:
            i += 1
            progDialog.setValue(i)
            progDialog.setLabelText(call)
            QApplication.processEvents()
            method = getattr(self.f2g, call)

            try:
                if method(subdomain=subdomain):
                    self.f2g.parser.write_mode = "a"
            except Exception as e:
                if debug is True:
                    self.uc.log_info(traceback.format_exc())
                else:
                    raise

        self.f2g.parser.write_mode = "w"

    def call_IO_methods_md_dat(self, calls, debug, *args):

        self.files_used = ""
        self.files_not_used = ""

        if calls[0] == "export_cont_toler":
            self.files_used = "CONT.DAT\n"

        for call in calls:
            # if call == "export_bridge_xsec":
            #     dat = "BRIDGE_XSEC.DAT"
            # elif call == "export_bridge_coeff_data":
            #     dat = "BRIDGE_COEFF_DATA.DAT"
            # elif call == "import_hystruc_bridge_xs":
            #     dat = "BRIDGE_XSEC.DAT"
            # elif call == "import_swmminp":
            #     dat = "SWMM.INP"
            if call == 'export_steep_slopen':
                dat = "STEEP_SLOPEN.DAT"
            # elif call == 'import_steep_slopen_md':
            #     dat = "STEEP_SLOPEN.DAT"
            elif call == 'export_lid_volume':
                dat = "LID_VOLUME.DAT"
            # elif call == 'import_lid_volume_md':
            #     dat = "LID_VOLUME.DAT"
            else:
                dat = call[:-3].split("_")[-1].upper() + ".DAT"
            # if call.startswith("import"):
            #     if self.f2g.parser.dat_files[dat] is None:
            #         if dat == "MULT.DAT":
            #             if self.f2g.parser.dat_files["SIMPLE_MULT.DAT"] is None:
            #                 self.uc.log_info('Files required for "{0}" not found. Action skipped!'.format(call))
            #                 self.files_not_used += dat + "\n"
            #                 continue
            #             else:
            #                 self.files_used += "SIMPLE_MULT.DAT\n"
            #                 pass
            #         else:
            #             self.uc.log_info('Files required for "{0}" not found. Action skipped!'.format(call))
            #             if dat not in ["WSURF.DAT", "WSTIME.DAT"]:
            #                 self.files_not_used += dat + "\n"
            #             continue
            #     else:
            #         if dat == "MULT.DAT":
            #             self.files_used += dat + " and/or SIMPLE_MULT.DAT" + "\n"
            #             pass
            #         elif os.path.getsize(os.path.join(last_dir, dat)) > 0:
            #             self.files_used += dat + "\n"
            #             if dat == "CHAN.DAT":
            #                 self.files_used += "CHANBANK.DAT" + "\n"
            #             pass
            #         else:
            #             self.files_not_used += dat + "\n"
            #             continue

            try:
                start_time = time.time()

                method = getattr(self.f2g, call)

                if method(*args):
                    if call.startswith("export"):
                        self.files_used += dat + "\n"
                        # if dat == "CHAN.DAT":
                        #     self.files_used += "CHANBANK.DAT" + "\n"
                        # if dat == "SWMMFLO.DAT":
                        #     self.files_used += "SWMM.INP" + "\n"
                        if dat == "TOPO.DAT":
                            self.files_used += "MANNINGS_N.DAT" + "\n"
                        # if dat == "MULT.DAT":
                        #     self.files_used += "SIMPLE_MULT.DAT" + "\n"
                        pass

                self.uc.log_info('{0:.3f} seconds => "{1}"'.format(time.time() - start_time, call))

            except Exception as e:
                if debug is True:
                    self.uc.log_info(traceback.format_exc())
                else:
                    raise

        QApplication.restoreOverrideCursor()