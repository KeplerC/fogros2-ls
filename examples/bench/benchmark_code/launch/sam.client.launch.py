
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    """Talker example that launches everything locally."""
    ld = LaunchDescription()
    
    client_node = Node(
        package="sam", executable="sam_client",
    )

    ld.add_action(client_node)

    sgc_router = Node(
        package="sgc_launch",
        executable="sgc_router", 
        output="screen",
        emulate_tty = True,
        parameters = [
            # find and add config file in ./sgc_launhc/configs
            # or use the `config_path` optional parameter
            {"config_file_name": "service-sam.yaml"}, 
            {"whoami": "machine_client"},
            {"release_mode": True}
        ]
    )
    ld.add_action(sgc_router)
    
    return ld
