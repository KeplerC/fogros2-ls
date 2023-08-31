
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
from sklearn.cluster import KMeans
import jenkspy

# calculate if the latency is within the bound
# considering: 
# max latency, average, mean, sigma, min_latency
class Time_Bound_Analyzer(rclpy.node.Node):
    def __init__(self):
        super().__init__('sgc_time_bound_analyzer')

        self.declare_parameter("whoami", "")
        self.identity = self.get_parameter("whoami").value
        self.declare_parameter("latency_window", 3.0)
        self.latency_window = self.get_parameter("latency_window").value

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

        self.create_timer(1, self.update_timer_callback)
        self.create_timer(self.latency_window, self.stats_timer_callback)

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
            mean_latency = sum(self.latency_sliding_window) / len(self.latency_sliding_window)
            max_latency = max(self.latency_sliding_window)
            min_latency = min(self.latency_sliding_window)
            median_latency = np.median(self.latency_sliding_window)
            std_latency = np.std(self.latency_sliding_window)
            self.get_logger().info("Latency: mean: {:.2f}, max: {:.2f}, min: {:.2f}, median: {:.2f}, std: {:.2f}".format(
                mean_latency, max_latency, min_latency, median_latency, std_latency
            ))
            self.profile.min_latency = min_latency
            self.profile.max_latency = max_latency
            self.profile.mean_latency = mean_latency
            self.profile.median_latency = median_latency
            self.profile.std_latency = std_latency
            
            gvf = 0.0
            b = -1.0
            try:
                for nclasses in [2, 3, 4, 5, 6]:
                    gvf, b = goodness_of_variance_fit(np.array(self.latency_sliding_window), nclasses)
                    if gvf > 0.9:
                        break
                    
                self.profile.max_kmeans_latency = b
            except:
                pass
            
        else:
            self.get_logger().info("No latency data received")
            
        self.latency_sliding_window = []
        self.status_publisher.publish(self.profile)

        # reset all latencies 
        self.profile.min_latency = -1.0
        self.profile.max_latency = -1.0
        self.profile.mean_latency = -1.0
        self.profile.median_latency = -1.0
        self.profile.std_latency = -1.0
        self.profile.max_kmeans_latency = -1.0

def main():
    rclpy.init()
    node = Time_Bound_Analyzer()
    rclpy.spin(node)

if __name__ == '__main__':
    main()

def goodness_of_variance_fit(array, classes):
    # get the break points
    classes = jenkspy.jenks_breaks(array, classes)

    # do the actual classification
    classified = np.array([classify(i, classes) for i in array])
    
    stat = 0
    
    separated_arrays = []
    
    for i in range(len(classes) - 1):
        idx = np.where(np.logical_and(array >= classes[i], array < classes[i+1]))
        separated_arrays.append(array[idx])

    for i in range(len(separated_arrays)-1, -1, -1):
        if len(separated_arrays[i]) / len(array) > 0.05:
            stat = np.mean(separated_arrays[i])
            break

    # max value of zones
    maxz = max(classified)

    # nested list of zone indices
    zone_indices = [[idx for idx, val in enumerate(classified) if zone + 1 == val] for zone in range(maxz)]

    # sum of squared deviations from array mean
    sdam = np.sum((array - array.mean()) ** 2)

    # sorted polygon stats
    array_sort = [np.array([array[index] for index in zone]) for zone in zone_indices]

    # sum of squared deviations of class means
    sdcm = sum([np.sum((classified - classified.mean()) ** 2) for classified in array_sort])

    # goodness of variance fit
    gvf = (sdam - sdcm) / sdam

    return gvf, stat

def classify(value, breaks):
    for i in range(1, len(breaks)):
        if value < breaks[i]:
            return i
    return len(breaks) - 1