import sys
import os
import tempfile


python_dir = sys.exec_prefix

def pip_install(name):
    temp_file = tempfile.NamedTemporaryFile('w',
                                           prefix = 'qgs_pip_install',
                                           suffix = 'temp.bat',
                                           delete = False)
    batch_file = temp_file.name
    print(batch_file)
    temp_file.close()

    with open(batch_file, 'w') as fid:
        fid.write('pushd "{}"\npython -m pip install "{}"\n'.format(python_dir, name))

    os.startfile(batch_file)
    os.unlink(batch_file)

