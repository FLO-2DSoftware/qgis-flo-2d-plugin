# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os
import re
from collections import OrderedDict, defaultdict
from itertools import chain, repeat, zip_longest
from operator import attrgetter
from typing import Any

import numpy as np
import pandas as pd

from ..flo2d_hdf5.hdf5_descriptions import CONTROL, GRID, NEIGHBORS, STORMDRAIN, BC, CHANNEL, HYSTRUCT, INFIL, RAIN, \
    REDUCTION_FACTORS, LEVEE, EVAPOR, FLOODPLAIN, GUTTER, TAILINGS, SPATIALLY_VARIABLE, MULT, SD, SEDIMENT, STREET, \
    MULTIDOMAIN, QGIS
from ..utils import Msge

try:
    import h5py
except ImportError:
    h5py = None # Define h5py as None when not installed to avoid NameError and allow custom error handling

class HDF5Group:
    def __init__(self, name: str):
        self.name = name
        self.datasets = {}

    def create_dataset(self, dataset_name: str, data: Any = None, update: bool = True):
        dataset = HDF5Dataset(name=dataset_name, data=data, group=self)
        if update:
            self.update_with_dataset(dataset)

    def update_with_dataset(self, dataset):
        if dataset.group != self:
            dataset.group = self
        self.datasets[dataset.name] = dataset


class HDF5Dataset:
    def __init__(self, name: str, data: Any = None, group: "HDF5Group" = None):
        self.name = name
        self.data = data
        self.group = group


