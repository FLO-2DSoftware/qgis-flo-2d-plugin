# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import traceback
from collections import OrderedDict
from itertools import izip_longest
from PyQt4.QtGui import QApplication
from ..user_communication import UserCommunication


class StormDrainProject(object):

    def __init__(self, iface, inp_file):
        self.iface = iface
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.inp_file = inp_file
        self.ignore = ';\n'
        self.INP_groups = OrderedDict() # ".INP_groups" will contain all groups [xxxx] in .INP file,
                                        # ordered as entered.
        self.INP_nodes = {}
        self.INP_conduits = {}

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
                for chunk in swmm_inp.read().split('['):  #  chunk gets all text (including newlines) until next '[' (may be empty).
                    try:
                        key, value = chunk.split(']')  # divide chunk into: 
                                                       # key = name of group (e.g. JUNCTIONS) and
                                                       # value = rest of text until ']'
                        self.INP_groups[key] = value.split('\n') # add new item {key, value.split('\n')} to dictionary INP_groups.
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
            except:
                return 0   
        
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 170618.0611: construction of INP dictionary failed!", e)
            return 0

    def select_this_INP_group(self, chars): 
        """ Returns the whole .INP group [´chars'xxx] 
        
        ´chars' is the  beginning of the string. Only the first 4 or 5 lower case letters are used in all calls.
        Returns a list of strings of the whole group, one list item for each line of the original .INP file.
                                         
        """
        part = None
        for tag in self.INP_groups.keys():
            low_tag = tag.lower()
            if low_tag.startswith(chars):
                part = self.INP_groups[tag]
                break     
            else:
                continue
        return part   # List of strings in .INT_groups dictionary item keyed by 'chars' (e.e.´junc', 'cond', 'outf',...)

    def update_tag_in_INP_groups(self, tag_to_update, new_part):
        """
        Find group 'tag_to_update' in INP_groups, and replace it with new_part list.
        """
        for tag in self.INP_groups.keys():  # Go thru all groups 
            low_tag = tag.lower()
            if low_tag.startswith(tag_to_update):
                self.INP_groups[tag] = new_part
                break
            else:
                continue

    def write_INP(self):
        with open(self.inp_file, 'w') as swmm_inp_file:
            for tag, part in self.INP_groups.items(): # The iterator self.INP_groups.items() contains all groups of .INP file
                part[0] = '[{}]'.format(tag)
                swmm_inp_file.write('\n'.join(part))

    def update_JUNCTIONS_in_INP_groups_dictionary(self, junctions_dict):
        """
        Replace values in INP_groups for the [JUNCTIONS] group.
        
        The parameter junctions_dict is a dictionary of dictionaries, keyed by the junction name (e.g. 'I12', 'J3',..),
        containing for each junction name, its variables values. 
        E.g. {'I3':   {'junction_invert_elev': 3456.9, 'max_depth': 7.3, 'ponded_area': 67.24, etc}
              'I467': {'junction_invert_elev': 132.2, 'max_depth': 8.21, 'ponded_area': 45.2, etc}
              
        """
        
        template = '{:<16} {:<10.2f} {:<10.5f} {:<10.2f} {:<10.2f} {:<10.2f}'
        junctions = self.select_this_INP_group('junc')  # 'junctions' contains a list of strings of each line of the 
                                                        # group [JUNCTIONS] in .INP file
        new_junctions = []
        for jun in junctions:  # For each line string 'jun' in 'junctions' list.
            jun_vals = jun.split()  # Creates list jun_vals by splitting jun into strings (those separated by whitespace)
            try:
                key = jun_vals.pop(0) # Removes first element of list jun_vals (updates jun_val), and returns 
                                      # that first element to the variable key. (First element is name of junction).
            except IndexError:
                key = None
                
            if key is None or key not in junctions_dict:
                new_junctions.append(jun)
                continue
            new_values = [float(val) for val in jun_vals]   # Iterate over all items in jun_val strings list, change 
                                                            # them to float,and add to the new list 'new_values' of float values.
            updated_values = junctions_dict[key]  # Get single item of junctions_dict, keyed by key, assign to 'updated_values'.
            
            new_values = [updated_values['junction_invert_elev'],
                          updated_values['max_depth'],
                          updated_values['init_depth'],
                          updated_values['surcharge_depth'],
                          updated_values['ponded_area']] 
            
            # Transform 'new_values' list into single string, and append it to end of 'new_junctions' list of strings:
            new_junctions.append(template.format(key, *new_values))
        
        # Finally update keyed element 'JUNCTIONS' of INP_groups dictionary:     
        self.update_tag_in_INP_groups('junc', new_junctions)

    def update_OUTFALLS_in_INP_groups_dictionary(self, outfalls_dict):
        """
        Replace values in INP_groups for the [OUTFALLS] group.
        
        The parameter outfalls_dict is a dictionary of dictionaries, keyed by the outfall name (e.g. 'OUT1', 'OUT2',..),
        containing for each junction name, its variables values. 
        E.g. {'OUT3':   {'outfall_invert_elev': 3456.9, 'outfall_type': ´FREE', 'tidal_curve': ´'name_st1', etc}
              'OUT4':   {'outfall_invert_elev': 4344.9, 'outfall_type': ´TIDAL CURVE', 'tidal_curve': ´'name_st2', etc}
              
        """

        template = '{:<16} {:<10.2f} {:<10} {:<10} {:<10}'
        outfalls = self.select_this_INP_group('outf')  # 'outfalls' contains a list of strings of each line of the 
                                                        # group 'OUTFALLS' in .INP_groups.
        new_outfalls = []
        for out in outfalls:  # For each line string 'out' in 'outfalls' list.
            out_vals = out.split()  # Creates list 'out_vals' by splitting 'out' into strings (those separated by whitespace)
            try:
                key = out_vals.pop(0) # Removes first element of list 'out_vals', updates 'out_vals', and returns 
                                      # that first element to the variable key. (First element is name of outfall).
            except IndexError:
                key = None
                
            if key is None or key not in outfalls_dict:
                new_outfalls.append(out)
                continue
            new_values = [val for val in out_vals]   # Iterate over all items in 'out_vals' strings list, 
                                                     # and add to the new list 'new_values' of float values.
            updated_values = outfalls_dict[key]  # Get single item of outfalls_dict, keyed by key.
            
            new_values = [updated_values['outfall_invert_elev'],
                          updated_values['outfall_type'],
                          updated_values['tidal_curve'],
                          updated_values['flapgate']]
            
            # Transform 'new_values' list into single string according to template, and append it to end of 'new_outfalls' list of strings:
            new_outfalls.append(template.format(key, *new_values))
        
        # Finally update keyed element 'OUTFALLS' of INP_groups dictionary:     
        self.update_tag_in_INP_groups('outf', new_outfalls)

    def update_CONDUITS_in_INP_groups_dictionary(self, conduits_dict):
        """
        Replace values in INP_groups for the [CONDUITS] group.
        
        The parameter conduits_dict is a dictionary of dictionaries, keyed by the conduit name (e.g. 'C9WT...', 'C11',..),
        containing for each conduit name, its variables values. 
        E.g. {'C3':   {'conduit_inlet': 345, 'conduit_outlet': '5432', 'conduit_length': '45.8', etc}
              'C4':   {'conduit_inlet': 7645, 'conduit_outlet': '328', 'conduit_length': '87.7', etc}
              
        """
        
        template = '{:<16} {:<13} {:13} {:10.2f} {:10.3f} {:10.2f} {:10.2f} {:10.2f} {:10.2f}'
        conduits = self.select_this_INP_group('cond')  # 'outfalls' contains a list of strings of each line of the 
                                                        # group 'OUTFALLS' in .INP_groups.
        new_conduits = []
        for out in conduits:  # For each line string 'out' in 'conduits' list.
            out_vals = out.split()  # Creates list 'out_vals' by splitting 'out' into strings (those separated by whitespace)
            try:
                key = out_vals.pop(0) # Removes first element of list 'out_vals', updates 'out_vals', and returns 
                                      # that first element to the variable key. (First element is name of conduit).
            except IndexError:
                key = None
                
            if key is None or key not in conduits_dict:
                new_conduits.append(out)
                continue
            new_values = [val for val in out_vals]   # Iterate over all items in 'out_vals' strings list,
                                                     # and add to the new list 'new_values' of float values.
            updated_values = conduits_dict[key]  # Get single item of conduits_dict, keyed by key.
            
            new_values = [updated_values['conduit_inlet'],
                          updated_values['conduit_outlet'],
                          updated_values['conduit_length'],
                          updated_values['conduit_manning'],
                          updated_values['conduit_inlet_offset'],
                          updated_values['conduit_outlet_offset'],
                          updated_values['conduit_init_flow'],
                          updated_values['conduit_max_flow']]
            
            # Transform 'new_values' list into single string according to template, and append it to end of 'new_conduits' list of strings:
            new_conduits.append(template.format(key, *new_values))
        
        # Finally update keyed element 'CONDUITS' of INP_groups dictionary:     
        self.update_tag_in_INP_groups('cond', new_conduits)

    def update_LOSSES_in_INP_groups_dictionary(self, losses_dict):
        """
        Replace values in INP_groups for the [LOSSES] group.
        
        The parameter losses_dict is a dictionary of dictionaries, keyed by the conduit name (e.g. 'C9WT...', 'C11',..),
        containing for each conduit name, its variables values. 
        E.g. {'C3':   {'losses_inlet': 345, 'losses_outlet': '5432, etc}
              C4':   {'losses_inlet': 1345, 'losses_outlet': '344, etc}
              
        """
        
        template = '{:<16} {:10.2f} {:10.2f} {:10.2f} {:10}'
        losses = self.select_this_INP_group('loss')  # 'losses' contains a list of strings of each line of the 
                                                        # group 'LOSSES' in .INP_groups.
        new_losses = []
        for lo in losses:  # For each line string 'out' in 'losses' list.
            lo_vals = lo.split()  # Creates list 'lo_vals' by splitting 'out' into strings (those separated by whitespace)
            try:
                key = lo_vals.pop(0) # Removes first element of list 'lo_vals', updates 'lo_vals', and returns 
                                      # that first element to the variable key. (First element is name of conduit).
            except IndexError:
                key = None
                
            if key is None or key not in losses_dict:
                new_losses.append(lo)
                continue
            new_values = [val for val in lo_vals]   # Iterate over all items in 'lo_vals' strings list, 
                                                     # and add to the new list 'new_values' of float values.
            updated_values = losses_dict[key]  # Get single item of losses_dict, keyed by key.
            
            new_values = [updated_values['losses_inlet'],
                          updated_values['losses_outlet'],
                          updated_values['losses_average'],
                          updated_values['losses_flapgate']]
            
            # Transform 'new_values' list into single string according to template, and append it to end of 'new_losses' list of strings:
            new_losses.append(template.format(key, *new_values))
        
        # Finally update keyed element 'LOSSES' of INP_groups dictionary:     
        self.update_tag_in_INP_groups('loss', new_losses)

    def update_XSECTIONS_in_INP_groups_dictionary(self, xsections_dict):
        """
        Replace values in INP_groups for the [XSECTIONS] group.
        
        The parameter xsections_dict is a dictionary of dictionaries, keyed by the conduit name (e.g. 'C9WT...', 'C11',..),
        containing for each conduit name, its variables values. 
        E.g. {'C3':   {'losses_inlet': 345, 'losses_outlet': '5432, etc}
              C4':   {'losses_inlet': 1345, 'losses_outlet': '344, etc}
              
        """
        
        template = '{:<16} {:10}  {:10.2f} {:10.2f} {:10.2f} {:10.2f} {:10.2f}'
        xsections = self.select_this_INP_group('xsec')  # 'xsections' contains a list of strings of each line of the 
                                                        # group 'LOSSES' in .INP_groups.
        new_xsections = []
        for xs in xsections:  # For each line string 'out' in 'xsections' list.
            xs_vals = xs.split()  # Creates list 'xs_vals' by splitting 'out' into strings (those separated by whitespace)
            try:
                key = xs_vals.pop(0) # Removes first element of list 'xs_vals', updates 'xs_vals', and returns 
                                      # that first element to the variable key. (First element is name of conduit).
            except IndexError:
                key = None
                
            if key is None or key not in xsections_dict:
                new_xsections.append(xs)
                continue
            new_values = [val for val in xs_vals]   # Iterate over all items in 'lo_vals' strings list, 
                                                     # and add to the new list 'new_values' of float values.
            updated_values = xsections_dict[key]  # Get single item of xsections_dict, keyed by key.
            
            new_values = [updated_values['xsections_shape'],
                          updated_values['xsections_barrels'],
                          updated_values['xsections_max_depth'],
                          updated_values['xsections_geom2'],
                          updated_values['xsections_geom3'],
                          updated_values['xsections_geom4']]
            
            # Transform 'new_values' list into single string according to template, and append it to end of 'new_xsections' list of strings:
            new_xsections.append(template.format(key, *new_values))
        
        # Finally update keyed element 'XSECTIONS' of INP_groups dictionary:     
        self.update_tag_in_INP_groups('xsec', new_xsections)

    def create_INP_nodes_dictionary_with_coordinates(self):
        try: 
            coord_cols = ['node', 'x', 'y']
            coord_list = self.select_this_INP_group('coor') # coord_list is a copy of the whole [COORDINATES] group of .INP file.
            if len(coord_list) > 0:
                for coord in coord_list:
                    if not coord or coord[0] in self.ignore:
                        continue
                    coord_dict = dict(izip_longest(coord_cols, coord.split())) # Creates one dictionary element {'node', x, y}
                    node = coord_dict.pop('node')
                    self.INP_nodes[node] = coord_dict  # Inserts one new element to dictionary with key "node".
                                                       # At the end, it will have all elements from the [COORDINATES] group in .INP file.
                                                       # E.g:                                                         
                                                       # "self.INP_nodes": 
                                                       # {'I1': {'x': '366976.000', 'y': '1185380.000'}, 
                                                       #  'I3': {'x': '366875.000', 'y': '1185664.000'}, 
                                                       #  'I2': {'x': '366969.000', 'y': '1185492.000'}, etc.  
            
            return len(coord_list)                                   
                                                  
        except Exception as e:
            self.uc.bar_warn('Reading coordinates from SWMM input data failed!') 
            return 0

    def create_INP_conduits_dictionary_with_conduits(self):
        try:
            conduit_cols = ['conduit_name', 'conduit_inlet', 'conduit_outlet', 'conduit_length', 'conduit_manning', 
                            'conduit_inlet_offset', 'conduit_outlet_offset', 'conduit_init_flow', 'conduit_max_flow']
            conduits = self.select_this_INP_group('condu')
            for cond in conduits:
                if not cond or cond[0] in self.ignore:
                    continue
                conduit_dict = dict(izip_longest(conduit_cols, cond.split()))
                conduit = conduit_dict.pop('conduit_name')
                self.INP_conduits[conduit] = conduit_dict
        except Exception as e:
            self.uc.bar_warn('Reading conduits from SWMM input data failed!') 

    def add_LOSSES_to_INP_conduits_dictionary(self):
        try:
            losses_cols = ['conduit_name', 'losses_inlet', 'losses_outlet', 'losses_average', 'losses_flapgate']
            losses = self.select_this_INP_group('losses')
            if losses is not None:
                for lo in losses:
                    if not lo or lo[0] in self.ignore:
                        continue
                    losses_dict = dict(izip_longest(losses_cols, lo.split()))
                    loss = losses_dict.pop('conduit_name')
                    self.INP_conduits[loss].update(losses_dict)  # Adds new values (from "losses_dict" , that include the "losses_cols") to 
                                                                 # an already existing key in dictionary INP_conduits.                    
        except Exception as e:
            self.uc.show_error("ERROR 170618.0701: couldn't create a [LOSSES] group from storm drain .INP file!", e)  

    def add_XSECTIONS_to_INP_conduits_dictionary(self):
        try:
            xsections_cols = ['conduit_name', 'xsections_shape', 'xsections_barrels', 'xsections_max_depth', 'xsections_geom2', 'xsections_geom3', 'xsections_geom4']
            xsections = self.select_this_INP_group('xsections')
            if xsections is not None:
                for xs in xsections:
                    if not xs or xs[0] in self.ignore:
                        continue
                    xsections_dict = dict(izip_longest(xsections_cols, xs.split()))
                    xsec = xsections_dict.pop('conduit_name')
                    self.INP_conduits[xsec].update(xsections_dict)  # Adds new values (from "xsections_dict" , that include the "xsections_cols") to 
                                                                 # an already existing key in dictionary INP_conduits.                    
        except Exception as e:
            self.uc.show_error("ERROR 1706180704.0456: couldn't create a [XSECTIONS] group from storm drain .INP file!", e)  

    def add_SUBCATCHMENTS_to_INP_nodes_dictionary(self):
        try:
            sub_cols = ['subcatchment', 'raingage', 'outlet', 'total_area', 'imperv', 'width', 'slope', 'curb_length', 'snow_pack']
            subcatchments = self.select_this_INP_group('subc')
            if subcatchments is not None:
                for sub in subcatchments:
                    if not sub or sub[0] in self.ignore:
                        continue
                    sub_dict = dict(izip_longest(sub_cols, sub.split())) # creates dictionary 'sub_dict' with column names defined in 'sub_cols'
                    out = sub_dict.pop('outlet')   # out is the value of the key, i.e. "I37CP1WTRADL"
                    self.INP_nodes[out].update(sub_dict)  # Adds new values (from "sub_dict" , that include the "sub_cols") to an already existing key in dictionary INP_nodes.
        except Exception as e:
            self.uc.show_error("ERROR 080618.0456: couldn't update the inlets/junctions component using [SUBCATCHMENT] group from storm drain .INP file!", e)    

    def add_OUTFALLS_to_INP_nodes_dictionary(self):
        try:
            out_cols = ['outfall', 'outfall_invert_elev', 'out_type', 'series','tide_gate' ]
            # out_cols = ['outfall', 'outfall_invert_elev', 'outfall_type', 'boundary_condition','flapgate' ]
            outfalls = self.select_this_INP_group('outf')  # Returns the whole [OUTFALLS] group. NOTE: Somehow 'outf' is used as key instead of 'OUTFALLS'. Why?
            if outfalls is not None:
                for out in outfalls:
                    if not out or out[0] in self.ignore:
                        continue
                    out_dict = dict(izip_longest(out_cols, out.split()))
                    outfall = out_dict.pop('outfall')
                    self.INP_nodes[outfall].update(out_dict)
        except Exception as e:
            self.uc.show_error("ERROR 170618.0700: couldn't create a [OUTFALLS] group from storm drain .INP file!", e)   

    def add_JUNCTIONS_to_INP_nodes_dictionary(self):
        try:
            jun_cols = ['junction', 'junction_invert_elev', 'max_depth', 'init_depth', 'surcharge_depth', 'ponded_area']
            jnctns = self.select_this_INP_group('junc')  # Returns the whole [JUNCTIONS] group from self.INP_groups. NOTE: Somehow 'junc' is used as key instead of 'JUNCTIONS'. Why?
            if jnctns is not None:
                for jun in jnctns:
                    if not jun or jun[0] in self.ignore:
                        continue
                    jun_dict = dict(izip_longest(jun_cols, jun.split()))
                    junction = jun_dict.pop('junction')
                    self.INP_nodes[junction].update(jun_dict) # Adds to the key 'junction' the values in 'jun_dict' in dictionary 'INP_nodes'.
        except Exception as e:
            self.uc.show_error("ERROR 170618.0701: couldn't create a [JUNCTIONS] group from storm drain .INP file!", e)                       
