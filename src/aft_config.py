import json
from enum import Enum
from os import listdir
from os.path import join, isfile


class Inputmode(Enum):
    STDIN = 1
    FILE = 2

class Outputmode(Enum):
    STDOUT = 1
    FILE = 2

class Fuzzingmode(Enum):
    BINARY = 1
    GCC = 2
    CLANG = 3


def generate_config (algorithm_dir):
    config = {}
    config['global'] = gen_global_config()

    for algorithm in listdir(algorithm_dir):
      if isfile(join(algorithm_dir, algorithm)):
        config[str(algorithm)] = gen_alg_config(algorithm)

    while True:
        config_path = input("Save the configuration? Enter a path or -1 to skip\n")
        if config_path == "-1":
            break
        else:
            print("Configuration will be saved")
            with open(config_path, 'w+') as outfile:
                outfile.write(json.dumps(config, indent=4))
            break
    return config


def check_config (config_path, algorithm_dir):
    config_str = ''
    try:
        with open(config_path) as cfg_file:
            config_str = cfg_file.read()
        config = json.loads(config_str)
    except FileNotFoundError:
        config = {}

    try:
        config['global'] = check_global_config(config['global'])
    except KeyError:
        config['global'] = gen_global_config()

    for algorithm in listdir(algorithm_dir):
        try:
            config[algorithm] = check_alg_config(algorithm, config[algorithm])
        except KeyError:
            config[algorithm] = gen_alg_config(algorithm)
    while True:
        save = input("Do you want to save the configuration? Input Yy/Nn\n")
        if save.lower() == 'y':
            with open(config_path, "w+") as config_file:
                config_file.write(json.dumps(config, indent=4))
            break
        if save.lower() == 'n':
            break

    return config


def check_global_config (global_config):
    print("Checking global configuration for aft")
    fields = [ \
            ('afl running time', int, 'Maximum time in minutes for one fuzzing process to take'),\
            ('afl iteration limit', int, 'Maximum amount of iterations while fuzzing'),\
            ('execution time limit', int, 'Time in seconds after which execution of the algorithms timeout'),\
            ('ground truth', str, 'name of the algorithm to compare the results against'),\
            ('dependencies', str, 'Dependencies needed for the algorithms to build an run.\nSeparate by whitespaces.\nThese will be installed with apt-get, make sure they are available'),\
            ('host keys', str, 'Path to a file, which contains the public host keys of the remote workers')
            ]
    for (key, key_type, descr) in fields:
        try:
            if not isinstance(global_config[key], key_type):
                global_config[key] = read_new_val(key, key_type, descr)
        except KeyError:
            global_config[key] = read_new_val(key, key_type, descr)
    try:
        workers = global_config['workers']
        for worker in workers:
            global_config['workers'][worker] = check_worker_config(workers[worker])
    except KeyError:
        global_config['workers'] = gen_worker_config()
    return global_config


def gen_global_config():
    global_config = check_global_config({})
    return global_config


def check_alg_config (algorithm_name, algorithm_config):
    print("Checking configuration for algorithm {}".format(algorithm_name))
    fields = [ \
            ('execution string', str, 'Input the command to run the algorithm.\nReplace a input file with \'@@\'; for arguments over stdin specify no inputs'), \
            ('build string', str, 'Input the command to compile the algorithm'), \
            ('output adapter', str, 'Path to a program that transforms the outputs of this algorithm accordingly'), \
            ('input format', int, '1 for stdin\n2 for file'), \
            ('output format', int, '1 for stdin\n2 for file'), \
            ('fuzzing mode', int, '1 for fuzzing in binary mode\n 2 for fuzzing with gcc\n3 for fuzzing with clang')\
            ]
    for (key, key_type, descr) in fields:
        try:
            if not isinstance(algorithm_config[key], key_type):
                algorithm_config[key] = read_new_val(key, key_type, descr)
        except KeyError:
            algorithm_config[key] = read_new_val(key, key_type, descr)
    return algorithm_config


def gen_alg_config (algorithm_name):
    algorithm_config = check_alg_config(algorithm_name, {})
    return algorithm_config


def check_worker_config(worker_config):
    fields = [
            ('remote', bool, 'Leave blank for a local worker or type anything for a remote worker'),
            ('ip', str, 'Input the IP or host name for a remote worker or leave blank for a local worker'),
            ('key file', str, 'Absolute path to the public key file for a remote worker or leave blank for a local worker'),
            ('port', int, 'Custom port for a remote worker, leave blank for local worker or port 22'),
            ('user', str, 'Username under which to connect to the remote worker, leave blank for a local worker'),
            ('instances', int, 'Amount of docker containers to run simultaneously')
            ]
    for (key, key_type, descr) in fields:
        try:
            if not isinstance(worker_config[key], key_type):
                worker_config[key] = read_new_val(key, key_type, descr)
        except KeyError:
            worker_config[key] = read_new_val(key, key_type, descr)
    return worker_config

def gen_worker_config():
    print("No workers found. Auto generating one")
    worker_config = {
            'auto_local': {
                'remote' : False,
                'ip': "",
                'port': 0,
                'instances': 1
                }
            }
    return worker_config


def read_new_val(key, key_type, descr):
    while True:
        print(descr)
        new_val = key_type(
                input(
                    "Please input a value of type {} for {}\n".format(key_type, key)
                    )
                )
        if isinstance(new_val, key_type):
            return new_val
    return None
