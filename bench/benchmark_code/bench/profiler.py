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

import rclpy
from std_msgs.msg import String
from time import sleep 
# pip install psutil
import psutil
import subprocess 
import multiprocessing



def main(args=None):
    rclpy.init(args=args)
    timer_period = 0.5  # seconds
    node = rclpy.create_node("minimal_publisher")
    global_cpu_publisher = node.create_publisher(String, "cpu_global", 10)
    top_cpu_publisher = node.create_publisher(String, "cpu_top", 10)
    host_name = socket.gethostname()
    host_ip = socket.gethostbyname(host_name)

    def global_cpu_usage():
        msg = String()
        cpu_percent = psutil.cpu_percent(interval=1)
        msg.data = f"{cpu_percent}"
        # node.get_logger().warning('Publishing: "%s"' % msg.data)
        global_cpu_publisher.publish(msg)

    timer = node.create_timer(timer_period, global_cpu_usage)

    def top_cpu_usage():
        msg = String()
        output = subprocess.run(f"top -b -n 5 | head -n 12 | tail -n 5", capture_output=True, text=True,  shell=True).stdout

        for line in output.split("\n"):
            if not line:
                continue
            process_name = line.split()[-1]
            process_cpu_usage = float(line.split()[-4]) / multiprocessing.cpu_count()
            msg.data = f"{process_name}, {process_cpu_usage}"
            # node.get_logger().warning('Publishing: "%s"' % msg.data)
            top_cpu_publisher.publish(msg)

    timer = node.create_timer(timer_period, top_cpu_usage)

    rclpy.spin(node)

    # Destroy the timer attached to the node explicitly
    # (optional - otherwise it will be done automatically
    # when the garbage collector destroys the node object)
    node.destroy_timer(timer)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
