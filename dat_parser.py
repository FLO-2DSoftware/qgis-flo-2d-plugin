import os
from itertools import izip, izip_longest


class ParseDAT(object):
    dat_files = {
        'CONT.DAT': None,
        'TOLER.DAT': None,
        'FPLAIN.DAT': None,
        'CADPTS.DAT': None,
        'MANNINGS_N.DAT': None,
        'TOPO.DAT': None,
        'INFLOW.DAT': None,
        'OUTFLOW.DAT': None
    }

    def __init__(self, fplain):
        self.project_dir = os.path.dirname(fplain)
        for f in os.listdir(self.project_dir):
            if f in self.dat_files:
                self.dat_files[f] = os.path.join(self.project_dir, f)
            else:
                pass

    def parse_cont(self):
        results = {}
        lines = [
            ['SIMULT', 'TOUT', 'LGPLOT', 'METRIC', 'IBACKUPrescont'],
            ['ICHANNEL', 'MSTREET', 'LEVEE', 'IWRFS', 'IMULTC'],
            ['IRAIN', 'INFIL', 'IEVAP', 'MUD', 'ISED', 'IMODFLOW', 'SWMM'],
            ['IHYDRSTRUCT', 'IFLOODWAY', 'IDEBRV'],
            ['AMANN', 'DEPTHDUR', 'XCONC', 'XARF', 'FROUDL', 'SHALLOWN', 'ENCROACH'],
            ['NOPRTFP', 'SUPER'],
            ['NOPRTC'],
            ['ITIMTEP', 'TIMTEP'],
            ['GRAPTIM']
        ]
        cont = self.dat_files['CONT.DAT']
        with open(cont, 'r') as f:
            c = 1
            for l in lines:
                if c == 1:
                    results.update(dict(izip_longest(l, f.readline().split()[:5])))
                elif c == 7 and results['ICHANNEL'] == '0':
                    results['NOPRTC'] = None
                elif c == 9 and results['LGPLOT'] == '0':
                    results['GRAPTIM'] = None
                else:
                    results.update(dict(izip_longest(l, f.readline().split())))
                c += 1
        return results

    def parse_toler(self):
        results = {}
        lines = [
            ['TOLGLOBAL', 'DEPTOL', 'WAVEMAX'],
            ['COURCHAR_C', 'COURANTFP', 'COURANTC', 'COURANTST'],
            ['COURCHAR_T', 'TIME_ACCEL']
        ]
        toler = self.dat_files['TOLER.DAT']
        with open(toler, 'r') as f:
            for l in lines:
                results.update(dict(izip_longest(l, f.readline().split())))
        return results

    @staticmethod
    def single_parser(file1):
        with open(file1, 'r') as f1:
            for line in f1:
                row = line.split()
                yield row

    @staticmethod
    def double_parser(file1, file2):
        with open(file1, 'r') as f1, open(file2, 'r') as f2:
            for line1, line2 in izip(f1, f2):
                row = line1.split() + line2.split()
                yield row

    def parse_fplain_cadpts(self):
        fplain = self.dat_files['FPLAIN.DAT']
        cadpts = self.dat_files['CADPTS.DAT']
        head = ['DUM_F', 'FP_IJ', 'FP_I5', 'FP_I6', 'DUM_C', 'XCOORD', 'YCOORD']
        results = self.double_parser(fplain, cadpts)
        return head, results

    def parse_mannings_n_topo(self):
        mannings_n = self.dat_files['MANNINGS_N.DAT']
        topo = self.dat_files['TOPO.DAT']
        head = ['DUM', 'FP_IJ', 'XCOORD', 'YCOORD', 'ELEV']
        results = self.double_parser(mannings_n, topo)
        return head, results

    def parse_inflow(self):
        results = []
        nodes = []
        inflow = self.dat_files['INFLOW.DAT']
        for row in self.single_parser(inflow):
            if row[0] == 'H':
                nodes.append(row)
            else:
                if nodes:
                    results.append(nodes)
                else:
                    pass
                nodes = []
                results.append(row)
        return results


if __name__ == '__main__':
    x = ParseDAT(r'D:\GIS_DATA\FLO-2D PRO Documentation\Example Projects\Alawai\FPLAIN.DAT')
    h1, d1 = x.parse_fplain_cadpts()
    h2, d2 = x.parse_mannings_n_topo()
    for i in d2:
        print(i)
