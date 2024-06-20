# first build an image with rust, ros and cargo chef
FROM osrf/ros:humble-desktop AS chef

ARG USER_NAME=ubuntu
ARG USER_ID=1000
ARG GROUP_ID=1000

RUN groupadd -g ${GROUP_ID} usergroup && \
    useradd -u ${USER_ID} -g usergroup -m ${USER_NAME}

RUN echo "${USER_NAME} ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
USER ${USER_NAME}

RUN sudo apt update && sudo apt install -y build-essential curl pkg-config libssl-dev protobuf-compiler clang python3-pip
RUN pip install requests
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y
ENV PATH="/home/${USER_NAME}/.cargo/bin:${PATH}"

WORKDIR /fog_ws 
# changed to .
COPY . /fog_ws/src/fogros2-ls
RUN . /opt/ros/humble/setup.sh && colcon build 
# --symlink-install

CMD ["bash"]
# docker build --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g)  -t dev-fr .
# docker run -ti --net=host -v ~/rt-fogros2:/fog_ws/rt-fogros2  dev-fr bash  

# docker build -t dev-fr . && docker run -ti --net=host -v ~/rt-fogros2:/fog_ws/rt-fogros2  dev-fr bash 