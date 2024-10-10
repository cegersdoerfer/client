#!/bin/bash

# Async vol support needed in bashrc and h5bench config
config_file="$1"

h5bench_dir="/mnt/hasanfs/openpmd_data"
cd $h5bench_dir
h5bench --debug $config_file