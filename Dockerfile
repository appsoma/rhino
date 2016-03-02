FROM debian:8
RUN apt-get update && apt-get install -y libsvn1 libcurl3 python-pip python-setuptools
RUN pip install pymongo kazoo
RUN easy_install http://downloads.mesosphere.io/master/debian/8/mesos-0.26.0-py2.7-linux-x86_64.egg
ENV PYTHONPATH ${PYTHONPATH}:/usr/lib/python2.7/site-packages/
COPY ./rhino.py /rhino/rhino.py

EXPOSE 8899
WORKDIR /rhino
CMD python rhino.py


