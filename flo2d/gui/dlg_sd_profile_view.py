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
        self.layout.setObjectName("Storm Drain View")
        self.setLayout(self.layout)

        # Keep a reference to the axis to avoid garbage collection
        self.ax = self.canvas.figure.add_subplot(1, 1, 1)
        self.ax.spines[['right', 'top']].set_visible(False)

    def plot_profile(self, model, path_selection, depths):
        """
        Function to plot the profile plot
        """
        # Clear canvas
        self.ax.clear()
        profile_config = build_profile_plot(self.ax, model, path_selection)
        # if depths:
        add_hgl_plot(self.ax, profile_config, depth=depths)
        add_node_labels_plot(self.ax, model, profile_config)
        add_link_labels_plot(self.ax, model, profile_config)
        self.ax.legend()
        self.ax.grid('xy')
        self.ax.grid(False)
        self.ax.set_xlabel("Length")
        self.ax.set_ylabel("Elevation")

        self.canvas.draw()


