import os
import shutil
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from qgis._core import QgsProject

from flo2d.gui.ui_utils import load_ui
from flo2d.user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui("gpkg_backup")


class GpkgBackupDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, gutils):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.setupUi(self)
        self.iface = iface
        self.gutils = gutils
        self.uc = UserCommunication(iface, "FLO-2D")

        self.gpkg_path = None
        self.gpkg_dir = None
        self.gpkg_name = None

        self.populate_backup_name()

        self.create_backup_btn.clicked.connect(self.create_backup)
        self.cancel_btn.clicked.connect(self.close_dlg)

    def populate_backup_name(self):
        """
        Function to populate the backup geopackage name based on a timestamp
        """
        self.gpkg_path = self.gutils.get_gpkg_path()
        self.gpkg_dir = os.path.dirname(self.gpkg_path)
        self.gpkg_name = os.path.splitext(os.path.basename(self.gpkg_path))[0]

        timestamp = datetime.now().strftime("%m%d%Y-%H%M")
        gpkg_backup_name = f"{self.gpkg_name}_{timestamp}"

        self.gpkg_name_le.setText(gpkg_backup_name)

    def create_backup(self):
        """
        Function to create the backup geopackage
        """

        gpkg_backup_name = self.gpkg_name_le.text()
        gpkg_backup_path = os.path.join(self.gpkg_dir, f"{gpkg_backup_name}.gpkg")

        QApplication.setOverrideCursor(Qt.WaitCursor)

        # First update the current geopackage name to the backup name to create the backup correctly
        self.gutils.execute(f"UPDATE metadata SET value = '{gpkg_backup_name}' WHERE name = 'PROJ_NAME';")

        # Make a copy of the gpkg with the new name to the same location as the current gpkg
        shutil.copy2(self.gpkg_path, gpkg_backup_path)

        self.gutils.update_qgis_project(self.gpkg_path, gpkg_backup_path)

        # Rollback the name
        self.gutils.execute(f"UPDATE metadata SET value = '{self.gpkg_name}' WHERE name = 'PROJ_NAME';")

        QApplication.restoreOverrideCursor()

        self.uc.log_info(f"Geopackage backup was successfully created on {gpkg_backup_path}")
        self.uc.bar_info(f"Geopackage backup was successfully created on {gpkg_backup_path}")

        self.close_dlg()

    def close_dlg(self):
        """
        Function to close the geopackage backup dialog
        """
        self.close()

