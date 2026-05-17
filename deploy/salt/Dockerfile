FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir \
        salt \
        cffi \
        cryptography \
        distro \
        importlib-metadata \
        jinja2 \
        looseversion \
        msgpack \
        packaging \
        psutil \
        pyasn1 \
        pycryptodomex \
        pyopenssl \
        pyzmq \
        pyyaml \
        requests \
        rsa \
        setproctitle \
        tornado

RUN mkdir -p /etc/salt /etc/salt/pki /srv/salt /srv/pillar /var/cache/salt /var/log/salt

EXPOSE 4505 4506

CMD ["salt-master", "--config-dir=/etc/salt", "--log-level=info"]
