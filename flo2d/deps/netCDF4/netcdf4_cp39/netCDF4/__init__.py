

""""""# start delvewheel patch
def _delvewheel_init_patch_1_3_7():
    import ctypes
    import os
    import platform
    import sys
    libs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, 'netCDF4.libs'))
    is_conda_cpython = platform.python_implementation() == 'CPython' and (hasattr(ctypes.pythonapi, 'Anaconda_GetVersion') or 'packaged by conda-forge' in sys.version)
    if sys.version_info[:2] >= (3, 8) and not is_conda_cpython or sys.version_info[:2] >= (3, 10):
        if os.path.isdir(libs_dir):
            os.add_dll_directory(libs_dir)
    else:
        load_order_filepath = os.path.join(libs_dir, '.load-order-netCDF4-1.6.4')
        if os.path.isfile(load_order_filepath):
            with open(os.path.join(libs_dir, '.load-order-netCDF4-1.6.4')) as file:
                load_order = file.read().split()
            for lib in load_order:
                lib_path = os.path.join(os.path.join(libs_dir, lib))
                if os.path.isfile(lib_path) and not ctypes.windll.kernel32.LoadLibraryExW(ctypes.c_wchar_p(lib_path), None, 0x00000008):
                    raise OSError('Error loading {}; {}'.format(lib, ctypes.FormatError()))


_delvewheel_init_patch_1_3_7()
del _delvewheel_init_patch_1_3_7
# end delvewheel patch

# init for netCDF4. package
# Docstring comes from extension module _netCDF4.
from ._netCDF4 import *
# Need explicit imports for names beginning with underscores
from ._netCDF4 import __doc__
from ._netCDF4 import (__version__, __netcdf4libversion__, __hdf5libversion__,
                       __has_rename_grp__, __has_nc_inq_path__,
                       __has_nc_inq_format_extended__, __has_nc_open_mem__,
                       __has_nc_create_mem__, __has_cdf5_format__,
                       __has_parallel4_support__, __has_pnetcdf_support__,
                       __has_quantization_support__, __has_zstandard_support__,
                       __has_bzip2_support__, __has_blosc_support__, __has_szip_support__,
                       __has_set_alignment__)
import os
__all__ =\
['Dataset','Variable','Dimension','Group','MFDataset','MFTime','CompoundType','VLType','date2num','num2date','date2index','stringtochar','chartostring','stringtoarr','getlibversion','EnumType','get_chunk_cache','set_chunk_cache','set_alignment','get_alignment']
# if HDF5_PLUGIN_PATH not set, point to package path if plugins live there
pluginpath = os.path.join(__path__[0],'plugins')
if 'HDF5_PLUGIN_PATH' not in os.environ and\
    (os.path.exists(os.path.join(pluginpath,'lib__nczhdf5filters.so')) or\
     os.path.exists(os.path.join(pluginpath,'lib__nczhdf5filters.dylib'))):
    os.environ['HDF5_PLUGIN_PATH']=pluginpath
