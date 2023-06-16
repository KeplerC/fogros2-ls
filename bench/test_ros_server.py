import requests 
uri = "http://localhost:3000/add"

ros_topic = {
    "api_op": "add",
    "ros_op": "pub",
    "crypto": "test_cert",
    "topic_name": "/chatter",
    "topic_type": "std_msgs/msg/String",
}

# Create a new resource
response = requests.post(uri, json = ros_topic)

ros_topic = {
    "api_op": "add",
    "ros_op": "sub",
    "crypto": "test_cert",
    "topic_name": "/chatter",
    "topic_type": "std_msgs/msg/String",
}

# Create a new resource
response = requests.post(uri, json = ros_topic)
print(response)