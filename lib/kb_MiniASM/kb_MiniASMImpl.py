# -*- coding: utf-8 -*-
#BEGIN_HEADER
# The header block is where all import statements should live
from __future__ import print_function
import os
import re
import uuid
from pprint import pformat
from pprint import pprint
from biokbase.workspace.client import Workspace as workspaceService
import requests
import json
import psutil
import subprocess
import numpy as np
from ReadsUtils.ReadsUtilsClient import ReadsUtils
from ReadsUtils.baseclient import ServerError
from AssemblyUtil.AssemblyUtilClient import AssemblyUtil
from KBaseReport.KBaseReportClient import KBaseReport
from KBaseReport.baseclient import ServerError as _RepError
from kb_quast.kb_quastClient import kb_quast
from kb_quast.baseclient import ServerError as QUASTError
from kb_ea_utils.kb_ea_utilsClient import kb_ea_utils
import time

class ShockException(Exception):
    pass

#END_HEADER


class kb_MiniASM:
    '''
    Module Name:
    kb_MiniASM

    Module Description:
    A KBase module: kb_MiniASM
A simple wrapper for MiniASM Assembler
https://github.com/lh3/miniasm
    '''

    ######## WARNING FOR GEVENT USERS ####### noqa
    # Since asynchronous IO can lead to methods - even the same method -
    # interrupting each other, you must be *very* careful when using global
    # state. A method could easily clobber the state set by another while
    # the latter method is running.
    ######################################### noqa
    VERSION = "0.0.1"
    GIT_URL = "https://github.com/ugswork/kb_MiniASM.git"
    GIT_COMMIT_HASH = "d13742460e84239e2fc72c114f668525ed0de1b9"

    #BEGIN_CLASS_HEADER
    # Class variables and functions can be defined in this block
    DISABLE_MINIMAP_OUTPUT = False  # should be False in production
    DISABLE_MINIASM_OUTPUT = False  # should be False in production

    PARAM_IN_WS = 'workspace_name'
    PARAM_IN_LIB = 'read_libraries'
    PARAM_IN_CS_NAME = 'output_contigset_name'
    PARAM_IN_MIN_CONTIG = 'min_contig'
    PARAM_IN_OPT_ARGS = 'opt_args'
    PARAM_IN_MIN_SPAN = 'min_span'
    PARAM_IN_MIN_COVERAGE = 'min_coverage'
    PARAM_IN_MIN_OVERLAP = 'min_overlap'

    INVALID_WS_OBJ_NAME_RE = re.compile('[^\\w\\|._-]')
    INVALID_WS_NAME_RE = re.compile('[^\\w:._-]')

    URL_WS = 'workspace-url'
    URL_SHOCK = 'shock-url'
    URL_KB_END = 'kbase-endpoint'

    TRUE = 'true'
    FALSE = 'false'

    # code taken from kb_SPAdes

    def log(self, message, prefix_newline=False):
        print(('\n' if prefix_newline else '') +
              str(time.time()) + ': ' + str(message))


    def exec_minimap(self, input_reads, outdir):

        if not os.path.exists(outdir):
            os.makedirs(outdir)

        minimap_outfile = os.path.join(outdir, 'minimap-output.gz')

        minimap_cmd1 = ['minimap', '-Sw5', '-L100', '-m0', '-t8',
                        input_reads['fwd_file'], input_reads['fwd_file']]

        minimap_cmd2 = ['gzip', '-1']

        print("minimap CMD:  " + str(minimap_cmd1) + str(minimap_cmd2) + "  outfile: " + minimap_outfile)
        self.log(minimap_cmd1)
        self.log(minimap_cmd2)

        minimap_of = open(minimap_outfile, 'wb')

        if self.DISABLE_MINIMAP_OUTPUT:
            with open(os.devnull, 'w') as null:
                p1 = subprocess.Popen(minimap_cmd1, cwd=self.scratch, shell=False,
                                      stdout=subprocess.PIPE, stderr=null)

                p2 = subprocess.Popen(minimap_cmd2, cwd=self.scratch, shell=False,
                                      stdin=p1.stdout, stdout=minimap_of, close_fds=True, stderr=null)
        else:

            p1 = subprocess.Popen(minimap_cmd1, cwd=self.scratch, shell=False,
                                  stdout=subprocess.PIPE)

            p2 = subprocess.Popen(minimap_cmd2, cwd=self.scratch, shell=False,
                                  stdin=p1.stdout, stdout=minimap_of, close_fds=True)

        retcode1 = p1.wait()
        p1.stdout.close()

        if p1.returncode != 0:
            raise ValueError('Error running minimap, return code: ' +
                             str(retcode1) + '\n')

        retcode2 = p2.wait()

        if p2.returncode != 0:
            raise ValueError('Error running gzip, return code: ' +
                             str(retcode2) + '\n')

        return minimap_outfile


    def exec_MiniASM(self, reads_data, params_in, outdir):

        #threads = psutil.cpu_count() * self.THREADS_PER_CORE

        if not os.path.exists(outdir):
            os.makedirs(outdir)

        # The fq2fa can only be run on a single library
        # The library must be paired end.

        if len(reads_data) > 1:  #or reads_data[0]['type'] != 'paired':
            error_msg = 'MiniASM assembly requires that one and ' + \
                            'only one paired end library as input.'
            if len(reads_data) > 1:
                error_msg += ' ' + str(len(reads_data)) + \
                                 ' libraries detected.'
            raise ValueError(error_msg)

        print("LENGTH OF READSDATA IN EXEC: " + str(len(reads_data)))
        print("READS DATA: ")
        pprint(reads_data)
        pprint("=============  END OF READS DATA  ===============")

        # first convert input reads_data from fastq to paf
        # output of minimap saved in minimap_outfile

        minimap_outfile = self.exec_minimap(reads_data[0], outdir)

        miniasm_gfa_outfile = os.path.join(outdir, 'MiniASM_output.gfa')

        # use minimap_outfile as input to MiniASM assembler
        # output file from the assembler saved in miniasm_gfa_outfile

        miniasm_cmd = ['miniasm', '-f', reads_data[0]['fwd_file'],
                       minimap_outfile]

        if self.PARAM_IN_OPT_ARGS in params_in and params_in[self.PARAM_IN_OPT_ARGS] is not None:
            oargs = params_in[self.PARAM_IN_OPT_ARGS]

            if int(oargs[self.PARAM_IN_MIN_SPAN]) > 0:
                miniasm_cmd.append('-s')
                miniasm_cmd.append(str(oargs[self.PARAM_IN_MIN_SPAN]))

            if int(oargs[self.PARAM_IN_MIN_COVERAGE]) > 0:
                miniasm_cmd.append('-c')
                miniasm_cmd.append(str(oargs[self.PARAM_IN_MIN_COVERAGE]))

            if int(oargs[self.PARAM_IN_MIN_OVERLAP]) > 0:
                miniasm_cmd.append('-o')
                miniasm_cmd.append(str(oargs[self.PARAM_IN_MIN_OVERLAP]))

        print("\nMiniASM CMD:     " + str(miniasm_cmd) + "Outfile: " + miniasm_gfa_outfile)
        self.log(miniasm_cmd)

        miniasm_gfa_of = open(miniasm_gfa_outfile, 'wb')

        if self.DISABLE_MINIASM_OUTPUT:
            with open(os.devnull, 'w') as null:
                p = subprocess.Popen(miniasm_cmd, cwd=self.scratch, shell=False,
                                     stdout=miniasm_gfa_of, close_fds=True, stderr=null)
        else:
            p = subprocess.Popen(miniasm_cmd, cwd=self.scratch, shell=False, stdout=miniasm_gfa_of, close_fds=True)
        retcode = p.wait()

        self.log('Return code: ' + str(retcode))
        if p.returncode != 0:
            raise ValueError('Error running MiniASM, return code: ' +
                             str(retcode) + '\n')

        miniasm_fasta_outfile = os.path.join(outdir, 'MiniASM_fasta_output.fa')
        miniasm_fa_of = open(miniasm_fasta_outfile, 'wb')
        gfa2fa_cmd = 'awk \'/^S/{print ">"$2"\\n"$3}\'  ' + miniasm_gfa_outfile + ' | fold '

        if self.DISABLE_MINIASM_OUTPUT:
            with open(os.devnull, 'w') as null:
                p = subprocess.Popen(gfa2fa_cmd, cwd=self.scratch, shell=False,
                                     stdout=miniasm_fa_of, close_fds=True, stderr=null)
        else:
            p = subprocess.Popen(gfa2fa_cmd, cwd=self.scratch, shell=True, stdout=miniasm_fa_of, close_fds=True)
        retcode = p.wait()

        self.log('Return code: ' + str(retcode))
        if p.returncode != 0:
            raise ValueError('Error running gfa2fa, return code: ' +
                             str(retcode) + '\n')

        return miniasm_fasta_outfile


    # adapted from
    # https://github.com/kbase/transform/blob/master/plugins/scripts/convert/trns_transform_KBaseFile_AssemblyFile_to_KBaseGenomes_ContigSet.py
    # which was adapted from an early version of
    # https://github.com/kbase/transform/blob/master/plugins/scripts/upload/trns_transform_FASTA_DNA_Assembly_to_KBaseGenomes_ContigSet.py
    def load_stats(self, input_file_name):
        self.log('Starting conversion of FASTA to KBaseGenomeAnnotations.Assembly')
        self.log('Building Object.')
        if not os.path.isfile(input_file_name):
            raise Exception('The input file name {0} is not a file!'.format(
                input_file_name))
        with open(input_file_name, 'r') as input_file_handle:
            contig_id = None
            sequence_len = 0
            fasta_dict = dict()
            first_header_found = False
            # Pattern for replacing white space
            pattern = re.compile(r'\s+')
            for current_line in input_file_handle:
                if (current_line[0] == '>'):
                    # found a header line
                    # Wrap up previous fasta sequence
                    if not first_header_found:
                        first_header_found = True
                    else:
                        fasta_dict[contig_id] = sequence_len
                        sequence_len = 0
                    fasta_header = current_line.replace('>', '').strip()
                    try:
                        contig_id = fasta_header.strip().split(' ', 1)[0]
                    except:
                        contig_id = fasta_header.strip()
                else:
                    sequence_len += len(re.sub(pattern, '', current_line))
        # wrap up last fasta sequence, should really make this a method
        if not first_header_found:
            raise Exception("There are no contigs in this file")
        else:
            fasta_dict[contig_id] = sequence_len
        return fasta_dict


    def load_report(self, input_file_name, params, wsname):
        fasta_stats = self.load_stats(input_file_name)
        lengths = [fasta_stats[contig_id] for contig_id in fasta_stats]

        assembly_ref = params[self.PARAM_IN_WS] + '/' + params[self.PARAM_IN_CS_NAME]

        report = ''
        report += 'Assembly saved to: ' + assembly_ref + '\n'
        report += 'Assembled into ' + str(len(lengths)) + ' contigs.\n'
        report += 'Avg Length: ' + str(sum(lengths) / float(len(lengths))) + \
            ' bp.\n'

        # compute a simple contig length distribution
        bins = 10
        counts, edges = np.histogram(lengths, bins)  # @UndefinedVariable
        report += 'Contig Length Distribution (# of contigs -- min to max ' +\
            'basepairs):\n'
        for c in range(bins):
            report += '   ' + str(counts[c]) + '\t--\t' + str(edges[c]) +\
                ' to ' + str(edges[c + 1]) + ' bp\n'
        print('Running QUAST')
        kbq = kb_quast(self.callbackURL)
        quastret = kbq.run_QUAST({'files': [{'path': input_file_name,
                                             'label': params[self.PARAM_IN_CS_NAME]}]})
        print('Saving report')
        kbr = KBaseReport(self.callbackURL)
        report_info = kbr.create_extended_report(
            {'message': report,
             'objects_created': [{'ref': assembly_ref, 'description': 'Assembled contigs'}],
             'direct_html_link_index': 0,
             'html_links': [{'shock_id': quastret['shock_id'],
                             'name': 'report.html',
                             'label': 'QUAST report'}
                            ],
             'report_object_name': 'kb_MiniASM-_report_' + str(uuid.uuid4()),
             'workspace_name': params['workspace_name']
            })
        reportName = report_info['name']
        reportRef = report_info['ref']
        return reportName, reportRef


    def make_ref(self, object_info):
        return str(object_info[6]) + '/' + str(object_info[0]) + \
            '/' + str(object_info[4])


    def process_params(self, params):
        if (self.PARAM_IN_WS not in params or
                not params[self.PARAM_IN_WS]):
            raise ValueError(self.PARAM_IN_WS + ' parameter is required')
        if self.INVALID_WS_NAME_RE.search(params[self.PARAM_IN_WS]):
            raise ValueError('Invalid workspace name ' +
                             params[self.PARAM_IN_WS])
        if self.PARAM_IN_LIB not in params:
            raise ValueError(self.PARAM_IN_LIB + ' parameter is required')
        if type(params[self.PARAM_IN_LIB]) != list:
            raise ValueError(self.PARAM_IN_LIB + ' must be a list')
        if not params[self.PARAM_IN_LIB]:
            raise ValueError('At least one reads library must be provided')
        # for l in params[self.PARAM_IN_LIB]:
        #    print("PARAM_IN_LIB : " + str(l))
        #    if self.INVALID_WS_OBJ_NAME_RE.search(l):
        #        raise ValueError('Invalid workspace object name ' + l)
        if (self.PARAM_IN_CS_NAME not in params or
                not params[self.PARAM_IN_CS_NAME]):
            raise ValueError(self.PARAM_IN_CS_NAME + ' parameter is required')
        if self.INVALID_WS_OBJ_NAME_RE.search(params[self.PARAM_IN_CS_NAME]):
            raise ValueError('Invalid workspace object name ' +
                             params[self.PARAM_IN_CS_NAME])

        if self.PARAM_IN_MIN_CONTIG in params:
            if not isinstance(params[self.PARAM_IN_MIN_CONTIG], int):
                raise ValueError('min_contig must be of type int')

        if self.PARAM_IN_OPT_ARGS in params and params[self.PARAM_IN_OPT_ARGS] is not None:
            oargs = params[self.PARAM_IN_OPT_ARGS]
            if not isinstance(oargs[self.PARAM_IN_MIN_SPAN], int):
                raise ValueError('min span must be of type int')
            if not isinstance(oargs[self.PARAM_IN_MIN_COVERAGE], int):
                raise ValueError('min coverage must be of type int')
            if not isinstance(oargs[self.PARAM_IN_MIN_OVERLAP], int):
                raise ValueError('min overlap must be of type int')

    #END_CLASS_HEADER

    # config contains contents of config file in a hash or None if it couldn't
    # be found
    def __init__(self, config):
        #BEGIN_CONSTRUCTOR
        self.callbackURL = os.environ['SDK_CALLBACK_URL']
        self.log('Callback URL: ' + self.callbackURL)
        self.workspaceURL = config[self.URL_WS]
        self.shockURL = config[self.URL_SHOCK]
        self.catalogURL = config[self.URL_KB_END] + '/catalog'
        self.scratch = os.path.abspath(config['scratch'])
        if not os.path.exists(self.scratch):
            os.makedirs(self.scratch)
        #END_CONSTRUCTOR
        pass


    def run_MiniASM(self, ctx, params):
        """
        Run MiniASM on paired end libraries
        :param params: instance of type "MiniASM_Params" -> structure:
           parameter "workspace_name" of String, parameter "read_libraries"
           of list of type "paired_end_lib" (The workspace object name of a
           PairedEndLibrary file, whether of the KBaseAssembly or KBaseFile
           type.), parameter "output_contigset_name" of String, parameter
           "min_contig" of Long, parameter "opt_args" of type "opt_args_type"
           (Input parameters for running MiniASM. string workspace_name - the
           name of the workspace from which to take input and store output.
           list<paired_end_lib> read_libraries - Illumina PairedEndLibrary
           files to assemble. string output_contigset_name - the name of the
           output contigset) -> structure: parameter "min_span" of Long,
           parameter "min_coverage" of Long, parameter "min_overlap" of Long
        :returns: instance of type "MiniASM_Output" (Output parameters for
           MiniASM run. string report_name - the name of the
           KBaseReport.Report workspace object. string report_ref - the
           workspace reference of the report.) -> structure: parameter
           "report_name" of String, parameter "report_ref" of String
        """
        # ctx is the context object
        # return variables are: output
        #BEGIN run_MiniASM
        
        print("===================  IN run_MiniASM")

        # A whole lot of this is adapted or outright copied from
        # https://github.com/msneddon/MEGAHIT
        self.log('Running run_MiniASM with params:\n' + pformat(params))

        token = ctx['token']

        # the reads should really be specified as a list of absolute ws refs
        # but the narrative doesn't do that yet
        self.process_params(params)

        # get absolute refs from ws
        wsname = params[self.PARAM_IN_WS]
        print("Workspace name: " + wsname)
        obj_ids = []
        for r in params[self.PARAM_IN_LIB]:
            obj_ids.append({'ref': r if '/' in r else (wsname + '/' + r)})
        ws = workspaceService(self.workspaceURL, token=token)
        ws_info = ws.get_object_info_new({'objects': obj_ids})
        reads_params = []

        reftoname = {}
        for wsi, oid in zip(ws_info, obj_ids):
            ref = oid['ref']
            reads_params.append(ref)
            obj_name = wsi[1]
            reftoname[ref] = wsi[7] + '/' + obj_name

        readcli = ReadsUtils(self.callbackURL, token=ctx['token'])

        typeerr = ('Supported types: KBaseFile.SingleEndLibrary ' +
                   'KBaseFile.PairedEndLibrary ' +
                   'KBaseAssembly.SingleEndLibrary ' +
                   'KBaseAssembly.PairedEndLibrary')
        try:
            reads = readcli.download_reads({'read_libraries': reads_params,
                                            'interleaved': 'true',
                                            'gzipped': None
                                            })['files']
        except ServerError as se:
            self.log('logging stacktrace from dynamic client error')
            self.log(se.data)
            if typeerr in se.message:
                prefix = se.message.split('.')[0]
                raise ValueError(
                    prefix + '. Only the types ' +
                    'KBaseAssembly.PairedEndLibrary ' +
                    'and KBaseFile.PairedEndLibrary are supported')
            else:
                raise

        self.log('Got reads data from converter:\n' + pformat(reads))

        reads_data = []
        for ref in reads:
            reads_name = reftoname[ref]
            f = reads[ref]['files']
            print ("REF:" + str(ref))
            print ("READS REF:" + str(reads[ref]))
            seq_tech = reads[ref]["sequencing_tech"]
            if f['type'] == 'interleaved':
                reads_data.append({'fwd_file': f['fwd'], 'type':'paired',
                                   'seq_tech': seq_tech})
            elif f['type'] == 'paired':
                reads_data.append({'fwd_file': f['fwd'], 'rev_file': f['rev'],
                                   'type':'paired', 'seq_tech': seq_tech})
            elif f['type'] == 'single':
                reads_data.append({'fwd_file': f['fwd'], 'type':'single',
                                   'seq_tech': seq_tech})
            else:
                raise ValueError('Something is very wrong with read lib' + reads_name)

        print("READS_DATA: ")
        pprint(reads_data)
        print("============================   END OF READS_DATA: ")

        outdir = os.path.join(self.scratch, 'MiniASM_dir')

        miniasm_outfile = self.exec_MiniASM(reads_data, params, outdir)
        self.log('MiniASM output dir: ' + miniasm_outfile)

        # parse the output and save back to KBase

        output_contigs = miniasm_outfile

        min_contig_len = 0

        if self.PARAM_IN_MIN_CONTIG in params and params[self.PARAM_IN_MIN_CONTIG] is not None:
            if (int(params[self.PARAM_IN_MIN_CONTIG])) > 0:
                min_contig_len = int(params[self.PARAM_IN_MIN_CONTIG])

        self.log('Uploading FASTA file to Assembly')
        assemblyUtil = AssemblyUtil(self.callbackURL, token=ctx['token'], service_ver='dev')

        assemblyUtil.save_assembly_from_fasta({'file': {'path': output_contigs},
                                               'workspace_name': wsname,
                                               'assembly_name': params[self.PARAM_IN_CS_NAME],
                                               'min_contig_length': min_contig_len
                                               })

        report_name, report_ref = self.load_report(output_contigs, params, wsname)

        output = {'report_name': report_name,
                  'report_ref': report_ref
                  }

        #END run_MiniASM

        # At some point might do deeper type checking...
        if not isinstance(output, dict):
            raise ValueError('Method run_MiniASM return value ' +
                             'output is not type dict as required.')
        # return the results
        return [output]
    def status(self, ctx):
        #BEGIN_STATUS
        returnVal = {'state': "OK",
                     'message': "",
                     'version': self.VERSION,
                     'git_url': self.GIT_URL,
                     'git_commit_hash': self.GIT_COMMIT_HASH}
        del ctx  # shut up pep8
        #END_STATUS
        return [returnVal]
