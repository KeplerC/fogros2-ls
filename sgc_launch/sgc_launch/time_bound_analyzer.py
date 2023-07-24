
import subprocess, os, yaml
import requests
import pprint
import socket 
import time 
import rclpy
import rclpy.node
from sgc_msgs.msg import Profile
from .utils import *
import psutil
import matplotlib.pyplot as plt
import pandas as pd 
import seaborn as sns
import numpy as np 
from rcl_interfaces.msg import SetParametersResult

class SGC_Analyzer(rclpy.node.Node):
    def __init__(self):
        super().__init__('sgc_time_bound_analyzer')

        self.declare_parameter("whoami", "")
        self.identity = self.get_parameter("whoami").value

        # in second 
        self.declare_parameter("latency_bound", 0.0)
        self.latency_bound = self.get_parameter("latency_bound").value

        # topic to subscribe to know the start and end of the benchmark
        self.declare_parameter("request_topic_name", "")
        request_topic = self.get_parameter("request_topic_name").value
        self.declare_parameter("request_topic_type", "")
        request_topic_type = self.get_parameter("request_topic_type").value
        self.declare_parameter("response_topic_name", "")
        response_topic = self.get_parameter("response_topic_name").value
        self.declare_parameter("response_topic_type", "")
        response_topic_type = self.get_parameter("response_topic_type").value

        # whether or not to generate a plot
        self.declare_parameter("plot", False)
        self.plot = self.get_parameter("plot").value

        self.logger = self.get_logger()

        self.machine_dict = dict()
        self.current_timestamp = int(time.time()) + 1
        self.latency_df = pd.DataFrame(
            [{
                "timestamp": self.current_timestamp,
                "robot": np.nan,
                "machine_local": np.nan,
            }]
        )
        # used for maintaining the current dataframe index
        

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
        
        self.status_publisher = self.create_publisher(Profile, 'fogros_sgc/profile', 10)

        # subscribe to the profile topic from other machines (if any)
        self.status_topic = self.create_subscription(
            Profile,
            'fogros_sgc/profile',
            self.profile_topic_callback,
            10)
        self.add_on_set_parameters_callback(self.parameters_callback)
        
        self.profile = Profile()
        self.profile.identity.data = self.identity
        self.profile.ip_addr.data = get_public_ip_address()
        self.profile.num_cpu_core = psutil.cpu_count()
        freq = [freq.current for freq in psutil.cpu_freq(True)]
        average_freq = sum(freq) / len(freq)
        self.logger.info(f"{freq}")
        self.profile.cpu_frequency = float(average_freq)

        self.machine_dict[self.identity] = self.profile

        self.create_timer(3, self.timer_callback)

        # Current heuristic: 
        # response_timestamp - the latest previous request timestamp 
        # this works if the resposne can catch up with the request rate 
        # if the rate cannot be controlled, simply publish message 
        # to some topic that indicates the start and end the request 
        self.last_request_time = None 
        self.last_response_time = None 
        self.latency_sliding_window = []

    def request_topic_callback(self, msg):
        self.last_request_time = time.time()
        self.logger.info(f"request: {self.last_request_time}")

    def response_topic_callback(self, msg):
        self.latency_sliding_window.append((time.time() - self.last_request_time))
        self.logger.info(f"response: {time.time()}, {(time.time() - self.last_request_time)}")

    def profile_topic_callback(self, profile_update):
        if profile_update.identity.data == self.identity:
            # same update from its own publisher, we are only interested in other machine's
            # updates 
            return 
        self.machine_dict[profile_update.identity.data] = profile_update
        if profile_update.latency:
            self.latency_df = pd.concat(
                    [self.latency_df, pd.DataFrame([
                        {
                        "timestamp": self.current_timestamp,
                        "robot": np.nan,
                        "machine_local": profile_update.latency,
                        }
                    ])]
                )
            
    # run every second to calculate the profile message and publish
    def timer_callback(self):
        latency = 0
        self.current_timestamp = int(time.time()) + 1 # round up
        # self.latency_df = pd.concat(
        #     [self.latency_df, pd.DataFrame([current_timestamp, None, None])], ignore_index=True
        # )
        
        if self.latency_sliding_window:
            latency = sum(self.latency_sliding_window) / len(self.latency_sliding_window) # / 1000000000
            self.get_logger().info(f"Average latency is {latency} out of {sorted(self.latency_sliding_window)}")
            self.latency_df = pd.concat(
                [self.latency_df, pd.DataFrame([
                    {
                    "timestamp": self.current_timestamp,
                    "robot": latency,
                    "machine_local": np.nan,
                    }
                ])]
            )
            
        self.latency_sliding_window = []
        self.profile.latency = float(latency)
        self.status_publisher.publish(self.profile)
        if self.plot:
            self.plot_latency_history()

    def plot_latency_history(self):
        try:
            #https://stackoverflow.com/questions/56170909/seaborn-lineplot-high-cpu-very-slow-compared-to-matplotlib
            sns.lineplot(data = self.latency_df.set_index("timestamp"), x = "timestamp", y = "robot", errorbar=None, palette="Accent")
            sns.lineplot(data = self.latency_df.set_index("timestamp"), x = "timestamp", y = "machine_local", errorbar=None, palette="Accent")
            plt.axhline(y = self.latency_bound, color = 'r', linestyle = '-')
            plt.legend(labels=['End-to-end', 'Compute', 'time bound'])
            plt.savefig("./plot.png")
        except:
            pass
        
    def parameters_callback(self, params):
        # do some actions, validate parameters, update class attributes, etc.
        for param in params:
            if param._name == "latency_bound":
                self.latency_bound = param._value
                self.logger.warn(f"successfully changing {vars(param)} to {self.latency_bound}")
                plt.clf()
            else:
                self.logger.warn(f"changing {vars(param)} is not supported yet")
        return SetParametersResult(successful=True)
    
    def get_the_best_machine(self):
        # get the best machine based on current spec collected 
        # param = optimize_compute vs optimize 
        # if machine has gpu 
        # else cpu_core >= cpu_core:
        # else cpu_frequency 

        # check networking 
        pass 

def main():
    rclpy.init()
    node = SGC_Analyzer()
    rclpy.spin(node)

if __name__ == '__main__':
    main()
