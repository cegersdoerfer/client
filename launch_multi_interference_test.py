import paramiko
import subprocess
import signal
import sys
import json
import os
import zipfile
import datetime
import argparse
import shutil
import time
import re

collect_stats_processes = []
run_workloads_processes = []

CONFIG_FILE = {"standard": "cluster_config.json", "debug": "debug_cluster_config.json"}

def parse_config(config_type):
    with open(CONFIG_FILE[config_type], 'r') as f:
        config = json.load(f)
    os.environ["IOSENSE_CONFIG_FILE"] = CONFIG_FILE[config_type]
    return config

def run_remote_command(host, username, command):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=host, username=username, timeout=10)
        # Prefix the command with sudo su - -c 'command'
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()
        ssh.close()
        return output.strip(), error.strip()
    except Exception as e:
        return '', f"SSH connection to {host} failed: {e}"


def start_collect_stats(hosts, username, server_config):
    global collect_stats_processes
    for host in hosts:
        stat_interval = 0.1
        stats_logging_dir = server_config['stats_log_dir']
        # Escape the $! so that it's evaluated on the remote host
        command = f"nohup {server_config['install_dir']}/collect_stats.sh {stat_interval} {stats_logging_dir} > /dev/null 2>&1 & echo $!"
        output, error = run_remote_command(host, username, command)
        if error:
            print(f"Error starting collect_stats.sh on {host}: {error}")
        else:
            pid = output.strip()
            if pid.isdigit():
                print(f"Started collect_stats.sh on {host} with PID {pid}")
                collect_stats_processes.append({'host': host, 'pid': pid})
            else:
                print(f"Failed to get PID for collect_stats.sh on {host}: {output}")

