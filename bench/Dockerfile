FROM osrf/ros:humble-desktop AS chef

RUN apt-get update && apt-get install -y python3-pip

RUN pip3 install requests 

COPY ./bench /bench