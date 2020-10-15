import sys
import shlex
import paramiko

from binascii           import hexlify
from os                 import listdir
from os.path            import dirname, realpath, join, isfile, isdir
from pathlib            import Path
from paramiko           import RSAKey
from paramiko.py3compat import u
from subprocess         import Popen, PIPE
from cryptography.hazmat.primitives     import serialization


def gen_dockerfile(host_rsakey, dependencies):

    aft_dir = Path(dirname(realpath(__file__))).parent
    docker_str = ""
    with open(join(aft_dir, 'templates', 'dockerfile.tmplt')) as dockerfile:
        docker_str = dockerfile.read()

    docker_str = docker_str.format(
        dependencies,
        host_rsakey.replace('\n', '\\n\\\n'),
        'xxx'
        )
    with open('dockerfile', 'w') as out_file:
        out_file.write(docker_str)
    return docker_str


def gen_rsa_key(filename):

    private_key_obj = RSAKey.generate(bits=1024)
    private_key = private_key_obj.key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()
            ).decode()
    private_key_obj.write_private_key_file('aft_container_host_key')
    public_key_obj  = RSAKey(filename='aft_container_host_key')

    return private_key, public_key_obj


def get_clients(worker_config, rsa_pub, host_key_file, dependencies):

    out = {}
    for worker in worker_config:
        out[worker] = []
        for instance in range(0, worker_config[worker]['instances']):
            if worker_config[worker]['remote'] is False:
                client = get_local_session(
                        rsa_pub,
                        dependencies,
                        instance
                        )
            else:
                client = get_remote_session(
                        worker_config[worker],
                        rsa_pub,
                        host_key_file,
                        dependencies,
                        instance
                        )
            out[worker].append(client)
    return out

def get_remote_session(config, rsa_pub, host_key_file, dependencies, instance):
    # connect to remote host
    client = paramiko.SSHClient()
    client.load_host_keys(os.path.expanduser(host_key_file))
    client.connect(
            config['ip'],
            port=config['port'],
            username=['user'],
            key_filename=config['key file']
            )
    #TODO
    # build docker container
    stdin, stdout, stderr = client.exec_command('docker build -t aft:1.0 -')
    stdin.write(docker_string)
    if err := stderr.read():
        sys.stderr.write(err)
        sys.stderr.flush()
        sys.exit(1)
    # run docker container
    stdin, stdout, stderr = client.exec_command('docker run -d -P --name aft{} aft:1.0'.format(instance))
    # forward all ssh traffic
    # return client
    pass

def get_local_session(rsa_pub, dependencies, instance):
    # start docker container
    p = Popen(
            shlex.split('docker run -d -P --name aft{} aft:1.0'.format(instance)),
            stdout=PIPE,
            stderr=PIPE
            )
    try:
        out, err = p.communicate(timeout=50)
    except TimeoutError:
        p.kill()
        out, err = p.communicate()
        print(err.decode())
        sys.exit(1)
    if p.returncode != 0:
        sys.exit(1)

    # get ssh port
    p = Popen(
            shlex.split('docker port aft{}'.format(instance)),
            stdout=PIPE,
            stderr=PIPE
            )
    try:
        out, err = p.communicate(timeout=5)
    except TimeoutError:
        p.kill()
        out, err = p.communicate()
    if p.returncode != 0:
        sys.exit(1)
    port = int(out.decode().split(':')[-1])
    # connect with paramiko
    client = paramiko.SSHClient()
    client.get_host_keys().add(
            '[0.0.0.0]:{}'.format(port),
            'ssh-rsa',
            rsa_pub
            )
    client.connect(
            '0.0.0.0',
            port=port,
            username='root',
            password='pass'
            )
    sin, sout, serr = client.exec_command(
            'apt-get update && apt-get install -y {}'.format(dependencies)
            )
    # return client
    return client

def shutdown_clients(clients, worker_config):
    # close ssh clients
    for client_list in clients.values():
        for client in client_list:
            client.close()
    # connect to workers and stop containers
    for worker in worker_config:
        if worker_config[worker]['remote'] is True:
            stop_remote_container(worker_config[worker])
        else:
            stop_local_container(worker_config[worker])

def stop_local_container(worker_config):
    commands = ["docker stop aft{}", "docker rm aft{}"]
    for command in commands:
        for instance in range(0, worker_config['instances']):
            p = Popen(
                    shlex.split(command.format(instance)),
                    stdout=PIPE,
                    stderr=PIPE
                    )
            stdout, stderr = p.communicate()
            if p.returncode != 0:
                print(stderr.decode())
                sys.exit(1)

def stop_remote_container(worker_config):
    # connect to remote
    stop_str = "docker stop aft"
    rm_str = "docker rm aft"


def put_dir(sftp, dir_path, dest_path):
    sftp.mkdir(dest_path)
    for f in listdir(dir_path):
        if isfile(join(dir_path, f)):
            sftp.put(
                    join(dir_path, f),
                    "{}/{}".format(dest_path, f)
                    )
        elif isdir:
            put_dir(
                    sftp,
                    join(dir_path, f),
                    "{}/{}".format(dest_path, f)
                    )
        else:
            pass
