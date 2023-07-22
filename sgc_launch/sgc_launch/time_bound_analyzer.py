
import subprocess, os, yaml
import requests
import pprint
import socket 
import time 
import rclpy
import rclpy.node
from sgc_msgs.msg import Profile
from .utils import get_ROS_class
import psutil

class SGC_Analyzer(rclpy.node.Node):
    def __init__(
            self,
            identity,
            request_topic, 
            request_topic_type,
            response_topic, 
            response_topic_type,
            latency_bound = 10
            ):
        super().__init__('sgc_time_bound_analyzer')
        # self.source_topic = request_topic
        # self.response = response_topic
        self.latency_bound = latency_bound
        self.logger = self.get_logger()

        self.request_topic = self.create_subscription(
            get_ROS_class(request_topic_type),
            request_topic,
            self.request_topic_callback,
            10)

        self.response_topic = self.create_subscription(
            get_ROS_class(response_topic_type),
            response_topic,
            self.response_topic_callback,
            10)
        
        self.status_publisher = self.create_publisher(Profile, 'sgc_profile', 10)

        self.profile = Profile()
        self.profile.identity.data = identity
        self.profile.ip_addr.data = socket.gethostname()
        self.profile.num_cpu_core = psutil.cpu_count()
        freq = [freq.current for freq in psutil.cpu_freq(True)]
        average_freq = sum(freq) / len(freq)
        self.logger.info(f"{freq}")
        self.profile.cpu_frequency = float(average_freq)

        self.create_timer(1, self.timer_callback)

        # Current heuristic: 
        # response_timestamp - the latest previous request timestamp 
        # this works if the resposne can catch up with the request rate 
        # if the rate cannot be controlled, simply publish message 
        # to some topic that indicates the start and end the request 
        self.last_request_time = None 
        self.last_response_time = None 
        self.latency_sliding_window = []

    def request_topic_callback(self, msg):
        self.last_request_time = time.time_ns()
    def response_topic_callback(self, msg):
        self.latency_sliding_window.append(time.time_ns() - self.last_request_time)

    def timer_callback(self):
        latency = 0
        if self.latency_sliding_window:
            latency = sum(self.latency_sliding_window) / len(self.latency_sliding_window) / 1000000000
            self.get_logger().info(f"Average latency is {latency}")
        self.latency_sliding_window = []
        self.profile.latency = float(latency)
        self.status_publisher.publish(self.profile)
