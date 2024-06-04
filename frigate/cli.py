import click

import frigate.gen
import frigate.pre_commit_hook
from frigate.utils import list_templates


@click.group()
def cli():
    pass


@cli.command()
@click.argument("filename")
@click.option(
    "-o",
    "--output-format",
    "output_format",
    default="markdown",
    help="Output format for the documentation",
    type=click.Choice(list_templates()),
)
@click.option(
    "--no-credits",
    is_flag=True,
    default=True,
    help="Disable the Frigate credits",
)
@click.option(
    "--no-deps",
    is_flag=True,
    default=True,
    help="Do not render dependency values",
)
@click.option(
    "--recursive",
    is_flag=True,
    default=False,
    help="Go deeper than the first level of the chart dependencies",
)
@click.option(
    "--helm-docs",
    is_flag=True,
    default=False,
    help="Use the helm-docs format for the documentation",
)
def gen(
    filename,
    output_format,
    no_credits,
    no_deps,
    recursive,
    helm_docs,
):
    click.echo(
        frigate.gen.gen(
            filename,
            output_format,
            credits=no_credits,
            deps=no_deps,
            recursive=recursive,
            helm_docs=helm_docs,
        )
    )


@cli.command(
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
    )
)
@click.option(
    "--artifact",
    default="README.md",
    help="What file to save the documentation as",
)
@click.option(
    "-o",
    "--output-format",
    "output_format",
    default="markdown",
    help="Output format for the documentation",
    type=click.Choice(list_templates()),
)
@click.option(
    "--no-credits",
    is_flag=True,
    default=True,
    help="Disable the Frigate credits",
)
@click.option(
    "--no-deps",
    is_flag=True,
    default=True,
    help="Do not render dependency values",
)
@click.option(
    "--recursive",
    is_flag=True,
    default=False,
    help="Go deeper than the first level of the chart dependencies",
)
@click.option(
    "--helm-docs",
    is_flag=True,
    default=False,
    help="Use the helm-docs format for the documentation",
)
def hook(artifact, output_format, no_credits, no_deps, recursive, helm_docs):
    frigate.pre_commit_hook.main(
        artifact,
        output_format,
        credits=no_credits,
        deps=no_deps,
        recursive=recursive,
        helm_docs=helm_docs,
    )
