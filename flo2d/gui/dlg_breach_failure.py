import math

from qgis._core import QgsMessageLog

from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils

uiDialog, qtBaseClass = load_ui("failure_modes")


class BreachFailureDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.con = con
        self.gutils = GeoPackageUtils(con, iface)
        self.setupUi(self)

        self.dam_height = None

        # Hydrologic
        self.input_flood_volume_dsb.valueChanged.connect(self.check_hydrologic_failure)
        self.spillway_chbox.stateChanged.connect(self.check_hydrologic_failure)
        self.max_allow_head_dsb.valueChanged.connect(self.check_hydrologic_failure)
        self.pmf_wse_dsb.valueChanged.connect(self.check_hydrologic_failure)

        # Static
        self.reservoir_lvl_cbo.currentIndexChanged.connect(self.check_static_failure)
        self.cohesion_dam_material_dsb.valueChanged.connect(self.check_static_failure)
        self.unit_weight_dam_dsb.valueChanged.connect(self.check_static_failure)
        self.soil_bellow_base_cbo.currentIndexChanged.connect(self.check_static_failure)
        self.spt_count_sb.valueChanged.connect(self.check_static_failure)

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

        self.populate_units_lbls()

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

        self.close_btn.clicked.connect(self.close_dialog)

    def close_dialog(self):
        """
        Function to close the dialog.
        """
        self.close()

    def check_static_failure(self):
        """
        Function to check for static failure of tailings dams.
        """

        cohesion_dam_material = self.cohesion_dam_material_dsb.value()
        unit_weight_dam = self.unit_weight_dam_dsb.value()

        if unit_weight_dam <= 0:
            cydamh = ""
        else:
            cydamh = str(round(cohesion_dam_material / (unit_weight_dam * self.dam_height), 4))

        self.cydamh_le.setText(cydamh)

        friction_angle_dam_material = self.friction_angle_dam_material_dsb.value()
        reservoir_lvl = self.reservoir_lvl_cbo.currentIndex()
        tailings_dam_slope = self.tailings_dam_slope_cbo.currentIndex()

        slope, level = self.slope_lvl_table[(reservoir_lvl, tailings_dam_slope)]

        slope_failure = slope * friction_angle_dam_material + level

        self.slope_failure_le.setText(str(round(slope_failure, 4)))

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
        elif foundation_soil == 1:  # Cohesive
            if spt_count < 8:
                breach_type = "Dam Breach by Foundation Failure"

        if cydamh < slope_failure:
            breach_type = "Dam Breach by Slope Instability"

        self.static_breach_type_lbl.setText(breach_type)

    def check_hydrologic_failure(self):
        """
        Function to check for hydrologic failure of tailings dams.
        """

        available_storage = float(self.available_storage_le.text())
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
        unit_weight_dam = self.unit_weight_dam_2_dsb.value()
        unit_weight_found = self.unit_weight_found_dsb.value()
        freeboard_from_surface = self.water_surface_freeboard_dsb.value()

        total_stress = depth_to_layer * (
                    unit_weight_dam * self.dam_height + unit_weight_found * (depth_to_layer - self.dam_height))
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
            deformation_of_crest = (self.dam_height + depth_to_bedrock) * math.exp(
                6.07 * peak_ground_acc + 0.57 * eq_mag - 8)
            if deformation_of_crest > freeboard_from_surface:
                breach_type = "Dam Breach by Deformation of Crest"

        self.seismic_breach_type_lbl.setText(str(breach_type))

    def populate_units_lbls(self):
        """
        Function to populate the units labels based on the metric/imperial setting
        """

        if self.gutils.get_cont_par("METRIC") == "1":

            self.aval_sto_unit_lbl.setText("m³")
            self.input_vol_unit_lbl.setText("m³")
            self.max_allow_head_unit_lbl.setText("m")
            self.pmf_unit_lbl.setText("m")
            self.depth_to_crest_unit_lbl.setText("m")

            self.dam_uw_unit_lbl.setText("KN/m³")
            self.dam_uw_unit_2_lbl.setText("KN/m³")
            self.cohesion_unit_lbl.setText("KN/m²")

            self.friction_angle_unit_lbl.setText("°")
            self.found_uw_unit_lbl.setText("KN/m³")

            self.wsf_unit_lbl.setText("m")

            self.depth_bedrock_unit_lbl.setText("m")
            self.depth_to_sat_unit_lbl.setText("m")

        else:

            self.aval_sto_unit_lbl.setText("yd³")
            self.input_vol_unit_lbl.setText("yd³")
            self.max_allow_head_unit_lbl.setText("ft")
            self.pmf_unit_lbl.setText("ft")
            self.depth_to_crest_unit_lbl.setText("ft")

            self.dam_uw_unit_lbl.setText("lb/ft³")
            self.dam_uw_unit_2_lbl.setText("lb/ft³")
            self.cohesion_unit_lbl.setText("lb/ft²")

            self.friction_angle_unit_lbl.setText("°")
            self.found_uw_unit_lbl.setText("lb/ft³")

            self.wsf_unit_lbl.setText("ft")

            self.depth_bedrock_unit_lbl.setText("ft")
            self.depth_to_sat_unit_lbl.setText("ft")
