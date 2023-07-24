
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
        self.declare_parameter("network_latency_bound", 0.0)
        self.network_latency_bound = self.get_parameter("network_latency_bound").value
        self.declare_parameter("compute_latency_bound", 0.0)
        self.compute_latency_bound = self.get_parameter("compute_latency_bound").value

        # time bound analysis is only conducted if 
        self.enforce_time_bound_analysis = self.network_latency_bound > 0 or self.compute_latency_bound > 0

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
                "latency": np.nan,
                "machine": "",
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


        self.create_timer(1, self.update_timer_callback)
        self.create_timer(3, self.stats_timer_callback)

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

    # calculate latency based on heuristics
    def response_topic_callback(self, msg):
        self.latency_sliding_window.append((time.time() - self.last_request_time))
        self.logger.info(f"response: {time.time()}, {(time.time() - self.last_request_time)}")

    def profile_topic_callback(self, profile_update):
        self.logger.info(f"received profile update from {profile_update}")
        if profile_update.identity.data == self.identity:
            # same update from its own publisher, we are only interested in other machine's
            # updates 
            return 
        self.machine_dict[profile_update.identity.data] = profile_update
        if profile_update.latency and not (((self.latency_df['timestamp'] == self.current_timestamp) & (self.latency_df['machine'] == profile_update.identity.data)).any()):
            self.latency_df = pd.concat(
                    [self.latency_df, pd.DataFrame([
                        {
                        "timestamp": self.current_timestamp,
                        "latency": profile_update.latency,
                        "machine": profile_update.identity.data,
                        }
                    ])], ignore_index=True
                )
    
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
            self.latency_df = pd.concat(
                [self.latency_df, pd.DataFrame([
                    {
                    "timestamp": self.current_timestamp,
                    "latency": latency,
                    "machine": self.identity,
                    }
                ])], ignore_index=True
            )

            # TODO: need to record the history of the attempts, currently it only gets the best one 
            # there might be some machine in the middle that can get both (e.g. an edge server)
            if self.enforce_time_bound_analysis:
                need_better_compute, need_better_network = self._check_latency_bound()
                if need_better_compute:
                    machine = self._get_machine_with_best_compute()
                    self.logger.info(f"need better compute; switching to machine {machine}")
                    self._switch_to_machine(machine)
                elif need_better_network:
                    machine = self._get_machine_with_best_network()
                    self.logger.info(f"need better network; switching to machine {machine}")
                    self._switch_to_machine(machine)
            
                if self.plot:
                    self.plot_latency_history()
            
        self.latency_sliding_window = []
        self.profile.latency = float(latency)
        self.status_publisher.publish(self.profile)

    def plot_latency_history(self):
        #https://stackoverflow.com/questions/56170909/seaborn-lineplot-high-cpu-very-slow-compared-to-matplotlib
        try:
            sns.lineplot(data = self.latency_df, x = "timestamp", y = "latency", errorbar=None, hue = "machine")
            # sns.lineplot(data = self.latency_df.set_index("timestamp"), x = "timestamp", y = "machine_local", errorbar=None, color = "green")
            plt.axhline(y = self.compute_latency_bound, color = 'b', linestyle = '-.')
            plt.axhline(y = self.compute_latency_bound + self.network_latency_bound, color = 'r', linestyle = '-')
            # plt.legend(labels=['End-to-end', 'Compute', 'compute bound', 'total bound'])
            plt.savefig("./plot.png")
            plt.clf()
        except Exception as e:
            self.logger.info(self.latency_df.to_string())
            self.logger.error(f"plotting error {e}")
        
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
    
    # check if the latency is within the bound using heuristics
    def _check_latency_bound(self):
        
        # get the latency from the dataframe for the last 15 seconds
        # replace 0 with NaN so that it doesn't affect the average
        # https://stackoverflow.com/questions/35608893/calculate-minimums-in-pandas-without-zero-values
        self.latency_df_of_current_timestamps = self.latency_df[self.latency_df['timestamp'] > self.current_timestamp - 15].replace(0, np.NaN)
        self.logger.info(f"latency at the past 15 second {self.latency_df_of_current_timestamps.to_string()}")

        # # compute latency is the smallest nonzero latency of the df
        # compute_latency = self.latency_df_of_current_timestamps[self.latency_df_of_current_timestamps['latency'] > 0]['latency'].min()
        self.logger.info(f"{self.latency_df_of_current_timestamps.groupby('machine')['latency'].mean()}")

        # compute latency is the average latency of the df of the column that has smallest nonzero average latency
        compute_latency = self.latency_df_of_current_timestamps.groupby('machine')['latency'].mean().min()
        self.logger.info(f"compute latency {compute_latency}")

        # end to end latency is the largest latency of the df
        # end_to_end_latency = self.latency_df_of_current_timestamps['latency'].max()
        # compute latency is the average latency of the df of the column that has largest average latency
        end_to_end_latency = self.latency_df_of_current_timestamps.groupby('machine')['latency'].mean().max()
        self.logger.info(f"end to end latency {end_to_end_latency}")

        network_latency =  end_to_end_latency - compute_latency
        self.logger.info(f"network latency {network_latency}")

        need_better_compute = compute_latency > self.compute_latency_bound
        need_better_network = network_latency > self.network_latency_bound
        self.logger.info(f"need better compute {need_better_compute}, need better network {need_better_network}")
        return need_better_compute, need_better_network
    
    def _get_machine_with_best_compute(self):
        # get the best machine based on current spec collected 
        # param = optimize_compute vs optimize 
        # if machine has gpu 
        # else cpu_core >= cpu_core:
        # else cpu_frequency 
        for machine in self.machine_dict:
            if self.machine_dict[machine].gpu_usage:
                return machine

    def _get_machine_with_best_network(self):
        # use ping to get the latency
        latency_dict = dict()
        for machine in self.machine_dict:
            network_info = ping_host(self.machine_dict[machine].ip_addr.data)
            self.logger.info(f"latency to {machine} is {network_info}")
            latency_dict[machine] = network_info["avg_latency"]
            # self.logger.info(f"latency to {machine} is {latency_dict[machine]}")
        return min(latency_dict, key=latency_dict.get)

    def _switch_to_machine(self, machine):
        if machine == self.identity:
            # no need to switch
            return
        self.logger.info(f"switching to machine {machine}")
def main():
    rclpy.init()
    node = SGC_Analyzer()
    rclpy.spin(node)

if __name__ == '__main__':
    main()
