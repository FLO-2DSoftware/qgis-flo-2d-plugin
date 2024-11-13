from matplotlib.animation import FuncAnimation
import mpl_toolkits.axes_grid1
import matplotlib.widgets
import numpy as np
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDialog, QVBoxLayout
from matplotlib import patches
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

# existing_nodes_dict = {'J1-37-30-31': [17430, 1393.99, 17.0, 0, 0, 0, 0], 'I5-36-30-30': [17432, 1391.79, 18.0, 72.507, 5.0, 0.0, 0.0], 'J1-36-30-32-A': [17446, 1388.98, 19.0, 420.175, 7.0, 0.0, 0.0], 'J1-36-30-32-B': [17449, 1388.81, 19.0, 88.308, 7.0, 0.0, 0.0], 'I5-36-30-32': [17452, 1388.69, 19.0, 75.573, 7.0, 0.0, 0.0], 'J1-36-30-27-A': [17454, 1388.57, 19.0, 61.506, 7.0, 0.0, 0.0], 'J1-36-30-27-B': [17463, 1388.07, 19.0, 266.526, 7.0, 0.0, 0.0], 'J1-36-30-27-C': [17472, 1387.5, 19.0, 299.229, 7.0, 0.0, 0.0], 'I5-36-30-27': [17474, 1387.42, 19.0, 41.104, 7.0, 0.0, 0.0], 'J1-36-30-28-A': [17475, 1387.3, 19.0, 27.703, 7.0, 0.0, 0.0], 'J1-36-30-28-B': [17475, 1387.2, 19.0, 21.702, 7.0, 0.0, 0.0], 'J1-36-30-28-C': [17476, 1387.12, 19.0, 19.802, 7.0, 0.0, 0.0], 'I5-36-30-28': [17302, 1386.63, 17.0, 109.813, 7.0, 0.0, 0.0], 'O-36-30-96': [16949, 1385.5, 0, 115.231, 7.0, 0.0, 0.0]}
# rpt_file = "swmm.RPT"
# topo_file = "TOPO.DAT"
# wse_file = "MAXWSELEV.OUT"
# units = 'feet'
# manhole_diameter = 5


