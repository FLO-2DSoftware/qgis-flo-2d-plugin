from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib import patches
import numpy as np
from PyQt5.QtWidgets import QDialog, QVBoxLayout
from qgis._core import QgsTemporalController, QgsTemporalNavigationObject, QgsMessageLog
from qgis.core import QgsProject, QgsDateTimeRange
from PyQt5.QtCore import QDateTime, Qt


class SDAnimator(QDialog):
    def __init__(self, iface, existing_nodes_dict, rpt_file, units, manhole_diameter, parent=None):
        super().__init__(parent)

        self.iface = iface
        self.existing_nodes_dict = existing_nodes_dict
        self.rpt_file = rpt_file
        self.units = units
        self.manhole_diameter = manhole_diameter

        self.vertical_layout = QVBoxLayout()
        self.canvas = FigureCanvas(Figure())
        self.vertical_layout.addWidget(self.canvas)
        self.setLayout(self.vertical_layout)

        self.setGeometry(0, 0, 800, 600)
        self.setWindowTitle("FLO-2D Storm Drain Profile Animator")

        self.ax = self.canvas.figure.add_subplot(111)
        self.line = None
        self.counter_label = None

        self.nodes_array = None
        self.nodes_ts = []
        self.nodes_qdatetime = []
        self.nodes_distances_anim = []

        self.setup_data()
        self.plot()
        self.init_line()
        self.setup_temporal_controller()

    def setup_data(self):
        nodes_data = []
        self.nodes_ts = []
        self.nodes_qdatetime = []
        NodeTSSummary = False
        i = 0
        for node in self.existing_nodes_dict.keys():
            node_data = []
            with open(self.rpt_file, "r") as f:
                for line in f:
                    if (f"<<< Node {node} >>>") in line:
                        NodeTSSummary = True
                        for _ in range(4):
                            next(f)
                        continue
                    if NodeTSSummary:
                        if len(line.split()) != 6:
                            NodeTSSummary = False
                        else:
                            NodeTSData = line.split()
                            node_data.append(float(NodeTSData[5]))
                            if i == 0:
                                ts_str = NodeTSData[0] + " " + NodeTSData[1]
                                self.nodes_ts.append(ts_str)
                                dt = QDateTime.fromString(ts_str, "MMM-dd-yyyy HH:mm:ss")
                                dt.setTimeSpec(Qt.UTC)
                                self.nodes_qdatetime.append(dt)
            i += 1
            nodes_data.append(node_data)
        self.nodes_array = np.array(nodes_data)

    def setup_temporal_controller(self):
        self.temporal_controller = self.iface.mapCanvas().temporalController()
        if hasattr(QgsTemporalNavigationObject.NavigationMode, "Animated"):
            self.temporal_controller.setNavigationMode(QgsTemporalNavigationObject.NavigationMode.Animated)
        self.temporal_controller.updateTemporalRange.connect(self.handle_time_change)

        # Set temporal extent from data range
        if self.nodes_qdatetime:
            start_time = self.nodes_qdatetime[0]
            end_time = self.nodes_qdatetime[-1]
            self.temporal_controller.setTemporalExtents(QgsDateTimeRange(start_time, end_time))
            self.handle_time_change(QgsDateTimeRange(start_time, start_time))


    def handle_time_change(self, time_range):
        QgsMessageLog.logMessage(f"[DEBUG] handle_time_change")
        current_time = time_range.begin()
        for idx, qdt in enumerate(self.nodes_qdatetime):
            if abs(qdt.msecsTo(current_time)) < 1000:
                self.update_frame_by_index(idx)
                return
        QgsMessageLog.logMessage(f"[DEBUG] No match found for time: {current_time.toString(Qt.ISODate)}")

    def update_frame_by_index(self, idx):
        self.line.set_data(np.array(self.nodes_distances_anim), self.nodes_array[:, idx])
        if self.counter_label:
            self.counter_label.get_texts()[0].set_text(f"HGL | {self.nodes_ts[idx]}")
        if self.base_title:
            self.ax.set_title(f"{self.base_title} | {self.nodes_ts[idx]}")
        self.canvas.draw_idle()

    def init_line(self):
        self.line, = self.ax.plot([], [], label="HGL")
        self.line.set_color('blue')
        self.counter_label = self.ax.legend([self.line], ["HGL"], loc="upper right", facecolor='white', framealpha=1)

    def plot(self):
        units = self.units
        manhole_diameter = self.manhole_diameter
        distance_acc_curr = 0
        distance_acc_prev = 0
        x_secondary_axis_labels = []

        for i in range(len(self.existing_nodes_dict)):
            if i != 0:
                distance_acc_prev += list(self.existing_nodes_dict.values())[i - 1][3]
                mh1_x = distance_acc_prev
                mh1_y_min = list(self.existing_nodes_dict.values())[i - 1][1] + \
                            list(self.existing_nodes_dict.values())[i][5]
                mh1_y_max = list(self.existing_nodes_dict.values())[i - 1][1] + \
                            list(self.existing_nodes_dict.values())[i][4] + list(self.existing_nodes_dict.values())[i][
                                5]
                distance_acc_curr += list(self.existing_nodes_dict.values())[i][3]
                mh2_x = distance_acc_curr
                mh2_y_min = list(self.existing_nodes_dict.values())[i][1] + list(self.existing_nodes_dict.values())[i][
                    6]
                mh2_y_max = list(self.existing_nodes_dict.values())[i][1] + list(self.existing_nodes_dict.values())[i][
                    4] + list(self.existing_nodes_dict.values())[i][6]
                coord = [[mh1_x, mh1_y_min], [mh2_x, mh2_y_min], [mh2_x, mh2_y_max], [mh1_x, mh1_y_max]]
                self.ax.add_patch(patches.Polygon(coord, linewidth=1, edgecolor='black', facecolor='white', zorder=1))
            x_secondary_axis_labels.append([list(self.existing_nodes_dict.keys())[i], distance_acc_curr])
            self.nodes_distances_anim.append(distance_acc_curr)

        distance_acc = 0
        invert_elevs = []
        max_depths = []
        for key, value in self.existing_nodes_dict.items():
            invert_elev = value[1]
            max_depth = value[2]
            length = value[3]
            invert_elevs.append(invert_elev)
            max_depths.append(max_depth)
            distance_acc += length
            rect = patches.Rectangle((distance_acc - (manhole_diameter / 2), invert_elev), manhole_diameter, max_depth,
                                     linewidth=1.5, edgecolor='black', facecolor='white', zorder=2)
            self.ax.add_patch(rect)

        secax = self.ax.secondary_xaxis('top')
        secax.set_xticks([d for _, d in x_secondary_axis_labels])
        secax.set_xticklabels([name for name, _ in x_secondary_axis_labels], rotation=90, ha='center', fontsize=8)

        max_invert_elev_idx = invert_elevs.index(max(invert_elevs))
        max_depth_idx = max_depths.index(max(max_depths))
        max_y = max(max_depths[max_depth_idx] + invert_elevs[max_depth_idx],
                    invert_elevs[max_invert_elev_idx] + max_depths[max_invert_elev_idx])

        self.ax.set_xlim(- (2 * manhole_diameter), distance_acc + (2 * manhole_diameter))
        self.ax.set_ylim(min(invert_elevs) - manhole_diameter, max_y + (1.5 * manhole_diameter))
        self.base_title = f'{list(self.existing_nodes_dict.keys())[0]} to {list(self.existing_nodes_dict.keys())[-1]}'
        self.ax.set_title(self.base_title)
        self.ax.set_xlabel(f"Distance ({units})")
        self.ax.set_ylabel(f"Elevation ({units})")

        self.canvas.figure.tight_layout()
        self.canvas.draw()