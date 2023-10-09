
import subprocess, os, yaml
import requests
import pprint
import socket 
import time 
import rclpy
import rclpy.node
from sgc_msgs.msg import Profile
from sgc_msgs.srv import SgcAssignment
from .utils import *
import psutil
import matplotlib.pyplot as plt
import pandas as pd 
import seaborn as sns
import numpy as np 
from rcl_interfaces.msg import SetParametersResult
from sgc_msgs.msg import Latency
from std_msgs.msg import Float64

class HeuristicPubSub(rclpy.node.Node):
    def __init__(self):
        super().__init__('heuristic_pubsub')


        self.declare_parameter("whoami", "")
        self.identity = self.get_parameter("whoami").value

        # topic to subscribe to know the start and end of the benchmark
        self.declare_parameter("request_topic_name", "")
        request_topic = self.get_parameter("request_topic_name").value
        self.declare_parameter("request_topic_type", "")
        request_topic_type = self.get_parameter("request_topic_type").value
        self.declare_parameter("response_topic_name", "")
        response_topic = self.get_parameter("response_topic_name").value
        self.declare_parameter("response_topic_type", "")
        response_topic_type = self.get_parameter("response_topic_type").value

        self.logger = self.get_logger()

        self.request_topic = self.create_subscription(
            get_ROS_class(request_topic_type),
            request_topic,
            self.request_topic_callback,
            1)

        self.response_topic = self.create_subscription(
            get_ROS_class(response_topic_type),
            response_topic,
            self.response_topic_callback,
            1)
        
        self.latency_publisher = self.create_publisher(Latency, 'fogros_sgc/latency', 10)


    
    def request_topic_callback(self, msg):
        self.last_request_time = time.time()
        self.logger.info(f"request: {self.last_request_time}")

    # calculate latency based on heuristics
    def response_topic_callback(self, msg):
        latency = Latency()
        latency.latency = (time.time() - self.last_request_time)
        latency.identity = self.identity
        self.latency_publisher.publish(latency)
        self.logger.info(f"response: {time.time()}, {(time.time() - self.last_request_time)}")

def main():
    rclpy.init()
    node = HeuristicPubSub()
    rclpy.spin(node)

if __name__ == '__main__':
    main()
