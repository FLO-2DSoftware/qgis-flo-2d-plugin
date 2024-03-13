# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
from collections import OrderedDict
from itertools import chain, zip_longest

from qgis.PyQt.QtWidgets import QApplication

from ..user_communication import UserCommunication
from ..utils import float_or_zero


class StormDrainProject(object):
    def __init__(self, iface, inp_file):
        self.iface = iface
        self.uc = UserCommunication(iface, "FLO-2D")
        self.inp_file = inp_file
        self.ignore = ";\n"
        self.INP_groups = OrderedDict()  # ".INP_groups" will contain all groups [xxxx] in .INP file,
        # ordered as entered.
        self.INP_nodes = {}
        self.INP_storages = {}
        self.INP_inflows = {}
        self.INP_patterns = []
        self.INP_timeseries = []
        self.INP_conduits = {}

        self.INP_pumps = {}
        self.INP_curves = []

        self.INP_orifices = {}
        self.INP_weirs = {}

        self.status_report = ""

    def split_INP_groups_dictionary_by_tags(self):
        """
        Creates an ordered dictionary INP_groups with all groups in [xxxx] .INP

        At the end, INP_groups will be a dictionary of lists of strings, with keys like
            ...
            SUBCATCHMENTS
            SUBAREAS
            INFILTRATION
            JUNCTIONS
            OUTFALLS
            CONDUITS
            etc.

        """
        try:
            with open(self.inp_file) as swmm_inp:  # open(file, mode='r',...) defaults to mode 'r' read.
                for chunk in swmm_inp.read().split(
                    "["
                ):  #  chunk gets all text (including newlines) until next '[' (may be empty).
                    try:
                        key, value = chunk.split("]")  # divide chunk into:
                        # key = name of group (e.g. JUNCTIONS) and
                        # value = rest of text until ']'
                        self.INP_groups[key] = value.split(
                            "\n"
                        )  # add new item {key, value.split('\n')} to dictionary INP_groups.
                        # E.g.:
                        #   key:
                        #     JUNCTIONS
                        #   value.split('\n') is list of strings:
                        #    I1  4685.00    6.00000    0.00       0.00       0.00
                        #    I2  4684.95    6.00000    0.00       0.00       0.00
                        #    I3  4688.87    6.00000    0.00       0.00       0.00

                    except ValueError:
                        continue
            try:
                return len(self.INP_groups["COORDINATES"])
            except Exception as e:
                return 3

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 170618.0611: construction of INP dictionary failed!", e)
            return 0

    def select_this_INP_group(self, chars):
        """Returns the whole .INP group [´chars'xxx]

        ´chars' is the  beginning of the string. Only the first 4 or 5 lower case letters are used in all calls.
        Returns a list of strings of the whole group, one list item for each line of the original .INP file.

        """
        part = None
        for tag in list(self.INP_groups.keys()):
            low_tag = tag.lower()
            if low_tag.startswith(chars):
                part = self.INP_groups[tag]
                break
            else:
                continue
        return part  # List of strings in .INT_groups dictionary item keyed by 'chars' (e.e.´junc', 'cond', 'outf',...)

    def update_tag_in_INP_groups(self, tag_to_update, new_part):
        """
        Find group 'tag_to_update' in INP_groups, and replace it with new_part list.
        """
        for tag in list(self.INP_groups.keys()):  # Go thru all groups
            low_tag = tag.lower()
            if low_tag.startswith(tag_to_update):
                self.INP_groups[tag] = new_part
                break
            else:
                continue

    def write_INP(self):
        with open(self.inp_file, "w") as swmm_inp_file:
            for tag, part in list(
                self.INP_groups.items()
            ):  # The iterator self.INP_groups.items() contains all groups of .INP file
                part[0] = "[{}]".format(tag)
                swmm_inp_file.write("\n".join(part))

    #         with open(self.inp_file, 'w') as swmm_inp_file:
    #             for tag, part in list(self.INP_groups.items()): # The iterator self.INP_groups.items() contains all groups of .INP file
    #                 part[0] = '[{}]'.format(tag)
    #                 swmm_inp_file.write('\n'.join(part))

    def update_JUNCTIONS_in_INP_groups_dictionary(self, junctions_dict):
        """
        Replace values in INP_groups for the [JUNCTIONS] group.

        The parameter junctions_dict is a dictionary of dictionaries, keyed by the junction name (e.g. 'I12', 'J3',..),
        containing for each junction name, its variables values.
        E.g. {'I3':   {'junction_invert_elev': 3456.9, 'max_depth': 7.3, 'ponded_area': 67.24, etc}
              'I467': {'junction_invert_elev': 132.2, 'max_depth': 8.21, 'ponded_area': 45.2, etc}

        """

        template = "{:<16} {:<10.2f} {:<10.5f} {:<10.2f} {:<10.2f} {:<10.2f}"
        junctions = self.select_this_INP_group("junc")  # 'junctions' contains a list of strings of each line of the
        # group [JUNCTIONS] in .INP file
        new_junctions = []
        for jun in junctions:  # For each line string 'jun' in 'junctions' list.
            jun_vals = (
                jun.split()
            )  # Creates list jun_vals by splitting jun into strings (those separated by whitespace)
            try:
                key = jun_vals.pop(0)  # Removes first element of list jun_vals (updates jun_val), and returns
                # that first element to the variable key. (First element is name of junction).
            except IndexError:
                key = None

            if key is None or key not in junctions_dict:
                new_junctions.append(jun)
                continue
            new_values = [float(val) for val in jun_vals]  # Iterate over all items in jun_val strings list, change
            # them to float,and add to the new list 'new_values' of float values.
            updated_values = junctions_dict[
                key
            ]  # Get single item of junctions_dict, keyed by key, assign to 'updated_values'.

            new_values = [
                updated_values["junction_invert_elev"],
                updated_values["max_depth"],
                updated_values["init_depth"],
                updated_values["surcharge_depth"],
                updated_values["ponded_area"],
            ]

            # Transform 'new_values' list into single string, and append it to end of 'new_junctions' list of strings:
            new_junctions.append(template.format(key, *new_values))

        # Finally update keyed element 'JUNCTIONS' of INP_groups dictionary:
        self.update_tag_in_INP_groups("junc", new_junctions)

    def update_OUTFALLS_in_INP_groups_dictionary(self, outfalls_dict):
        """
        Replace values in INP_groups for the [OUTFALLS] group.

        The parameter outfalls_dict is a dictionary of dictionaries, keyed by the outfall name (e.g. 'OUT1', 'OUT2',..),
        containing for each junction name, its variables values.
        E.g. {'OUT3':   {'outfall_invert_elev': 3456.9, 'outfall_type': ´FREE', 'tidal_curve': ´'name_st1', etc}
              'OUT4':   {'outfall_invert_elev': 4344.9, 'outfall_type': ´TIDAL', 'tidal_curve': ´'name_st2', etc}

        """

        template = "{:<16} {:<10.2f} {:<10} {:<10} {:<10}"
        outfalls = self.select_this_INP_group("outf")  # 'outfalls' contains a list of strings of each line of the
        # group 'OUTFALLS' in .INP_groups.
        new_outfalls = []
        for out in outfalls:  # For each line string 'out' in 'outfalls' list.
            out_vals = (
                out.split()
            )  # Creates list 'out_vals' by splitting 'out' into strings (those separated by whitespace)
            try:
                key = out_vals.pop(0)  # Removes first element of list 'out_vals', updates 'out_vals', and returns
                # that first element to the variable key. (First element is name of outfall).
            except IndexError:
                key = None

            if key is None or key not in outfalls_dict:
                new_outfalls.append(out)
                continue
            new_values = [val for val in out_vals]  # Iterate over all items in 'out_vals' strings list,
            # and add to the new list 'new_values' of float values.
            updated_values = outfalls_dict[key]  # Get single item of outfalls_dict, keyed by key.

            new_values = [
                updated_values["outfall_invert_elev"],
                updated_values["outfall_type"],
                updated_values["tidal_curve"],
                updated_values["flapgate"],
            ]

            # Transform 'new_values' list into single string according to template, and append it to end of 'new_outfalls' list of strings:
            new_outfalls.append(template.format(key, *new_values))

        # Finally update keyed element 'OUTFALLS' of INP_groups dictionary:
        self.update_tag_in_INP_groups("outf", new_outfalls)

    def update_CONDUITS_in_INP_groups_dictionary(self, conduits_dict):
        """
        Replace values in INP_groups for the [CONDUITS] group.

        The parameter conduits_dict is a dictionary of dictionaries, keyed by the conduit name (e.g. 'C9WT...', 'C11',..),
        containing for each conduit name, its variables values.
        E.g. {'C3':   {'conduit_inlet': 345, 'conduit_outlet': '5432', 'conduit_length': '45.8', etc}
              'C4':   {'conduit_inlet': 7645, 'conduit_outlet': '328', 'conduit_length': '87.7', etc}

        """

        template = "{:<16} {:<13} {:13} {:10.2f} {:10.3f} {:10.2f} {:10.2f} {:10.2f} {:10.2f}"
        conduits = self.select_this_INP_group("cond")  # 'outfalls' contains a list of strings of each line of the
        # group 'OUTFALLS' in .INP_groups.
        new_conduits = []
        for out in conduits:  # For each line string 'out' in 'conduits' list.
            out_vals = (
                out.split()
            )  # Creates list 'out_vals' by splitting 'out' into strings (those separated by whitespace)
            try:
                key = out_vals.pop(0)  # Removes first element of list 'out_vals', updates 'out_vals', and returns
                # that first element to the variable key. (First element is name of conduit).
            except IndexError:
                key = None

            if key is None or key not in conduits_dict:
                new_conduits.append(out)
                continue
            new_values = [val for val in out_vals]  # Iterate over all items in 'out_vals' strings list,
            # and add to the new list 'new_values' of float values.
            updated_values = conduits_dict[key]  # Get single item of conduits_dict, keyed by key.

            new_values = [
                updated_values["conduit_inlet"],
                updated_values["conduit_outlet"],
                updated_values["conduit_length"],
                updated_values["conduit_manning"],
                updated_values["conduit_inlet_offset"],
                updated_values["conduit_outlet_offset"],
                updated_values["conduit_init_flow"],
                updated_values["conduit_max_flow"],
            ]

            # Transform 'new_values' list into single string according to template, and append it to end of 'new_conduits' list of strings:
            new_conduits.append(template.format(key, *new_values))

        # Finally update keyed element 'CONDUITS' of INP_groups dictionary:
        self.update_tag_in_INP_groups("cond", new_conduits)

    def update_LOSSES_in_INP_groups_dictionary(self, losses_dict):
        """
        Replace values in INP_groups for the [LOSSES] group.

        The parameter losses_dict is a dictionary of dictionaries, keyed by the conduit name (e.g. 'C9WT...', 'C11',..),
        containing for each conduit name, its variables values.
        E.g. {'C3':   {'losses_inlet': 345, 'losses_outlet': '5432, etc}
              C4':   {'losses_inlet': 1345, 'losses_outlet': '344, etc}

        """

        template = "{:<16} {:10.2f} {:10.2f} {:10.2f} {:10}"
        losses = self.select_this_INP_group("loss")  # 'losses' contains a list of strings of each line of the
        # group 'LOSSES' in .INP_groups.
        new_losses = []
        for lo in losses:  # For each line string 'out' in 'losses' list.
            lo_vals = (
                lo.split()
            )  # Creates list 'lo_vals' by splitting 'out' into strings (those separated by whitespace)
            try:
                key = lo_vals.pop(0)  # Removes first element of list 'lo_vals', updates 'lo_vals', and returns
                # that first element to the variable key. (First element is name of conduit).
            except IndexError:
                key = None

            if key is None or key not in losses_dict:
                new_losses.append(lo)
                continue
            new_values = [val for val in lo_vals]  # Iterate over all items in 'lo_vals' strings list,
            # and add to the new list 'new_values' of float values.
            updated_values = losses_dict[key]  # Get single item of losses_dict, keyed by key.

            new_values = [
                updated_values["losses_inlet"],
                updated_values["losses_outlet"],
                updated_values["losses_average"],
                updated_values["losses_flapgate"],
            ]

            # Transform 'new_values' list into single string according to template, and append it to end of 'new_losses' list of strings:
            new_losses.append(template.format(key, *new_values))

        # Finally update keyed element 'LOSSES' of INP_groups dictionary:
        self.update_tag_in_INP_groups("loss", new_losses)

    def update_XSECTIONS_in_INP_groups_dictionary(self, xsections_dict):
        """
        Replace values in INP_groups for the [XSECTIONS] group.

        The parameter xsections_dict is a dictionary of dictionaries, keyed by the conduit name (e.g. 'C9WT...', 'C11',..),
        containing for each conduit name, its variables values.
        E.g. {'C3':   {'losses_inlet': 345, 'losses_outlet': '5432, etc}
              C4':   {'losses_inlet': 1345, 'losses_outlet': '344, etc}

        """

        template = "{:<16} {:10}  {:10.2f} {:10.2f} {:10.2f} {:10.2f} {:10.2f}"
        xsections = self.select_this_INP_group("xsec")  # 'xsections' contains a list of strings of each line of the
        # group 'LOSSES' in .INP_groups.
        new_xsections = []
        for xs in xsections:  # For each line string 'out' in 'xsections' list.
            xs_vals = (
                xs.split()
            )  # Creates list 'xs_vals' by splitting 'out' into strings (those separated by whitespace)
            try:
                key = xs_vals.pop(0)  # Removes first element of list 'xs_vals', updates 'xs_vals', and returns
                # that first element to the variable key. (First element is name of conduit).
            except IndexError:
                key = None

            if key is None or key not in xsections_dict:
                new_xsections.append(xs)
                continue
            new_values = [val for val in xs_vals]  # Iterate over all items in 'lo_vals' strings list,
            # and add to the new list 'new_values' of float values.
            updated_values = xsections_dict[key]  # Get single item of xsections_dict, keyed by key.

            new_values = [
                updated_values["xsections_shape"],
                updated_values["xsections_barrels"],
                updated_values["xsections_max_depth"],
                updated_values["xsections_geom2"],
                updated_values["xsections_geom3"],
                updated_values["xsections_geom4"],
            ]

            # Transform 'new_values' list into single string according to template, and append it to end of 'new_xsections' list of strings:
            new_xsections.append(template.format(key, *new_values))

        # Finally update keyed element 'XSECTIONS' of INP_groups dictionary:
        self.update_tag_in_INP_groups("xsec", new_xsections)

    def add_coordinates_INP_nodes_dictionary(self):
        try:
            coord_cols = ["node", "x", "y"]
            coord_list = self.select_this_INP_group(
                "coor"
            )  # coord_list is a copy of the whole [COORDINATES] group of .INP file.
            if len(coord_list) > 0:
                for coord in coord_list:
                    if not coord or coord[0] in self.ignore:
                        continue
                    coord_dict = dict(
                        zip_longest(coord_cols, coord.split())
                    )  # Creates one dictionary element {'node', x, y}
                    node = coord_dict.pop("node")
                    if node in self.INP_nodes:
                        self.INP_nodes[node].update(coord_dict)  # Inserts one new element to dictionary with key "node".
                        # At the end, it will have all elements from the [COORDINATES] group in .INP file.
                        # E.g:
                        # "self.INP_nodes":
                        # {'I1': {'x': '366976.000', 'y': '1185380.000'},
                        #  'I3': {'x': '366875.000', 'y': '1185664.000'},
                        #  'I2': {'x': '366969.000', 'y': '1185492.000'}, etc.

            return len(coord_list)

        except Exception as e:
            self.uc.bar_warn("WARNING 221121.1017: Reading coordinates from SWMM input data failed!")
            return 0

    def create_INP_storage_dictionary_with_storage(self):
        try:
            funct_and_infil_cols = [
                "name",
                "invert_elev",
                "max_depth" ,
                "init_depth" ,
                "storage_curve",
                "coefficient",
                "exponent",
                "constant",  
                "ponded_area",
                "evap_factor",
                "suction_head",
                "conductivity",
                "initial_deficit"                              
            ]


            funct_no_infil_cols = [
                "name",
                "invert_elev",
                "max_depth" ,
                "init_depth" ,
                "storage_curve",
                "coefficient",
                "exponent",
                "constant",  
                "ponded_area",
                "evap_factor"                            
            ]
                        
            tab_and_infil_cols = [
                "name",
                "invert_elev",
                "max_depth" ,
                "init_depth" ,
                "storage_curve",
                "curve_name", 
                "ponded_area",
                "evap_factor",
                "suction_head",
                "conductivity",
                "initial_deficit"                              
            ] 
            
            tab_no_infil_cols = [
                "name",
                "invert_elev",
                "max_depth" ,
                "init_depth" ,
                "storage_curve",
                "curve_name", 
                "ponded_area",
                "evap_factor"                            
            ]  
                                   
                                   
            storage = self.select_this_INP_group("stora")
            if storage:
                for strg in storage:
                    if not strg or strg[0] in self.ignore:
                        continue
                    split = strg.split()
                    if len(split) == 13:  # functional with infiltration
                        storage_dict = dict(zip_longest(funct_and_infil_cols, split ))
                    elif len(split) == 11: # tabular with infiltration
                        storage_dict = dict(zip_longest(tab_and_infil_cols, split))
                    elif len(split) == 10: # functional no infiltration
                        storage_dict = dict(zip_longest(funct_no_infil_cols, split))
                    elif len(split) == 8: # tabular no infiltration
                        storage_dict = dict(zip_longest(tab_no_infil_cols, split))
                    else:
                        self.status_report += "\u25E6 Wrong Storage unit '" + split[0] + "' in [STORAGE] group.\n\n"   
                        continue          
                    storage = storage_dict.pop("name")
                    self.INP_storages[storage] = storage_dict

        except Exception as e:
            self.uc.bar_warn("WARNING 290124.1840: Reading storage units from SWMM input data failed!")

    def add_coordinates_to_INP_storages_dictionary(self):
        try:
            coord_cols = ["node", "x", "y"]
            coord_list = self.select_this_INP_group(
                "coor"
            )  # coord_list is a copy of the whole [COORDINATES] group of .INP file.
            if len(coord_list) > 0:
                for coord in coord_list:
                    if not coord or coord[0] in self.ignore:
                        continue
                    coord_dict = dict(
                        zip_longest(coord_cols, coord.split())
                    )  # Creates one dictionary element {'node', x, y}
                    node = coord_dict.pop("node")
                    if node in self.INP_storages:
                        self.INP_storages[node].update(coord_dict)  # Inserts one new element to dictionary with key "node".
                        # At the end, it will have all elements from the [COORDINATES] group in .INP file.
                        # E.g:
                        # "self.INP_storages":
                        # {'I1': {'x': '366976.000', 'y': '1185380.000'},
                        #  'I3': {'x': '366875.000', 'y': '1185664.000'},
                        #  'I2': {'x': '366969.000', 'y': '1185492.000'}, etc.  
            
            # Remove storage units without coordinates:
            new_storages = {}
            for key, inner_dict in self.INP_storages.items():
                if "x" in inner_dict:
                    new_storages[key] = inner_dict
                else:
                    self.status_report += "\u25E6 Storage unit '" + key + "' in [STORAGE] group without coordinates in [COORDINATES] group.\n\n"    


            self.INP_storages = new_storages
            return len(self.INP_storages)

        except Exception as e:
            self.uc.bar_warn("WARNING 221121.1017: Reading coordinates from SWMM input data failed!")
            return 0

    def create_INP_conduits_dictionary_with_conduits(self):
        try:
            conduit_cols = [
                "conduit_name",
                "conduit_inlet",
                "conduit_outlet",
                "conduit_length",
                "conduit_manning",
                "conduit_inlet_offset",
                "conduit_outlet_offset",
                "conduit_init_flow",
                "conduit_max_flow",
            ]
            conduits = self.select_this_INP_group("condu")
            if conduits:
                for cond in conduits:
                    if not cond or cond[0] in self.ignore:
                        continue
                    conduit_dict = dict(zip_longest(conduit_cols, cond.split()))
                    conduit = conduit_dict.pop("conduit_name")
                    self.INP_conduits[conduit] = conduit_dict

                    if conduit_dict["conduit_inlet"] == "?" or conduit_dict["conduit_outlet"] == "?":
                        self.status_report += "\u25E6 Undefined Node (?) reference at \n   [CONDUITS]\n   " + cond + "\n\n"

        except Exception as e:
            self.uc.bar_warn("WARNING 221121.1018: Reading conduits from SWMM input data failed!")

    def create_INP_pumps_dictionary_with_pumps(self):
        try:
            pumps_cols = [
                "pump_name",
                "pump_inlet",
                "pump_outlet",
                "pump_curve",
                "pump_init_status",
                "pump_startup_depth",
                "pump_shutoff_depth",
            ]

            pumps = self.select_this_INP_group("pumps")
            if pumps:
                for p in pumps:
                    if not p or p[0] in self.ignore:
                        continue
                    pump_dict = dict(zip_longest(pumps_cols, p.split()))
                    pump = pump_dict.pop("pump_name")
                    self.INP_pumps[pump] = pump_dict
        except Exception:
            self.uc.bar_warn("WARNING 221121.1019: Reading pumps from SWMM input data failed!")

    def create_INP_orifices_dictionary_with_orifices(self):
        try:
            orifices_cols = [
                "ori_name",
                "ori_inlet",
                "ori_outlet",
                "ori_type",
                "ori_crest_height",
                "ori_disch_coeff",
                "ori_flap_gate",
                "ori_open_close_time",
            ]

            orifices = self.select_this_INP_group("orifices")
            if orifices:
                for ori in orifices:
                    if not ori or ori[0] in self.ignore:
                        continue
                    ori_dict = dict(zip_longest(orifices_cols, ori.split()))
                    orifice = ori_dict.pop("ori_name")
                    self.INP_orifices[orifice] = ori_dict
        except Exception as e:
            self.uc.show_error("WARNING 300322.0923: Reading orifices from SWMM input data failed!", e)

    def create_INP_weirs_dictionary_with_weirs(self):
        try:
            weirs_cols = [
                "weir_name",
                "weir_inlet",
                "weir_outlet",
                "weir_type",
                "weir_crest_height",
                "weir_disch_coeff",
                "weir_flap_gate",
                "weir_end_contrac",
                "weir_end_coeff",
            ]

            weirs = self.select_this_INP_group("weirs")
            if weirs:
                for we in weirs:
                    if not we or we[0] in self.ignore:
                        continue
                    weir_dict = dict(zip_longest(weirs_cols, we.split()))
                    weir = weir_dict.pop("weir_name")
                    self.INP_weirs[weir] = weir_dict
        except Exception as e:
            self.uc.show_error("WARNING 300322.0928: Reading weirs from SWMM input data failed!", e)

    def create_INP_curves_dictionary_with_curves(self):
        try:
            curves_cols = [
                "pump_curve_name",
                "pump_curve_type",
                "x_value",
                "y_value",
            ]

            curves = self.select_this_INP_group("curves")
            if curves:
                for c in curves:
                    if not c or c[0] in self.ignore:
                        continue
                    curve_list = list(zip_longest(curves_cols, c.split()))
                    curve_dict = dict(zip_longest(curves_cols, c.split()))
                    curve_name = curve_dict.pop("pump_curve_name")
                    if curve_name in self.INP_curves:
                        nxt = dict()
                        nxt[curve_list[0][1]] = curve_list[1:]
                        a_dict = dict(chain(self.INP_curves.items(), nxt.items()))
                        self.INP_curves = a_dict
                    else:
                        self.INP_curves[curve_name] = curve_dict

        except Exception as e:
            self.uc.show_error("ERROR 241121.0529: Reading pump curves from SWMM input data failed!", e)

    def add_LOSSES_to_INP_conduits_dictionary(self):
        try:
            losses_cols = [
                "conduit_name",
                "losses_inlet",
                "losses_outlet",
                "losses_average",
                "losses_flapgate",
            ]
            losses = self.select_this_INP_group("losses")
            if losses is not None:
                for lo in losses:
                    if not lo or lo[0] in self.ignore:
                        continue
                    losses_dict = dict(zip_longest(losses_cols, lo.split()))
                    loss = losses_dict.pop("conduit_name")
                    if loss in self.INP_conduits:
                        self.INP_conduits[loss].update(
                            losses_dict
                        )  # Adds new values (from "losses_dict" , that include the "losses_cols") to
                        # an already existing key in dictionary INP_conduits.
                    else:
                        self.status_report += "\u25E6 Undefined Link (" + loss + ") reference at \n   [LOSSES]\n" + lo + "\n\n"
        except Exception as e:
            self.uc.show_error(
                "ERROR 010422.0513: couldn't create a [LOSSES] group from storm drain .INP file!",
                e,
            )

    def add_XSECTIONS_to_INP_conduits_dictionary(self):
        try:
            xsections_cols = [
                "conduit_name",
                "xsections_shape",
                "xsections_max_depth",
                "xsections_geom2",
                "xsections_geom3",
                "xsections_geom4",
                "xsections_barrels",
            ]
            xsections = self.select_this_INP_group("xsections")
            if xsections is not None:
                for xs in xsections:
                    if not xs or xs[0] in self.ignore:
                        continue
                    xsections_dict = dict(zip_longest(xsections_cols, xs.split()))
                    xsec = xsections_dict.pop("conduit_name")

                    if xsec in self.INP_conduits:
                        self.INP_conduits[xsec].update(
                            xsections_dict
                        )  # Adds new values (from "xsections_dict" , that include the "xsections_cols") to
                        # an already existing key in dictionary INP_conduits.
                    elif xsec in self.INP_orifices:
                        pass
                    elif xsec in self.INP_weirs:
                        pass
                    else:
                        self.status_report += "\u25E6 Undefined Link (" + xsec + ") reference in [XSECTIONS] group\n   " + xs + "\n\n"

        except Exception as e:
            self.uc.show_error(
                "ERROR 170618.0456: couldn't create a [XSECTIONS] group from storm drain .INP file!",
                e,
            )

    def add_XSECTIONS_to_INP_orifices_dictionary(self):
        try:
            xsections_cols = [
                "orifice_name",
                "xsections_shape",
                "xsections_height",
                "xsections_width",
                "xsections_geom3",
                "xsections_geom4",
                "xsections_barrels",
            ]
            xsections = self.select_this_INP_group("xsections")
            if xsections is not None:
                for xs in xsections:
                    if not xs or xs[0] in self.ignore:
                        continue
                    xsections_dict = dict(zip_longest(xsections_cols, xs.split()))
                    xsec = xsections_dict.pop("orifice_name")

                    if xsec in self.INP_orifices:
                        self.INP_orifices[xsec].update(
                            xsections_dict
                        )  # Adds new values (from "xsections_dict" , that include the "xsections_cols") to
                        # an already existing key in dictionary INP_orifices.

        except Exception as e:
            self.uc.show_error(
                "ERROR 310322.1014: couldn't create a [XSECTIONS] group from storm drain .INP file!",
                e,
            )

    def add_XSECTIONS_to_INP_weirs_dictionary(self):
        try:
            xsections_cols = [
                "weir_name",
                "xsections_shape",
                "xsections_height",
                "xsections_width",
                "xsections_geom3",
                "xsections_geom4",
                "xsections_barrels",
            ]
            xsections = self.select_this_INP_group("xsections")
            if xsections is not None:
                for xs in xsections:
                    if not xs or xs[0] in self.ignore:
                        continue
                    xsections_dict = dict(zip_longest(xsections_cols, xs.split()))
                    xsec = xsections_dict.pop("weir_name")

                    if xsec in self.INP_weirs:
                        self.INP_weirs[xsec].update(
                            xsections_dict
                        )  # Adds new values (from "xsections_dict" , that include the "xsections_cols") to
                        # an already existing key in dictionary INP_weirs.

        except Exception as e:
            self.uc.show_error(
                "ERROR 080422.1050: couldn't create a [XSECTIONS] group from storm drain .INP file!",
                e,
            )

    def add_SUBCATCHMENTS_to_INP_nodes_dictionary(self):
        try:
            subcatchments = None
            sub_cols = [
                "subcatchment",
                "raingage",
                "outlet",
                "total_area",
                "imperv",
                "width",
                "slope",
                "curb_length",
                "snow_pack",
            ]
            subcatchments = self.select_this_INP_group("subc")
            if subcatchments is not None:
                for sub in subcatchments:
                    if not sub or sub[0] in self.ignore:
                        continue
                    sub_dict = dict(
                        zip_longest(sub_cols, sub.split())
                    )  # creates dictionary 'sub_dict' with column names defined in 'sub_cols'
                    out = sub_dict.pop("outlet")  # out is the value of the key, i.e. "I37CP1WTRADL"
                    if out is not None:
                        self.INP_nodes[out].update(
                            sub_dict
                        )  # Adds new values (from "sub_dict" , that include the "sub_cols") to an already existing key in dictionary INP_nodes.
        except Exception as e:
            self.uc.show_error(
                "ERROR 080618.0456: couldn't update the inlets/junctions component using [SUBCATCHMENT] group from storm drain .INP file!",
                e,
            )
        finally:
            return subcatchments

    def add_OUTFALLS_to_INP_nodes_dictionary(self):
        try:
            out_cols = [
                "outfall",
                "outfall_invert_elev",
                "out_type",
                "series",
                "tide_gate",
            ]
            # out_cols = ['outfall', 'outfall_invert_elev', 'outfall_type', 'boundary_condition','flapgate' ]
            outfalls = self.select_this_INP_group(
                "outf"
            )  # Returns the whole [OUTFALLS] group. NOTE: Somehow 'outf' is used as key instead of 'OUTFALLS'. Why?
            if outfalls is not None:
                for out in outfalls:
                    if (not out) or (out[0] in self.ignore):
                        continue
                    items = out.split()
                    if not items:
                        continue
                    i0 = items[0]
                    i1 = items[1]
                    if items[2] == "TIDAL":
                        i2 = "TIDAL"
                    elif items[2] == "TIME":
                        i2 = "TIMESERIES"
                    else:
                        i2 = items[2]

                    if items[2] == "FIXED":
                        i3 = items[3]
                    elif items[2] == "TIDAL" or items[2] == "TIMESERIES":
                        i3 = items[3]
                    else:
                        i3 = ""

                    if "YES" in items:
                        i4 = "True"
                    else:
                        i4 = "False"

                    items = [i0, i1, i2, i3, i4]
                    out_dict = dict(zip_longest(out_cols, items))
                    outfall = out_dict.pop("outfall")
                    self.INP_nodes[outfall] = out_dict
        except Exception as e:
            self.uc.show_error(
                "ERROR 170618.0700: couldn't create a [OUTFALLS] group from storm drain .INP file!",
                e,
            )

    def add_JUNCTIONS_to_INP_nodes_dictionary(self):
        try:
            jun_cols = [
                "junction",
                "junction_invert_elev",
                "max_depth",
                "init_depth",
                "surcharge_depth",
                "ponded_area",
            ]
            jnctns = self.select_this_INP_group(
                "junc"
            )  # Returns the whole [JUNCTIONS] group from self.INP_groups. NOTE: Somehow 'junc' is used as key instead of 'JUNCTIONS'. Why?
            if jnctns is not None:
                for jun in jnctns:
                    if not jun or jun[0] in self.ignore:
                        continue
                    jun_dict = dict(zip_longest(jun_cols, jun.split()))
                    junction = jun_dict.pop("junction")
                    if junction is not None:
                        self.INP_nodes[junction]= jun_dict  # Adds to the key 'junction' the values in 'jun_dict' in dictionary 'INP_nodes'.
        except Exception as e:
            self.uc.show_error(
                "ERROR 170618.0701: couldn't create a [JUNCTIONS] group from storm drain .INP file!\n"
                + "                   Are coordinates missing?"
                + "\n__________________________________________________",
                e,
            )

    def create_INP_inflows_dictionary_with_inflows(self):
        try:
            inflows_cols = [
                "node_name",
                "constituent",
                "time_series_name",
                "param_type",
                "units_factor",
                "scale_factor",
                "baseline",
                "pattern_name",
            ]
            inflows = self.select_this_INP_group("inflow")
            if inflows:
                for infl in inflows:
                    if not infl or infl[0] in self.ignore:
                        continue                   
                    elif not (infl.split()[0] in self.INP_nodes or infl.split()[0] in self.INP_storages):
                        self.status_report += "\u25E6 Undefined Node reference (" + infl.split()[0] + ") at \n   [INFLOW]\n   " + infl + "\n\n"      
                    else:
                        inflow_dict = dict(zip_longest(inflows_cols, infl.split()))
                        inflow = inflow_dict.pop("node_name")
                        self.INP_inflows[inflow] = inflow_dict
        except Exception as e:
            self.uc.bar_warn("WARNING 221121.1021: Reading inflows from SWMM input data failed!")

    def create_INP_patterns_list_with_patterns(self):
        try:
            pattern_cols = [
                "pattern_name",
                "type",
                "mult1",
                "mult2",
                "mult3",
                "mult4",
                "mult5",
                "mult6",
                "mult7",
            ]
            patterns = self.select_this_INP_group("pattern")
            if patterns:
                for patt in patterns:
                    if not patt or patt[:2] in ";;\n":
                        continue
                    if patt[0] == ";":
                        descr = patt[1:]
                        continue
                    pattSplit = patt.split()
                    type = pattSplit[1].upper().strip()
                    if type in ["HOURLY", "MONTHLY", "DAILY", "WEEKEND"]:
                        pattern_list = list(zip_longest(pattern_cols, pattSplit))
                        name = pattSplit[0].strip()
                    else:
                        pattSplit.insert(1, pattern_list[2][1])
                        pattern_list = list(zip_longest(pattern_cols, pattSplit))
                    pattern_list.insert(0, ["description", descr])
                    self.INP_patterns.append(pattern_list)
        except Exception as e:
            self.uc.bar_warn("WARNING 221121.1020: Reading patterns from SWMM input data failed!")

    def create_INP_time_series_list_with_time_series(self):
        try:
            time_cols_file = ["time_series_name", "file", "file_name"]
            time_cols_date = ["name", "date", "time", "value"]
            times = self.select_this_INP_group("timeseries")
            warn = "WARNING 310323.0507:"
            descr = ""
            if times:
                for time in times:
                    if not time or time[:2] in ";;\n":
                        continue
                    if time[0] == ";":
                        descr = time[1:]
                        continue
                    timeSplit = time.split()
                    type = timeSplit[1].upper().strip()
                    if type == "FILE":
                        timeSplit2 = time.split('"')
                        timeSplit = [timeSplit[0], timeSplit[1], timeSplit2[1]]
                        time_list = list(zip_longest(time_cols_file, timeSplit))
                    else:
                        if len(timeSplit) < 4:
                            if len(timeSplit)== 3:
                                # One item missing, assume it's the date:
                                name = timeSplit[0]
                                date = "          "
                                time = timeSplit[1]
                                value = timeSplit[2]
                                timeSplit = [name, date, time, value]
                                time_list = list(zip_longest(time_cols_date, timeSplit))                                
                            else:
                                warn += "\nWrong [TIMESERIES] line: " + time
                                continue
                                # if warn == "":
                                #     if timeSplit[0] != name:
                                #         warn = "WARNING 310323.0507: Wrong data in [TIMESERIES] group!"
                                #         continue
                                #     else:
                                #         time = timeSplit[1]
                                #         value = timeSplit[2]
                                #         timeSplit = [name, date, time, value]
                                #         time_list = list(zip_longest(time_cols_date, timeSplit))
                        else:
                            name = timeSplit[0]
                            date = timeSplit[1]
                            time = timeSplit[2]
                            value = timeSplit[3]
                            timeSplit = [name, date, time, value]
                            time_list = list(zip_longest(time_cols_date, timeSplit))
                    time_list.insert(0, ["description", descr if descr is not None else ""])
                    self.INP_timeseries.append(time_list)
            if warn != "WARNING 310323.0507:":
                self.uc.show_warn(warn)
        except Exception as e:
            self.uc.bar_warn("WARNING 221121.1022: Reading time series from SWMM input data failed!")

    def create_INP_curves_list_with_curves(self):
        try:
            prev_type = ""
            msg = ""
            curves = self.select_this_INP_group("curves")
            if curves:
                for c in curves:
                    if not c or c[0] in self.ignore:
                        if c:
                            description = ""
                            if c[1]:
                                if c[1] != ";": # This is a description:
                                    description = c[1:]
                                    continue
                                else:
                                    continue 
                        else:
                            description = ""
                            continue    
                           
                    items = c.split()
                    if len(items) == 4:
                        prev_type = items[1]
                        items.insert(len(items),description)
                        self.INP_curves.append(items)
                    elif len(items) == 3:
                        items.insert(1, prev_type)
                        items.insert(len(items),description)
                        self.INP_curves.append(items)
                    else:
                        msg += c + "\n"

                if msg:
                    msg = (
                        "WARNING 251121.0538: error reading the following lines from [CURVES] group.\nMaybe curve names with spaces?:\n\n"
                        + msg
                    )
                    self.uc.show_warn(msg)

        except Exception as e:
            self.uc.show_error("ERROR 241121.0529: Reading pump curves from SWMM input data failed!", e)