class SDAnimator(QDialog):

    # constructor
    def __init__(self, existing_nodes_dict, rpt_file, units, manhole_diameter, parent=None):
        super().__init__(parent)

        self.existing_nodes_dict = existing_nodes_dict
        self.rpt_file = rpt_file
        self.units = units
        self.manhole_diameter = manhole_diameter

        # Set up layout and canvas
        self.vertical_layout = QVBoxLayout()
        self.canvas = FigureCanvas(Figure())
        self.vertical_layout.addWidget(self.canvas)

        self.setLayout(self.vertical_layout)

        self.setGeometry(0, 0, 800, 600)
        self.setWindowTitle("FLO-2D Storm Drain Profile Animator")

        # Initialize animation figure
        self.ax = self.canvas.figure.add_subplot(111)
        self.animation = None
        self.paused = False
        self.current_frame = 0  # Track the current frame
        self.total_frames = None

        self.nodes_array = None
        self.nodes_distances_anim = []
        self.nodes_ts = []

        self.setup_data()
        self.plot()
        self.init_animation()

    def setup_data(self):
        """
        Function to set up all results data
        """
        nodes_data = []
        self.nodes_ts = []
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
                                self.nodes_ts.append(NodeTSData[0] + " " + NodeTSData[1])
            i += 1
            nodes_data.append(node_data)
        self.nodes_array = np.array(nodes_data)

        self.total_frames = self.nodes_array.shape[1]

    def init_animation(self):
        # Example data generation for an animation
        self.line, = self.ax.plot([], [], label="HGL")

        self.animation = Player(
            self.canvas.figure,
            self.update_animation,
            init_func=self.init_line,
            frames=self.total_frames,
            interval=100,
            blit=False)

    def init_line(self):
        # Initialize an empty line
        self.line.set_data([], [])
        self.line.set_color('blue')
        return self.line,

    def update_animation(self, frame):
        # Update the data for the line (e.g., sine wave)

        if not self.ax.get_legend():
            self.ax.legend(loc="upper right", facecolor='white', framealpha=1)
            self.counter_label = self.ax.legend([self.line], [f"HGL | {self.nodes_ts[frame]}"], loc="upper right")

        self.line.set_data(np.array(self.nodes_distances_anim), self.nodes_array[:, frame])  # Update line data
        self.counter_label.get_texts()[0].set_text(f"HGL | {self.nodes_ts[frame]}")

        return self.line, self.counter_label

    def plot(self):
        """
        Function to plot the profile
        """
        units = 'feet'
        manhole_diameter = 5

        grid_elements = []
        for key, value in self.existing_nodes_dict.items():
            grid_elements.append(value[0])

        if self.rpt_file:
            max_hgl = []
            NodeDepthSummary = False
            NodeDepthDict = {}
            with open(self.rpt_file, "r") as f:
                for line in f:
                    if 'Node Depth Summary' in line:
                        NodeDepthSummary = True
                        for _ in range(7):
                            next(f)
                        continue
                    if NodeDepthSummary:
                        if len(line.split()) != 7:
                            break
                        elif line.split()[0] in list(self.existing_nodes_dict.keys()):
                            # node type average_depth max_depth max_hgl time_max_days time_max_hours
                            NodeDepthData = line.split()
                            NodeDepthDict[NodeDepthData[0]] = [NodeDepthData[2], NodeDepthData[3]]
                            max_hgl.append(float(NodeDepthData[4]))

        x_secondary_axis_labels = []

        # Pipes [[1,1], [2,1], [2,2], [1,2]]
        distance_acc_curr = 0
        distance_acc_prev = 0

        for i in range(len(self.existing_nodes_dict)):
            if i != 0:
                distance_acc_prev += list(self.existing_nodes_dict.values())[i - 1][3]
                mh1_x = distance_acc_prev
                mh1_y_min = list(self.existing_nodes_dict.values())[i - 1][1] + list(self.existing_nodes_dict.values())[i][5]
                mh1_y_max = list(self.existing_nodes_dict.values())[i - 1][1] + list(self.existing_nodes_dict.values())[i][
                    4] + list(self.existing_nodes_dict.values())[i][5]
                distance_acc_curr += list(self.existing_nodes_dict.values())[i][3]
                mh2_x = distance_acc_curr
                mh2_y_min = list(self.existing_nodes_dict.values())[i][1] + list(self.existing_nodes_dict.values())[i][6]
                mh2_y_max = list(self.existing_nodes_dict.values())[i][1] + list(self.existing_nodes_dict.values())[i][4] + \
                            list(self.existing_nodes_dict.values())[i][6]
                coord = [[mh1_x, mh1_y_min], [mh2_x, mh2_y_min], [mh2_x, mh2_y_max], [mh1_x, mh1_y_max]]
                self.ax.add_patch(patches.Polygon(coord, linewidth=1, edgecolor='black', facecolor='white', zorder=1))
            x_secondary_axis_labels.append([list(self.existing_nodes_dict.keys())[i], distance_acc_curr])
            self.nodes_distances_anim.append(distance_acc_curr)

        distance_acc = 0
        invert_elevs = []
        max_depths = []
        # Manholes
        for key, value in self.existing_nodes_dict.items():
            invert_elev = value[1]
            max_depth = value[2]
            length = value[3]
            invert_elevs.append(invert_elev)
            max_depths.append(max_depth)
            distance_acc += length
            rect = patches.Rectangle((distance_acc - (manhole_diameter / 2), invert_elev), manhole_diameter, max_depth,
                                     linewidth=1.5, edgecolor='black',
                                     facecolor='white', zorder=2)
            self.ax.add_patch(rect)

        secax = self.ax.secondary_xaxis('top')
        secax.set_xticks([distance for _, distance in x_secondary_axis_labels])
        secax.set_xticklabels([name for name, _ in x_secondary_axis_labels], rotation=90, ha='center', fontsize=8)

        # Set limits and labels
        self.ax.set_xlim(- (2 * manhole_diameter), distance_acc + (2 * manhole_diameter))

        max_invert_elev_idx = invert_elevs.index(max(invert_elevs))
        max_depth_idx = max_depths.index(max(max_depths))

        if not self.rpt_file:
            # The maximum y should be whichever is greater:
            # The maximum of max depth plus its invert elevation or the maximum of invert elevation plus max depth
            max_y = max(max(max_depths) + invert_elevs[max_depth_idx],
                        max(invert_elevs) + max_depths[max_invert_elev_idx])
            self.ax.set_ylim(min(invert_elevs) - manhole_diameter, max_y + (1.5 * manhole_diameter))
        else:
            # The maximum y should be whichever is greater:
            # The maximum of max depth plus its invert elevation or the maximum of invert elevation plus max depth or the maximum hgl
            max_y = max(max(max_depths) + invert_elevs[max_depth_idx],
                        max(invert_elevs) + max_depths[max_invert_elev_idx], max(max_hgl))
            self.ax.set_ylim(min(invert_elevs) - manhole_diameter, max_y + (1.5 * manhole_diameter))

        self.ax.set_title(f'{list(self.existing_nodes_dict.keys())[0]} to {list(self.existing_nodes_dict.keys())[-1]}')
        self.ax.set_xlabel(f"Distance ({units})")
        self.ax.set_ylabel(f"Elevation ({units})")

        if self.rpt_file:
            handles, labels = self.ax.get_legend_handles_labels()
            handle_list, label_list = [], []
            for handle, label in zip(handles, labels):
                if label not in label_list:
                    handle_list.append(handle)
                    label_list.append(label)
            plt.legend(handle_list, label_list, loc="upper right")

        # Show plot
        self.canvas.figure.tight_layout()
        self.canvas.draw()


