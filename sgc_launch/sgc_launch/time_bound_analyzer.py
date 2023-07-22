
import subprocess, os, yaml
import requests
import pprint
import time 
import rclpy
import rclpy.node

from .utils import get_ROS_class

class SGC_Analyzer(rclpy.node.Node):
    def __init__(self,
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
        self.logger.info(f"request_topic_time: {self.last_request_time}")
    def response_topic_callback(self, msg):
        self.latency_sliding_window.append(time.time_ns() - self.last_request_time)
        self.logger.info(f"response_topic_time: {self.latency_sliding_window}")

    def timer_callback(self):
        if self.latency_sliding_window:
            self.get_logger().info(f"Average latency is {sum(self.latency_sliding_window) / len(self.latency_sliding_window) / 1000000000}")
        self.latency_sliding_window = []