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

def reverse_topic_direction(topic_list):
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
    # print(f"topic {topic.name} with operation {api_op} request sent with response {response}")

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
# cloud_ip = "localhost"
# robot_ip = "localhost"
# cloud_ip = "128.32.37.48"
# robot_ip = "128.32.37.48"

# service_topics = [
#     Topic(
#         "/offload_detection/scheduler_yolo/input/cloud", 
#         "sensor_msgs/msg/CompressedImage", 
#         "pub"
# ), Topic(
#         "/offload_detection/scheduler_yolo/output/cloud", 
#         "sensor_msgs/msg/CompressedImage", 
#         "sub"
# )]
# robot_topics = reverse_topic_direction(service_topics)

# cloud = Machine(f"{cloud_ip}:3001")
# robot = Machine(f"{robot_ip}:4001")

# while True:
#     add_topics_to_machine(service_topics, cloud)
#     add_topics_to_machine(robot_topics, robot)
#     input("ENTER to remove Topics")
#     remove_topics_from_machine(service_topics, cloud)
#     remove_topics_from_machine(robot_topics, robot)
#     input("ENTER to add Topics")




# 

service_topics = [
    Topic(
        "/offload_detection/scheduler_yolo/input/cloud", 
        "sensor_msgs/msg/CompressedImage", 
        "pub"
), Topic(
        "/offload_detection/scheduler_yolo/output/cloud", 
        "sensor_msgs/msg/CompressedImage", 
        "sub"
)]
robot_topics = reverse_topic_direction(service_topics)

# cloud = Machine(f"{cloud_ip}:3001")
# edge = Machine(f"{edge_ip}:3001")
# robot = Machine(f"{robot_ip}:3001")

# print("Running camera node on robot")
# add_topics_to_machine(robot_topics, robot)
# add_topics_to_machine(service_topics, cloud)
# while True:
#     input("ENTER to migrate to the edge")
#     add_topics_to_machine(service_topics, edge)
#     remove_topics_from_machine(service_topics, cloud)

#     input("ENTER to migrate to the cloud")
#     add_topics_to_machine(service_topics, cloud)
#     remove_topics_from_machine(service_topics, edge)


sam_cloud_ip = "54.183.212.211"
yolo_cloud_ip = "localhost"
robot_ip = "128.32.37.48"

cloud = Machine(f"{sam_cloud_ip}:3000")
edge = Machine(f"{yolo_cloud_ip}:3000")
robot = Machine(f"{robot_ip}:4001")

add_topics_to_machine(robot_topics, robot)
add_topics_to_machine(service_topics, edge)


while True: 
    input("ENTER to migrate to the cloud (SAM)")
    add_topics_to_machine(service_topics, cloud)
    remove_topics_from_machine(service_topics, edge)

    input("ENTER to migrate to the edge (YOLO)")
    add_topics_to_machine(service_topics, edge)
    remove_topics_from_machine(service_topics, cloud)


