#!/usr/bin/env python

import argparse
import subprocess
import signal
import sys
import time
import os
import random
import json
import shutil
import datetime

terminate_flag = False

APPS = ["IO500", "amrex", "macsio", "e3sm", "openpmd"]

def load_config(config_path):
    global DEBUG
    try:
        if "IOSENSE_CONFIG_FILE" in os.environ:
            with open(os.environ["IOSENSE_CONFIG_FILE"], "r") as f:
                config = json.load(f)
                print("config content: ", config)
                if "debug" in config:
                    if config["debug"]:
                        print("DEBUG was set to true in the config file")
                        DEBUG = True
                    else:
                        print("DEBUG was set to false in the config file")
                        DEBUG = False
                else:
                    DEBUG = None
        else:
            DEBUG = None
            with open(config_path, "r") as f:
                config = json.load(f)

        return config
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

def signal_handler(signum, frame):
    global terminate_flag
    print(f"Signal {signum} received, terminating interference workload.")
    terminate_flag = True

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def run_interference_workload(config, interference_level):
    """
    Run interference workload by maintaining interference_level number of IO500 processes.
    Each process runs with a random configuration from the interference_configs directory.
    """
    global terminate_flag
    processes = []
    print(f"Starting interference workload with interference level {interference_level}")

    # Paths to the run script and configuration directory
    client_root = config['client']['install_dir']
    run_script = os.path.join(client_root, "workloads/IO500/run.sh")
    config_dir = os.path.join(client_root, "workloads/IO500/interference_configs")

    # Get list of configuration files
    sample_dict = create_sample_dict(config_dir)
    if not sample_dict:
        print(f"No configuration directories found in {config_dir}")
        sys.exit(1)

    try:
        # Start initial IO500 processes
        for _ in range(interference_level):
            print(f"Starting IO500 process {_}")
            p = start_io500_process(run_script, sample_dict)
            if p:
                processes.append(p)

        # Main loop to monitor processes
        while not terminate_flag:
            # Check for completed processes
            for p in processes[:]:  # Iterate over a copy of the list
                retcode = p.poll()
                if retcode is not None:
                    # Process has finished
                    print(f"IO500 process with PID {p.pid} exited with return code {retcode}")
                    processes.remove(p)
                    if not terminate_flag:
                        # Start a new process to maintain the interference level
                        new_p = start_io500_process(run_script, sample_dict)
                        if new_p:
                            processes.append(new_p)
            time.sleep(1)  # Sleep to prevent busy waiting

    except Exception as e:
        print(f"Error during interference workload: {e}")
    finally:
        # Terminate all running IO500 processes
        print("Terminating all IO500 interference processes.")
        for p in processes:
            terminate_process(p)
        print("Interference workload terminated.")

def create_sample_dict(config_dir):
    """
    Create a dictionary with the number of configuration files in each directory.
    """
    config_dirs = get_config_dirs(config_dir)
    sample_dict = {}
    for subdir in config_dirs:
        config_files = get_config_files(subdir)
        sample_dict[subdir] = config_files
    return sample_dict


def sample_config_file(sample_dict):
    """
    Sample a random configuration file from the specified directories.
    """
    config_dir = random.choice(list(sample_dict.keys()))
    config_files = sample_dict[config_dir]
    return random.choice(config_files)

def start_io500_process(run_script, sample_dict):
    """
    Start an IO500 process with a random configuration file.
    """
    try:
        sampled_config_file = sample_config_file(sample_dict)
        print(f"Starting IO500 with configuration: {sampled_config_file}")
        command = f"{run_script} {sampled_config_file} > output.txt"
        print(f"Running command: {command}")
        p = subprocess.Popen(command, shell=True, env=os.environ)
        print(f"Started IO500 process with PID {p.pid}")
        return p
    except Exception as e:
        print(f"Failed to start IO500 process: {e}")
        return None

def terminate_process(p):
    """
    Terminate the given subprocess.Popen object.
    """
    try:
        p.terminate()
        p.wait(timeout=5)
        print(f"Terminated IO500 process with PID {p.pid}")
    except subprocess.TimeoutExpired:
        p.kill()
        print(f"Killed IO500 process with PID {p.pid} after timeout")
    except Exception as e:
        print(f"Error terminating process {p.pid}: {e}")

def get_config_dirs(config_dir):
    """
    Get a list of configuration files from the specified directory.
    """
    try:
        dirs = [os.path.join(config_dir, f) for f in os.listdir(config_dir)
                 if os.path.isdir(os.path.join(config_dir, f))]
        return dirs
    except Exception as e:
        print(f"Error accessing configuration directory {config_dir}: {e}")
        return []
    
def get_config_files(dir_path):
    """
    Get a list of configuration files from the specified directory.
    """
    try:
        files = [os.path.join(dir_path, f) for f in os.listdir(dir_path)
                 if os.path.isfile(os.path.join(dir_path, f))]
        return files
    except Exception as e:
        print(f"Error accessing configuration directory {dir_path}: {e}")
        return []


