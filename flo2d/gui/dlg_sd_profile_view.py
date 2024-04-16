from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib.pyplot as plt


from flo2d.gui.ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("sd_profile_view")


class SDProfileView(qtBaseClass, uiDialog):
    def __init__(self, gutils, parent=None):
        super(SDProfileView, self).__init__(parent)

        self.gutils = gutils
        self.canvas = FigureCanvas(plt.figure())
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.canvas)
        self.layout.addWidget(self.toolbar)
        self.layout.setObjectName("Storm Drain View")
        self.setWindowTitle("Storm Drain Profile View")
        self.setLayout(self.layout)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        self.ax = self.canvas.figure.add_subplot(1, 1, 1)
        self.ax.spines[['right', 'top']].set_visible(False)

        self.canvas.mpl_connect('scroll_event', self.on_scroll)

    def on_scroll(self, event):
        """
        Zoom function triggered by mouse wheel event
        """
        cur_xlim = self.ax.get_xlim()
        cur_ylim = self.ax.get_ylim()
        cur_xrange = (cur_xlim[1] - cur_xlim[0]) * .5
        cur_yrange = (cur_ylim[1] - cur_ylim[0]) * .5
        xdata = event.xdata
        ydata = event.ydata
        if event.button == 'up':
            # zoom in
            scale_factor = 1 / 2
        elif event.button == 'down':
            # zoom out
            scale_factor = 2
        else:
            scale_factor = 1
        self.ax.set_xlim([xdata - cur_xrange * scale_factor,
                     xdata + cur_xrange * scale_factor])
        self.ax.set_ylim([ydata - cur_yrange * scale_factor,
                     ydata + cur_yrange * scale_factor])
        plt.draw()

    def plot_profile(self, swmmio, model, path_selection, max_depth, ave_depth):
        """
        Function to plot the profile plot
        """
        # Clear canvas
        self.ax.clear()
        profile_config = swmmio.build_profile_plot(self.ax, model, path_selection)
        swmmio.add_hgl_plot(self.ax, profile_config, depth=max_depth, color='red', label="Maximum Depth")
        swmmio.add_hgl_plot(self.ax, profile_config, depth=ave_depth, label="Average Depth")
        swmmio.add_node_labels_plot(self.ax, model, profile_config)
        swmmio.add_link_labels_plot(self.ax, model, profile_config)
        self.ax.legend(loc='best')
        self.ax.grid('xy')
        self.ax.grid(False)

        units = "m" if self.gutils.get_cont_par("METRIC") == "1" else "ft"

        self.ax.set_xlabel(f"Length ({units})")
        self.ax.set_ylabel(f"Elevation ({units})")

        self.canvas.draw()

