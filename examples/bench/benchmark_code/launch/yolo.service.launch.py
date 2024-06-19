
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    """Talker example that launches everything locally."""
    ld = LaunchDescription()

    service_node = Node(
        package="yolo", executable="yolo_service",
    )

    ld.add_action(service_node)

    sgc_router = Node(
        package="sgc_launch",
        executable="sgc_router", 
        output="screen",
        emulate_tty = True,
        parameters = [
            # find and add config file in ./sgc_launhc/configs
            # or use the `config_path` optional parameter
            {"config_file_name": "service-yolo.yaml"}, 
            {"whoami": "machine_server_1"},
            {"release_mode": True}
        ]
    )
    ld.add_action(sgc_router)
    
    return ld
