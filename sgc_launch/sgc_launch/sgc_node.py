

import subprocess, os, yaml
import requests
import pprint
from time import sleep 
import rclpy
import rclpy.node
from rcl_interfaces.msg import SetParametersResult
from sgc_msgs.srv import SgcAssignment
from .time_bound_analyzer import SGC_Analyzer

def send_request(
    api_op, 
    topic_action,
    topic_name,
    topic_type,
    machine_address, 
):
    ros_topic = {
        "api_op": api_op,
        "ros_op": topic_action,
        "crypto": "test_cert",
        "topic_name": topic_name,
        "topic_type": topic_type,
    }
    uri = f"http://{machine_address}/topic"
    # Create a new resource
    response = requests.post(uri, json = ros_topic)
    # print(f"topic {topic.name} with operation {api_op} request sent with response {response}")

class SGC_StateMachine: 
    def __init__(self, state_name, topic_dict, param_dict):
        self.state_name = state_name
        self.topics = topic_dict
        self.params = param_dict

    def __repr__(self):
        return str(self.__dict__)
    
class SGC_Swarm: 
    def __init__(self, yaml_config, 
                 whoami, logger,
                 sgc_address):
        # the identifers for the task and ROS instance
        self.task_identifier = None 
        self.instance_identifer = whoami 
        
        # default Berkeley's parameters 
        self.signaling_server_address = 'ws://3.18.194.127:8000'
        self.routing_information_base_address = '3.18.194.127:8002'
        self.sgc_address = sgc_address

        # topic dictionary: map topic to topic type 
        self.topic_dict = dict()

        # states: map state_name to SGC_StateMachine
        self.state_dict = dict()

        # assignment: map identifer to state_names 
        self.assignment_dict = dict()

        self.logger = logger
        
        self.load(yaml_config)

    def load(self, yaml_config):
        with open(yaml_config, "r") as f:
            config = yaml.safe_load(f)
            self.logger.info(f"The config file is \n {pprint.pformat(config)}")
        self._load_addresses(config)
        self._load_identifiers(config)
        self._load_topics(config)
        self._load_state_machine(config)
        
    '''
    apply assignment dictionary
    '''
    def apply_assignment(self, new_assignment_dict):
        # currently: just focus on its own machine 
        # TODO: propagate the applied assignment to other machines 
        if self.instance_identifer not in new_assignment_dict:
            self.logger.warn(f"[Warn] the assignment dict {new_assignment_dict} doesn't have the identifier {self.instance_identifer} for this machine")
            return 
        
        previous_state = self.assignment_dict[self.instance_identifer] if self.instance_identifer in self.assignment_dict else None 
        current_state = new_assignment_dict[self.instance_identifer]
        if self.instance_identifer in self.assignment_dict and \
            previous_state != current_state:
            self.logger.warn("the assignment has changed! need to revoke the current assignment ")
            for topic_to_action_pair in self.state_dict[previous_state].topics:
                topic_name = list(topic_to_action_pair.keys())[0] # because it only has one element for sure
                topic_type = self.topic_dict[topic_name]
                topic_action = topic_to_action_pair[topic_name]
                send_request("del", topic_action, topic_name, topic_type, self.sgc_address)
                    
        # add in new topics 
        for topic_to_action_pair in self.state_dict[current_state].topics:
            topic_name = list(topic_to_action_pair.keys())[0] # because it only has one element for sure
            topic_type = self.topic_dict[topic_name]
            topic_action = topic_to_action_pair[topic_name]
            send_request("add", topic_action, topic_name, topic_type, self.sgc_address)

        # TODO: apply parameter changes 

    def _load_addresses(self, config):
        if "address" not in config:
            return 
        self.signaling_server_address = config["addresses"]["signaling_server_address"] if "signaling_server_address" in config["addresses"] else self.signaling_server_address
        self.routing_information_base_address = config["addresses"]["routing_information_base_address"] if "routing_information_base_address" in config["addresses"] else self.routing_information_base_address

    def _load_identifiers(self, config):
        self.task_identifier = config["identifiers"]["task"]
        if "whoami" not in config["identifiers"]: 
            # whoami not defined in the rosparam, we directly use the value from config file
            # the value is already in self.instance_identifier
            if not self.instance_identifer:
                self.logger.error("Both rosparam and config file do not define whoami, define it")
                exit()
        else:
            # either way,if rosparam is already defined, use rosparam's value
            if self.instance_identifer:
                self.logger.warn("both ros param and config file defines whoami, using the value from rosparam")
            else:
                self.instance_identifer = config["identifiers"]["whoami"]

    def _load_topics(self, config):
        for topic in config["topics"]:
            self.topic_dict[topic["topic_name"]] = topic["topic_type"]

    def _load_state_machine(self, config):
        for state_name in config["state_machine"]:
            state_description = config["state_machine"][state_name]
            if state_description:
                topics =  state_description["topics"] if "topics" in state_description else None 
                params =  state_description["params"] if "params" in state_description else None 
                self.state_dict[state_name] = SGC_StateMachine(state_name, topics, params)
            else:
                self.state_dict[state_name] = SGC_StateMachine(state_name, None, None)
        self.logger.info(str(self.state_dict))

    def get_assignment_from_yaml(self, yaml_path):
        with open(yaml_path, "r") as f:
            config = yaml.safe_load(f)
        for identity_name in config["assignment"]:
            state_name = config["assignment"][identity_name]
            if state_name not in self.state_dict:
                self.logger.warn(f"State {state_name} not defined. Not added!")
                continue 
            self.assignment_dict[identity_name] = state_name
        return self.assignment_dict


    # phase 1: only allow changing the state on state machine 
    # TODO: allowing changing the state machine (not a must)
    def update():
        pass 


