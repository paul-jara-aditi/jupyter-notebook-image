# Using Python 3.11 slim for a lightweight image
FROM python:3.11-slim

# 1. Block user-level installations
# PYTHONNOUSERSITE prevents pip from using the ~/.local/lib/... directory
ENV PYTHONNOUSERSITE=1 \
    PIP_NO_CACHE_DIR=1

# 2. Copy the requirements file into the container
COPY requirements.txt /tmp/

# 3. Install Jupyter and libraries as ROOT
# Installing as root places them in /usr/local/lib/ making them read-only for other users
RUN pip install jupyter -r /tmp/requirements.txt

# 3b. Copy startup script and make it executable
COPY start.sh /start.sh
RUN chmod +x /start.sh

# 4. Create a standard unprivileged user (named 'jupyter_user')
RUN useradd -ms /bin/bash jupyter_user

# 5. Create the project folder structure and assign ownership to the new user
WORKDIR /home/jupyter_user/notebook-paypal
RUN mkdir -p \
    notebooks \
    data/raw \
    data/processed \
    data/external \
    src \
    tests \
    docs \
    && chown -R jupyter_user:jupyter_user /home/jupyter_user/notebook-paypal

# 6. Copy notebooks and data into the image
COPY --chown=jupyter_user:jupyter_user notebooks/ ./notebooks/
COPY --chown=jupyter_user:jupyter_user data/ ./data/

# 6. Switch to the unprivileged user. Everything after this line will not have root access.
USER jupyter_user

# 7. Expose the standard Jupyter port
EXPOSE 8888

# 8. Start Jupyter Notebook (token read from JUPYTER_TOKEN env var via start.sh)
CMD ["/start.sh"]