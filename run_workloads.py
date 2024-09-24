#!/usr/bin/env python

import argparse
import subprocess
import signal
import sys
import time
import os
import random
import json


terminate_flag = False

def load_config():
    if "iosense_config" in os.environ:
        with open(os.environ["iosense_config"], "r") as f:
            return json.load(f)
    else:
        print("Error: iosense_config environment variable is not set.")
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

        p = subprocess.Popen([run_script, sampled_config_file])
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
    
def run_application_workload(config, app_name):
    """
    Run the specified application workload.
    """
    print(f"Starting application workload: {app_name}")

    if app_name == "IO500":
        client_root = config['client']['install_dir']
        run_script = os.path.join(client_root, "workloads/IO500/run.sh")
        config_dir = os.path.join(client_root, "workloads/IO500/regular_configs")
    
        config_files = get_config_files(config_dir)
        if not config_files:
            print(f"No configuration files found in {config_dir}")
            sys.exit(1)
        try:
            for config_file in config_files:
                print(f"Running IO500 with configuration: {config_file}")
                p = subprocess.Popen([run_script, config_file])
                retcode = p.wait()
                if retcode != 0:
                    print(f"IO500 process exited with return code {retcode}")
                    sys.exit(retcode)
                else:
                    print(f"Completed IO500 with configuration: {config_file}")
            print("Application workload completed.")
        except Exception as e:
            print(f"Error during application workload: {e}")
            sys.exit(1)
    else:
        print(f"Unknown application workload: {app_name}")
        sys.exit(1)

def main(config):
    parser = argparse.ArgumentParser(description='Run workloads for cluster testing.')
    parser.add_argument('--interference_level', type=int, help='Interference level (integer)')
    parser.add_argument('--app', type=str, help='Application workload to run')

    args = parser.parse_args()

    if args.interference_level is not None:
        run_interference_workload(config, args.interference_level)
    elif args.app:
        run_application_workload(config, args.app)
    else:
        print("No valid arguments provided. Use --interference_level or --app.")
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    config = load_config()
    main(config)