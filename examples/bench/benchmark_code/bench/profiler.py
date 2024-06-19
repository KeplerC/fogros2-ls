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
from rclpy.node import Node
from std_msgs.msg import String
from time import sleep 
# pip install psutil
import psutil
import subprocess 
import multiprocessing

class Profiler_Node(Node):
    def __init__(self):
        super().__init__('Profiler_Node')
        self.declare_parameter("machine_name", "local")
        self.machine_name = self.get_parameter("machine_name").value

        self.declare_parameter("select_process", [""])
        self.process_names = self.get_parameter("select_process").value

        timer_period = 0.5  # seconds
        global_cpu_publisher = self.create_publisher(String, "cpu_global", 10)
        top_cpu_publisher = self.create_publisher(String, "cpu_top", 10)
        select_cpu_publisher = self.create_publisher(String, "cpu_select", 10)
        host_name = socket.gethostname()
        host_ip = socket.gethostbyname(host_name)

        def global_cpu_usage():
            msg = String()
            cpu_percent = psutil.cpu_percent(interval=1)
            msg.data = f"{self.machine_name}, {cpu_percent},{psutil.virtual_memory()[2]}"
            # node.get_logger().warning('Publishing: "%s"' % msg.data)
            global_cpu_publisher.publish(msg)

        timer = self.create_timer(timer_period, global_cpu_usage)

        def top_cpu_usage():
            msg = String()
            msg.data += self.machine_name
            output = subprocess.run(f"top -b -n 5 | head -n 12 | tail -n 5", capture_output=True, text=True,  shell=True).stdout

            for line in output.split("\n"):
                if not line:
                    continue
                process_name = line.split()[-1]
                process_cpu_usage = float(line.split()[-4]) / psutil.cpu_count()
                process_mem_usage = float(line.split()[-3])
                msg.data+=(f",{process_name},{process_cpu_usage},{process_mem_usage}")
                # node.get_logger().warning('Publishing: "%s"' % msg.data)
            top_cpu_publisher.publish(msg)

        timer = self.create_timer(timer_period, top_cpu_usage)

        def select_cpu_usage():
            msg = String()
            msg.data += self.machine_name
            for process in self.process_names:
                if process == "":
                    continue 
                output = subprocess.run(f"pidof -x {process}", capture_output=True, text=True,  shell=True).stdout
                self.get_logger().info(output)
                process_name = process
                if not output:
                    self.get_logger().warn(f"No process named {process}")
                for process_id in output.split():  
                    if not process_id:
                        continue
                    process_stat = psutil.Process(int(process_id))
                    process_cpu_usage = process_stat.cpu_percent() / psutil.cpu_count()
                    msg.data+=(f", {process_name}, {process_cpu_usage}, {process_stat.memory_percent}")
            select_cpu_publisher.publish(msg)

        timer = self.create_timer(timer_period, select_cpu_usage)

def main(args=None):
    rclpy.init(args=args)
    node = Profiler_Node()
    rclpy.spin(node)
    rclpy.shutdown()


if __name__ == "__main__":
    main()
