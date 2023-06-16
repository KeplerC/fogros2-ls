import requests 
from time import sleep

def send_request(
    api_op, 
    ros_op,
    topic = "/chatter",
    type = "std_msgs/msg/String", 
    uri = "http://localhost:3000/add"

):
    sleep(2)
    ros_topic = {
        "api_op": api_op,
        "ros_op": ros_op,
        "crypto": "test_cert",
        "topic_name": topic,
        "topic_type": type,
    }
    # Create a new resource
    response = requests.post(uri, json = ros_topic)
    print(response)

send_request("add", "sub", topic = "/chatter2")
send_request("add", "pub", topic = "/chatter2")  
send_request("add", "sub")
send_request("add", "pub")
send_request("del", "sub")