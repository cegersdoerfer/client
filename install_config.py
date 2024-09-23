import json
import paramiko
import subprocess
import argparse

CONFIG_FILE = "cluster_config.json"

def parse_config(config_file):
    with open(config_file, 'r') as f:
        config = json.load(f)
    return config

def run_remote_command(host, username, command):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=host, username=username, timeout=10)
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()
        ssh.close()
        return output.strip(), error.strip()
    except Exception as e:
        return '', f"SSH connection to {host} failed: {e}"
    
def run_local_command(command):
    try:
        stdin, stdout, stderr = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = stdout.read().decode()
        error = stderr.read().decode()
        return output.strip(), error.strip()
    except Exception as e:
        return '', f"Local command failed: {e}"

def install_iosense(host, username, host_type, host_type_config, local=False):
    if host_type == 'client':
        repo_url = "https://github.com/cegersdoerfer/client.git"
        permission_command = f"chmod +x {host_type_config['install_dir']}/run_workloads.py"
    else:
        repo_url = "https://github.com/cegersdoerfer/server.git"
        permission_command = f"chmod +x {host_type_config['install_dir']}/collect_stats.sh"
    install_dir = host_type_config['install_dir']
    
    if local:
        command = f"chmod +x ./launch_multi_interference_test.py && chmod +x ./run_workloads.py"
        output, error = run_local_command(command)
    else:
        command = f"rm -rf {install_dir} && mkdir -p {install_dir} && git clone {repo_url} {install_dir} && {permission_command}"
        output, error = run_remote_command(host, username, command)
    if error:
        print(f"Error installing iosense on {host}: {error}")
    else:
        print(f"Installed iosense on {host}")

def configure_cluster(config, username):
    # Configure servers (MDS and OSS)
    server_hosts = config['mds'] + config['oss']
    for host in server_hosts:
        print(f"Configuring server on {host}...")
        install_iosense(host, username, 'server', config['server'])

    # Configure interference clients
    for host in config['interference_clients']:
        print(f"Configuring client on {host}...")
        install_iosense(host, username, 'client', config['client'])

    # Configure target client
    target_client = config['target_client']
    print(f"Configuring target client on {target_client}...")
    install_iosense(target_client, username, 'client', config['client'], local=True)

def main(args):
    username = "root"  # You might want to change this or prompt for it
    config = parse_config(args.config)
    configure_cluster(config, username)
    print("Cluster configuration completed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Install and configure the iosense on the cluster.")
    parser.add_argument("--config", type=str, default=CONFIG_FILE, help="Path to the cluster configuration file.")
    global username
    username = "root"
    args = parser.parse_args()
    main(args)
