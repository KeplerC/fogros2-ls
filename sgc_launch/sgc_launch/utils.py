from pydoc import locate

def get_ROS_class(ros_message_type, srv=False):
    """
    Returns the ROS message class from ros_message_type.
    :return AnyMsgClass: Class of the ROS message.
    """
    try:
        package_name, msg, message_name = ros_message_type.split('/')
    except ValueError:
        raise ValueError(
            'ros_message_type should be in the shape of package_msgs/Message' +
            ' (it was ' + ros_message_type + ')')
    if not srv:
        msg_class = locate('{}.msg.{}'.format(package_name, message_name))
    else:
        msg_class = locate('{}.srv.{}'.format(package_name, message_name))
    if msg_class is None:
        if srv:
            msg_or_srv = '.srv'
        else:
            msg_or_srv = '.msg'
        raise ValueError(
            'ros_message_type could not be imported. (' +
            ros_message_type + ', as "from ' + package_name +
            msg_or_srv + ' import ' + message_name + '" failed.')
    return msg_class