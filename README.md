![Auto Tests](https://github.com/FLO-2DSoftware/qgis-flo-2d-plugin/workflows/Auto%20Tests/badge.svg)

# qgis-flo-2d-plugin
A plugin for pre-processing/post-processing FLO-2D models
 
# Testing

New tests can be added to the folder `test/` and the corresponding data are in folder `test/data`. It is 
usefull to reuse existing data in the data folder where possible to keep the repository size small. Also it 
is not recommended to add data larger than 3MB to the test suite.

Tests can be run on Linux by running script `test/run-env-linux.sh /usr` to setup the environment, following by 
running `python3 -m unittest` to run all tests in the test suite.

New tests can be added by just copy of any existing test file and modifying it. The tests are auto discovered and run
by CI afterwards.