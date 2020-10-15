import hashlib
import os
import shlex
import shutil
import stat

from os import sep, listdir, makedirs, remove
from os.path import join, isfile


class FST_HANDLER:

    def __init__(self, input_dir, output_dir, alg_dir):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.queue = join(output_dir, "queue")
        self.alg_dir = alg_dir

    def get_in(self):
        return self.input_dir

    def get_out(self):
        return self.output_dir

    def get_alg(self):
        return self.alg_dir

    def get_queue(self):
        return self.queue

    def get_alg_dir(self, algorithm):
        alg_dir = join(self.alg_dir, algorithm)
        if isdir(alg_dir):
            return alg_dir
        else:
            return None

    # make all directories for the algorithms
    def init_dir_structure(self):
        algorithms = [f for f in listdir(self.alg_dir)]
        makedirs(
                self.queue,
                exist_ok=True
                )

        dirs = ["tmp", "crashes", "false"]
        for a in algorithms:
            for d in dirs:
                makedirs(
                        join(self.output_dir, a, d),
                        exist_ok=True
                        )


    # take file handle and write it to the correct location
    # algorithm : String (Name of algorithm)
    # input_name: String (Name of the used input)
    # content   : List of String (Will be written)
    def get_crash_handle(self, algorithm, input_name):
        path = join(self.output_dir, algorithm, 'crashes', input_name)
        out_file = open(path, 'w+')
        return out_file


    # take file handle and write it to the correct location
    # algorithm : String (Name of algorithm)
    # input_name: String (Name of the used input)
    # content   : List of String (will be written)
    def get_tmp_handle(self, algorithm, input_name):
        path = join(self.output_dir, algorithm, 'tmp', input_name)
        out_file = open(path, 'w+')
        return out_file

    # move a file from the tmp directory to the false directory
    # algorithm     : String (Name of algorithm)
    # output_name   : String (Name of the used input)
    def put_false(self, algorithm, output_name):
        tmp_path = join(self.output_dir, algorithm, 'tmp', output_name)
        f_path = join(self.output_dir, algorithm, 'false', output_name)
        os.rename(tmp_path, f_path)


    # move files form algorithm/tmp/queue into the main queue and rename them
    # algorithm : String (Algorithm used to generate the input)
    def gen_names(self, algorithm):
        directories = ['queue', 'crashes', 'hangs']
        for directory in directories:
            path = join(self.output_dir, algorithm, 'tmp', directory)
            files = listdir(path)
            for f in files:
                if f[:2] != 'id':
                    continue
                f_path = join(path, f)
                name = self.gen_name(f, algorithm, directory)
                os.rename(
                        join(f_path),
                        join(
                            self.output_dir,
                            'queue',
                            name
                            )
                        )
            # clean up tmp
            shutil.rmtree(path)


    # generate a name for an input to store it in the queue
    # input_name: String (Name of the input file: initial or from afl++ )
    # algorithm : String (Name of the algorithm used to generate the input)
    def gen_name(self, input_name, algorithm, directory):
        name = input_name.split(',')[:3]
        name = ",".join(name)
        name = algorithm + '-' + directory + '-' + name
        return name

    # remove redundant inputs from the queue
    # hash all files in the queue and keep only first of each hash string
    def queue_remove_duplicates(self):
        # maximum block size for sha1
        BLOCKSIZE=64
        hashdict = {}
        rev_hashdict = {}
        inputs = listdir(self.get_queue())

        # generate hashes for all instances of inputs
        for inp in inputs:
            hasher = hashlib.sha1()
            with open(
                    join(self.get_queue(), inp),
                    'rb'
                    ) as file_handle:
                buf = file_handle.read(BLOCKSIZE)
                while len(buf) > 0:
                    hasher.update(buf)
                    buf = file_handle.read(BLOCKSIZE)
            hash_str = hasher.hexdigest()
            if not hash_str in hashdict:
                hashdict[hash_str] = inp
                rev_hashdict[inp] = hash_str

        # remove duplicates
        for inp in inputs:
            if not inp in rev_hashdict:
                remove(
                    join(self.get_queue(), inp)
                    )

