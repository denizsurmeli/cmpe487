FROM ubuntu:latest
RUN apt-get update && apt-get install -qq -y python3 python3-pip
RUN pip3 install pyDes
COPY . /home/ws6

WORKDIR /home/ws6