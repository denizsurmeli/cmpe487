FROM ubuntu:latest
RUN apt-get update && apt-get install -qq -y python3 netcat git
RUN git clone https://github.com/denizsurmeli/cmpe487.git

ENTRYPOINT [ "/bin/bash" ]