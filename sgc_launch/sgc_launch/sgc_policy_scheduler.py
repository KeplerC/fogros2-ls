
import subprocess, os, yaml
import requests
import pprint
import socket 
import time 
import rclpy
import rclpy.node
from sgc_msgs.msg import Profile
from sgc_msgs.srv import SgcAssignment
from sgc_msgs.srv import SgcProfiling
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
        self.current_active_service_machine = self._get_service_machine_name_from_state_assignment()

        # subscribe to the profile topic from other machines (if any)
        self.status_topic = self.create_subscription(
            Profile,
            'fogros_sgc/profile',
            self.profile_topic_callback,
            10)

        self.optimize_profiling_server = self.create_service(SgcProfiling, 'sgc_profiling_optimizer', self.sgc_profiling_optimizer_callback)

        # assignment service client to sgc_node
        self.assignment_service_client = self.create_client(SgcAssignment, 'sgc_assignment_service')

        self.max_latency_bound = float(self.config["time_bound"]["max_latency"]) if "max_latency" in self.config["time_bound"] else -1
        self.mean_latency_bound = float(self.config["time_bound"]["mean_latency"]) if "mean_latency" in self.config["time_bound"] else -1
        self.median_latency_bound = float(self.config["time_bound"]["median_latency"]) if "median_latency" in self.config["time_bound"] else -1
        self.min_latency_bound = float(self.config["time_bound"]["min_latency"]) if "min_latency" in self.config["time_bound"] else -1
        self.std_latency_bound = float(self.config["time_bound"]["std_latency"]) if "std_latency" in self.config["time_bound"] else -1

        self.is_doing_profiling = False  
        self.active_profiling_result = dict() # string to Profile
        self.max_num_waiting_profiles = 5 # profiles messages; if received 5 profile messages but still no latency, assume it is disconnected
        self.curr_num_waiting_profiles = 0 # profiles messages

    def sgc_profiling_optimizer_callback(self, request, response):
        self.is_doing_profiling = True
        self.active_profiling_result = dict()
        response.result.data = "start to do profiling"
        return response

    def profile_topic_callback(self, profile_update):
        self.logger.info(f"received profile update from {profile_update}")
        self.machine_profile_dict[profile_update.identity.data] = profile_update

        # TODO: we only monitor the state `robot`'s latency for now
        if profile_update.identity.data != self._get_robot_machine_name_from_state_assignment():
            return  

        if not self.is_doing_profiling: # acutal runnning the application
            if profile_update.median_latency != -1:
                is_fulfill_bound = self._check_latency_bound(profile_update)
                if not is_fulfill_bound:
                    self._switch_to_machine(self._get_machine_with_better_compute())
            else:
                self.logger.info(f"median latency is -1, no latency data is collected this window")
                self.curr_num_waiting_profiles +=1 
                if self.curr_num_waiting_profiles >= self.max_num_waiting_profiles:
                    self.logger.error(f"no latency data is collected for {self.max_num_waiting_profiles} times, assume it is disconnected")
                    self._switch_to_machine(self._get_machine_with_better_compute())
                    self.curr_num_waiting_profiles = 0
        else: # doing profiling
            if profile_update.median_latency != -1:
                self.active_profiling_result[profile_update.identity.data] = profile_update
                unprofiled_machines = self._get_list_of_machine_not_profiled()
                if len(unprofiled_machines) == 0: # profiling is done
                    self.is_doing_profiling = False
                    self._switch_to_machine(self._get_machine_with_better_compute())
                    self.logger.info(f"profiling is done, switch to {self.current_active_service_machine}")
                else:
                    self._switch_to_machine(unprofiled_machines[0])
            else:
                self.logger.info(f"median latency is -1, no latency data is collected this window")
                self.curr_num_waiting_profiles +=1 
                if self.curr_num_waiting_profiles >= self.max_num_waiting_profiles:
                    self.logger.error(f"no latency data is collected for {self.max_num_waiting_profiles} times, assume it is disconnected")
                    self.curr_num_waiting_profiles = 0
                    

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


    # check if the latency is within the bound using heuristics
    def _check_latency_bound(self, profile):
        fulfill_bound = True
        # max 
        if self.max_latency_bound != -1 and profile.max_latency > self.max_latency_bound:
            self.logger.info(f"max latency {profile.max_latency} is larger than the bound {self.max_latency_bound}")
            fulfill_bound = False
        # mean
        if self.mean_latency_bound != -1 and profile.mean_latency > self.mean_latency_bound:
            self.logger.info(f"mean latency {profile.mean_latency} is larger than the bound {self.mean_latency_bound}")
            fulfill_bound = False
        # median
        if self.median_latency_bound != -1 and profile.median_latency > self.median_latency_bound:
            self.logger.info(f"median latency {profile.median_latency} is larger than the bound {self.median_latency_bound}")
            fulfill_bound = False
        # min
        if self.min_latency_bound != -1 and profile.min_latency < self.min_latency_bound:
            self.logger.info(f"min latency {profile.min_latency} is smaller than the bound {self.min_latency_bound}")
            # TODO: here need to switch to a worse compute machine
            fulfill_bound = False
        # std
        if self.std_latency_bound != -1 and profile.std_latency > self.std_latency_bound:
            self.logger.info(f"std latency {profile.std_latency} is larger than the bound {self.std_latency_bound}")
            fulfill_bound = False
        return fulfill_bound 

    def _get_list_of_machine_not_profiled(self):
        all_machines = self.assignment_dict.keys()
        profiled_machines = self.active_profiling_result.keys()
        self.logger.info(f"[Profile status] All machines {all_machines}, profiled machines {profiled_machines}, choosing from {list(set(all_machines) - set(profiled_machines))}")
        return list(set(all_machines) - set(profiled_machines))


    def get_a_machine_with_working_profile(self):
        all_passed_machines = self._get_list_of_machine_with_working_profile()
        if len(all_passed_machines) == 0:
            self.logger.error(f"no machine is passed the latency bound, choosing the one with better compute")
            all_passed_machines = self.assignment_dict.keys()
            # TODO: actually implement the function
            return self._get_machine_with_better_compute()
        elif len(all_passed_machines) > 1:
            self.logger.info(f"more than one machine is passed the latency bound, choosing the one with better compute")
            # TODO: need a function that has a list
            return self._get_machine_with_better_compute()
        else:
            return all_passed_machines[0]   

    def _get_list_of_machine_with_working_profile(self):
        # use ping to get the latency
        passed_machines = []
        for machine in self.active_profiling_result:
            self._check_latency_bound(self.active_profiling_result[machine])
            # self.logger.info(f"latency to {machine} is {latency_dict[machine]}")
        return passed_machines


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
        
        if machine_new == self._get_service_machine_name_from_state_assignment():
            self.logger.warn(f"{machine_new} is the same as the current machine, not switching")
            return
        
        request = SgcAssignment.Request()
        request.machine.data = self._get_service_machine_name_from_state_assignment()
        request.state.data = "standby" 
        self.assignment_dict[request.machine.data] = "standby" 
        _ = self.assignment_service_client.call_async(request)
        
        request.machine.data = machine_new
        request.state.data = "service" 
        self.assignment_dict[request.machine.data] = "service" 
        _ = self.assignment_service_client.call_async(request)

        self.curr_num_waiting_profiles = 0

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
