
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

# calculate if the latency is within the bound
# considering: 
# max latency, average, mean, sigma, min_latency
class Time_Bound_Analyzer(rclpy.node.Node):
    def __init__(self):
        super().__init__('sgc_time_bound_analyzer')

        self.declare_parameter("whoami", "")
        self.identity = self.get_parameter("whoami").value

        self.latency_topic = self.create_subscription(
            get_ROS_class("std_msgs/msg/Float64"),
            "fogros_sgc/latency",
            self.latency_topic_callback,
            1)

        self.logger = self.get_logger()

        self.machine_dict = dict()
        self.current_timestamp = int(time.time()) + 1

        # used for maintaining the current dataframe index        
        self.profile = Profile()
        self.profile.identity.data = self.identity
        self.profile.ip_addr.data = get_public_ip_address()
        self.profile.num_cpu_core = psutil.cpu_count()
        freq = [freq.current for freq in psutil.cpu_freq(True)]
        average_freq = sum(freq) / len(freq)
        self.logger.info(f"{freq}")
        self.profile.cpu_frequency = float(average_freq)

        try:
            import pynvml
            pynvml.nvmlInit()
            self.has_gpu = pynvml.nvmlDeviceGetCount() > 0
            if not self.has_gpu:
                print(f"No GPU with ID {self.gpu_id} found.")
        except pynvml.NVMLError_LibraryNotFound:
            print("NVIDIA driver not installed.")
            self.has_gpu = False
        self.profile.has_gpu = self.has_gpu

        self.status_publisher = self.create_publisher(Profile, 'fogros_sgc/profile', 10)

        self.add_on_set_parameters_callback(self.parameters_callback)

        self.create_timer(1, self.update_timer_callback)
        self.create_timer(3, self.stats_timer_callback)

        self.latency_sliding_window = []

    def latency_topic_callback(self, latency_msg):
        # for now, message is defined as a string
        # identity, type, latency 
        self.latency_sliding_window.append(latency_msg.data)

    def update_timer_callback(self):
        self.current_timestamp = int(time.time()) + 1 # round up

    # run every X second to calculate the profile message and publish to the topic 
    # if it's the controller node (i.e. robot), also check if the latency is within the bound
    def stats_timer_callback(self):
        latency = 0
        # self.latency_df = pd.concat(
        #     [self.latency_df, pd.DataFrame([current_timestamp, None, None])], ignore_index=True
        # )
        
        if self.latency_sliding_window:
            latency = sum(self.latency_sliding_window) / len(self.latency_sliding_window) # / 1000000000
            self.get_logger().info(f"Average latency is {latency} out of {sorted(self.latency_sliding_window)}")
            # self.latency_df = pd.concat(
            #     [self.latency_df, pd.DataFrame([
            #         {
            #         "timestamp": self.current_timestamp,
            #         "latency": latency,
            #         "machine": self.identity,
            #         }
            #     ])], ignore_index=True
            # )

            # TODO: need to record the history of the attempts, currently it only gets the best one 
            # there might be some machine in the middle that can get both (e.g. an edge server)
            if self.enforce_time_bound_analysis:
                need_better_compute, need_better_network = self._check_latency_bound()
                if need_better_compute:
                    machine = self._get_machine_with_better_compute()
                    self.logger.info(f"need better compute; switching to machine {machine}")
                    self._switch_to_machine(machine)
                elif need_better_network:
                    machine = self._get_machine_with_best_network()
                    self.logger.info(f"need better network; switching to machine {machine}")
                    self._switch_to_machine(machine)
            
            
        self.latency_sliding_window = []
        self.profile.latency = float(latency)
        self.status_publisher.publish(self.profile)

    def parameters_callback(self, params):
        for param in params:
            if param._name == "compute_latency_bound":
                self.compute_latency_bound = param._value
                self.logger.warn(f"successfully changing {vars(param)} to {self.compute_latency_bound}")
                plt.clf()
            if param._name == "network_latency_bound":
                self.network_latency_bound = param._value
                self.logger.warn(f"successfully changing {vars(param)} to {self.network_latency_bound}")
                plt.clf()
            else:
                self.logger.warn(f"changing {vars(param)} is not supported yet")
        return SetParametersResult(successful=True)

def main():
    rclpy.init()
    node = Time_Bound_Analyzer()
    rclpy.spin(node)

if __name__ == '__main__':
    main()
