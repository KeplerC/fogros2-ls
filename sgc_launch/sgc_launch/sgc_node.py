

import subprocess, os, yaml
import requests
import pprint
from time import sleep 
import rclpy
import rclpy.node

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
                 sgc_address="localhost:3000"):
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
            pprint.pprint(config)
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
            # whoami not defined in the rosparam, use the value from config file
            if self.instance_identifer != "":
                self.instance_identifer = config["identifiers"]["whoami"]
            # need to define whoami either at rosparam or config file 
            else:
                self.logger.error("Both rosparam and config file do not define whoami, define it")
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



def launch_sgc(logger, whoami):
    current_env = os.environ.copy()
    current_env["PATH"] = f"/usr/sbin:/sbin:{current_env['PATH']}"
    ws_path = current_env["COLCON_PREFIX_PATH"]
    # source directory of sgc
    sgc_path = f"{ws_path}/../src/fogros2-sgc-digial-double"
    # directory of all the config files
    config_path = f"{ws_path}/sgc_launch/share/sgc_launch/configs"
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

    config_path = f"{config_path}/talker.yaml"
    swarm = SGC_Swarm(config_path, whoami, logger)

    # build and run SGC
    logger.info("building FogROS SGC... It takes longer for first time")
    # remove the stale SGC router
    subprocess.call("kill $(ps aux | grep 'gdp-router' | awk '{print $2}')", env=current_env,  shell=True)
    subprocess.call(f"cargo build --manifest-path {sgc_path}/Cargo.toml", env=current_env,  shell=True)
    subprocess.Popen(f"cargo run --manifest-path {sgc_path}/Cargo.toml router", env=current_env,  shell=True)

    sleep(2)
    swarm.apply_assignment(swarm.get_assignment_from_yaml(config_path))


class SGC_Router_Node(rclpy.node.Node):
    def __init__(self):
        super().__init__('sgc_launch_node')

        self.declare_parameter("whoami", "")
        self.whoami = self.get_parameter("whoami").value
        self.logger = self.get_logger()

        launch_sgc(self.logger, self.whoami)
       


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

def main():
    rclpy.init()
    node = SGC_Router_Node()
    rclpy.spin(node)

if __name__ == '__main__':
    main()
