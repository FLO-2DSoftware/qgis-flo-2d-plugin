from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QFileDialog

from .ui_utils import load_ui
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

        self.sub1_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub1_le))
        self.sub2_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub2_le))
        self.sub3_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub3_le))
        self.sub4_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub4_le))
        self.sub5_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub5_le))
        self.sub6_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub6_le))
        self.sub7_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub7_le))
        self.sub8_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub8_le))
        self.sub9_tb.clicked.connect(lambda: self.select_subdomain_folder(self.sub9_le))

        self.ok_btn.clicked.connect(self.import_global_domain)
        self.cancel_btn.clicked.connect(self.close_dlg)

    def select_subdomain_folder(self, domain_le):
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
        domain_le.setText(domain_dir)

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

        s = QSettings()
        s.setValue(f"FLO-2D/Subdomain 1", sub1_path)
        s.setValue(f"FLO-2D/Subdomain 2", sub2_path)
        s.setValue(f"FLO-2D/Subdomain 3", sub3_path)
        s.setValue(f"FLO-2D/Subdomain 4", sub4_path)
        s.setValue(f"FLO-2D/Subdomain 5", sub5_path)
        s.setValue(f"FLO-2D/Subdomain 6", sub6_path)
        s.setValue(f"FLO-2D/Subdomain 7", sub7_path)
        s.setValue(f"FLO-2D/Subdomain 8", sub8_path)
        s.setValue(f"FLO-2D/Subdomain 9", sub9_path)


