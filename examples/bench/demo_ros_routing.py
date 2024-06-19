import requests 
from time import sleep
import yaml
import hashlib
switch = "localhost:3003"
server = "localhost:3002"
client = "localhost:3005"

# def send_routing_request(addr, source_or_destination, sender_url, receiver_url, connection_type):
#     send_routing_request_service(addr, source_or_destination, sender_url, receiver_url, connection_type)
#     send_routing_request_topic(addr, source_or_destination, sender_url, receiver_url, connection_type)

def send_routing_request_service(addr, source_or_destination, sender_url, receiver_url, connection_type):
    sha = hashlib.sha256()
    sha.update(sender_url.encode())
    sender_url = sha.hexdigest()
    sha = hashlib.sha256()
    sha.update(receiver_url.encode())
    receiver_url = sha.hexdigest()
    ros_topic = {
        "api_op": "routing",
        "ros_op": source_or_destination,
        "crypto": "test_cert",
        "topic_name": "/add_three_ints",
        "topic_type": "bench_msgs/srv/AddThreeInts",
        "connection_type": connection_type,
        "forward_sender_url": sender_url, 
        "forward_receiver_url": receiver_url
    }
    print(addr, ros_topic)
    uri = f"http://{addr}/service"
    # Create a new resource
    response = requests.post(uri, json = ros_topic)
    print(response)
    sleep(1)


def send_routing_request_topic(addr, source_or_destination, sender_url, receiver_url, connection_type):
    sha = hashlib.sha256()
    sha.update(sender_url.encode())
    sender_url = sha.hexdigest()
    sha = hashlib.sha256()
    sha.update(receiver_url.encode())
    receiver_url = sha.hexdigest()
    ros_topic = {
        "api_op": "routing",
        "ros_op": source_or_destination,
        "crypto": "test_cert",
        "topic_name": "/chatter",
        "topic_type": "std_msgs/msg/String",
        "connection_type": connection_type,
        "forward_sender_url": sender_url, 
        "forward_receiver_url": receiver_url
    }
    print(addr, ros_topic)
    uri = f"http://{addr}/topic"
    # Create a new resource
    response = requests.post(uri, json = ros_topic)
    print(response)
    sleep(1)

class Node:
    def __init__(self, address, is_compute=False, parent=None):
        self.address = address
        self.is_compute = is_compute
        self.children = []
        self.parent = parent

def build_tree(node_dict, parent=None):
    address = node_dict.get("address")
    is_compute = node_dict.get("is_compute", False)
    node = Node(address, is_compute, parent)
    
    for child_dict in node_dict.get("children", []):
        child_node = build_tree(child_dict, node)
        node.children.append(child_node)
    
    return node

def print_tree(node, level=0):
    print("  " * level + f"{node.address}, is_compute: {node.is_compute}")
    for child in node.children:
        print_tree(child, level + 1)


def construct_tree_by_sending_request_service(node):
    for child in node.children:
        # uniquely identify the session
        session_id = node.address + child.address

        # establish request channel from node to child
        send_routing_request_service(
            node.address,
            "source",
            "request" + node.address + session_id,
            "request" + child.address + session_id,
            "request"
        )
        send_routing_request_service(
            child.address,
            "destination",
            "request" + node.address + session_id,
            "request" + child.address + session_id,
            "request"
        )

        # establish response channel from child to node
        send_routing_request_service(
            child.address,
            "source",
            "response" + child.address + session_id,
            "response" + node.address + session_id,
            "response"
        )
        send_routing_request_service(
            node.address,
            "destination",
            "response" + child.address + session_id,
            "response" + node.address + session_id,
            "response"
        )
        construct_tree_by_sending_request_service(child)

def construct_tree_by_sending_request_topic(node):
    for child in node.children:
        # uniquely identify the session
        session_id = node.address + child.address

        # establish request channel from node to child
        send_routing_request_topic(
            node.address,
            "source",
            "topic" + node.address + session_id,
            "topic" + child.address + session_id,
            "pub"
        )
        send_routing_request_topic(
            child.address,
            "destination",
            "topic" + node.address + session_id,
            "topic" + child.address + session_id,
            "pub"
        )
        construct_tree_by_sending_request_topic(child)


with open("topology.yaml") as f:
    yaml_str = f.read()

# Load YAML into a Python dictionary
yaml_dict = yaml.safe_load(yaml_str)

# Build the tree
root_dict = yaml_dict['root']
root_node = build_tree(root_dict)
print_tree(root_node)
construct_tree_by_sending_request_service(root_node)
construct_tree_by_sending_request_topic(root_node)
