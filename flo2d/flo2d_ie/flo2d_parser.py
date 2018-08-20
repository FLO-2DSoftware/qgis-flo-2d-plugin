# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
from collections import OrderedDict, defaultdict
from itertools import izip, izip_longest, chain, repeat


class ParseDAT(object):
    """
    Parser object for handling FLO-2D "DAT" files.
    """
    def __init__(self):
        self.project_dir = None
        self.dat_files = {
            'CONT.DAT': None,
            'TOLER.DAT': None,
            'FPLAIN.DAT': None,
            'CADPTS.DAT': None,
            'MANNINGS_N.DAT': None,
            'TOPO.DAT': None,
            'INFLOW.DAT': None,
            'OUTFLOW.DAT': None,
            'RAIN.DAT': None,
            'RAINCELL.DAT': None,
            'INFIL.DAT': None,
            'EVAPOR.DAT': None,
            'CHAN.DAT': None,
            'CHANBANK.DAT': None,
            'XSEC.DAT': None,
            'HYSTRUC.DAT': None,
            'STREET.DAT': None,
            'ARF.DAT': None,
            'MULT.DAT': None,
            'SED.DAT': None,
            'LEVEE.DAT': None,
            'FPXSEC.DAT': None,
            'BREACH.DAT': None,
            'FPFROUDE.DAT': None,
            'SWMMFLO.DAT': None,
            'SWMMFLORT.DAT': None,
            'SWMMOUTF.DAT': None,
            'TOLSPATIAL.DAT': None,
            'SHALLOWN_SPATIAL.DAT':None,
            'WSURF.DAT': None,
            'WSTIME.DAT': None
        }
        self.cont_rows = [
            ['SIMUL', 'TOUT', 'LGPLOT', 'METRIC', 'IBACKUP', 'build'],
            ['ICHANNEL', 'MSTREET', 'LEVEE', 'IWRFS', 'IMULTC'],
            ['IRAIN', 'INFIL', 'IEVAP', 'MUD', 'ISED', 'IMODFLOW', 'SWMM'],
            ['IHYDRSTRUCT', 'IFLOODWAY', 'IDEBRV'],
            ['AMANN', 'DEPTHDUR', 'XCONC', 'XARF', 'FROUDL', 'SHALLOWN', 'ENCROACH'],
            ['NOPRTFP', 'DEPRESSDEPTH'],
            ['NOPRTC'],
            ['ITIMTEP', 'TIMTEP'],
            ['GRAPTIM']
        ]
        self.toler_rows = [
            ['TOLGLOBAL', 'DEPTOL', 'WAVEMAX'],
            ['COURCHAR_C', 'COURANTFP', 'COURANTC', 'COURANTST'],
            ['COURCHAR_T', 'TIME_ACCEL']
        ]

    def scan_project_dir(self, path):
        self.project_dir = os.path.dirname(path)
        for f in os.listdir(self.project_dir):
            fname = f.upper()
            if fname in self.dat_files:
                self.dat_files[fname] = os.path.join(self.project_dir, f)
            else:
                pass

    def _calculate_cellsize(self):
        fplain = self.dat_files['FPLAIN.DAT']
        cadpts = self.dat_files['CADPTS.DAT']
        neighbour = None
        side = 0

        with open(fplain) as fpl:
            for n in fpl.readline().split()[1:5]:
                if n != '0':
                    neighbour = int(n)
                    break
                else:
                    pass
                side += 1

        with open(cadpts) as cad:
            x1, y1 = cad.readline().split()[1:]
            for dummy in xrange(neighbour-2):
                cad.readline()
            x2, y2 = cad.readline().split()[1:]

        dtx = abs(float(x1) - float(x2))
        dty = abs(float(y1) - float(y2))
        cell_size = dty if side % 2 == 0 else dtx
        return cell_size

    def calculate_cellsize(self):
        cell_size = 0
        topo = self.dat_files['TOPO.DAT']
        if topo is None:
            return 0
        if not os.path.isfile(topo):
            return 0
        if not os.path.getsize(topo) > 0:
            return 0
        with open(topo) as top:
            first_coord = top.readline().split()[:2]
            first_x = float(first_coord[0])
            first_y = float(first_coord[1])
            top.seek(0)
            dx_coords = (abs(first_x - float(row.split()[0])) for row in top)
            try:
                size = min(dx for dx in dx_coords if dx > 0)
            except ValueError:
                top.seek(0)
                dy_coords = (abs(first_y - float(row.split()[1])) for row in top)
                size = min(dy for dy in dy_coords if dy > 0)
            cell_size += size
        return cell_size

    @staticmethod
    def single_parser(file1):
        with open(file1, 'r') as f1:
            for line in f1:
                row = line.split()
                if row:
                    yield row

    @staticmethod
    def double_parser(file1, file2):
        with open(file1, 'r') as f1, open(file2, 'r') as f2:
            for line1, line2 in izip(f1, f2):
                row = line1.split() + line2.split()
                if row:
                    yield row

    @staticmethod
    def fix_row_size(row, fix_size, default=None, index=None):
        loops = fix_size - len(row)
        if index is None:
            for dummy in range(loops):
                row.append(default)
        else:
            for dummy in range(loops):
                row.insert(index, default)

    def parse_cont(self):
        results = {}
        cont = self.dat_files['CONT.DAT']
        with open(cont, 'r') as f:
            for c, row in enumerate(self.cont_rows):
                if c == 0:
                    results.update(dict(izip_longest(row, f.readline().rstrip().split(None, 5))))
                elif c == 6 and results['ICHANNEL'] == '0':
                    results['NOPRTC'] = None
                elif c == 8 and results['LGPLOT'] == '0':
                    results['GRAPTIM'] = None
                else:
                    results.update(dict(izip_longest(row, f.readline().split())))
        return results

    def parse_toler(self):
        results = {}
        toler = self.dat_files['TOLER.DAT']
        with open(toler, 'r') as f:
            for row in self.toler_rows:
                results.update(dict(izip_longest(row, f.readline().split())))
        return results

    def parse_fplain_cadpts(self):
        fplain = self.dat_files['FPLAIN.DAT']
        cadpts = self.dat_files['CADPTS.DAT']
        results = self.double_parser(fplain, cadpts)
        return results

    def parse_mannings_n_topo(self):
        mannings_n = self.dat_files['MANNINGS_N.DAT']
        topo = self.dat_files['TOPO.DAT']
        results = self.double_parser(mannings_n, topo)
        return results

    def parse_inflow(self):
        inflow = self.dat_files['INFLOW.DAT']
        par = self.single_parser(inflow)
        head = dict(zip(['IHOURDAILY', 'IDEPLT'], next(par)))
        inf = OrderedDict()
        res = OrderedDict()
        gid = None
        for row in par:
            char = row[0]
            if char == 'C' or char == 'F':
                gid = row[-1]
                inf[gid] = OrderedDict([('row', row), ('time_series', [])])
            elif char == 'H':
                self.fix_row_size(row, 4)
                inf[gid]['time_series'].append(row)
            elif char == 'R':
                gid = row[1]
                res[gid] = OrderedDict([('row', row)])
            else:
                pass
        return head, inf, res

    def parse_outflow(self):
        outflow = self.dat_files['OUTFLOW.DAT']
        par = self.single_parser(outflow)
        data = OrderedDict()
        cur_gid = None
        for row in par:
            char = row[0]
            if char == 'K' or char == 'N' or char.startswith('O'):
                gid = row[1]
                cur_gid = gid
                if gid not in data:
                    data[gid] = {'K': 0, 'N': 0, 'O': 0, 'hydro_out': 0, 'qh_params': [], 'qh_data': [], 'time_series': []}
                else:
                    pass
                if char == 'N':
                    nostacfp = int(row[-1])
                    data[gid][char] = nostacfp + 1 if nostacfp == 1 else 1
                elif char[-1].isdigit():
                    data[gid]['hydro_out'] = char[-1]
                else:
                    data[gid][char[0]] = 1
            elif char == 'H':
                self.fix_row_size(row, 4)
                data[cur_gid]['qh_params'].append(row[1:])
            elif char == 'T':
                data[cur_gid]['qh_data'].append(row[1:])
            elif char == 'S':
                data[cur_gid]['time_series'].append(row[1:])
            else:
                pass
        return data

    def parse_rain(self):
        rain = self.dat_files['RAIN.DAT']
        head = ['IRAINREAL', 'IRAINBUILDING', 'RTT', 'RAINABS', 'RAINARF', 'MOVINGSTORM']
        par = self.single_parser(rain)
        line1 = next(par)
        line2 = next(par)
        data = OrderedDict(zip(head, chain(line1, line2)))
        time_series = []
        rain_arf = []
        for row in par:
            rainchar = row[0]
            if rainchar == 'R':
                time_series.append(row)
            elif data['MOVINGSTORM'] != '0' and 'RAINSPEED' not in data:
                rainspeed, iraindir = row
                data['RAINSPEED'] = rainspeed
                data['IRAINDIR'] = iraindir
            else:
                rain_arf.append(row)
            if 'RAINSPEED' not in data:
                data['RAINSPEED'] = None
                data['IRAINDIR'] = None
            else:
                pass
        return data, time_series, rain_arf

    def parse_raincell(self):
        rain = self.dat_files['RAINCELL.DAT']
        par = self.single_parser(rain)
        line1 = next(par)
        head = line1[:2]
        head.append(' '.join(line1[2:]))
        data = [row for row in par]
        return head, data

    def parse_infil(self):
        infil = self.dat_files['INFIL.DAT']
        line1 = ['INFMETHOD']
        line2 = ['ABSTR', 'SATI', 'SATF', 'POROS', 'SOILD', 'INFCHAN']
        line3 = ['HYDCALL', 'SOILALL', 'HYDCADJ']
        line5 = ['SCSNALL', 'ABSTR1']
        par = self.single_parser(infil)
        data = OrderedDict(zip(line1, next(par)))
        method = data['INFMETHOD']
        if method == '1' or method == '3':
            data.update(zip(line2, next(par)))
            data.update(zip(line3, next(par)))
            if data['INFCHAN'] == '1':
                data['HYDCXX'] = next(par)[0]
            else:
                pass
        else:
            pass
        chars = {'R': 4, 'F': 8, 'S': 3, 'C': 3, 'H': 5}
        for char in chars:
            data[char] = []
        for row in par:
            char = row[0]
            if char in chars:
                self.fix_row_size(row, chars[char])
                data[char].append(row[1:])
            elif char == 'I':
                self.fix_row_size(row, 3)
                data['FHORTONI'] = row[1]
                data['FHORTONF'] = row[2]
                data['DECAYA'] = row[3]
            else:
                data.update(zip(line5, row))
        return data

    def parse_evapor(self):
        evapor = self.dat_files['EVAPOR.DAT']
        par = self.single_parser(evapor)
        head = next(par)
        data = OrderedDict()
        month = None
        for row in par:
            if len(row) > 1:
                month = row[0]
                data[month] = {'row': row, 'time_series': []}
            else:
                data[month]['time_series'].extend(row)
        return head, data

    def parse_chan(self):
        chan = self.dat_files['CHAN.DAT']
        bank = self.dat_files['CHANBANK.DAT']
        xsec = self.dat_files['XSEC.DAT']
        par = self.single_parser(chan)  # Iterator to deliver lines of CHAN.DAT one by one.
        parbank = self.single_parser(bank)
        if xsec is not None:
            parxs = (['{0}'.format(xs[-1])] for xs in self.single_parser(xsec) if xs[0] == 'X')
        else:
            parxs = repeat([None])
        start = True
        segments = []
        wsel = []
        confluence = []
        noexchange = []
        shape = {'R': 8, 'V': 20, 'T': 10, 'N': 5}
        chanchar = ['C', 'E']
        for row in par:
            char = row[0]
            if char not in shape and char not in chanchar and len(row) > 2:
                self.fix_row_size(row, 4)
                segments.append(row)
                segments[-1].append([]) # Appends an empty list at end of 'segments' list.
            elif char in shape:
                fix_index = 2 if char == 'T' else None
                self.fix_row_size(row, shape[char], index=fix_index)
                rbank = next(parbank)[1:]
                xsec = next(parxs)[0:1] if char == 'N' else []
                segments[-1][-1].append(row + xsec + rbank)
            elif char == 'C':
                confluence.append(row)
            elif char == 'E':
                noexchange.append(row)
            else:
                if start is True:
                    wsel.append(row)
                    start = False
                else:
                    wsel[-1].extend(row)
                    start = True
        return segments, wsel, confluence, noexchange

    def parse_xsec(self):
        xsec = self.dat_files['XSEC.DAT']
        par = self.single_parser(xsec)
        key = ()
        data = OrderedDict()
        for row in par:
            if row[0] == 'X':
                key = (row[1], row[2])
                data[key] = []
            else:
                data[key].append(row)
        return data

    def parse_hystruct(self):
        hystruct = self.dat_files['HYSTRUC.DAT']
        par = self.single_parser(hystruct)
        data = []
        chars = {'S': 10, 'C': 6, 'R': 6, 'T': 4, 'F': 6, 'D': 3}
        for row in par:
            char = row[0]
            self.fix_row_size(row, chars[char])
            if char == 'S':
                params = defaultdict(list)
                row.append(params)
                data.append(row[1:])
            else:
                data[-1][-1][char].append(row[1:])
        return data

    def parse_street(self):
        street = self.dat_files['STREET.DAT']
        par = self.single_parser(street)
        head = next(par)
        data = []
        vals = slice(1, None)
        chars = {'N': 2, 'S': 5, 'W': 3}
        for row in par:
            char = row[0]
            self.fix_row_size(row, chars[char])
            if char == 'N':
                row.append([])
                data.append(row[vals])
            elif char == 'S':
                row.append([])
                data[-1][-1].append(row[vals])
            elif char == 'W':
                data[-1][-1][-1][-1].append(row[vals])
        return head, data

    def parse_arf(self):
        arf = self.dat_files['ARF.DAT']
        par = self.single_parser(arf)
        head = []
        data = defaultdict(list)
        arf_row = [1] * 9
        for row in par:
            char = row[0]
            if char == 'S':
                head.append(row[-1])
            elif char == 'T':
                row += arf_row
                data[char].append(row[1:])
            else:
                data['PB'].append(row)
        self.fix_row_size(head, 1)
        return head, data

    def parse_mult(self):
        mult = self.dat_files['MULT.DAT']
        par = self.single_parser(mult)
        head = next(par)
        self.fix_row_size(head, 8)
        data = []
        for row in par:
            self.fix_row_size(row, 5)
            data.append(row)
        return head, data

    def parse_sed(self):
        sed = self.dat_files['SED.DAT']
        par = self.single_parser(sed)
        data = defaultdict(list)
        vals = slice(1, None)
        chars = {'M': 7, 'C': 10, 'Z': 4, 'P': 3, 'D': 3, 'E': 2, 'R': 2, 'S': 5, 'N': 3, 'G': 3}
        for row in par:
            char = row[0]
            self.fix_row_size(row, chars[char])
            if char == 'Z' or char == 'S':
                row.append([])
                data[char].append(row[vals])
            elif char == 'P':
                data['Z'][-1][-1].append(row[vals])
            elif char == 'N':
                data['S'][-1][-1].append(row[vals])
            else:
                data[char].append(row[vals])
        return data

    def parse_levee(self):
        levee = self.dat_files['LEVEE.DAT']
        par = self.single_parser(levee)
        head = next(par)
        data = defaultdict(list)
        vals = slice(1, None)
        chars = {'L': 2, 'D': 3, 'F': 2, 'W': 8, 'C': 3, 'P': 4}
        for row in par:
            char = row[0]
            self.fix_row_size(row, chars[char])
            if char == 'L' or char == 'F':
                row.append([])
                data[char].append(row[vals])
            elif char == 'D':
                data['L'][-1][-1].append(row[vals])
            elif char == 'W':
                data['F'][-1][-1].append(row[vals])
            elif char == 'C':
                head.extend(row[vals])
            elif char == 'P':
                data[char].append(row[vals])
            else:
                pass
        self.fix_row_size(head, 4)
        return head, data

    def parse_fpxsec(self):
        fpxsec = self.dat_files['FPXSEC.DAT']
        par = self.single_parser(fpxsec)
        head = next(par)[-1]
        data = []
        for row in par:
            params = row[1:3]
            gids = row[3:]
            data.append([params, gids])
        return head, data

    def parse_breach(self):
        breach = self.dat_files['BREACH.DAT']
        par = self.single_parser(breach)
        data = defaultdict(list)
        for row in par:
            char = row[0][0]
            if char == 'B' and len(row) == 5:
                data['G'].append(row[1:])
            elif char == 'B' and len(row) == 3:
                data['D'].append(row[1:])
            elif char == 'G' or char == 'D':
                data[char][-1] += row[1:]
            else:
                data['F'].append(row[1:])
        chars = {'G': 32, 'D': 33, 'F': 3}
        for k in data.iterkeys():
            for row in data[k]:
                self.fix_row_size(row, chars[k])
        return data

    def parse_fpfroude(self):
        fpfroude = self.dat_files['FPFROUDE.DAT']
        par = self.single_parser(fpfroude)
        data = [row[1:] for row in par]
        return data

    def parse_swmmflo(self):
        swmmflo = self.dat_files['SWMMFLO.DAT']
        par = self.single_parser(swmmflo)
        data = [row for row in par]
        return data

    def parse_swmmflort(self):
        swmmflort = self.dat_files['SWMMFLORT.DAT']
        par = self.single_parser(swmmflort)
        data = []
        for row in par:
            char = row[0]
            if char == 'D':
                row.append([])
                data.append(row[1:])
            else:
                data[-1][-1].append(row[1:])
        return data

    def parse_swmmoutf(self):
        swmmoutf = self.dat_files['SWMMOUTF.DAT']
        par = self.single_parser(swmmoutf)
        data = [row for row in par]
        return data

    def parse_tolspatial(self):
        tolspatial = self.dat_files['TOLSPATIAL.DAT']
        par = self.single_parser(tolspatial)
        data = [row for row in par]
        return data

    def parse_wsurf(self):
        wsurf = self.dat_files['WSURF.DAT']
        par = self.single_parser(wsurf)
        head = next(par)[0]
        data = []
        for row in par:
            data.append(row)
        return head, data

    def parse_wstime(self):
        wstime = self.dat_files['WSTIME.DAT']
        par = self.single_parser(wstime)
        head = next(par)[0]
        data = []
        for row in par:
            data.append(row)
        return head, data
