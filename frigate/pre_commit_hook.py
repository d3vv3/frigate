import os
from pathlib import Path

from frigate.gen import gen

"""[pre-commit-hook]
Add features, fix bugs locally with :
```
pre-commit try-repo /path/to/frigate --verbose --all-files
```

https://pre-commit.com/#developing-hooks-interactively

Note : pre-commit creates a virtualenv with the hook

"""


def main(
    output_file,
    format,
    credits=True,
    deps=True,
    recursive=False,
    helm_docs=False,
    skip_helm_update=False,
):
    """Write a README file for discovered Helm chart(s).


    Args:
        output_file (str): Basename of the file to generate
        output_format (str): Output format (maps to jinja templates in frigate)
        credits (bool): Show Frigate credits in documentation
        deps (bool): Read values from chart dependencies and include them in the config table
        recursive (bool): Go deeper than the first level of the chart dependencies
        helm_docs (bool): Use the helm-docs format for the documentation.
        skip_helm_update (bool): Skip helm dependency update before generating the documentation.

    Returns:
        int: How many files were updated by the hook

    """
    dirs = []
    path = os.getcwd()
    name = "Chart.yaml"

    retval = 0
    charts = []

    # Find all the charts
    for root, dirs, files in os.walk(path):
        if name in files:
            charts.append(os.path.join(root, name))

    # For each chart
    for chart in charts:
        chart_location = os.path.dirname(chart)
        frigate_output = gen(
            chart_location,
            format,
            credits=credits,
            deps=deps,
            recursive=recursive,
            helm_docs=helm_docs,
            skip_helm_update=skip_helm_update,
        )
        artifact = Path(chart_location, output_file)
        Path(artifact).touch()
        with open(artifact, "r") as before:
            current_output = before.read()
        if current_output != frigate_output:
            retval += 1
            with open(artifact, "w") as generated:
                generated.write(frigate_output)
    return retval
