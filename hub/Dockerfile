FROM jupyterhub/jupyterhub:latest

COPY hub/requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY hub/start.sh /start.sh
RUN chmod +x /start.sh

RUN useradd -ms /bin/bash jupyter_user

WORKDIR /home/jupyter_user

RUN mkdir -p /var/lib/jupyterhub

EXPOSE 8000

CMD ["/start.sh"]