class Player(FuncAnimation):
    def __init__(self, fig, func, frames=None, init_func=None, fargs=None,
                 save_count=None, mini=0, maxi=100, pos=(0.68, 0.025), **kwargs):
        self.i = 0
        self.min=mini
        self.max=maxi
        self.runs = True
        self.forwards = True
        self.fig = fig
        self.func = func
        self.setup(pos)
        FuncAnimation.__init__(self, self.fig, self.func, frames=self.play(),
                                           init_func=init_func, fargs=fargs,
                                           save_count=save_count, **kwargs )

    def play(self):
        while self.runs:
            self.i = self.i + self.forwards - (not self.forwards)
            if self.min < self.i < self.max:
                yield self.i
            else:
                self.i = self.min
                self.stop()
                yield self.i

    def start(self):
        if self.runs:
            self.runs = False
            self.event_source.stop()
        else:
            self.runs=True
            self.event_source.start()

    def stop(self, event=None):
        self.runs = False
        self.event_source.stop()
        self.i = self.min
        self.func(self.i)
        self.fig.canvas.draw_idle()

    def forward(self, event=None):
        self.forwards = True
        self.start()
    def backward(self, event=None):
        self.forwards = False
        self.start()
    def oneforward(self, event=None):
        self.forwards = True
        self.onestep()
    def onebackward(self, event=None):
        self.forwards = False
        self.onestep()

    def onestep(self):
        if self.i > self.min and self.i < self.max:
            self.i = self.i+self.forwards-(not self.forwards)
        elif self.i == self.min and self.forwards:
            self.i+=1
        elif self.i == self.max and not self.forwards:
            self.i-=1
        self.func(self.i)
        self.fig.canvas.draw_idle()

    def setup(self, pos):
        playerax = self.fig.add_axes([pos[0],pos[1], 0.22, 0.04])
        divider = mpl_toolkits.axes_grid1.make_axes_locatable(playerax)
        bax = divider.append_axes("right", size="80%", pad=0.05)
        sax = divider.append_axes("right", size="80%", pad=0.05)
        fax = divider.append_axes("right", size="80%", pad=0.05)
        ofax = divider.append_axes("right", size="100%", pad=0.05)
        self.button_oneback = matplotlib.widgets.Button(playerax, label='$\u29CF$')
        self.button_back = matplotlib.widgets.Button(bax, label=u'$\u25C0$')
        self.button_stop = matplotlib.widgets.Button(sax, label=u'$\u25A0$')
        self.button_forward = matplotlib.widgets.Button(fax, label=u'$\u25B6$')
        self.button_oneforward = matplotlib.widgets.Button(ofax, label=u'$\u29D0$')
        self.button_oneback.on_clicked(self.onebackward)
        self.button_back.on_clicked(self.backward)
        self.button_stop.on_clicked(self.stop)
        self.button_forward.on_clicked(self.forward)
        self.button_oneforward.on_clicked(self.oneforward)

