import os
import re

from PyQt5.QtCore import QSettings
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

        self.lbl_cb = {
            self.label_1: self.sub1_cb,
            self.label_2: self.sub2_cb,
            self.label_3: self.sub3_cb,
            self.label_4: self.sub4_cb,
            self.label_5: self.sub5_cb,
            self.label_6: self.sub6_cb,
            self.label_7: self.sub7_cb,
            self.label_8: self.sub8_cb,
            self.label_9: self.sub9_cb,
        }

        self.subdomains_connectivity_cbos = {
            self.ds1_file_cbo: self.sub1_cbo,
            self.ds2_file_cbo: self.sub2_cbo,
            self.ds3_file_cbo: self.sub3_cbo,
            self.ds4_file_cbo: self.sub4_cbo,
            self.ds5_file_cbo: self.sub5_cbo,
            self.ds6_file_cbo: self.sub6_cbo,
            self.ds7_file_cbo: self.sub7_cbo,
            self.ds8_file_cbo: self.sub8_cbo,
            self.ds9_file_cbo: self.sub9_cbo,
        }

        self.populate_current_subdomains()

        self.cancel_btn.clicked.connect(self.close_dlg)
        self.ok_btn.clicked.connect(self.save_connectivity)

        self.current_subdomain_cbo.currentIndexChanged.connect(self.repopulate_cbos)

        self.ds1_file_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.ds2_file_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.ds3_file_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.ds4_file_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.ds5_file_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.ds6_file_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.ds7_file_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.ds8_file_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.ds9_file_cbo.currentIndexChanged.connect(self.save_cbo_data)

        self.sub1_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.sub2_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.sub3_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.sub4_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.sub5_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.sub6_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.sub7_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.sub8_cbo.currentIndexChanged.connect(self.save_cbo_data)
        self.sub9_cbo.currentIndexChanged.connect(self.save_cbo_data)

    def fill_cbo_data(self):
        """
        Function to fill the combo boxes with data from the 'md_method_1' table in the GeoPackage.
        """
        current_subdomain = self.current_subdomain_cbo.currentText()
        selected_data = self.gutils.execute(
            f"SELECT * FROM md_method_1 WHERE subdomain_name = ?;", (current_subdomain,)
        ).fetchone()

        if selected_data:
            for i in range(1, 10):  # Loop through subdomains 1 to 9
                subdomain_name_index = 3 + (i - 1) * 4  # Get index for subdomain name
                ds_file_index = subdomain_name_index + 1  # Get index for ds_file

                subdomain_name = selected_data[subdomain_name_index] if selected_data[subdomain_name_index] else ""
                ds_file = selected_data[ds_file_index] if selected_data[ds_file_index] else ""

                sub_cbo = getattr(self, f"sub{i}_cbo", None)
                ds_cbo = getattr(self, f"ds{i}_file_cbo", None)

                if sub_cbo:
                    self.uc.log_info(str(subdomain_name))
                    sub_cbo.setCurrentIndex(sub_cbo.findText(subdomain_name))
                if ds_cbo:
                    self.uc.log_info(str(ds_file))
                    ds_cbo.setCurrentIndex(ds_cbo.findText(ds_file))

    def save_cbo_data(self):
        """
        Function to save the connections defined on the cbos to the geopackage.
        """
        current_subdomain = self.current_subdomain_cbo.currentText()

        # Get the selected fid for the current subdomain
        selected_fid = self.gutils.execute(
            "SELECT fid FROM md_method_1 WHERE subdomain_name = ?", (current_subdomain,)
        ).fetchone()

        if not selected_fid:
            return

        selected_fid = selected_fid[0]

        # Prepare data for update
        update_data = {}

        for i in range(1, 10):  # Loop through 1 to 9 (matching subdomain fields)
            subdomain_cbo = getattr(self, f"sub{i}_cbo").currentText()
            ds_file_cbo = getattr(self, f"ds{i}_file_cbo").currentText()

            if subdomain_cbo:
                fid_query = self.gutils.execute(
                    "SELECT fid FROM mult_domains_methods WHERE subdomain_name = ?", (subdomain_cbo,)
                ).fetchone()
                fid_value = fid_query[0] if fid_query else "NULL"
            else:
                fid_value = "NULL"

            update_data[f"fid_subdomain_{i}"] = fid_value
            update_data[f"subdomain_name_{i}"] = subdomain_cbo
            update_data[f"ds_file_{i}"] = ds_file_cbo

        # Construct the SQL UPDATE query dynamically
        set_clause = ", ".join([f"{col} = ?" for col in update_data.keys()])
        values = list(update_data.values()) + [selected_fid]

        sql_query = f"UPDATE md_method_1 SET {set_clause} WHERE fid = ?"

        # Execute update query
        self.gutils.execute(sql_query, values)

    def repopulate_cbos(self):
        """
        Function to repopulate cbos
        """
        self.blockSignals(True)
        self.populate_subdomains()
        self.populate_ds_cbos()
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
        self.populate_ds_cbos()
        self.fill_cbo_data()
        self.hide_cbos()

    def populate_subdomains(self):
        """
        Function to populate the subdomains
        """
        current_subdomain = self.current_subdomain_cbo.currentText()
        connect_subdomains = list(self.subdomains_connectivity_cbos.values())
        subdomain_names = self.gutils.execute(f"""SELECT subdomain_name FROM mult_domains_methods WHERE NOT subdomain_name = '{current_subdomain}';""").fetchall()
        if subdomain_names:
            for connect_subdomain in connect_subdomains:
                connect_subdomain.clear()
                connect_subdomain.addItems([s[0] for s in subdomain_names])
                connect_subdomain.setCurrentIndex(-1)

    def populate_ds_cbos(self):
        """
        This function populates the ds files
        """
        current_subdomain = self.current_subdomain_cbo.currentText()
        subdomain_path = self.gutils.execute(f"""SELECT subdomain_path FROM mult_domains_methods WHERE subdomain_name = '{current_subdomain}';""").fetchone()
        if subdomain_path:
            files = os.listdir(subdomain_path[0])

            cadpts_files = []
            for f in files:
                if f.startswith("CADPTS_DS"):
                    cadpts_files.append(f)

            connect_ds = list(self.subdomains_connectivity_cbos.keys())
            for ds in connect_ds:
                ds.clear()
                ds.addItems(cadpts_files)
                ds.setCurrentIndex(-1)

    def hide_cbos(self):
        """
        This function hides the cbos that do not contain information related to the CADPTS_DS
        """
        lbls = list(self.lbl_cb.keys())
        cbs = list(self.lbl_cb.values())
        # Number of DS files
        n_ds = self.ds1_file_cbo.count()
        i = 0
        for ds_cbo, sub_cbo in self.subdomains_connectivity_cbos.items():
            if i >= n_ds:
                ds_cbo.setVisible(False)
                sub_cbo.setVisible(False)
                lbls[i].setVisible(False)
                cbs[i].setVisible(False)
            else:
                ds_cbo.setVisible(True)
                sub_cbo.setVisible(True)
                lbls[i].setVisible(True)
                cbs[i].setVisible(True)
            i += 1

    def save_connectivity(self):
        """Function to save the connectivity data into FLO-2D Settings"""

        # Adjust the UPS-DOWNS
        subdomains = self.gutils.execute(f"""SELECT subdomain_name FROM md_method_1;""").fetchall()
        if subdomains:
            for subdomain in subdomains:

                selected_data = self.gutils.execute(
                    "SELECT * FROM md_method_1 WHERE subdomain_name = ?;", (subdomain[0],)
                ).fetchone()

                if selected_data:
                    update_query = """
                        UPDATE md_method_1 
                        SET subdomain_name_{i} = ?, ds_file_{i} = ?, ups_downs_{i} = ?
                        WHERE subdomain_name = ?;
                    """

                    for i in range(1, 10):  # Loop through subdomains 1 to 9
                        subdomain_name_index = 3 + (i - 1) * 4
                        ds_file_index = subdomain_name_index + 1
                        ups_downs_index = subdomain_name_index + 2  # ups_downs is 2 columns after subdomain_name_x

                        subdomain_name = selected_data[subdomain_name_index]
                        ds_file = selected_data[ds_file_index]

                        ups_downs_value = ""

                        if subdomain_name and ds_file:  # Both exist, extract the correct 'x' from ds_file_x
                            match = re.search(r'CADPTS_DS(\d+)\.DAT', ds_file)
                            if match:
                                ds_number = match.group(1)  # Extract x from CADPTS_DSx.DAT
                                ups_downs_value = f"Ups-Dows-Connectivity_DS{ds_number}.OUT"
                            else:
                                # If the ds_file_x format is incorrect, reset everything
                                subdomain_name = ""
                                ds_file = ""
                                ups_downs_value = ""

                        else:  # Either is missing, reset subdomain_name_x and ds_file_x
                            subdomain_name = ""
                            ds_file = ""

                        self.uc.log_info(str([subdomain_name, ds_file, ups_downs_value, subdomain[0]]))
                        # Execute the update query
                        self.gutils.execute(
                            update_query.format(i=i),
                            (subdomain_name, ds_file, ups_downs_value, subdomain[0]),
                        )

        self.uc.log_info("Connectivity saved!")
        self.uc.bar_info("Connectivity saved!")

        self.close_dlg()

    def blockSignals(self, true_false):
        """
        Function to block cbo signals
        """
        for ds_cbo, sub_cbo in self.subdomains_connectivity_cbos.items():
            ds_cbo.blockSignals(true_false)
            sub_cbo.blockSignals(true_false)

    def close_dlg(self):
        """
        Function to close the dialog
        """
        self.close()