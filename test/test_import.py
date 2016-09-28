import unittest 

# Find data dir for data required for tests
import os 
THIS_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(THIS_DIR, 'data')

# Import our plugin
import sys
sys.path.append('..')
from flo2d.flo2d_parser import ParseDAT

def get_data_dir(dirname):
    return os.path.join(DATA_DIR, dirname, 'CONT.DAT')

class TestFlo2dParser(unittest.TestCase):

    def test_calculate_cellsize(self):
        p = ParseDAT()
        p.scan_project_dir(get_data_dir('min_grid_data'))
        cell_size = p.calculate_cellsize()
        
        self.assertTrue(abs(cell_size - 1) < 0.1)
            
if __name__ == '__main__':
  unittest.main()
