import requests 
uri = "http://localhost:3000/add"

ros_topic = {
    "action": "pub",
    "topic_name": "/chatter",
    "topic_type": "std_msgs/msg/String",
}

# Create a new resource
response = requests.post(uri, json = ros_topic)
print(response)