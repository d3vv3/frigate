import json
import os.path
import shutil
import subprocess
import tempfile

from jinja2 import Environment, FileSystemLoader
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from frigate import DOTFILE_NAME, TEMPLATES_PATH
from frigate.utils import flatten

yaml = YAML()


def load_chart(chartdir, root=None, helm_docs=False):
    """Load the yaml information from a Helm chart directory.

    Load in the `Chart.yaml` and `values.yaml` files from a Helm
    chart.

    Args:
        chartdir (str): Path to the Helm chart.
        root (list, optional): The root of the namespace we are currently at. Used for recursion.
        helm_docs (bool): Use helm-docs style comments

    Returns:
        chart (dict): Contents of `Chart.yaml` loaded into a dict.
        values (dict): Contents of `values.yaml` loaded into a dict.

    """
    with open(os.path.join(chartdir, "values.yaml"), "r") as fh:
        values = yaml.load(fh.read())
    with open(os.path.join(chartdir, "values.yaml")) as f:
        lines = f.read().splitlines()
    with open(os.path.join(chartdir, "Chart.yaml"), "r") as fh:
        chart = yaml.load(fh.read())
    try:
        with open(os.path.join(chartdir, "Chart.lock"), "r") as fh:
            lock = yaml.load(fh.read())
    except FileNotFoundError:
        lock = {}
    return (
        chart,
        lock,
        list(
            traverse(
                values,
                lines,
                root=root,
                helm_docs=helm_docs,
            )
        ),
    )


def load_chart_with_dependencies(chartdir, root=None, recursive=False, helm_docs=False):
    """
    Load and return dictionaries representing Chart.yaml and values.yaml from
    the Helm chart. If Chart.yaml declares dependencies, recursively merge in
    their values as well.

    Args:
        chartdir (str): Path to the Helm chart.
        root (list, optional): The root of the namespace we are currently at. Used for recursion.
        recursive (bool): Recursively load values from dependencies further from one level.
        helm_docs (bool): Use helm-docs style comments.

    Returns:
        chart (dict): Contents of `Chart.yaml` loaded into a dict.
        values (dict): Contents of `values.yaml` loaded into a dict.
    """
    if root is None:
        root = []
    chart, lock, values = load_chart(chartdir, root=root, helm_docs=helm_docs)
    if "dependencies" in (lock or chart):
        # update the helm chart's charts/ folder
        update_chart_dependencies(chartdir)

        # recursively update values by unpacking the helm charts in the charts/ folder
        for dependency in lock["dependencies"]:
            dependency_name = dependency["name"]
            dependency_path = os.path.join(
                chartdir,
                "charts",
                f"{dependency_name}-{dependency['version']}.tgz",
            )
            with tempfile.TemporaryDirectory() as tmpdirname:
                shutil.unpack_archive(dependency_path, tmpdirname)
                dependency_dir = os.path.join(tmpdirname, dependency_name)

                if not recursive:
                    _, _, dependency_values = load_chart(
                        dependency_dir, root + [dependency_name], helm_docs=helm_docs
                    )
                else:
                    _, _, dependency_values = load_chart_with_dependencies(
                        dependency_dir, root + [dependency_name], helm_docs=helm_docs
                    )
                values = squash_duplicate_values(values + dependency_values)

    return chart, lock, values


def squash_duplicate_values(values):
    """Remove duplicates from values.

    If a value has already been defined remove future values.

    Args:
        values (list): List of value tuples.

    Returns:
        values (list): List of value tuples with duplicated removed.

    """
    tmp = {}
    for item in values:
        if item[0] not in tmp:
            tmp[item[0]] = (item[1], item[2])
    return [(key, tmp[key][0], tmp[key][1]) for key in tmp]