class ParseHDF5:
    """
    Parser object for handling FLO-2D "HDF5" files.
    """

    def __init__(self):
        self.project_dir = None
        self.hdf5_filepath = None
        self.read_mode = "r"
        self.write_mode = "w"

    @property
    def control_group(self):
        group_name = "Input/Control Parameters"
        group = HDF5Group(group_name)
        return group

    @property
    def qgis_group(self):
        group_name = "Input/QGIS"
        group = HDF5Group(group_name)
        return group

    @property
    def tol_group(self):
        group_name = "Input/Tolerance"
        group = HDF5Group(group_name)
        return group

    @property
    def grid_group(self):
        group_name = "Input/Grid"
        group_datasets = ["GRIDCODE", "MANNING", "COORDINATES", "ELEVATION", "NEIGHBORS"]
        group = HDF5Group(group_name)
        for dataset_name in group_datasets:
            group.create_dataset(dataset_name, [])
        return group

    @property
    def bc_group(self):
        group_name = "Input/Boundary Conditions"
        group = HDF5Group(group_name)
        return group

    @property
    def infil_group(self):
        group_name = "Input/Infiltration"
        group = HDF5Group(group_name)
        return group

    @property
    def arfwrf_group(self):
        group_name = "Input/Reduction Factors"
        group = HDF5Group(group_name)
        return group

    @property
    def rain_group(self):
        group_name = "Input/Rainfall"
        group = HDF5Group(group_name)
        return group

    @property
    def levee_group(self):
        group_name = "Input/Levee"
        group = HDF5Group(group_name)
        return group

    @property
    def spatially_variable_group(self):
        group_name = "Input/Spatially Variable"
        group = HDF5Group(group_name)
        return group

    @property
    def hystruc_group(self):
        group_name = "Input/Hydraulic Structures"
        group = HDF5Group(group_name)
        return group

    @property
    def channel_group(self):
        group_name = "Input/Channels"
        group = HDF5Group(group_name)
        return group

    @property
    def SD_group(self):
        group_name = "Input/Storm Drain"
        group = HDF5Group(group_name)
        return group

    @property
    def mult_group(self):
        group_name = "Input/Multiple Channels"
        group = HDF5Group(group_name)
        return group

    @property
    def floodplain_group(self):
        group_name = "Input/Floodplain"
        group = HDF5Group(group_name)
        return group

    @property
    def sed_group(self):
        group_name = "Input/Mudflow and Sediment Transport"
        group = HDF5Group(group_name)
        return group

    @property
    def stormdrain_group(self):
        group_name = "Input/Storm Drain"
        group = HDF5Group(group_name)
        return group

    @property
    def evap_group(self):
        group_name = "Input/Evaporation"
        group = HDF5Group(group_name)
        return group

    @property
    def gutter_group(self):
        group_name = "Input/Gutter"
        group = HDF5Group(group_name)
        return group

    @property
    def tailings_group(self):
        group_name = "Input/Tailings"
        group = HDF5Group(group_name)
        return group

    @property
    def street_group(self):
        group_name = "Input/Street"
        group = HDF5Group(group_name)
        return group

    @property
    def multipledomain_group(self):
        group_name = "Input/Multiple Domains"
        group = HDF5Group(group_name)
        return group

    @property
    def groups(self):
        grouped_datasets_list = [
            self.control_group,
            self.grid_group,
            self.bc_group
        ]
        return grouped_datasets_list

    @property
    def groups_template(self):
        groups_template_dict = {group.name: group for group in self.groups}
        return groups_template_dict

    @staticmethod
    def write_group_datasets(hdf5_file, group):
        if group.name not in hdf5_file:
            hdf5_file.create_group(group.name)
        for dataset in sorted(group.datasets.values(), key=attrgetter("name")):
            hdf5_group = hdf5_file[group.name]
            ds = hdf5_group.create_dataset(dataset.name, data=dataset.data, compression="gzip")
            attributes_dicts = [CONTROL, GRID, NEIGHBORS, STORMDRAIN, BC, CHANNEL, HYSTRUCT, INFIL, RAIN,
                                REDUCTION_FACTORS, LEVEE, EVAPOR, FLOODPLAIN, GUTTER, TAILINGS, SPATIALLY_VARIABLE,
                                MULT, SD, SEDIMENT, STREET, MULTIDOMAIN, QGIS]

            for attributes_dict in attributes_dicts:
                if dataset.name in attributes_dict:
                    ds.attrs[dataset.name] = attributes_dict[dataset.name]

    def write_groups(self, *groups):
        with h5py.File(self.hdf5_filepath, self.write_mode) as f:
            for group in groups:
                self.write_group_datasets(f, group)

    def write(self, dataset):
        with h5py.File(self.hdf5_filepath, self.write_mode) as f:
            group = dataset.group
            if group:
                try:
                    group = f[group.name]
                except KeyError:
                    group = f.create_group(group.name)
                root = group
            else:
                root = f
            root.create_dataset(dataset.name, data=dataset.data)

    def read_groups(self, *group_names):
        groups_list = []
        with h5py.File(self.hdf5_filepath, self.read_mode) as f:
            for group_name in group_names:
                try:
                    group = f[group_name]
                except KeyError:
                    continue
                group_hdf5 = HDF5Group(group_name)
                for dataset_name, dataset in group.items():
                    group_hdf5.create_dataset(dataset_name, dataset[()])
                groups_list.append(group_hdf5)
        return groups_list

    def read(self, dataset_name, group_name=None, dataset_slice=()):
        with h5py.File(self.hdf5_filepath, self.read_mode) as f:
            try:
                if group_name:
                    dataset = f[group_name][dataset_name]
                else:
                    dataset = f[dataset_name]
            except KeyError:
                return None
            data = dataset[dataset_slice]
            hdf5_dataset = HDF5Dataset(dataset_name, data=data)
            return hdf5_dataset

    def calculate_cellsize(self):
        cell_size = 0
        if self.hdf5_filepath is None:
            return 0
        if not os.path.isfile(self.hdf5_filepath):
            return 0
        if not os.path.getsize(self.hdf5_filepath) > 0:
            return 0

        # Read COORDINATES dataset
        coordinates_dataset = self.read("COORDINATES", "Input/Grid")
        # Return 0 if the dataset or its data is missing
        if coordinates_dataset is None or getattr(coordinates_dataset, "data", None) is None:
            return 0
        coordinates = coordinates_dataset.data

        # Extract x and y coordinates
        x_coords = coordinates[:, 0]
        y_coords = coordinates[:, 1]

        # Calculate differences in x-coordinates
        dx = np.diff(np.sort(np.unique(x_coords)))
        dx = dx[dx > 0]  # Filter out non-positive differences

        if dx.size > 0:
            size = np.min(dx)
        else:
            # Calculate differences in y-coordinates if no valid dx
            dy = np.diff(np.sort(np.unique(y_coords)))
            dy = dy[dy > 0]  # Filter out non-positive differences
            if dy.size > 0:
                size = np.min(dy)
            else:
                return 0

        cell_size += size
        return cell_size

    def list_input_subfolders(self):
        files_used = ""
        with h5py.File(self.hdf5_filepath, self.read_mode) as f:
            input_group = f.get("Input")
            if input_group is None:
                return files_used
            for name in input_group:
                if isinstance(input_group[name], h5py.Group):
                    files_used += name + "\n"
        return files_used


