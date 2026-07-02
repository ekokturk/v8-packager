FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ARG GCC_VERSION=12

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        gcc-${GCC_VERSION} \
        g++-${GCC_VERSION} \
        git \
        libglib2.0-dev \
        libstdc++-${GCC_VERSION}-dev \
        pkg-config \
        python3 \
        python3-pip \
        xz-utils \
    && update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-${GCC_VERSION} 100 \
    && update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-${GCC_VERSION} 100 \
    && update-alternatives --install /usr/bin/cc cc /usr/bin/gcc-${GCC_VERSION} 100 \
    && update-alternatives --install /usr/bin/c++ c++ /usr/bin/g++-${GCC_VERSION} 100 \
    && rm -rf /var/lib/apt/lists/*

RUN git config --global --add safe.directory "*"
RUN python3 -m pip install --no-cache-dir requests==2.31.0

WORKDIR /workspace
CMD ["/bin/bash"]
