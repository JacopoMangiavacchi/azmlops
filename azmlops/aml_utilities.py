import yaml
import tempfile
from azureml.core import Workspace, Datastore, Dataset
from azureml.core import ScriptRunConfig, Experiment, ComputeTarget, Environment
from azureml.data.data_reference import DataReference
from azureml.core.authentication import InteractiveLoginAuthentication
from azureml.pipeline.core import Pipeline
from azureml.pipeline.steps import PythonScriptStep
from azureml.core.runconfig import RunConfiguration

def get_configuration(config):
    """
    Open Config YAML file
    """
    with open(config) as f:
        configuration = yaml.load(f, Loader=yaml.FullLoader)
    return configuration

def connect_workspace(configuration):
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

def register_datastore(ws, datastore):
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

def connect_dataset(ws, input_data_object):
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

def connect_datareference(ws, input_data_object, data_name):
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

def connect_all_data(ws, configuration):
    """
    Connect DataReference and Dataset and optionally register associated Datastore
    """
    data = {}

    for _, (data_name, input_data_object) in enumerate(configuration["data"].items()):
        if input_data_object["type"] == "dataset":
            data[data_name] = connect_dataset(ws, input_data_object)

        if input_data_object["type"] == "datareference":
            data[data_name] = connect_datareference(ws, input_data_object, data_name)

    return data

def get_env(environment):
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

def get_arguments(configuration, data):
    """
    Create script arguments based on Configuration
    """
    arguments = []
    job = configuration["job"]

    if "inputs" in job:
        for data_name in job["inputs"]:
            data_object = data[data_name]
            data_config = configuration["data"][data_name]

            if data_object["type"] == "dataset":
                arguments.append(f"--{data_config['parameter_name']}")
                arguments.append(data_object["dataset_object"].as_named_input(f"{data_config['datastore']['name']}_input").as_mount())
            else:
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

def submit_job(ws, configuration, data):
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
        arguments = get_arguments(configuration, data),
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

def create_step(ws, configuration, data, job_name, job_data, cluster):
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

    # Connect DataReferences
    for datastore in datastores:
        if datastore["readonly"] == False:
            run_config.data_references = {
                datastore["datareference"].data_reference_name: datastore["datareference"].to_config()
            }

    # Create the step
    step = PythonScriptStep(name=configuration["name"],
                            script_name=configuration["scripts"]["main"], 
                            compute_target=cluster, 
                            source_directory=configuration["scripts"]["folder"],
                            arguments = get_arguments(configuration, datastores),
                            allow_reuse=False,
                            runconfig=run_config)

    return step

def submit_pipeline(ws, configuration, data):
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

    # Publish Pipeline

    # Submit Pipeline

    return "url"
