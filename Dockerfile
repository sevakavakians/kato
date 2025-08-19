FROM docker.io/library/debian:bullseye-slim

# set noninteractive installation
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get -y dist-upgrade && apt-get -y autoremove
RUN apt-get install -y git wget python3 python3-pip python3-dev libopenjp2-7-dev \
    && apt-get autoremove -y \
    && ln -s /usr/bin/python3 /usr/local/bin/python

RUN pip3 install --upgrade pip setuptools wheel

ENV LOG_LEVEL DEBUG
ENV KATO_VERSION 11.0.0
ENV ARCH 'x86_64'
ENV MONGO_BASE_URL mongodb://mongo-kb:27017
ENV MANIFEST "primitive-manifest-to-be-overwritten"
ENV HOSTNAME 'change-via-run-cmd'
ENV SOURCES 'change-via-run-cmd'
ENV TARGETS 'change-via-run-cmd'
ENV AS_INPUTS 'change-via-run-cmd'
ENV PORT 1441
EXPOSE 1441

RUN apt-get update && apt-get install -y apt-utils make automake gcc g++ subversion python3-dev gfortran libfreetype6-dev libpng-dev libopenblas-dev linux-headers-generic

COPY ./ /kato
WORKDIR /kato
# RUN pip3 install Cython
RUN pip install --trusted-host pypi.python.org -r requirements.txt
# Regenerate protobuf files in container environment to ensure compatibility
RUN python3 -m grpc_tools.protoc --python_out=. --grpc_python_out=. --proto_path=. kato/kato_proc.proto
RUN pip install -v .
WORKDIR /
RUN rm -fr /kato

CMD python3 /usr/local/bin/kato-engine
