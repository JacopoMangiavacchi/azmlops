# azmlops - MLOps in a Script for Azure ML

Minimal MLOps CLI interface tool for submitting Experiments and Pipelines to Azure ML.

## Introduction

**azmlops** is a minimal MLOps command line interface (CLI) tool to easily submit Azure ML (AML) Experiments and Pipelinse and automatically register DataStore and mount these as DataReference and/or Datasets passed as parameters to the Python scripts to be executed with the AML Experiment.

The intent of the tool is to provide an easy and fully **declarative** and **modular** approach to create and submit AML Experiments and Pipeline using a single source of truth to configure all the information needed to run completely parametrized Experiments and Pipelines on an AML Compute environment connected to one or more DataStores.

This tool also implement a mechanism for optionally protecting **data immutability** while executing Experiments and Pipelines allowing to run different parametric experimentations with the certainty to always feed the same original input data.

Other main reasons for the development of this tool have been the transparent support for **local test** of experiments and pipeline steps, reducing friction both in execution time and debugging, and the **transparent** capacity to being able to **run full pipelines or to manually submit individual steps** of a pipeline as independent experiments, with no need of reconfiguration or any code changes.

## Install

```bash
$ pip install azmlops
```

## Command line tool usage

This tool receive as single input parameter the path to the YAML file containing the configuration of the Experiment to run.  If executed without parameter it will prompt for inputing the path of the YAM file.

```bash
$ azmlops --help
$ azmlops experiment path_to_experiment_config.yaml
$ azmlops pipeline path_to_pipeline_config.yaml
```

Calling the CLI tool with success will return a URL for monitoring in the Azure ML Studio web portal the execution and logs of Experiment or Pipeline.

## Implementation

This tool is implemented in Python 3.7 and it use the Azure ML Python SDK to create and submit data connection and scripts to an AML Compute environment such as a Azure Batch cluster or a VM.

This tool depends on the following requirements:

```text
azureml
azureml-core
click
pyyaml
```

## Experiment

### What is an Experiment?

An Azure Machine Learning (AML) Experiment represent the collection of trials used to validate a user's hypothesis.

In the AML SDK, an experiment is represented by the Experiment class and a trial is represented by the Run class.

In order to submit an experiment trial for execution to run on a AML Compute environment the following information must be passed to the Experiment object:

- a main python script file containing the experiment code to run
- other optional pythons scripts imported in the main script flow and saved in the same folder
- a definition of the environments and references used by the python scripts
- a list of datastores necessary to execute the script in terms of input and optionally output data necessary to execute the experiment
- optional parameters to pass to the script

### Python experiment script (an example)

This is the core of the experiment that we want to run in the AML workspace.

>As an example we can start thinking about a simulation of a data preparation experiment that simply need to copy an input file to an output file.

The python snapshot below implement a simple function that we can easily test locally on any python environment.  This *prepare_data* function will receive as parameter both the path of the input and output files. In the implementation it will dump on stdout the content of the input file, it will create necessary folders and subfolder for the output file and it finally copy the input file on the output file.

```python
def prepare_data(input_file_path, output_file_path):
    """Copy input file to output file"""
    with open(input_file_path, 'r') as reader:
        print(f"Input file Data: {reader.read()}")

    makedirs(path.dirname(output_file_path), exist_ok=True)
    copyfile(input_file_path, output_file_path)
```

Once we test locally this function we may want to eventually create and submit this code to AML as an Experiment and connect the input and output path parameter to some specific Azure Storage that will contain the real data we want to use for running our experiment.

In order to execute the *prepare_data* function above in the context of an Experiment we need to first encapsulate this function in the context of a python script file.

In the main entry point of our script we will use then the standard python ArgumentParser to receive arguments for the following information:

- **--input_path**: the path to the Azure Storage containing the input data we want to connect to the AML Compute environment when running the experiment
- **--output_path**: the path to the Azure Storage containing the output data we want to connect to the AML Compute environment when running the experiment
- **--input_file**: the path to the specific file in input_path we want to pass as input to our *prepare_data* function
- **--output_file**: the path to the specific file in output_path we want to pass as output to our *prepare_data* function

In the snapshot below you can see the full main script and how the arguments are parsed, the input and output path concatenated and finally passed to the *prepare_data* function.