class SGC_Router_Node(rclpy.node.Node):
    def __init__(self):
        super().__init__('sgc_launch_node')
        self.logger = self.get_logger()

        self.declare_parameter("whoami", "")
        self.whoami = self.get_parameter("whoami").value

        self.declare_parameter("config_path", "")
        self.config_path = self.get_parameter("config_path").value

        self.declare_parameter("sgc_base_port", 3000) # port = base_port + ROS_DOMAIN_ID
        self.sgc_base_port = self.get_parameter("sgc_base_port").value

        self.declare_parameter("config_file_name", "PARAMETER NOT SET") # ROS2 parameter is strongly typed
        self.config_file_name = self.get_parameter("config_file_name").value

        self.ros_domain_id = os.getenv('ROS_DOMAIN_ID') if os.getenv('ROS_DOMAIN_ID') else 0
        self.sgc_router_api_port = self.sgc_base_port + int(self.ros_domain_id)
        self.sgc_router_api_addr = f"localhost:{self.sgc_router_api_port}"

        if self.config_file_name == "PARAMETER NOT SET":
            
            self.logger.warn("No config file specified! Use unstable automatic topic discovery!")
            self.timer = self.create_timer(1, self.discovery_callback)
            self.automatic_mode = True 
        else:
            self.automatic_mode = False

        self.declare_parameter("release_mode", True)
        self.release_mode = self.get_parameter("release_mode").value

        self.launch_sgc(self.config_path, self.config_file_name, self.logger, self.whoami, self.release_mode, self.automatic_mode )

        self.discovered_topics = ["/rosout", "/parameter_events"] # we shouldn't expose them as global topics 
        self.add_on_set_parameters_callback(self.parameters_callback)

        self.assignment_server = self.create_service(SgcAssignment, 'sgc_assignment_service', self.sgc_assignment_callback)

    def parameters_callback(self, params):
        self.logger.info(f"got {params}!!!")
        return SetParametersResult(successful=False)

    # ros2 service call /sgc_assignment_service sgc_msgs/srv/SgcAssignment '{machine: {data: "a"}, state: {data: "b"} }'
    def sgc_assignment_callback(self, request, response):
        machine = request.machine.data
        state = request.state.data
        assignment_dict = {machine: state}
        self.swarm.apply_assignment(assignment_dict)
        response.result.data = "success"
        return response

    def launch_sgc(self, config_path, config_file_name, logger, whoami, release_mode, automatic_mode):
        current_env = os.environ.copy()
        current_env["PATH"] = f"/usr/sbin:/sbin:{current_env['PATH']}"
        ws_path = current_env["COLCON_PREFIX_PATH"]
        # source directory of sgc
        sgc_path = f"{ws_path}/../src/fogros2-sgc"
        # directory of all the config files
        config_path = f"{ws_path}/sgc_launch/share/sgc_launch/configs" if not config_path else config_path
        # directory of all the crypto files
        crypto_path = f"{ws_path}/sgc_launch/share/sgc_launch/configs/crypto/test_cert/test_cert-private.pem"
        # check if the crypto files are generated, if not, generate them
        if not os.path.isfile(crypto_path):
            logger.info(f"crypto file does not exist in {crypto_path}, generating...")
            subprocess.call([f"cd {ws_path}/sgc_launch/share/sgc_launch/configs && ./generate_crypto.sh"],  shell=True)
        
        # setup the config path
        current_env["SGC_CONFIG"] = f"{config_path}/automatic.toml"
        # setup crypto path
        current_env["SGC_CRYPTO_PATH"] = f"{crypto_path}"

        if automatic_mode:
            logger.info("automatic discovery is enabled")  
        else:
            config_path = f"{config_path}/{config_file_name}"
            logger.info(f"using yaml config file {config_path}")
            self.swarm = SGC_Swarm(config_path, whoami, logger, self.sgc_router_api_addr)
            

        # build and run SGC
        logger.info("building FogROS SGC... It takes longer for first time")
        # remove the stale SGC router if the domain id is the same 
        grep_result = subprocess.run(f"lsof -i -P -n | grep LISTEN | grep {self.sgc_router_api_port}", env=current_env, capture_output=True, text=True,  shell=True).stdout
        if grep_result:
            logger.warn("Previous run of SGC router in the same domain is running, killing it...")
            pid = grep_result.split()[1]
            subprocess.call(f"kill {pid}", env=current_env,  shell=True)
        # check if the port exists
        current_env["SGC_API_PORT"] = str(self.sgc_router_api_port)

        if release_mode:
            subprocess.call(f"cargo build --release --manifest-path {sgc_path}/Cargo.toml", env=current_env,  shell=True)
            subprocess.Popen(f"cargo run --release --manifest-path {sgc_path}/Cargo.toml router", env=current_env,  shell=True)
        else:
            subprocess.call(f"cargo build --manifest-path {sgc_path}/Cargo.toml", env=current_env,  shell=True)
            subprocess.Popen(f"cargo run --manifest-path {sgc_path}/Cargo.toml router", env=current_env,  shell=True)
        
        if not self.automatic_mode:
            sleep(2)
            self.swarm.apply_assignment(self.swarm.get_assignment_from_yaml(config_path))


    def discovery_callback(self):
        current_env = os.environ.copy()
        output = subprocess.run(f"ros2 topic list -t", env=current_env, capture_output=True, text=True,  shell=True).stdout
        for line in output.split("\n"):
            # /rosout [rcl_interfaces/msg/Log]
            if line == "":
                continue
            topic_name = line.split(" ")[0]
            topic_type = line.split(" ")[1][1:-1]
            if topic_name not in self.discovered_topics:
                self.get_logger().info(f"found a new topic {topic_name} {topic_type}")
                output = subprocess.run(f"ros2 topic info {topic_name}", env=current_env, capture_output=True, text=True,  shell=True).stdout
                if "Subscription count: 0" in output:
                    self.get_logger().info(f"publish {topic_name} as a remote publisher")
                    topic_action = "pub"
                    send_request("add", topic_action, topic_name, topic_type, self.sgc_router_api_addr)
                elif "Publisher count: 0" in output:
                    self.get_logger().info(f"publish {topic_name} as a remote subscriber")
                    topic_action = "sub"
                    send_request("add", topic_action, topic_name, topic_type, self.sgc_router_api_addr)
                else:
                    self.get_logger().info(f"cannot determine {topic_name} direction")
                self.discovered_topics.append(topic_name)
            # TODO: remove a topic when the topic is gone 


    # self.timer = self.create_timer(1, self.timer_callback)
    # def timer_callback(self):
    #     my_param = self.get_parameter('my_parameter').get_parameter_value().string_value
    #     self.get_logger().info('Hello %s!' % my_param)
    #     my_new_param = rclpy.parameter.Parameter(
    #         'my_parameter',
    #         rclpy.Parameter.Type.STRING,
    #         'world'
    #     )
    #     all_new_parameters = [my_new_param]
    #     self.set_parameters(all_new_parameters)

# def main():
#     rclpy.init()
#     node = SGC_Router_Node()

#     rclpy.spin(node)

spin_queue = []
PERIOD = 0.01


def main(args=None):
    rclpy.init(args=args)

    # you'll probably want to append your own node here
    spin_queue.append(SGC_Router_Node())
    spin_queue.append(SGC_Analyzer("identity",
                                    "/offload_detection/scheduler_yolo/input/cloud",
                                    "sensor_msgs/msg/CompressedImage",
                                    "/offload_detection/scheduler_yolo/output/cloud",
                                    "sensor_msgs/msg/CompressedImage",
                                    10
                                    ))


    while rclpy.ok():
        try:
            for node in spin_queue:
                rclpy.spin_once(node, timeout_sec=(PERIOD / len(spin_queue)))
        except Exception as e:
            print(f"something went wrong in the ROS Loop: {e}")

    rclpy.shutdown()

if __name__ == '__main__':
    main()
