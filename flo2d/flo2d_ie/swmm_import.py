# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from itertools import izip_longest


class StormDrainProject(object):

    def __init__(self, inp_path):
        self.inp = inp_path
        self.ignore = ';\n'
        self.parts = {}
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
        sub_cols = ['subcatchment', 'raingage', 'outlet', 'total_area', 'imperv', 'width', 'slope', 'curb_length', 'snow_pack']
        subcachments = self.select_by_tag('subc')
        for sub in subcachments:
            if not sub or sub[0] in self.ignore:
                continue
            sub_dict = dict(izip_longest(sub_cols, sub.split()))
            out = sub_dict.pop('outlet')
            self.coordinates[out].update(sub_dict)

    def find_outlets(self):
        out_cols = ['outfall', 'invert_elev', 'out_type']
        outfalls = self.select_by_tag('outf')
        for out in outfalls:
            if not out or out[0] in self.ignore:
                continue
            out_dict = dict(izip_longest(out_cols, out.split()[:3]))
            outfall = out_dict.pop('outfall')
            self.coordinates[outfall].update(out_dict)


if __name__ == '__main__':
    pth = r'D:\GIS_DATA\UEFCC Baseline\swmm.inp'
    sdp = StormDrainProject(pth)
    sdp.split_by_tags()
    sdp.find_coordinates()
    sdp.find_inlets()
    sdp.find_outlets()
    coords = sdp.coordinates
    for k, v in coords.items():
        if 'out_type' in v:
            print(k, v)
