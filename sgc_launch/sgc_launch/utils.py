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

from icmplib import ping

def ping_host(host, payload = 500):
    ping_result = ping(address=host, count=5, interval = 0.2, timeout=2, payload_size=payload, privileged=False)

    return {
        'host': host,
        'avg_latency': ping_result.avg_rtt,
        'min_latency': ping_result.min_rtt,
        'max_latency': ping_result.max_rtt,
        'packet_loss': ping_result.packet_loss
    }

import urllib.request

def get_public_ip_address():
    return urllib.request.urlopen('https://ident.me').read().decode('utf8')
