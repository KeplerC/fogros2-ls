from itertools import chain
import os, sys
from glob import glob, iglob
from attr import s
from setuptools import setup

package_name = 'sgc_launch'

# https://stackoverflow.com/questions/27829754/include-entire-directory-in-python-setup-py-data-files/76159267#76159267?newreg=0c740c2c1e204531a52f362c66fb8b1d
def generate_data_files(share_path, dir):
    data_files = []
    
    for path, _, files in os.walk(dir):
        list_entry = (share_path + path, [os.path.join(path, f) for f in files if not f.startswith('.')])
        data_files.append(list_entry)

    return data_files

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        (os.path.join("share", package_name), ["package.xml"]),
        (os.path.join("share", package_name), glob("launch/*.launch.py")),
        (
            os.path.join("share", package_name, "configs"),
            glob("configs/*.yaml"),
        ),
    ] + generate_data_files('share/' + package_name + '/', 'configs'),
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ubuntu',
    maintainer_email='kych@berkeley.edu',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'sgc_router = sgc_launch.sgc_node:main',
            'time_bound_analyzer = sgc_launch.time_bound_analyzer:main',
            'heuristic_pubsub = sgc_launch.heuristic_pubsub:main',
        ],
    },
)