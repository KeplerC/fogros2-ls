
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

class SGC_Policy_Scheduler(rclpy.node.Node):
    def __init__(self):
        super().__init__('sgc_policy_scheduler')
        self.logger = self.get_logger()

        self.load_config_file()

        self.machine_dict = dict()

        # subscribe to the profile topic from other machines (if any)
        self.status_topic = self.create_subscription(
            Profile,
            'fogros_sgc/profile',
            self.profile_topic_callback,
            10)

        # assignment service client to sgc_node
        self.assignment_service_client = self.create_client(SgcAssignment, 'sgc_assignment_service')

    def load_config_file(self):
        self.declare_parameter("config_path", "")
        self.config_path = self.get_parameter("config_path").value

        self.declare_parameter("config_file_name", "offload_detection.yaml") # ROS2 parameter is strongly typed
        self.config_file_name = self.get_parameter("config_file_name").value

        current_env = os.environ.copy()
        current_env["PATH"] = f"/usr/sbin:/sbin:{current_env['PATH']}"
        ws_path = current_env["COLCON_PREFIX_PATH"]
        config_path = f"{ws_path}/sgc_launch/share/sgc_launch/configs" if not config_path else config_path
        config_yaml_file_path = f"{config_path}/{self.config_file_name}"
        with open(config_yaml_file_path, "r") as f:
            self.config = yaml.safe_load(f)
            self.logger.info(f"The config file is \n {pprint.pformat(self.config)}")

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
    
    def _get_machine_with_better_compute(self):
        # get the best machine based on current spec collected 
        # param = optimize_compute vs optimize 
        # if machine has gpu 
        # else cpu_core >= cpu_core:
        # else cpu_frequency 
        # for machine in self.machine_dict:
        #     if self.machine_dict[machine].has_gpu and not self.has_gpu:
        #         return machine
        #     if self.machine_dict[machine].num_cpu_core >= self.profile.num_cpu_core:
        #         return machine
        #     if self.machine_dict[machine].cpu_frequency >= self.profile.cpu_frequency:
        #         return machine
        # return "machine_cloud" #TODO: currently it's hardcoded placeholder
        self.logger.error("not implemented yet; need to switch to a compute")
        pass
    
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
        
        request = SgcAssignment.Request()
        request.machine.data = "machine_local"
        request.state.data = "standby" # TODO: currently it's hardcoded
        _ = self.assignment_service_client.call_async(request)


        
        request.machine.data = "machine_cloud"
        request.state.data = "service" # TODO: currently it's hardcoded
        _ = self.assignment_service_client.call_async(request)

    def get_initial_state_assignment(self):
        for identity_name in self.config["assignment"]:
            state_name = self.config["assignment"][identity_name]
            if state_name not in self.state_dict:
                self.logger.warn(f"State {state_name} not defined. Not added!")
                continue 
            self.assignment_dict[identity_name] = state_name
        return self.assignment_dict
    
def main():
    rclpy.init()
    node = SGC_Policy_Scheduler()
    rclpy.spin(node)

if __name__ == '__main__':
    main()
