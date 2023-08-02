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
    uri = f"http://{machine.address}/service"
    # Create a new resource
    response = requests.post(uri, json = ros_topic)
    print(response)

def add_topics_to_machine(topics, machine):
    for topic in topics:
        send_request("add", topic, machine)
        # sleep(2)

def remove_topics_from_machine(topics, machine):
    for topic in topics:
        send_request("del", topic, machine)
        # sleep(2)
        
robot_service = [
    Topic(
    "/add_two_ints", "example_interfaces/srv/AddTwoInts", "client"
)]

server_service = [
    Topic(
    "/add_two_ints", "example_interfaces/srv/AddTwoInts", "service"
)]

# robot_topics = reverse_topics(service_topics)

# cloud = Machine("fogros2-sgc-lite-listener-1:3000")
robot = Machine("localhost:3000")

add_topics_to_machine(robot_service, robot)
# add_topics_to_machine(robot_topics, robot)
# input()
# remove_topics_from_machine(service_topics, cloud)
# remove_topics_from_machine(robot_topics, robot)

# talker_machine = ""
# listener_machine = ""

# print("adding listener")
# send_request("add", "pub", ip = listener_machine)

# print("adding talker")
# send_request("add", "sub", ip = talker_machine)

# sleep(5)

# print("remove the topic of talker's published topic")
# send_request("del", "sub", ip = talker_machine)

# sleep(5)
# print("adding it back")
# send_request("add", "sub", ip = talker_machine)


# for i in range(10):
#     sleep(1)
#     print(".")

# print("remove the topic of Machine 1's published topic")
# send_request("del", "sub", ip="172.190.80.56")
# print("have machine 2 (Another AWs) to publish the topic")
# send_request("add", "sub", ip="54.67.119.252")
# print("locally publish chatter topic")
# send_request("add", "pub")
# migration!
# print("remove the topic of Machine 1's published topic")
# send_request("del", "sub", ip="172.190.80.56")
# print("have machine 2 (Another AWs) to publish the topic")
# send_request("add", "sub", ip="54.67.119.252")