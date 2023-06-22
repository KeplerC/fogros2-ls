import requests 
from time import sleep

# available actions 
# pub enum FibChangeAction {
#     ADD,
#     PAUSE, // pausing the forwarding of the topic, keeping connections alive
#     PAUSEADD, // adding the entry to FIB, but keeps it paused
#     RESUME, // resume a paused topic
#     DELETE, // deleting a local topic interface and all its network connections 
# }

class Topic: 
    def __init__(self, name, type, action):
        self.name = name
        self.type = type 
        self.action = action

class Machine:
    def __init__(self, address):
        self.address = address

def reverse_topics(topic_list):
    ret = []
    for topic in topic_list:
        if topic.action == "sub":
            action = "pub"
        if topic.action == "pub":
            action = "sub"
        if topic.action == "noop":
            action = "noop"
        ret.append(Topic(
            topic.name,
            topic.type,
            action
        ))
    return ret

def send_request(
    api_op, 
    topic,
    machine, 
):
    ros_topic = {
        "api_op": api_op,
        "ros_op": topic.action,
        "crypto": "test_cert",
        "topic_name": topic.name,
        "topic_type": topic.type,
    }
    uri = f"http://{machine.address}/topic"
    # Create a new resource
    response = requests.post(uri, json = ros_topic)
    print(response)

def add_topics_to_machine(topics, machine):
    for topic in topics:
        send_request("add", topic, machine)

def remove_topics_from_machine(topics, machine):
    for topic in topics:
        send_request("del", topic, machine)
        
# service_topics = [
#     Topic(
#     "/offload_detection/profile/cloud", "offload_detection/msg/Profile", "sub"
# ), Topic(
#     "/offload_detection/scheduler_yolo/input/cloud", "sensor_msgs/msg/CompressedImage", "pub"
# ), Topic(
#     "/offload_detection/scheduler_yolo/output/cloud", "sensor_msgs/msg/CompressedImage", "sub"
# )]

service_topics = [
    Topic(
    "/offload_detection/scheduler_yolo/input/cloud", "sensor_msgs/msg/CompressedImage", "pub"
), Topic(
    "/offload_detection/scheduler_yolo/output/cloud", "sensor_msgs/msg/CompressedImage", "sub"
)]


robot_topics = reverse_topics(service_topics)

cloud = Machine("localhost:3001")
robot = Machine("localhost:4001")

while True:
    add_topics_to_machine(service_topics, cloud)
    add_topics_to_machine(robot_topics, robot)
    input("ENTER to remove Topcs")
    remove_topics_from_machine(service_topics, cloud)
    remove_topics_from_machine(robot_topics, robot)
    input("ENTER to add Topcs")