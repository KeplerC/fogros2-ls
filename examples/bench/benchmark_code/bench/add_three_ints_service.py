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
import random

import rclpy
from rclpy.node import Node
from bench_msgs.srv import AddThreeInts
import hashlib


def print_string_with_color_based_on_name(string, name):
    
    hash_value = int(hashlib.sha256(name.encode()).hexdigest(), 16)
    # Choose a color based on the hash value
    color_code = hash_value % 8  # You can change the number of colors as needed

    # Define color codes (you can modify this based on your preferences)
    colors = ["\033[91m", "\033[92m", "\033[93m", "\033[94m", "\033[95m", "\033[96m", "\033[97m", "\033[90m"]

    return colors[color_code] + string + "\033[00m"


class AddThreeIntsServiceNode(Node):
    def __init__(self):
        super().__init__("add_two_ints")
        # generate random name
        self.host_name = socket.gethostname() + str(random.randint(0, 1000))

        self.get_logger().info(f'I am {self.host_name}. Starting service /add_three_ints.')

        self.service = self.create_service(AddThreeInts, "add_three_ints", self.add_three_ints_callback)


    def add_three_ints_callback(self, request, response):
        response.sum = request.a + request.b + request.c
        response.server_name = self.host_name
        self.get_logger().info(
            print_string_with_color_based_on_name(f'Incoming request: a: {request.a}, b: {request.b}, c: {request.c}. Sending: {response.sum}'
                                                  , self.host_name)
            
        )

        return response


def main(args=None):
    rclpy.init(args=args)


    add_three_ints_service_node = AddThreeIntsServiceNode()

    rclpy.spin(add_three_ints_service_node)

    # Destroy the node explicitly
    # (optional - otherwise it will be done automatically
    # when the garbage collector destroys the node object)
    add_three_ints_service_node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
