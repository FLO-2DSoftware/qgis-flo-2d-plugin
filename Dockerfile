# Use an official Ubuntu as a parent image
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y \
    software-properties-common \
    python3-pip \
    qgis \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy the plugin code
COPY . /app

# Command to run your tests
CMD ["python3", "-m", "unittest", "discover", "--verbose"]