class ParseDAT(object):
    """
    Parser object for handling FLO-2D "DAT" files.
    """

    def __init__(self):
        self.project_dir = None
        self.dat_files = {
            "CONT.DAT": None,
            "TOLER.DAT": None,
            "FPLAIN.DAT": None,
            "CADPTS.DAT": None,
            "MANNINGS_N.DAT": None,
            "TOPO.DAT": None,
            "INFLOW.DAT": None,
            "TAILINGS.DAT": None,
            "TAILINGS_CV.DAT": None,
            "TAILINGS_STACK_DEPTH.DAT": None,
            "OUTFLOW.DAT": None,
            "RAIN.DAT": None,
            "RAINCELL.DAT": None,
            "RAINCELLRAW.DAT": None,
            "FLO2DRAINCELL.DAT": None,
            "INFIL.DAT": None,
            "EVAPOR.DAT": None,
            "CHAN.DAT": None,
            "CHANBANK.DAT": None,
            "XSEC.DAT": None,
            "HYSTRUC.DAT": None,
            "BRIDGE_XSEC.DAT": None,
            "STREET.DAT": None,
            "ARF.DAT": None,
            "MULT.DAT": None,
            "SIMPLE_MULT.DAT": None,
            "SED.DAT": None,
            "LEVEE.DAT": None,
            "FPXSEC.DAT": None,
            "BREACH.DAT": None,
            "FPFROUDE.DAT": None,
            "STEEP_SLOPEN.DAT": None,
            "LID_VOLUME.DAT": None,
            "SWMM.INP": None,
            "SWMMFLO.DAT": None,
            "SWMMFLORT.DAT": None,
            "SWMMOUTF.DAT": None,
            "SWMMFLODROPBOX.DAT": None,
            "SDCLOGGING.DAT": None,
            "TOLSPATIAL.DAT": None,
            "SHALLOWN_SPATIAL.DAT": None,
            "WSURF.DAT": None,
            "GUTTER.DAT": None,
            "WSTIME.DAT": None,
            "OUTRC.DAT": None,
            "CHAN_INTERIOR_NODES.OUT": None,
        }
        self.cont_rows = [
            ["SIMUL", "TOUT", "LGPLOT", "METRIC", "IBACKUP", "build"],
            ["ICHANNEL", "MSTREET", "LEVEE", "IWRFS", "IMULTC"],
            ["IRAIN", "INFIL", "IEVAP", "MUD", "ISED", "IMODFLOW", "SWMM"],
            ["IHYDRSTRUCT", "IFLOODWAY", "IDEBRV"],
            ["AMANN", "DEPTHDUR", "XCONC", "XARF", "FROUDL", "SHALLOWN", "ENCROACH"],
            ["NOPRTFP", "DEPRESSDEPTH"],
            ["NOPRTC"],
            ["ITIMTEP", "TIMTEP", "STARTIMTEP", "ENDTIMTEP"],
            ["GRAPTIM"],
        ]
        self.toler_rows = [
            ["TOLGLOBAL", "DEPTOL", ""],
            ["COURCHAR_C", "COURANTFP", "COURANTC", "COURANTST"],
            ["COURCHAR_T", "TIME_ACCEL"],
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
        fplain = self.dat_files["FPLAIN.DAT"]
        cadpts = self.dat_files["CADPTS.DAT"]
        neighbour = None
        side = 0

        with open(fplain) as fpl:
            for n in fpl.readline().split()[1:5]:
                if n != "0":
                    neighbour = int(n)
                    break
                else:
                    pass
                side += 1

        with open(cadpts) as cad:
            x1, y1 = cad.readline().split()[1:]
            for dummy in range(neighbour - 2):
                cad.readline()
            x2, y2 = cad.readline().split()[1:]

        dtx = abs(float(x1) - float(x2))
        dty = abs(float(y1) - float(y2))
        cell_size = dty if side % 2 == 0 else dtx
        return cell_size

    def calculate_cellsize(self):
        cell_size = 0
        topo = self.dat_files["TOPO.DAT"]
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
        with open(file1, "r") as f1:
            for line in f1:
                row = line.split()
                if row:
                    yield row

    @staticmethod
    def pandas_single_parser(file1, chunksize=10000):
        """Parse one large text file line-by-line using pandas in chunks."""
        with pd.read_csv(file1, sep=r'\s+', header=None, chunksize=chunksize) as f_iter:
            for chunk in f_iter:
                for row in chunk.itertuples(index=False, name=None):
                    yield list(row)

    @staticmethod
    def double_parser(file1, file2):
        with open(file1, "r") as f1, open(file2, "r") as f2:
            for line1, line2 in zip(f1, f2):
                row = line1.split() + line2.split()
                if row:
                    yield row

    @staticmethod
    def pandas_double_parser(file1, file2, chunksize=10000):
        """Parse two large text files line-by-line using pandas in chunks."""
        with pd.read_csv(file1, sep=r'\s+', header=None, chunksize=chunksize) as f1_iter, \
                pd.read_csv(file2, sep=r'\s+', header=None, chunksize=chunksize) as f2_iter:

            for chunk1, chunk2 in zip(f1_iter, f2_iter):
                combined = pd.concat([chunk1, chunk2], axis=1)
                for row in combined.itertuples(index=False, name=None):
                    yield list(row)

    @staticmethod
    def swmminp_parser(swmminp_file):
        """
        This is the new swmm parser. Usage example:

        To get data from a specific section
            junctions_data = sections.get('JUNCTIONS', [])

        To print all sections
            for section, lines in sections.items():
                print(f"[{section}]")
                for line in lines:
                    print(line)
                print("\n")
        """
        sections = defaultdict(list)
        current_section = None

        if not swmminp_file:
            return {}

        with open(swmminp_file, 'r') as inp_file:
            for line in inp_file:
                line = line.strip()

                # Ignore empty lines and comments
                if not line or line.startswith(';'):
                    continue

                # Check for section headers (e.g., [JUNCTIONS])
                if line.startswith('[') and line.endswith(']'):
                    current_section = line[1:-1].strip().upper()  # Strip brackets and set as current section
                elif current_section:
                    # Split the line by any whitespace (e.g., space, tab)
                    sections[current_section].append(re.split(r'\s+', line))

        return sections

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
        cont = self.dat_files["CONT.DAT"]
        with open(cont, "r") as f:
            for c, row in enumerate(self.cont_rows):
                if c == 0:
                    results.update(dict(zip_longest(row, f.readline().rstrip().split(None, 5))))
                elif c == 6 and results["ICHANNEL"] == "0":
                    results["NOPRTC"] = None
                elif c == 8 and results["LGPLOT"] == "0":
                    results["GRAPTIM"] = None
                else:
                    results.update(dict(zip_longest(row, f.readline().split())))
        return results

    def parse_toler(self):
        results = {}
        toler = self.dat_files["TOLER.DAT"]
        with open(toler, "r") as f:
            for row in self.toler_rows:
                results.update(dict(zip_longest(row, f.readline().split())))
        return results

    def parse_fplain_cadpts(self):
        fplain = self.dat_files["FPLAIN.DAT"]
        cadpts = self.dat_files["CADPTS.DAT"]
        results = self.double_parser(fplain, cadpts)
        return results

    def parse_mannings_n_topo(self):
        mannings_n = self.dat_files["MANNINGS_N.DAT"]
        topo = self.dat_files["TOPO.DAT"]
        results = self.double_parser(mannings_n, topo)
        return results

    def parse_topo(self):
        topo = self.dat_files["TOPO.DAT"]
        results = self.single_parser(topo)
        return results

    def parse_mannings_n(self):
        mannings_n = self.dat_files["MANNINGS_N.DAT"]
        results = self.single_parser(mannings_n)
        return results

    def parse_inflow(self, inflow=None):
        if inflow is None:
            inflow = self.dat_files["INFLOW.DAT"]
            if inflow is None:
                return None, None, None
        par = self.single_parser(inflow)
        nxt = next(par)
        if not nxt[0] == "R":
            head = dict(list(zip(["IHOURDAILY", "IDEPLT"], nxt)))
            inf = OrderedDict()
            res = OrderedDict()
            gid = None
            for row in par:
                char = row[0]
                if char == "C" or char == "F":
                    gid = row[-1]
                    inf[gid] = OrderedDict([("row", row), ("time_series", [])])
                elif char == "H":
                    self.fix_row_size(row, 4)
                    inf[gid]["time_series"].append(row)
                elif char == "R":
                    gid = row[1]
                    res[gid] = OrderedDict([("row", row)])
                else:
                    pass
        else:
            head, inf, res = None, None, OrderedDict()
            gid = nxt[1]
            res[gid] = OrderedDict([("row", nxt)])
            for row in par:
                gid = row[1]
                res[gid] = OrderedDict([("row", row)])
        return head, inf, res

    def parse_tailings(self):
        tailings = self.dat_files["TAILINGS.DAT"]
        if tailings is not None:
            par = self.single_parser(tailings)
            data = [row for row in par]
            return data

    def parse_outrc(self):
        outrc = self.dat_files["OUTRC.DAT"]
        if outrc is not None:
            par = self.single_parser(outrc)
            data = [row for row in par]
            return data

    def parse_tailings_cv(self):
        tailings = self.dat_files["TAILINGS_CV.DAT"]
        if tailings is not None:
            par = self.single_parser(tailings)
            data = [row for row in par]
            return data

    def parse_tailings_sd(self):
        tailings = self.dat_files["TAILINGS_STACK_DEPTH.DAT"]
        if tailings is not None:
            par = self.single_parser(tailings)
            data = [row for row in par]
            return data

    def parse_outflow(self, outflow=None):
        if outflow is None:
            outflow = self.dat_files["OUTFLOW.DAT"]
        par = self.single_parser(outflow)
        data = OrderedDict()
        cur_gid = None
        for row in par:
            char = row[0]
            if char == "K" or char == "N" or char.startswith("O"):
                gid = row[1]
                cur_gid = gid
                if gid not in data:
                    data[gid] = {
                        "K": 0,
                        "N": 0,
                        "O": 0,
                        "hydro_out": 0,
                        "qh_params": [],
                        "qh_data": [],
                        "time_series": [],
                    }
                else:
                    pass
                if char == "N":
                    nostacfp = int(row[-1])
                    data[gid][char] = nostacfp + 1 if nostacfp == 1 else 1
                elif char[-1].isdigit():
                    data[gid]["hydro_out"] = char[-1]
                else:
                    data[gid][char[0]] = 1
            elif char == "H":
                self.fix_row_size(row, 4)
                data[cur_gid]["qh_params"].append(row[1:])
            elif char == "T":
                data[cur_gid]["qh_data"].append(row[1:])
            elif char == "S":
                data[cur_gid]["time_series"].append(row[1:])
            else:
                pass
        return data

    def parse_rain(self):
        rain = self.dat_files["RAIN.DAT"]
        if not rain:
            return None, None, None
        head = [
            "IRAINREAL",
            "IRAINBUILDING",
            "RTT",
            "RAINABS",
            "RAINARF",
            "MOVINGSTORM",
        ]
        par = self.single_parser(rain)
        line1 = next(par)
        line2 = next(par)
        data = OrderedDict(list(zip(head, chain(line1, line2))))
        time_series = []
        rain_arf = []
        for row in par:
            rainchar = row[0]
            if rainchar == "R":
                time_series.append(row)
            elif data["MOVINGSTORM"] != "0" and "RAINSPEED" not in data:
                rainspeed, iraindir = row
                data["RAINSPEED"] = rainspeed
                data["IRAINDIR"] = iraindir
            else:
                rain_arf.append(row)
            if "RAINSPEED" not in data:
                data["RAINSPEED"] = None
                data["IRAINDIR"] = None
            else:
                pass
        return data, time_series, rain_arf

    def parse_raincell(self):
        rain = self.dat_files["RAINCELL.DAT"]
        par = self.single_parser(rain)
        line1 = next(par)
        head = line1[:2]
        head.append(" ".join(line1[2:]))
        data = [row for row in par]
        return head, data

    def parse_raincellraw(self):
        rain = self.dat_files["RAINCELLRAW.DAT"]
        par = self.single_parser(rain)
        line1 = next(par)
        rainintime = line1[0]
        irinters = line1[1]
        data = [row for row in par]
        return rainintime, irinters, data

    def parse_flo2draincell(self):
        rain = self.dat_files["FLO2DRAINCELL.DAT"]
        par = self.single_parser(rain)
        data = [row for row in par]
        return data

    def parse_infil(self):
        infil = self.dat_files["INFIL.DAT"]
        if not infil:
            return None
        line1 = ["INFMETHOD"]
        line2h = ["FHORTONIA"]
        line2 = ["ABSTR", "SATI", "SATF", "POROS", "SOILD", "INFCHAN"]
        line3 = ["HYDCALL", "SOILALL", "HYDCADJ"]
        line5 = ["SCSNALL", "ABSTR1"]
        par = self.single_parser(infil)
        data = OrderedDict(list(zip(line1, next(par))))
        method = data["INFMETHOD"]
        if method == "1" or method == "3":
            data.update(list(zip(line2, next(par))))
            data.update(list(zip(line3, next(par))))
            if data["INFCHAN"] == "1":
                data["HYDCXX"] = next(par)[0]
            else:
                pass
        elif method == "4":
            data.update(list(zip(line2h, next(par))))
        else:
            pass
        chars = {"R": 4, "F": 8, "S": 3, "C": 3, "H": 5}
        for char in chars:
            data[char] = []
        for row in par:
            char = row[0]
            if char in chars:
                self.fix_row_size(row, chars[char])
                data[char].append(row[1:])
            elif char == "I":
                self.fix_row_size(row, 3)
                data["FHORTONI"] = row[1]
                data["FHORTONF"] = row[2]
                data["DECAYA"] = row[3]
            else:
                data.update(list(zip(line5, row)))
        return data

    def parse_evapor(self):
        evapor = self.dat_files["EVAPOR.DAT"]
        par = self.single_parser(evapor)
        head = next(par)
        data = OrderedDict()
        month = None
        for row in par:
            if len(row) > 1:
                month = row[0]
                data[month] = {"row": row, "time_series": []}
            else:
                data[month]["time_series"].extend(row)
        return head, data

    def parse_chan(self):
        chan = self.dat_files["CHAN.DAT"]
        bank = self.dat_files["CHANBANK.DAT"]
        xsec = self.dat_files["XSEC.DAT"]
        par = self.single_parser(chan)  # Iterator to deliver lines of CHAN.DAT one by one.
        parbank = self.single_parser(bank)
        if xsec is not None:
            parxs = (["{0}".format(xs[-1])] for xs in self.single_parser(xsec) if xs[0] == "X")
        else:
            parxs = repeat([None])
        start = True
        segments = []
        wsel = []
        confluence = []
        noexchange = []
        baseflow = []
        shape = {"R": 8, "V": 20, "T": 10, "N": 5}
        chanchar = ["C", "E"]
        no_rb = ""
        for row in par:
            char = row[0]
            if char not in shape and char not in chanchar and len(row) > 2:
                self.fix_row_size(row, 4)
                segments.append(row)
                segments[-1].append([])  # Appends an empty list at end of 'segments' list.
            elif char in shape:
                fix_index = 2 if char == "T" else None
                self.fix_row_size(row, shape[char], index=fix_index)

                try:
                    nxt = next(parbank)
                    rbank = nxt[1:]
                    lbank = nxt[0]
                    if row[1] != lbank:
                        # Msge(
                        # "ERROR 010219.2020: Element "
                        # + row[1]
                        # + " in CHAN.DAT has no right bank element in CHANBANK.DAT !",
                        # "Error",
                        # )
                        no_rb += "\n" + row[1]
                except StopIteration:
                    Msge(
                        "ERROR 010219.0956: There is a missing right bank element in CHANBANK.DAT !\n\n"
                        "The number of left bank elements in CHAN.DAT must be the same of the number of pairs (left bank, right bank) in CHANBANK.DAT.",
                        "Error",
                    )
                    return

                try:
                    xsec = next(parxs)[0:1] if char == "N" else []
                    segments[-1][-1].append(row + xsec + rbank)
                except StopIteration:
                    return
                
            elif char == "B":
                baseflow.append(row)
                # segments[-1].append(row)

            elif char == "C":
                confluence.append(row)
            elif char == "E":
                noexchange.append(row)
            else:
                if start is True:
                    wsel.append(row)
                    start = False
                else:
                    wsel[-1].extend(row)
                    start = True
        if no_rb != "":
            Msge(
                "ERROR 010219.2020: These elements in CHAN.DAT have no right bank element in CHANBANK.DAT !\n" + no_rb,
                "Error",
            )
        for i in range(len(segments)):
            try:
                segments[i].append(baseflow[i])
            except:
                pass
              
        return segments, wsel, confluence, noexchange

    def parse_chan_interior_nodes(self):
        chan_interior_nodes = self.dat_files["CHAN_INTERIOR_NODES.OUT"]
        par = self.single_parser(chan_interior_nodes)
        data = [row for row in par]
        return data

    def parse_xsec(self):
        xsec = self.dat_files["XSEC.DAT"]
        par = self.single_parser(xsec)
        key = ()
        data = OrderedDict()
        for row in par:
            if row[0] == "X":
                key = (row[1], row[2])
                data[key] = []
            else:
                data[key].append(row)
        return data

    def parse_hystruct(self):
        hystruct = self.dat_files["HYSTRUC.DAT"]
        if not hystruct:
            return None
        par = self.single_parser(hystruct)
        data = []
        chars = {"S": 10, "C": 6, "R": 6, "T": 4, "F": 7, "D": 3, "B": 15}
        firstB = True
        for row in par:
            char = row[0]
            self.fix_row_size(row, chars[char], default=1)
            if char == "S":
                params = defaultdict(list)
                row.append(params)
                data.append(row[1:])
            elif char == "B":
                if firstB:
                    row = row[:10]
                    firstB = False
                else:
                    firstB = True
                data[-1][-1][char].append(row[1:])
            else:
                data[-1][-1][char].append(row[1:])
        return data

    def parse_hystruct_bridge_xs(self):
        bridge_xs = self.dat_files["BRIDGE_XSEC.DAT"]
        par = self.single_parser(bridge_xs)
        data = OrderedDict()
        for row in par:
            if row[0] == "X":
                key = row[1]
                data[key] = []
            else:
                data[key].append(row)
        return data

    def parse_street(self):
        street = self.dat_files["STREET.DAT"]
        par = self.single_parser(street)
        head = next(par)
        data = []
        vals = slice(1, None)
        chars = {"N": 2, "S": 5, "W": 3}
        for row in par:
            char = row[0]
            self.fix_row_size(row, chars[char])
            if char == "N":
                row.append([])
                data.append(row[vals])
            elif char == "S":
                row.append([])
                data[-1][-1].append(row[vals])
            elif char == "W":
                data[-1][-1][-1][-1].append(row[vals])
        return head, data

    def parse_arf(self):
        arf = self.dat_files["ARF.DAT"]
        if not arf:
            return None, None
        par = self.single_parser(arf)
        head = []
        data = defaultdict(list)
        arf_row = [1] * 9
        for row in par:
            char = row[0]
            if char == "S":
                head.append(row[-1])
            elif char == "T":
                row += arf_row
                data[char].append(row[1:])
            else:
                data["PB"].append(row)
        self.fix_row_size(head, 1)
        return head, data

    def parse_mult(self):
        mult = self.dat_files["MULT.DAT"]
        par = self.single_parser(mult)
        head = next(par)
        data = []
        for row in par:
            data.append(row)
        return head, data

    def parse_simple_mult(self):
        simple_mult = self.dat_files["SIMPLE_MULT.DAT"]
        if not simple_mult:
            return None, None
        par = self.single_parser(simple_mult)
        head = next(par)
        self.fix_row_size(head, 1)
        data = []
        for row in par:
            self.fix_row_size(row, 1)
            data.append(row)
        return head, data

    def parse_sed(self):
        sed = self.dat_files["SED.DAT"]
        par = self.single_parser(sed)
        data = defaultdict(list)
        vals = slice(1, None)
        chars = {
            "M": 7,
            "C": 10,
            "Z": 4,
            "P": 3,
            "D": 3,
            "E": 2,
            "R": 2,
            "S": 5,
            "N": 3,
            "G": 3,
        }
        for row in par:
            char = row[0]
            self.fix_row_size(row, chars[char])
            if char == "Z" or char == "S":
                row.append([])
                data[char].append(row[vals])
            elif char == "P":
                data["Z"][-1][-1].append(row[vals])
            elif char == "N":
                data["S"][-1][-1].append(row[vals])
            else:
                data[char].append(row[vals])
        return data

    def parse_levee(self):
        levee = self.dat_files["LEVEE.DAT"]
        if not levee:
            return None, None
        par = self.single_parser(levee)
        head = next(par)
        data = defaultdict(list)
        vals = slice(1, None)
        chars = {"L": 2, "D": 3, "F": 2, "W": 8, "C": 3, "P": 4}
        for row in par:
            char = row[0]
            self.fix_row_size(row, chars[char])
            if char == "L" or char == "F":
                row.append([])
                data[char].append(row[vals])
            elif char == "D":
                data["L"][-1][-1].append(row[vals])
            elif char == "W":
                data["F"][-1][-1].append(row[vals])
            elif char == "C":
                head.extend(row[vals])
            elif char == "P":
                data[char].append(row[vals])
            else:
                pass
        self.fix_row_size(head, 4)
        return head, data

    def parse_fpxsec(self):
        fpxsec = self.dat_files["FPXSEC.DAT"]
        if not fpxsec:
            return None, None
        par = self.single_parser(fpxsec)
        head = next(par)[-1]
        data = []
        for row in par:
            params = row[1:3]
            gids = row[3:]
            data.append([params, gids])
        return head, data

    def parse_breach(self):
        breach = self.dat_files["BREACH.DAT"]
        par = self.single_parser(breach)
        data = defaultdict(list)
        for row in par:
            char = row[0][0]
            if char == "B" and len(row) == 5:
                data["G"].append(row[1:])
            elif char == "B" and len(row) == 3:
                data["D"].append(row[1:])
            elif char == "G" or char == "D":
                data[char][-1] += row[1:]
            else:
                data["F"].append(row[1:])
        chars = {"G": 32, "D": 33, "F": 3}
        for k in data.keys():
            for row in data[k]:
                self.fix_row_size(row, chars[k])
        return data

    def parse_fpfroude(self):
        fpfroude = self.dat_files["FPFROUDE.DAT"]
        if not fpfroude:
            return None
        par = self.single_parser(fpfroude)
        data = [row[1:] for row in par]
        return data

    def parse_steep_slopen(self):
        steep_slopen = self.dat_files["STEEP_SLOPEN.DAT"]
        if not steep_slopen:
            return None
        par = self.single_parser(steep_slopen)
        data = [row for row in par]
        return data

    def parse_lid_volume(self):
        lid_volume = self.dat_files["LID_VOLUME.DAT"]
        if not lid_volume:
            return None
        par = self.single_parser(lid_volume)
        data = [row for row in par]
        return data

    def parse_gutter(self):
        gutter = self.dat_files["GUTTER.DAT"]
        par = self.single_parser(gutter)
        head = next(par)
        data = []
        for row in par:
            data.append(row)
        return head, data

    def parse_swmminp(self, swmm_file):
        if swmm_file == "SWMM.INP":
            swmminp = self.dat_files[swmm_file]
        else:
            swmminp = swmm_file
        swmminp_dict = self.swmminp_parser(swmminp)
        return swmminp_dict

    def parse_swmmflo(self):
        swmmflo = self.dat_files["SWMMFLO.DAT"]
        par = self.single_parser(swmmflo)
        data = [row for row in par]
        return data

    def parse_swmmflodropbox(self):
        swmmflodropbox = self.dat_files["SWMMFLODROPBOX.DAT"]
        par = self.single_parser(swmmflodropbox)
        data = [row for row in par]
        return data
    
    def parse_sdclogging(self):
        sdclogging = self.dat_files["SDCLOGGING.DAT"]
        par = self.single_parser(sdclogging)
        data = [row for row in par]
        return data
    
    def parse_swmmflort(self):
        # swmmflort = self.dat_files["SWMMFLORT.DAT"]
        # par = self.single_parser(swmmflort)
        # data = []
        # for row in par:
        #     char = row[0]
        #     if char == "D":
        #         row.append([])
        #         data.append(row[1:])
        #     else:
        #         data[-1][-1].append(row[1:])
        # return data

        swmmflort = self.dat_files["SWMMFLORT.DAT"]
        par = self.single_parser(swmmflort)
        data = []
        for row in par:
            char = row[0]
            if char == "D":  # Rating Table.
                row.append([])
                data.append(row[0:])
            if char == "S":  # Culvert Eq.
                row.append([])
                data.append(row[0:])
            else:
                data[-1][-1].append(row[1:])
        return data

    def parse_swmmoutf(self):
        swmmoutf = self.dat_files["SWMMOUTF.DAT"]
        par = self.single_parser(swmmoutf)
        data = [row for row in par]
        return data

    def parse_tolspatial(self):
        tolspatial = self.dat_files["TOLSPATIAL.DAT"]
        if not tolspatial:
            return None
        par = self.single_parser(tolspatial)
        data = [row for row in par]
        return data

    def parse_shallowNSpatial(self):
        shallowNSpatial = self.dat_files["SHALLOWN_SPATIAL.DAT"]
        if not shallowNSpatial:
            return None
        par = self.single_parser(shallowNSpatial)
        data = [row for row in par]
        return data

    def parse_wsurf(self):
        wsurf = self.dat_files["WSURF.DAT"]
        par = self.single_parser(wsurf)
        head = next(par)[0]
        data = []
        for row in par:
            data.append(row)
        return head, data

    def parse_wstime(self):
        wstime = self.dat_files["WSTIME.DAT"]
        par = self.single_parser(wstime)
        head = next(par)[0]
        data = []
        for row in par:
            data.append(row)
        return head, data

    def parse_hychan(self, HYCHAN_file, mode):
        """
        Function to parse the two types of HYCHAN.OUT - clear water and mudflow.
        Modes:
            - "peaks": Returns peak values (peaks_dict, peaks_list).
            - "time_series": Returns time series data (ts_dict, ts_list).
        """
        result_dict = {}
        result_list = []

        def parse_data_line(line, max_sed_con, lists):
            """Helper function to parse a single data line."""
            line = line.split()
            lists["time"].append(float(line[0]))
            lists["elevation"].append(float(line[1]))
            lists["depth"].append(float(line[2]))
            lists["velocity"].append(float(line[3]))
            lists["discharge"].append(float(line[4]))
            lists["froude"].append(float(line[5]))
            if max_sed_con is not None:
                lists["con"].append(float(line[6]))
            else:
                lists["flow_area"].append(float(line[6]))
                lists["w_perimeter"].append(float(line[7]))
                lists["hyd_radius"].append(float(line[8]))
                lists["top_width"].append(float(line[9]))
                lists["width_depth"].append(float(line[10]))
                lists["energy_slope"].append(float(line[11]))
                lists["shear_stress"].append(float(line[12]))
                lists["surf_area"].append(float(line[13]))

        with open(HYCHAN_file, "r") as myfile:
            while True:
                try:
                    # Initialize lists for data
                    lists = {
                        "time": [],
                        "elevation": [],
                        "depth": [],
                        "velocity": [],
                        "discharge": [],
                        "froude": [],
                        "flow_area": [],
                        "con": [],
                        "w_perimeter": [],
                        "hyd_radius": [],
                        "top_width": [],
                        "width_depth": [],
                        "energy_slope": [],
                        "shear_stress": [],
                        "surf_area": [],
                    }
                    line = next(myfile)
                    if "CHANNEL HYDROGRAPH FOR ELEMENT NO:" in line:
                        grid = line.split()[-1]
                        peak_discharge = max_water_elev = max_sed_con = None

                        # Parse header lines
                        for _ in range(3):
                            line = next(myfile)
                            if "DISCHARGE" in line:
                                peak_discharge = float(line.split("=")[1].split()[0])
                            elif "STAGE" in line:
                                max_water_elev = float(line.split("=")[1].split()[0])
                            elif "SEDIMENT" in line:
                                max_sed_con = float(line.split("=")[1].split()[0])

                        # Skip fixed 4 lines of table headers
                        for _ in range(4):
                            line = next(myfile)

                        # Parse data rows
                        while True:
                            try:
                                line = next(myfile)
                                if not line.strip():  # If the line is empty, exit the loop
                                    break
                                parse_data_line(line, max_sed_con, lists)
                            except StopIteration:
                                # Handle the end of the file gracefully
                                break

                        # Handle results based on mode
                        if mode == "peaks":
                            if max_sed_con is not None:
                                result_dict[grid] = [
                                    max_water_elev,
                                    peak_discharge,
                                    max_sed_con,
                                    max(lists["velocity"]),
                                    max(lists["froude"]),
                                    max(lists["con"]),
                                ]
                                result_list.append((grid, *result_dict[grid]))
                            else:
                                result_dict[grid] = [
                                    max_water_elev,
                                    peak_discharge,
                                    max(lists["velocity"]),
                                    max(lists["froude"]),
                                    max(lists["flow_area"]),
                                    max(lists["w_perimeter"]),
                                    max(lists["hyd_radius"]),
                                    max(lists["top_width"]),
                                    max(lists["width_depth"]),
                                    max(lists["energy_slope"]),
                                    max(lists["shear_stress"]),
                                    max(lists["surf_area"]),
                                ]
                                result_list.append((grid, *result_dict[grid]))
                        elif mode == "time_series":
                            if max_sed_con is not None:
                                result_dict[grid] = [
                                    lists["time"],
                                    lists["elevation"],
                                    lists["depth"],
                                    lists["velocity"],
                                    lists["discharge"],
                                    lists["froude"],
                                    lists["con"],
                                ]
                                result_list.append((grid, *result_dict[grid]))
                            else:
                                result_dict[grid] = [
                                    lists["time"],
                                    lists["elevation"],
                                    lists["depth"],
                                    lists["velocity"],
                                    lists["discharge"],
                                    lists["froude"],
                                    lists["flow_area"],
                                    lists["w_perimeter"],
                                    lists["hyd_radius"],
                                    lists["top_width"],
                                    lists["width_depth"],
                                    lists["energy_slope"],
                                    lists["shear_stress"],
                                    lists["surf_area"],
                                ]
                                result_list.append((grid, *result_dict[grid]))
                    else:
                        pass
                except StopIteration:
                    break

        return result_dict, result_list