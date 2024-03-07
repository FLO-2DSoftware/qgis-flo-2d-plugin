from PyQt5.QtWidgets import QVBoxLayout, QWidget
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from swmmio import find_network_trace, build_profile_plot, add_hgl_plot, add_node_labels_plot, add_link_labels_plot

from flo2d.gui.ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("sd_profile_view")


class SDProfileView(qtBaseClass, uiDialog):
    def __init__(self, parent=None):
        super(SDProfileView, self).__init__(parent)

        self.canvas = FigureCanvas(plt.figure())
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.canvas)
        self.setLayout(self.layout)

        # Keep a reference to the axis to avoid garbage collection
        self.ax = self.canvas.figure.add_subplot(1,1,1)


    def plot_data(self, model, start_node, end_node):
        # Clear canvas
        self.ax.clear()

        path_selection = find_network_trace(model, start_node, end_node)
        profile_config = build_profile_plot(self.ax, model, path_selection)
        # add_hgl_plot(self.ax, profile_config, depth=None, label="No Control")
        # add_hgl_plot(self.ax, profile_config, depth=None, color='green', label="With Control")
        add_node_labels_plot(self.ax, model, profile_config)
        add_link_labels_plot(self.ax, model, profile_config)
        leg = self.ax.legend()
        # self.ax.grid('xy')
        self.ax.grid(False)
        self.ax.get_xaxis().set_ticklabels([])

        self.canvas.draw()


# # FLO-2D Preprocessor tools for QGIS
# # Copyright © 2021 Lutra Consulting for FLO-2D
# from PyQt5.QtWidgets import QVBoxLayout
# from swmmio import find_network_trace, build_profile_plot, add_hgl_plot, add_node_labels_plot, add_link_labels_plot
#
# # This program is free software; you can redistribute it and/or
# # modify it under the terms of the GNU General Public License
# # as published by the Free Software Foundation; either version 2
# # of the License, or (at your option) any later version
#
# from .ui_utils import load_ui
# from ..geopackage_utils import GeoPackageUtils
# import matplotlib.pyplot as plt
# from matplotlib.figure import Figure
# from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
# from ..user_communication import UserCommunication
#
#
# uiDialog, qtBaseClass = load_ui("sd_profile_view")
#
#
# class SDProfileView(qtBaseClass, uiDialog):
#     def __init__(self, con, iface):
#         qtBaseClass.__init__(self)
#         uiDialog.__init__(self)
#         self.iface = iface
#         self.con = con
#         self.setupUi()
#         self.gutils = GeoPackageUtils(con, iface)
#         self.uc = UserCommunication(iface, "FLO-2D")
#
#     def setupUi(self):
#         self.setWindowTitle("Storm Drain Profile View")
#
#         # Setup layout
#         self.layout = QVBoxLayout(self)
#
#         # Add Matplotlib canvas
#         self.figure = Figure()
#         self.canvas = FigureCanvas(self.figure)
#         self.layout.addWidget(self.canvas)
#
#         # Add a button to close the dialog
#         # self.close_button = QPushButton("Close")
#         # self.close_button.clicked.connect(self.close)
#         # self.layout.addWidget(self.close_button)
#
#         # Plot data
#         # self.plot_data()
#
#     def plot_data(self, model, start_node, end_node):
#
#         fig = plt.figure(figsize=(11, 9))
#         fig.suptitle(f"{start_node} - {end_node}")
#         ax = fig.add_subplot(1, 1, 1)
#         path_selection = find_network_trace(model, 'J1', 'J8')
#         profile_config = build_profile_plot(ax, model, path_selection)
#         # add_hgl_plot(ax, profile_config, depth=None, label="No Control")
#         # add_hgl_plot(ax, profile_config, depth=None, color='green', label="With Control")
#         add_node_labels_plot(ax, model, profile_config)
#         add_link_labels_plot(ax, model, profile_config)
#         leg = ax.legend()
#         ax.grid('xy')
#         ax.get_xaxis().set_ticklabels([])
#
#         fig.tight_layout()
#         fig.savefig(r"D:/FLO-2D/FLO-2D Plugin/_STORMDRAIN/PYSWMM/profiles2.png")
#         plt.close()
#
#         # Refresh canvas
#         self.canvas.draw()
