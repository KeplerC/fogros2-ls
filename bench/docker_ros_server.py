import requests 
from time import sleep

# available actions 
# pub enum FibChangeAction {
#     ADD,
#     PAUSE, // pausing the forwarding of the topic, keeping connections alive
#     PAUSEADD, // adding the entry to FIB, but keeps it paused
#     RESUME, // resume a paused topic
#     DELETE, // deleting a local topic interface and all its connections 
# }


def send_request(
    api_op, 
    ros_op = "noop",
    topic = "/chatter",
    type = "std_msgs/msg/String", 
    ip = "localhost", 
    port = "3000"
):
    ros_topic = {
        "api_op": api_op,
        "ros_op": ros_op,
        "crypto": "test_cert",
        "topic_name": topic,
        "topic_type": type,
    }
    uri = f"http://{ip}:{port}/topic"
    # Create a new resource
    response = requests.post(uri, json = ros_topic)
    print(response)
 
print("adding listener")
send_request("add", "pub", ip = "fogros2-sgc-lite-listener-1")

print("adding talker")
send_request("add", "sub", ip = "fogros2-sgc-lite-talker-1")

sleep(5)

print("remove the topic of talker's published topic")
send_request("del", "sub", ip = "fogros2-sgc-lite-talker-1")

sleep(5)
print("adding it back")
send_request("add", "sub", ip = "fogros2-sgc-lite-talker-1")


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