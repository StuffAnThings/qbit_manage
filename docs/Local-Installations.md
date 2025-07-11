# Local Installations

Below is a simple high level set of instructions for cloning the repository and executing qbit_manage

* Requires `python 3.9.0`. Dependencies must be installed by running:

Navigate to the directory you'd liked to clone the repo into

Clone the repo

```bash
git clone https://github.com/StuffAnThings/qbit_manage
```

Install requirements

```bash
pip install .
```

If there are issues installing dependencies try:

```bash
pip install . --ignore-installed
```

## Usage

To run the script in an interactive terminal run:

* copy the `config.yml.sample` file to `config.yml`
* Fill out the config file as outlined in the [Config-Setup](https://github.com/StuffAnThings/qbit_manage/wiki/Config-Setup)

Run the script `-h` to see a list of commands

```bash
python qbit_manage.py -h
```

### Web API and Web UI

To run the Web API and Web UI, use the `--web-server` flag:

```bash
python qbit_manage.py --web-server
```

You can then access the Web UI in your browser, typically at `http://localhost:8080`.

### Config

To choose the location of the YAML config file

```bash
python qbit_manage.py --config-file <path_to_config>
```

### Log

To choose the location of the Log File

```bash
python qbit_manage.py --log-file <path_to_log>
```
