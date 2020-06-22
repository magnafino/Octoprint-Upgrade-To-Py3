#!/usr/bin/env python3
import sys
if sys.version_info.major != 3:
    print("This script will only run on python 3")
    print("Run using 'python3 upgrade.py'")
    sys.exit(0)

import os
import json
import subprocess
import zipfile
import requests
import re


def oprint_version_gt_141(venv_path):
    try:
        output = subprocess.run(
            ['{}/bin/python'.format(venv_path), '-m', 'octoprint', '--version'],
            check=True,
            capture_output=True
        ).stdout.rstrip().decode('utf-8')
    except subprocess.CalledProcessError:
        print("Failed to find OctoPrint install")
        print("If this is not OctoPi, please check that you have specified the right virtual env")
        sys.exit(0)

    version_no = re.search(r"(?<=version )(.*)", output).group().split('.')
    print("Octoprint version: {}.{}.{}".format(version_no[0], version_no[1], version_no[2]))
    if int(version_no[0]) >= 1 and int(version_no[1]) >= 4:
        if int(version_no[2]) > 0:
            return True
        else:
            return False
    else:
        # This is not strictly needed, but since I am only testing this against Octoprint 1.4.0 or later
        # I cannot guarantee behaviour of previous versions
        print("Please upgrade to an OctoPrint version >= 1.4.0 for Python 3 compatibility")
        sys.exit(0)


# Intro text
print("This script is about to perform an upgrade of your OctoPrint install from python 2 to 3")
print("It requires an internet connection to run")
print("**This action will disrupt any ongoing print jobs**")
print("It will install the latest OctoPrint release (1.4.0), as well as the latest version of all plugins")
print("No configuration or other files will be overwritten")
print("If the install fails, download the 'go_back.py' file here: https://github.com/cp2004/Octoprint-Upgrade-To-Py3/go_back.py")
confirm = input("Press [enter] to continue or ctrl-c to quit")

# Detect OctoPi or prompt for paths
PATH_TO_VENV = None
CONFBASE = None
if os.path.isfile("/etc/octopi_version"):
    print("\nDetected OctoPi installation")
    PATH_TO_VENV = "/home/pi/oprint"
    STOP_COMMAND = "sudo service octoprint stop"
    START_COMMAND = "sudo service octoprint start"
    print("Checking version")
    OPRINT_GT_141 = oprint_version_gt_141(PATH_TO_VENV)
    if not OPRINT_GT_141:
        CONFBASE = "/home/pi/.octoprint"
else:
    print("\nManual install detected")
    print("Please provide the path to your virtual environment and the config directory of octoprint")
    while not PATH_TO_VENV:
        path = input("Path: ")
        if os.path.isfile("{}/bin/python".format(path)):
            print("Venv found")
            PATH_TO_VENV = path
        else:
            print("Invalid venv path, please try again")
    print("Checking version")
    OPRINT_GT_141 = oprint_version_gt_141(PATH_TO_VENV)
    if not OPRINT_GT_141:
        while not CONFBASE:
            CONFBASE = input("Config directory: ")
            if os.path.isfile(os.path.join(CONFBASE, 'config.yaml')):
                print("Config directory valid")
            else:
                print("Invalid path, please try again")
                CONFBASE = None
    print("\nTo do the install, we need the service stop and start commands.")
    STOP_COMMAND = input("Stop command: ")
    START_COMMAND = input("Start command: ")

# Create backup to read the plugin list
print("\nCreating a backup so we can read the plugin list")
try:
    backup_output = subprocess.run(
        ["{}/bin/python".format(PATH_TO_VENV), "-m", "octoprint", "plugins", "backup:backup", "--exclude", "timelapse", "--exclude", "uploads"],
        check=True,
        capture_output=True
    ).stdout.rstrip().decode('utf-8')
except subprocess.CalledProcessError:
    print("Error getting backup from Octoprint")
    print("If you are on a manual install, please check octoprint is installed in the venv specified")
    sys.exit(0)

if OPRINT_GT_141:
    backup_target = re.search(r'(?<=Backup located at )(.*)(?=.zip)', backup_output).group()
else:
    octoprint_zip_name = re.search(r'(?<=Creating backup at )(.*)(?=.zip)', backup_output).group()
    backup_target = '{}/data/backup/{}'.format(CONFBASE, octoprint_zip_name)