```python
from azureml.core import Run
from os import makedirs, path
from shutil import copyfile

def prepare_data(input_file_path, output_file_path, run):
    """Copy input file to output file"""
    with open(input_file_path, 'r') as reader:
        print(f"Input file Data: {reader.read()}")

    makedirs(path.dirname(output_file_path), exist_ok=True)
    copyfile(input_file_path, output_file_path)
        

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
```

> Advise: the main python script file and the optional other python files used for the experiment should be saved in a specific folder.

### How an AML Experiment connect to data

When executing Experiments and Pipelines AML has the capacity to mount on Compute engines, independently if VM or Cluster, a virtual file system extension that connect through the Linux FUSE kernel module to any configurable Azure Blob Storage.

This way with the AML SDK it is possible to transparently instruct an Experiment to mount Blog Storage paths and reference to any file contained in it as local file from the Experiment script code.

This basically avoid to use specific Azure Storage API in the experiment script to download the data on the Compute engine and guarantee transparent migration of these scripts between local and experiment execution.

DataStore, DataReference and DataSet are the main classes in the AML Python SDK to configure this feature.

### DataStore

A DataStore represents a storage abstraction over an Azure Machine Learning storage account. It can be created interactively with the Azure Studio web interface or programmatically in Python with the DataStore class.

Datastores are attached to workspaces and are used to store connection information to Azure storage services so you can refer to them in Experiments and Pipelines by name and don't need to remember the connection information and secret used to connect to the storage services.

Examples of supported Azure storage services that can be registered as datastores are:

- Azure Blob Container
- Azure File Share
- Azure Data Lake
- Azure Data Lake Gen2
- Azure SQL Database
- Azure Database for PostgreSQL
- Databricks File System
- Azure Database for MySQL

> This version of the **azmlops** tool allow the automatic creation of DataStore connected to Azure Blob Container.

### DataReference

A DataReference represents a specific path in a datastore and can be used to describe how and where data should be made available in an Experiment or Pipeline run.

The path to the data in the datastore can be the root /, a directory within the datastore, or a file in the datastore.

### DataSet

As DataReference Dataset is a reference to data in a Datastore and it is created specifying a specific path to the root /, a directory within the datastore, or a file in the datastore.

The main difference between a DataSet and a DataReference is that DataSet are mounted through the Linux FUSE kernel module as Read-only mounting path and therefor they guarantee the **data immutability** pattern when running Experiment and Pipelines.

> The **azmlops** tool use DataSet for Input data and DataReference for output data.

### YAML Configuration file for Experiment

This **azmlops** CLI tool utilize a **single YAML file** for configuring all the following necessary information needed to submit and run an Experiment in AML:

- An experiment name
- The AML Workspace connection information
- The AML Compute to use to run the experiment
- The python Environment to use to run the experiment and the list of dependencies
- The path to the script folder and the main script file in that folder that implement the code of the experiment
- The list of input and output datastores, in term of DataSet and DataReference to be created and mounted in the AML Compute environment when running the experiment

> Example of the experiment YAML configuration file needed for the *prepare_data* sample above:

```yaml
---
name: Test_Experiment_Script
tenant_id: tenantid
force_login: False
workspace:
  subscription_id: subscription_id
  resource_group: resource_group
  workspace_name: workspace_name
compute_name: cluster
environment:
  name: experiment_env
  dependencies:
  - python=3.7
  - pip:
    - azureml-defaults
scripts:
  folder: experiment_scripts
  main: main.py
data:
  input:
    - name: input_data
      data_store_name: input_datastore
      container_name: container
      mount_path: input
      parameter_name: input_path
      register: true
      account_name: account
      account_key: xxx
  output:
    - name: output_data
      data_store_name: output_datastore
      container_name: container
      mount_path: output
      parameter_name: output_path
      register: true
      account_name: account
      account_key: xxx
parameters:
  input_file: test.txt
  output_file: test.txt
```

> Note that the **parameter_name** and **parameters** keys correspond to the argument parsed with ArgumentParser in the experiment  python script file main entry point.

### YAML Experiment fields documentation

