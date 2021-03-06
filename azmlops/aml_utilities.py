import yaml
import tempfile
from azureml.core import Workspace, Datastore, Dataset
from azureml.core import ScriptRunConfig, Experiment, ComputeTarget, Environment
from azureml.data.data_reference import DataReference
from azureml.core.authentication import InteractiveLoginAuthentication
from azureml.pipeline.core import Pipeline, PipelineData
from azureml.pipeline.steps import PythonScriptStep
from azureml.core.runconfig import RunConfiguration

def get_configuration(config: str) -> dict:
    """
    Open Config YAML file
    """
    with open(config) as f:
        configuration = yaml.load(f, Loader=yaml.FullLoader)
    return configuration

def connect_workspace(configuration: dict) -> Workspace:
    """
    Connect to AML Workspace
    """
    azureml = configuration["provider"]["azureml"]

    force = False
    if "force_login" in azureml:
        force = azureml["force_login"]

    if "tenant_id" in azureml:
        interactive_auth = InteractiveLoginAuthentication(tenant_id=azureml["tenant_id"], force=force)
    else:
        interactive_auth = None

    return Workspace(
        subscription_id=azureml["workspace"]["subscription_id"],
        resource_group=azureml["workspace"]["resource_group"],
        workspace_name=azureml["workspace"]["workspace_name"],
        auth=interactive_auth
    )

def register_datastore(ws: Workspace, datastore: dict) -> None:
    """
    Register a Datastore if container_name, account_name and account_key are provided
    """
    if "container_name" in datastore and "account_name" in datastore and "account_key" in datastore:
        Datastore.register_azure_blob_container(
            workspace=ws, 
            datastore_name=datastore["name"],
            container_name=datastore["container_name"],
            account_name=datastore["account_name"],
            account_key=datastore["account_key"],
            create_if_not_exists=False)

def connect_dataset(ws: Workspace, input_data_object: dict) -> dict:
    """
    Connect a Dataset and optionally register associated Datastore
    """
    # Register DataStore
    datastore = input_data_object["datastore"]
    register_datastore(ws, datastore)
    datastore_object = Datastore(ws, datastore["name"])

    # Create Datasets for input Datastore
    dataset_object = Dataset.File.from_files(
        path=(datastore_object, input_data_object["mount_path"])
    )

    return { 
        "type" : input_data_object["type"],
        "datastore_object" : datastore_object,
        "dataset_object" : dataset_object
    }

def connect_datareference(ws: Workspace, input_data_object: dict, data_name: str) -> dict:
    """
    Connect a DataReference and optionally register associated Datastore
    """
    # Register DataStore
    datastore = input_data_object["datastore"]
    register_datastore(ws, datastore)
    datastore_object = Datastore(ws, datastore["name"])

    # Create DataReference for output Datastore
    datareference_object = DataReference(
        datastore=datastore_object,
        data_reference_name=f"{data_name}_reference",
        path_on_datastore=input_data_object["mount_path"]
    )

    return { 
        "type" : input_data_object["type"],
        "datastore_object" : datastore_object,
        "datareference_object" : datareference_object
    }

def connect_pipelinedata(ws: Workspace, input_data_object: dict, data_name: str) -> dict:
    """
    Connect a PipelineData and optionally register associated Datastore
    """
    # Register DataStore
    datastore = input_data_object["datastore"]
    register_datastore(ws, datastore)
    datastore_object = Datastore(ws, datastore["name"])

    # Create PipelineData for output Datastore
    pipelinedata_object = PipelineData(f"{data_name}_pipelinedata", datastore=datastore_object)
    
    return { 
        "type" : input_data_object["type"],
        "datastore_object" : datastore_object,
        "pipelinedata_object" : pipelinedata_object
    }

