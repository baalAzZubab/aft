import getopt
import json
import os
import shlex
import subprocess
import sys
import time

from os         import listdir, chdir, mkdir, getcwd
from os.path    import join
from resource   import getrusage, RUSAGE_CHILDREN
from signal     import SIGINT, SIGTERM
from subprocess import Popen, PIPE, STDOUT, DEVNULL, TimeoutExpired


def dispatch_fuzzing(algorithm, input_mode, output_mode, exec_args, build_args, fuzzing_mode, timeout, max_cycle):
    os.chdir('workdir')

    # load build script
    if build_args in listdir('/root/util'):
        with open('/root/util/{}'.format(build_args)) as f:
            build_script = f.read().splitlines()
    else:
        build_script = [build_args]

    # build the algorithm
    environment = os.environ.copy()
    environment['AFL_USE_ASAN'] = '1'
    environment['AFL_USE_UBSAN'] = '1'
    if fuzzing_mode == '1':
        # binary mode; just compile
        for line in build_script:
            if 'cd' in line:
                os.chdir(line[3:])
            elif 'export' in line:
                var = line[7:].split('=')
                environment[var[0]] = var[1]
            else:
                proc = subprocess.run(
                        line,
                        shell=True,
                        stdout=DEVNULL,
                        check=True,
                        env=environment
                        )
    elif fuzzing_mode == '2':
        # gcc plugin; compile with afl-gcc plugin
        for line in build_script:
            if 'g++' in line:
                line = line.replace('g++', 'afl-g++-fast')
            elif 'gcc' in line:
                line = line.replace('gcc', 'afl-gcc-fast')
            if 'cd' in line:
                os.chdir(line[3:])
            elif 'export' in line:
                var = line[7:].split('=')
                environment[var[0]] = var[1]
            else:
                environment['CC'] = "afl-gcc-fast"
                environment['CXX'] = "afl-g++-fast"
                proc = subprocess.run(
                        line,
                        shell=True,
                        stdout=DEVNULL,
                        check=True,
                        env=environment
                        )
    elif fuzzing_mode == '3':
        # llvm mode; compile with afl-clang-lto
        for line in build_script:
            if 'clang++' in line:
                line = line.replace('clang++', 'afl-clang-lto++')
            elif 'clang' in line:
                line = line.replace('clang', 'afl-clang-lto')
            if 'cd' in line:
                os.chdir(line[3:])
            elif 'export' in line:
                var = line[7:].split('=')
                environment[var[0]] = var[1]
            else:
                environment['CC'] = "afl-clang-lto"
                environment['CXX'] = "afl-clang-lto++"
                proc = subprocess.run(
                        line,
                        shell=True,
                        stdout=DEVNULL,
                        check=True,
                        env=environment
                        )
    else:
        print('unknown fuzzing mode')
        sys.exit(1)

    # run the fuzzer
    qemu = '-Q' if fuzzing_mode == '1' else ''
    fuzzing_command = 'afl-fuzz -i /root/inputs -o out -V {} -m none -d -L -1 {} -- {}'.format(timeout, qemu, exec_args)
    fuzzer = Popen(
            shlex.split(fuzzing_command),
            stdout=PIPE,
            stderr=STDOUT
            )
    with fuzzer.stdout:
        for line in iter(fuzzer.stdout.readline, b''):
            # get relevant lines of output
            if 'cycle' in line.decode():
                # extract the number of cycle from afl++ output
                words = line.decode().rstrip().split(" ")
                cycle = words[-1].replace('.','').replace('\x1b[0m','').strip()
                print('entering cycle {}'.format(cycle))
                # end afl++ after finishing max_cycle or timeout
                if int(cycle) > int(max_cycle):
                    print('maximum cycle completed')
                    print('shutting afl++ down')
                    fuzzer.send_signal(SIGINT)


