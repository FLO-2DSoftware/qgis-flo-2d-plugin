# Use an official Ubuntu as a parent image
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install QGIS, QGIS Python, and necessary libraries
RUN apt-get update && apt-get install -y \
    qgis \
    qgis-plugin-grass \
    python3-qgis \
    python3-pyqt5 \
    python3-pip

# Install Python dependencies if necessary
RUN pip3 install --upgrade pip \
    && pip3 install pandas \
    && pip3 install hdf5

ENV QGIS_PREFIX_PATH=/usr
ENV GDAL_FILENAME_IS_UTF8=YES
ENV VSI_CACHE=TRUE
ENV VSI_CACHE_SIZE=1000000
ENV QT_PLUGIN_PATH=/usr/lib/qgis/plugins:/usr/lib/qt5/plugins
ENV PYTHONPATH=/usr/share/qgis/python:/usr/share/qgis/python/plugins

# Set the working directory
WORKDIR /app

# Copy the plugin code
COPY . /app

# Command to run your tests
CMD ["python3", "-m", "unittest", "discover", "--verbose"]