- **experiment_name**: is the name of the Experiment or the Pipeline to run as an Experiment on AML
- **tenant_id**: Azure Tenant Id to connect to
- **force_login**: boolean value. If True force interactive login
- **workspace**: contain information about how to connect to the AML Workspace. A config.json file with this information could be downloaded from the Azure Portal on the main configuration page of the AML Service.
- **compute_name**: is the name of the AML Compute cluster or VM to use from the ones configured in the AML Workspace.  Other optional values could be for example "cpucluster" or "dlcluser" (for GPU requirements).
- **environment**: is the placeholder for a classic conda environment yaml file that contain the list of all dependencies
- scripts: contain path to the script folder and the name of the main script file in that folder
- **datastores**: contain the list of all input and output datastore, datareference and dataset to be created for the experiment.
    - the following fields are **mandatory** for each datastore:
        - **name**: a unique name for the data. To be used for Pipeline I/O and step sequencing
        - **data_store_name**: unique name in the context of a AML Workspace to identify a DataStore
        - **parameter_name**: name of the parameter to be passed to the main python script file of the experiment for the mounting path associated to the corresponding DataReference or DataSet
    - the following fields are **optional** for DataStore creation:
        - **register**: true
        - **container_name**: name of the Blog Storage container to be registered for the DataStore
        - **account_name**: is the name of the Azure Blob Storage to use
        - **account_key**: is the security key to access the "account_name" Azure Blob Storage
- parameters: list of parameter name and value touples to pass to the experiments.

## Pipeline

### What is a Pipeline?

An Machine Learning pipeline is an independently executable workflow of a complete machine learning operation. Individual tasks are encapsulated as a series of **steps** within the pipeline.

An Azure Machine Learning Pipeline can be as simple as one that calls a single Python script, just like an Experiment, or as a flow of tasks such as:

- Data preparation including importing, validating and cleaning, munging and transformation, normalization, and staging
- Training configuration including parameterizing arguments, file paths, and logging / reporting configurations
- Training and validating efficiently and repeatedly. Efficiency might come from specifying specific data subsets, different hardware compute resources, distributed processing, and progress monitoring
- Deployment, including versioning, scaling, provisioning, and access control

In the AML SDK, a pipeline is represented by the Pipeline. When creating and running a Pipeline object, the following high-level steps occur:

- For each step, the service calculates requirements for:
  - Hardware compute resources
  - OS resources (Docker image(s))
  - Software resources (Conda / virtualenv dependencies)
  - Data inputs
- The service determines the dependencies between steps, resulting in a dynamic execution graph
  - When each node in the execution graph runs:
  - The service configures the necessary hardware and software environment (perhaps reusing existing resources)
  - The step runs, providing logging and monitoring information to its containing Experiment object
  - When the step completes, its outputs are prepared as inputs to the next step and/or written to storage
  - Resources that are no longer needed are finalized and detached

A Pipeline object contains an ordered sequence of one or more PipelineStep objects.  Each PipelineStep object is configured reusing the same concepts described above for defining DataStorage, DataReference, DataSet, Python environment and script folder and main script file.

Finally, Pipeline are submitted for execution to run on a AML Compute environment  as part of an Experiment.

### Modularity and Transparent execution of Steps as Experiments or full Pipeline

A fundamental element in the design of the **azmlops** tool is the complete reusability of the Python script files and folders that could be transparently reused and submitted as individual Experiment or as sequence of steps of a more complex Pipeline.

### YAML Configuration file for Pipeline

This **azmlops** CLI tool utilize a **single YAML file** for configuring all the following necessary information needed to submit and run a Pipeline in AML:

- A pipeline name
- ...

[WORK IN PROGRESS]

> Example of a pipeline YAML configuration file reusing the same  *prepare_data* sample script used in an Experiment above:

```yaml
---
[WORK IN PROGRESS]
```

### YAML Pipeline fields documentation

[WORK IN PROGRESS]

## CI/CD Integration

While you can use different kind of pipelines like Azure DevOps or GitHub Actions for CI/CD automation of ML tasks, that type of pipeline is not deeply integrated or stored in Azure ML Workspace.

**azmlops** is completely agnostic to any particular integration with CI/CD pipelines but at the same time it has been designed with the specific goal of simplifying and optimizing the integration on both testing and deploying phases on Azure DevOps, GitHub Actions and any similar tool.

### Continuous Integration

#### Unit Test

[WORK IN PROGRESS]

#### Integration Test

[WORK IN PROGRESS]

### Continuous Deployment

[WORK IN PROGRESS]
