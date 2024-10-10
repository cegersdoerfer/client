#!/bin/bash
config_file="$1"

h5bench_dir="/mnt/hasanfs/openpmd_data"
cd $h5bench_dir
h5bench --debug $config_file