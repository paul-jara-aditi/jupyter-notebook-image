FROM python:3.11-slim

ENV PYTHONNOUSERSITE=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt /tmp/

RUN pip install jupyterhub notebook -r /tmp/requirements.txt

# Standard jupyter/docker-stacks username convention
RUN useradd -ms /bin/bash jovyan

WORKDIR /home/jovyan/work
RUN chown -R jovyan:jovyan /home/jovyan/work

USER jovyan

CMD ["jupyterhub-singleuser", "--ip=0.0.0.0"]