def connect_all_data(ws: Workspace, configuration: dict) -> dict:
    """
    Connect DataReference and Dataset and optionally register associated Datastore
    """
    data = {}

    for _, (data_name, input_data_object) in enumerate(configuration["data"].items()):
        if input_data_object["type"] == "dataset":
            data[data_name] = connect_dataset(ws, input_data_object)
        if input_data_object["type"] == "datareference":
            data[data_name] = connect_datareference(ws, input_data_object, data_name)
        if input_data_object["type"] == "pipelinedata":
            data[data_name] = connect_pipelinedata(ws, input_data_object, data_name)

    return data

def get_env(environment: dict) -> Environment:
    """
    Setup Environment to execute the job
    writing temporary Env file
    """
    with tempfile.NamedTemporaryFile(delete=True) as fp:
        with open(fp.name, 'w') as outfile:
            yaml.dump(environment, outfile, default_flow_style=False)
        env = Environment.from_conda_specification(
            name=environment["name"],
            file_path=fp.name
        )
    return env

def get_arguments(job: dict, configuration: dict, data: dict) -> list:
    """
    Create script arguments based on Configuration
    """
    arguments = []

    if "inputs" in job:
        for data_name in job["inputs"]:
            data_object = data[data_name]
            data_config = configuration["data"][data_name]

            if data_object["type"] == "dataset":
                arguments.append(f"--{data_config['parameter_name']}")
                arguments.append(data_object["dataset_object"].as_named_input(f"{data_config['datastore']['name']}_input").as_mount())
            if data_object["type"] == "datareference":
                arguments.append(f"--{data_config['parameter_name']}")
                arguments.append(str(data_object["datareference_object"]))

    if "outputs" in job:
        for data_name in job["outputs"]:
            data_object = data[data_name]
            data_config = configuration["data"][data_name]

            arguments.append(f"--{data_config['parameter_name']}")
            arguments.append(str(data_object["datareference_object"]))

    if "parameters" in job:
        for parameter in job["parameters"].items():
            arguments.append(f"--{parameter[0]}")
            arguments.append(parameter[1])

    return arguments

def submit_job(ws: Workspace, configuration: dict, data: dict) -> str:
    """
    Create and Submit the Job as AML Experiment
    """
    azureml = configuration["provider"]["azureml"]
    job = configuration["job"]

    # Connect to Compute Cluster or VM
    cluster = ws.compute_targets[azureml["compute_name"]]

    # Setup Environment to execute the job
    # writing temporary Env file
    env = get_env(job["environment"])

    # Create the AML Experiment
    experiment = Experiment(ws, configuration["name"])

    # Create the job
    job_object = ScriptRunConfig(
        source_directory = job["code"]["folder"],
        script = job["code"]["main"],
        arguments = get_arguments(job, configuration, data),
        compute_target = cluster)

    # Connect DataReferences
    if "inputs" in job:
        for data_name in configuration["job"]["inputs"]:
            data_object = data[data_name]
            if data_object["type"] == "datareference":
                job_object.run_config.data_references[data_object["datareference_object"].data_reference_name] = data_object["datareference_object"].to_config()

    if "outputs" in job:
        for data_name in configuration["job"]["outputs"]:
            data_object = data[data_name]
            if data_object["type"] == "datareference":
                job_object.run_config.data_references[data_object["datareference_object"].data_reference_name] = data_object["datareference_object"].to_config()

    # Config Environment
    job_object.run_config.environment = env

    # Submit the Experiment job
    run = experiment.submit(job_object)

    return run.get_portal_url()

def get_inputs(job: dict, configuration: dict, data: dict) -> list:
    """
    Get list of input Datareference and Dataset
    """
    inputs = []

    if "inputs" in job:
        for data_name in job["inputs"]:
            data_object = data[data_name]
            data_config = configuration["data"][data_name]

            if data_object["type"] == "dataset":
                inputs.append(data_object["dataset_object"].as_named_input(f"{data_config['datastore']['name']}_input").as_mount())
            if data_object["type"] == "datareference":
                inputs.append(data_object["datareference_object"])
            if data_object["type"] == "pipelinedata":
                inputs.append(data_object["pipelinedata_object"])

    return inputs

