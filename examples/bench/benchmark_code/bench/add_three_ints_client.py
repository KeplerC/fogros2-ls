# Copyright 2022 The Regents of the University of California (Regents)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Copyright ©2022. The Regents of the University of California (Regents).
# All Rights Reserved. Permission to use, copy, modify, and distribute this
# software and its documentation for educational, research, and not-for-profit
# purposes, without fee and without a signed licensing agreement, is hereby
# granted, provided that the above copyright notice, this paragraph and the
# following two paragraphs appear in all copies, modifications, and
# distributions. Contact The Office of Technology Licensing, UC Berkeley, 2150
# Shattuck Avenue, Suite 510, Berkeley, CA 94720-1620, (510) 643-7201,
# otl@berkeley.edu, http://ipira.berkeley.edu/industry-info for commercial
# licensing opportunities. IN NO EVENT SHALL REGENTS BE LIABLE TO ANY PARTY
# FOR DIRECT, INDIRECT, SPECIAL, INCIDENTAL, OR CONSEQUENTIAL DAMAGES,
# INCLUDING LOST PROFITS, ARISING OUT OF THE USE OF THIS SOFTWARE AND ITS
# DOCUMENTATION, EVEN IF REGENTS HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH
# DAMAGE. REGENTS SPECIFICALLY DISCLAIMS ANY WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE. THE SOFTWARE AND ACCOMPANYING DOCUMENTATION, IF ANY,
# PROVIDED HEREUNDER IS PROVIDED "AS IS". REGENTS HAS NO OBLIGATION TO PROVIDE
# MAINTENANCE, SUPPORT, UPDATES, ENHANCEMENTS, OR MODIFICATIONS.

import socket
from time import sleep

import rclpy
from rclpy.node import Node
from bench_msgs.srv import AddThreeInts
import hashlib 
from matplotlib import pyplot as plt
from time import time 
import numpy as np

def print_string_with_color_based_on_name(string, name):
    
    hash_value = int(hashlib.sha256(name.encode()).hexdigest(), 16)
    # Choose a color based on the hash value
    color_code = hash_value % 8  # You can change the number of colors as needed

    # Define color codes (you can modify this based on your preferences)
    colors = ["\033[91m", "\033[92m", "\033[93m", "\033[94m", "\033[95m", "\033[96m", "\033[97m", "\033[90m"]

    return colors[color_code] + string + "\033[00m"

class AddThreeIntsAsyncClientNode(Node):

    def __init__(self):
        super().__init__('add_three_ints_client_async')
        self.get_logger().info(f"Initializing client for /add_three_ints.")
        self.cli = self.create_client(AddThreeInts, 'add_three_ints')
        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        self.req = AddThreeInts.Request()

    def send_request(self, a, b, c):
        self.req.a = a
        self.req.b = b
        self.req.c = c
        self.future = self.cli.call_async(self.req)
        rclpy.spin_until_future_complete(self, self.future)
        return self.future.result()


def main(args=None):
    rclpy.init(args=args)

    host_name = socket.gethostname()
    host_ip = socket.gethostbyname(host_name)
    
    add_three_ints_client = AddThreeIntsAsyncClientNode()

    a = 0
    b = 1
    c = 2

    latency = dict()
    latency_timetsamp = dict()
    beginning_time = time()
    overall_latency = []


    while True:
        time_start = time()
        add_three_ints_client.get_logger().info(f"I am {host_name} ond {host_ip}. Sending request {a}, {b}, {c}")
        response = add_three_ints_client.send_request(a,b,c)
        if response == None:
            add_three_ints_client.get_logger().error(
                print(
                    f'Result is None!',
                )
            )
        
        elif response.sum == 0:
            add_three_ints_client.get_logger().error(
                print_string_with_color_based_on_name(
                    f'Result times out!',
                    response.server_name
                )
            )
        else:
            add_three_ints_client.get_logger().info(
                print_string_with_color_based_on_name(
                    f'Received from {response.server_name}. Result of add_two_ints: {a} + {b} + {c} = {response.sum}',
                    response.server_name
                )
            )
        overall_latency.append(time() - time_start)
        print_string_with_color_based_on_name(f"mean latency: {sum(overall_latency)/len(overall_latency)}, stddev: {np.std(overall_latency)}", response.server_name)
        
        a += 1
        b += 1
        c += 1
        sleep(2)
        

    add_three_ints_service_node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
