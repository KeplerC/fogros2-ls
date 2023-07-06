

import subprocess, os, yaml

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

    with open(f"{config_path}/talker.yaml", "r") as f:
        print(yaml.safe_load(f)) 
    return 
    # build and run SGC
    print("building FogROS SGC... It takes longer for first time")
    subprocess.call(f"cargo run --manifest-path {sgc_path}/Cargo.toml router", env=current_env,  shell=True)

def main():
    launch_sgc()

if __name__ == '__main__':
    main()
