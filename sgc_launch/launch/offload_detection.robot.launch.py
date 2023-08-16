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

    time_bound_analyzer = Node(
        package="sgc_launch",
        executable="sgc_time_analyzer", 
        output="screen",
        emulate_tty = True,
        parameters = [
            {"whoami": "robot"},
            {"latency_window" : 3.0}, 
        ]
    )
    launch_description.add_action(time_bound_analyzer)

    time_bound_analyzer = Node(
        package="sgc_launch",
        executable="sgc_policy_scheduler", 
        output="screen",
        emulate_tty = True,
        parameters = [
            {"config_file_name": "offload_detection.yaml"}, 
        ]
    )
    launch_description.add_action(time_bound_analyzer)

    heuristic_pubsub = Node(
        package="sgc_launch",
        executable="heuristic_pubsub", 
        output="screen",
        emulate_tty = True,
        parameters = [
            {"whoami": "robot"},
            {"request_topic_name": "/offload_detection/scheduler_yolo/input/cloud"}, 
            {"request_topic_type": "sensor_msgs/msg/CompressedImage"}, 
            {"response_topic_name": "/offload_detection/scheduler_yolo/output/cloud"}, 
            {"response_topic_type": "sensor_msgs/msg/CompressedImage"}, 
        ]
    )
    launch_description.add_action(heuristic_pubsub)

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