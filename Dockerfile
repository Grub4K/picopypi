FROM quay.io/pypa/manylinux_2_31_armv7l@sha256:3d1bb16c69d0acafcb90fdbaa5e1b9a2d6634089006d76e2427ca6cdae136be0

RUN <<EOF
set -e
useradd --create-home --shell /bin/bash builder

mkdir -p /home/builder/repos
chown builder:builder /home/builder/repos
EOF

ENV DEBIAN_FRONTEND=noninteractive CI=1
USER builder
WORKDIR /home/builder

COPY ./src/picopypi/command/build_armv7l.py /entrypoint.py
ENTRYPOINT [ "/usr/bin/python3", "/entrypoint.py" ]

VOLUME [ "/home/builder/repos" ]
