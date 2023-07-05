

import subprocess, os

def build_sgc():
    print("building FogROS sgc... It takes longer time for first time")
    current_env = os.environ.copy()
    current_env["PATH"] = f"/usr/sbin:/sbin:{current_env['PATH']}"
    subprocess.Popen("cargo run --manifest-path ./src/fogros2-sgc-digial-double/Cargo.toml router", env=current_env,  shell=True)

def main():
    build_sgc()

if __name__ == '__main__':
    main()
