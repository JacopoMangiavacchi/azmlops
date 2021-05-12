# azmlops - MLOps in a Script for Azure ML

Minimal MLOps CLI interface tool for submitting Job and Pipeline to Azure ML.

## Introduction

**azmlops** is a minimal MLOps command line interface (CLI) tool to easily submit to Azure ML (AML) Job and Pipeline as AML Experiments and automatically register DataStore and mount these as DataReference and/or Datasets passed as parameters to the Python scripts to be executed with the AML Experiment.

The intent of the tool is to provide an easy and fully **declarative** and **modular** approach to create and submit Job and Pipeline using a single source of truth to configure all the information needed to run completely parametrized Experiments on an AML Compute environment connected to one or more DataStores.

This tool also implement a mechanism for optionally protecting **data immutability** while executing Jobs and Pipelines allowing to run different parametric experimentations with the certainty to always feed the same original input data.

Other main reasons for the development of this tool have been the transparent support for **local test** of jobs and pipeline steps, reducing friction both in execution time and debugging, and the **transparent** capacity to being able to **run full pipelines or to manually submit individual steps** of a pipeline as independent experiments, with no need of reconfiguration or any code changes.

## Install

```bash
$ git clone git@github.com:JacopoMangiavacchi/azmlops.git
$ pip install ./azmlops
```

## Local install from source code

```bash
$ python setup.py install
```

## Usage

This tool receive as single input parameter the path to the YAML file containing the configuration of the Job or Pipeline to run.

```bash
$ azmlops --help
$ azmlops job {local path to job config}.yml
# E.g. ./examples/job_config.yml, which you can create based on ./examples/job_config_example.yml
$ azmlops pipeline {local path to pipeline config}.yml 
# E.g. ./examples/pipeline_config.yml, which you can create based on ./examples/pipeline_config_example.yml
```

Calling the CLI tool with success will return a URL for monitoring in the Azure ML Studio web portal the execution and logs of Experiments about the submitted Jobs or Pipelines.

## Implementation

This tool is implemented in Python 3.8 and it use the Azure ML Python SDK to create and submit data connection and scripts to an AML Compute environment such as a Azure Batch cluster or a VM.

This tool depends on the following requirements, which are installed with it:

```text
azureml
azureml-core
azureml-pipeline
click
pyyaml
```

## Job, Pipeline and Experiment

### What is an Experiment?

An Azure Machine Learning (AML) Experiment represent the collection of *trials* used to validate a user's hypothesis. In the AML SDK, an experiment is represented by the Experiment class and a trial is represented by the Run class.

A *trial* is some specific Python code a data scientist want to submit for execution to an AML Workspace in order to observe/document log, metric and results through the AML Studio Experiment view.

An *Experiment trial* could be a specific **job** described by a single python script or a more complex **pipeline** defining a flow of different jobs to be coordinate as a single end to end experiment.

### Submit a Job Experiment

In order to submit a *Job Experiment trial* for execution to run on a AML Compute environment the following information must be passed to the AML Workspace:

- a main python script file containing the Job code to run
- other optional pythons scripts imported in the main script flow and saved in the same folder
- a definition of the environment and references used by the python scripts
- a list of datastores necessary to execute the script in terms of input and optionally output data necessary to execute the job
- optional parameters to pass to the script

### Python Job script (an example)

This is the core of the *Job Experiment trial* that we want to run in the AML workspace.

>As an example we can start thinking about a simulation of a data preparation job that simply need to copy an input file to an output file.

The python snapshot below implement a simple function that we can easily test locally on any python environment.  This *copy_data* function will receive as parameter both the full path of the input and output files. In the implementation it will create necessary folders and subfolder for the output file and it will finally copy the input file on the output file.

```python
def copy_data(input_file_path, output_file_path):
    """Copy input file to output file"""
    makedirs(path.dirname(output_file_path), exist_ok=True)
    copyfile(input_file_path, output_file_path)
```

Once we test locally this function we may want to eventually create and submit this code to AML as an *Job Experiment* and connect the input and output path parameter to some specific Azure Storage that will contain the real data we want to use for running our job.

