
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
import random 

TOTAL_THROW_AWAY_PROFILES = 2

'''
[] <- collection of benchmarking results 

latency_callback_function(): 
if latency does not fulfill time bound: 
		get_a_machine_with_better_profile()
if network disconnection detected:
		remove the currently connected service from benchmark result, 
		get_a_machine_with_better_profile()



get_a_machine_with_better_profile():
		pass_bound_checked_machine <- check all benchmarking result see which one fulfill time bound
		connected_machine <- machines that are connected, may not fulfill timebound
		
		if no connected machine: 
				rerun the benchmark
		if pass_bound_checked_machine exists:
				choose random one from list
		else
				randomly choose one from connected_machine
'''
class SGC_Policy_Scheduler(rclpy.node.Node):
    def __init__(self):
        super().__init__('sgc_policy_scheduler')

        self.declare_parameter("max_num_waiting_profiles", 5)
        self.max_num_waiting_profiles = self.get_parameter("max_num_waiting_profiles").value

        self.declare_parameter("automatic_switching", True)
        self.automatic_switching = self.get_parameter("automatic_switching").value


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
        self.ls_active_profile_server = self.create_service(SgcProfiling, 'sgc_profiling_ls', self.ls_active_profile_callback)
        self.get_machine_with_better_profile_server = self.create_service(SgcProfiling, 'sgc_profiling_get_best', self.get_machine_with_better_profile_callback)


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

        self.has_skipped_the_first_x_profile = 0

        # self._do_profiling()

    def get_machine_with_better_profile_callback(self, request, response):
        response.result.data = self.get_a_machine_with_better_profile()
        return response
    
    def ls_active_profile_callback(self, request, response):
        response.result.data = self.dump_scheduler_state()
        return response

    def sgc_profiling_optimizer_callback(self, request, response):
        if self.is_doing_profiling:
            self.logger.info(f"already doing profiling, ignore the request")
            response.result.data = self.dump_scheduler_state()
            return response
        self._do_profiling()
        response.result.data = self.dump_scheduler_state()
        # this is just in case the scheduler is not aligned with the sgc_node state
        return response
    
    def _do_profiling(self):
        if self.is_doing_profiling:
            return 
        self.is_doing_profiling = True
        self.active_profiling_result = dict()
        self._switch_to_machine(self._get_service_machine_name_from_state_assignment(), force = True)

    def dump_scheduler_state(self):
        s = ""
        s += f"current active service machine: {self.current_active_service_machine};"
        s += f"current active robot machine: {self._get_robot_machine_name_from_state_assignment()};"
        s += f"current active service machine: {self._get_service_machine_name_from_state_assignment()};"
        s += f"current standby machines: {self._get_standby_machine_list_from_state_assignment()};"
        s += f"is doing profiling: {self.is_doing_profiling};"
        s += f"current profiled results: {self.active_profiling_result}\n"
        self.logger.info(s)
        return s
    
    def profile_topic_callback(self, profile_update):
        self.machine_profile_dict[profile_update.identity.data] = profile_update

        # TODO: we only monitor the state `robot`'s latency for now
        if profile_update.identity.data != self._get_robot_machine_name_from_state_assignment():
            return  
        if not self.is_doing_profiling: # acutal runnning the application
            self.logger.info(f"[{self._get_service_machine_name_from_state_assignment()}]received an update from {profile_update}")
            if profile_update.median_latency != -1:
                is_fulfill_bound = self._check_latency_bound(profile_update)
                if not is_fulfill_bound:
                    self.logger.error(f"latency {profile_update.median_latency} does not fulfill the bound!!!!!")
                    if self.automatic_switching:
                        self._switch_to_machine(self.get_a_machine_with_better_profile())
                    else:
                        self.logger.error(f"automatic_switching is disabled, not switching")
            else:
                self.logger.info(f"median latency is -1, no latency data is collected this window")
                self.curr_num_waiting_profiles +=1 
                if self.curr_num_waiting_profiles >= self.max_num_waiting_profiles:
                    self.logger.error(f"no latency data is collected for {self.max_num_waiting_profiles} times, assume {self._get_service_machine_name_from_state_assignment()} is disconnected")
                    # because the service is disconnected, we remove it from the already-profiled list 
                    # if all the machines are disconnected, we will just rerun the profiling algorithm
                    if self._get_service_machine_name_from_state_assignment() in self.active_profiling_result:
                        self.logger.error(f"remove {self._get_service_machine_name_from_state_assignment()} from the already-profiled list")
                        del self.active_profiling_result[self._get_service_machine_name_from_state_assignment()]
                    self._switch_to_machine(self.get_a_machine_with_better_profile())
                    self.curr_num_waiting_profiles = 0
        else: # doing profiling
            self.logger.info(f"[profile-{self._get_service_machine_name_from_state_assignment()}]received an update from {profile_update}")
            if profile_update.median_latency != -1 or self.curr_num_waiting_profiles >= self.max_num_waiting_profiles:
                if self.has_skipped_the_first_x_profile < TOTAL_THROW_AWAY_PROFILES:
                    self.logger.info(f"skipping the first {TOTAL_THROW_AWAY_PROFILES} profiles, this is {self.has_skipped_the_first_x_profile}")
                    self.has_skipped_the_first_x_profile += 1
                    return
                self.active_profiling_result[self._get_service_machine_name_from_state_assignment()] = profile_update
                unprofiled_machines = self._get_list_of_machine_not_profiled()
                if self.curr_num_waiting_profiles >= self.max_num_waiting_profiles:
                    self.logger.error(f"no latency data is collected for {self.max_num_waiting_profiles} times, assume {self._get_service_machine_name_from_state_assignment()} is disconnected")
                if len(unprofiled_machines) == 0: # profiling is done
                    self.is_doing_profiling = False
                    self.logger.warn(f"profiling is done, {self.active_profiling_result}, switch to {self.current_active_service_machine}")
                    self._switch_to_machine(self.get_a_machine_with_better_profile())
                else:
                    self._switch_to_machine(random.choice(unprofiled_machines))
            else:
                self.logger.info(f"median latency is -1, no latency data is collected this window")
                self.curr_num_waiting_profiles +=1 


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
        # self.logger.info(f"checking profile {profile}")
        # max 
        if self.max_latency_bound != -1 and profile.max_latency > self.max_latency_bound:
            self.logger.info(f"max latency {profile.max_latency} is larger than the bound {self.max_latency_bound}")
            return False
        # mean
        if self.mean_latency_bound != -1 and profile.mean_latency > self.mean_latency_bound:
            self.logger.info(f"mean latency {profile.mean_latency} is larger than the bound {self.mean_latency_bound}")
            return False
        # median
        if self.median_latency_bound != -1 and profile.median_latency > self.median_latency_bound:
            self.logger.info(f"median latency {profile.median_latency} is larger than the bound {self.median_latency_bound}")
            return False
        # min
        if self.min_latency_bound != -1 and profile.min_latency < self.min_latency_bound:
            self.logger.info(f"min latency {profile.min_latency} is smaller than the bound {self.min_latency_bound}")
            # TODO: here need to switch to a worse compute machine
            return False
        # std
        if self.std_latency_bound != -1 and profile.std_latency > self.std_latency_bound:
            self.logger.info(f"std latency {profile.std_latency} is larger than the bound {self.std_latency_bound}")
            return False
        return True 

    def _get_list_of_machine_not_profiled(self):
        all_machines = self.assignment_dict.keys()
        profiled_machines = list(self.active_profiling_result.keys()) + [self._get_robot_machine_name_from_state_assignment()]
        self.logger.info(f"[Profile status] All machines {all_machines}, profiled machines {profiled_machines}, yet from profile machine {list(set(all_machines) - set(profiled_machines))}")
        return list(set(all_machines) - set(profiled_machines))


    def get_a_machine_with_better_profile(self):
        all_passed_machines = []
        connected_machines = []
        for machine in self.active_profiling_result:
            result = self._check_latency_bound(self.active_profiling_result[machine])
            if result:
                all_passed_machines.append(machine)
            if self.active_profiling_result[machine].median_latency != -1:
                connected_machines.append(machine)

        if len(all_passed_machines) == 0:
            self.logger.error(f"no machine is passed the latency bound")
            if len(connected_machines) == 0:
                self.logger.error(f"no machine in profile is marked as connected, running profiling again")
                self._do_profiling()
                # since the profiling already switch to the desired service machine
                return self._get_service_machine_name_from_state_assignment()
            else:
                self.logger.error(f"some machines are connected, switch to some connected one")
                return random.choice(connected_machines)
        else:
            passed_machine = random.choice(all_passed_machines)  
            self.logger.info(f"machine {passed_machine} is passed the latency bound, switch to one of them")
            return passed_machine



    def _get_machine_standby(self):
        standby_machine = random.choice(self._get_standby_machine_list_from_state_assignment())
        self.logger.info(f"switch to {standby_machine} because it is the only standby machine")
        return standby_machine
            
    def _get_machine_with_better_spect(self):
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
        pass 

    def _get_machine_with_best_network(self):
        # use ping to get the latency
        latency_dict = dict()
        for machine in self.machine_profile_dict:
            network_info = ping_host(self.machine_profile_dict[machine].ip_addr.data)
            self.logger.info(f"latency to {machine} is {network_info}")
            latency_dict[machine] = network_info["avg_latency"]
            # self.logger.info(f"latency to {machine} is {latency_dict[machine]}")
        return min(latency_dict, key=latency_dict.get)

    def _switch_to_machine(self, machine_new, force = False):
        
        self.has_skipped_the_first_x_profile = 0
        previous_service_machine = self._get_service_machine_name_from_state_assignment()
        if not force and machine_new == previous_service_machine:
            self.logger.warn(f"{machine_new} is the same as the current machine, not switching")
            return
        
        
        request = SgcAssignment.Request()        


        request.machine.data = previous_service_machine
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