def dispatch_consuming(algorithm, input_mode, output_mode, exec_args, build_args, input_name, timeout):
    # named fields procduced by the getusage syscall
    usage_fields = [
            'utime',
            'stime',
            'maxrss',
            'ixrss',
            'idrss',
            'isrss',
            'minflt',
            'majflt',
            'nswap',
            'inblock',
            'oublock',
            'msgsnd',
            'msgrcv',
            'nsignals',
            'nvcsw',
            'nivscw'
            ]
    output = {}

    # fix path
    if getcwd() != '/root':
        chdir('/root')

    # load build script
    if build_args in listdir('/root/util'):
        with open('/root/util/{}'.format(build_args)) as f:
            build_script = f.read().splitlines()
    else:
        build_script = [build_args]

    if algorithm not in listdir('/root/builds'):
        mkdir('/root/builds/{}'.format(algorithm))
        os.system('cp -R /root/algorithms/{} /root/builds/{}/{}'.format(algorithm, algorithm, algorithm))
        # build the algorithm
        chdir('builds/{}'.format(algorithm))
        environment = os.environ.copy()
        for line in build_script:
            if 'cd' in line:
                chdir(line[3:])
            elif 'export' in line:
                var = line[7:].split('=')
                environment[var[0]] = var[1]
            else:
                proc = subprocess.run(
                        shlex.split(line),
                        shell=True,
                        stdout=DEVNULL,
                        check=True,
                        env=environment
                        )
    else:
        chdir('builds/{}'.format(algorithm))

    # if input file is required replace the command
    if input_mode == '1':
        # stdin
        with open('/root/inputs/{}'.format(input_name), 'rb') as in_file:
            data = in_file.read()
        pass
    elif input_mode == '2':
        # file
        data = None
        exec_args = exec_args.replace(
                '@@',
                '/root/inputs/{}'.format(input_name)
                )
    else:
        # error
        sys.stderr.write('false input mode')
        sys.exit(1)
    # run the algorithm
    process = Popen(
            shlex.split(exec_args),
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE
            )
    try:
        stdout, stderr = process.communicate(data, timeout=int(timeout))
    except TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
    # capture returncode and add to output
    output['failed'] = True if process.returncode != 0 else False
    # capture stdout and stderr and add to output
    output['stdout'] = []
    for line in stdout.decode().splitlines():
        output['stdout'].append(line)
    output['stderr'] = []
    for line in stderr.decode().splitlines():
        output['stderr'].append(line)

    # generate the usage dictionary and add to output
    output['usage'] = {}
    for field_name, val in zip(usage_fields, getrusage(RUSAGE_CHILDREN)):
        output['usage'][field_name] = val

    # write the info in json
    print(json.dumps(output))


def main(argv):
    # argparsing
    opts = "m:a:i:o:e:b:f:t:c:f:"
    l_opts = [
            'mode=',
            'alg=',
            'imode=',
            'omode=',
            'exec-args=',
            'build-args=',
            'fmode=',
            'timeout=',
            'max-cycle=',
            'file='
            ]
    try:
        opts, args = getopt.getopt(argv, opts, l_opts)
    except getopt.GetoptError as err:
        print(err)
        sys.exit(1)
    for opt, arg in opts:
        if opt in ('-m', '--mode'):
            mode = arg
        elif opt in ('-a', '--alg'):
            algorithm = arg
        elif opt in ('-i', '--imode'):
            input_mode = arg
        elif opt in ('-o', '--omode'):
            output_mode = arg
        elif opt in ('-e', '--exec-args'):
            exec_args = arg
        elif opt in ('-b', '--build-args'):
            build_args = arg
        elif opt in ('-f', '--fmode'):
            fuzzing_mode = arg
        elif opt in ('-t', '--timeout'):
            timeout = arg
        elif opt in ('-c', '--max-cycle'):
            max_cycle = arg
        elif opt in ('-f', '--file'):
            input_name = arg
        else:
            sys.exit(1)

    if mode == 'fuzz':
        dispatch_fuzzing(
                algorithm,
                input_mode,
                output_mode,
                exec_args,
                build_args,
                fuzzing_mode,
                timeout,
                max_cycle
                )
    elif mode == 'run':
        dispatch_consuming(
                algorithm,
                input_mode,
                output_mode,
                exec_args,
                build_args,
                input_name,
                timeout
                )
    else:
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