# Extract plugin_list.json from the backup
print("Extracting plugin_list.json from backup")
with zipfile.ZipFile('{}.zip'.format(backup_target), 'r') as zip_ref:
    try:
        zip_ref.getinfo("plugin_list.json")
    except KeyError:
        # no plugin list
        plugin_list = None
    else:
        # read in list
        with zip_ref.open("plugin_list.json") as plugins:
            plugin_list = json.load(plugins)

# Generate a list of installed plugin keys
if plugin_list:
    print("\nPlugins installed:")
    plugin_keys = []
    for plugin in plugin_list:
        print("- {}".format(plugin['name']))
        plugin_keys.append(plugin['key'])
    print("If you think there is something missing from here, please check the list of plugins in Octoprint")
    go = input("Continue? [enter]")
else:
    plugin_keys = []
    print("No plugins found")
    print("If you think this is an error, please ask for help. Note this doesn't include bundled plugins.")
    go = input("Press [enter] to continue, or ctrl-c to quit")

# Move octoprint venv, create new one, install octoprint
PATH_TO_PYTHON = '{}/bin/python'.format(PATH_TO_VENV)  # Note this is the VIRTUALENV python
commands = [
    STOP_COMMAND.split(),
    ['mv', PATH_TO_VENV, '{}.bak'.format(PATH_TO_VENV)],
    ['virtualenv', '--python=/usr/bin/python3', PATH_TO_VENV],  # Only time we want to use system python
    [PATH_TO_PYTHON, '-m', 'pip', 'install', 'OctoPrint']
]
print("\nMoving venv and installing octoprint... (This may take a while - Do not cancel!)")
for command in commands:
    try:
        output = subprocess.run(
            command,
            check=True,
            capture_output=True
        ).stdout.decode('utf-8')
    except subprocess.CalledProcessError as e:
        print("ERROR: Failed to install Octoprint")
        print(e)
        # Remove zip
        print("\nCleaning Up... \nRemoving backup zip")
        os.remove("{}.zip".format(backup_target))
        print("Exiting")
        sys.exit(0)
print("Octoprint successfully installed")

# Create list of plugin urls, then install one by one
if len(plugin_keys):
    # Get the plugin repo
    print("\nFetching octoprint's plugin repo")
    PLUGIN_REPO = requests.get('https://plugins.octoprint.org/plugins.json').json()
    plugin_urls = []
    for plugin in PLUGIN_REPO:
        if plugin['id'] in plugin_keys:
            plugin_urls.append(plugin['archive'])
            plugin_keys.remove(plugin['id'])

    # Install plugins that were installed to the new env
    print("\nReinstalling plugins...")
    plugin_errors = []
    for plugin in plugin_urls:
        print("Installing {}".format(plugin))
        try:
            cmd_output = subprocess.run(
                [PATH_TO_PYTHON, '-m', 'pip', 'install', plugin],
                check=True,
                capture_output=True
            ).stdout.rstrip().decode('utf-8')
        except subprocess.CalledProcessError as e:
            plugin_errors.append(plugin[plugin])
            print("Error installing plugin, maybe it's not compatible?")
            print(e)
            sys.exit(0)
    if len(plugin_errors):
        print("Could not install these plugins:")
        for plugin in plugin_errors:
            print(" - {}".format(plugin))
        print("Reasons for this could be: \n- Not on the repository (Installed from uploaded archive/url) \n- Incompatible with your system")
        print("It is recommended that you reinstall them when you log back into octoprint")

    # Print plugins that were not on the repo
    print("\nThese plugins were not found on the repo, please install them manually")
    for not_found_plugin in plugin_keys:
        for plugin in plugin_list:
            if plugin['key'] == not_found_plugin:
                print("- {}".format(plugin['name']))

# Restart OctoPrint, and clean up
print("\nStarting Octoprint")
try:
    cmd_output = subprocess.run(
        START_COMMAND.split(),
        check=True,
        capture_output=True
    ).stdout.rstrip().decode('utf-8')
except subprocess.CalledProcessError as e:
    print("Error starting the OctoPrint service")
    print(e)
    sys.exit(0)

print("\nCleaning Up... \nRemoving backup zip")
os.remove("{}.zip".format(backup_target))
print("\nFinished! Octoprint should be restarted and ready to go")
print("Once you have verified the install works, you can safely remove the folder {}.bak".format(PATH_TO_VENV))
