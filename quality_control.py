
import yaml
import os
import os.path
import subprocess
import sys
from subprocess import Popen, PIPE, STDOUT
import shutil
from os.path import exists

class workflow_manager:
    required_configurations = ['directory_of_datasets', 'single_or_multiple_datasets']


    def __init__(self, configuration_file_path):
        self.configuration_file_path = configuration_file_path
        self.config_dict = self.get_configurations()
        self.run_datasets()


    def get_configurations(self): # loads yaml file and converts it into one single dictionary with list of configurations unnested
        with open(self.configuration_file_path, "r") as file:
            yaml_dict = yaml.load(file, Loader=yaml.FullLoader)
            config_dict = {}
            list_of_dicts = [yaml_dict]

            for a_dict in list_of_dicts:
                for key,value in a_dict.items():
                    
                    if isinstance(value, dict) == True:
                        
                        list_of_dicts.append(value)
                    
                    else:

                        config_dict[key] = str(value)
        print(config_dict)

        return config_dict

    def verify_mandatory_configurations(self):
        print("to do")

    def initialise_tools(self):
        
        workflow_tools = workflow_tools(self.configuration_dict)
        summary_tools = summary_tools(self.configuration_dict)

        return workflow_tools, summary_tools

    def run_datasets(self):
        
        directory_of_datasets = self.config_dict['directory_of_datasets']
        if self.config_dict['single_or_multiple_datasets'] == 'single':
            dataset(directory_of_datasets, self.config_dict)

        else:
            list_of_datasets = os.listdir(directory_of_datasets)
            list_of_dataset_paths = ["%s/%s" % (directory_of_datasets, dset) for dset in list_of_datasets]
            
            for path in list_of_dataset_paths:
                dataset(path, self.config_dict)          



