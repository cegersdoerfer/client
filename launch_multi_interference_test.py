import paramiko
import subprocess
import signal
import sys
import json
import getpass

collect_stats_processes = []
run_workloads_processes = []

CONFIG_FILE = "cluster_config.json"

def parse_config():
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
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
    
def check_remote_dir(host, username, dir):
    command = f"if [ -d '{dir}' ]; then echo 'true'; else echo 'false'; fi"
    output, error = run_remote_command(host, username, command)
    return output.strip() == 'true'

def install_iosense(host, username, host_type, host_type_config):
    if host_type == 'client':
        repo_url = "https://github.com/cegersdoerfer/client.git"
        permission_command = f"chmod +x {host_type_config['install_dir']}/run_workloads.py"
    else:
        repo_url = "https://github.com/cegersdoerfer/server.git"
        permission_command = f"chmod +x {host_type_config['install_dir']}/collect_stats.sh"
    install_dir = host_type_config['install_dir']
    # create install_dir and clone repo
    command = f"mkdir -p {install_dir} && git clone {repo_url} {install_dir} && {permission_command}"
    output, error = run_remote_command(host, username, command)
    if error:
        print(f"Error installing iosense on {host}: {error}")
    else:
        print(f"Installed iosense on {host}")


def start_collect_stats(hosts, username, server_config):
    global collect_stats_processes
    for host in hosts:
        # check if install_dir exists on remote host
        if not check_remote_dir(host, username, server_config['install_dir']):
            install_iosense(host, username, 'server', server_config)
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

def start_run_workloads(hosts, username, interference_level, client_config):
    global run_workloads_processes
    for host in hosts:
        # check if install_dir exists on remote host
        if not check_remote_dir(host, username, client_config['install_dir']):
            install_iosense(host, username, 'client', client_config)
        command = f"nohup python run_workloads.py --interference_level {interference_level} > /dev/null 2>&1 & echo $!"
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
    # Start collect_stats.sh on mdt and osts
    server_hosts = config['mdts'] + config['osts']
    print("Starting collect_stats.sh on servers...")
    start_collect_stats(server_hosts, username, config['server'])
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Interference levels from 1 to 5
    interference_levels = [1, 2, 3, 4, 5]

    for interference_level in interference_levels:
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
    print("\nAll interference levels completed.")
    cleanup()

if __name__ == "__main__":
    main()