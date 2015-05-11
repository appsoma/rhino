FROM ubuntu:14.10
RUN apt-get update && apt-get install -y python-setuptools build-essential python-dev
RUN easy_install pymongo
RUN apt-get update && apt-get update && apt-get install -y libsvn-dev
COPY mesos_interface/*.py /rhino/mesos/interface/
COPY mesos_py_2/ /rhino/mesos_py_2/
RUN apt-get update && apt-get install python-protobuf
RUN apt-get update && apt-get install git