In order to execute the *copy_data* function above in the context of a Job Experiment we need to first encapsulate this function in the context of a python script file and parse the parametric information we need.

In the main entry point of our script we will use the standard python ArgumentParser to receive arguments for the following information:

- **--input_path**: the path to the Azure Storage containing the input data we want to connect to the AML Compute environment when running the job
- **--output_path**: the path to the Azure Storage containing the output data we want to connect to the AML Compute environment when running the job
- **--input_file**: the name of the specific file in input_path we want to pass as input to our *copy_data* function
- **--output_file**: the name of the specific file in output_path we want to pass as output to our *copy_data* function

In the snapshot below you can see the full main script and how the arguments are parsed, the input and output path concatenated and finally passed to the *copy_data* function.

```python
from azureml.core import Run
from os import makedirs, path
from shutil import copyfile

def copy_data(input_file_path, output_file_path, run):
    """Copy input file to output file"""
    makedirs(path.dirname(output_file_path), exist_ok=True)
    copyfile(input_file_path, output_file_path)
        

if __name__ == "__main__":
    RUN = Run.get_context()

    # Get Parameters
    PARSER = argparse.ArgumentParser("job")
    PARSER.add_argument("--input_path", type=str, help="input folder", required=True)
    PARSER.add_argument("--output_path", type=str, help="output folder", required=True)
    PARSER.add_argument("--input_file", type=str, help="input file name", required=True)
    PARSER.add_argument("--output_file", type=str, help="output file name", required=True)
    ARGS = PARSER.parse_args()
    
    # Prepare full file paths
    input_file_path = f"{ARGS.input_path}/{ARGS.input_file}"
    output_file_path = f"{ARGS.output_path}/{ARGS.output_file}"
    
    # Call job entry point
    copy_data(input_file_path, output_file_path, RUN)

    RUN.complete()
```

> Advise: the main python script file and the optional other python files used for the job experiment should be saved in a specific folder.

### How an AML Job Experiment connect to data

When executing Jobs and Pipelines as Experiments the AML platform has the capacity to *mount* on Compute engines, independently if VM or Cluster, a virtual file system extension that connect through the Linux FUSE kernel module to any configurable Azure Blob Storage.

This way with the AML SDK it is possible to transparently instruct a Job or a Pipeline Step to mount Blog Storage paths and reference to any file contained in it as local file from the Job script code.

This basically avoid to use specific Azure Storage API in the job or pipeline scripts to download the data on the Compute engine and guarantee transparent migration of these scripts between local and AML Compute Engine execution.

DataStore, DataReference and DataSet are the main classes in the AML Python SDK to configure this feature.

![Data in Azure ML](images/amldata.png)

### DataStore

A DataStore represents a storage abstraction over an Azure Machine Learning storage account. It can be created interactively with the Azure Studio web interface or programmatically in Python with the DataStore class.

Datastores are attached to AML Workspaces and are used to store connection information to Azure Storage services so you can refer to them in Job and Pipeline Experiments by name and don't need to remember the connection information and secret used to connect to the storage services.

Examples of supported Azure Storage services that can be registered as Datastores are:

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

A DataReference represents a specific path in a datastore and can be used to describe how and where data should be made available in an Job or Pipeline Experiment to run.

The path to the data in the datastore can be the root (/), a directory within the datastore, or a file in the datastore.

### DataSet

A Dataset is a reference to data in a Datastore and it is created specifying a specific path to the root (/), a directory within the datastore, or a file in the datastore.

The main difference between a DataSet and a DataReference is that DataSet are mounted through the Linux FUSE kernel module as Read-only volume and therefore they guarantee the **data immutability** pattern when running Jobs and Pipelines.

> The **azmlops** tool use DataSet or DataReference for Input data and DataReference for output data.

### YAML Configuration file for Job

This **azmlops** CLI tool utilize a **single YAML file** for configuring all the following necessary information needed to submit and run an Job as an Experiment in AML:

- An experiment name
- The AML Workspace connection information
- The AML Compute to use to run the experiment
- The python Environment to use to run the job and the list of dependencies
- The path to the script folder and the main script file in that folder that implement the code of the job
- The list of input and output data, in terms of DataSet and DataReference, to be created and mounted in the AML Compute environment when running the job experiment

> Example of the Job YAML configuration file needed for the *copy_data* sample above:

```yaml
---
name: Copy_Data_Job

provider: 
  azureml:
    workspace:
      subscription_id: subscription_id
      resource_group: resource_group
      workspace_name: workspace_name
    compute_name: cluster

job:
  code:
    folder: copy_data_scripts
    main: main.py
  inputs:
  - input_data
  outputs:
  - output_data
  parameters:
    input_file: test.txt
    output_file: test1.txt
  environment:
    name: experiment_env
    dependencies:
    - python=3.7
    - pip:
      - azureml-defaults

data:
  input_data:
    type: dataset
    parameter_name: input_path
    mount_path: input
    datastore:
      name: input_datastore
  output_data:
    type: datareference
    parameter_name: output_path
    mount_path: output
    datastore:
      name: output_datastore
```

> Note that the **parameter_name** (input_path, output_path) and **parameters** keys (input_file, output_file) correspond to the arguments parsed with ArgumentParser in the Job python script file main entry point.

The **azmlops** tool can utilize datastores already registered to the AML Workspace or directly create and register new one passing to the datastore parameter of the YAML file above also the following information:

```yaml
...
      datastore:
        name: input_datastore
        container_name: container
        account_name: account
        account_key: xxx
...
```

 Azure Tenant Id and a boolean value to force interactive login can be also configured for the *azureml* provider configuration:

```yaml
...
provider: 
  azureml:
    tenant_id: tenant_id
    force_login: false
    workspace:
      subscription_id: subscription_id
      resource_group: resource_group
      workspace_name: workspace_name
    compute_name: cluster
...
```

### YAML Job fields documentation

- **name**: is the name of the Experiment to run this Job
- **provider**: *azmlops* is designed to potentially support different ML orchestrator such as Azure ML, KubeFlow or other providers.
  - **azureml** is the only ML provider type supported at the moment. It require the following information:
    - **tenant_id**: Azure Tenant Id to connect to
    - **force_login**: boolean value. If True force interactive login
    - **workspace**: contain information about how to connect to the AML Workspace. These information could be retrieved from the Azure Portal on the main configuration page of the AML Workspace instance.
    - **compute_name**: is the name of the AML Compute cluster or VM to use from the ones configured in the AML Workspace.
- **environment**: is the placeholder for a classic conda environment yaml file that contain the list of all dependencies
- **scripts**: contain path to the script folder and the name of the main script file in that folder
- **data**: contain the list of all input and output datareference / dataset and associated datastore to be created for the job experiment. Use *dataset* for unmutable input data and *datareference* for writable input or output data.
    - the following fields must be configured for each data element independently if *dataset* or *datareference*:
        - **name**: a unique name for the data element. To be used for Pipeline I/O and step sequencing
        - **parameter_name**: name of the parameter to be passed to the main python script file of the job for the mounting path associated to the corresponding *dataset* or *datareference*
        - **mount_path**: the path to be used for mounting a specific folder of the associated *datastore*
        - **datastore**: the associated datastore
          - **name**: unique name in the context of a AML Workspace to identify a *datastore*
          - **container_name**: name of the Blog Storage container to be registered for the DataStore
          - **account_name**: is the name of the Azure Blob Storage to use
          - **account_key**: is the security key to access the "account_name" Azure Blob Storage
- **parameters**: list of parameter name and value touples to pass to the job script.

## Pipeline

### What is a Pipeline?

A Machine Learning pipeline is an independently executable workflow of a complete end to end machine learning operation. Individual jobs are encapsulated as a series of **steps** within the pipeline.

An Azure Machine Learning Pipeline can be as simple as one that calls a single Python script, just like a Job, or as a flow of different jobs or steps such as:

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