def gather_stats(hosts, username, workload, config):
    server_config = config['server']
    timestamp_dir = os.environ["IOSENSE_LOG_TIMESTAMP"]
    local_stats_dir = f"{config['data_dir']}/{workload}/stats/{timestamp_dir}"
    if not os.path.exists(local_stats_dir):
        os.makedirs(local_stats_dir)
    for host in hosts:
        zip_file_name = f"{host}_stats_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        remote_stats_dir = f"{server_config['stats_log_dir']}"
        remote_zip_file = f"{server_config['zip_logs_dir']}/{zip_file_name}"
        local_zip_file = os.path.join(local_stats_dir, zip_file_name)
        local_unzip_dir = os.path.join(local_stats_dir, f"{host}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        # Command to zip the stats directory on the remote host
        zip_command = f"cd {remote_stats_dir} && zip -r {remote_zip_file} ."
        output, error = run_remote_command(host, username, zip_command)
        if error:
            print(f"Error zipping stats on {host}: {error}")
            continue
        
        # Create an SFTP client and download the zip file
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(hostname=host, username=username, timeout=10)
            sftp = ssh.open_sftp()
            sftp.get(remote_zip_file, local_zip_file)
            sftp.remove(remote_zip_file)  # Remove the zip file from the remote host
            sftp.close()
            
            # Clear the stats files on the remote host
            clear_command = f"rm -rf {remote_stats_dir}/*"
            output, error = run_remote_command(host, username, clear_command)
            if error:
                print(f"Error clearing stats on {host}: {error}")
            else:
                print(f"Successfully cleared stats on {host}")
            
            ssh.close()
            print(f"Successfully gathered stats from {host} to {local_zip_file}")
        except Exception as e:
            print(f"Error transferring stats from {host}: {e}")

        # Unzip the stats file
        try:
            os.makedirs(local_unzip_dir, exist_ok=True)
            with zipfile.ZipFile(local_zip_file, 'r') as zip_ref:
                zip_ref.extractall(local_unzip_dir)
            print(f"Successfully unzipped stats for {host} to {local_unzip_dir}")
            # Optionally remove the zip file after unzipping
            os.remove(local_zip_file)
        except Exception as e:
            print(f"Error unzipping stats for {host}: {e}")

def start_run_workloads(hosts, username, interference_level, client_config, config_path):
    global run_workloads_processes
    for host in hosts:
        command = f"nohup python {client_config['install_dir']}/run_workloads.py --interference_level {interference_level} --config {config_path} > /dev/null 2>&1 & echo $!"
        output, error = run_remote_command(host, username, command)
        if error:
            print(f"Error starting run_workloads.py on {host}: {error}")
        else:
            pid = output.strip()
            if pid.isdigit():
                print(f"Started run_workloads.py on {host} with PID {pid}")
                run_workloads_processes.append({'host': host, 'pid': pid})
            else:
                print(f"Failed to get PID for run_workloads.py on {host}: {output}")

def remove_created_files(workload):
    mnt_dir = "/mnt/hasanfs"
    workload_name = workload.lower()
    data_dir = f"{mnt_dir}/{workload_name}_data"
    if os.path.exists(data_dir):
        print(f"Removing all files in {data_dir}...")
        command = f"rm -rf {data_dir}/*"
        print(f"Running command: {command}")
        # remove all files in the data_dir recursively
        try:
            start_time = time.time()
            subprocess.run(command, shell=True, check=True)
            end_time = time.time()
            print(f"Files removed successfully in {end_time - start_time} seconds.")
            # sleep for 5 minutes to allow garbage collection
            time.sleep(180)
        except subprocess.CalledProcessError as e:
            print(f"Error removing files in {data_dir}: {e}")



def stop_remote_processes(processes, username):
    for proc in processes:
        host = proc['host']
        pid = proc['pid']
        command = f"kill -9 {pid}"
        output, error = run_remote_command(host, username, command)
        if "node" in host:
            backup_command1 = f"kill -9 $(pgrep run_workloads.py)"
            output, error = run_remote_command(host, username, backup_command1)
            backup_command2 = f"kill -9 $(pgrep io500)"
            output, error = run_remote_command(host, username, backup_command2)
            
        if error:
            print(f"Error stopping process {pid} on {host}: {error}")
        else:
            print(f"Stopped process {pid} on {host}")

def start_local_run_workloads(workload, interference_level, repetition_idx):
    process = subprocess.Popen(["python", "run_workloads.py", "--app", workload, "--interference_level", str(interference_level), "--target_host", "--repetition_idx", str(repetition_idx)], env=os.environ)
    return process

def signal_handler(sig, frame):
    print("Signal received, performing cleanup...")
    cleanup()
    sys.exit(0)

def cleanup():
    print("Stopping any remaining remote run_workloads.py processes...")
    if run_workloads_processes:
        stop_remote_processes(run_workloads_processes, username)
        run_workloads_processes.clear()
    print("Stopping collect_stats.sh processes on servers...")
    if collect_stats_processes:
        stop_remote_processes(collect_stats_processes, username)
        collect_stats_processes.clear()


def wait_for_sync_changes(mds_list, check_interval=2, verbose=True):
    """
    1) For each MDS node, read the current 'osc.*.max_rpcs_in_progress' values
    and store them.
    2) Set all to 16384 to speed up processing.
    3) Wait until all MDS nodes have osc.*.sync_changes == 0.
    4) Restore the original 'max_rpcs_in_progress' values on each MDS node.

    :param mds_list: A list of MDS node hostnames (or IPs).
    :param check_interval: number of seconds to sleep between checks of sync_changes
    :param verbose: if True, print progress messages
    """

    # Regex to parse lines like:
    #   osc.myfs-OST0000-osc-MDT0000.max_rpcs_in_progress=512
    rpc_pattern = re.compile(r'^(osc\.[^=]+)\.max_rpcs_in_progress=(\d+)$')
    # Regex for lines like:
    #   osc.hasanfs-OST0000-osc-MDT0000.sync_changes=1747330
    sync_pattern = re.compile(r'^.*sync_changes=(\d+)$')

    # Step 1: Gather the current max_rpcs_in_progress on each MDS
    # We'll store them in a dict of the form:
    #   saved_params[MDS][osc_name] = old_value
    saved_params = {}

    for mds in mds_list:
        saved_params[mds] = {}
        # 1A) read current param values:
        cmd = ["ssh", mds, "lctl", "get_param", "osc.*.max_rpcs_in_progress"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"[{mds}] Failed to get max_rpcs_in_progress:\n{result.stderr}")

        lines = result.stdout.strip().splitlines()
        for line in lines:
            match = rpc_pattern.match(line.strip())
            if match:
                osc_name, old_val_str = match.groups()
                old_val = int(old_val_str)
                # e.g. osc_name='osc.hasanfs-OST0000-osc-MDT0000'
                saved_params[mds][osc_name] = old_val

        if verbose:
            print(f"[{mds}] Found {len(saved_params[mds])} OSTs with max_rpcs_in_progress")

    # Step 2: set all to 16384
    NEW_VALUE = 16384
    if verbose:
        print(f"Setting all MDS max_rpcs_in_progress to {NEW_VALUE}")

    for mds in mds_list:
        for osc_name in saved_params[mds]:
            cmd = ["ssh", mds, "lctl", "set_param",
                f"{osc_name}.max_rpcs_in_progress={NEW_VALUE}"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, check=False)
            if result.returncode != 0:
                raise RuntimeError(f"[{mds}] Failed setting {osc_name}.max_rpcs_in_progress:\n{result.stderr}")

    # Step 3: Wait for sync_changes to hit 0 on all MDSes
    if verbose:
        print("Now waiting for osc.*.sync_changes to reach 0 on all MDS nodes...")

    while True:
        all_done = True
        for mds in mds_list:
            # read sync_changes from each MDS
            cmd = ["ssh", mds, "lctl", "get_param", "osc.*.sync_changes"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, check=False)
            if result.returncode != 0:
                raise RuntimeError(f"[{mds}] get_param sync_changes failed:\n{result.stderr}")

            lines = result.stdout.strip().splitlines()
            total_changes = 0
            for line in lines:
                m = sync_pattern.match(line.strip())
                if m:
                    total_changes += int(m.group(1))

            if verbose:
                print(f"   [{mds}] sync_changes total={total_changes}")

            if total_changes > 0:
                all_done = False

        if all_done:
            if verbose:
                print("All MDS nodes have zero sync_changes. Done.")
            break

        time.sleep(check_interval)

    # Step 4: restore the old max_rpcs_in_progress on each MDS
    if verbose:
        print("Restoring original max_rpcs_in_progress values...")

    for mds in mds_list:
        for osc_name, old_val in saved_params[mds].items():
            cmd = ["ssh", mds, "lctl", "set_param",
                f"{osc_name}.max_rpcs_in_progress={old_val}"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, check=False)
            if result.returncode != 0:
                raise RuntimeError(f"[{mds}] Failed restoring {osc_name}.max_rpcs_in_progress:\n{result.stderr}")

    if verbose:
        print("All original values restored.")

def main():
    global DEBUG
    parser = argparse.ArgumentParser(description='Run workloads for cluster testing.')
    parser.add_argument('--debug', action='store_true', help='Run in debug mode')
    args = parser.parse_args()
    if args.debug:
        DEBUG = True
    else:
        DEBUG = False

    global username
    workload = "IO500"
    username = "root"
    if DEBUG:
        print("RUNNING IN DEBUG MODE")
        config = parse_config("debug")
        config_path = os.path.join(config['client']['install_dir'], CONFIG_FILE["debug"])
    else:
        config = parse_config("standard")
        config_path = os.path.join(config['client']['install_dir'], CONFIG_FILE["standard"])
    os.environ["IOSENSE_LOG_TIMESTAMP"] = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # Start collect_stats.sh on mdt and osts
    server_hosts = config['mds'] + config['oss']
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Interference levels from 1 to 5
    interference_levels = [1, 2]
    #assert 0 in interference_levels, "Interference level 0 is required"
    for interference_level in interference_levels:
        num_repetitions = 3
        if interference_level == 0:
            num_repetitions = 1
        for repetition_idx in range(num_repetitions):
            print("Starting collect_stats.sh on servers...")
            start_collect_stats(server_hosts, username, config['server'])
            print(f"\n=== Starting interference level {interference_level} ===")
            if interference_level > 0:
                print(f"Starting run_workloads.py on remote clients with interference level {interference_level}...")
                start_run_workloads(config['interference_clients'], username, interference_level, config['client'], config_path)
            print(f"Starting run_workloads.py locally with workload {workload}...")
            local_process = start_local_run_workloads(workload, interference_level, repetition_idx)
            try:
                # Wait for local_process to complete
                local_process.wait()
                print(f"Local run_workloads.py process completed for interference level {interference_level}.")
            except Exception as e:
                print(f"Exception: {e}")
            finally:
                print(f"Stopping remote run_workloads.py processes for interference level {interference_level}...")
                stop_remote_processes(run_workloads_processes, username)
                run_workloads_processes.clear()
                print(f"Stopping collect_stats.sh on servers for interference level {interference_level}...")
                stop_remote_processes(collect_stats_processes, username)
                gather_stats(server_hosts, username, workload, config)
                remove_created_files(workload)
                collect_stats_processes.clear()
                wait_for_sync_changes(server_hosts)
    print("\nAll interference levels completed.")
    cleanup()

if __name__ == "__main__":
    main()