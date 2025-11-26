FROM quay.io/jupyter/pyspark-notebook:latest
USER root
COPY requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt
USER ${NB_UID}