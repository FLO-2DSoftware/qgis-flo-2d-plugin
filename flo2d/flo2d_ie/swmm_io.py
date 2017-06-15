# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from collections import OrderedDict
from itertools import izip_longest


class StormDrainProject(object):

    def __init__(self, inp_path):
        self.inp = inp_path
        self.ignore = ';\n'
        self.parts = OrderedDict()
        self.coordinates = {}

    def split_by_tags(self):
        with open(self.inp) as swmm_inp:
            for chunk in swmm_inp.read().split('['):
                try:
                    key, value = chunk.split(']')
                    self.parts[key] = value.split('\n')
                except ValueError:
                    continue

    def select_by_tag(self, chars):
        part = None
        for tag in self.parts.keys():
            low_tag = tag.lower()
            if low_tag.startswith(chars):
                part = self.parts[tag]
                break
            else:
                continue
        return part

    def update_by_tag(self, chars, new_part):
        for tag in self.parts.keys():
            low_tag = tag.lower()
            if low_tag.startswith(chars):
                self.parts[tag] = new_part
                break
            else:
                continue

    def reassemble_inp(self):
        with open(self.inp, 'w') as swmm_inp:
            for tag, part in self.parts.items():
                part[0] = '[{}]'.format(tag)
                swmm_inp.write('\n'.join(part))

    def update_junctions(self, junctions_dict):
        chars = 'junc'
        template = '{:<16} {:<10.2f} {:<10.5f} {:<10.2f} {:<10.2f} {:<10.2f}'
        junctions = self.select_by_tag(chars)
        new_junctions = []
        for jun in junctions:
            jun_vals = jun.split()
            try:
                key = jun_vals.pop(0)
            except IndexError:
                key = None
            if key is None or key not in junctions_dict:
                new_junctions.append(jun)
                continue
            new_values = [float(val) for val in jun_vals]
            updated_values = junctions_dict[key]
            new_values[0:2] = [updated_values['invert_elev'], updated_values['max_depth']]
            new_junctions.append(template.format(key, *new_values))
        self.update_by_tag(chars, new_junctions)

    def find_coordinates(self):
        coord_cols = ['node', 'x', 'y']
        coord_list = self.select_by_tag('coor')
        for coord in coord_list:
            if not coord or coord[0] in self.ignore:
                continue
            coord_dict = dict(izip_longest(coord_cols, coord.split()))
            node = coord_dict.pop('node')
            self.coordinates[node] = coord_dict

    def find_inlets(self):
        sub_cols = [
            'subcatchment', 'raingage', 'outlet', 'total_area', 'imperv', 'width', 'slope', 'curb_length', 'snow_pack'
        ]
        subcachments = self.select_by_tag('subc')
        for sub in subcachments:
            if not sub or sub[0] in self.ignore:
                continue
            sub_dict = dict(izip_longest(sub_cols, sub.split()))
            out = sub_dict.pop('outlet')
            self.coordinates[out].update(sub_dict)

    def find_outlets(self):
        out_cols = ['outfall', 'invert_elev_out', 'out_type']
        outfalls = self.select_by_tag('outf')
        for out in outfalls:
            if not out or out[0] in self.ignore:
                continue
            out_dict = dict(izip_longest(out_cols, out.split()[:3]))
            outfall = out_dict.pop('outfall')
            self.coordinates[outfall].update(out_dict)

    def find_junctions(self):
        jun_cols = ['junction', 'invert_elev', 'max_depth', 'init_depth', 'surcharge_depth', 'ponded_area']
        junctions = self.select_by_tag('junc')
        for jun in junctions:
            if not jun or jun[0] in self.ignore:
                continue
            jun_dict = dict(izip_longest(jun_cols, jun.split()))
            junction = jun_dict.pop('junction')
            self.coordinates[junction].update(jun_dict)


if __name__ == '__main__':
    sd = StormDrainProject(r'D:\GIS_DATA\FLO-2D PRO Documentation\SWMM_examples\SWMM Lesson\swmm.inp')
    sd.split_by_tags()
    sd.find_coordinates()
    sd.find_inlets()
    sd.find_outlets()
    sd.find_junctions()
    nd = {}
    for k, v in sd.coordinates.items():
        if 'subcatchment' in v and 'invert_elev' in v:
            nd[k] = {'invert_elev': 1000, 'max_depth': 5.555}
    sd.update_junctions(nd)
    sd.reassemble_inp()
    for v in sd.parts['JUNCTIONS']:
        print(v)
