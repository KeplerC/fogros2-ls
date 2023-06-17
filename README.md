# FogROS2 SGC Lite

FogROS2-SGC is a cloud robotics platform for connecting disjoint ROS2 networks across different physical locations, networks, and Data Distribution Services. 

\[[Website](https://sites.google.com/view/fogros2-sgc)\] \[[Video](https://youtu.be/hVVFVGLcK0c)\] \[[Arxiv](https://arxiv.org/abs/2210.11691)\] (TODO: arxiv link)

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**

- [Local Demo](#local-demo)
- [Build FogROS2 SGC](#build-fogros2-sgc)
  - [Install dependencies](#install-dependencies)
    - [Install Rust](#install-rust)
    - [Install ROS](#install-ros)
  - [Build the repo](#build-the-repo)
- [Run with Different Machines](#run-with-different-machines)
    - [Certificate Generation](#certificate-generation)
    - [Run ROS2 talker and listener](#run-ros2-talker-and-listener)
    - [Run with Environment Variables](#run-with-environment-variables)
- [From SGC to SGC-lite](#from-sgc-to-sgc-lite)
    - [Why Lite version](#why-lite-version)
    - [Deploying Your Own Routing Infrastructure](#deploying-your-own-routing-infrastructure)
    - [Notes on using Berkeley's Public Servers](#notes-on-using-berkeleys-public-servers)
    - [TODOs](#todos)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->


## TODO List 

[x] A local restful API interface for ROS topic management  
[x] adding a topic dynamically 
[x] removal of a topic thread
[x] Removing topics dynamically 
(Note, above approach doesn't work)

Refactor 
[] make topic_creator a separate thread that handles all pubsub
[] one ROS node for all topics 
[] remove a topic by removing the future of the polling topic 
[] stoppable ROS future (connect as a publisher, but doesn't publish/susbcribe to the actual topic); needs to request to actually start and stop 
[] internal multicast

controller (separate repo)
[] Put topic scanning as a separate program to replace `automatic.toml`
[] Question: how to coordinate switching (TCP to a common server? may work in short term)
[] well defined crypto per topic

Optimizations  
[] create one ROS subscriber thread per topic 
[] One ros node for all the topics (need to rearchitect, but important)
[] delete by deleting topics instead of killing threads 
[] alias (repulish) for local topics 

## Local Demo 
If you want to get a taste of FogROS2 SGC without setting up the environment, just run 
```
docker compose build && docker compose up 
```
with docker ([install](https://docs.docker.com/get-docker/)) and docker compose ([install](https://docs.docker.com/compose/install/linux/)). 
It takes some time to build. You will see two docker containers running `talker` and `listener` are connected securely with FogROS2-SGC.


## Build FogROS2 SGC 
The following are instructions of building FogROS2 SGC. 

### Install dependencies 
```
sudo apt update
sudo apt install build-essential curl pkg-config libssl-dev protobuf-compiler clang
```

#### Install Rust 
```
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -y
source "$HOME/.cargo/env"
```

#### Install ROS 
ROS2 ~Dashing~ ~Eloquent~ Foxy Galactic Humble Rolling should work fine with FogROS2 SGC. 

Here we show the instruction of installing ROS2 rolling with Debian packages. 

First, install ROS2 from binaries with [these instructions](https://docs.ros.org/en/rolling/Installation/Ubuntu-Install-Debians.html).

Setup your environment with [these instructions](https://docs.ros.org/en/rolling/Installation/Ubuntu-Install-Debians.html#environment-setup).

Every terminal should be configured with 
```
source /opt/ros/rolling/setup.bash
```

If you have custom types in a specific ROS colcon directory, `source` the `setup.bash` in that directory. 


### Build the repo 

The repo is built with 
```
cargo build
```
If you want to deploy with production system, use `cargo build --release` option for optimization level and removal of debug logs. 

## Run with Different Machines
In the example, we use two machines to show talker (machine A) and listener (machine B) example. 

#### Certificate Generation
The certificates can be generated by 
```
cd scripts
./generate_crypto.sh
```
Every directory in `./scripts/crypto` contains the cryptographic secrets needed for communication. 

Distribute the `crypto` directory by from machine A and machine B. Here is an example with `scp`: 
```
scp -r crypto USER@MACHINE_B_IP_ADDR:/SGC_PATH/scripts/
```
replace `USER`, `MACHINE_B_IP_ADDR`, `SGC_PATH` with the actual paths.

After the crypto secrets are delivered, go back to project main directory. 

#### Run ROS2 talker and listener
Now run talker and listener on ROS2. 
Machine A:
```
ros2 run demo_nodes_cpp talker
```
and
Machine B 
```
ros2 run demo_nodes_cpp listener
```

The listener may not get messages from Machine A. If they are in the same local network/machine, SGC is not needed.

#### Run with Environment Variables 
Run FogROS2-SGC routers on the root project directory. 
On the machine A
```
export SGC_CONFIG=talker.toml
cargo run router
```
On the machine B
```
export SGC_CONFIG=listener.toml
cargo run router
```

The talker and listener toml configuration file can be found [here](./src/resources/README.md). The configuration is currently coded with a Berkeley's signaling server that facilitates the routing inforamtion exchange. See [Making your own signaling server](#making-your-own-signaling-server) section for creating your own signaling server.
The system should also work if you don't specify the configuration file, then it uses automatic mode that 
constantly checking for new topics. We note that it is only a convenient interface and not FogROS2-SGC is designed for.
As long as the talker and listener use the same crypto, the system should work.

To disable the logs and run with high optimization, run with `release` option by 
`
cargo run --release router
`
instead.


## From SGC to SGC-lite
The updated configuration file format can be found [here](./src/resources/README.md), which we removed all the setup about protocols, ports, ips and gateways. Only one change on the signaling server field `signaling_server_address = "ws://128.32.37.42:8000"` is required to the old config file. The default signaling server is provided by Berkeley, but feel free to make your own server by the following instructions.

(Note: remember to migrate the credentials from `./scripts` to the new repo as well!)


#### Why Lite version 

The FogROS2-SGC carries a bag of protocols to support heterogenous demands and requirements. 
In this version, we streamline the routing setup by [webrtc](./docs/webrtc.md) instead of building all protocols with raw DTLS sockets.
webrtc is generally not compatible with the previous protocol. As a result, we make a lite version with only webrtc version. 


#### Deploying Your Own Routing Infrastructure
The simplest routing infrastructure consists a signaling server and a routing information base(RIB). 
This can be done by running 
```
docker compose up -d signal rib
```
The only requirement is to expose port 8000 and 8002 to other robots/machines. 

Signaling server faciliates the communication by exchanging the address information of webrtc. The details about how signaling server works can be found [HERE](./docs/webrtc.md).

#### Notes on using Berkeley's Public Servers
Berkeley's public servers are for experimental purposes and do not intend to be used for production system. We do not provide any guarantee on avaialbility. Please use your own signaling server for benchmarking and deployment.
The security guarnatees of FogROS2-SGC prevents other users/Berkeley from learning sensitive information, such as your ROS2 topic name and type, and on the actual data payload. What is visible is a random 256 bit name are published and subscribed by other random 256 bit names. 

#### TODOs 
1. expiration time for stale keys (this may happen if the subscriber suddenly drops off and does not connect to an existing publisher)
2. in some rare cases, the IP address and port provided cannot connect, which blocks the publisher and subscriber. I noticed this only when running docker's talker on the edge and docker's listener on the cloud. (it works fine even if one of them is native) This happens periocially and sometime it just works. I don't know why. My hypothesis is some NAT issues with docker engine.
