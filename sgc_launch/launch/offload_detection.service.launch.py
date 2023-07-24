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
            {"whoami": "machine_local"},
            {"release_mode": True}
        ]
    )
    launch_description.add_action(sgc_router)

    time_bound_analyzer = Node(
        package="sgc_launch",
        executable="time_bound_analyzer", 
        output="screen",
        emulate_tty = True,
        parameters = [
            {"whoami": "machine_local"},
            {"request_topic_name": "/offload_detection/scheduler_yolo/input/cloud"}, 
            {"request_topic_type": "sensor_msgs/msg/CompressedImage"}, 
            {"response_topic_name": "/offload_detection/scheduler_yolo/output/cloud"}, 
            {"response_topic_type": "sensor_msgs/msg/CompressedImage"}, 
        ]
    )
    launch_description.add_action(time_bound_analyzer)

    detector = Node(
        package = "offload_detection",
        name = "detector_node_yolo_cloud",
        executable = "detector_node_yolo.py",
        output = "screen",
        emulate_tty = True,
        parameters = [{"on_cloud": True}],
        arguments = ["--log-level", "info"])
    launch_description.add_action(detector)

    profiler = Node(
        package = "offload_detection",
        name = "profiler_node_cloud",
        executable = "profiler_node.py",
        output = "screen",
        emulate_tty = True,
        parameters = [
            {"on_cloud": True},
            {"gpu_id": 0},
            {"update_interval": 0.5},
            {"bandwidth_smoothing": 0.0},
            {"framerate_smoothing": 0.0},
            {"latency_smoothing": 0.0},
            {"processor_smoothing": 0.0},
            {"network_smoothing": 0.0}])
    launch_description.add_action(profiler)
    
    return launch_description