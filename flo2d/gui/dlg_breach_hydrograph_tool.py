# -*- coding: utf-8 -*-
import math

import processing
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QListWidgetItem, QSizePolicy, QFileDialog
from qgis._core import QgsProject, QgsWkbTypes, QgsVectorLayer, QgsFeature, QgsGeometry
from qgis.core import QgsMapLayerType

from .dlg_sampling_elev import SamplingElevDialog
from .dlg_sampling_raster_roughness import SamplingRoughnessDialog
from ..flo2d_ie.breach_hydrographs import TAILINGS_HYDROGRAPHS, TAILINGS_SEDIMENT_CV
from ..flo2d_tools.grid_tools import square_grid
from ..flo2dobjects import Inflow

from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from .ui_utils import load_ui
from qgis.PyQt.QtCore import Qt, NULL

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import numpy as np

import xml.etree.ElementTree as ET

uiDialog, qtBaseClass = load_ui("breach_hydrograph_tool")


class BreachHydrographToolDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs, bc_editor):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.bc_editor = bc_editor
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = GeoPackageUtils(con, iface)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint)

        self.t_hr, self.Qt = None, None
        self.hyd_map = {}
        self.sed_map = {}

        self.check_dam_type()

        self.cancel_btn.clicked.connect(self.close_dialog)
        self.next_btn.clicked.connect(self.next_page)
        self.previous_btn.clicked.connect(self.previous_page)

        self.water_group.clicked.connect(self.check_dam_type)
        self.tailings_group.clicked.connect(self.check_dam_type)

        self.generate_breach_parameters_btn.clicked.connect(self.generate_breach_parameters)
        self.generate_hydrograph_btn.clicked.connect(self.generate_hydrograph)
        self.create_cd_btn.clicked.connect(self.create_computational_domain)
        self.refresh_btn.clicked.connect(self.populate_user_inflow)

        self.open_tailings_data_btn.clicked.connect(self.open_tailings_data)
        self.save_tailings_data_btn.clicked.connect(self.save_tailings_data)

        self.water_add_btn.clicked.connect(self.add_ts_to_inflow)

        self.populate_information()
        self.stackedWidget.currentChanged.connect(self.populate_information)

        # Hydrologic
        self.input_flood_volume_dsb.valueChanged.connect(self.check_hydrologic_failure)
        self.spillway_chbox.stateChanged.connect(self.check_hydrologic_failure)
        self.max_allow_head_dsb.valueChanged.connect(self.check_hydrologic_failure)
        self.pmf_wse_dsb.valueChanged.connect(self.check_hydrologic_failure)

        # Static
        self.reservoir_lvl_cbo.currentIndexChanged.connect(self.check_static_failure)

        # Seismic
        self.eq_mag_dsb.valueChanged.connect(self.check_seismic_failure)
        self.peak_ground_acc_dsb.valueChanged.connect(self.check_seismic_failure)
        self.soft_lyr_chbox.toggled.connect(self.check_seismic_failure)
        self.depth_to_layer_dsb.valueChanged.connect(self.check_seismic_failure)
        self.blow_continuous_dsb.valueChanged.connect(self.check_seismic_failure)
        self.drop_rb.toggled.connect(self.check_seismic_failure)
        self.automatic_rb.toggled.connect(self.check_seismic_failure)
        self.fine_content_cbo.currentIndexChanged.connect(self.check_seismic_failure)

        self.hydrologic_grp.toggled.connect(lambda checked: checked and self.group_toggled(0))
        self.static_grp.toggled.connect(lambda checked: checked and self.group_toggled(1))
        self.seismic_grp.toggled.connect(lambda checked: checked and self.group_toggled(2))

        self.slope_lvl_table = {
            (0, 0): (-0.0048, 0.140),
            (1, 0): (-0.0041, 0.140),
            (2, 0): (-0.0034, 0.140),

            (0, 1): (-0.0051, 0.120),
            (1, 1): (-0.0042, 0.120),
            (2, 1): (-0.0033, 0.120),

            (0, 2): (-0.0055, 0.110),
            (1, 2): (-0.0043, 0.110),
            (2, 2): (-0.0032, 0.110),

            (0, 3): (-0.0061, 0.100),
            (1, 3): (-0.0046, 0.100),
            (2, 3): (-0.0031, 0.100),

            (0, 4): (-0.0062, 0.090),
            (1, 4): (-0.0047, 0.090),
            (2, 4): (-0.0031, 0.090),

            (0, 5): (-0.0065, 0.085),
            (1, 5): (-0.0048, 0.085),
            (2, 5): (-0.0031, 0.085),
        }

    def add_ts_to_inflow(self):
        """
        Function to add time series to selected inflow
        """
        if self.t_hr is None or self.Qt is None or len(self.t_hr) == 0 or len(self.Qt) == 0:
            self.uc.bar_warn("No hydrograph data to add. Please generate a hydrograph first.")
            self.uc.log_info("No hydrograph data to add. Please generate a hydrograph first.")
            return

        selected_inflow_name = self.water_inflow_cbo.currentText()

        inflow_qry = self.gutils.execute("SELECT fid, time_series_fid FROM inflow WHERE name = ?", (selected_inflow_name,)).fetchone()
        if inflow_qry:
            inflow_fid = inflow_qry[0]
            inflow = Inflow(inflow_fid, self.iface.f2d["con"], self.iface)

            time_series_fid = inflow_qry[1]
            if time_series_fid is None:
                ts_name = f"Time Series {inflow_fid}"
                inflow.add_time_series(name=ts_name)
                time_series_fid = self.gutils.execute("SELECT fid FROM inflow_time_series WHERE name = ?", (ts_name,)).fetchone()[0]
            else:
                ts_name = self.gutils.execute("SELECT name FROM inflow_time_series WHERE fid = ?", (time_series_fid,)).fetchone()[0]
        else:
            return

        ts_data = []
        for t, q in zip(self.t_hr, self.Qt):
            ts_data.append((time_series_fid, round(float(t), 2), round(float(q), 2), None))

        inflow.time_series_fid = time_series_fid
        inflow.set_time_series_data(ts_name, ts_data)

        self.bc_editor.inflow_changed()

    def populate_information(self):
        """
        Function to populate information based on the current page
        """
        self.populate_user_channel()
        self.populate_user_inflow()
        self.populate_rasters()
        self.populate_water_blank_graph()
        self.populate_tailings_hyd_graphs()
        self.populate_tailings_sed_graphs()

        if self.tailings_group.isChecked():
            self.populate_tailings_breach_volume()

    def populate_water_blank_graph(self):
        """
        Function to populate a blank graph area
        """
        # Clear previous plot
        while self.verticalLayout.count():
            item = self.verticalLayout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        fig = Figure(figsize=(6, 3.5), dpi=100)
        ax = fig.add_subplot(111)

        ax.set_xlabel("Time (hrs)")
        ax.set_ylabel("Discharge (m³/s)")
        ax.set_title("")

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(False)

        # Explicit margins for Qt dialogs
        fig.subplots_adjust(
            left=0.09,
            right=0.97,
            top=0.87,
            bottom=0.18
        )

        fig.patch.set_edgecolor("#b0b0b0")
        fig.patch.set_linewidth(0.8)

        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        canvas.setMinimumHeight(220)

        self.verticalLayout.addWidget(canvas, stretch=1)
        canvas.draw()

    def populate_tailings_sed_graphs(self):
        """
        Create 3x2 selectable plots
        """

        if self.sediment_grid.count() > 0:
            return

        fig = Figure(figsize=(7, 6), dpi=100)
        axes = fig.subplots(3, 2).flatten()

        for i, ax in enumerate(axes):
            ax.set_xlabel("Time/Duration")
            ax.set_ylabel("Cv/Cvmax")
            ax.set_ylim([0, 1.1])

            ax._plot_index = i

            sed = TAILINGS_SEDIMENT_CV[f"S{i + 1}"]

            line, = ax.plot(sed["time"], sed["cv"],
                            label="Cv/Cvmax",
                            color="orange")

            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)

            ax.legend([line], [line.get_label()],
                      loc="lower right",
                      fontsize=6,
                      frameon=False)

            self.sed_map[ax] = f"Scenario {i + 1}"

        fig.subplots_adjust(
            left=0.08,
            right=0.98,
            top=0.94,
            bottom=0.08,
            hspace=0.35,
            wspace=0.25
        )

        fig.tight_layout()

        canvas = FigureCanvas(fig)
        canvas.setMinimumHeight(450)

        canvas.mpl_connect("button_press_event", self.on_plot_clicked)

        self.sediment_grid.addWidget(canvas)
        canvas.draw()

    def populate_tailings_hyd_graphs(self):
        """
        Create 3x2 selectable plots
        """

        if self.hydrographs_grid.count() > 0:
            return

        fig = Figure(figsize=(7, 6), dpi=100)
        axes = fig.subplots(3, 2).flatten()

        for i, ax in enumerate(axes):
            ax.set_xlabel("Time/Duration")
            ax.set_ylabel("Q/Qpeak")
            ax.set_ylim([0, 1.1])
            ax._plot_index = i

            hg = TAILINGS_HYDROGRAPHS[f"H{i + 1}"]

            # --- Primary axis ---
            line1, = ax.plot(hg["time"], hg["qqp"], label="Q/Qp", color="blue")

            # --- Secondary axis ---
            ax2 = ax.twinx()
            ax2.set_axis_off()
            ax2.set_ylim([0, 1.1])
            ax2._parent_ax = ax

            line2, = ax2.plot(hg["time"], hg["mass"], label="Mass Curve", color="gold")

            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax2.spines["top"].set_visible(False)
            ax2.spines["right"].set_visible(False)

            lines = [line1, line2]
            labels = [l.get_label() for l in lines]
            ax.legend(lines, labels, loc="right", fontsize=6, frameon=False)

            self.hyd_map[ax] = f"Scenario {i + 1}"

        fig.subplots_adjust(
            left=0.08,
            right=0.98,
            top=0.94,
            bottom=0.08,
            hspace=0.35,
            wspace=0.25
        )

        fig.tight_layout()

        canvas = FigureCanvas(fig)
        canvas.setMinimumHeight(450)

        canvas.mpl_connect("button_press_event", self.on_plot_clicked)

        self.hydrographs_grid.addWidget(canvas)
        canvas.draw()

    def on_plot_clicked(self, event):

        if event.inaxes is None:
            return

        ax_clicked = getattr(event.inaxes, "_parent_ax", event.inaxes)
        idx = getattr(ax_clicked, "_plot_index", None)

        if idx is None:
            return

        for ax in self.hyd_map:
            ax.patch.set_edgecolor("white")
            ax.patch.set_linewidth(1)

        for ax in self.sed_map:
            ax.patch.set_edgecolor("white")
            ax.patch.set_linewidth(1)

        for ax in self.hyd_map:
            if getattr(ax, "_plot_index", None) == idx:
                ax.patch.set_edgecolor("red")
                ax.patch.set_linewidth(3)

        for ax in self.sed_map:
            if getattr(ax, "_plot_index", None) == idx:
                ax.patch.set_edgecolor("red")
                ax.patch.set_linewidth(3)

        if self.hydrographs_grid.count():
            self.hydrographs_grid.itemAt(0).widget().draw()

        if self.sediment_grid.count():
            self.sediment_grid.itemAt(0).widget().draw()

        volume = float(self.tal_select_volume_cbo.currentData()[0])
        total_duration = float(self.tal_event_time_le.text())

        peak_discharge = self.estimate_peak_discharge(idx, volume, total_duration)
        self.tal_peak_q_le.setText(f"{round(peak_discharge, 2)}")

        max_cv = float(self.tal_max_sed_con_le.text())
        hyd_sed_vol = self.estimate_hyd_sed_vol(idx, peak_discharge, max_cv, total_duration)
        self.tal_hyd_sed_vol_le.setText(f"{round(hyd_sed_vol, 2)}")

    def estimate_hyd_sed_vol(self, idx, qpeak, max_cv, total_duration_hours):
        """
        Find peak Hydrograph Sediment Volume
        """

        hg = TAILINGS_HYDROGRAPHS[f"H{idx + 1}"]
        sed = TAILINGS_SEDIMENT_CV[f"S{idx + 1}"]

        total_duration_sec = total_duration_hours * 3600.0

        cv_interp = np.interp(
            hg["time"],
            sed["time"],
            sed["cv"],
            left=0.0,
            right=sed["cv"][-1]
        )

        final_sediment = 0.0

        for i in range(1, len(hg["time"])):
            t0 = hg["time"][i - 1] * total_duration_sec
            t1 = hg["time"][i] * total_duration_sec

            q0 = hg["qqp"][i - 1] * qpeak
            q1 = hg["qqp"][i] * qpeak

            water_volume = 0.5 * (t1 - t0) * (q0 + q1)

            cv = max_cv * cv_interp[i]
            cv = min(cv, 0.999)

            sediment_volume = water_volume * cv / (1.0 - cv)
            final_sediment += sediment_volume

        return final_sediment

    def estimate_peak_discharge(self, idx, target_volume, total_duration, tol=0.01, max_iter=100):
        """
        Find peak discharge so hydrograph volume matches target volume.
        """

        # convert duration to seconds
        total_duration_sec = total_duration * 3600.0

        hg = TAILINGS_HYDROGRAPHS[f"H{idx + 1}"]

        lower = 0.0
        upper = target_volume / total_duration_sec * 10.0

        for _ in range(max_iter):

            qpeak = 0.5 * (lower + upper)
            volume = 0.0

            for i in range(1, len(hg["time"])):
                t0 = hg["time"][i - 1] * total_duration_sec
                t1 = hg["time"][i] * total_duration_sec

                q0 = hg["qqp"][i - 1] * qpeak
                q1 = hg["qqp"][i] * qpeak

                volume += 0.5 * (t1 - t0) * (q0 + q1)

            if abs(volume - target_volume) < tol:
                return qpeak

            if volume > target_volume:
                upper = qpeak
            else:
                lower = qpeak

        return qpeak

    def populate_rasters(self):
        """
        Function to populate raster layers in the combo boxes
        """
        self.elevation_cbo.clear()
        self.roughness_cbo.clear()

        user_layers = []
        gpkg_path = self.gutils.get_gpkg_path()
        gpkg_path_adj = gpkg_path.replace("\\", "/")

        for l in QgsProject.instance().mapLayers().values():
            layer_source_adj = l.source().replace("\\", "/")
            if gpkg_path_adj not in layer_source_adj:
                if l.type() == QgsMapLayerType.RasterLayer:
                    user_layers.append(l)

        for s in user_layers:
            self.roughness_cbo.addItem(s.name(), s.dataProvider().dataSourceUri())
            self.elevation_cbo.addItem(s.name(), s.dataProvider().dataSourceUri())


    def populate_user_inflow(self):
        """
        Function to populate user inflow combo box
        """
        self.water_inflow_cbo.clear()
        self.tailings_inflow_cbo.clear()

        all_inflows = self.gutils.get_inflows_list()
        if not all_inflows:
            return
        for i, row in enumerate(all_inflows):
            row = [x if x is not None else "" for x in row]
            fid, name, geom_type, ts_fid = row
            if not name:
                name = "Inflow {}".format(fid)
            self.water_inflow_cbo.addItem(name)
            self.tailings_inflow_cbo.addItem(name)

    def create_computational_domain(self):
        """
        Function to create computational domain from user channel
        """
        selected_layer_name = self.user_channel_cb.currentText()
        selected_layer = None

        bl = self.lyrs.data["user_model_boundary"]["qlyr"]
        grid_lyr = self.lyrs.data["grid"]["qlyr"]
        elev_raster = self.elevation_cbo.itemData(self.elevation_cbo.currentIndex())
        roughness_raster = self.roughness_cbo.itemData(self.roughness_cbo.currentIndex())

        for l in QgsProject.instance().mapLayers().values():
            if l.name() == selected_layer_name:
                selected_layer = l
                break

        if selected_layer is None:
            self.uc.bar_error("Selected layer not found.")
            self.uc.log_info("Selected layer not found.")
            return

        if selected_layer.featureCount() < 1:
            self.uc.bar_warn("Selected layer has no features.")
            self.uc.log_info("Selected layer has no features.")
            return

        if selected_layer.crs().authid() != bl.crs().authid():
            self.uc.bar_warn("Selected layer CRS does not match project CRS.")
            self.uc.log_info("Selected layer CRS does not match project CRS.")
            return

        buffer = self.buffer_dsb.value()
        if buffer <= 0:
            self.uc.bar_warn("Buffer distance must be greater than zero.")
            self.uc.log_info("Buffer distance must be greater than zero.")
            return

        empty = self.gutils.is_table_empty("user_model_boundary")
        # check if a grid exists in the grid table
        if not empty:
            q = "There is a computational domain already defined in GeoPackage. Overwrite it?"
            if self.uc.question(q):
                self.gutils.clear_tables("user_model_boundary", "grid")
            else:
                self.uc.bar_info("Creation of computational domain canceled!")
                self.uc.log_info("Creation of computational domain canceled!")
                return


        params = {
            "INPUT": selected_layer,
            "DISTANCE": buffer,
            "SEGMENTS": 5,
            "END_CAP_STYLE": 1,
            "JOIN_STYLE": 0,
            "MITER_LIMIT": 2,
            "DISSOLVE": True,
            "SEPARATE_DISJOINT": False,
            "OUTPUT": "TEMPORARY_OUTPUT",
        }
        tmp = processing.run("native:buffer", params)["OUTPUT"]

        bl.startEditing()

        for f in tmp.getFeatures():
            new_f = QgsFeature(bl.fields())
            new_f.setGeometry(f.geometry())
            bl.addFeature(new_f)

        bl.commitChanges()

        cellSize = float(self.gutils.get_cont_par("CELLSIZE"))
        self.gutils.execute("UPDATE user_model_boundary SET cell_size = ?", (cellSize,))

        # TODO add a cellsize check
        # Create the grid
        square_grid(self.gutils, bl, None)
        sample_elev = SamplingElevDialog(self.con, self.iface, self.lyrs, cellSize)
        sample_elev.probe_elevation(elev_raster)
        sample_roughness = SamplingRoughnessDialog(self.con, self.iface, self.lyrs, cellSize)
        sample_roughness.probe_roughness(roughness_raster)

        bl.triggerRepaint()
        grid_lyr.triggerRepaint()

        self.uc.show_info("The grid was successfully created.")
        self.uc.log_info("The grid was successfully created.")

    def populate_user_channel(self):
        """
        Function to populate user channel combo box
        """
        self.user_channel_cb.clear()

        user_layers = []
        gpkg_path = self.gutils.get_gpkg_path()
        gpkg_path_adj = gpkg_path.replace("\\", "/")

        for l in QgsProject.instance().mapLayers().values():
            layer_source_adj = l.source().replace("\\", "/")
            if gpkg_path_adj not in layer_source_adj:
                if l.type() == QgsMapLayerType.VectorLayer:
                    geom_type = l.geometryType()

                    # Check against the line geometry types
                    if geom_type == QgsWkbTypes.LineGeometry:
                        user_layers.append(l)

        for s in user_layers:
            self.user_channel_cb.addItem(s.name(), s.dataProvider().dataSourceUri())

    def populate_tailings_breach_volume(self):
        """
        Function to calculate breach parameters for tailings dams.
        """
        dam_height = self.dam_height_2_dsb.value()
        tot_imp_vol = self.tot_imp_vol_dsb.value()
        imp_tal_vol = self.imp_tal_vol_dsb.value()

        # hydrologic parameters
        available_storage = tot_imp_vol - imp_tal_vol  # m³
        self.available_storage_le.setText(str(available_storage))

        # static parameters
        cohesion_dam_material = self.cohesion_dam_material_dsb.value()
        unit_weight_dam =  self.unit_weight_dam_dsb.value()

        if dam_height <= 0:
            self.uc.log_info("Dam Height must be greater than 0.")
            self.uc.bar_warn("Dam Height must be greater than 0.")
            return

        if tot_imp_vol <= 0:
            self.uc.log_info("Total Impoundment Volume must be greater than 0.")
            self.uc.bar_warn("Total Impoundment Volume must be greater than 0.")
            return

        if imp_tal_vol < 0:
            self.uc.log_info("Impounded Tailings Volume must be positive.")
            self.uc.bar_warn("Impounded Tailings Volume must be positive.")
            return

        if unit_weight_dam <= 0:
            self.uc.log_info("Unit Weight of Dam Material must be positive and greater than 0.")
            self.uc.bar_warn("Unit Weight of Dam Material must be positive and greater than 0.")
            return

        if self.gutils.get_cont_par("METRIC") == "1":
            m3_to_cy = 1.30795
            g = 9.81  # m/s2
        else:
            m3_to_cy = 1
            g = 32.2  # ft/s2

        cydamh = cohesion_dam_material / (unit_weight_dam * dam_height)
        self.cydamh_le.setText(str(round(cydamh, 4)))

        friction_angle_dam_material = self.friction_angle_dam_material_dsb.value()
        reservoir_lvl = self.reservoir_lvl_cbo.currentIndex()
        tailings_dam_slope = self.tailings_dam_slope_cbo.currentIndex()

        slope, level = self.slope_lvl_table[(reservoir_lvl, tailings_dam_slope)]

        slope_failure = slope * friction_angle_dam_material + level

        self.slope_failure_le.setText(str(round(slope_failure, 4)))

        # Estimate the volumes
        Vrmin = min(1052 * dam_height ** 1.2821, 0.95 * imp_tal_vol)
        Vrave = min(3604 * dam_height ** 1.2821, 0.95 * imp_tal_vol)
        Vrmax = min(20419 * dam_height ** 1.2821, 0.95 * imp_tal_vol)

        self.vrmin_le.setText(str(int(Vrmin)))
        self.vrave_le.setText(str(int(Vrave)))
        self.vrmax_le.setText(str(int(Vrmax)))

        larrauri = min(0.332 * (tot_imp_vol / 1000000) ** 0.95, 0.95 * imp_tal_vol)
        rico = min(0.354 * (tot_imp_vol/ 1000000) ** 1.01, 0.95 * imp_tal_vol)
        piciullo1 = min(0.214 * (tot_imp_vol/ 1000000) ** 0.35, 0.95 * imp_tal_vol)
        piciullo2 = min((10 ** 0.33) * (tot_imp_vol ** 0.611) * (dam_height ** 0.994), 0.95 * imp_tal_vol)

        self.larrauri_dsb.setText(str(int(larrauri * 1000000)))
        self.rico_dsb.setText(str(int(rico * 1000000)))
        self.piciullo1_dsb.setText(str(int(piciullo1 * 1000000)))
        self.piciullo2_dsb.setText(str(int(piciullo2)))

        # Hydrologic Failure Check
        self.check_hydrologic_failure()

        # Static Failure Check
        self.check_static_failure()

        # Seismic Failure Check
        self.check_seismic_failure()

        # Save Options
        self.tal_select_volume_cbo.clear()
        user_volume = float(self.user_volume_le.text()) if self.user_volume_le.text() != "" else 0
        volumes = {
            "User Volume": user_volume,
            "Minimum Volume": Vrmin,
            "Average Volume": Vrave,
            "Maximum Volume": Vrmax,
            "Larrauri and Lall (2018)": larrauri * 1000000,
            "Rico et al. (2008)": rico * 1000000,
            "Piciullo et al. (2022)": piciullo1 * 1000000,
            "Piciullo et al. (updated eq.)": piciullo2
        }

        for name, volume in volumes.items():
            item = f"{name} - {round(volume, 2)}"
            self.tal_select_volume_cbo.addItem(item, [str(volume)])

    def check_static_failure(self):
        """
        Function to check for static failure of tailings dams.
        """
        foundation_soil = self.soil_bellow_base_cbo.currentIndex()
        spt_count = self.spt_count_sb.value()
        cydamh = self.cydamh_le.text()
        if cydamh == "":
            cydamh = 0
        else:
            cydamh = float(cydamh)

        slope_failure = self.slope_failure_le.text()
        if slope_failure == "":
            slope_failure = 0
        else:
            slope_failure = float(slope_failure)

        breach_type = "No Breach"

        if foundation_soil == 0:  # Granular
            if spt_count < 10:
                breach_type = "Dam Breach by Foundation Failure"
        elif foundation_soil == 1: # Cohesive
            if spt_count < 8:
                breach_type = "Dam Breach by Foundation Failure"

        if cydamh < slope_failure:
            breach_type = "Dam Breach by Slope Instability"

        self.static_breach_type_lbl.setText(breach_type)


    def check_hydrologic_failure(self):
        """
        Function to check for hydrologic failure of tailings dams.
        """

        tot_imp_vol = self.tot_imp_vol_dsb.value()
        imp_tal_vol = self.imp_tal_vol_dsb.value()
        available_storage = tot_imp_vol - imp_tal_vol
        input_flood_volume = self.input_flood_volume_dsb.value()
        spillway = self.spillway_chbox.isChecked()
        max_allow_head = self.max_allow_head_dsb.value()
        pmf_wse = self.pmf_wse_dsb.value()

        breach_type = "No Breach"

        if input_flood_volume > available_storage:
            if spillway:
                if pmf_wse > max_allow_head:
                    breach_type = "Dam Breach by Erosion"
            else:
                breach_type = "Dam Breach"

        self.hyd_breach_type_lbl.setText(str(breach_type))

    def check_seismic_failure(self):
        """
        Function to check for seismic failure of tailings dams.
        """
        breach_type = "No Breach"

        drop_hammer = True

        if self.drop_rb.isChecked():
            drop_hammer = True
        if self.automatic_rb.isChecked():
            drop_hammer = False

        spt_blow_count = self.blow_continuous_dsb.value()
        n60 = 0

        if not drop_hammer:
            n60 = 1.33 * spt_blow_count

        # TODO check this code with Noemi
        VES = 0.04
        Cn = 0.77 * math.log10(20 / VES)

        N160 = Cn * n60
        CorrectedN160 = N160

        fines_content = self.fine_content_cbo.currentIndex()

        if fines_content == 0:
            CorrectedN160 += 1
        elif fines_content == 1:
            CorrectedN160 += 2
        elif fines_content == 2:
            CorrectedN160 += 4
        elif fines_content == 3:
            CorrectedN160 += 5

        depth_to_layer = self.depth_to_layer_dsb.value()
        unit_weight_dam = self.unit_weight_dam_dsb.value()
        unit_weight_found = self.unit_weight_found_dsb.value()
        dam_height = self.dam_height_2_dsb.value()
        freeboard_from_surface = self.water_surface_freeboard_dsb.value()

        total_stress = depth_to_layer * (unit_weight_dam * dam_height + unit_weight_found * (depth_to_layer - dam_height))
        effective_stress = total_stress - (depth_to_layer - freeboard_from_surface) * 62.4

        if depth_to_layer <= 30:
            stress_red_factor = 1 - 0.00765 * (depth_to_layer / 3)
        else:
            stress_red_factor = 1.174 - 0.0267 * (depth_to_layer / 3.0)

        peak_ground_acc = self.peak_ground_acc_dsb.value()
        cyclic_shear_stress_ratio = (0.65 * peak_ground_acc * total_stress) / (effective_stress * stress_red_factor)

        liquefaction_potential_boundary = 0.01125 * N160

        depth_to_sat_tailings = self.depth_to_saturated_dsb.value()
        depth_to_bedrock = self.depth_to_bedrock_dsb.value()
        eq_mag = self.eq_mag_dsb.value()

        if peak_ground_acc > 0.22 and CorrectedN160 < 14 and depth_to_sat_tailings < 10 and freeboard_from_surface > 10 and cyclic_shear_stress_ratio > liquefaction_potential_boundary:
            breach_type = "Dam Breach by Liquefaction"
        else:
            deformation_of_crest = (dam_height + depth_to_bedrock) * math.exp(6.07 * peak_ground_acc + 0.57 * eq_mag - 8)
            if deformation_of_crest > freeboard_from_surface:
                breach_type = "Dam Breach by Deformation of Crest"

        self.seismic_breach_type_lbl.setText(str(breach_type))

    def next_page(self):
        """
        Move to the next page based on the selected mode (water or tailings).
        """
        current = self.stackedWidget.currentIndex()
        max_index = self.stackedWidget.count() - 1
        if current >= max_index:
            return

        # Define allowed pages for each mode
        if self.water_group.isChecked():
            allowed = [0, 2]
        elif self.tailings_group.isChecked():
            allowed = [0, 1, 3]
        else:
            return

        for p in allowed:
            if p > current:
                self.stackedWidget.setCurrentIndex(min(p, max_index))
                return

    def previous_page(self):
        """
        Move to the previous page based on the selected mode (water or tailings).
        """
        current = self.stackedWidget.currentIndex()
        if current <= 0:
            return

        if self.water_group.isChecked():
            allowed = [0, 2]
        elif self.tailings_group.isChecked():
            allowed = [0, 1, 3]
        else:
            return

        for p in reversed(allowed):
            if p < current:
                self.stackedWidget.setCurrentIndex(max(p, 0))
                return

    def close_dialog(self):
        """
        Function to close the dialog
        """
        self.close()

    def check_dam_type(self):
        """
        Function to check the selected dam type and adjust the UI accordingly.
        """

        if self.water_group.isChecked():
            self.tailings_group.blockSignals(True)
            self.tailings_group.setChecked(False)
            self.tailings_group.blockSignals(False)

            self.tailings_group.setEnabled(True)
            self.water_group.setEnabled(True)

        elif self.tailings_group.isChecked():
            self.water_group.blockSignals(True)
            self.water_group.setChecked(False)
            self.water_group.blockSignals(False)

            self.water_group.setEnabled(True)
            self.tailings_group.setEnabled(True)

    def group_toggled(self, group_id):
        """
        Function to handle the toggling of the hydrologic, static, and seismic groups.
        """

        groups = [
            self.hydrologic_grp,
            self.static_grp,
            self.seismic_grp
        ]

        for i, grp in enumerate(groups):
            grp.blockSignals(True)
            grp.setChecked(i == group_id)
            grp.blockSignals(False)

    def generate_breach_parameters(self):
        """
        Function to generate breach parameters based on the selected method.
        """

        dam_height = self.dam_height_dsb.value()
        dam_volume = self.dam_volume_dsb.value()
        failure_mechanism = self.failure_mechanism_cb.currentIndex()
        baseflow = self.baseflow_dsb.value()

        if dam_height <= 0:
            self.uc.log_info("Dam Height must be greater than 0.")
            self.uc.bar_warn("Dam Height must be greater than 0.")
            return
        if dam_volume <= 0:
            self.uc.log_info("Total Impoundment Volume must be greater than 0.")
            self.uc.bar_warn("Total Impoundment Volume must be greater than 0.")
            return
        if baseflow < 0:
            self.uc.log_info("Baseflow must be positive or equal to 0.")
            self.uc.bar_warn("Baseflow must be positive or equal to 0.")
            return

        if self.gutils.get_cont_par("METRIC") == "1":
            g = 9.81  # m/s2
        else:
            g = 32.2  # ft/s2

        if self.froehlich_1995_rb.isChecked():
            peak_discharge = 0.607 * pow(dam_volume, 0.295) * pow(dam_height, 1.24)
            time_to_peak = 0.00254 * pow(dam_volume, 0.53) * pow(dam_height, -0.9)
            if failure_mechanism == 0:
                k = 1.4
            else:
                k = 1.0
            ave_breach_width = 0.1803 * k * pow(dam_volume, 0.32) * pow(dam_height, 0.19)

        elif self.froehlich_2008_rb.isChecked():
            peak_discharge = 0.607 * pow(dam_volume, 0.295) * pow(dam_height, 1.24)
            time_to_peak = 0.0176 * pow((dam_volume / (g * pow(dam_height, 2))), 0.5)
            if failure_mechanism == 0:
                k = 1.3
            else:
                k = 1.0
            ave_breach_width = 0.27 * k * pow(dam_volume, 0.5)

        elif self.mmc_rb.isChecked():
            peak_discharge = 0.0039042 * pow(dam_volume, 0.8122)
            ave_breach_width = 3 * dam_height
            time_to_peak = 0.011 * ave_breach_width

        elif self.analnec_rb.isChecked():
            peak_discharge_1 = 0.607 * pow(dam_volume, 0.295) * pow(dam_height, 1.24)
            peak_discharge_2 = 0.0039 * pow(dam_volume, 0.8122)
            peak_discharge = max(peak_discharge_1, peak_discharge_2)
            time_to_peak = 0.00254 * pow(dam_volume, 0.53) * pow(dam_height, -0.9)
            if failure_mechanism == 0:
                k = 1.4
            else:
                k = 1.0
            ave_breach_width = 0.1803 * k * pow(dam_volume, 0.32) * pow(dam_height, 0.19)

        else:
            self.uc.log_info("No breach parameter method selected.")
            self.uc.bar_warn("No breach parameter method selected.")
            return

        hydrograph_length = 2.0 * dam_volume / peak_discharge / 3600.0  # hours

        if peak_discharge is not None:
            self.peak_discharge_le.setText(str(round(peak_discharge, 2)))
        if time_to_peak is not None:
            self.time_to_peak_le.setText(str(round(time_to_peak, 2)))
        if ave_breach_width is not None:
            self.ave_breach_width_le.setText(str(round(ave_breach_width, 2)))
        if hydrograph_length is not None:
            self.hyd_length_le.setText(str(round(hydrograph_length, 2)))

    def generate_hydrograph(self):
        """
        Function to generate breach hydrograph based on the calculated parameters.
        """

        peak_discharge = float(self.peak_discharge_le.text())
        time_to_peak = float(self.time_to_peak_le.text())
        baseflow = float(self.baseflow_dsb.value())
        dam_volume = self.dam_volume_dsb.value()
        T_total = float(self.hyd_length_le.text())

        if self.tr66_rb.isChecked():
            self.t_hr, self.Qt = self.tr66_hydrograph(peak_discharge, time_to_peak, dam_volume, T_total, baseflow)

        elif self.parabolic_rb.isChecked():
            self.t_hr, self.Qt = self.ana_lnec_hydrograph(peak_discharge, time_to_peak, T_total, baseflow)

        elif self.triangular_rb.isChecked():
            self.t_hr, self.Qt = self.triangular_hydrograph(peak_discharge, time_to_peak, T_total, baseflow)

        else:
            self.uc.log_info("No hydrograph method selected.")
            self.uc.bar_warn("No hydrograph method selected.")
            return

        # --------------------------------------------------
        # Compute total volume under the hydrograph
        # --------------------------------------------------
        t_sec = np.asarray(self.t_hr) * 3600.0  # hours → seconds
        Qt = np.asarray(self.Qt)

        total_volume = np.trapz(Qt, t_sec)  # m³
        ratio = round(total_volume / dam_volume, 2)
        # --------------------------------------------------

        fig = Figure(figsize=(6, 3.5), dpi=100)
        ax = fig.add_subplot(111)

        ax.plot(self.t_hr, self.Qt)
        ax.set_xlabel("Time (hrs)")
        ax.set_ylabel("Discharge (m³/s)")
        ax.set_title(f"Total Volume = {total_volume:,.1f} m³ ({ratio})")

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(False)

        # Explicit margins for Qt dialogs
        fig.subplots_adjust(
            left=0.09,
            right=0.97,
            top=0.87,
            bottom=0.18
        )

        fig.patch.set_edgecolor("#b0b0b0")
        fig.patch.set_linewidth(0.8)

        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        canvas.setMinimumHeight(220)

        # Clear previous plot
        while self.verticalLayout.count():
            item = self.verticalLayout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        self.verticalLayout.addWidget(canvas, stretch=1)
        canvas.draw()

    def tr66_hydrograph(self, Qp, Tf, V, T_total, Qbase=0.0, dt_hr = 0.1):
        """
       TR66 (SCS, 1981) hydrograph (as in your table).

       Parameters
       ----------
       Qp : float
           Peak discharge (m3/s).
       Tf : float
           Rising-limb time threshold (hours).
       V : float
           Volume (m3).
       Qbase : float
           Base flow (m3/s).
       dt_hr : float
           Time step in hours (default 0.1 hr).

       Returns
       -------
       t_hr : np.ndarray
           Time vector (hours).
       Qt : np.ndarray
           Discharge vector (m3/s).
       """

        # Convert hours to seconds internally to match V/Qp units (m3)/(m3/s) = s
        Tf_s = Tf * 3600.0
        dt_s = dt_hr * 3600.0

        T_total = T_total * 3600.0  # total time in seconds

        # Number of steps
        n_steps = int(np.floor(T_total / dt_s)) + 1

        # Time array in seconds and hours
        t_s = np.arange(n_steps, dtype=float) * dt_s
        t_hr = t_s / 3600.0

        # Build hydrograph
        Qt = np.empty_like(t_s)

        # Rising limb: t <= Tf
        mask_rise = t_s <= Tf_s
        Qt[mask_rise] = Qbase + Qp * (t_s[mask_rise] / Tf_s)

        # Falling limb: t > Tf
        mask_fall = ~mask_rise
        Qt[mask_fall] = Qbase + Qp * np.exp(-(t_s[mask_fall] - Tf_s) * (Qp / V))

        # Optional: clip any numerical negatives (can happen if Tp is large)
        Qt = np.maximum(Qt, 0.0)

        return t_hr, Qt

    def ana_lnec_hydrograph(self, Qp, Tf, T_total, Qbase=0.0, dt_hr=0.1, beta=10):
        """
        ANA LNEC Adaptado (Petry et al., 2018) hydrograph as in your table.

        Qt = Qbase + Qx * [ (t/tf) * exp(1 - t/tp) ]^beta

        Parameters
        ----------
        Qp : float
            Peak discharge (used to compute Qx).
        Tf : float
            Time to peak
        V : float
            Volume used to compute Qx (V > 0).
        Qbase : float
            Baseflow discharge.

        Returns
        -------
        t_hr : np.ndarray
           Time vector (hours).
        Qt : np.ndarray
           Discharge vector (m3/s).
        """

        Tf_s = Tf * 3600.0
        dt_s = dt_hr * 3600.0

        T_total = T_total * 3600.0  # total time in seconds

        n_steps = int(np.floor(T_total / dt_s)) + 1

        t_s = np.arange(n_steps, dtype=float) * dt_s
        t_hr = t_s / 3600.0

        x = t_s / Tf_s
        core = x * np.exp(1.0 - x)
        core = np.maximum(core, 0.0)

        Qt = Qbase + Qp * (core ** beta)

        return t_hr, Qt

    def triangular_hydrograph(self, Qp, Tf, T_total, Qbase=0.0):
        """
        Triangular hydrograph method.
        """
        # Convert hours to seconds internally to match V/Qp units (m3)/(m3/s) = s
        Tf_s = Tf * 3600.0
        T_total_s = T_total * 3600.0

        Q_ini = Qbase
        Q_end = Qbase

        Qt = [Q_ini, (Qp + Qbase), Q_end]
        t_hr = [0.0, Tf, T_total]

        return t_hr, Qt

    def parse_tailings_data_xml(self, xml_path):
        """
        Parse the Dataset1_HydrologicFailure XML file into a Python dictionary.
        """

        tree = ET.parse(xml_path)
        root = tree.getroot()

        data = {}

        for element in root:
            key = element.tag
            raw_value = element.text.strip() if element.text else None

            # Type inference (explicit and conservative)
            if raw_value is None:
                value = None

            elif raw_value.lower() in ("true", "false"):
                value = raw_value.lower() == "true"

            else:
                # Try numeric conversion
                try:
                    if "." in raw_value or "e" in raw_value.lower():
                        value = float(raw_value)
                    else:
                        value = int(raw_value)
                except ValueError:
                    # Fallback to string
                    value = raw_value

            data[key] = value

        return data

    def save_tailings_data(self):
        """
        Function to save the tailings breach data into an XML file following the structure of Dataset1_HydrologicFailure.xml.
        """
        s = QSettings()
        last_gpkg_dir = s.value("FLO-2D/lastGpkgDir", "")
        tailings_data_path, __ = QFileDialog.getSaveFileName(
            None, "Save tailings breach file as...", directory=last_gpkg_dir, filter="*.xml"
        )
        if not tailings_data_path:
            return

        if self.gutils.get_cont_par("METRIC") == "1":
            crs_system = "Metric"
        else:
            crs_system = "English"

        failure_mode = None
        failure = "No Breach"
        if self.hydrologic_grp.isChecked():
            failure_mode = "Hydrologic"
            failure = self.hyd_breach_type_lbl.text()
        if self.static_grp.isChecked():
            failure_mode = "Static"
            failure = self.static_breach_type_lbl.text()
        if self.seismic_grp.isChecked():
            failure_mode = "Seismic"
            failure = self.seismic_breach_type_lbl.text()

        spillway = False
        if self.spillway_chbox.isChecked():
            spillway = True

        foundation_soil = "Granular" if self.soil_bellow_base_cbo.currentIndex() == 0 else "Cohesive"

        slope_idx = self.tailings_dam_slope_cbo.currentIndex()
        slope = "DSR_151"
        if slope_idx == 0:
            slope = "DSR_151"
        elif slope_idx == 1:
            slope = "DSR_201"
        elif slope_idx == 2:
            slope = "DSR_251"
        elif slope_idx == 3:
            slope = "DSR_301"
        elif slope_idx == 4:
            slope = "DSR_351"
        elif slope_idx == 5:
            slope = "DSR_401"

        if self.reservoir_lvl_cbo.currentIndex() == 0:
            reservoir_lvl = "High"
        elif self.reservoir_lvl_cbo.currentIndex() == 1 :
            reservoir_lvl = "Medium"
        else:
            reservoir_lvl = "Low"

        if self.pore_pressure_cbo.currentIndex() == 0:
            pore_pressure = "HighHigh"
        elif self.pore_pressure_cbo.currentIndex() == 1:
            pore_pressure = "High"
        else:
            pore_pressure = "Low"

        if self.fine_content_cbo.currentIndex() == 0:
            fine_contents = "eFC_0"
        elif self.fine_content_cbo.currentIndex() == 1:
            fine_contents = "eFC_10"
        elif self.fine_content_cbo.currentIndex() == 2:
            fine_contents = "eFC_25"
        elif self.fine_content_cbo.currentIndex() == 3:
            fine_contents = "eFC_50"
        else:
            fine_contents = "eFC_75"

        params = {
            "m_units": crs_system,
            "m_fDamHeight": self.dam_height_2_dsb.value(),
            "m_fFreeboardFromSurface": self.water_surface_freeboard_dsb.value(),
            "m_fDepthToBedrock": self.depth_to_bedrock_dsb.value(),
            "m_fDepthToSaturatedTailings": self.depth_to_saturated_dsb.value(),
            "m_fMaxAllowableHead": self.max_allow_head_dsb.value(),
            "m_fPMGWSE": self.pmf_wse_dsb.value(),
            "m_fTotalImpoundmentVolume": self.tot_imp_vol_dsb.value(),
            "m_fImpoundedTailingsVolume": self.imp_tal_vol_dsb.value(),
            "m_fAvailableStorage": self.available_storage_le.text(),
            "m_fInputFloodEventVolume": self.input_flood_volume_dsb.value(),
            "m_fUnitWeightOfFoundation": self.unit_weight_found_dsb.value(),
            "m_fUnitWeights": self.unit_weight_dam_dsb.value(),
            "m_fCohesion": self.cohesion_dam_material_dsb.value(),
            "m_Vrmax": self.vrmax_le.text(),
            "m_Vrmin": self.vrmin_le.text(),
            "m_Vaverage": self.vrave_le.text(),
            "m_Vuser": self.user_volume_le.text(),
            "m_Larrauri": self.larrauri_dsb.text(),
            "m_Rico": self.rico_dsb.text(),
            "m_Piciullo": self.piciullo1_dsb.text(),
            "m_Piciullo_B": self.piciullo2_dsb.text(),
            "m_fPeakDischarge": self.peak_discharge_le.text(),
            "m_fHydrographSedimentVolume": 0,
            "m_fSPTBlowCount": self.spt_count_sb.value(),
            "m_fFrictionAngle": self.friction_angle_dam_material_dsb.value(),
            "m_fEarthquakeMagnitude": self.eq_mag_dsb.value(),
            "m_fBlowCount": self.blow_continuous_dsb.value(),
            "m_fSValue": self.slope_failure_le.text(),
            "m_CYHValue": self.cydamh_le.text(),
            "m_fPeakGroundAcceleration": self.peak_ground_acc_dsb.value(),
            "m_fDepthToLayer": self.depth_to_layer_dsb.value(),
            "m_FailureMode": failure_mode,
            "m_Failure": failure,
            "m_bHaveSpillway": spillway,
            "m_FoundationSoil": foundation_soil,
            "m_DownstreamSlopeRatio": slope,
            "m_ReservoirLevel": reservoir_lvl,
            "m_PorePressure": pore_pressure,
            "m_FinesContent": fine_contents,
            "m_bContinuosSoftLayer": self.soft_lyr_chbox.isChecked(),
            "m_bDropHammer": True if self.drop_rb.isChecked() else False,
            "m_RecalculateReleaseVolumes": "", # TODO Check these later
            "m_InflowCells": "",
            "m_fEventTime": "",
            "m_fMaxSedContr": ""
        }

        # Root element must match exactly
        root = ET.Element("TailingDamModelPrivate")

        for key, value in params.items():
            element = ET.SubElement(root, key)

            # Convert Python types back to XML text
            if value is None:
                element.text = ""
            elif isinstance(value, bool):
                element.text = "true" if value else "false"
            else:
                element.text = str(value)

        self.indent_xml(root)

        tree = ET.ElementTree(root)

        tree.write(
            tailings_data_path,
            encoding="utf-8",
            xml_declaration=True
        )

        self.uc.log_info(f"Tailings breach data saved to {tailings_data_path}")
        self.uc.bar_info(f"Tailings breach data saved to {tailings_data_path}")

    def indent_xml(self, elem, level=0):
        i = "\n" + level * "    "

        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "    "

            for child in elem:
                self.indent_xml(child, level + 1)

            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i

    def open_tailings_data(self):
        """
        Function to open the tailings breach data XML file and populate the fields accordingly.
        The XML file should follow the structure of Dataset1_HydrologicFailure.xml as provided in the FLO-2D Preprocessor documentation.
        """
        s = QSettings()
        last_dir = s.value("FLO-2D/lastGpkgDir", "")
        tailings_data_path, __ = QFileDialog.getOpenFileName(
            None,
            "Select a tailings breach file with data to import",
            directory=last_dir,
            filter="*.xml",
        )
        if not tailings_data_path:
            return

        tailings_data = self.parse_tailings_data_xml(tailings_data_path)
        if self.gutils.get_cont_par("METRIC") == "1":
            crs_system = "Metric"
        else:
            crs_system = "English"

        if tailings_data["m_units"] != crs_system:
            self.uc.log_info(f"Units in the XML file ({tailings_data['m_units']}) do not match the project's CRS system ({crs_system}). Please check the units and try again.")
            self.uc.bar_error(f"Units in the XML file ({tailings_data['m_units']}) do not match the project's CRS system ({crs_system}). Please check the units and try again.")
            return

        self.dam_height_2_dsb.setValue(tailings_data["m_fDamHeight"])
        self.tot_imp_vol_dsb.setValue(tailings_data["m_fTotalImpoundmentVolume"])
        self.imp_tal_vol_dsb.setValue(tailings_data["m_fImpoundedTailingsVolume"])
        self.water_surface_freeboard_dsb.setValue(tailings_data["m_fFreeboardFromSurface"])
        self.depth_to_bedrock_dsb.setValue(tailings_data["m_fDepthToBedrock"])
        if tailings_data["m_FoundationSoil"] == "Granular":
            self.soil_bellow_base_cbo.setCurrentIndex(0)
        else:
            self.soil_bellow_base_cbo.setCurrentIndex(1)
        self.spt_count_sb.setValue(tailings_data["m_fSPTBlowCount"])
        self.unit_weight_found_dsb.setValue(tailings_data["m_fUnitWeightOfFoundation"])
        # self.tailings_material_cbo.
        self.depth_to_saturated_dsb.setValue(tailings_data["m_fDepthToSaturatedTailings"])
        # self.friction_angle_tailings_cbo
        # self.tailings_unit_weight_cbo
        # self.tailings_dam_material_cbo
        self.unit_weight_dam_dsb.setValue(tailings_data["m_fUnitWeights"])
        self.cohesion_dam_material_dsb.setValue(tailings_data["m_fCohesion"])
        self.friction_angle_dam_material_dsb.setValue(tailings_data["m_fFrictionAngle"])
        slope = tailings_data["m_DownstreamSlopeRatio"]
        if slope == "DSR_151":
            self.tailings_dam_slope_cbo.setCurrentIndex(0)
        elif slope == "DSR_201":
            self.tailings_dam_slope_cbo.setCurrentIndex(1)
        elif slope == "DSR_251":
            self.tailings_dam_slope_cbo.setCurrentIndex(2)
        elif slope == "DSR_301":
            self.tailings_dam_slope_cbo.setCurrentIndex(3)
        elif slope == "DSR_351":
            self.tailings_dam_slope_cbo.setCurrentIndex(4)
        elif slope == "DSR_401":
            self.tailings_dam_slope_cbo.setCurrentIndex(5)

        # Hydrologic
        self.input_flood_volume_dsb.setValue(tailings_data["m_fInputFloodEventVolume"])
        self.spillway_chbox.setChecked(tailings_data["m_bHaveSpillway"])
        self.max_allow_head_dsb.setValue(tailings_data["m_fMaxAllowableHead"])
        self.pmf_wse_dsb.setValue(tailings_data["m_fPMGWSE"])

        # Static
        reservoir_lvl = tailings_data["m_ReservoirLevel"]
        if reservoir_lvl == "High":
            self.reservoir_lvl_cbo.setCurrentIndex(0)
        elif reservoir_lvl == "Medium":
            self.reservoir_lvl_cbo.setCurrentIndex(1)
        elif reservoir_lvl == "Low":
            self.reservoir_lvl_cbo.setCurrentIndex(2)
        pore_pressure = tailings_data["m_PorePressure"]
        if pore_pressure == "HighHigh":
            self.pore_pressure_cbo.setCurrentIndex(0)
        elif pore_pressure == "High":
            self.pore_pressure_cbo.setCurrentIndex(1)
        elif pore_pressure == "Low":
            self.pore_pressure_cbo.setCurrentIndex(2)

        # Seismic
        self.eq_mag_dsb.setValue(tailings_data["m_fEarthquakeMagnitude"])
        self.peak_ground_acc_dsb.setValue(tailings_data["m_fPeakGroundAcceleration"])
        self.soft_lyr_chbox.setChecked(tailings_data["m_bContinuosSoftLayer"])
        self.depth_to_layer_dsb.setValue(tailings_data["m_fDepthToLayer"])
        self.blow_continuous_dsb.setValue(tailings_data["m_fBlowCount"])
        hammer_type = tailings_data["m_bDropHammer"]
        if hammer_type:
            self.drop_rb.setChecked(True)
            self.automatic_rb.setChecked(False)
        else:
            self.drop_rb.setChecked(False)
            self.automatic_rb.setChecked(True)
        fine_contents = tailings_data["m_FinesContent"]
        if fine_contents == "eFC_0":
            self.fine_content_cbo.setCurrentIndex(0)
        elif fine_contents == "eFC_10":
            self.fine_content_cbo.setCurrentIndex(1)
        elif fine_contents == "eFC_25":
            self.fine_content_cbo.setCurrentIndex(2)
        elif fine_contents == "eFC_50":
            self.fine_content_cbo.setCurrentIndex(3)
        elif fine_contents == "eFC_75":
            self.fine_content_cbo.setCurrentIndex(4)

        failure_mode = tailings_data["m_FailureMode"]
        if failure_mode in ["Hydrolic", "Hydrologic"]:
            self.hydrologic_grp.setChecked(True)
            self.static_grp.setChecked(False)
            self.seismic_grp.setChecked(False)
        elif failure_mode == "Static":
            self.hydrologic_grp.setChecked(False)
            self.static_grp.setChecked(True)
            self.seismic_grp.setChecked(False)
        elif failure_mode == "Seismic":
            self.hydrologic_grp.setChecked(False)
            self.static_grp.setChecked(False)
            self.seismic_grp.setChecked(True)

        # Save Options
        self.tal_event_time_le.setText(str(tailings_data["m_fEventTime"]))
        self.tal_max_sed_con_le.setText(str(tailings_data["m_fMaxSedContr"]))






