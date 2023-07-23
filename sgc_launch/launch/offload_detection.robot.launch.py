import os
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    """TODO"""

    launch_description = LaunchDescription()

    sgc_router = Node(
        package="sgc_launch",
        executable="sgc_router", 
        output="screen",
        emulate_tty = True,
        parameters = [
            # find and add config file in ./sgc_launhc/configs
            # or use the `config_path` optional parameter
            {"config_file_name": "offload_detection.yaml"}, 
            {"whoami": "robot"},
            {"release_mode": True}
        ]
    )
    launch_description.add_action(sgc_router)

    camera = Node(
        package = "offload_detection",
        name = "simulate_camera_node",
        executable = "simulate_camera_node.py",
        output = "screen",
        emulate_tty = True,
        parameters = [
            {"rate": 15}])
    launch_description.add_action(camera)

    scheduler = Node(
        package = "offload_detection",
        name = "scheduler_yolo",
        executable = "scheduler_node_capped.py",
        output = "screen",
        emulate_tty = True,
        parameters = [
            {"edge_on": False},
            {"cloud_on": True},
            {"max_framerate": 10.0},
            {"detector_timeout": 10.0}])
    launch_description.add_action(scheduler)
    
    profiler = Node(
        package = "offload_detection",
        name = "profiler_node_edge",
        executable = "profiler_node.py",
        output = "screen",
        parameters = [
            {"on_cloud": False},
            {"gpu_id": 0},
            {"update_interval": 0.5},
            {"bandwidth_smoothing": 0.0},
            {"framerate_smoothing": 0.0},
            {"latency_smoothing": 0.0},
            {"processor_smoothing": 0.0},
            {"network_smoothing": 0.0}])
    launch_description.add_action(profiler)
    
    return launch_description