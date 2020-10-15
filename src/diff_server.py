import os
import sys

from os         import listdir
from os.path    import join


class Diff_Server():

    def __init__(self, aft):
        self.aft = aft


    def run(self):
        print('Diff running')
        # generate list of algorithms
        algorithms = os.listdir(self.aft.output_dir)
        algorithms.remove('queue')
        if self.aft.config['global']['ground truth'] not in algorithms:
            sys.stderr.write("No outputs of ground truth found. Aborting...")
            sys.stderr.flush
            sys.exit(1)

        # load and store outputs from ground truth
        reference_dict = {}
        gt_path = join(
            self.aft.output_dir,
            self.aft.config['global']['ground truth'],
            'tmp'
            )
        for output in listdir(gt_path):
            with open(join(gt_path, output), 'r') as data:
                reference_dict[output] = data.read()
        del gt_path

        # compare outputs of algorithms to reference
        algorithms.remove(self.aft.config['global']['ground truth'])
        for algorithm in algorithms:
            alg_path = join(
                    self.aft.output_dir,
                    algorithm,
                    'tmp'
                    )
            for output in listdir(alg_path):
                with open(join(alg_path, output), 'r') as data:
                    alg_output = data.read()
                    try:
                        if alg_output != reference_dict[output]:
                            self.aft.fh.put_false(algorithm, output)
                    except KeyError:
                        self.aft.fh.put_false(algorithm, output)
            # clean and remove the tmp directory of algorithm
            for output in listdir(alg_path):
                os.remove(join(alg_path, output))
            os.rmdir(alg_path)
        return
