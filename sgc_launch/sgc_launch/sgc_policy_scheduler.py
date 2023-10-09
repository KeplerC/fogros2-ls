
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
import threading

TOTAL_THROW_AWAY_PROFILES = 6
MAX_ALLOWED_DISCONNCTED_TIME = 10 # ms


class SGC_Service:
    def __init__(self, identity, logger):
        self.identity = identity
        self.last_profile = None 
        self.last_connected_time = None
        self.last_switched_time = time.time()

        # not used for detecting timeout, but for skipping the first few profiles after the machine is connected
        self.num_profiles_after_connected = 0
        self.logger = logger
    
    def update(self, profile_update, is_profiling = False):
        if profile_update.median_latency != -1:
            self.last_connected_time = time.time()
            self.num_profiles_after_connected += 1         
        self.last_profile = profile_update
            
    def check_timeout(self, is_profiling = False):
        self.logger.info(f"[{self.identity}] checking timeout")
        
        # either latency is -1 or the machine is never connected
        # if self.last_connected_time is None:
        #     self.logger.info(f"no profile received yet, timeout")
        #     return True 

        if self.last_connected_time is None:
            # not connected; but has not been enough time since the last switch
            if time.time() - self.last_switched_time < MAX_ALLOWED_DISCONNCTED_TIME:
                self.logger.info(f"[{self.identity}] not connected, but has not been enough time since the last switch")
                return False
            else:
                self.logger.warn(f"[{self.identity}] not connected, timeout since the last switch")
                return True
        else:
            # connected but last profile is too long ago
            self.logger.info(f"[{self.identity}] last connected time is {self.last_connected_time}, current time is {time.time()}, diff is {time.time() - self.last_connected_time}")
            return time.time() - self.last_connected_time > MAX_ALLOWED_DISCONNCTED_TIME
    
    def has_run_out_of_skipped_profiles(self):
        return self.num_profiles_after_connected >= TOTAL_THROW_AWAY_PROFILES

    # reset when switched, etc.
    def reset(self):
        self.last_connected_time = None
        self.last_switched_time = time.time()
        self.num_profiles_after_connected = 0

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

        self.assignment_dict = dict() # identity_name to state_name
        self.service_dict = dict() # identity_name to SGC_Service

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
        self.parallel_profiling_server = self.create_service(SgcProfiling, 'sgc_parallel_profiling', self.sgc_parallel_profiling_callback)
        self.get_best_parallel_profiling_server = self.create_service(SgcProfiling, 'sgc_parallel_profiling_get_best', self.sgc_parallel_profiling_best_callback)

        # assignment service client to sgc_node
        self.assignment_service_client = self.create_client(SgcAssignment, 'sgc_assignment_service')

        self.max_latency_bound = float(self.config["time_bound"]["max_latency"]) if "max_latency" in self.config["time_bound"] else -1
        self.mean_latency_bound = float(self.config["time_bound"]["mean_latency"]) if "mean_latency" in self.config["time_bound"] else -1
        self.median_latency_bound = float(self.config["time_bound"]["median_latency"]) if "median_latency" in self.config["time_bound"] else -1
        self.min_latency_bound = float(self.config["time_bound"]["min_latency"]) if "min_latency" in self.config["time_bound"] else -1
        self.std_latency_bound = float(self.config["time_bound"]["std_latency"]) if "std_latency" in self.config["time_bound"] else -1
        self.smart_bound = float(self.config["time_bound"]["smart_latency"]) if "smart_latency" in self.config["time_bound"] else -1
        
        self.is_doing_profiling = False  
        self.is_doing_parallel_profiling = False
        self.t0 = 0
        self.is_parallel_profiling_ready = False
        self.active_profiling_result = dict() # string to Profile
        self.active_profiling_disconnected_list = []
        # self.max_num_waiting_profiles = 5 # profiles messages; if received 5 profile messages but still no latency, assume it is disconnected
        # self.curr_num_waiting_profiles = 0 # profiles messages


        
        # self.time_dict_of_last_profile = dict() # string to time.time()
        # self.num_profiles_after_connected = dict() 
        # self._do_profiling()

    def get_machine_with_better_profile_callback(self, request, response):
        self._switch_to_machine(self.get_a_machine_with_better_profile())
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
    
    def sgc_parallel_profiling_callback(self, request, response):
        if self.is_doing_parallel_profiling:
            self.logger.info(f"already doing profiling, ignore the request")
            response.result.data = self.dump_scheduler_state()
            return response
        
        self._do_parallel_profiling()
        response.result.data = self.dump_scheduler_state()
        # this is just in case the scheduler is not aligned with the sgc_node state
        return response
    
    def _do_profiling(self):
        if self.is_doing_profiling or self.is_doing_parallel_profiling:
            return 
        self.is_doing_profiling = True
        self.active_profiling_result = dict()
        self.active_profiling_disconnected_list = []
        # self._switch_to_machine(self._get_service_machine_name_from_state_assignment(), force = True)
        self._switch_to_next_unprofiled_machine()
        
    ###
    def _do_parallel_profiling(self):
        if self.is_doing_profiling or self.is_doing_parallel_profiling:
            return
        self.current_active_service_machine = self._get_service_machine_name_from_state_assignment()
        self.is_doing_parallel_profiling = True
        self.is_parallel_profiling_ready = False
        self.active_profiling_result = dict()
        
        self._switch_to_all()
        
        self.t0 = time.time()
        return
         
    def sgc_parallel_profiling_best_callback(self, request, response):
        response.result.data = ""
        if self.is_parallel_profiling_ready and self.is_doing_parallel_profiling:
            self.is_doing_parallel_profiling = False
            machine_with_better_profile = self.get_a_machine_with_better_profile()
            if machine_with_better_profile is not None:
                self._switch_off_all_but_one(machine_with_better_profile)
                self.logger.warn(f"PARALLEL PROFILING CHOSE: {machine_with_better_profile}")
            else:
                machine_with_better_profile = self.current_active_service_machine
                self._switch_off_all_but_one(machine_with_better_profile)
                
            response.result.data = machine_with_better_profile
        return response
    ###
        
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
        if self.is_doing_parallel_profiling:
            self.service_dict[profile_update.identity.data].update(profile_update, self.is_doing_parallel_profiling)
            self.logger.warn(f"received a profile from {profile_update.identity.data}")
            # if self.service_dict[current_service_machine].check_timeout(self.is_doing_profiling):
            #     return
            
            if self.service_dict[profile_update.identity.data].has_run_out_of_skipped_profiles():
                self.logger.warn(f"received a good, after trash, profile from {profile_update.identity.data}")
                self._handle_profile_message_at_profiling(profile_update)
                
                num_servers = len(self._get_nonrobot_machine_list_from_state_assignment())
                
                if len(list(self.active_profiling_result.keys())) == num_servers or time.time() - self.t0 > 0.05:
                    self.is_parallel_profiling_ready = True
            return
        
        current_service_machine = self._get_service_machine_name_from_state_assignment()
        if profile_update.identity.data != current_service_machine:
            self.logger.info(f"received a profile from {profile_update.identity.data}, but the current active service machine is {current_service_machine}")
            if self.service_dict[current_service_machine].check_timeout(self.is_doing_profiling):
                self._handle_timeout()
            return
        
        self.service_dict[profile_update.identity.data].update(profile_update, self.is_doing_profiling)
        if self.service_dict[current_service_machine].check_timeout(self.is_doing_profiling):
            self._handle_timeout()
            return

        self.logger.info(f"received a profile from {profile_update.identity.data}, and the current active service machine is {current_service_machine}")

        if self.is_doing_profiling:
            if self.service_dict[current_service_machine].has_run_out_of_skipped_profiles():
                self.logger.info(f"received a profile from {profile_update.identity.data}, and the current active service machine is {current_service_machine}, and the scheduler is doing profiling")
                self._handle_profile_message_at_profiling(profile_update)
        else:
            self._handle_profile_message_at_running(profile_update)

    def _handle_timeout(self):
        if self.is_doing_profiling:
            self.logger.error(f"timeout detected at profiling, switch to the next unprofiled machine")
            self.active_profiling_disconnected_list.append(self._get_service_machine_name_from_state_assignment())
            self._switch_to_next_unprofiled_machine()
        else:
            self.logger.error(f"timeout detected at running, switch to the next machine with better profile")
            if self._get_service_machine_name_from_state_assignment() in self.active_profiling_result:
                # because the service is disconnected, we remove it from the already-profiled list 
                # if all the machines are disconnected, we will just rerun the profiling algorithm
                self.logger.error(f"remove {self._get_service_machine_name_from_state_assignment()} from the already-profiled list")
                del self.active_profiling_result[self._get_service_machine_name_from_state_assignment()]
            better_profile_machine = self.get_a_machine_with_better_profile()
            if better_profile_machine is not None:
                self._switch_to_machine(better_profile_machine)

    def _handle_profile_message_at_profiling(self, profile_update):
        if self.is_doing_parallel_profiling:
            self.logger.info(f"[profile-{profile_update.identity.data}] received an update from {profile_update}")
            self.active_profiling_result[profile_update.identity.data] = profile_update
            
            return
        self.logger.info(f"[profile-{self._get_service_machine_name_from_state_assignment()}] received an update from {profile_update}")
        self.active_profiling_result[self._get_service_machine_name_from_state_assignment()] = profile_update
        self._switch_to_next_unprofiled_machine()

    def _handle_profile_message_at_running(self, profile_update):
        self.logger.info(f"[{self._get_service_machine_name_from_state_assignment()}]received an update from {profile_update}")

        if not self._check_latency_bound(profile_update):
            self.logger.error(f"latency {profile_update.median_latency} does not fulfill the bound!!!!!")
            if self.automatic_switching:
                better_profile_machine = self.get_a_machine_with_better_profile(exclude_list=[self._get_service_machine_name_from_state_assignment()])
                if better_profile_machine is not None:
                    self.logger.info(f"switching to {better_profile_machine} because it has better profile")
                    self._switch_to_machine(better_profile_machine)
            else:
                self.logger.error(f"automatic_switching is disabled, not switching") 

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
        if profile.median_latency == -1:
            self.logger.info(f"median latency is -1, no latency data is collected this window")
            return False
        # smart
        if self.smart_bound != -1 and profile.max_kmeans_latency > self.smart_bound:
            self.logger.info(f"jenks latency {profile.max_kmeans_latency} is larger than the bound {self.smart_bound}")
            return False
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
        profiled_machines = list(self.active_profiling_result.keys()) + [self._get_robot_machine_name_from_state_assignment()] + self.active_profiling_disconnected_list
        self.logger.info(f"[Profile status] All machines {all_machines}, profiled machines {profiled_machines}, yet from profile machine {list(set(all_machines) - set(profiled_machines))}")
        return list(set(all_machines) - set(profiled_machines))


    def get_a_machine_with_better_profile(self, exclude_list = []):
        all_passed_machines = []
        connected_machines = []
        for machine in self.active_profiling_result:
            if machine in exclude_list:
                continue
            result = self._check_latency_bound(self.active_profiling_result[machine])
            if result:
                all_passed_machines.append(machine)
            if self.active_profiling_result[machine].median_latency != -1:
                connected_machines.append(machine)

        if len(all_passed_machines) == 0:
            self.logger.error(f"no machine is passed the latency bound")
            if len(connected_machines) == 0:
                self.logger.error(f"no machine in profile is marked as connected, do nothing")
                # self.logger.error(f"no machine in profile is marked as connected, running profiling again")
                # self._do_profiling()
                # since the profiling already switch to the desired service machine
                return None
            else:
                self.logger.error(f"some machines are connected, switch to some connected one")
                sorted_machines = sorted(connected_machines, key=lambda x: self.active_profiling_result[x].max_latency)
                return sorted_machines[0] #random.choice(connected_machines)
        else:
            sorted_machines = sorted(all_passed_machines, key=lambda x: self.active_profiling_result[x].max_latency)
            passed_machine = sorted_machines[0] #random.choice(all_passed_machines)  
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
        for machine in self.machine_profile_dict.keys():
            network_info = ping_host(self.service_dict[machine].last_profile.ip_addr.data)
            self.logger.info(f"latency to {machine} is {network_info}")
            latency_dict[machine] = network_info["avg_latency"]
            # self.logger.info(f"latency to {machine} is {latency_dict[machine]}")
        return min(latency_dict, key=latency_dict.get)

    def _switch_to_next_unprofiled_machine(self):
        unprofiled_machines = self._get_list_of_machine_not_profiled()
        self.logger.info(f"unprofiled machines are {unprofiled_machines}")
        if len(unprofiled_machines) == 0:
            self.logger.info(f"unprofiled machines are {unprofiled_machines}")
            self.logger.info(f"all machines are profiled, switch to the best one")
            self.is_doing_profiling = False
            machine_with_better_profile = self.get_a_machine_with_better_profile()
            if machine_with_better_profile:
                self._switch_to_machine(machine_with_better_profile)
        else:
            # switch to a random one other than the current service machine
            unprofiled_machines_other_than_current_service = [x for x in unprofiled_machines if x != self._get_service_machine_name_from_state_assignment()]
            if len(unprofiled_machines_other_than_current_service) == 0:
                self._switch_to_machine(self._get_service_machine_name_from_state_assignment())
            else:
                self._switch_to_machine(random.choice(unprofiled_machines_other_than_current_service))


    def _switch_to_machine(self, machine_new, force = False):
        previous_service_machine = self._get_service_machine_name_from_state_assignment()
        if not force and machine_new == previous_service_machine:
            self.logger.warn(f"{machine_new} is the same as the current machine, not switching")
            return
        
        self.service_dict[machine_new].reset()
        self.service_dict[previous_service_machine].reset()
        self.logger.info(f"switching from {previous_service_machine} to {machine_new}")

        request = SgcAssignment.Request()        

        request.machine.data = previous_service_machine
        request.state.data = "standby" 
        self.assignment_dict[request.machine.data] = "standby" 
        _ = self.assignment_service_client.call_async(request)
        
        request.machine.data = machine_new
        request.state.data = "service" 
        self.assignment_dict[request.machine.data] = "service" 
        _ = self.assignment_service_client.call_async(request)
        
    def _switch_to_all(self, force = False):
        previous_service_machine = self._get_service_machine_name_from_state_assignment()
        for machine in self._get_standby_machine_list_from_state_assignment():
            if not force and machine == previous_service_machine:
                self.logger.warn(f"{machine} is the same as the current machine, not switching")
                continue
            
            request = SgcAssignment.Request()        

            request.machine.data = machine
            request.state.data = "service" 
            self.assignment_dict[request.machine.data] = "service" 
            _ = self.assignment_service_client.call_async(request)
            
    def _switch_off_all_but_one(self, machine_new):
        # I think standbys must be called first or else bug, like in switch_to_machine()
        request = SgcAssignment.Request()
        for machine in self._get_nonrobot_machine_list_from_state_assignment():
            if machine_new != machine:
                request.machine.data = machine
                request.state.data = "standby" 
                self.assignment_dict[request.machine.data] = "standby" 
                _ = self.assignment_service_client.call_async(request) 
            
            
        self.logger.warn(f"{machine_new} is the best")
        request.machine.data = machine_new
        request.state.data = "service" 
        self.assignment_dict[request.machine.data] = "service" 
        _ = self.assignment_service_client.call_async(request)



    def _load_initial_state_assignment(self):
        for identity_name in self.config["assignment"]:
            state_name = self.config["assignment"][identity_name]
            self.assignment_dict[identity_name] = state_name
            self.service_dict[identity_name] = SGC_Service(identity_name, self.logger)
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
    
    def _get_nonrobot_machine_list_from_state_assignment(self):
        standby_machine_list = []
        for identity_name in self.assignment_dict:
            if self.assignment_dict[identity_name] != "robot":
                standby_machine_list.append(identity_name)
        return standby_machine_list
    
def main():
    rclpy.init()
    node = SGC_Policy_Scheduler()
    rclpy.spin(node)

if __name__ == '__main__':
    main()
