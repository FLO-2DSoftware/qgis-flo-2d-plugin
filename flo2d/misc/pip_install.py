import sys
import os
import tempfile
import subprocess

python_dir = sys.exec_prefix
python_or_qgis_exe = sys.executable


def pip_install(name, pipe=print):
    libs = name.split(",")
    pipe("Installing python libraries: %r\n" % libs)
    try:
        pipe("Using QGIS python 3 pip via subprocess ...\n")
        result = subprocess.run(
            ["python3", "-m", "pip", "install", *libs], capture_output=True, check=True, text=True, env=os.environ
        )
    except subprocess.CalledProcessError as e:
        pipe("Exception: stderr: %s\n" % e.stderr)
        pipe("Exception: stdout: %s\n" % e.stdout)
        pipe("Exception: outout: %s\n" % e.output)
        pipe("Using pip from batch file batch file ...\n")
        for lib in libs:
            pip_install_batch(lib, pipe)

    else:
        pipe("Installation complete.")


def pip_install_batch(name, pipe=print):
    temp_file = tempfile.NamedTemporaryFile("w", prefix="qgs_pip_install", suffix="temp.bat", delete=False)
    batch_file = temp_file.name
    pipe("batch file = %s\n" % (batch_file))
    temp_file.close()

    with open(batch_file, "w") as fid:
        lines = 'pushd "{}"\npip install "{}"\n'.format(os.path.join(python_dir, "Scripts"), name)
        fid.write(lines)

    try:
        result = subprocess.run(batch_file, capture_output=True, check=True, text=True, env=os.environ)
    except subprocess.CalledProcessError as e:
        pipe("Batch exception: stderr: %s\n" % e.stderr)
        pipe("Batch Exception: stdout: %s\n" % e.stdout)
        pipe("Batch Exception: output: %s\n" % e.output)

    else:
        pipe("Installation complete.")
