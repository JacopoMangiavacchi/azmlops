import yaml
import tempfile
from azureml.core import Workspace, Datastore, Dataset
from azureml.core import ScriptRunConfig, Experiment, ComputeTarget, Environment
from azureml.data.data_reference import DataReference
from azureml.core.authentication import InteractiveLoginAuthentication

def get_configuration(config):
    """
    Open Experiment Config YAML file
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

def register_datastores(ws, datastore):
    """
    Register a Datastore if register is True
    """
    if "register" in datastore and datastore["register"] == True:
        Datastore.register_azure_blob_container(
            workspace=ws, 
            datastore_name=datastore["data_store_name"],
            container_name=datastore["container_name"],
            account_name=datastore["account_name"],
            account_key=datastore["account_key"],
            create_if_not_exists=False)

def connect_datastores(ws, configuration):
    """
    Connect and optionally Register Datastores
    """
    datastores = configuration["datastores"]

    if "input" in datastores:
        for datastore in datastores["input"]:
            # Register Input DataStores
            register_datastores(ws, datastore)
            # Create Datasets for input Datastores
            datastore["datastore"] = Datastore(ws, datastore["data_store_name"])
            datastore["dataset"] = Dataset.File.from_files(
                path=(datastore["datastore"], datastore["mount_path"])
            )

    if "output" in datastores:
        for datastore in datastores["output"]:
            # Register Output DataStores
            register_datastores(ws, datastore)
            # Create DataReference for output Datastores
            datastore["datastore"] = Datastore(ws, datastore["data_store_name"])
            datastore["datareference"] = DataReference(
                datastore=datastore["datastore"],
                data_reference_name=f"{datastore['data_store_name']}_reference",
                path_on_datastore=datastore["mount_path"]
            )

    return datastores

def get_env(configuration):
    """
    Setup Environment to execute the experiment
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

def get_arguments(configuration, datastores):
    """
    Create script arguments based on Configuration loaded from Experiment_Config
    """
    arguments = []

    if "input" in datastores:
        for datastore in datastores["input"]:
            arguments.append(f"--{datastore['parameter_name']}")
            arguments.append(datastore["dataset"].as_named_input(f"{datastore['data_store_name']}_input").as_mount())

    if "output" in datastores:
        for datastore in datastores["output"]:
            arguments.append(f"--{datastore['parameter_name']}")
            arguments.append(str(datastore["datareference"]))

    if "parameters" in configuration:
        for parameter in configuration["parameters"].items():
            arguments.append(f"--{parameter[0]}")
            arguments.append(parameter[1])

    return arguments

def submit_experiment(ws, configuration, datastores, env):
    """
    Create and Submit the AML Experiment
    """
    # Connect to Compute Cluster or VM
    cluster = ws.compute_targets[configuration["compute_name"]]

    # Create the AML Experiment
    experiment = Experiment(ws, configuration["name"])

    # Create the job
    job = ScriptRunConfig(
        source_directory = configuration["scripts"]["folder"],
        script = configuration["scripts"]["main"],
        arguments = get_arguments(configuration, datastores),
        compute_target = cluster)

    # Connect DataReferences
    if "output" in datastores:
        for datastore in datastores["output"]:
            job.run_config.data_references[datastore["datareference"].data_reference_name] = datastore["datareference"].to_config()

    # Config Environment
    job.run_config.environment = env

    # Submit the Experiment job
    run = experiment.submit(job)

    return run.get_portal_url()
