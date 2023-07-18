# ROS Launchable FogROS2-SGC

### Configuartion file 

FogROS2-SGC requires a separate configuration file to expose the topics. While it supports automatic topic scanning, we want the users to expose the topics globally only if they want to, to enhance the isolation and protect the privacy of the robots and services. An example of the configuration file can be found as following: 

```
identifiers: 
  # crypto for the task (same for all robots/services on the same task)
  task: test_cert 
  # crypto unique for the robot 
  # note #0 : 
  # for now, it's not bound to an actual certificate yet, name whatever you want
  # but make sure to match this with the assignment 
  # note #1 : this value is overriden by rosparam's whoami
  # note #2 : feel free to define it here or define it at rosparam
  whoami: machine_talker 
  
topics:
  - topic_name: /chatter
    topic_type: std_msgs/msg/String

# declare possible states 
# pub: publish to the swarm
# sub: subscribe to the swarm
# note this is reversed from prior version of SGC config file
state_machine: 
  talker: 
    topics:
      - /chatter: pub 
  listener: 
    topics:
      - /chatter: sub 

# name: state
# name need to match the identitifer's whoami
# state should be declared in possible states 
# Phase 1: only allow changing the assignment at runtime 
assignment:
  machine_talker: talker
  machine_listener: listener
```

We observe that the cloud services are usually the reversed of the robots' configuration file (e.g. cloud is the publisher then robot is the subscriber). We want the user only need to write and distribute one copy of the configuration file, and mark themselves as different only at `whoami` in `identifiers`. This value is overriden by the ros2 launch file's parameter. 

In the example, the configuration configures `whoami` as `machine_talker`, which is assigned with the `talker`'s state (at a`assignment`). The `talker` state is defined to `pub` (publish) to the topic `chatter`. The `chatter` is configured to be of type `std_msgs/msgs/String`. Vise versa, the listener only need to set `whoami` as `machine_listener`, and the states (how the topics are handled) are automated. 


## Examples 

### Profiling Example 
Remember to `colcon build` and `source install/setup.bash` the workspace. 

On local robot, run robot sensors by 
```
ros2 launch sgc_launch profiler.robot.launch.py 
```
then we run the local service modules by 
```
ROS_DOMAIN_ID=2 ros2 launch sgc_launch profiler.service.local.launch.py
```
We use different domain ID, and use FogROS-SGC to bridge them. 


On the cloud, run 
```
ROS_DOMAIN_ID=1 ros2 launch sgc_launch profiler.service.cloud.launch.py
```
by default, the cloud will be in standby state and only active when reconfigured. 


For reconfiguration, run 
```
ROS_DOMAIN_ID=2 ros2 service call /sgc_assignment_service sgc_msgs/srv/SgcAssignment '{machine: {data: "machine_local"}, state: {data: "standby"} }'
```
to change the local service to be the standby mode (doesn't do anything). 
To resume, run 
```
ROS_DOMAIN_ID=2 ros2 service call /sgc_assignment_service sgc_msgs/srv/SgcAssignment '{machine: {data: "machine_local"}, state: {data: "service"} }'
```
TODO: later wrap this in a more user friendly CLI


### H264 Example 

```
cd sgc_ws/src
git clone https://github.com/KeplerC/h264_image_transport.git
```

The SGC will automatically incoperate H264 streaming ROS2 message type in its build system. 


### Automated version without configuration file 

SGC supports autoamtic topic discovery by simply not setting the configuration file. This works with heristics that if the topic misses the publisher (publisher count = 0), then it exposes as a remote subscriber, and vise versa. 


