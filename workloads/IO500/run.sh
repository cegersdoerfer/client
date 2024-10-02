
#!/bin/bash


# Check if a config file is provided as an argument
if [ $# -eq 0 ]; then
    echo "Error: Config file must be provided as an argument."
    echo "Usage: $0 <config_file> [darshan_file]"
    exit 1
fi

config_file="$1"

# Check if there are two arguments
if [ $# -eq 2 ]; then
    # Check if Darshan tracing is enabled (second argument is a boolean)
    if [ "$2" = "true" ]; then
        mpi_args="-np 4 -env DXT_ENABLE_IO_TRACE 1 -env LD_PRELOAD /custom-install/hpc-tools/pnetcdf-1.13.0/install/lib/libpnetcdf.so:/custom-install/hpc-tools/hdf5-1.14.4-3/install/lib/libhdf5.so:/custom-install/io-profilers/darshan-3.4.5/darshan-runtime/install/lib/libdarshan.so"
    else
        mpi_args="-np 4"
    fi
else
    # Default to no Darshan tracing if only one argument is provided
    mpi_args="-np 4"
fi

# Export the MPI arguments so they can be used in the IO500 script
export IO500_MPIARGS="$mpi_args"

io500_dir="/custom-install/benchmarks/io500"
cd $io500_dir
# Run the IO500 benchmark with the provided config file
./io500.sh "$config_file"

