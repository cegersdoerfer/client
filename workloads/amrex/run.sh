#!/bin/bash
config_file="$1"

h5bench_dir="/custom-install/benchmarks/h5bench"
cd $h5bench_dir
h5bench --debug $config_file