def update_chart_dependencies(chart_path):
    """Update a helm charts local cache of dependencies.

    In order to generate a values table including dependencies we need
    all dependencies to be checked out locally. For each chart we are generating
    values for we will call ``helm dep update <chart>``.

    Args:
        chart_path (string): Path to the directory containing the helm chart
                             with dependencies to update to its charts/ folder.

    """
    if shutil.which("helm") is None:
        raise RuntimeError(
            "Unable to locate `helm` command which is needed for updating dependencies. "
            "Please ensure `helm` is installed and available on the path. "
            "Alternatively run frigate again with the `--no-deps` flag to skip generating "
            "value table entried for dependencies."
        )
    subprocess.check_call(
        ["helm", "dep", "update", "."],
        cwd=chart_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return None


def get_inline_comment(tree, key):
    """Extract the in-line comment from a ruamel.yaml.comments.Comment list.

    When ruamel.yaml parses a YAML file it also extracts a ruamel.yaml.comments.Comment
    object for each item. This is a list of CommentToken objects which represent comments
    adjacent to the item.

    This function attempts to extract the comment which is on the same line as the item.

    Examples:
        Extract a comment

        >>> from ruamel.yaml import YAML
        >>> yaml = YAML()
        >>> tree = yaml.load("hello: world  # this is the comment")
        >>> get_inline_comment(tree, "hello")
        "This is the comment"

    Args:
        comments (list): List of CommentToken objects (potentially nested)

    Returns:
        str: Comment

    """
    comments = tree.ca.items[key]
    linecol = tree.lc.data[key]
    for comment in flatten(comments):
        if isinstance(comment, str):
            return clean_comment(comment)
        if comment is not None and comment.start_mark.line == linecol[0]:
            first_line = comment.value.strip().split("\n")[0]
            return clean_comment(first_line)
    return ""


def get_helm_docs_comment(tree, lines, key):
    # TODO: Write documentation and tests
    linecol = tree.lc.data[key]

    # No comment above the key
    if not lines[linecol[0] - 1].strip().startswith("#"):
        return ""

    relevant_comments = []
    found_comment_beggining = False
    current_line = linecol[0] - 1
    while not found_comment_beggining:
        if not lines[current_line].strip().startswith("#"):
            break
        relevant_comments.append(
            clean_comment(lines[current_line].strip().split("\n")[0].strip())
        )
        if lines[current_line].strip().startswith("# --"):
            found_comment_beggining = True
        current_line -= 1

    return (" ").join(relevant_comments[::-1])


def clean_comment(comment):
    """Remove comment formatting.

    Strip a comment from plain comment formatting and helm-docs comment formatting.

    Examples:
        Strip down a comment

        >>> clean_comment("# hello world")
        "hello world"

    Args:
        comment (str): Comment to clean

    Returns:
        str: Cleaned sentence

    """
    return comment.strip("# -- ").strip("# ")


def traverse(tree, lines, root=None, helm_docs=False):
    """Iterate over a tree of configuration and extract all information.

    Iterate over nested configuration and extract parameters, comments and values.

    Parameters will be fully namespaced. Descriptions will be extracted from the inline
    comment. Values will be taken as the default value.

    Examples:
        Traversing the following YAML config would yield this list.

        my:
          config:
            hello: world  # comment to describe the option

        >>> traverse(tree)
        ['my.config.hello', 'Comment to describe the option', 'world']

    Args:
        comment (ruamel.yaml.comments.CommentedMap): Tree of config to traverse.
        root (list, optional): The root of the namespace we are currently at. Used for recursion.

    Yields:
        list(param, comment, value): Each namespaced parameter (str), the comment (str) and value (obj).

    """
    if root is None:
        root = []
    for key in tree:
        default = tree[key]
        if isinstance(default, dict) and default != {}:
            newroot = root + [key]
            for value in traverse(default, lines, root=newroot, helm_docs=helm_docs):
                yield value
        else:
            if isinstance(default, list):
                default = [
                    (dict(item) if isinstance(item, CommentedMap) else item)
                    for item in default
                ]
            if isinstance(default, CommentedMap):
                default = dict(default)
            comment = ""
            if key in tree.ca.items or helm_docs:
                comment = (
                    get_inline_comment(tree, key)
                    if helm_docs is False
                    else get_helm_docs_comment(tree, lines, key)
                )
            param = ".".join(root + [key])
            yield [param, comment, json.dumps(default)]


def gen(
    chartdir, output_format, credits=True, deps=True, recursive=False, helm_docs=False
):
    """Generate documentation for a Helm chart.

    Generate documentation for a Helm chart given the path to a chart and a
    format to write out in.

    Args:
        chartdir (str): Path to Helm chart
        output_format (str): Output format (maps to jinja templates in frigate)
        credits (bool): Show Frigate credits in documentation
        deps (bool): Read values from chart dependencies and include them in the config table
        recursive (bool): Recursively read values from chart dependencies further than one level
        helm_docs (bool): Use helm-docs style comments

    Returns:
        str: Rendered documentation for the Helm chart

    """
    chart, _, values = (
        load_chart_with_dependencies(chartdir, recursive=recursive, helm_docs=helm_docs)
        if deps
        else load_chart(chartdir, helm_docs=helm_docs)
    )

    templates = Environment(loader=FileSystemLoader([chartdir, TEMPLATES_PATH]))
    if os.path.isfile(os.path.join(chartdir, DOTFILE_NAME)):
        template_name = DOTFILE_NAME
    else:
        template_name = f"{output_format}.jinja2"
    template = templates.get_template(template_name)

    return template.render(**chart, values=values, credits=credits)
