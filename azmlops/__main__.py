import sys
import click
from .aml_utilities import get_configuration, connect_workspace, connect_all_data, submit_job, submit_pipeline


@click.group()
@click.version_option("0.0.21")
def main():
    """Minimal MLOps CLI interface tool for submitting Job and Pipeline to Azure ML"""
    pass


@main.command()
@click.argument('job', required=True)
def job(**kwargs):
    """Submit an ML Job to an Azure ML Workspace"""
    config = kwargs.get("job")

    click.echo(f"Submitting Job {config} ...")

    # Open Job Config YAML file
    configuration = get_configuration(config)

    # Connect to AML Workspace
    ws = connect_workspace(configuration)

    # Connect and optionally Register Datastores, Dataset and Datareference
    data = connect_all_data(ws, configuration)

    # Create and Submit the Job as AML Experiment
    url = submit_job(ws, configuration, data)

    click.echo("Job submitted")
    click.echo(f"Experiment URL: {url}")



@main.command()
@click.argument('pipeline', required=True)
def pipeline(**kwargs):
    """Submit an ML Pipeline to an Azure ML Workspace"""
    config = kwargs.get("pipeline")
    
    click.echo(f"Submitting Pipeline {config} ...")

    # Open Job Config YAML file
    configuration = get_configuration(config)

    # Connect to AML Workspace
    ws = connect_workspace(configuration)

    # Connect and optionally Register Datastores, Dataset and Datareference
    data = connect_all_data(ws, configuration)

    # Create and Submit the Pipeline as AML Experiment
    url = submit_pipeline(ws, configuration, data)

    click.echo("Pipeline submitted")
    click.echo(f"Experiment URL: {url}")



if __name__ == '__main__':
    args = sys.argv
    if "--help" in args or len(args) == 1:
        print("az_mlops")
    main()
