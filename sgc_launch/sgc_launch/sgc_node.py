

import subprocess, os, yaml
import pprint

class SGC_State: 
    def __init__(self, state_name, topic_dict, param_dict):
        self.state_name = state_name
        self.topics = topic_dict
        self.params = param_dict


class SGC_Swarm: 
    def __init__(self, yaml_config):
        # the identifers for the task and ROS instance
        self.task_identifier = None 
        self.instance_identifer = None 
        
        # default Berkeley's parameters 
        self.signaling_server_address = 'ws://3.18.194.127:8000'
        self.routing_information_base_address = '3.18.194.127:8002'

        # topic dictionary: map topic to topic type 
        self.topic_dict = dict()

        # states: map state_name to SGC_State
        self.state_dict = dict()

        # assignment: map identifer to state_names 
        self.assignment = dict()

        self.load(yaml_config)

    def load(self, yaml_config):
        with open(yaml_config, "r") as f:
            config = yaml.safe_load(f)
            pprint.pprint(config)
        

        

    # phase 1: only allow changing the state on state machine 
    # TODO: allowing changing the state machine (not a must)
    def update():
        pass 



def launch_sgc():
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
        print("crypto file does not exist, generating...")
        subprocess.call([f"cd {ws_path}/sgc_launch/share/sgc_launch/configs && ./generate_crypto.sh"],  shell=True)
    
    # setup the config path
    current_env["SGC_CONFIG"] = f"{config_path}/automatic.toml"
    # setup crypto path
    current_env["SGC_CRYPTO_PATH"] = f"{crypto_path}"


    SGC_Swarm(f"{config_path}/template.yaml")

    return 
    # build and run SGC
    print("building FogROS SGC... It takes longer for first time")
    subprocess.call(f"cargo run --manifest-path {sgc_path}/Cargo.toml router", env=current_env,  shell=True)

def main():
    launch_sgc()

if __name__ == '__main__':
    main()
