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
    force = False
    if "force_login" in configuration:
        force = configuration["force_login"]

    if "tenant_id" in configuration:
        interactive_auth = InteractiveLoginAuthentication(tenant_id=configuration["tenant_id"], force=force)
    else:
        interactive_auth = None

    return Workspace(
        subscription_id=configuration["workspace"]["subscription_id"],
        resource_group=configuration["workspace"]["resource_group"],
        workspace_name=configuration["workspace"]["workspace_name"],
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

def connect_dataset(ws, dataset_type):
    """
    Connect a DataReference or Dataset and optionally register associated Datastore
    """
    # Register DataStore
    datastore = dataset_type["datastore"]
    register_datastore(ws, datastore)
    dataset_type["datastore_object"] = Datastore(ws, datastore["name"])

    # Create Datasets for input Datastore
    dataset_type["dataset_object"] = Dataset.File.from_files(
        path=(dataset_type["datastore_object"], dataset_type["mount_path"])
    )

def connect_datareference(ws, datareference_type):
    """
    Connect a DataReference or Dataset and optionally register associated Datastore
    """
    # Register DataStore
    datastore = datareference_type["datastore"]
    register_datastore(ws, datastore)
    datareference_type["datastore_object"] = Datastore(ws, datastore["name"])

    # Create DataReference for output Datastore
    datareference_type["datareference_object"] = DataReference(
        datastore=datareference_type["datastore_object"],
        data_reference_name=f"{datareference_type['name']}_reference",
        path_on_datastore=datareference_type["mount_path"]
    )

def connect_data(ws, data_type):
    """
    Connect a DataReference or Dataset and optionally register associated Datastore
    """
    if "dataset" in data_type:
        connect_dataset(ws, data_type["dataset"])

    if "datareference" in data_type:
        connect_datareference(ws, data_type["datareference"])

def connect_all_data(ws, configuration):
    """
    Connect DataReference and Dataset and optionally register associated Datastore
    """
    data = configuration["data"]

    if "input" in data:
        for data_type in data["input"]:
            connect_data(ws, data_type)

    if "output" in data:
        for data_type in data["output"]:
            connect_data(ws, data_type)

    return data

def get_env(configuration):
    """
    Setup Environment to execute the job
    writing temporary Env file
    """
    with tempfile.NamedTemporaryFile(delete=True) as fp:
        environment = configuration["environment"]
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

    if "input" in data:
        for d in data["input"]:
            arguments.append(f"--{d['parameter_name']}")
            if d["readonly"] == True:
                arguments.append(d["dataset_object"].as_named_input(f"{d['datastore']['name']}_input").as_mount())
            else:
                arguments.append(str(d["datareference_object"]))

    if "output" in data:
        for d in data["output"]:
            arguments.append(f"--{d['parameter_name']}")
            arguments.append(str(d["datareference_object"]))

    if "parameters" in configuration:
        for parameter in configuration["parameters"].items():
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

    # Create the job
    job = ScriptRunConfig(
        source_directory = configuration["scripts"]["folder"],
        script = configuration["scripts"]["main"],
        arguments = get_arguments(configuration, data),
        compute_target = cluster)

    # Connect DataReferences
    if "input" in data:
        for d in data["input"]:
            if d["readonly"] == False:
                job.run_config.data_references[d["datareference_object"].data_reference_name] = d["datareference_object"].to_config()
    if "output" in data:
        for d in data["output"]:
            job.run_config.data_references[d["datareference_object"].data_reference_name] = d["datareference_object"].to_config()

    # Config Environment
    job.run_config.environment = env

    # Submit the Experiment job
    run = experiment.submit(job)

    return run.get_portal_url()
