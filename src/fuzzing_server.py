import asyncio
import os
import shlex
import sys

from os import listdir
from os.path import join, isfile, isdir
from subprocess import Popen, PIPE, STDOUT
from ssh_util import put_dir


class Fuzzing_Server():

    def __init__(self, aft):
        self.aft = aft
        self.workers = []


    def run(self):
        print('fuzzer running')
        asyncio.run(self.fork_workers())
        # remove duplicates
        print('removing duplicates from queue...', end='')
        self.aft.fh.queue_remove_duplicates()
        print('done')


    async def fork_workers(self):
        self.queue = asyncio.Queue()
        self.fh_lock = asyncio.Lock()
        # create worker list
        self.producer = asyncio.create_task(self.produce())
        clients = [ client for client_list in self.aft.clients.values() for client in client_list ]
        self.workers = [ asyncio.create_task(self.consume(client)) for client in clients ]
        await asyncio.gather(self.producer)
        await self.queue.join()
        for worker in self.workers:
            worker.cancel()


    async def produce(self):
        for algorithm in listdir(self.aft.alg_dir):
            await self.queue.put(algorithm)


    async def consume(self, client):
        # setup
        client.exec_command('mkdir algorithms workdir inputs util')
        async with self.fh_lock:
            sftp = client.open_sftp()
            sftp.put(
                    join(self.aft.aft_dir, 'dispatch.py'),
                    'util/dispatch.py'
                    )
            # move all input files to remote
            for fl in listdir(self.aft.input_dir):
                sftp.put(
                    join(self.aft.input_dir, fl),
                    'inputs/{}'.format(fl)
                    )
            sftp.close()

        # start the working loop
        while True:
            algorithm = await self.queue.get()
            print("start fuzzing {}".format(algorithm))
            # move algorithm and utility to container
            async with self.fh_lock:
                sftp = client.open_sftp()
                # check whether the algorithm is a directory
                alg_path = join(self.aft.alg_dir, algorithm)
                if isfile(alg_path):
                    sftp.put(
                            alg_path,
                            'algorithms/{}'.format(algorithm)
                            )
                elif isdir(alg_path):
                    put_dir(
                            sftp,
                            alg_path,
                            'algorithms/{}'.format(algorithm)
                            )
                else:
                    sys.stderr.write('Algorithms have to be a file or directory')
                    sys.stderr.flush()
                    sys.exit(1)
                # move auxiliary scripts for the algorithm in place
                if isfile(self.aft.config[algorithm]['build string']):
                    build_file = os.path.split(self.aft.config[algorithm]['build string'])[-1]
                    # check whether it exists in the container
                    if build_file not in sftp.listdir('util'):
                        sftp.put(
                                self.aft.config[algorithm]['build string'],
                                'util/{}'.format(build_file)
                                )
                else:
                    build_file = self.aft.config[algorithm]['build string']
                # build script
                sftp.close()
            #move algorithm in place
            client.exec_command('rm -rf workdir/*')
            client.exec_command('cp -R algorithms/{} workdir/{}'.format(algorithm, algorithm))
            # run fuzzing dispatcher
            stdin, stdout, stderr = client.exec_command(
                """python3 util/dispatch.py --mode fuzz \
                        --alg {} --imode {} --omode {} \
                        --exec-args "{}" --build-args "{}" --fmode {} \
                        --timeout {} --max-cycle {}""".format(
                            algorithm,
                            self.aft.config[algorithm]['input format'],
                            self.aft.config[algorithm]['output format'],
                            self.aft.config[algorithm]['execution string'],
                            build_file,
                            self.aft.config[algorithm]['fuzzing mode'],
                            self.aft.config['global']['afl running time'] * 60,
                            self.aft.config['global']['afl iteration limit']
                            )
                        )
            for line in stdout:
                print(line.strip('\n'))
            for line in stderr:
                print(line.strip('\n'))
            commands = [
                    'docker cp -a aft0:root/workdir/out/queue {}'.format(join(
                        self.aft.output_dir,
                        algorithm,
                        'tmp'
                        )),
                    'docker cp -a aft0:root/workdir/out/crashes {}'.format(join(
                        self.aft.output_dir,
                        algorithm,
                        'tmp'
                        )),
                    'docker cp -a aft0:root/workdir/out/hangs {}'.format(join(
                        self.aft.output_dir,
                        algorithm,
                        'tmp'
                        ))
                    ]
            async with self.fh_lock:
                for cmd in commands:
                    p = Popen(
                            shlex.split(cmd),
                            stdout=PIPE,
                            stderr=STDOUT
                            )
                    stdout = p.communicate()[0]
                    if stdout.decode() != "":
                        print(stdout.decode())
                        sys.exit(1)
                self.aft.fh.gen_names(algorithm)

            # clean workdir
            client.exec_command('rm -rf workdir/*')

            print("done  fuzzing {}".format(algorithm))
            self.queue.task_done()
