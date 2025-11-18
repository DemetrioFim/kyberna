FROM quay.io/jupyter/pyspark-notebook:spark-4.0.1
USER root
COPY requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt
USER ${NB_UID}