def gather_darshan_logs(darshan_log_dir, workload, config, config_ini, interference_level, repetition_idx):
    config_ini = os.path.basename(config_ini).split(".")[0]
    print(f"Starting to gather Darshan logs for workload: {workload}, config: {config_ini}, interference level: {interference_level}")
    
    day, month, year = datetime.datetime.now().day, datetime.datetime.now().month, datetime.datetime.now().year
    darshan_log_dir = f"{darshan_log_dir}/{year}/{month}/{day}"
    print(f"Darshan log directory: {darshan_log_dir}")

    if "IOSENSE_LOG_TIMESTAMP" in os.environ:
        timestamp_dir = os.environ["IOSENSE_LOG_TIMESTAMP"]
        print(f"Using timestamp directory: {timestamp_dir}")
    else:
        print("Error: IOSENSE_LOG_TIMESTAMP environment variable is not set.")
        sys.exit(1)

    print(f"Config: {config}")
    print(f"Config ini: {config_ini}")
    print(f"Interference level: {interference_level}")
    
    target_dir = f"{config['data_dir']}/{workload}/darshan_logs/{timestamp_dir}/interference_level_{interference_level}/{repetition_idx}"
    print(f"Target directory for logs: {target_dir}")

    if not os.path.exists(target_dir):
        print(f"Creating target directory: {target_dir}")
        os.makedirs(target_dir)

    # move all darshan logs to the target dir
    idx = 0
    print(f"Starting to move Darshan log files from {darshan_log_dir} to {target_dir}")
    for file in os.listdir(darshan_log_dir):
        if file.endswith(".darshan"):
            print(f"file: {file}")
            old_path = os.path.join(darshan_log_dir, file)
            print(f"old path: {old_path}")
            new_name = f"{config_ini}_{idx}.darshan"
            print(f"new name: {new_name}")
            new_path = os.path.join(target_dir, new_name)
            print(f"new path: {new_path}")
            print(f"Moving file: {old_path} -> {new_path}")
            shutil.move(old_path, new_path)
            idx += 1

    print(f"Finished gathering Darshan logs. Moved {idx} files.")


def run_application_workload(config, app_name, interference_level, repetition_idx):
    """
    Run the specified application workload.
    """
    print(f"Starting application workload: {app_name}")
    global DEBUG
    if app_name in APPS:
        client_root = config['client']['install_dir']
        run_script = os.path.join(client_root, f"workloads/{app_name}/run.sh")
        config_dir = os.path.join(client_root, f"workloads/{app_name}/regular_configs")
    
        config_files = get_config_files(config_dir)
        if not config_files:
            print(f"No configuration files found in {config_dir}")
            sys.exit(1)
        try:
            for config_file in config_files:
                if app_name == "IO500":
                    if not config_file.endswith(".ini"):
                        print(f"Skipping {config_file} because it is not an ini file")
                        continue
                if app_name in APPS[1:]:
                    if not config_file.endswith(".json"):
                        print(f"Skipping {config_file} because it is not a json file")
                        continue
                if DEBUG:
                    if not "debug" in config_file:
                        print(f"Skipping {config_file} because it is not a debug config")
                        continue
                else:
                    if "debug" in config_file:
                        print(f"Skipping {config_file} because it is a debug config")
                        continue
                print(f"Running {app_name} with configuration: {config_file}")
                if app_name == "IO500":
                    command = f"{run_script} {config_file} true"
                else:
                    command = f"{run_script} {config_file}"
                print(f"Running command: {command}")
                p = subprocess.Popen(command, shell=True, env=os.environ)
                retcode = p.wait()
                if retcode != 0:
                    print(f"{app_name} process exited with return code {retcode}")
                    sys.exit(retcode)
                else:
                    print(f"Completed {app_name} with configuration: {config_file}")
                    gather_darshan_logs(config['darshan_log_dir'], app_name, config, config_file, interference_level, repetition_idx)
                
                command = "rm -rf /mnt/hasanfs/io500_data"
                print(f"Running command: {command}")
                p = subprocess.Popen(command, shell=True, env=os.environ)
                retcode = p.wait()
                if retcode != 0:
                    print(f"rm -rf /mnt/hasanfs/io500_data exited with return code {retcode}")
                    sys.exit(retcode)
                else:
                    print("rm -rf /mnt/hasanfs/io500_data completed")
                # sleep for 15 minutes to allow for garbage collection
                time.sleep(15*60)
            print("Application workload completed.")
        except Exception as e:
            print(f"Error during application workload: {e}")
            sys.exit(1)
    else:
        print(f"Unknown application workload: {app_name}")
        sys.exit(1)

def main(args):
    config = load_config(args.config)
    if not args.target_host:
        if args.interference_level > 0:
            random.seed(args.interference_level+10)
            run_interference_workload(config, args.interference_level)
    else:
        run_application_workload(config, args.app, args.interference_level, args.repetition_idx)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run workloads for cluster testing.')
    parser.add_argument('--target_host', action='store_true', help='Target host to run the workload on')
    parser.add_argument('--interference_level', type=int, help='Interference level (integer)')
    parser.add_argument('--app', type=str, help='Application workload to run')
    parser.add_argument('--repetition_idx', type=int, help='Repetition index (integer)')
    parser.add_argument('--config', type=str, help='Path to the config file')
    args = parser.parse_args()

    main(args)