def get_outputs(job: dict, configuration: dict, data: dict) -> list:
    """
    Get list of output Datareference
    """
    outputs = []

    if "outputs" in job:
        for data_name in job["outputs"]:
            data_object = data[data_name]
            outputs.append(data_object["pipelinedata_object"])

    return outputs

def get_arguments_step(job: dict, configuration: dict, data: dict) -> list:
    """
    Create script arguments based on Configuration
    """
    arguments = []

    if "inputs" in job:
        for data_name in job["inputs"]:
            data_object = data[data_name]
            data_config = configuration["data"][data_name]

            if data_object["type"] == "dataset":
                arguments.append(f"--{data_config['parameter_name']}")
                arguments.append(data_object["dataset_object"].as_named_input(f"{data_config['datastore']['name']}_input").as_mount())
            if data_object["type"] == "datareference":
                arguments.append(f"--{data_config['parameter_name']}")
                arguments.append(str(data_object["datareference_object"]))
            if data_object["type"] == "pipelinedata":
                arguments.append(f"--{data_config['input_parameter_name']}")
                arguments.append(str(data_object["pipelinedata_object"]))

    if "outputs" in job:
        for data_name in job["outputs"]:
            data_object = data[data_name]
            data_config = configuration["data"][data_name]

            if data_object["type"] == "datareference":
                arguments.append(f"--{data_config['parameter_name']}")
                arguments.append(str(data_object["datareference_object"]))
            if data_object["type"] == "pipelinedata":
                arguments.append(f"--{data_config['output_parameter_name']}")
                arguments.append(str(data_object["pipelinedata_object"]))

    if "parameters" in job:
        for parameter in job["parameters"].items():
            arguments.append(f"--{parameter[0]}")
            arguments.append(parameter[1])

    return arguments

def create_step(ws: Workspace, configuration: dict, data: dict, job_name: str, job_data: dict, cluster: ComputeTarget) -> PythonScriptStep:
    """
    Create an AML Pipeline step
    """
    # Setup Environment to execute the job
    # writing temporary Env file
    env = get_env(configuration["environments"][job_data["environment"]])

    # create a new runconfig object
    run_config = RunConfiguration()

    # Config Environment
    run_config.environment = env

    # Create the step
    step = PythonScriptStep(name=job_name,
                            script_name=job_data["code"]["main"], 
                            source_directory=job_data["code"]["folder"],
                            compute_target=cluster,
                            arguments = get_arguments_step(job_data, configuration, data),
                            inputs = get_inputs(job_data, configuration, data),
                            outputs = get_outputs(job_data, configuration, data),
                            allow_reuse=False,
                            runconfig=run_config)

    return step

def submit_pipeline(ws: Workspace, configuration: dict, data: dict) -> str:
    """
    Create and Submit the Pipeline as AML Experiment
    """
    azureml = configuration["provider"]["azureml"]
    jobs = configuration["jobs"]

    # Connect to Compute Cluster or VM
    cluster = ws.compute_targets[azureml["compute_name"]]

    # Create all pipeline steps
    steps = []
    for job in jobs:
        job_name, job_data = list(job.items())[0]
        steps.append(create_step(ws, configuration, data, job_name, job_data, cluster))

    # Create Pipeline
    pipeline = Pipeline(ws, steps=steps)
    
    # Validate Pipeline
    pipeline.validate()
    
    # Publish Pipeline
    published_pipeline = pipeline.publish(name=configuration["name"])
    print(f"The published pipeline ID is {published_pipeline.id}")

    # Submit Pipeline via AML Experiment
    experiment = Experiment(ws, f"{configuration['name']}_Experiment")

    # Submit the Experiment job
    run = experiment.submit(pipeline)

    return run.get_portal_url()
