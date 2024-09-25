import os
import configparser

def update_ini_files(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.ini'):
                file_path = os.path.join(root, file)
                config = configparser.ConfigParser()
                config.read(file_path)

                #if 'global' in config:
                #    config['global']['datadir'] = '/mnt/hasanfs/io500_runs/datafiles_interference'
                #    config['global']['resultdir'] = '/mnt/hasanfs/io500_runs/results_interference'
                
                #if 'ior-easy' in config:
                #    config['ior-easy']['blockSize'] = '10g'

                #for section in config:
                #    if 'mdt' in section or 'mdw' in section:
                #        # Set the API to POSIX for all mdtest sections
                #        config[section]['API'] = 'POSIX'

                if 'debug' in config:
                    config['debug']['stonewall-time'] = '30'

                with open(file_path, 'w') as configfile:
                    config.write(configfile)
                print(f"Updated {file_path}")

# Path to the interference_configs directory
interference_configs_dir = '../workloads/IO500/interference_configs'

update_ini_files(interference_configs_dir)
print("All ini files have been updated.")