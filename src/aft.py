import sys
import signal
import getopt
import shlex
import time

import ssh_util
import aft_config as cfg

from os                 import listdir
from os.path            import dirname, join, realpath
from pathlib            import Path
from subprocess         import Popen, PIPE
from filestruct_handler import FST_HANDLER
from consumer_server    import Consumer_Server
from fuzzing_server     import Fuzzing_Server
from diff_server        import Diff_Server


class Aftstruct():

    def __init__(self):
        self.aft_dir = dirname(realpath(__file__))
        self.input_dir = ""
        self.output_dir = ""
        self.alg_dir = ""
        self.queue_dir = ""
        self.config = None
        self.rsa_id = None
        self.rsa_pub = None
        self.clients = None

    def init_filehandler(self):
        # initialize the file handler and directories
        self.fh = FST_HANDLER(
                self.input_dir,
                self.output_dir,
                self.alg_dir
                )
        self.fh.init_dir_structure()
        self.queue_dir = join(self.output_dir, 'queue')

    def check_config(self):
        # check config and/or generate new
        if self.config is None:
            self.config = cfg.generate_config(self.alg_dir)
        else:
            self.config = cfg.check_config(
                    self.config,
                    self.alg_dir
                    )

    def get_docker_image(self):
        sys.stdout.write('generating docker image...')
        sys.stdout.flush()
        self.rsa_id, self.rsa_pub = ssh_util.gen_rsa_key('aft_container_key')
        self.dockerfile = ssh_util.gen_dockerfile(
                self.rsa_id,
                self.config['global']['dependencies']
                )
        p = Popen(
                shlex.split('docker build -t aft:1.0 -'),
                stdin=PIPE,
                stdout=PIPE,
                stderr=PIPE
                )
        out, err = p.communicate(self.dockerfile.encode())
        if p.returncode != 0:
            sys.exit(1)
        sys.stdout.write(' done\n')
        sys.stdout.flush()

    def get_clients(self):
        if not self.clients is None:
            return
        # create clients
        print('Establishing connection to clients...', end='')
        self.clients = ssh_util.get_clients(
                self.config['global']['workers'],
                self.rsa_pub,
                self.config['global']['host keys'],
                self.config['global']['dependencies']
                )
        print(' done')

    def shutdown_clients(self):
        # shut down clients and stop docker containers
        print('Shutting down clients...', end='')
        ssh_util.shutdown_clients(
                self.clients,
                self.config['global']['workers']
                )
        print(' done')

    def interrupt_handler(self, sig, frame):
        print("received {}. shutting down".format(sig))
        sys.exit(0)

    def interrupt_handler_fz(self, sig, frame):
        # cancel workers
        print("received {}. shutting down".format(sig))
        for worker in self.fz_server.workers:
            worker.cancel()
        # shutdown clients
        self.shutdown_clients()
        sys.exit(0)

    def interrupt_handler_cs(self, sig, frame):
        print("received {}. shutting down".format(sig))
        # cancel workers
        for worker in self.cs_server.workers:
            worker.cancel()
        # shutdown clients
        self.shutdown_clients()
        sys.exit(0)

    def interrupt_handler_df(self, sig, frame):
        print("received {}. shutting down".format(sig))
        # cancel workers
        for worker in self.df_server.workers:
            worker.cancel()
        # empty queue
        sys.exit(0)

    def generate_html(self):

        # load templates
        contents = ""
        with open(join(
            Path(self.aft_dir).parent,
            'templates',
            'index.template'
            )) as index_template:
                contents = index_template.read()
        alg_template = ""
        with open(join(
            Path(self.aft_dir).parent,
            'templates',
            'index.algorithm.template'
            )) as index_template:
                alg_template = index_template.read()

        # general info
        # all queue entries
        num_q = len(listdir(join(
            self.output_dir,
            'queue'
            )))
        # number of outputs by gt
        num_out_gt = len(listdir(join(
            self.output_dir,
            self.config['global']['ground truth'],
            'tmp'
            )))
        # number of crashes by gt
        num_crash_gt = len(listdir(join(
            self.output_dir,
            self.config['global']['ground truth'],
            'crashes'
            )))

        algorithm_html = []
        # per algorithm
        for alg in listdir(self.alg_dir):
            if alg == self.config['global']['ground truth']:
                continue
            num_false_alg = len(listdir(join(
                self.output_dir,
                alg,
                'false'
                )))
            num_crashes_alg = len(listdir(join(
                self.output_dir,
                alg,
                'crashes'
                )))
            algorithm_html.append(
                    alg_template.format(
                        alg,
                        num_false_alg,
                        num_crashes_alg,
                        ))


        contents = contents.format(
                len(listdir(self.input_dir)),
                num_q,
                num_out_gt,
                num_crash_gt,
                "\n".join(algorithm_html)
                )
        with open(
                join(self.output_dir, 'index.html'),
                'w'
                ) as html_file:
            html_file.write(contents)


def usage():
    print("usage: aft [-i | --input] DIRECTORY [-o | --output] DIRECTORY [-a | --algs] DIRECTORY [-c | --config] FILE")


def main(argv):

    aft = Aftstruct()
    signal.signal(signal.SIGINT, aft.interrupt_handler)

    opts = "hi:o:a:c:"
    l_opts = [
            "help",
            "input=",
            "output=",
            "alg=",
            "config="]
    try:
        opts, args = getopt.getopt(argv, opts, l_opts)
    except getopt.GetoptError as err:
        print(err)
        usage()
        sys.exit(2)
    for opt, arg in opts:
        if opt in ('-h', '--help'):
            usage()
            sys.exit(0)
        elif opt in ('-i', '--input'):
            aft.input_dir = arg
        elif opt in ('-o', '--output'):
            aft.output_dir = arg
        elif opt in ('-a', '--alg'):
            aft.alg_dir = arg
        elif opt in ('-c', '--config'):
            aft.config = arg
        else:
            usage()
            sys.exit(1)

    # initialize the file handler and directories
    aft.init_filehandler()

    # check config and/or generate new
    aft.check_config()

    # generate docker image
    aft.get_docker_image()

    # create clients
    aft.get_clients()

    # afl stuff goes here
    a = time.perf_counter()
    aft.fz_server = Fuzzing_Server(aft)
    signal.signal(signal.SIGINT, aft.interrupt_handler_fz)
    aft.fz_server.run()
    b = time.perf_counter()
    print(f"Time used for fuzzing was {b-a:0.4f}s")

    # automatic execution of the algorithms
    aft.cs_server = Consumer_Server(aft)
    signal.signal(signal.SIGINT, aft.interrupt_handler_cs)
    aft.cs_server.run()

    # shut down clients and stop/rm docker containers
    aft.shutdown_clients()

    # diff module
    aft.df_server = Diff_Server(aft)
    signal.signal(signal.SIGINT, aft.interrupt_handler_df)
    aft.df_server.run()

    print('Generating index.html...', end='')
    aft.generate_html()
    print('done')


if __name__ == "__main__":
        main(sys.argv[1:])

