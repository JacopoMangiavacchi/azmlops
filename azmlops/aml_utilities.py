import yaml
import tempfile
from azureml.core import Workspace, Datastore, Dataset
from azureml.core import ScriptRunConfig, Experiment, ComputeTarget, Environment
from azureml.data.data_reference import DataReference
from azureml.core.authentication import InteractiveLoginAuthentication

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

def connect_datareference(ws, input_data_object):
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
        data_reference_name=f"{input_data_object['name']}_reference",
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

    for x in configuration["data"]:
        x = list(x.items())[0]
        data_name = x[0]
        input_data_object = x[1]
        if input_data_object["type"] == "dataset":
            data[data_name] = connect_dataset(ws, input_data_object)

        if input_data_object["type"] == "datareference":
            data[data_name] = connect_datareference(ws, input_data_object)

    return data

def get_env(configuration):
    """
    Setup Environment to execute the job
    writing temporary Env file
    """
    with tempfile.NamedTemporaryFile(delete=True) as fp:
        environment = configuration["job"]["environment"]
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

            if data_object["type"] == "dataset":
                arguments.append(f"--{configuration["data"][data_name]['parameter_name']}")
                arguments.append(data_object["dataset_object"].as_named_input(f"{configuration["data"][data_name]['datastore']['name']}_input").as_mount())
            else:
                arguments.append(f"--{configuration["data"][data_name]['parameter_name']}")
                arguments.append(str(data_object["datareference_object"]))

    if "outputs" in job:
        for data_name in job["outputs"]:
            data_object = data[data_name]

            arguments.append(f"--{configuration["data"][data_name]['parameter_name']}")
            arguments.append(str(data_object["datareference_object"]))

    if "parameters" in job:
        for parameter in job["parameters"].items():
            arguments.append(f"--{parameter[0]}")
            arguments.append(parameter[1])

    return arguments

def submit_job(ws, configuration, data, env):
    """
    Create and Submit the Job as AML Experiment
    """
    # Connect to Compute Cluster or VM
    cluster = ws.compute_targets[configuration["compute_name"]]

    # Create the AML Experiment
    experiment = Experiment(ws, configuration["name"])

    job = configuration["job"]

    # Create the job
    job_object = ScriptRunConfig(
        source_directory = job["scripts"]["folder"],
        script = job["scripts"]["main"],
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
