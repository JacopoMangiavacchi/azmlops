import sys
import click
from aml_utilities import get_configuration, connect_workspace, register_datastores, connect_datastores, get_env, get_arguments, submit_experiment


@click.group()
@click.version_option("1.0.0")
def main():
    """Minimal MLOps CLI interface tool for submitting Experiments and Pipelines to Azure ML"""
    pass


@main.command()
@click.argument('experiment', required=True)
def experiment(**kwargs):
    """Submit an ML Experiment to an Azure ML Workspace"""
    config = kwargs.get("experiment")

    click.echo(f"Submitting Experiment {config} ...")

    # Open Experiment Config YAML file
    configuration = get_configuration(config)

    # Connect to AML Workspace
    ws = connect_workspace(configuration)

    # Connect and optionally Register Datastores
    datastores = connect_datastores(ws, configuration)

    # Setup Environment to execute the experiment
    # writing temporary Env file
    env = get_env(configuration)

    # Create and Submit the AML Experiment
    url = submit_experiment(ws, configuration, datastores, env)

    click.echo(f"Experiment submitted: {url}")



@main.command()
@click.argument('pipeline', required=True)
def pipeline(**kwargs):
    """Submit an ML Pipeline to an Azure ML Workspace"""
    config = kwargs.get("pipeline")
    
    click.echo("Not implemented yet.")


if __name__ == '__main__':
    args = sys.argv
    if "--help" in args or len(args) == 1:
        print("az-mlops")
    main()