Finally, Pipeline are submitted for execution to run on a AML Compute environment as part of an Experiment.

### Modularity and Transparent execution of Steps as Experiments or full Pipeline

A fundamental element in the design of the **azmlops** tool is the complete reusability of Job resources such as the Python script files and folders that could be transparently reused and submitted as individual Job or as sequence of steps of a more complex Pipeline.

### How an AML Pipeline Experiment connect to data

As for Job Experiment the AML platform when executing all steps of a pipeline use the same Linux FUSE kernel module to mount Blog Storage paths and reference to any file contained in it as local file from the Job script code.

Other than DataReference and DataSet pipelines also support a special kind of data object to manage the passage of data between the different steps of a pipeline.  The PipelineData class in the AML Python SDK implement this feature.

Through the use of DataReference the AML infrastructure, when executing a pipeline, is able to automatically understand the details of the Directed Acyclic Graph behind the pipeline logic and understand implicitly what steps can be executed in parallel or sequentially.

### PipelineData

A PipelineData represents a temporary path in a datastore created automatically by the AML pipeline execution. This path can be passed to the step python code as a parameter exactly like DataReference and DataSet path are passed to job experiment.  There is nothing special that the python script file need to do differently for PipelineData.

> PipelineData is the only mechanism supported for passing data between different steps of a pipeline.

As a single PipelineData by definition could be used as output of one step and as input of another step this **azmlops** tool allows to specify two distinct parameter name, one for the input and one for the output, for each PipelineData configured.

### YAML Configuration file for Pipeline

This **azmlops** CLI tool utilize a **single YAML file** for configuring all the following necessary information needed to submit and run a Pipeline as AML Experiment:

- A pipeline name
- The AML Workspace connection information
- The AML Compute to use to run the experiment
- For all the steps of a pipeline:
  - The python Environment to use to run the job and the list of dependencies
  - The path to the script folder and the main script file in that folder that implement the code of the job
  - The list of input and output data, in terms of DataSet, DataReference and DataPipeline to be created and mounted in the AML Compute environment when running the job experiment

> Example of a pipeline YAML configuration file reusing the same  *copy_data* sample script used in an Job Experiment above in two different steps of a single pipeline:

```yaml
---
name: Copy_Data_Pipeline

provider: 
  azureml:
    workspace:
      subscription_id: subscription_id
      resource_group: resource_group
      workspace_name: workspace_name
    compute_name: cluster

jobs:
- copy_data1:
    code:
      folder: copy_data_scripts
      main: main.py
    inputs:
    - input_data
    outputs:
    - pipeline_data
    parameters:
      input_file: test.txt
      output_file: test1.txt
    environment: experiment_env
- copy_data2:
    code:
      folder: copy_data_scripts
      main: main.py
    inputs:
    - pipeline_data
    - output_data
    parameters:
      input_file: test1.txt
      output_file: output2.txt
    environment: experiment_env

data:
  input_data:
    type: datareference
    parameter_name: input_path
    mount_path: input
    datastore:
      name: input_datastore
  output_data:
    type: datareference
    parameter_name: output_path
    mount_path: output
    datastore:
      name: output_datastore
  pipeline_data:
    type: pipelinedata
    input_parameter_name: input_path
    output_parameter_name: output_path
    datastore:
      name: output_datastore

environments:
  experiment_env:
    name: experiment_env
    dependencies:
    - python=3.7
    - pip:
      - azureml-defaults
```

> Note that the same python script we used before to physically copy a file from a source path to a definition path is execute in two different steps. The PipelineData object will allow to copy on a temporary path and pass this information as output of the first step and input of the second step.

> Note in particular how the two different parameter name for the same PipelineData object allows to transparently reuse the same python script with the same parameter name for the two tasks.

The image below shows the final AML Pipeline built from the pipeline configuration above.  

![Copy Data Pipeline](images/pipeline.png)

> Note how through the usage of PipelineData the AML runtime is able to understand that the two steps copy_data1 and copy_data2 have to be executed in sequence and not in parallel.

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
