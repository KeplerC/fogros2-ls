
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    """Talker example that launches everything locally."""
    ld = LaunchDescription()

    # talker_node = Node(
    #     package="bench", executable="listener",
    # )

    # ld.add_action(talker_node)

    client_node = Node(
        package="bench", executable="add_three_ints_client",
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
            {"config_file_name": "service-client.yaml"}, 
            {"whoami": "machine_client"},
            {"release_mode": False}
        ]
    )
    ld.add_action(sgc_router)
    
    return ld
