import asyncio
import json
import os
import sys
import time

from os         import listdir
from os.path    import join, isfile, isdir
from ssh_util   import put_dir

class Consumer_Server():

    def __init__(self, aft):
        self.aft = aft
        self.workers = []
        self.ressource_log = {}


    def run(self):
        print('Consumer running')
        # fork and run workers
        asyncio.run(self.fork_workers())
        # write the logs
        for algorithm in self.ressource_log:
            with open(
                join(
                    self.aft.output_dir,
                    algorithm,
                    'ressource_logs.json'
                    ),
                'w'
                ) as log_file:
                    log_file.write(
                            json.dumps(
                                self.ressource_log[algorithm],
                                indent=4
                                )
                            )
        return

    async def fork_workers(self):
        self.queue = asyncio.Queue()
        self.ressource_log_lock = asyncio.Lock()
        self.fh_lock = asyncio.Lock()
        self.producer = asyncio.create_task(self.produce())
        clients = [ client for client_list in self.aft.clients.values() for client in client_list ]
        self.workers = [ asyncio.create_task(self.consume(client)) for client in clients ]
        await asyncio.gather(self.producer)
        await self.queue.join()
        for worker in self.workers:
            worker.cancel()
        pass

    async def produce(self):
        inputs = listdir(self.aft.queue_dir)
        algorithms = listdir(self.aft.alg_dir)
        for algorithm in algorithms:
            for inp in inputs:
                await self.queue.put((algorithm, inp))

    async def consume(self, client):
        # setup
        client.exec_command('mkdir /root/algorithms')
        client.exec_command('mkdir /root/builds')
        client.exec_command('mkdir /root/inputs')
        client.exec_command('mkdir /root/util')
        # consumer loop
        while True:
            algorithm, inp = await self.queue.get()
            # if 'hangs' in inp:
            #     print('skipped hang: {}'.format(inp))
            #     self.queue.task_done()
            #     continue
            # elif 'crashes' in inp:
            #     print('skipped crash: {}'.format(inp))
            #     self.queue.task_done()
            #     continue
            sys.stdout.write("running {} with input {}\n".format(algorithm, inp))
            sys.stdout.flush()
            async with self.fh_lock:
                sftp = client.open_sftp()
                # check whether the algorithm is available
                if algorithm not in sftp.listdir('algorithms'):
                    alg_path = join(self.aft.alg_dir, algorithm)
                    if isfile(alg_path):
                        sftp.put(
                                join(self.aft.alg_dir, algorithm),
                                'algorithms/{}'.format(algorithm))
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
                # check whether auxiliary scripts are in place
                if 'dispatch.py' not in sftp.listdir('util'):
                    sftp.put(
                            join(self.aft.aft_dir, 'dispatch.py'),
                            'util/dispatch.py'
                            )
                if isfile(self.aft.config[algorithm]['build string']):
                    build_file = os.path.split(self.aft.config[algorithm]['build string'])[-1]
                    if build_file not in sftp.listdir('/root/util'):
                        sftp.put(
                                self.aft.config[algorithm]['build string'],
                                'util/{}'.format(build_file)
                                )
                else:
                    build_file = self.aft.config[algorithm]['build string']
                # check whether input is available in container
                if inp not in sftp.listdir('inputs'):
                    # move input to container
                    sftp.put(
                            join(self.aft.queue_dir, inp),
                            'inputs/{}'.format(inp)
                            )
                sftp.close()
            stdin, stdout, stderr = client.exec_command(
                    """python3 util/dispatch.py --mode run \
                        --alg {} --imode {} --omode {} \
                        --exec-args "{}" --build-args "{}" \
                        --file {} --timeout {}""".format(
                            algorithm,
                            self.aft.config[algorithm]['input format'],
                            self.aft.config[algorithm]['output format'],
                            self.aft.config[algorithm]['execution string'],
                            build_file,
                            inp,
                            self.aft.config['global']['execution time limit']
                            )
                        )
            try:
                json_data = json.load(stdout)
            except JSONDecodeError:
                print(output)
            # log the algorithm and input
            async with self.ressource_log_lock:
                try:
                    self.ressource_log[algorithm]
                except KeyError:
                    self.ressource_log[algorithm] = {}
                self.ressource_log[algorithm][inp] = json_data['usage']
            async with self.fh_lock:
                if json_data['failed']:
                    # write to crashes
                    if not json_data['stderr']:
                        json_data['stderr'] = "";
                    crash_file = self.aft.fh.get_crash_handle(algorithm, inp)
                    crash_file.write('\n'.join(json_data['stderr']))
                    crash_file.close()
                else:
                    # write outputs to tmp
                    if not json_data['stdout']:
                        json_data['stdout'] = ""
                    tmp_file = self.aft.fh.get_tmp_handle(algorithm, inp)
                    tmp_file.write('\n'.join(json_data['stdout']))
                    tmp_file.close()
            self.queue.task_done()