class dataset: # dataset object with fastq paths and attributes to be added etc.

    def __init__(self, dataset_path, configuration_dict):
        self.dataset_path = dataset_path
        self.configuration_dict = configuration_dict
        self.initial_fastq_paths, self.fastq_ext = self.get_fastq_paths()
        self.sample_names = self.get_sample_names()
        
        self.host_indices = self.build_genome_indices()
        self.run_workflow()
    
    def run_workflow(self):
        initial_fastqc_directory = f"{self.configuration_dict['output_directory']}/initial_fastqc_results"
        initial_multiqc_directory = f"{self.configuration_dict['output_directory']}initial_multiqc_results"

        self.run_fastqc_and_multiqc(self.initial_fastq_paths, initial_fastqc_directory, initial_multiqc_directory)
        self.run_trimming()
        self.run_merging()
        unaligned_reads = self.run_bowtie_alignment()

        final_fastqc_directory = f"{self.configuration_dict['output_directory']}/final_fastqc_results"
        final_multiqc_directory = f"{self.configuration_dict['output_directory']}/final_multiqc_results"

        self.run_fastqc_and_multiqc(unaligned_reads, final_fastqc_directory, final_multiqc_directory)



    def get_sample_names(self):

        sample_paths_without_ext = [fastq.replace(f"{self.fastq_ext}", "") for fastq in self.initial_fastq_paths]

        sample_names = [path.split("/")[-1] for path in sample_paths_without_ext]
        
        if self.configuration_dict['paired_or_unpaired'] == 'paired':
            sample_names = self.get_pairs(sample_names)
       
        return sample_names

    def get_fastq_paths(self):
        if self.configuration_dict['gzip_compressed'] == 'Y':
            fastq_paths = ["%s/%s" % (self.dataset_path, file) for file in os.listdir(self.dataset_path) if file[-9:] == '.fastq.gz' or file[-6:] == '.fq.gz']
            fastq_ext = ".gz"
        else:
            fastq_paths = ["%s/%s" % (self.dataset_path, file) for file in os.listdir(self.dataset_path) if file[-6:] == '.fastq' or file[-3:] == '.fq']
            fastq_ext = ""
        print(fastq_paths[0])

        if ".fastq" in fastq_paths[0]:
            fastq_ext = ".fastq" + fastq_ext
            print("correct")

        else:
            fastq_ext = ".fq" + fastq_ext

        return fastq_paths, fastq_ext

    def get_pairs(self, list_of_fastqs):
        forward_pair = self.configuration_dict['forward_pair']
        backward_pair = self.configuration_dict['backward_pair']
        unique_fastqs_dict = {}
        for fastq in list_of_fastqs:
            if forward_pair in fastq:
                
                fastq_no_ext = fastq.replace(forward_pair, "")
            
            else:
                
                fastq_no_ext = fastq.replace(backward_pair, "")
            
            if fastq_no_ext not in unique_fastqs_dict.keys():
                
                unique_fastqs_dict[fastq_no_ext] =  fastq

            else:

                if forward_pair in fastq:

                    fastq_names = [fastq, unique_fastqs_dict[fastq_no_ext]]

                else:

                    fastq_names = [unique_fastqs_dict[fastq_no_ext], fastq]

                unique_fastqs_dict[fastq_no_ext] = fastq_names
        
        return unique_fastqs_dict


    def run_fastqc_and_multiqc(self, fastq_files, fastqc_directory, multiqc_directory):

        if os.path.isdir(multiqc_directory) == True and os.path.isdir(fastqc_directory) == True:
            return
        
        os.mkdir(fastqc_directory)
        os.mkdir(multiqc_directory)

        for fastq in fastq_files:
            fastqc_args = ['fastqc', fastq, '-threads', self.configuration_dict['threads'], '-outdir', fastqc_directory]
            subprocess.call(fastqc_args)
        
        multiqc_args = ['multiqc', fastqc_directory, '-o', multiqc_directory]

        subprocess.call(multiqc_args)

   
    def run_trimming(self):
        trimming_directory = f"{self.configuration_dict['output_directory']}/trimmed_fastqs"
        if self.configuration_dict['run_trimming'] == 'N' or self.configuration_dict['run_trimming'] == 'n':
            self.dataset_path = trimming_directory
            print("skipping trimmin")
            return

        
        try:
            os.mkdir(trimming_directory)
        except:
            print("trim dir already there.")
        if self.configuration_dict['paired_or_unpaired'] == 'Y' or self.configuration_dict['paired_or_unpaired'] == 'paired':
            for sample_name,fwd_and_bck in self.sample_names.items():
                
                forward_sample = f"{self.dataset_path}/{fwd_and_bck[0]}{self.fastq_ext}"
                backward_sample = f"{self.dataset_path}/{fwd_and_bck[1]}{self.fastq_ext}"

                trimmed_forward = f"{trimming_directory}/{fwd_and_bck[0]}_trimmed{self.fastq_ext}"
                trimmed_backward = f"{trimming_directory}/{fwd_and_bck[1]}_trimmed{self.fastq_ext}"


                
                trim_galore_args = ['trim_galore', '-q', self.configuration_dict['trim_phred_quality'], '--length', self.configuration_dict['minimum_read_length'], '--trim-n', '--cores', self.configuration_dict['threads'],
                 '--output_dir', trimming_directory, '--paired', forward_sample, backward_sample]
                
                galore_trimmed_forward = f"{trimming_directory}/{fwd_and_bck[0]}_val_1.fq.gz"
                galore_trimmed_backward = f"{trimming_directory}/{fwd_and_bck[1]}_val_2.fq.gz"

                subprocess.call(trim_galore_args)
                try:
                    shutil.move(galore_trimmed_forward, trimmed_forward)
                    shutil.move(galore_trimmed_backward, trimmed_backward)
                except:
                    print("cont.")


            files = os.listdir(self.dataset_path)
            trimmed_files = [file for file in files if "trimmed" in file]


        # trim_galore -q 20 --gzip --paired --length 50 --trim-n --output_dir --cores
        self.dataset_path = trimming_directory

    def run_merging(self):
        merging_directory = f"{self.configuration_dict['output_directory']}/merged_fastqs"
        try:
            os.mkdir(merging_directory)
        except:
            print("merged directory already there.")
        for sample_name,fwd_and_bck in self.sample_names.items():
                
                forward_sample = f"{self.dataset_path}/{fwd_and_bck[0]}_trimmed{self.fastq_ext}"
                backward_sample = f"{self.dataset_path}/{fwd_and_bck[1]}_trimmed{self.fastq_ext}"
                merged_fastq_path = f"{merging_directory}/merged_{sample_name}{self.fastq_ext}"
                unmerged_forward = f"{merging_directory}/unmerged_{sample_name}_1{self.fastq_ext}"
                unmerged_backward = f"{merging_directory}/unmerged_{sample_name}_2{self.fastq_ext}"
                unmerged_path = f"{merging_directory}/unmerged_{sample_name}"
                
                if exists(merged_fastq_path) == True:
                    continue
                
                merge_args = ['NGmerge', '-n', self.configuration_dict['threads'], '-m', self.configuration_dict['minimum_ngmerge_overlap'], '-p', self.configuration_dict['perc_mismatches_allowed_in_overlap'], '-z', '-1', forward_sample, '-2', backward_sample, '-o', merged_fastq_path, '-f', unmerged_path]
                subprocess.call(merge_args)

    def check_for_indices_and_get_host_name(self):
        build_file_extensions = [".1.bt2", ".2.bt2", ".3.bt2", ".4.bt2", ".rev.1.bt2", ".rev.2.bt2"]

        indice_count = 0
        host_indices = []
        for extent in build_file_extensions:
            for file in os.listdir(self.configuration_dict['bowtie_host_directory']):
                print(file)
                if extent in file:
                    indice_count += 1
                    print("hi")
                    if indice_count == 6:
                        host_file_name = file.split("/")[-1].replace(extent, "")
                        print("found all indices")
                        return host_file_name
                    break
        return "No host indices found."

    def build_genome_indices(self):
        
        host_indices = self.check_for_indices_and_get_host_name()
        if host_indices != "No host indices found.":
            return host_indices


        files_in_dir = os.listdir(self.configuration_dict['bowtie_host_directory'])
        fastas_in_dir = [f"{self.configuration_dict['bowtie_host_directory']}/{fastq}" for fastq in files_in_dir if fastq[-3:] == 'fna' or fastq[-5:] == 'fasta']

        fasta_comma_indented_string = ""
        if len(fastas_in_dir) == 1:
            fasta_comma_indented_string = fastas_in_dir[0]
        else:   
            for fasta in fastas_in_dir:
                fasta_comma_indented_string = f"{fasta_comma_indented_string},{fasta}"


        bowtie_args = ['bowtie2-build', '--threads', self.configuration_dict['threads'], fasta_comma_indented_string, self.configuration_dict['bowtie_host_directory']]

        subprocess.call(bowtie_args)

        host_indices = self.check_for_indices_and_get_host_name()
        if host_indices == "No host indices found.":
            print("bowtie 2 build fail.")
            exit()
        return host_indices

    def run_bowtie_alignment(self):
        
        bowtie_directory = f"{self.configuration_dict['output_directory']}/bowtie_alignment_directory"
        try:
            os.mkdir(bowtie_directory)
        except:
            print("bowtie dir found")
        
        summary_directory = f"{bowtie_directory}/results_summaries"
        try:
            os.mkdir(summary_directory)
        except:
            print("summary dir found")


        if self.configuration_dict['paired_or_unpaired'] == 'paired':
            fastq_directory = f"{self.configuration_dict['output_directory']}/merged_fastqs"
            files = os.listdir(fastq_directory)
            fastq_paths = [f"{fastq_directory}/{file}" for file in files if f"{self.fastq_ext}" in file]
        else:
            
            fastq_directory = f"{self.configuraiton_dict['output_directory']}/trimmed_fastqs"
            fastq_paths = [f"{fastq_directory}/{file}" for file in files if f"{self.fastq_ext}" in file]
        final_unaligned_reads = []
        for fastq in fastq_paths:
            
            fastq_name = fastq.split("/")[-1].replace(self.fastq_ext, "")
            unaligned_reads_path = f"{bowtie_directory}/bowtie_unaligned_{fastq_name}.fastq.gz"
            sam_file = f"{bowtie_directory}/bowtie_unaligned_align_file_{fastq_name}.sam"
            sum_path = f"{summary_directory}/{fastq_name.split('.')[0]}_bowtie_sum.txt"


            if exists(unaligned_reads_path) == True:
                continue

            # bowtie2 -x testing_workflow_script/host_genomes/bovine/bovine --very-sensitive -p 6 -U testing_workflow_script/fastq_directory/merged_fastqs/merged_test_paired_cow.fastq --un testing.fastq
            bowtie_args = ['bowtie2', '-x', f"{self.configuration_dict['bowtie_host_directory']}/{self.host_indices}", '--very-sensitive', '-p', self.configuration_dict['threads'], '-U', fastq, '--un-gz', unaligned_reads_path, '--met-file', sum_path]
            print(bowtie_args)

                


            subprocess.call(bowtie_args)
            final_unaligned_reads.append(unaligned_reads_path)
        return final_unaligned_reads

workflow_manager(sys.argv[1])