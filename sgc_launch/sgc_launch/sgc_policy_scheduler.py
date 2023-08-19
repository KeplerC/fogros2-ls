
import subprocess, os, yaml
import requests
import pprint
import socket 
import time 
import rclpy
import rclpy.node
from sgc_msgs.msg import Profile
from sgc_msgs.srv import SgcAssignment
from sgc_msgs.srv import SgcProfling
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

        self.machine_profile_dict = dict()
        self.assignment_dict = dict()

        self._load_config_file()
        self._load_initial_state_assignment()

        # subscribe to the profile topic from other machines (if any)
        self.status_topic = self.create_subscription(
            Profile,
            'fogros_sgc/profile',
            self.profile_topic_callback,
            10)

        self.optimize_profiling_server = self.create_service(SgcProfling, 'sgc_profiling_optimizer', self.sgc_profiling_optimizer_callback)

        # assignment service client to sgc_node
        self.assignment_service_client = self.create_client(SgcAssignment, 'sgc_assignment_service')

        self.max_latency_bound = float(self.config["time_bound"]["max_latency"]) if "max_latency" in self.config["time_bound"] else -1
        self.mean_latency_bound = float(self.config["time_bound"]["mean_latency"]) if "mean_latency" in self.config["time_bound"] else -1
        self.median_latency_bound = float(self.config["time_bound"]["median_latency"]) if "median_latency" in self.config["time_bound"] else -1
        self.min_latency_bound = float(self.config["time_bound"]["min_latency"]) if "min_latency" in self.config["time_bound"] else -1
        self.std_latency_bound = float(self.config["time_bound"]["std_latency"]) if "std_latency" in self.config["time_bound"] else -1

    def sgc_profiling_optimizer_callback(self, request, response):
        self._optimize_profiling()
        response.result.data = "success"
        return response
    
    def _optimize_profiling(self):
        pass

    def _load_config_file(self):
        self.declare_parameter("config_path", "")
        self.config_path = self.get_parameter("config_path").value

        self.declare_parameter("config_file_name", "offload_detection.yaml") # ROS2 parameter is strongly typed
        self.config_file_name = self.get_parameter("config_file_name").value

        current_env = os.environ.copy()
        current_env["PATH"] = f"/usr/sbin:/sbin:{current_env['PATH']}"
        ws_path = current_env["COLCON_PREFIX_PATH"]
        config_path = f"{ws_path}/sgc_launch/share/sgc_launch/configs" if not self.config_path else self.config_path
        config_yaml_file_path = f"{config_path}/{self.config_file_name}"
        with open(config_yaml_file_path, "r") as f:
            self.config = yaml.safe_load(f)
            self.logger.info(f"The config file is \n {pprint.pformat(self.config)}")

    def profile_topic_callback(self, profile_update):
        self.logger.info(f"received profile update from {profile_update}")
        self.machine_profile_dict[profile_update.identity.data] = profile_update

        # we assume the robot runs the scheduler for now
        # self.logger.info(f"")
        if profile_update.identity.data == self._get_robot_machine_name_from_state_assignment():
            if profile_update.median_latency != 0:
                self._check_latency_bound(profile_update)
            else:
                self.logger.info(f"median latency is 0, no latency data is collected this window")
            
    # check if the latency is within the bound using heuristics
    def _check_latency_bound(self, profile):
        # max 
        if self.max_latency_bound != -1 and profile.max_latency > self.max_latency_bound:
            self.logger.info(f"max latency {profile.max_latency} is larger than the bound {self.max_latency_bound}")
            self._switch_to_machine(self._get_machine_with_better_compute())
        # mean
        if self.mean_latency_bound != -1 and profile.mean_latency > self.mean_latency_bound:
            self.logger.info(f"mean latency {profile.mean_latency} is larger than the bound {self.mean_latency_bound}")
            self._switch_to_machine(self._get_machine_with_better_compute())
        # median
        if self.median_latency_bound != -1 and profile.median_latency > self.median_latency_bound:
            self.logger.info(f"median latency {profile.median_latency} is larger than the bound {self.median_latency_bound}")
            self._switch_to_machine(self._get_machine_with_better_compute())
        # min
        if self.min_latency_bound != -1 and profile.min_latency < self.min_latency_bound:
            self.logger.info(f"min latency {profile.min_latency} is smaller than the bound {self.min_latency_bound}")
            # TODO: here need to switch to a worse compute machine
            self._switch_to_machine(self._get_machine_with_better_compute())
        # std
        if self.std_latency_bound != -1 and profile.std_latency > self.std_latency_bound:
            self.logger.info(f"std latency {profile.std_latency} is larger than the bound {self.std_latency_bound}")
            self._switch_to_machine(self._get_machine_with_better_compute())

    def _get_machine_with_better_compute(self):
        # get the best machine based on current spec collected 
        # param = optimize_compute vs optimize 
        # if machine has gpu 
        # else cpu_core >= cpu_core:
        # else cpu_frequency 
        # for machine in self.machine_profile_dict:
        #     if self.machine_profile_dict[machine].has_gpu and not self.has_gpu:
        #         return machine
        #     if self.machine_profile_dict[machine].num_cpu_core >= self.profile.num_cpu_core:
        #         return machine
        #     if self.machine_profile_dict[machine].cpu_frequency >= self.profile.cpu_frequency:
        #         return machine
        # return "machine_cloud" #TODO: currently it's hardcoded placeholder
        # current_machine = self._get_service_machine_name_from_state_assignment()
        standby_machines = self._get_standby_machine_list_from_state_assignment()
        if len(standby_machines) == 1:
            self.logger.info(f"switch to {standby_machines[0]} because it is the only standby machine")
            return standby_machines[0]
        for machine in standby_machines:
            # this is a new machine that has not been profiled yet
            if self.machine_profile_dict[machine].latency == 0:
                self.logger.info(f"switch to {machine} because it has not been profiled yet")
                return machine
            
    def _get_machine_with_best_network(self):
        # use ping to get the latency
        latency_dict = dict()
        for machine in self.machine_profile_dict:
            network_info = ping_host(self.machine_profile_dict[machine].ip_addr.data)
            self.logger.info(f"latency to {machine} is {network_info}")
            latency_dict[machine] = network_info["avg_latency"]
            # self.logger.info(f"latency to {machine} is {latency_dict[machine]}")
        return min(latency_dict, key=latency_dict.get)

    def _switch_to_machine(self, machine_new):
        
        request = SgcAssignment.Request()
        request.machine.data = self._get_service_machine_name_from_state_assignment()
        request.state.data = "standby" 
        self.assignment_dict[request.machine.data] = "standby" 
        _ = self.assignment_service_client.call_async(request)
        
        request.machine.data = machine_new
        request.state.data = "service" 
        self.assignment_dict[request.machine.data] = "service" 
        _ = self.assignment_service_client.call_async(request)

    def _load_initial_state_assignment(self):
        for identity_name in self.config["assignment"]:
            state_name = self.config["assignment"][identity_name]
            self.assignment_dict[identity_name] = state_name
        self.logger.info(f"initial assignment is loaded {self.assignment_dict}")
        return self.assignment_dict

    def _get_robot_machine_name_from_state_assignment(self):
        for identity_name in self.assignment_dict:
            if self.assignment_dict[identity_name] == "robot":
                return identity_name
        return None
    
    def _get_service_machine_name_from_state_assignment(self):
        for identity_name in self.assignment_dict:
            if self.assignment_dict[identity_name] == "service":
                return identity_name
        return None
    
    def _get_standby_machine_list_from_state_assignment(self):
        standby_machine_list = []
        for identity_name in self.assignment_dict:
            if self.assignment_dict[identity_name] == "standby":
                standby_machine_list.append(identity_name)
        return standby_machine_list
    
def main():
    rclpy.init()
    node = SGC_Policy_Scheduler()
    rclpy.spin(node)

if __name__ == '__main__':
    main()
