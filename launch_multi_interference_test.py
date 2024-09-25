import paramiko
import subprocess
import signal
import sys
import json
import os
import zipfile
import datetime


collect_stats_processes = []
run_workloads_processes = []

CONFIG_FILE = "cluster_config.json"

def parse_config():
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    os.environ["IOSENSE_CONFIG_FILE"] = CONFIG_FILE
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
        # Escape the $! so that it's evaluated on the remote host
        command = f"nohup {server_config['install_dir']}/collect_stats.sh > /dev/null 2>&1 & echo $!"
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
        zip_file_name = f"{host}_stats.zip"
        remote_stats_dir = f"{server_config['stats_log_dir']}"
        remote_zip_file = f"/tmp/{zip_file_name}"
        local_zip_file = os.path.join(local_stats_dir, zip_file_name)
        local_unzip_dir = os.path.join(local_stats_dir, host)
        
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
            ssh.close()
            print(f"Successfully gathered stats from {host} to {local_zip_file}")
        except Exception as e:
            print(f"Error transferring stats from {host}: {e}")

        # Unzip the stats file
        try:
            if not os.path.exists(local_unzip_dir):
                os.makedirs(local_unzip_dir)
            with zipfile.ZipFile(local_zip_file, 'r') as zip_ref:
                zip_ref.extractall(local_unzip_dir)
            print(f"Successfully unzipped stats for {host} to {local_unzip_dir}")
            # Optionally remove the zip file after unzipping
            os.remove(local_zip_file)
        except Exception as e:
            print(f"Error unzipping stats for {host}: {e}")

def start_run_workloads(hosts, username, interference_level, client_config):
    global run_workloads_processes
    for host in hosts:
        command = f"nohup python {client_config['install_dir']}/run_workloads.py --interference_level {interference_level} > /dev/null 2>&1 & echo $!"
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


def stop_remote_processes(processes, username):
    for proc in processes:
        host = proc['host']
        pid = proc['pid']
        command = f"kill -9 {pid}"
        output, error = run_remote_command(host, username, command)
        if error:
            print(f"Error stopping process {pid} on {host}: {error}")
        else:
            print(f"Stopped process {pid} on {host}")

def start_local_run_workloads(workload):
    process = subprocess.Popen(["python", "run_workloads.py", "--app", workload])
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

def main():
    global username
    workload = "IO500"
    username = "root"
    config = parse_config()
    os.environ["IOSENSE_LOG_TIMESTAMP"] = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # Start collect_stats.sh on mdt and osts
    server_hosts = config['mdts'] + config['osts']
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Interference levels from 1 to 5
    interference_levels = [0, 1, 3, 5]

    for interference_level in interference_levels:
        print("Starting collect_stats.sh on servers...")
        start_collect_stats(server_hosts, username, config['server'])
        print(f"\n=== Starting interference level {interference_level} ===")
        print(f"Starting run_workloads.py on remote clients with interference level {interference_level}...")
        start_run_workloads(config['interference_clients'], username, interference_level, config['client'])
        print(f"Starting run_workloads.py locally with workload {workload}...")
        local_process = start_local_run_workloads(workload)
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
            collect_stats_processes.clear()
    print("\nAll interference levels completed.")
    cleanup()

if __name__ == "__main__":
    main()