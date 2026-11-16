# Contributing to "eutaxis"

> [!IMPORTANT]
> To contribute effectively, please conform to those guidelines and use the provided templates.

## Submitting Issues

To submit a new issue:

1. In the repository page, navigate to the "Issues" tab and click on "New Issue".
2. Select and fill the issue template.
3. Add relevant labels, assignees, and milestone if applicable.

## Developing the Code

Contributions to the codebase should be developed in a local clone of the repository. Follow these steps to set up a development environment:

### Installation

1. Initialize a local copy of the repository:

   ```sh
   cd /path/to/local/directory
   git clone git@github.com:eresther/eutaxis.git
   ```

2. Create a virtual environment containing the development dependencies:

   ```sh
   cd  eutaxis
   conda env create -f environment.yml
   ```

   By default, the environment will be named `eutaxis`, as specified in the `environment.yml` file. This name can be modified by passing the `-n` option.

3. Register the packages in "editable mode":

   ```sh
   conda activate eutaxis
   pip install -e ".[dev]"
   ```

### Using the Commit Message Template

1. Edit the commit template (`.gitmessage`, at the root of the repository) to specify the name and email address of the committer.

2. Configure `git` to use this file as a commit template:

   ```sh
   git config commit.template .gitmessage
   ```

3. Verify the configuration:

   ```sh
   git config --get commit.template
   ```

### Commit Message Format

> [!NOTE]
> To write a commit message with this template, adhere to the following format:

- Capitalize the subject, do not add a period at the end
- Limit the subject line to 50 characters
- Use the imperative mood in the subject line
- Separate subject from body with a blank line
- Wrap the body at 72 characters per line
- Use the body to explain what and why (not how)
- Add references to issues or other commits using [GitHub keywords](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/using-keywords-in-issues-and-pull-requests)

## Configuration file organization

The project configures its build, dependencies and active tools in the project file `pyproject.toml`:

- the table `[build-system]` selects the build backend;
- the table `[project]` and its subtables declare package metadata, dependencies and entry points;
- the tables `[tool.setuptools]`, `[tool.black]` and `[tool.pytest.ini_options]` configure their named tools.

MyPy uses its defaults because no separate MyPy configuration file exists.
