from azureml.core import Run
from os import makedirs, path
from shutil import copyfile

def prepare_data(input_file_path, output_file_path, run):
    """
    Copy input file to output file
    """
    
    run.log("Experiment Start", 1)
    
    with open(input_file_path, 'r') as reader:
        print(f"Input file Data: {reader.read()}")

    makedirs(path.dirname(output_file_path), exist_ok=True)
    copyfile(input_file_path, output_file_path)
        
    run.log("Experiment End", 2)


if __name__ == "__main__":
    RUN = Run.get_context()

    # Get Parameters
    PARSER = argparse.ArgumentParser("experiment")
    PARSER.add_argument("--input_path", type=str, help="input data", required=True)
    PARSER.add_argument("--output_path", type=str, help="output data", required=True)
    PARSER.add_argument("--input_file", type=str, help="input file name", required=True)
    PARSER.add_argument("--output_file", type=str, help="output file name", required=True)

    ARGS = PARSER.parse_args()
    
    # Prepare full file paths
    input_file_path = f"{ARGS.input_path}/{ARGS.input_file}"
    output_file_path = f"{ARGS.output_path}/{ARGS.output_file}"
    
    print(f"Input file: {input_file_path}")
    print(f"Output file: {output_file_path}")
    
    # Call experiment entry point
    prepare_data(input_file_path, output_file_path, RUN)

    RUN.complete()
