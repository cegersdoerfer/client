import json
import paramiko
import subprocess
import argparse


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
        # Wait for the command to complete
        exit_status = stdout.channel.recv_exit_status()
        output = stdout.read().decode()
        error = stderr.read().decode()
        ssh.close()
        return output.strip(), error.strip(), exit_status
    except Exception as e:
        return '', f"SSH connection to {host} failed: {e}", -1

def run_local_command(command):
    try:
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = process.communicate()
        exit_status = process.returncode
        return output.decode().strip(), error.decode().strip(), exit_status
    except Exception as e:
        return '', f"Local command failed: {e}", -1

def overwrite_io500_script(host, username, client_config, local=False):
    command = f"cp {client_config['install_dir']}/workloads/IO500/io500.sh /custom-install/benchmarks/io500/io500.sh"
    if local:
        output, error, exit_status = run_local_command(command)
    else:
        output, error, exit_status = run_remote_command(host, username, command)
    if exit_status != 0:
        print(f"Error overwriting io500.sh on {host}: {error}")

def install_iosense(host, username, host_type, host_type_config, local=False):
    permission_commands = []
    dir_commands = []
    if host_type == 'client':
        repo_url = "https://github.com/cegersdoerfer/client.git"
        permission_commands.append(f"chmod +x {host_type_config['install_dir']}/run_workloads.py")
        permission_commands.append(f"chmod +x {host_type_config['install_dir']}/workloads/IO500/run.sh")
        permission_commands.append(f"chmod +x {host_type_config['install_dir']}/workloads/IO500/io500.sh")
        dir_commands.append(f"mkdir -p {host_type_config['install_dir']}")
    else:
        repo_url = "https://github.com/cegersdoerfer/server.git"
        permission_commands.append(f"chmod +x {host_type_config['install_dir']}/collect_stats.sh")
        dir_commands.append(f"mkdir -p {host_type_config['install_dir']}")
        dir_commands.append(f"mkdir -p {host_type_config['stats_log_dir']}")
        dir_commands.append(f"mkdir -p {host_type_config['zip_logs_dir']}")

    
    if local:
        permission_commands.append(f"chmod +x ./launch_multi_interference_test.py")
        permission_commands.append(f"chmod +x ./run_workloads.py")
        permission_commands.append(f"chmod +x ./workloads/IO500/run.sh")
        permission_commands.append(f"chmod +x ./workloads/IO500/io500.sh")
        command = " && ".join(permission_commands)
        output, error, exit_status = run_local_command(command)
    else:
        install_dir = host_type_config['install_dir']
        command = f"rm -rf {install_dir} && git clone {repo_url} {install_dir}"
        for dir_command in dir_commands:
            command += f" && {dir_command}"
        for permission_command in permission_commands:
            command += f" && {permission_command}"
        output, error, exit_status = run_remote_command(host, username, command)
    if exit_status != 0:
        print(f"Error installing iosense on {host}: {error}")
    else:
        print(f"Installed iosense on {host}")
        if output:
            print(f"Output from {host}: {output}")
        if error:
            print(f"Error messages from {host}: {error}")

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
        overwrite_io500_script(host, username, config['client'])
    # Configure target client
    target_client = config['target_client']
    print(f"Configuring target client on {target_client}...")
    install_iosense(target_client, username, 'client', config['client'], local=True)
    overwrite_io500_script(target_client, username, config['client'], local=True)

def main(config_file):
    username = "root"  # You might want to change this or prompt for it
    if DEBUG:
        config = parse_config('debug_cluster_config.json')
    else:
        config = parse_config(config_file)
    configure_cluster(config, username)
    print("Cluster configuration completed.")

if __name__ == "__main__":
    global DEBUG
    DEBUG = False
    CONFIG_FILE = "cluster_config.json"
    parser = argparse.ArgumentParser(description="Install and configure the iosense on the cluster.")
    parser.add_argument("--config", type=str, default=CONFIG_FILE, help="Path to the cluster configuration file.")
    parser.add_argument("--debug", action="store_true", help="Run in debug mode")
    args = parser.parse_args()
    if args.debug:
        DEBUG = True
    main(args.config)